"""Workspace transversal Alpha06; todos los cambios de negocio siguen en sus pasos."""
from math import cos,sin,pi
from html import escape
import json
from . import alpha06_transversal as data
from .alpha_navigation import STEPS, STEP_NAMES, STAGES, go_to
from .alpha02_sidebar import COLORS, ICONS
from .alpha_guidance import GUIDANCE

TOOLS=('Control Tower','Buscador global','Trazabilidad del valor','Calidad metodológica','Gobernanza','Academia PMO','Laboratorio V5','Administración y respaldo','Modo presentación')

def ring_svg():
    chunks=['<svg viewBox="0 0 320 320" width="100%" role="img" aria-label="Cinco etapas y diez pasos, cliente al centro" xmlns="http://www.w3.org/2000/svg">']
    for i,color in enumerate(COLORS):
        a=(-90+i*72+2)*pi/180; b=(-90+(i+1)*72-2)*pi/180
        chunks.append(f'<path d="M {160+117*cos(a):.2f} {160+117*sin(a):.2f} A 117 117 0 0 1 {160+117*cos(b):.2f} {160+117*sin(b):.2f}" fill="none" stroke="{color}" stroke-width="46"/>')
    for i in range(10):
        a=(-72+i*36)*pi/180
        chunks.append(f'<text x="{160+117*cos(a):.2f}" y="{165+117*sin(a):.2f}" text-anchor="middle" font-size="17" font-weight="700" fill="#15283c">{i+1:02}</text>')
    chunks.append('<circle cx="160" cy="160" r="76" fill="#123d4d"/><text x="160" y="154" text-anchor="middle" font-size="18" fill="white" font-weight="700">CLIENTE</text><text x="160" y="177" text-anchor="middle" font-size="13" fill="white">DE LA PMO</text></svg>')
    return ''.join(chunks)

def route_button(st,n,key):
    st.button(f'{n:02d} · {STEP_NAMES[n-1]}',icon=f':material/{ICONS[n-1]}:',key=key,on_click=go_to,args=(STEPS[n-1],),use_container_width=True)

def ring(st):
    st.subheader('Recorrido interactivo del Flywheel')
    st.caption('Selecciona un botón alrededor del diagrama. Las etapas no representan avance ni requisitos de bloqueo.')
    for col,n in zip(st.columns(4),(1,2,3,4)):
        with col:route_button(st,n,f'a06_ring_{n}')
    left,center,right=st.columns([1,2,1])
    with left:route_button(st,10,'a06_ring_10')
    with center:st.markdown(ring_svg(),unsafe_allow_html=True)
    with right:route_button(st,5,'a06_ring_5')
    for col,n in zip(st.columns(4),(9,8,7,6)):
        with col:route_button(st,n,f'a06_ring_{n}')
    for col,(stage,color) in zip(st.columns(5),zip(STAGES,COLORS)):
        col.markdown(f'<span style="color:{color};font-weight:700">{escape(stage)}</span>',unsafe_allow_html=True)

def table(st,rows):
    if rows is None:st.warning('Fuente no disponible en esta base o sin vínculo de origen comprobable.')
    elif not rows:st.info('Sin registros que cumplan la consulta.')
    else:st.dataframe(rows,hide_index=True,use_container_width=True)

def search_ui(st):
    st.subheader('Buscador global')
    st.caption('Busca por texto, ID o código en fuentes autorizadas del ciclo conectado. No busca correos ni contenido de archivos. Máximo 200 coincidencias visibles.')
    text=st.text_input('Texto, código o identificador',key='a06_query')
    categories=st.multiselect('Fuentes',list(data.SEARCH),default=list(data.SEARCH),key='a06_categories')
    if not text.strip():st.info('Escribe una palabra o un código para comenzar.');return
    rows,missing,total=data.search(text,categories)
    st.caption(f'{len(rows)} de {total} coincidencias; {len(missing)} fuentes no disponibles.')
    if missing:st.warning('No disponibles: '+', '.join(missing))
    table(st,rows)
    if rows:
        ix=st.selectbox('Selecciona un registro',[*range(len(rows))],format_func=lambda i:f"Paso {rows[i]['Paso']:02d} · {rows[i]['Título']} · {rows[i]['ID']}",key='a06_result')
        r=rows[ix];st.caption(f"Identificador para localizar en el formulario: {r['ID']}")
        from .beta02_search import exact,open_source
        selected=exact(r['Tipo'],r['ID'])
        if selected is None:st.warning('El registro ya no está disponible.')
        else:
            st.markdown('**Ficha de consulta del registro exacto**')
            st.write(selected)
            if r['Tipo']=='Clientes' and st.checkbox('Consultar ficha 360° aquí',key='b02_search_client_360'):
                from .clients import get_client
                from .alpha02_clients import render_client
                client=get_client(r['ID'])
                if client:render_client(client)
            st.button('Abrir componente de origen',key='a06_open_result',on_click=open_source,args=(r['Tipo'],r['ID']))
            st.caption('Selecciona cliente, diagnóstico o servicio cuando existe un selector compatible. Otras fuentes abren el componente y muestran el ID para localizar el registro.')
        if st.session_state.pop('b02_search_missing',False):st.warning('No se pudo abrir el registro; actualiza la búsqueda.')

