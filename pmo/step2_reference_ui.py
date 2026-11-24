"""Pantallas del Paso 2 V0.8, separadas conforme al HTML de referencia del usuario.

No precarga cifras de ejemplo. Las vistas utilizan el repositorio existente (SQLite)
y delegan los formularios originales, preservando sus validaciones y auditoría.
"""
from __future__ import annotations
from collections import Counter
from . import step2 as p2, step2_ui as v7
from .step2_catalog import OUTCOMES,SERVICES
from .clients import list_clients
from .ui import e
import streamlit as st


def heading(text,desc=''):
    st.markdown(f'<div class="p2-ref-heading">{e(text)}</div><div class="p2-ref-caption">{e(desc)}</div>',unsafe_allow_html=True)


def bars(items, limit=8):
    """Render de barras simple y accesible sin agregar dependencias externas."""
    items=list(items)[:limit]
    if not items:
        st.caption('Sin registros suficientes para mostrar resultados.');return
    maximum=max(float(s) for _,s in items) or 1.0
    html=''.join(f'<div class="p2-ref-bar-row"><div title="{e(name)}">{e(name)}</div><div class="p2-ref-track"><i style="width:{max(0,min(100,100*float(score)/maximum)):.2f}%"></i></div><strong>{float(score):.1f}%</strong></div>' for name,score in items)
    st.markdown(f'<div class="p2-ref-bars">{html}</div>',unsafe_allow_html=True)


def route():
    parts=[('01','Planificar la evaluación','Definir participantes, enfoque y objetivos'),
           ('02','Escuchar la voz del cliente','Entrevistas, encuestas y grupos focales'),
           ('03','Analizar evidencias','Identificar dificultades, ganancias y brechas'),
           ('04','Priorizar necesidades','Ponderar resultados y determinar servicios candidatos'),
           ('05','Validar y comunicar','Documentar hallazgos y decisiones')]
    cards=''.join(f'<div class="p2-ref-route-row"><b>{number}</b><div><strong>{e(title)}</strong><small>{e(desc)}</small></div></div>' for number,title,desc in parts)
    st.markdown(f'<div class="p2-ref-route">{cards}</div>',unsafe_allow_html=True)


def _nav(name):
    st.session_state['pmo_active_p2_page']=name


def overview(diag,item):
    summary=p2.summary(diag)
    interviews=p2.interviews(diag)
    people=list_clients(status='Activos')
    raised={x['cliente_id'] for x in interviews}
    visited={x['id']:x for x in people if x['id'] in raised}
    locations={x['sede'] for x in visited.values() if x.get('sede')}
    completed=sum(len(x['priorities'])==5 for x in p2._participant_records(diag))
    v7.kpis([
        ('Expectativas completas',str(completed),'Clientes con cinco preferencias guardadas','✓',''),
        ('Clientes con levantamiento',str(len(raised)),'Actividades documentadas; no equivale a respuesta','♙','blue'),
        ('Dependencias de levantamiento',str(summary['areas']),'Dependencias con actividades registradas','▤','orange'),
        ('Necesidades validadas',str(summary['necesidades_validadas']),'Decisiones respaldadas','✓','purple'),
    ])
    v7._maturity_cycle_summary(item)
    l,r=st.columns([1.53,1],gap='medium')
    runs=p2.runs(diag)
    with l:
        with st.container(border=True):
            heading('Servicios candidatos más relevantes','Ranking de la última corrida guardada')
            if runs:
                data=p2.get_run(runs[0]['id'])['resultados']
                bars([(x['name'],x['score']) for x in data['services']],5)
                st.caption(f"Último cálculo · {data['participants']} respuestas completas · {data.get('matrix_model','Versión no identificada')}")
                st.button('Ver cálculo →',key='p2v8_nav_calculation',on_click=_nav,args=('Motor Excel · Priorización',))
            else:
                st.info('El ranking estará disponible cuando registres cinco prioridades por participante y ejecutes el análisis.')
                st.button('Abrir motor de priorización →',key='p2v8_nav_priority',on_click=_nav,args=('Motor Excel · Priorización',))
    with r:
        with st.container(border=True):
            heading('Estado del diagnóstico','Lectura rápida de los registros disponibles')
            audit=p2.assessments(diag)
            last=audit[0] if audit else None
            total_ans=len(p2.answers(last['id'])) if last else 0
            values=[('Instrumento PMI · Paso 2',f'{total_ans}/25 respuestas'),
                    ('Expectativas priorizadas',f"{sum(len(x['priorities'])==5 for x in p2._participant_records(diag))} participantes"),
                    ('Necesidades por validar',str(summary['necesidades_pendientes'])),
                    ('Servicios preseleccionados',str(sum(x['estado']=='Preseleccionado' for x in p2.candidates(diag))))]
            for label,value in values:
                st.markdown(f'<div class="p2-ref-pair"><span>{e(label)}</span><b>{e(value)}</b></div>',unsafe_allow_html=True)
            st.markdown('<div class="p2-ref-note"><strong>Ruta siguiente</strong><div>Necesidades → resultados → servicios candidatos</div></div>',unsafe_allow_html=True)
    l,r=st.columns([1.53,1],gap='medium')
    with l:
        with st.container(border=True):
            heading('Resultados esperados que lideran','Preferencias declaradas por los clientes de la muestra')
            if runs:
                data=p2.get_run(runs[0]['id'])['resultados']
                bars([(x['name'],x['score']) for x in data['outcomes']],6)
            else:
                st.caption('Registra expectativas completas para consultar la relevancia de los resultados.')
    with r:
        with st.container(border=True):
            heading('Cadena de trazabilidad','De la voz del cliente a la propuesta de valor')
            st.markdown('''<div class="p2-ref-causal">
                <div><b>01</b><span><strong>Voz del cliente</strong><small>Levantamientos y resultados esperados</small></span></div>
                <div><b>02</b><span><strong>Necesidades verificadas</strong><small>Dificultades, ganancias y fuentes documentales</small></span></div>
                <div><b>03</b><span><strong>Servicios candidatos</strong><small>Ranking contrastado con decisiones de validación</small></span></div>
            </div>''',unsafe_allow_html=True)
    st.caption('Los porcentajes proceden exclusivamente de corridas guardadas en este diagnóstico, no del prototipo HTML.')


