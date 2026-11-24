"""UI Streamlit Paso 5, sin sustituir los módulos previos. Cinco pantallas."""
from __future__ import annotations
from .date_widgets import iso_date_input
import html, io, json
from pathlib import Path
import streamlit as st
from .staff_picker import staff_picker
from .client_picker import choose_client
import pandas as pd
from . import step5 as s
from .public_codes import code as public_code
from .ui import kpi

NAV=list(s.NAV)
CSS=Path(__file__).parent/'assets'/'step5_ux.css'

def apply_step5_theme():
    st.markdown('<style>'+CSS.read_text(encoding='utf-8')+'</style>',unsafe_allow_html=True)
def e(x):return html.escape(str(x if x is not None else ''))
def dump(x):return json.dumps(x,ensure_ascii=False,indent=2,default=str).encode('utf-8')
def header(label,title,sub):
    st.markdown(f'<div class="pmo-eyebrow">PASO 05 · {e(label)}</div><div class="pmo-title">{e(title)}</div><div class="pmo-subtitle">{e(sub)}</div>',unsafe_allow_html=True)
def cards(items):
    for idx,(col,(label,value,desc,icon)) in enumerate(zip(st.columns(len(items)),items)):
        with col:kpi(label,str(value),desc,icon,('orange','blue','purple','teal')[idx%4])
def service_name(sid):
    sr=s.service(sid)
    return f"{public_code('servicio',sid)} · {sr['nombre']}" if sr else 'Servicio no encontrado'
def options():return {x['id']:f"{public_code('servicio',x['id'])} · {x['nombre']}" for x in s.services()}
def pct(pair):return '—' if not pair[1] else f'{100*pair[0]/pair[1]:.0f}%'
def call(func,*args,**kwargs):
    try:
        value=func(*args,**kwargs);st.success('Registro guardado correctamente.');return True,value
    except Exception as ex:
        st.error(str(ex));return False,None

@st.dialog('Importar servicios aprobados del Paso 4',width='large')
def import_modal():
    st.write('**Solo se incorporan servicios preparados y aprobados en el Paso 4.**')
    from . import step4
    transfer=step4.step5_transfer()
    st.caption(f"Paso 04: {len(transfer['services'])} elegibles · {len(transfer['blocked'])} pendientes de requisitos. Los planes preliminares no son aprobaciones.")
    if transfer['blocked']:
        with st.expander('Ver requisitos pendientes de importación'):
            st.dataframe(pd.DataFrame([{'Servicio':b['codigo'],'Pendiente':'; '.join(b['faltan'])} for b in transfer['blocked']]),
                         hide_index=True,use_container_width=True)
    a,b=st.columns(2)
    with a:
        st.caption('Integración directa con la misma base SQLite')
        if st.button('Consultar e importar desde Paso 4',type='primary',use_container_width=True):
            try:
                result=s.import_step4_direct();st.success(f"Nuevos: {result['nuevos']} · Ya existentes: {result['existentes']}");st.rerun()
            except Exception as ex:st.error(str(ex))
    with b:
        up=st.file_uploader('O seleccionar expediente JSON',type=['json'],key='p5_json_in')
        if up and st.button('Validar e importar JSON',use_container_width=True):
            try:
                if up.size>12_000_000:raise s.ValidationError('Máximo 12 MB.')
                result=s.import_step4(json.load(up));st.success(str(result));st.rerun()
            except Exception as ex:st.error(str(ex))
    st.caption('La importación no aprueba planes, no activa servicios y no crea tickets operativos.')

@st.dialog('Plan de incorporación',width='large')
def plan_modal(sid):
    sr=s.service(sid);p=s.plan(sid)
    if not sr or not p:return st.error('Servicio no disponible.')
    st.markdown(f"**{public_code('servicio',sid)} · {e(sr['nombre'])}**")
    locked=bool(p['approved_at'])
    if locked:st.info(f'Plan aprobado por {p["approved_by"]} el {p["approved_at"]}. Se conserva como versión aprobada.')
    with st.form('p5_plan_form'):
        c1,c2=st.columns(2)
        with c1:
            owner=staff_picker('Responsable de incorporación *',p['owner'],disabled=locked)
            groups=st.text_input('Clientes destinatarios *',p['groups_target'],disabled=locked)
            date=iso_date_input('Fecha de lanzamiento *',p['launch_date'],disabled=locked)
        with c2:
            strategy=st.text_area('Estrategia de despliegue *',p['strategy'],height=76,disabled=locked)
            resources=st.text_area('Recursos necesarios *',p['resources'],height=76,disabled=locked)
            risks=st.text_area('Riesgos y acciones *',p['risks'],height=76,disabled=locked)
        comm=st.text_area('Plan de comunicación',p['communication'],disabled=locked)
        criteria=st.text_area('Criterios de éxito *',p['success_criteria'],disabled=locked)
        submitted=st.form_submit_button('Guardar plan',type='primary',disabled=locked)
    if submitted:
        ok,_=call(s.save_plan,sid,{'owner':owner,'groups_target':groups,'launch_date':date,'strategy':strategy,'resources':resources,'risks':risks,'communication':comm,'success_criteria':criteria})
        if ok:st.rerun()
    st.markdown('##### Hitos del plan')
    ms=json.loads(p['milestones_json'])
    for m in ms:
        a,b=st.columns([4,1])
        with a:st.caption(f"{m.get('date') or 'Sin fecha'} · {m['title']}")
        with b:
            if st.checkbox('Realizado',value=bool(m.get('done')),key='p5_milestone_'+m['id'],disabled=locked):
                if not m.get('done'):
                    ok,_=call(s.set_milestone,sid,m['id'],True)
                    if ok:st.rerun()
            elif m.get('done') and not locked:
                ok,_=call(s.set_milestone,sid,m['id'],False)
                if ok:st.rerun()
    if not locked:
        with st.form('p5_add_milestone'):
            a,b=st.columns([3,1]);title=a.text_input('Nuevo hito');date=iso_date_input('Fecha objetivo',container=b);go=st.form_submit_button('Añadir hito')
        if go:
            ok,_=call(s.add_milestone,sid,title,date)
            if ok:st.rerun()
        st.divider()
        approver=st.text_input('Nombre del aprobador',key='p5_approver_'+sid)
        proof=st.text_input('Acta o evidencia de aprobación',key='p5_proof_'+sid)
        if st.button('Aprobar formalmente el plan',key='p5_approve_'+sid,type='primary'):
            ok,_=call(s.approve_plan,sid,approver,proof)
            if ok:st.rerun()

