"""Alpha04: análisis consultivo de adopción y operación; escenarios no persistidos."""
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from collections import Counter
from math import isfinite
import json
import sqlite3
from .config import database_path
from . import step6 as ops
from .step6_calendar import due_at, local_dt


def read_data(queries, path=None):
    """Una instantánea de lectura. None = fuente no disponible, [] = sin filas."""
    result = {k: None for k in queries}
    try:
        with closing(sqlite3.connect(Path(path or database_path()).resolve().as_uri()+'?mode=ro', uri=True, timeout=3)) as c:
            c.row_factory = sqlite3.Row
            c.execute('PRAGMA query_only=ON'); c.execute('BEGIN')
            for k, q in queries.items():
                try: result[k] = [dict(r) for r in c.execute(q)]
                except sqlite3.Error: pass
    except sqlite3.Error: pass
    return result


def adoption_data(path=None):
    data = read_data({
        'services': '''SELECT s.id,s.codigo,s.nombre,s.responsable_p4,p.owner,p.launch_date,p.approved_at,p.milestones_json,
            a.target_people,a.trained_people,a.enabled_clients,a.active_clients,a.authorized_at
            FROM p5_services s LEFT JOIN p5_plans p ON p.service_id=s.id
            LEFT JOIN p5_adoptions a ON a.service_id=s.id
            WHERE s.demo=0 ORDER BY s.codigo''',
        'routes': 'SELECT r.service_id,r.route_type FROM p5_routes r JOIN p5_services s ON s.id=r.service_id WHERE s.demo=0',
        'activities': 'SELECT a.* FROM p5_activities a JOIN p5_services s ON s.id=a.service_id WHERE s.demo=0',
        'pilots': 'SELECT a.* FROM p5_pilots a JOIN p5_services s ON s.id=a.service_id WHERE s.demo=0',
        'issues': 'SELECT a.* FROM p5_issues a JOIN p5_services s ON s.id=a.service_id WHERE s.demo=0',
    },path)
    routes=data.pop('routes')
    lookup={r['service_id']:r['route_type'] for r in routes or []}
    for row in data['services'] or []:
        row['route_type']=lookup.get(row['id']) if routes is not None else 'Fuente no disponible'
    return data


def ratio(n,d):
    if isinstance(n,(int,float)) and isinstance(d,(int,float)) and d>0 and 0<=n<=d: return n/d
    return None


def timeline(service, activities, pilots, today=None):
    """Fechas originales; fechas ausentes/inválidas no se inventan."""
    today=today or date.today(); rows=[]
    def add(kind,title,raw,status,owner='',evidence='',pending=False):
        raw=str(raw or '')
        try: dt=date.fromisoformat(raw)
        except ValueError: dt=None
        rows.append({'Tipo':kind,'Actividad / hito':title,'Fecha':raw or 'Sin fecha',
                     'Estado registrado':status,'Responsable':owner or 'Sin asignar',
                     'Evidencia':evidence or '—','Fecha válida':bool(dt),
                     'Pendiente con fecha pasada':bool(dt and dt<today and pending)})
    if service.get('launch_date'):
        add('Plan','Lanzamiento previsto',service['launch_date'],'Fecha planificada',service.get('owner'))
    try: milestones=json.loads(service.get('milestones_json') or '[]')
    except (ValueError,TypeError): milestones=[]
    if isinstance(milestones,list):
        for m in milestones:
            if isinstance(m,dict): add('Hito',m.get('title',''),m.get('date'),'Realizado' if m.get('done') is True else 'Pendiente',service.get('owner'),pending=m.get('done') is not True)
    for a in activities:
        if a['service_id']==service['id']:
            add(a['kind'],a['title'],a['date'],a['status'],a['owner'],a['evidence'],a['status']=='Programada')
    for p in pilots:
        if p['service_id']==service['id']:
            add('Piloto · inicio',p['title'],p['start_date'],p['status'],p['owner'],p['evidence'],p['status']=='Planificado')
            add('Piloto · fin',p['title'],p['end_date'],p['status'],p['owner'],p['evidence'],p['status'] in ('Planificado','En ejecución'))
    return sorted(rows,key=lambda r:(not r['Fecha válida'],r['Fecha'],r['Actividad / hito']))


def operation_data(path=None):
    return read_data({
        'tickets':'SELECT t.*,c.nombre AS servicio_nombre,c.codigo AS servicio_codigo FROM p6_tickets t JOIN p6_catalog c ON c.id=t.servicio_id WHERE t.demo=0 AND c.demo=0 ORDER BY t.creado_en DESC',
        'team':'SELECT id,nombre,rol,capacidad FROM p4_team ORDER BY nombre,id',
        'tasks':'SELECT a.ticket_id,COUNT(*) AS total,SUM(a.completada) AS done FROM p6_tareas a JOIN p6_tickets t ON t.id=a.ticket_id JOIN p6_catalog c ON c.id=t.servicio_id WHERE t.demo=0 AND c.demo=0 GROUP BY a.ticket_id',
    },path)