def _radar_svg(rows):
    order=list(p2.MATURITY)
    source={x['dimension']:x for x in rows}
    def coords(prop):
        vals=[float(source[n][prop]) for n in order]
        xy=[(160,120-90*vals[0]/5),(160+90*vals[1]/5,120),
            (160,120+90*vals[2]/5),(160-90*vals[3]/5,120)]
        return ' '.join(f'{x:.1f},{y:.1f}' for x,y in xy)
    grid=''.join(f'<polygon points="160,{120-r} {160+r},120 160,{120+r} {160-r},120" fill="none" stroke="#DDE8EE" stroke-width="1"/>' for r in (18,36,54,72,90))
    caption=[('Estandarización',160,13,'middle'),('Gobernanza',300,124,'start'),('Seguimiento',160,237,'middle'),('Metodologías',20,124,'end')]
    labels=''.join(f'<text x="{x}" y="{y}" text-anchor="{anchor}" fill="#657E8F" font-size="10">{e(name)}</text>' for name,x,y,anchor in caption)
    return (f'<svg viewBox="0 0 350 255" role="img" aria-label="Radar de percepción actual y deseada" width="100%" xmlns="http://www.w3.org/2000/svg">'
            +grid+'<path d="M160 30 V210 M70 120 H250" stroke="#DDE8EE" fill="none"/>'
            +f'<polygon points="{coords("deseado")}" fill="#ED925021" stroke="#ED9250" stroke-width="2"/>'
            +f'<polygon points="{coords("actual")}" fill="#0B9A9F24" stroke="#0B9A9F" stroke-width="2.5"/>'
            +labels+'</svg>')


def maturity(diag,item):
    """Panel independiente de madurez CENS, sin lectura del diagnóstico PMOGA."""
    from .step2_maturity_annual_ui import render_history
    render_history(None,None)