def trace_ui(st):
    st.subheader('Trazabilidad del valor')
    st.caption('Recorrido desde una necesidad registrada. Solo IDs explícitos; no se vincula por nombres ni se certifica causalidad o aprobación.')
    text=st.text_input('Busca una necesidad por texto o ID',key='a06_trace_search')
    if not text.strip():return
    rows,missing,total=data.search(text,['Necesidades'])
    if not rows:table(st,None if missing else []);return
    n=st.selectbox('Necesidad',[r['ID'] for r in rows],format_func=lambda id:next(r['Título']+' · '+id for r in rows if r['ID']==id),key='a06_trace_need')
    r=data.trace(n)
    order=[('Cliente',1),('Necesidad',2),('Compromisos Paso 03',3),('Propuestas',3),('Servicios diseñados',4),('Incorporación',5),('Catálogo operativo',6),('Solicitudes',6),('Monitoreo',7),('Mejoras',8),('Beneficios',9),('Reconocimiento',10),('Percepción vinculada',10)]
    for label,num in order:
        with st.expander(f'Paso {num:02d} · {label} · '+('No evaluable' if r[label] is None else str(len(r[label]))),expanded=num==2):
            table(st,r[label]);route_button(st,num,'a06_trace_'+label)
    st.caption('Los beneficios se enlazan por importación local del Paso 03; el reconocimiento por importación local del Paso 09. Un vínculo no prueba vigencia ni materialización. Las mejoras se relacionan al servicio y ciclo, no necesariamente a una solicitud particular.')

def quality_ui(st):
    st.subheader('Centro de calidad metodológica')
    st.caption('Advertencias de revisión, no errores definitivos ni bloqueos. Algunos registros pueden estar en construcción. No se realizan correcciones automáticas.')
    r=data.quality()
    a,b,c=st.columns(3);a.metric('Reglas consultadas',sum(v is not None for v in r.values()));b.metric('Reglas con hallazgos',sum(bool(v) for v in r.values()));c.metric('Fuentes no evaluables',sum(v is None for v in r.values()))
    for label,rows in r.items():
        n=data.QUALITY[label][0]
        with st.expander(f'Paso {n:02d} · {label} · '+('No evaluable' if rows is None else str(len(rows)))):
            table(st,rows);route_button(st,n,'a06_quality_'+label)
    st.caption('Los conteos son coincidencias por regla y pueden superponerse; no constituyen una calificación de madurez.')

def governance_ui(st):
    st.subheader('Gobernanza y compromisos')
    from .beta02_governance import render as render_register
    from .rc2_mandate import render as render_mandate
    render_mandate(st)
    render_register(st)
    st.caption('Lectura de decisiones registradas y auditoría. No constituye un flujo de autorización nuevo. Últimos 100 registros por fuente, salvo retroalimentación (200).')
    r=data.governance()
    selected=st.selectbox('Fuente de decisión',list(r),key='a06_govern')
    table(st,r[selected])
    from .alpha04_operations import operation_data,commitments
    with st.expander('Compromisos ANS abiertos'):
        ops=operation_data();tickets=ops.get('tickets')
        if tickets is None:table(st,None)
        else:
            rows=commitments(tickets)
            table(st,[x for x in rows if x['Estado ANS'] in ('Vencido','En riesgo')]);st.caption('Solo hitos en riesgo o vencidos; consulta completa en Paso 06.')
            route_button(st,6,'a06_gov_ops')