def open_items(tickets):
    return [t for t in tickets if t['estado']!='Finalizado' and not t.get('demo')]


def deadline(t,kind):
    limit=t.get('ans_respuesta_h' if kind=='respuesta' else 'ans_resolucion_h')
    if limit is None:return None
    try:
        if t.get('ans_tipo','Calendario')=='Hábil':
            return due_at(t['creado_en'],limit,json.loads(t.get('ans_calendario_json') or '{}'))
        return ops._dt(t['creado_en'])+timedelta(hours=limit)
    except (ValueError,TypeError,KeyError,OverflowError,AttributeError):return None


def commitments(tickets,at=None):
    """Solo hitos ANS abiertos, usando el motor original y sus plazos congelados."""
    at=at or ops.now(); out=[]
    for t in open_items(tickets):
        for kind,mark in [('respuesta','primera_respuesta_en'),('resolucion','terminado_en')]:
            if t.get(mark):continue
            try: state=ops.sla_state(t,kind,at)
            except (ValueError,TypeError,KeyError,ZeroDivisionError,OverflowError):state={'estado':'Datos no evaluables'}
            due=deadline(t,kind) if state['estado'] not in ('Calendario inválido','Datos no evaluables') else None
            frozen=t.get('ans_respuesta_limite_en' if kind=='respuesta' else 'ans_resolucion_limite_en')
            source='Calculado con ANS congelado' if due else 'No disponible'
            if due and frozen:
                try:
                    recorded=ops._dt(frozen)
                    if recorded is not None and recorded==due:
                        due=recorded; source='Vencimiento registrado'
                    else:
                        due=None; source='Inconsistencia con plazo registrado'
                except (ValueError,TypeError):
                    due=None; source='Fecha registrada inválida'
            out.append({'id':t['id'],'Ticket':t['folio'],'Solicitud':t['titulo'],'Responsable':t['responsable'] or 'Sin asignar',
                        'Compromiso':'Respuesta' if kind=='respuesta' else 'Resolución','Estado ANS':state['estado'],
                        'Vencimiento Colombia':local_dt(due).strftime('%Y-%m-%d %H:%M') if due else '—',
                        'Fuente del vencimiento':source,'Horas restantes':state.get('restantes_h'),'Unidad':state.get('unidad') or '—',
                        'Prioridad':t['prioridad']})
    ranks={'Vencido':0,'En riesgo':1,'En plazo':2,'Sin ANS':3}
    return sorted(out,key=lambda r:(ranks.get(r['Estado ANS'],4),r['Vencimiento Colombia']=='—',r['Vencimiento Colombia'],r['Ticket']))


def capacity(rows,unassigned=0):
    """Horas del mismo periodo. No usa el tiempo ANS como esfuerzo de trabajo."""
    def number(v):
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not isfinite(v) or v<0:raise ValueError('Valor numérico no negativo requerido.')
        return float(v)
    unassigned=number(unassigned); result=[]
    for r in rows:
        gross,absence,pct,fixed,demand=(number(r[k]) for k in ('gross','absence','pct','fixed','demand'))
        if absence>gross or pct>100:raise ValueError('Ausencias superiores a horas brutas o dedicación mayor al 100%.')
        dedicated=(gross-absence)*pct/100
        if fixed>dedicated:raise ValueError('Carga fija superior a horas de dedicación PMO.')
        available=dedicated-fixed
        result.append(dict(r,available=available,balance=available-demand,utilization=demand/available if available else None))
    supply=sum(r['available'] for r in result); demand=sum(r['demand'] for r in result)+unassigned
    return {'rows':result,'supply':supply,'demand':demand,'balance':supply-demand,'unassigned':unassigned,
            'individual_deficit':sum(max(0,-r['balance']) for r in result),'utilization':demand/supply if supply else None}