def plan(diag,item):
    summary=p2.summary(diag)
    visits=p2.interviews(diag)
    v7.kpis([
        ('Población objetivo',str(item['poblacion_objetivo']) if item['poblacion_objetivo'] else '—','Definida en la ficha','♙',''),
        ('Participantes de muestra',str(len({x['cliente_id'] for x in visits})),'Clientes con levantamientos','▤','blue'),
        ('Métodos aplicados',str(len({x['metodo'] for x in visits})),'Entrevistas, encuestas y otros','▦','orange'),
        ('Ciclo',str(item['ciclo']),'Periodo del diagnóstico','▧','purple')])
    l,r=st.columns([1.6,1],gap='medium')
    with l:
        with st.container(border=True):
            heading('Ficha del diagnóstico','Parámetros y alcance del periodo vigente')
            fields=[('Nombre',item['nombre']),('Alcance',item['alcance'] or 'Sin definir'),
                    ('Responsable',item['responsable']),('Estado',item['estado']),
                    ('Población objetivo',item['poblacion_objetivo'] or 'Sin definir')]
            for name,value in fields:st.markdown(f'<div class="p2-ref-pair"><span>{e(name)}</span><b>{e(value)}</b></div>',unsafe_allow_html=True)
            st.caption('La muestra y los pesos de roles deben revisarse antes de interpretar el ranking.')
    with r:
        with st.container(border=True):
            heading('Ruta de ejecución','Cinco actividades para desarrollar la evaluación')
            route()
    l,r=st.columns([1.25,1],gap='medium')
    with l:
        with st.container(border=True):
            heading('Composición por rol','Participantes registrados en actividades')
            people=list_clients(status='Activos');index={p['id']:p for p in people}
            counts=Counter(index[x['cliente_id']].get('segmento') or 'Sin clasificar' for x in visits if x['cliente_id'] in index)
            total=max(counts.values(),default=0)
            if not counts:st.caption('Sin levantamientos registrados en el ciclo.')
            else:
                for group,n in counts.most_common():
                    st.markdown(f'<div class="p2-ref-progress-title">{e(group)} · {n}</div><div class="p2-ref-track"><i style="width:{round(100*n/total,2)}%"></i></div>',unsafe_allow_html=True)
    with r:
        with st.container(border=True):
            heading('Instrumentos de levantamiento','Actividades que pueden registrarse para el diagnóstico')
            for title,desc in [('Entrevistas individuales','Necesidades explícitas e implícitas'),('Encuestas de expectativas','Resultados preferidos y prioridades declaradas'),('Grupos focales','Coincidencias y tensiones entre roles')]:
                st.markdown(f'<div class="p2-ref-route-row"><b>▤</b><div><strong>{title}</strong><small>{desc}</small></div></div>',unsafe_allow_html=True)
    with st.expander('✎ Editar plan de evaluación',expanded=False):
        v7._plan_form(diag,item)


def clients(diag,item):
    """Directorio unificado: Rol, Dependencia y Equipo son categorías distintas."""
    from .v0391_clients import client_role
    records=list_clients(status='Activos'); interviews=p2.interviews(diag)
    unknown={'pendiente de confirmar','sin clasificar','sin registrar','sin dato','sin asignar'}
    roles={client_role(x) for x in records if client_role(x).strip() and client_role(x).casefold() not in unknown}
    dependencias={str(x.get('dependencia') or '').strip().casefold() for x in records
                  if str(x.get('dependencia') or '').strip().casefold() not in unknown | {''}}
    equipos={str(x.get('equipo_trabajo') or '').strip().casefold() for x in records
             if str(x.get('equipo_trabajo') or '').strip().casefold() not in unknown | {''}}
    # La versión general de kpis usa 4 columnas; esta sección precisa 5 KPIs.
    from .ui import kpi
    stats=[('Clientes disponibles',str(len(records)),'Directorio único del Paso 1','♙','orange'),
           ('Entrevistas y encuestas',str(len(interviews)),'Actividades del diagnóstico','▤','orange'),
           ('Roles',str(len(roles)),'Roles identificados en el directorio','◎','blue'),
           ('Dependencias',str(len(dependencias)),'Dependencias con clientes activos','⌁','purple'),
           ('Equipos de trabajo',str(len(equipos)),'Equipos registrados en las dependencias','▦','teal')]
    for col,(label,value,foot,icon,color) in zip(st.columns(5,gap='small'),stats):
        with col:kpi(label,value,foot,icon,color)
    v7._clients_section(diag,item)
    heading('Actividades de levantamiento','Planificación, registro y seguimiento de entrevistas y encuestas')
    v7._interviews_section(diag,item)