@st.dialog('Actividad de comunicación o formación',width='large')
def activity_modal(key=None):
    old=next((x for x in s.activities() if x['id']==key),None)
    opts=options()
    if not opts:return st.warning('Importa servicios primero.')
    with st.form('p5_activity_form'):
        sid=st.selectbox('Servicio *',list(opts),format_func=lambda x:opts[x],index=list(opts).index(old['service_id']) if old else 0)
        a,b=st.columns(2)
        with a:
            kind=st.selectbox('Tipo',['Comunicación','Formación'],index=['Comunicación','Formación'].index(old['kind']) if old else 0)
            title=st.text_input('Nombre de la actividad *',old['title'] if old else '')
            date=iso_date_input('Fecha',old['date'] if old else '')
            invited=st.number_input('Personas convocadas',0,100000,int(old['invited'] or 0) if old else 0)
        with b:
            owner=staff_picker('Responsable',old['owner'] if old else '')
            audience=st.text_input('Público objetivo',old['audience'] if old else '')
            status=st.selectbox('Estado',['Programada','En ejecución','Realizada','Cancelada'],index=['Programada','En ejecución','Realizada','Cancelada'].index(old['status']) if old and old['status'] in ['Programada','En ejecución','Realizada','Cancelada'] else 0)
            attendees=st.number_input('Personas asistentes',0,100000,int(old['attendees'] or 0) if old else 0)
        materials=st.text_input('Material / enlace',old['materials'] if old else '')
        proof=st.text_input('Referencia de evidencia',old['evidence'] if old else '')
        submitted=st.form_submit_button('Guardar actividad',type='primary')
    if submitted:
        ok,_=call(s.save_activity,{'service_id':sid,'kind':kind,'title':title,'date':date,'owner':owner,'audience':audience,'status':status,
                       'invited':invited,'attendees':attendees,'materials':materials,'evidence':proof},key)
        if ok:st.rerun()

@st.dialog('Registrar o actualizar piloto',width='large')
def pilot_modal(key=None):
    old=next((x for x in s.pilots() if x['id']==key),None)
    opts=options()
    if not opts:return st.warning('Importa servicios primero.')
    with st.form('p5_pilot_form'):
        sid=st.selectbox('Servicio *',list(opts),format_func=lambda x:opts[x],index=list(opts).index(old['service_id']) if old else 0)
        title=st.text_input('Nombre del piloto *',old['title'] if old else '')
        a,b=st.columns(2)
        with a:
            client=choose_client(st,'Cliente del piloto · Directorio Paso 01',old['client'] if old else '',key=f'p5_pilot_client_{key or "new"}')[0]
            start=iso_date_input('Inicio',old['start_date'] if old else '')
            end=iso_date_input('Fin',old['end_date'] if old else '')
        with b:
            owner=staff_picker('Responsable',old['owner'] if old else '')
            states=['Planificado','En ejecución','Completado','Validado','Cancelado']
            status=st.selectbox('Estado',states,index=states.index(old['status']) if old and old['status'] in states else 0)
            sat=st.selectbox('Satisfacción del cliente (1–10)',[None]+list(range(1,11)),index=old['satisfaction'] if old and old['satisfaction'] else 0)
        criteria=st.text_area('Objetivos y criterios de éxito',old['criteria'] if old else '')
        results=st.text_area('Resultados observados',old['results'] if old else '')
        proof=st.text_input('Evidencia',old['evidence'] if old else '')
        submitted=st.form_submit_button('Guardar piloto',type='primary')
    if submitted:
        ok,_=call(s.save_pilot,{'service_id':sid,'title':title,'client':client,'start_date':start,'end_date':end,'owner':owner,
             'status':status,'satisfaction':sat,'criteria':criteria,'results':results,'evidence':proof},key)
        if ok:st.rerun()

@st.dialog('Incidencia de incorporación',width='large')
def issue_modal(key=None):
    old=next((x for x in s.issues() if x['id']==key),None)
    opts=options()
    if not opts:return st.warning('Importa servicios primero.')
    with st.form('p5_issue_form'):
        sid=st.selectbox('Servicio *',list(opts),format_func=lambda x:opts[x],index=list(opts).index(old['service_id']) if old else 0)
        title=st.text_input('Hallazgo / incidencia *',old['title'] if old else '')
        a,b=st.columns(2)
        with a:
            kind=st.selectbox('Tipo',['Incidencia','Duda','Sugerencia','Riesgo'],index=['Incidencia','Duda','Sugerencia','Riesgo'].index(old['kind']) if old and old['kind'] in ['Incidencia','Duda','Sugerencia','Riesgo'] else 0)
            owner=staff_picker('Responsable',old['owner'] if old else '')
        with b:
            status=st.selectbox('Estado',['Abierta','En tratamiento','Resuelta','Descartada'],index=['Abierta','En tratamiento','Resuelta','Descartada'].index(old['status']) if old and old['status'] in ['Abierta','En tratamiento','Resuelta','Descartada'] else 0)
        action=st.text_area('Acción correctiva',old['action'] if old else '')
        evidence=st.text_input('Evidencia',old['evidence'] if old else '')
        submitted=st.form_submit_button('Guardar incidencia',type='primary')
    if submitted:
        ok,_=call(s.save_issue,{'service_id':sid,'title':title,'kind':kind,'owner':owner,'status':status,'action':action,'evidence':evidence},key)
        if ok:st.rerun()