def render_adoption():
    import streamlit as st
    with st.expander('Centro de adopción · panorama y cronograma',expanded=False):
        st.caption('Solo servicios incorporados no demostrativos. Los datos declarados no prueban usuarios únicos ni autorizan la transición.')
        data=adoption_data(); services=data['services']
        if services is None:st.warning('Fuente de incorporación no disponible.');return
        if not services:st.info('No hay servicios no demo incorporados. Utiliza los controles originales de importación del Paso 04.');return
        from . import step5
        rows=[]
        for sr in services:
            try:
                readiness=step5.readiness(sr['id']); gate='Autorizada y elegible' if readiness['authorized'] and readiness['eligible'] else 'Autorización con bloqueos' if readiness['authorized'] else 'Lista para autorizar' if readiness['eligible'] else 'Con pendientes'
            except (ValueError,TypeError,sqlite3.Error,KeyError):gate='No disponible'
            rows.append({'Servicio':sr['codigo']+' · '+sr['nombre'],'Ruta':sr['route_type'] or 'Sin definir','Plan aprobado':'Sí' if sr['approved_at'] else 'No',
                         'Formación declarada':f"{sr['trained_people']}/{sr['target_people']}" if ratio(sr['trained_people'],sr['target_people']) is not None else '—',
                         'Adopción declarada':f"{sr['active_clients']}/{sr['enabled_clients']}" if ratio(sr['active_clients'],sr['enabled_clients']) is not None else '—',
                         'Transición':gate})
        st.dataframe(rows,hide_index=True,use_container_width=True)
        options={s['id']:s for s in services}
        sid=st.selectbox('Servicio para consultar cronograma',list(options),format_func=lambda k:options[k]['codigo']+' · '+options[k]['nombre'],key='a04_adopt_service')
        sr=options[sid]; c1,c2=st.columns(2)
        for col,n,d,label in [(c1,sr['trained_people'],sr['target_people'],'Formación declarada'),(c2,sr['active_clients'],sr['enabled_clients'],'Adopción declarada')]:
            value=ratio(n,d); col.metric(label,f'{value:.0%}' if value is not None else '—')
            if value is not None:col.progress(value,text=f'{n}/{d} declarados')
        if data['issues'] is not None:
            st.caption(f"Incidencias abiertas: {sum(x['service_id']==sid and x['status'] not in ('Resuelta','Descartada') for x in data['issues'])}")
        if data['activities'] is None or data['pilots'] is None:st.warning('Cronograma parcial: faltan fuentes de actividades o pilotos.')
        entries=timeline(sr,data['activities'] or [],data['pilots'] or [],local_dt(datetime.now(timezone.utc)).date())
        if not entries:st.info('Sin hitos, actividades o pilotos registrados. Gestiona los datos en las pantallas originales.');return
        st.subheader('Cronograma de incorporación')
        st.caption('Incluye fechas registradas, no fechas estimadas. Un lanzamiento previsto no equivale a una autorización.')
        filt=st.radio('Mostrar',['Todos','Pendientes con fecha pasada','Sin fecha válida'],horizontal=True,key='a04_timeline_filter')
        shown=[r for r in entries if filt=='Todos' or (filt=='Pendientes con fecha pasada' and r['Pendiente con fecha pasada']) or (filt=='Sin fecha válida' and not r['Fecha válida'])]
        for r in shown:
            with st.container(border=True):
                a,b=st.columns([1,3]);a.markdown('**'+r['Fecha']+'**');a.caption(r['Tipo']);b.write(r['Actividad / hito']);b.caption(f"{r['Estado registrado']} · {r['Responsable']}")
                if r['Pendiente con fecha pasada']:b.warning('Pendiente con fecha pasada')
                if r['Evidencia']!='—':b.caption('Evidencia: '+str(r['Evidencia']))
        if not shown:st.caption('Sin registros con este filtro.')