def expectations(diag,item):
    mode=st.radio('Gestión de expectativas',
                  ['Registrar o editar respuesta individual','Importar o actualizar respuestas desde Excel'],
                  horizontal=True,key='p2v8_expectations_mode')
    if mode=='Importar o actualizar respuestas desde Excel':
        st.caption('Este archivo agrega o actualiza preferencias del diagnóstico seleccionado; no crea otro diagnóstico.')
        v7._load_excel_section(diag,item)
        return
    people=list_clients(status='Activos')
    participant_data=p2._participant_records(diag)
    complete=sum(len(x['priorities'])==5 for x in participant_data)
    v7.kpis([('Resultados disponibles','30','Catálogo de resultados de valor','◎',''),
             ('Respuestas completas',str(complete),'Cinco prioridades distintas','✓','orange'),
             ('Clientes activos',str(len(people)),'Compartidos con el Paso 1','♙','blue'),
             ('Resultados elegidos',str(len({oid for x in participant_data for oid in x['priorities']})),'Distintos resultados priorizados','▦','purple')])
    if not people:
        st.warning('Primero registra los clientes activos en el Paso 1.');return
    labels=v7.person_option(people)
    l,r=st.columns([1.72,1],gap='medium')
    with r:
        with st.container(border=True):
            heading('Prioridades del cliente','Selecciona una persona y organiza sus cinco resultados')
            answered_ids={r['cliente_id'] for r in p2.expectations(diag)}
            available_new=[p['id'] for p in people if p['id'] not in answered_ids]
            if st.button('＋ Nueva respuesta de otro cliente',key='p2v8_new_client_response',
                         disabled=not available_new, help='Selecciona el primer cliente activo que todavía no tiene prioridades guardadas'):
                st.session_state['p2v8_outcome_client']=available_new[0]
                st.rerun()
            client=st.selectbox('Participante',list(labels),format_func=lambda k:labels[k],key='p2v8_outcome_client')
            old=p2.expectations(diag,client)
            if old:
                st.info('Este cliente tiene una respuesta guardada. Puedes revisarla o reemplazarla con confirmación; el cambio quedará auditado.')
            else:
                st.caption('Nueva respuesta: selecciona cinco resultados distintos en orden de prioridad.')
            selkey=f'p2v8_selected_{diag}_{client}'
            if selkey not in st.session_state:
                st.session_state[selkey]=[x['resultado_id'] for x in old]
            selected=st.session_state[selkey]
            st.progress(len(selected)/5,text=f'{len(selected)} de 5 resultados seleccionados')
            if not selected:st.caption('Selecciona resultados desde el catálogo de la izquierda.')
            for pos,oid in enumerate(selected):
                c0,c1,c2,c3=st.columns([7,1,1,1],gap='small',vertical_alignment='center')
                with c0:
                    st.markdown(f'<div class="p2-ref-ranked"><b>{pos+1}</b><span>{e(OUTCOMES[oid])}<small>{5-pos} puntos por la posición</small></span></div>',unsafe_allow_html=True)
                with c1:
                    if st.button('↑',key=f'p2v8_up_{client}_{pos}',disabled=pos==0,help='Subir prioridad'):
                        selected[pos-1],selected[pos]=selected[pos],selected[pos-1];st.rerun()
                with c2:
                    if st.button('↓',key=f'p2v8_down_{client}_{pos}',disabled=pos==len(selected)-1,help='Bajar prioridad'):
                        selected[pos],selected[pos+1]=selected[pos+1],selected[pos];st.rerun()
                with c3:
                    if st.button('×',key=f'p2v8_remove_{client}_{pos}',help='Quitar resultado'):
                        selected.pop(pos);st.rerun()
            a,b=st.columns(2)
            with a:
                if st.button('Limpiar selección',key=f'p2v8_reset_{client}',use_container_width=True):
                    st.session_state[selkey]=[];st.rerun()
            with b:
                if st.button('Recuperar guardado',key=f'p2v8_reload_{client}',use_container_width=True):
                    st.session_state[selkey]=[x['resultado_id'] for x in p2.expectations(diag,client)];st.rerun()
            with st.form(f'p2v8_priority_save_{diag}_{client}'):
                actor=st.text_input('Responsable del registro *')
                confirm=st.checkbox('Confirmo que deseo sobrescribir las cinco prioridades guardadas de este cliente.',
                                    value=False) if old else True
                sent=st.form_submit_button('Actualizar prioridades' if old else 'Guardar nueva respuesta',
                                           type='primary',use_container_width=True)
            if sent:
                if old and not confirm:
                    st.warning('Para actualizar una respuesta guardada debes confirmar explícitamente el reemplazo.')
                else:
                    try:
                        notes={oid:st.session_state.get(f'p2v8_note_{diag}_{client}_{oid}','') for oid in selected}
                        p2.save_priorities(diag,client,list(selected),actor,notes=notes)
                        st.success('Respuesta guardada y auditada. Las corridas previas del motor no se sobrescriben.');st.rerun()
                    except v7.ValidationError as ex:v7.err(ex)
        with st.container(border=True):
            heading('Indagación y evidencia','Profundiza en un resultado deseado antes de interpretarlo')
            if selected:
                choose=st.selectbox('Resultado a explorar',selected,format_func=lambda oid:f'O-{oid:02d} · {OUTCOMES[oid]}',key='p2v8_note_choice')
                noteval=next((x['notas'] for x in old if x['resultado_id']==choose),'')
                st.text_area('¿Qué dificultad concreta expresa el cliente y cuál es su evidencia?',value=noteval,
                    key=f'p2v8_note_{diag}_{client}_{choose}',height=105)
                st.caption('Las notas se guardan junto con las prioridades al seleccionar «Guardar prioridades».')
            else:st.caption('Selecciona un resultado para registrar observaciones o evidencias de la entrevista.')
    with l:
        with st.container(border=True):
            heading('Catálogo de 30 resultados potenciales','Selecciona hasta cinco. El orden puede modificarse en el panel derecho.')
            search=st.text_input('Buscar resultado',placeholder='Nombre del resultado o código...',key='p2v8_outcome_search')
            found=[(oid,name) for oid,name in OUTCOMES.items() if search.casefold() in f'O-{oid:02d} {name}'.casefold()]
            if not found:st.info('No hay resultados que coincidan con la búsqueda.')
            for start in range(0,len(found),3):
                cols=st.columns(3,gap='small')
                for col,(oid,name) in zip(cols,found[start:start+3]):
                    with col:
                        is_selected=oid in selected
                        with st.container(border=True):
                            st.caption(f'O-{oid:02d} · '+ ('Seleccionado' if is_selected else 'Disponible'))
                            if st.button(name, key=f'p2v8_outcome_{diag}_{client}_{oid}',
                              use_container_width=True,type='primary' if is_selected else 'secondary',
                              help='Seleccionar o retirar este resultado'):
                                if is_selected:selected.remove(oid)
                                elif len(selected)<5:selected.append(oid)
                                else:st.toast('Solo se pueden seleccionar cinco resultados.',icon='⚠️')
                                st.rerun()
            st.caption('La asignación 5–4–3–2–1 se determina por la posición, no por una puntuación indicada directamente por el cliente.')
    with st.expander('Ver participantes y estado de sus expectativas',expanded=False):
        records=p2.expectations(diag)
        compiled={}
        for x in records:compiled.setdefault((x['cliente_id'],x['nombre'],x['segmento']),[]).append(x['resultado_id'])
        if compiled:
            st.dataframe([{'Cliente':name,'Grupo':group or 'Sin clasificar','Prioridades':', '.join(f'O-{n:02d}' for n in ids),
                           'Completas':'Sí' if len(ids)==5 else 'No'} for (_,name,group),ids in compiled.items()],
                           hide_index=True,use_container_width=True)
        else:st.caption('Todavía no hay expectativas registradas.')