@st.dialog('Adopción y autorización de transición',width='large')
def adoption_modal(sid):
    a=s.adoption(sid)
    if not a:return st.error('Servicio no disponible.')
    locked=bool(a['authorized_at'])
    st.markdown('**'+e(service_name(sid))+'**')
    if locked:st.success(f'Autorizado por {a["authorized_by"]} el {a["authorized_at"]}. Registro protegido.')
    checks=json.loads(a['checks_json'])
    with st.form('p5_adoption_form'):
        c,d=st.columns(2)
        with c:
            target=st.number_input('Personas objetivo',0,100000,int(a['target_people'] or 0),disabled=locked)
            trained=st.number_input('Personas únicas capacitadas',0,100000,int(a['trained_people'] or 0),disabled=locked)
        with d:
            enabled=st.number_input('Clientes habilitados',0,100000,int(a['enabled_clients'] or 0),disabled=locked)
            active=st.number_input('Clientes que utilizaron el servicio',0,100000,int(a['active_clients'] or 0),disabled=locked)
        st.markdown('##### Lista de comprobación de transición')
        chosen={}
        cols=st.columns(2)
        for idx,(code,label) in enumerate(s.CHECKS):
            with cols[idx%2]:
                statuses=['pendiente','cumple','na']
                chosen[code]=st.selectbox(label,statuses,index=statuses.index(checks.get(code,'pendiente')),key='p5_chk_'+sid+'_'+code,disabled=locked,
                 format_func=lambda x:{'pendiente':'Pendiente','cumple':'Cumple','na':'No aplica'}[x])
        reason=st.text_area('Justificación de criterios no aplicables',a['exemption_reason'],disabled=locked)
        proof=st.text_input('Evidencia de transición *',a['evidence'],disabled=locked)
        submitted=st.form_submit_button('Guardar comprobación',type='primary',disabled=locked)
    if submitted:
        ok,_=call(s.save_adoption,sid,{'target_people':target,'trained_people':trained,'enabled_clients':enabled,'active_clients':active,
                     'checks':chosen,'exemption_reason':reason,'evidence':proof})
        if ok:st.rerun()
    ready=s.readiness(sid)
    if ready['authorized'] and ready['eligible']:
        st.success('Transición formalmente autorizada. Puedes transferir este servicio al catálogo del Paso 06 desde Adopción y transición.')
    elif ready['blockers']:
        st.warning('Pendiente para autorizar: '+'; '.join(ready['blockers']))
    elif not locked:
        st.info('Preparación completa, pero todavía NO está autorizado para operar. La firma del responsable es un acto distinto de guardar la comprobación.')
        approver=st.text_input('Responsable que autoriza el traspaso *',key='p5_autoriza_'+sid)
        if st.button('Autorizar expresamente para Paso 06',type='primary',disabled=not bool(approver.strip()),key='p5_confirmar_aut_'+sid):
            ok,_=call(s.authorize,sid,approver)
            if ok:st.rerun()

@st.dialog('Respaldo y restauración del Paso 5',width='large')
def backup_dialog():
    st.download_button('Descargar respaldo JSON del Paso 5',dump(s.backup()),'PMO_CENS_Paso5_Respaldo.json',mime='application/json')
    st.divider()
    st.warning('Restaurar reemplaza únicamente las tablas del Paso 5. Los pasos anteriores y el Paso 6 se mantienen.')
    f=st.file_uploader('Respaldo JSON',type='json',key='p5_backup_up')
    confirmation=st.checkbox('Confirmo que deseo sustituir los registros del Paso 5')
    if f and st.button('Restaurar respaldo',disabled=not confirmation):
        try:
            if f.size>12_000_000:raise s.ValidationError('Máximo 12 MB.')
            s.restore_backup(json.load(f),confirm=True);st.rerun()
        except Exception as ex:st.error(str(ex))

@st.dialog('Preparación del plan de incorporación · borrador',width='large')
def preplan_modal(sid):
    from . import step4
    origin=step4.service(sid)
    if not origin:return st.error('Servicio del Paso 04 no encontrado.')
    draft=s.preplan(sid) or {}
    missing=step4.service_readiness(origin)
    st.markdown(f"**{public_code('servicio',sid)} · {e(origin['nombre'])}**")
    st.info('Este formulario es una planificación preliminar editable. No aprueba el servicio, no activa pilotos ni lo transfiere al Paso 05.')
    if missing:
        with st.expander(f'Requisitos del Paso 04 pendientes ({len(missing)})'):
            for issue in missing:st.caption('○ '+issue)
    with st.form('p5_preplan_form'):
        a,b=st.columns(2)
        with a:
            owner=staff_picker('Responsable previsto',draft.get('owner',''))
            groups=st.text_input('Clientes destinatarios',draft.get('groups_target','') or origin.get('cliente',''))
            date=iso_date_input('Fecha tentativa de lanzamiento',draft.get('launch_date',''))
            communication=st.text_area('Divulgación y formación',draft.get('communication',''))
        with b:
            strategy=st.text_area('Estrategia de incorporación gradual',draft.get('strategy',''))
            resources=st.text_area('Recursos y dedicación requeridos',draft.get('resources',''))
            risks=st.text_area('Riesgos y acciones de tratamiento',draft.get('risks',''))
            success=st.text_area('Criterios de éxito y aceptación',draft.get('success_criteria',''))
        try:milestones=json.loads(draft.get('milestones_json') or '[]')
        except (TypeError,ValueError):milestones=[]
        st.caption('Hitos propuestos · un hito por línea, opcionalmente FECHA | DESCRIPCIÓN. No representa ejecución real.')
        milestone_lines='\n'.join((m.get('date','')+' | ' if m.get('date') else '')+m.get('title','') for m in milestones)
        txt=st.text_area('Hitos y dependencias',milestone_lines,placeholder='2027-01-15 | Revisión de ficha con el cliente')
        saved=st.form_submit_button('Guardar planificación preliminar',type='primary')
    if saved:
        try:
            ms=[]
            for line in txt.splitlines():
                line=line.strip()
                if not line:continue
                if '|' in line:
                    dt,ttl=line.split('|',1);dt,ttl=dt.strip(),ttl.strip()
                else:dt,ttl='',line
                if not ttl:raise s.ValidationError('Cada hito debe tener un título.')
                ms.append({'id':str(len(ms)+1).zfill(2),'title':ttl,'date':dt,'done':False})
            s.save_preplan(sid,{'owner':owner,'groups_target':groups,'strategy':strategy,
                  'launch_date':date,'resources':resources,'risks':risks,'communication':communication,
                  'success_criteria':success,'milestones':ms})
            st.rerun()
        except Exception as ex:st.error(str(ex))