def academy(st):
    st.subheader('Academia PMO')
    st.caption('Orientación original adaptada a CENS, no reproduce el texto de la guía ni constituye una certificación PMI.')
    n=st.selectbox('Ruta de aprendizaje',list(range(1,11)),format_func=lambda n:f'{n:02d} · {STEP_NAMES[n-1]}',key='a06_academy')
    g=GUIDANCE[n];st.write(g['purpose'])
    for k,v in g['sections']:
        with st.expander(k):st.write(v)
    st.caption(f"Referencia: PMI (2025), guía práctica, capítulo {g['chapter']}.")
    route_button(st,n,'a06_academy_step')
    with st.expander('Taller facilitado · caso ficticio'):
        st.info('Caso de práctica: un área tarda demasiado en consolidar reportes de proyectos. No es un diagnóstico real de CENS.')
        fields=['Problema verificable','Ganancia esperada','Servicio propuesto','Indicador y evidencia','Validación del cliente']
        notes={k:st.text_area(k,key='a06_workshop_'+str(i),height=80) for i,k in enumerate(fields)}
        st.download_button('Exportar notas de práctica',json.dumps({'modo':'FICTICIO · sin persistencia oficial','notas':notes},ensure_ascii=False,indent=2),file_name='taller_pmo_practica.json',mime='application/json',key='a06_workshop_export')
        st.caption('Notas de sesión; no se guardan en SQLite. Taller de facilitador único.')

def scenario(st):
    st.subheader('Laboratorio de escenarios V5')
    st.caption('Análisis hipotético sobre participantes y matriz congelados de una corrida V5 archivada. No guarda pesos, resultados, decisiones ni nuevas corridas.')
    runs=data.archived_runs()
    if not runs:table(st,runs);return
    selected=st.selectbox('Corrida archivada',[r['id'] for r in runs],format_func=lambda i:next(f"{r['fecha']} · {r['actor']} · {i}" for r in runs if r['id']==i),key='a06_run')
    try:
        run=data.snapshot(selected);weights=json.loads(run['pesos_json']); data.simulate(run,weights)
    except (ValueError,TypeError,KeyError,IndexError,OverflowError) as ex:st.warning(f'Snapshot no apto: {ex}');return
    new={k:st.number_input(f'Peso · {k}',min_value=0,max_value=100,value=int(v),step=1,key=f'a06_weight_{selected}_{i}') for i,(k,v) in enumerate(sorted(weights.items()))}
    st.caption(f'Total de ponderaciones: {sum(new.values())}% · Debe ser 100%.')
    justification=st.text_area('Justificación del escenario (solo sesión)',key='a06_reason_'+selected)
    if st.button('Simular sin guardar',key='a06_simulate'):
        if len(justification.strip())<12:st.warning('Documenta una justificación de al menos 12 caracteres.');return
        try:rows=data.simulate(run,new)
        except (ValueError,TypeError,KeyError) as ex:st.warning(str(ex));return
        from .step2_catalog import SERVICES
        rows=[{**r,'Servicio':SERVICES[r['Servicio ID']]} for r in rows]
        st.caption('Comparación con base recalculada desde el snapshot, no una modificación del ranking archivado.')
        table(st,rows)
        st.download_button('Exportar escenario hipotético',json.dumps({'tipo':'Simulación no aprobada','corrida_origen':selected,'pesos':new,'justificacion':justification,'resultados':rows},ensure_ascii=False,indent=2),file_name='escenario_V5_no_oficial.json',mime='application/json',key='a06_scenario_export',on_click='ignore')

def render(isolated=False):
    import streamlit as st
    from .alpha_control_tower import render as original
    from .design_system import alpha_heading
    alpha_heading('INICIO · INTELIGENCIA TRANSVERSAL','Espacio integral PMO','Diez pasos, una misma fuente de datos y herramientas complementarias.')
    tool=st.selectbox('Espacio de trabajo',TOOLS,key='a06_workspace')
    if tool=='Control Tower':
        original(isolated=isolated,show_steps=False);ring(st)
        from .beta01_workspace import render_shortcuts
        render_shortcuts(st)
        with st.expander('Alertas de calidad · consulta bajo demanda'):
            if st.checkbox('Consultar reglas',key='a06_home_quality'):
                r=data.quality();st.write([{'Regla':k,'Coincidencias':None if v is None else len(v)} for k,v in r.items()])
    elif tool=='Modo presentación':
        from .beta03_presentation import render as render_presentation
        render_presentation(st,isolated=isolated)
    elif tool=='Administración y respaldo':
        from .beta01_admin import render as render_admin
        render_admin(st)
    else:
        if isolated:st.info('Entorno aislado de vista previa. No constituye información oficial de CENS.')
        {'Buscador global':search_ui,'Trazabilidad del valor':trace_ui,'Calidad metodológica':quality_ui,'Gobernanza':governance_ui,'Academia PMO':academy,'Laboratorio V5':scenario}[tool](st)