def needs(diag,item):
    from .needs_console import public_codes, filter_needs
    entries = p2.needs(diag)
    codes = public_codes(diag) if entries else {}
    for item_row in entries:
        item_row['codigo_publico'] = codes.get(item_row['id'], 'Sin código')
    levels = Counter(x['estado'] for x in entries)
    v7.kpis([('Hallazgos registrados',str(len(entries)),'Dificultades documentadas','▤','orange'),
             ('Validadas',str(levels['Validada']),'Decisiones registradas','✓','blue'),
             ('En validación',str(levels['En validación']),'Pendientes de revisión','◷','purple'),
             ('Con fuente',str(sum(bool(x.get('fuente')) for x in entries)),'Fuente o evidencia referenciada','▧','teal')])
    heading('Consultar y validar necesidades','Filtros combinables por dependencia, rol, resultado esperado y cliente')
    if entries:
        filter_key = f'p2v8_need_{diag}_'
        status = st.pills('Estado', ['Todas','Registrada','En validación','Validada','Descartada'],
                          selection_mode='single',default='Todas',key=filter_key+'state')
        deps = ['Todas',*sorted({x['dependencia'] for x in entries if x['dependencia']},key=str.casefold)]
        groups = ['Todos',*sorted({x.get('segmento') or 'Sin rol / cliente' for x in entries},key=str.casefold)]
        clients = {x['cliente_id']:(x.get('cliente_codigo') or '')+' · '+(x.get('cliente') or '')
                   for x in entries if x.get('cliente_id')}
        choices = ['Todos',*sorted(clients,key=lambda k: clients[k].casefold())]
        if any(not x.get('cliente_id') for x in entries): choices.append('__general__')
        f1,f2,f3,f4=st.columns(4,gap='small')
        with f1: department=st.selectbox('Dependencia',deps,key=filter_key+'dep')
        with f2: segment=st.selectbox('Rol',groups,key=filter_key+'segment')
        with f3:
            result=st.selectbox('Resultado esperado (1–30)',[-1,0,*OUTCOMES],
                  format_func=lambda n:'Todos los resultados' if n==-1 else ('Sin asignar' if n==0 else f'{n:02d} · {OUTCOMES[n]}'),
                  key=filter_key+'result')
        with f4:
            client=st.selectbox('Cliente',choices,format_func=lambda k:'Todos los clientes' if k=='Todos' else (
                'Necesidad general / sin cliente' if k=='__general__' else clients[k]),key=filter_key+'client')
        term=st.text_input('Buscar necesidad por código, dificultad, ganancia o fuente',
                           placeholder='Ej.: NEC-0012, retrasos, mantenimiento...',key=filter_key+'search')
        filtered=filter_needs(entries,status=status,department=department,segment=segment,
                              result=result,client=client,search=term)
        st.caption(f'{len(filtered)} de {len(entries)} necesidades coinciden con los filtros. '
                   'Los roles sin cliente se muestran como «Sin rol / cliente».')
    else:
        filtered=[]
    # El panel de gestión/validación se sitúa ANTES del listado largo.
    heading('Registrar y gestionar necesidades','Seleccione una necesidad filtrada para consultar su ficha o registrar la decisión')
    v7._needs_section(diag,item,display_entries=filtered,public_code_map=codes)
    if not entries:
        return
    heading('Consola Pain–Gain','Tarjetas compactas, contraídas inicialmente; active la vista detallada cuando la necesite')
    show=st.checkbox('Mostrar tarjetas Pain–Gain',value=False,key=f'p2v8_show_needs_{diag}',
                     help='Desmarque para contraer todas las tarjetas. Los filtros y la tabla permanecen disponibles.')
    if not filtered:
        st.info('No hay necesidades que coincidan con los filtros seleccionados.');return
    if not show:
        st.caption('Tarjetas contraídas. Use «Consultar necesidad» o active la vista de tarjetas para explorar el diagnóstico.')
        return
    pages=(len(filtered)+8)//9
    page=st.selectbox('Página de tarjetas',list(range(1,pages+1)),
                      format_func=lambda n:f'Página {n} de {pages}',key=f'p2v8_need_page_{diag}')
    visible=filtered[(page-1)*9:page*9]
    for pos in range(0,len(visible),3):
        cols=st.columns(3,gap='small')
        for col,q in zip(cols,visible[pos:pos+3]):
            with col:
                st.markdown(f'<div class="p2-ref-need-card"><div class="p2-ref-need-title"><strong>{e(q["codigo_publico"])}</strong><span>{e(q["estado"])}</span></div><b>{e(q["dependencia"])}</b><div class="p2-ref-pain"><small>SITUACIÓN / DOLOR</small>{e(q["problema"])}</div><div class="p2-ref-gain"><small>RESULTADO / GANANCIA</small>{e(q["ganancia"])}</div><div class="p2-ref-need-footer">{e("O-"+str(q["resultado_id"]).zfill(2) if q.get("resultado_id") else "Resultado no asignado")} · {e(q["impacto"])}</div></div>',unsafe_allow_html=True)
    st.caption('Los estados registrados son declarativos y no equivalen a aprobaciones institucionales autenticadas.')