def toolbar():
    a,b,c=st.columns([1.7,1,1])
    with a:
        if st.button('↑ Importar Paso 4',key='p5_import_header'):import_modal()
    with b:st.download_button('↓ Respaldo JSON',dump(s.backup()),'PMO_CENS_Paso5_Respaldo.json',mime='application/json',key='p5_backup_header')
    with c:
        if st.button('↺ Restaurar',key='p5_restore_header'):backup_dialog()

def _goto_p5(name):
    """Callback: cambio de radio previo a su creación en el siguiente rerun."""
    st.session_state['pmo_active_p5_page']=name


def route_panel():
    """Gestor transversal de rutas por servicio. No crea otros registros de negocio."""
    sv=s.services()
    if not sv:
        st.info('No existen servicios incorporados al Paso 05. Utiliza **Importar Paso 4** para registrar un servicio aprobado; no se crearán autorizaciones automáticamente.')
        return
    st.markdown('### Ruta de incorporación por servicio')
    st.caption('Adaptación operativa CENS del capítulo 18 de la Guía Práctica PMI. Las rutas son orientativas; no sustituyen las aprobaciones y evidencias del Paso 05.')
    labels={x['id']:f"{public_code('servicio',x['id'])} · {x['nombre']}" for x in sv}
    chosen=st.selectbox('Seleccionar servicio',list(labels),format_func=lambda sid:labels[sid],key='p5_route_selected')
    summary=s.route_summary(chosen)
    cfg=summary['route'] or {}
    ready=summary['readiness']
    labels_status={x['key']:x['status'] for x in summary['stages']}
    route_label=cfg.get('route_type') or 'Sin ruta definida'
    c1,c2,c3,c4=st.columns(4)
    c1.metric('Ruta',route_label)
    c2.metric('Etapas con registros',f"{summary['stages_with_progress']}/6")
    c3.metric('Incidencias abiertas',summary['issues_open'])
    c4.metric('Transición', 'Autorizada' if ready['authorized'] and ready['eligible'] else 'Lista para autorizar' if ready['eligible'] else 'Con pendientes')
    if ready['authorized'] and ready['eligible']:
        st.success('Este servicio tiene autorización formal vigente. La incorporación al catálogo del Paso 06 sigue siendo una acción independiente.')
    elif ready['eligible']:
        st.info('Los controles declarados permiten **solicitar la autorización**; la ruta por sí sola NO autoriza el servicio ni certifica evidencias individuales.')
    else:
        st.warning('Pendientes de transición formal: '+'; '.join(ready['blockers'][:5]))
    with st.expander('Configurar estrategia de incorporación CENS',expanded=not bool(cfg)):
        st.caption('La ruta pilotada se recomienda para servicios nuevos o de mayor impacto; la gradual despliega por grupos; la simplificada requiere justificar proporcionalidad y no omite autorizaciones.')
        locked=bool(cfg and ready['authorized'])
        if ready['authorized'] and not cfg:
            st.warning('Servicio autorizado antes de definir una ruta. Solo se permite clasificarlo retrospectivamente, con una fuente, sin modificar su autorización ni afirmar que se ejecutó esa estrategia.')
        with st.form('p5_route_edit_'+chosen):
            a,b=st.columns(2)
            existing_type=cfg.get('route_type') or 'Pilotada'
            typ=a.selectbox('Tipo de ruta *',list(s.ROUTE_TYPES),index=list(s.ROUTE_TYPES).index(existing_type),disabled=locked)
            rollout=b.selectbox('Modalidad de despliegue', ['Por definir','Piloto acotado','Por dependencia o regional','Por oleadas','Despliegue general'],
                index=(['Por definir','Piloto acotado','Por dependencia o regional','Por oleadas','Despliegue general'].index(cfg.get('rollout','Por definir')) if cfg.get('rollout','Por definir') in ['Por definir','Piloto acotado','Por dependencia o regional','Por oleadas','Despliegue general'] else 0),disabled=locked)
            plan=s.plan(chosen) or {}
            owner=staff_picker('Responsable de la ruta',value=cfg.get('owner') or plan.get('owner') or '',disabled=locked)
            clients=st.text_input('Grupos de clientes',value=cfg.get('client_groups') or plan.get('groups_target') or '',disabled=locked)
            reason=st.text_area('Justificación de la ruta *',value=cfg.get('rationale') or '',height=84,disabled=locked,
                                 placeholder='Complejidad, riesgo, número de dependencias, capacidad y evidencia de aprendizaje')
            support=st.text_area('Notas de apoyo, infraestructura y seguimiento',value=cfg.get('support_notes') or '',height=72,disabled=locked)
            retrospective_confirm=False
            reconstruction_note=''
            if ready['authorized'] and not cfg:
                retrospective_confirm=st.checkbox('Confirmo que esta clasificación es retrospectiva y no modifica la autorización')
                reconstruction_note=st.text_input('Fuente de la reconstrucción (acta, expediente o referencia) *')
            saved=st.form_submit_button('Guardar estrategia de incorporación',type='primary',disabled=locked)
        if saved:
            ok,_=call(s.save_route,chosen,{'route_type':typ,'rollout':rollout,'owner':owner,
                 'client_groups':clients,'rationale':reason,'support_notes':support,
                 'retrospective_confirm':retrospective_confirm,'reconstruction_note':reconstruction_note})
            if ok:st.rerun()
        if cfg.get('retrospective'):
            st.caption('**Clasificación retrospectiva:** '+str(cfg.get('reconstruction_note') or 'Sin referencia')+'; no equivale a una ruta aprobada antes del lanzamiento.')
        if locked:st.caption('La estrategia está protegida; su trazabilidad permanece en la auditoría.')
    st.markdown('#### Recorrido de incorporación')
    st.caption('Seis actividades de gestión CENS agrupadas a partir de la guía PMI. “Registrada” no significa “validada”.')
    step_names={
     'preparacion':'Plan de incorporación',
     'formacion':'Comunicación y formación',
     'piloto':'Pilotos y soporte',
     'soporte':'Pilotos y soporte',
     'verificacion':'Adopción y transición',
     'autorizacion':'Adopción y transición'}
    icons={'preparacion':'📋','formacion':'🎓','piloto':'🧪','soporte':'🛠️','verificacion':'✅','autorizacion':'🔐'}
    for offset in range(0,len(summary['stages']),2):
        cols=st.columns(2)
        for col,item in zip(cols,summary['stages'][offset:offset+2]):
            with col:
                with st.container(border=True):
                    st.markdown(f"**{icons[item['key']]} {item['name']}**")
                    st.caption('Estado: '+item['status'])
                    st.write(item['detail'])
                    if item['notes']:st.caption(item['notes'])
                    st.caption('Fuente: '+item['source'])
                    if item['key']=='preparacion':
                        if st.button('Abrir plan',key='p5_route_plan_'+chosen):plan_modal(chosen)
                    elif item['key']=='autorizacion':
                        if st.button('Revisar y autorizar',key='p5_route_gate_'+chosen):adoption_modal(chosen)
                    else:
                        st.button('Ir a '+step_names[item['key']],key='p5_route_link_'+item['key']+'_'+chosen,
                            on_click=_goto_p5,args=(step_names[item['key']],),use_container_width=True)
    with st.expander('Hitos del servicio · cronología vinculada al plan',expanded=bool(summary['milestones'])):
        ms=sorted(summary['milestones'],key=lambda x:(x.get('date') or '9999',x.get('title') or ''))
        if ms:
            st.dataframe([{'Fecha':m.get('date') or 'Sin fecha','Hito':m.get('title',''),
                       'Estado':'Realizado' if m.get('done') else 'Pendiente'} for m in ms],
                       hide_index=True,use_container_width=True)
        else:st.caption('Aún no hay hitos vinculados. Se registran en Gestionar plan; no debes volverlos a crear aquí.')
    with st.expander('Control de calidad del registro y trazabilidad'):
        st.markdown('**Coberturas declaradas (no conciliadas automáticamente)**')
        tr=summary['training_declared'];ad=summary['adoption_declared']
        st.write('Formación: '+(f'{tr[0]}/{tr[1]} personas declaradas' if tr[0] is not None and tr[1] is not None else 'Sin datos comparables'))
        st.write('Adopción: '+(f'{ad[0]}/{ad[1]} clientes declarados' if ad[0] is not None and ad[1] is not None else 'Sin datos comparables'))
        st.caption('Asistencias de actividades y personas únicas no pueden equipararse sin identificadores individuales. Un porcentaje de 100% declarado no acredita necesariamente la ejecución.')
        st.write(f"Actividades con evidencia: {summary['activity_evidence']} · Pilotos con criterios, resultados y evidencia: {summary['pilot_evidence']}.")
        st.caption('El sistema no altera las aprobaciones del Paso 04 ni las autorizaciones de los Pasos 05 y 06.')
    st.download_button('↓ Exportar resumen de ruta (JSON)',dump(summary),
         f"PMO_CENS_Paso5_Ruta_{e(summary['service']['codigo'])}.json",mime='application/json',key='p5_route_export_'+chosen)