def render_operations(open_ticket):
    import streamlit as st
    with st.expander('Centro de operaciones · bandeja, compromisos y capacidad',expanded=False):
        st.caption('Vistas consultivas sobre solicitudes no demo. Abre la ficha original para editar; los escenarios de capacidad no se guardan en SQLite.')
        data=operation_data(); tickets=data['tickets']
        if tickets is None:st.warning('Fuente de solicitudes no disponible.');return
        active=open_items(tickets); tasks={r['ticket_id']:r for r in data['tasks'] or []}
        team=data['team'] or []
        if data['team'] is None:st.warning('Directorio del equipo PMO no disponible.')
        owners=sorted({str(t['responsable'] or '') for t in active}|{r['nombre'] for r in team})
        mode=st.radio('Vista',['Bandeja de trabajo','Compromisos ANS','Simulador de capacidad'],horizontal=True,key='a04_ops_mode')
        if mode in ('Bandeja de trabajo','Compromisos ANS'):
            owner=st.selectbox('Responsable registrado',[None,*owners],format_func=lambda x:'Todos' if x is None else x or 'Sin asignar',key='a04_ops_owner')
            chosen=[t for t in active if owner is None or (t['responsable'] or '')==owner]
            now=ops.now(); c=commitments(chosen,now)
            if mode=='Bandeja de trabajo':
                a,b,d=st.columns(3);a.metric('Sin finalizar',len(chosen));b.metric('Sin asignar',sum(not t['responsable'] for t in chosen));d.metric('Con ANS en riesgo o vencido',len({r['id'] for r in c if r['Estado ANS'] in ('Vencido','En riesgo')}))
                stage=st.selectbox('Etapa de la bandeja',[None,*ops.STAGES[:-1]],format_func=lambda k:k or 'Todas',key='a04_ops_stage')
                chosen=[t for t in chosen if stage is None or t['estado']==stage]
                st.dataframe([{'Ticket':t['folio'],'Solicitud':t['titulo'],'Servicio':t['servicio_nombre'],'Responsable':t['responsable'] or 'Sin asignar','Etapa':t['estado'],'Prioridad':t['prioridad'],
                               'Tareas':f"{tasks[t['id']]['done']}/{tasks[t['id']]['total']}" if t['id'] in tasks else ('0/0' if data['tasks'] is not None else '—')} for t in chosen],hide_index=True,use_container_width=True)
            else:
                a,b,d=st.columns(3);a.metric('Vencidos',sum(r['Estado ANS']=='Vencido' for r in c));b.metric('En riesgo',sum(r['Estado ANS']=='En riesgo' for r in c));d.metric('Sin ANS',sum(r['Estado ANS']=='Sin ANS' for r in c))
                st.caption('Cada solicitud puede aportar dos compromisos. Se excluyen los hitos ya atendidos; se conserva la unidad calendario/hábil congelada. Consulta actual, no alerta en segundo plano.')
                risk=st.selectbox('Estado del compromiso',[None,*sorted({r['Estado ANS'] for r in c})],format_func=lambda k:k or 'Todos',key='a04_ops_risk')
                c=[r for r in c if risk is None or r['Estado ANS']==risk]
                st.dataframe([{k:v for k,v in r.items() if k!='id'} for r in c],hide_index=True,use_container_width=True)
                chosen=[t for t in chosen if t['id'] in {r['id'] for r in c}]
            if chosen:
                options={t['id']:t['folio']+' · '+t['titulo'] for t in chosen}
                selected=st.selectbox('Abrir ficha de solicitud',list(options),format_func=options.get,key='a04_ops_ticket')
                if st.button('Consultar ficha original',key='a04_ops_open'):open_ticket(selected)
            else:st.info('Sin solicitudes para esta selección.')
            return
        st.subheader('Simulador de capacidad y demanda')
        st.caption('Periodo común: un mes de planificación. Ingresa horas de trabajo estimadas, no horas de ANS. La dedicación inicial proviene del directorio del Paso 04; el resto comienza en cero. Ajusta todas las hipótesis.')
        if not team:st.info('Registra integrantes en el Paso 04 para construir el escenario.');return
        rows=[]; counts=Counter(t['responsable'] for t in active)
        for person in team:
            k=person['id'];name=person['nombre']
            with st.container(border=True):
                st.write(f"**{name}** · {person['rol']}");st.caption(f"{counts[name]} solicitudes sin finalizar asociadas al nombre registrado; no equivalen a horas ni resuelven homónimos.")
                a,b,c=st.columns(3);gross=a.number_input('Horas brutas',0.0,744.0,0.0,step=1.0,key='a04_g_'+k);absence=b.number_input('Ausencias (h)',0.0,744.0,0.0,step=1.0,key='a04_a_'+k);pct=c.number_input('Dedicación PMO (%)',0,100,int(person['capacidad']),key='a04_p_'+k)
                a,b=st.columns(2);fixed=a.number_input('Carga fija PMO (h)',0.0,744.0,0.0,step=1.0,key='a04_f_'+k);demand=b.number_input('Demanda variable (h)',0.0,10000.0,0.0,step=1.0,key='a04_d_'+k)
                rows.append(dict(name=name,member_id=k,gross=gross,absence=absence,pct=pct,fixed=fixed,demand=demand))
        u=st.number_input('Demanda aún sin asignar (h)',0.0,100000.0,0.0,step=1.0,key='a04_unassigned')
        if not st.checkbox('Confirmo que las hipótesis corresponden al mismo periodo mensual y no incluyen doble conteo',key='a04_capacity_confirm'):st.info('Confirma las hipótesis para interpretar el escenario.');return
        try:r=capacity(rows,u)
        except ValueError as ex:st.warning(str(ex));return
        a,b,c=st.columns(3);a.metric('Capacidad neta',f"{r['supply']:.1f} h");b.metric('Demanda variable',f"{r['demand']:.1f} h");c.metric('Balance',f"{r['balance']:.1f} h")
        st.dataframe([{'Integrante':x['name'],'Disponible (h)':round(x['available'],1),'Demanda (h)':x['demand'],'Balance (h)':round(x['balance'],1),'Utilización':f"{x['utilization']:.0%}" if x['utilization'] is not None else '—'} for x in r['rows']],hide_index=True,use_container_width=True)
        st.caption(f"Déficit individual acumulado: {r['individual_deficit']:.1f} h · Demanda sin asignar: {u:.1f} h. Un balance global positivo no garantiza competencias ni redistribución viable.")