def prioritization(diag,item):
    heading('Ponderación de roles','Cada cliente aporta cinco prioridades. Los pesos estratégicos suman 100%.')
    st.info('El recorrido completo de priorización está integrado en «Motor Excel · Priorización», con captura, validación, ponderación, resultados y auditoría.')
    st.button('Abrir recorrido completo →',on_click=_nav,args=('Motor Excel · Priorización',),key=f'p2v032_priority_to_engine_{diag}')
    current=p2.runs(diag)
    if current:
        result=p2.get_run(current[0]['id'])['resultados']
        l,r=st.columns([1.45,1],gap='medium')
        with l:
            with st.container(border=True):
                heading('Relevancia de resultados','Última corrida conservada')
                bars([(x['name'],x['score']) for x in result['outcomes']],8)
        with r:
            with st.container(border=True):
                heading('Servicios candidatos','Según la matriz utilizada')
                bars([(x['name'],x['score']) for x in result['services']],8)
        st.caption('El ranking es una recomendación analítica; no sustituye la validación con clientes y responsables.')
        with st.expander('Resultados detallados de la vista clásica',expanded=False):
            v7._results_section(diag,item)
    with st.container(border=True):
        heading('Cómo se calcula','Orden 5–4–3–2–1 → normalización por grupo → pesos → matriz 30 × 26 → ranking')
        steps=['01 · Prioridades por persona','02 · Normalización dentro del grupo','03 · Ponderación de roles','04 · Correspondencias resultado–servicio','05 · Relevancia de cada servicio']
        st.markdown('<div class="p2-ref-steps">'+''.join(f'<span>{e(x)}</span>' for x in steps)+'</div>',unsafe_allow_html=True)
        v7._weights_section(diag,item)