def plans_page():
    header('01 · PLANIFICACIÓN','Plan de incorporación','Rutas por servicio, planificación, lanzamiento y aprobación formal de los servicios preparados en Paso 04.')
    toolbar()
    from .alpha04_operations import render_adoption
    render_adoption()
    mode=st.radio('Vista del módulo',('Rutas de incorporación','Administrar planes y fichas'),horizontal=True,
                  key='p5_plan_view')
    if mode=='Rutas de incorporación':
        route_panel()
        return
    sv=s.services();plans=[s.plan(x['id']) for x in sv];pilots=s.pilots()
    cards([('Servicios por incorporar',len(sv),'Importados desde Paso 4','layers'),('Planes aprobados',sum(bool(x['approved_at']) for x in plans),'Aprobación documentada','check-circle'),
      ('Servicios en piloto',len({x['service_id'] for x in pilots if x['status']=='En ejecución'}),'Pilotos en ejecución','flask-conical'),('Autorizados para Paso 06',sum(s.readiness(x['id'])['authorized'] and s.readiness(x['id'])['eligible'] for x in sv),'Autorización expresa y sin bloqueos','arrow-right')])
    st.info('La aprobación del plan, el lanzamiento y la autorización para operar son decisiones distintas.')
    from . import step4
    waiting=step4.services()
    blockers={r['id']:step4.service_readiness(r) for r in waiting}
    pending=[r for r in waiting if r['id'] not in {x['id'] for x in sv}]
    with st.expander(f'Preparación desde Paso 04 · {len(pending)} fichas aún no incorporadas',expanded=not bool(sv)):
        if not pending:
            st.success('No hay fichas adicionales del Paso 04 pendientes de incorporación.')
        else:
            st.caption('Las fichas pueden prepararse, pero solo pasan a incorporación cuando completan todos sus requisitos y obtienen aprobación documentada.')
            a,b,c=st.columns(3)
            a.metric('Fichas en preparación',len(pending))
            b.metric('Aptas para importar',sum(not blockers.get(x['id']) for x in pending))
            c.metric('Preplanes guardados',sum(bool(s.preplan(x['id'])) for x in pending))
            filter_text=st.text_input('Buscar ficha en preparación',key='p5_pending_search')
            visible=[r for r in pending if filter_text.casefold() in (r['nombre']+' '+r['codigo']+' '+public_code('servicio',r['id'])).casefold()]
            for r in visible:
                a,b=st.columns([6,1])
                pending_checks=blockers[r['id']]
                with a:
                    st.markdown(f"**{public_code('servicio',r['id'])} · {e(r['nombre'])}**")
                    st.caption(f"Estado Paso 04: {r['estado']} · {len(pending_checks)} criterios pendientes"+(' · Plan preliminar guardado' if s.preplan(r['id']) else ''))
                    if pending_checks:st.caption('Pendiente: '+ '; '.join(pending_checks))
                    else:st.success('Ficha apta para transferir al Paso 05.')
                with b:
                    if st.button('Preparar',key='p5_pre_'+r['id']):preplan_modal(r['id'])
                st.divider()
    
    term=st.text_input('Buscar servicio por código o nombre',key='p5_plan_search')
    shown=[x for x in sv if term.casefold() in (x['codigo']+' '+public_code('servicio',x['id'])+' '+x['nombre']).casefold()]
    if not shown:st.info('Aún no hay servicios incorporados. Consulta arriba la preparación de las fichas del Paso 04 y los requisitos pendientes.')
    else:
        for idx in range(0,len(shown),3):
            for col,sr in zip(st.columns(3),shown[idx:idx+3]):
                with col:
                    with st.container(border=True):
                        p=s.plan(sr['id']);state='Autorizado' if s.readiness(sr['id'])['authorized'] else 'Plan aprobado' if p['approved_at'] else 'En preparación'
                        st.caption(public_code('servicio',sr['id']));st.markdown('**'+e(sr['nombre'])+'**')
                        st.caption('Estado: '+state)
                        st.write(sr['descripcion'] or 'Descripción no registrada')
                        st.caption('Responsable: '+(p['owner'] or 'Pendiente')+' · Lanzamiento: '+(p['launch_date'] or 'Por definir'))
                        if st.button('Gestionar plan',key='p5_plan_'+sr['id'],use_container_width=True):plan_modal(sr['id'])
    left,right=st.columns([1.4,1])
    with left:
        with st.container(border=True):
            st.markdown('**Próximos hitos**')
            ms=[dict(x,service=sr['nombre']) for sr in sv for x in json.loads(s.plan(sr['id'])['milestones_json']) if x.get('date')]
            for m in sorted(ms,key=lambda x:x['date'])[:12]:st.caption(('✓ ' if m.get('done') else '○ ')+m['date']+' · '+m['title']+' — '+m['service'])
            if not ms:st.caption('Aún no hay hitos programados.')
    with right:
        with st.container(border=True):
            st.markdown('**Criterios de aprobación**')
            for x in ('Origen Paso 4 aprobado','Responsable de incorporación','Clientes destinatarios','Estrategia, hitos y lanzamiento','Riesgos y recursos identificados','Aprobación documentada'):st.caption('○ '+x)
    st.download_button('↓ Resumen CSV',s.export_csv('plans'),'PMO_CENS_Paso5_Planes.csv',mime='text/csv')