def engine(diag,item):
    """Unifica la captura, la validación, la ponderación y el ranking de V5.

    Todas las operaciones mutadoras delegan en las funciones V0.31 probadas.
    """
    from .step2_engine_ui import render_engine
    render_engine(diag,item)


def matrix(diag,item):
    from . import matrix_ui
    heading('Matriz PMO Value Ring · 30 × 26','780 cruces · X2 documental · escenario experimental previo · V5 reconstruida con 30 FOCO.')
    matrix_ui.panel(diag)


def validation(diag,item, *, show_transfer=True):
    entries=p2.needs(diag)
    valid=sum(x['estado']=='Validada' for x in entries)
    cand=p2.candidates(diag)
    run=p2.runs(diag)
    outcomes=p2.get_run(run[0]['id'])['resultados']['outcomes'][:5] if run else []
    v7.kpis([('Resultados líderes',str(len(outcomes)),'A partir del análisis disponible','◎',''),
            ('Roles evaluados',str(len(p2.groups_with_participants(diag))),'Con respuestas disponibles','♙','blue'),
            ('Preselección MVS',str(sum(x['estado']=='Preseleccionado' for x in cand)),'Decisión provisional registrada','✓','orange'),
            ('Necesidades validadas',str(valid),'Sin aprobación automática de servicios','▤','purple')])
    if run:
        heading('Matriz de expectativas por rol','Importancia relativa de los cinco principales resultados en cada rol')
        data=p2.get_run(run[0]['id'])['resultados'];cols=outcomes
        head='<tr><th>Rol</th>'+''.join(f'<th>O-{x["id"]:02d}<small>{e(x["name"][:38])}</small></th>' for x in cols)+'</tr>'
        body=''
        for name,group in data['groups'].items():
            values=group.get('outcomes',{});cells=''
            for x in cols:
                v=100*float(values.get(str(x['id']),values.get(x['id'],0)))
                alpha=.08+.42*max(0,min(1,v/50))
                cells+=f'<td style="background:rgba(11,154,159,{alpha:.2f})">{v:.0f}%</td>'
            body+=f'<tr><th>{e(name)}</th>{cells}</tr>'
        st.markdown(f'<div class="p2-ref-table-scroll"><table class="p2-ref-table">{head}{body}</table></div>',unsafe_allow_html=True)
    l,r=st.columns([1.5,1],gap='medium')
    with l:
        with st.container(border=True):
            heading('Servicios mínimos viables · preselección','Servicios candidatos pendientes de validación formal')
            candidate_map={x['servicio_id']:x for x in cand}
            for service in list(SERVICES)[:26]:
                if service not in candidate_map:continue
                row=candidate_map[service]
                st.markdown(f'<div class="p2-ref-pair"><span>{e(SERVICES[service])}</span><b>{e(row["estado"])}</b></div>',unsafe_allow_html=True)
            if not cand:st.caption('No hay decisiones sobre servicios candidatos todavía.')
    with r:
        with st.container(border=True):
            heading('Control de avance y decisiones','Antes de preparar el Paso 3')
            for x in [('01','Validar necesidades con los clientes'),('02','Examinar la priorización'),('03','Seleccionar candidatos MVS'),('04','Preparar el expediente para Paso 3')]:
                st.markdown(f'<div class="p2-ref-route-row"><b>{x[0]}</b><div><strong>{x[1]}</strong></div></div>',unsafe_allow_html=True)
            if show_transfer:
                st.download_button('↓ Descargar expediente de transición',p2.transfer_json(diag),file_name=f'PMO_CENS_PASO2_{diag[:8]}.json',mime='application/json',key='p2v8_transfer')
    with st.expander('＋ Registrar o cambiar decisión sobre un servicio candidato',expanded=False):
        with st.form('p2v8_candidate_form'):
            a,b=st.columns(2)
            svc=a.selectbox('Servicio del catálogo (26) *',list(SERVICES),
                format_func=lambda sid:f'S-{sid:02d} · {SERVICES[sid]}')
            state=b.selectbox('Estado',['Preseleccionado','En validación','Validado','Descartado'])
            reason=st.text_area('Justificación y referencia de validación *',height=110)
            owner=st.text_input('Responsable que registra *')
            sent=st.form_submit_button('Guardar decisión',type='primary')
        if sent:
            try:
                p2.set_candidate(diag,svc,state,reason,owner)
                st.success('Decisión guardada con registro de auditoría.');st.rerun()
            except v7.ValidationError as ex:v7.err(ex)
        st.caption('Las decisiones registradas son declarativas. Esta versión local no verifica la identidad corporativa de quien aprueba.')


def assessment(diag,item):
    audits=p2.assessments(diag)
    last=audits[0] if audits else None
    answered=len(p2.answers(last['id'])) if last else 0
    status=last['estado'] if last else 'Sin iniciar'
    score=last['puntaje'] if last and status=='Finalizada' else None
    v7.kpis([('Respuestas diligenciadas',f'{answered}/25','Cinco dimensiones','▤',''),
            ('Puntaje',f'{score}/125' if score is not None else '— / 125','No clasificar cuestionarios incompletos','▥','blue'),
            ('Clasificación',last['clasificacion'] if score is not None else 'Sin concluir','Requiere evaluación completa','✓','orange'),
            ('Ciclo',str(item['ciclo']),'Diagnóstico activo','▧','purple')])
    v7._assessment_section(diag,item)
    st.caption('Los enunciados son adaptaciones CENS, no reproducción oficial íntegra del cuestionario PMI.')


def evidence(diag,item):
    from .needs_console import public_codes
    linked_need_codes=public_codes(diag)
    references=p2.evidence(diag)
    visits=p2.interviews(diag)
    all_needs=p2.needs(diag)
    assessments=p2.assessments(diag)
    audit_count=max([len(p2.answers(x['id'])) for x in assessments],default=0)
    v7.kpis([('Referencias',str(len(references)),'Documentos y enlaces registrados','▧',''),
        ('Levantamientos',str(len(visits)),'Actividades documentadas','♙','blue'),
        ('Necesidades',str(len(all_needs)),'Hallazgos vinculables','▤','orange'),
        ('Autoevaluación',f'{audit_count}/25','Criterios respondidos','✓','purple')])
    l,r=st.columns([1.58,1],gap='medium')
    with l:
        with st.container(border=True):
            heading('Repositorio de evidencias','Referencias y metadatos que respaldan el diagnóstico')
            if references:
                st.dataframe([{'Código':x['id'][:8],'Descripción':x['titulo'],'Tipo':x['tipo'],'Fecha':x['fecha'],'Necesidad':linked_need_codes.get(x['necesidad_id'],'Sin asociar')} for x in references],hide_index=True,use_container_width=True)
            else:st.caption('Aún no hay documentos o enlaces registrados.')
    with r:
        with st.container(border=True):
            heading('Preparación del informe ejecutivo','Contenido para sustentar la propuesta de valor')
            for n,text in enumerate(['Caracterización de clientes','Resultados esperados','Necesidades y evidencias','Servicios candidatos','Observaciones y decisiones pendientes'],1):
                st.markdown(f'<div class="p2-ref-route-row"><b>{n:02d}</b><div><strong>{text}</strong></div></div>',unsafe_allow_html=True)
    with st.expander('＋ Registrar evidencia / exportar expediente',expanded=False):
        v7._evidence_section(diag,item)
    st.markdown('<div class="p2-ref-footer"><small>CONEXIÓN CON EL SIGUIENTE PASO</small><h3>De los hallazgos a la propuesta de valor</h3><p>La salida del Paso 2 es un conjunto verificable de necesidades, prioridades y servicios candidatos. El Paso 03 cuenta con lienzos de valor y soluciones editables; la transferencia requiere revisión y validación institucional.</p></div>',unsafe_allow_html=True)
    st.download_button('↓ Descargar paquete de transición',p2.transfer_json(diag),file_name=f'PMO_CENS_P2_TRANSICION_{diag[:8]}.json',mime='application/json',key='p2v8_transfer_evidence')


VIEWS={
    'Resumen ejecutivo':overview,
    'Panorama y madurez':maturity,
    'Plan de evaluación':plan,
    'Clientes y levantamiento':clients,
    'Expectativas de valor':expectations,
    'Necesidades y evidencias':needs,
    'Priorización':prioritization,
    'Motor Excel · Priorización':engine,
    'Matriz PMO Value Ring':matrix,
    'Matriz de correspondencia':matrix,  # alias de compatibilidad para navegación histórica
    'Validación y MVS':validation,
    'Autoevaluación PMI':assessment,
    'Evidencias e informes':evidence,
}