def communication_page():
    header('02 · CAMBIO Y FORMACIÓN','Comunicación y formación','Capacitación para usar servicios concretos; distinta de la sensibilización general del Paso 1.')
    a,b=st.columns([1,4])
    with a:
        if st.button('＋ Nueva actividad',type='primary'):activity_modal()
    st.download_button('↓ Exportar CSV',s.export_csv('activities'),'PMO_CENS_Paso5_Actividades.csv',mime='text/csv')
    items=s.activities();train=[a for a in items if a['kind']=='Formación']
    cards([('Acciones registradas',len(items),'Comunicación y formación','megaphone'),('Realizadas',sum(a['status']=='Realizada' for a in items),'Con estado de ejecución','check-circle'),
      ('Formaciones completadas',sum(a['status']=='Realizada' for a in train),f'De {len(train)} programadas','graduation-cap'),('Con material',sum(bool(a['materials']) for a in items),'Documento o enlace registrado','folder-open')])
    with st.container(border=True):
        st.markdown('**Plan de divulgación y aprendizaje**')
        for item in items:
            a,b=st.columns([6,1]);a.write('**'+e(item['title'])+'** · '+e(item['kind'])+' · '+e(item['status']))
            a.caption(service_name(item['service_id'])+f" · {item['date'] or 'Sin fecha'} · {item['attendees'] if item['attendees'] is not None else '—'} asistentes")
            if b.button('Editar',key='p5_activ_'+item['id']):activity_modal(item['id'])
            st.divider()
        if not items:st.info('No hay actividades registradas. Crea acciones asociadas a un servicio.')

def pilot_page():
    header('03 · PILOTOS','Pilotos y soporte','Registra pilotos, evidencia, valoración inicial y dificultades antes de un despliegue general.')
    a,b,c=st.columns([1,1,4])
    if a.button('＋ Nuevo piloto',type='primary'):pilot_modal()
    if b.button('＋ Incidencia'):issue_modal()
    ps=s.pilots();issues=s.issues();ratings=[x['satisfaction'] for x in ps if x['satisfaction'] is not None]
    cards([('Pilotos',len(ps),'Con criterios y resultados','flask-conical'),('Completados',sum(x['status'] in ('Completado','Validado') for x in ps),'Terminación registrada','check-circle'),
      ('Incidencias abiertas',sum(x['status'] not in ('Resuelta','Descartada') for x in issues),'Por atender','alert-circle'),
      ('Satisfacción piloto',f"{sum(ratings)/len(ratings):.1f}/10" if ratings else '—','Solo calificaciones recibidas','star')])
    left,right=st.columns([1.2,1])
    with left:
        with st.container(border=True):
            st.markdown('**Seguimiento de pilotos**')
            for x in ps:
                a,b=st.columns([4,1]);a.write('**'+e(x['title'])+'**');a.caption(service_name(x['service_id'])+' · '+x['status'])
                if b.button('Editar',key='p5_pilot_'+x['id']):pilot_modal(x['id'])
                st.divider()
            if not ps:st.caption('Sin pilotos registrados.')
    with right:
        with st.container(border=True):
            st.markdown('**Soporte, observaciones y acciones**')
            for x in issues:
                a,b=st.columns([4,1]);a.write('**'+e(x['title'])+'**');a.caption(x['status']+' · '+service_name(x['service_id']))
                if b.button('Editar',key='p5_issue_'+x['id']):issue_modal(x['id'])
                st.divider()
            if not issues:st.caption('Sin incidencias registradas.')
    c,d=st.columns(2)
    c.download_button('↓ Pilotos CSV',s.export_csv('pilots'),'PMO_CENS_Paso5_Pilotos.csv',mime='text/csv')
    d.download_button('↓ Incidencias CSV',s.export_csv('issues'),'PMO_CENS_Paso5_Incidencias.csv',mime='text/csv')

def adoption_page():
    header('04 · TRANSICIÓN','Adopción y transición','Comprueba la preparación de los servicios y autoriza expresamente su entrada a operación.')
    ag=s.aggregates()
    rows=[(sr,s.readiness(sr['id'])) for sr in s.services()]
    prepared=[(sr,rd) for sr,rd in rows if rd['eligible'] and not rd['authorized']]
    authorized=[(sr,rd) for sr,rd in rows if rd['authorized'] and rd['eligible']]
    previously_authorized_blocked=[(sr,rd) for sr,rd in rows if rd['authorized'] and not rd['eligible']]
    cards([('Cobertura formación',pct(ag['training']),f"{ag['training'][0]}/{ag['training'][1]} personas únicas" if ag['training'][1] else 'Sin denominador','users'),
      ('Adopción inicial',pct(ag['adoption']),f"{ag['adoption'][0]}/{ag['adoption'][1]} clientes" if ag['adoption'][1] else 'Sin denominador','chart-no-axes-column'),
      ('Pilotos completados',pct(ag['pilots']),'Completados/registrados','flask-conical'),('Servicios autorizados',len(authorized),'Autorización expresa y sin bloqueos','check-circle')])
    if prepared:
        st.info(f'**{len(prepared)} servicio(s) listos para autorizar**, pero aún NO autorizados para operar. En cada uno pulsa **Revisar y autorizar**, registra al responsable y confirma **Autorizar expresamente para Paso 06**.')
    elif not authorized and rows:
        st.caption('Todavía no hay servicios autorizados. La cobertura, adopción y pilotos al 100% no sustituyen la autorización expresa de transición.')
    if previously_authorized_blocked:
        st.warning(f'{len(previously_authorized_blocked)} servicio(s) con autorización anterior tienen bloqueos sobrevenidos y no serán transferidos hasta resolverlos.')
    with st.container(border=True):
        st.markdown('**Preparación por servicio**')
        for sr,r in rows:
            a,b=st.columns([4,1])
            a.write('**'+public_code('servicio',sr['id'])+' · '+e(sr['nombre'])+'**')
            if r['authorized'] and r['eligible']:
                a.caption('Autorizado para Paso 06 · transferencia habilitada')
            elif r['authorized']:
                a.caption('Autorizado anteriormente, pero con bloqueos: '+'; '.join(r['blockers'][:3]))
            elif r['eligible']:
                a.caption('Preparación completa · PENDIENTE autorización expresa')
            else:
                a.caption('Pendiente: '+'; '.join(r['blockers'][:3]))
            label='Revisar y autorizar' if r['eligible'] and not r['authorized'] else 'Revisar'
            if b.button(label,key='p5_trans_'+sr['id']):adoption_modal(sr['id'])
            st.divider()
        if not rows:st.info('No existen servicios. Importa los aprobados del Paso 4.')
    with st.container(border=True):
        st.markdown('**Marco de resultados iniciales**')
        check_total=check_done=0
        for sr,_ in rows:
            ac=s.adoption(sr['id']);check=json.loads(ac['checks_json'])
            check_total+=sum(x!='na' for x in check.values());check_done+=sum(x=='cumple' for x in check.values())
        c,d=st.columns(2)
        c.metric('Preparación operativa',pct((check_done,check_total)))
        ratings=[p['satisfaction'] for p in s.pilots() if p['satisfaction'] is not None]
        d.metric('Satisfacción inicial',f'{sum(ratings)/len(ratings):.1f}/10' if ratings else '—')
        st.caption('La preparación operativa mide los criterios diligenciados; no equivale a autorización. Los tickets y resultados operativos se registran en el Paso 06.')
    st.download_button('↓ Exportar expediente Paso 6 (JSON)',dump(s.export_step6()),'CENS_Paso5_Servicios_para_Paso6.json',mime='application/json',type='primary')
    st.download_button('↓ Reporte adopción CSV',s.export_csv('adoption'),'PMO_CENS_Paso5_Adopcion.csv',mime='text/csv')
    if not authorized:
        st.caption('Transferencia deshabilitada: primero autoriza expresamente al menos un servicio en **Revisar y autorizar**. Este botón NO autoriza servicios ni cambia su estado.')
    if st.button('Transferir servicios YA AUTORIZADOS al catálogo del Paso 06',disabled=not bool(authorized),type='primary'):
        from . import step6
        try:
            result=step6.import_step5_direct()
            if result['nuevos']:
                st.success(f"Se incorporaron {result['nuevos']} servicio(s) al catálogo del Paso 06. Ya existentes: {result['existentes']}.")
            elif result['existentes']:
                st.info(f"No se crearon nuevos registros: {result['existentes']} servicio(s) ya estaban en el catálogo del Paso 06.")
            else:
                st.warning('No se importó ningún servicio. Revisa la autorización y los bloqueos actuales de cada ficha.')
        except Exception as ex:st.error(str(ex))

def evaluation_page():
    header('05 · PMI','Evaluación metodológica de incorporación','30 criterios y seis dimensiones. Calificación PMI independiente de la satisfacción de los clientes.')
    es=s.evaluations();draft=next((x for x in es if x['state']=='Borrador'),None)
    if not draft:
        with st.form('p5_start_eval'):
            owner=st.text_input('Responsable de la autoevaluación')
            submit=st.form_submit_button('Iniciar nueva evaluación PMI',type='primary')
        if submit:
            ok,key=call(s.new_evaluation,owner)
            if ok:st.session_state['p5_eval_id']=key;st.rerun()
    eid=st.session_state.get('p5_eval_id')
    if eid not in [e['id'] for e in es if e['state']=='Borrador']:eid=draft['id'] if draft else None
    summary=s.evaluation_summary(eid) if eid else None
    cards([('Criterios respondidos',f"{summary['answered']}/30" if summary else '0/30','Seis dimensiones','clipboard-list'),
      ('Puntuación',str(summary['score'])+'/150' if summary and summary['score'] is not None else '—','Solo evaluación completa','chart-bar'),
      ('Clasificación',summary['classification'] if summary else 'Pendiente','Sin valoración automática','badge-check'),
      ('Evaluaciones archivadas',sum(e['state']=='Finalizada' for e in es),'Historial sin sobrescritura','archive')])
    if eid:
        dim=st.selectbox('Dimensión PMI',range(6),format_func=lambda n:f'{n+1:02d} · {s.DIMENSIONS[n][0]}',key='p5_dim')
        saved={x['number']:x for x in s.answers(eid)}
        with st.form('p5_pmi_dim'):
            values=[]
            for pos,question in enumerate(s.DIMENSIONS[dim][1],1):
                num=dim*5+pos;old=saved.get(num)
                st.markdown(f'**{pos}. {e(question)}**')
                val=st.radio('Puntuación',options=[None,1,2,3,4,5],index=(old['score'] if old else 0),
                   key='p5_q_'+str(num),format_func=lambda x:'Sin responder' if x is None else str(x),horizontal=True)
                a,b=st.columns(2)
                observation=a.text_input('Observación',value=old['observation'] if old else '',key='p5_obs_'+str(num))
                evidence=b.text_input('Evidencia / referencia',value=old['evidence'] if old else '',key='p5_ev_'+str(num))
                values.append((num,val,observation,evidence));st.divider()
            submit=st.form_submit_button('Guardar respuestas de la dimensión',type='primary')
        if submit:
            try:
                for num,val,obs,ref in values:
                    if val is not None:s.save_answer(eid,num,val,obs,ref)
                st.success('Respuestas guardadas.');st.rerun()
            except Exception as ex:st.error(str(ex))
        if summary and summary['answered']==30:
            if st.button('Finalizar y archivar evaluación',type='primary'):
                ok,_=call(s.finish_evaluation,eid)
                if ok:st.session_state.pop('p5_eval_id',None);st.rerun()
        elif summary:st.caption(f'Faltan {30-summary["answered"]} respuestas para establecer clasificación.')
    st.markdown('##### Resultados por dimensión')
    if summary:
        for d in summary['dimensions']:
            st.write(f"{d['title']} · {d['answered']}/5 respuestas")
            st.progress(d['score']/25)
    st.markdown('##### Historial')
    historic=[x for x in s.evaluations() if x['state']=='Finalizada']
    if historic:st.dataframe([{'Versión':h['version'],'Responsable':h['owner'],'Puntaje':h['score'],'Clasificación':h['classification'],'Fecha':h['finished_at']} for h in historic],hide_index=True,use_container_width=True)
    else:st.caption('Sin evaluaciones archivadas.')
    if eid:
        st.download_button('↓ Exportar evaluación PMI',dump({'evaluation':s.evaluation(eid),'answers':s.answers(eid),'summary':s.evaluation_summary(eid)}),
             'PMO_CENS_Paso5_Evaluacion_PMI.json',mime='application/json')

def page(name):
    views={NAV[0]:plans_page,NAV[1]:communication_page,NAV[2]:pilot_page,NAV[3]:adoption_page,NAV[4]:evaluation_page}
    views[name]()
