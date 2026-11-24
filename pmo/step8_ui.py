"""Paso 8, vistas Streamlit de madurez PMO-GA. Cinco componentes, sin alterar los demás pasos."""
from __future__ import annotations
import html,io,json,math
from datetime import date,timedelta
from pathlib import Path
import pandas as pd
import streamlit as st
from . import step8 as s
from .ui import kpi

NAV=list(s.MODULES) + ['Autoevaluación PMI']
THEME=Path(__file__).parent/'assets'/'step8_ux.css'
DOCS=Path(__file__).parent.parent/'referencias'

def apply_step8_theme():
    st.markdown('<style>'+THEME.read_text(encoding='utf-8')+'</style>',unsafe_allow_html=True)

def e(v):return html.escape(str(v if v is not None else ''))
def fmt(x):return '—' if x is None else f'{x:.1f}%'.replace('.',',')
def bjson(obj):return json.dumps(obj,ensure_ascii=False,indent=2,default=str).encode('utf8')

def head(part,title,desc):
    st.markdown(f'<div class="pmo-eyebrow">PASO 08 · {e(part)}</div><div class="pmo-title">{e(title)}</div><div class="pmo-subtitle">{e(desc)}</div>',unsafe_allow_html=True)

def safe_run(fun,label='Registro guardado'):
    try:
        result=fun();st.success(label);return result if result is not None else True
    except (s.ValidationError,ValueError,KeyError,TypeError,RuntimeError) as ex:
        st.error(str(ex));return None

def kpis(items):
    for col,(name,val,foot) in zip(st.columns(len(items)),items):
        with col:kpi(name,str(val),foot,'chart-no-axes-column')

def cycle_select():
    all_=s.cycles()
    if not all_:return None
    opts={a['id']:a for a in all_}
    desired=st.session_state.get('p8_active_cycle')
    if desired not in opts:desired=all_[0]['id'];st.session_state['p8_active_cycle']=desired
    chosen=st.selectbox('Ciclo de madurez',list(opts),format_func=lambda k:f"{opts[k]['nombre']} · {opts[k]['inicio']} — {opts[k]['fin']} {'[LABORATORIO]' if opts[k]['es_demo'] else ''}",key='p8_active_cycle')
    return s.report(chosen)

def demo_warn(r):
    if r and r['cycle']['es_demo']:st.warning('Este ciclo corresponde a datos de demostración. No representa la madurez real de CENS.')

def downloads(r):
    key=r['cycle']['id']
    with st.expander('Exportar evaluación y consultar fuentes',expanded=False):
        a,b,c,d=st.columns(4)
        with a:st.download_button('Excel de resultados',s.export_xlsx(key),file_name='CENS_Paso8_Madurez.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True)
        with b:st.download_button('Informe PDF',s.pdf_report(key),file_name='CENS_Paso8_Informe.pdf',mime='application/pdf',use_container_width=True)
        with c:st.download_button('JSON estructurado',bjson(__import__('pmo.step8_documented',fromlist=['export_documented_json']).export_documented_json(key)),file_name='CENS_Paso8_Madurez.json',mime='application/json',use_container_width=True)
        with d:st.download_button('Datos CSV',s.export_csv(key),file_name='CENS_Paso8_Datos.csv',mime='text/csv',use_container_width=True)
        st.caption('La cifra principal utiliza promedio simple de categorías estratégicas, tácticas y operativas. La ponderación por servicios es un indicador complementario.')

def sources():
    st.markdown('#### 0. Recopilar información y criterios')
    st.info('Evalúa exclusivamente los servicios efectivamente ofrecidos por la PMO. Cada servicio tiene cinco niveles descriptivos específicos en la guía recibida. Los no ofrecidos permanecen sin calificación.')
    a,b,c=st.columns(3)
    with a:
        p=DOCS/'Plantilla_para_CENS_y_PMOGA_ES.xlsx'
        if p.exists():st.download_button('Plantilla Excel en español · 26 servicios',p.read_bytes(),file_name=p.name,mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True)
    with b:
        p=DOCS/'PMO_Service_Maturity_Sample_Data.xlsx'
        if p.exists():st.download_button('Descargar ejemplo ilustrativo',p.read_bytes(),file_name=p.name,mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True)
    with c:
        p=DOCS/'PMO_Service_Maturity_Assessment.pdf'
        if p.exists():st.download_button('Consultar guía de madurez PDF',p.read_bytes(),file_name=p.name,mime='application/pdf',use_container_width=True)
    with st.expander('Orientaciones para el levantamiento'):
        st.markdown('Documenta el nivel **actual**, el nivel **deseado**, el **evaluador** y la **evidencia** por servicio. Entrevistas, documentos y métricas sirven de soporte; no generan calificación automáticamente. Un nivel 5 no es obligatorio para todos los servicios.')

def upload_and_validate():
    st.markdown('#### 1–2. Cargar y validar datos de madurez')
    excel=st.file_uploader('Plantilla Excel CENS / PMO-GA (.xlsx)',type=['xlsx'],key='p8_excel_file')
    results=st.file_uploader('O importar los resultados JSON de la aplicación de madurez',type=['json'],key='p8_json_result_file')
    if excel and results:
        st.warning('Selecciona solo un tipo de entrada por vez: Excel o JSON.');return None
    if not excel and not results:
        st.caption('Puedes cargar la plantilla o registrar un ciclo manualmente más abajo.');return None
    try:
        if excel:
            raw=excel.getvalue();scored=s.parse_xlsx(raw);src='excel'
        else:
            raw=results.getvalue();obj=json.loads(raw);scored=s.parse_results_json(obj);src='json'
        su=s.compute_summary(scored)
        kpis([('Servicios evaluados',su['assessed'],'Con niveles actual y deseado'),('No ofrecidos',su['not_offered'],'Sin puntuación'),('Madurez actual',fmt(su['current']),'Promedio categorías'),('Brecha',fmt(su['gap']),'Deseada menos actual')])
        st.dataframe(pd.DataFrame([{'ID':x['id'],'Servicio':s.CAT[x['id']]['name_es'],'Categoría':s.CATEGORIES_ES[s.CAT[x['id']]['category']],
                     'Estado':x['status'],'Actual':x['current'],'Deseado':x['desired']} for x in scored]),
                     hide_index=True,use_container_width=True,height=275)
        if su['assessed']==0:st.error('El archivo no tiene servicios evaluados.');return None
        if src=='json':
            source_period=obj.get('cycle') or {}
            st.caption('Periodo declarado en resultados: '+str(source_period.get('startDate',''))[:10]+' a '+str(source_period.get('endDate',''))[:10])
        return (src,raw,scored)
    except (s.ValidationError,ValueError,KeyError,json.JSONDecodeError) as ex:
        st.error(f'No se pudo validar la entrada: {ex}');return None

def cycle_create(imported):
    st.markdown('#### 3–4. Configurar ciclo y procesar la evaluación')
    today=date.today();default_end=today+timedelta(days=365)
    if imported and imported[0]=='json':
        obj=json.loads(imported[1]);t=obj.get('cycle') or {}
        try:today=date.fromisoformat(str(t.get('startDate'))[:10]);default_end=date.fromisoformat(str(t.get('endDate'))[:10])
        except (TypeError,ValueError):pass
    with st.form('p8_new_cycle_form'):
        name=st.text_input('Nombre del ciclo',value='Evaluación de madurez de la PMO')
        owner=st.text_input('Responsable de la evaluación',value='Equipo PMO')
        a,b=st.columns(2)
        with a:start=st.date_input('Inicio del ciclo',value=today, format='YYYY/MM/DD')
        with b:end=st.date_input('Fin del ciclo / objetivo',value=default_end, format='YYYY/MM/DD')
        demo=st.checkbox('Ciclo de ensayo / datos ficticios (no institucionales)',value=bool(imported))
        save=st.form_submit_button('Procesar y guardar evaluación' if imported else 'Crear ciclo para diligenciar manualmente',type='primary')
        if save:
            if imported:
                source,raw,_=imported
                if source=='json':
                    obj=json.loads(raw)
                    try:
                        ia,ib=s._valid_dates(str((obj.get('cycle') or {}).get('startDate') or '')[:10],str((obj.get('cycle') or {}).get('endDate') or '')[:10])
                        if (str(start),str(end))!=(ia,ib):
                            st.error('El JSON de resultados contiene un ciclo distinto. Para conservar trazabilidad, utiliza las fechas del archivo.');return
                    except s.ValidationError as ex:st.error(str(ex));return
                    key=safe_run(lambda:s.import_results_json(obj,owner,demo),'Evaluación PMO-GA importada en un nuevo ciclo')
                else:key=safe_run(lambda:s.import_excel(raw,name,str(start),str(end),owner,demo),'Plantilla Excel importada en nuevo ciclo')
            else:key=safe_run(lambda:s.create_cycle(name,str(start),str(end),owner,demo=demo),'Nuevo ciclo creado')
            if key:st.session_state['p8_active_cycle']=key;st.rerun()

def manual_ratings(r):
    """Acceso al catálogo documentado sin crear un módulo nuevo."""
    from .step8_review_ui import service_review_catalog
    service_review_catalog(r)


def capture_matrix(r):
    st.markdown('#### Matriz de captura rápida · 26 servicios')
    st.caption('Edición masiva opcional: permite valorar varios servicios y distinguir los pendientes de los que no se ofrecen. Todas las filas se validan juntas antes de guardarse.')
    current={x['servicio_ref']:x for x in r['ratings']}
    frame=pd.DataFrame([{'ID':x['id'],'Servicio':x['name_es'],'Categoría':s.CATEGORIES_ES[x['category']],
        'Estado':current[x['id']]['estado'],'Actual':current[x['id']]['actual'],
        'Deseado':current[x['id']]['deseado']} for x in s.CATALOG])
    if r['cycle']['estado']=='Cerrado':
        st.dataframe(frame,hide_index=True,use_container_width=True,height=430)
        st.caption('Ciclo cerrado: la matriz es de solo lectura.');return
    with st.form('p8_quick_matrix_'+r['cycle']['id']):
        updated=st.data_editor(frame,hide_index=True,use_container_width=True,num_rows='fixed',height=450,
            disabled=['ID','Servicio','Categoría'],
            column_config={'ID':st.column_config.NumberColumn('ID',disabled=True),
                'Estado':st.column_config.SelectboxColumn('Estado',options=list(s.STATUS),required=True),
                'Actual':st.column_config.NumberColumn('Actual (1–5)',min_value=1,max_value=5,step=1),
                'Deseado':st.column_config.NumberColumn('Deseado (1–5)',min_value=1,max_value=5,step=1)})
        actor=st.text_input('Evaluador responsable de la matriz',value=r['cycle']['responsable'])
        st.caption('Para «No ofrecido» o «Pendiente», deja Actual y Deseado vacíos. Para «Evaluado», completa ambos. Las observaciones y evidencias previas se conservan.')
        if st.form_submit_button('Validar y guardar los 26 registros',type='primary'):
            entries=[]
            for _,x in updated.iterrows():
                v=lambda z:None if pd.isna(z) else z
                entries.append({'id':int(x['ID']),'estado':x['Estado'],'actual':v(x['Actual']),'deseado':v(x['Deseado'])})
            if safe_run(lambda:s.save_ratings_batch(r['cycle']['id'],entries,actor),'Matriz completa registrada sin pérdida de evidencias'):st.rerun()

def assessment():
    head('MODELO PMO GA','Evaluación de madurez de los servicios','Recopila, valida y procesa la madurez actual y deseada de los 26 servicios. Conserva el ciclo y las evidencias.')
    st.markdown('<div class="p8-steps">① Recopilar datos　›　② Cargar archivo　›　③ Validar　›　④ Configurar ciclo　›　⑤ Procesar　›　⑥ Resultados</div>',unsafe_allow_html=True)
    sources()
    imported=upload_and_validate()
    cycle_create(imported)
    r=cycle_select()
    if r:
        demo_warn(r)
        z=r['summary'];kpis([('Servicios evaluados',z['assessed'],'De 26 servicios PMO'),('No ofrecidos',z['not_offered'],'No se califican'),('Pendientes',z['pending'],'Deben clasificarse'),('Brecha macro',fmt(z['gap']),'Puntos porcentuales')])
        capture_matrix(r)
        manual_ratings(r)
        col1,col2=st.columns([1,2])
        with col1:
            if r['cycle']['estado']=='Borrador' and st.button('Cerrar evaluación y conservar versión',key='p8_close'):
                if safe_run(lambda:s.close_cycle(r['cycle']['id']),'Ciclo archivado sin modificar los niveles'):st.rerun()
        with col2:st.caption('Cerrar el ciclo congela los 26 estados. Una nueva evaluación podrá utilizar este ciclo como referencia, sin sobrescribirlo.')
        downloads(r)
    with st.expander('Respaldo / restauración del Paso 8'):
        from . import step8_improvement as improvements
        st.download_button('Descargar respaldo integral Paso 08 · V0.39.25 (incluye iniciativas)',bjson(improvements.backup_v03925()),file_name='CENS_Paso08_Respaldo_Integral_V03925.json',mime='application/json')
        st.caption('Respalda además la base SQLite local: el JSON del Paso 08 no contiene los registros de los otros nueve pasos.')
        uploaded=st.file_uploader('Respaldo Paso 8',type=['json'],key='p8_restore_file')
        confirm=st.checkbox('Confirmo reemplazar únicamente los registros del Paso 8',key='p8_restore_confirm')
        if uploaded and st.button('Restaurar respaldo del Paso 8',disabled=not confirm):
            obj=json.loads(uploaded.getvalue())
            if obj.get('schema')=='PMO-FLYWHEEL-CENS-paso8-integral-v03925-v3':
                result=safe_run(lambda:improvements.restore_v03925(obj,confirmed=confirm),'Expediente integral restaurado')
            elif improvements.has_extended_records():
                st.error('Este respaldo anterior no incluye iniciativas ampliadas. No se restaurará sobre una base con datos V0.39.25. Conserva tu SQLite y utiliza un respaldo integral.')
                result=None
            else:
                result=safe_run(lambda:__import__('pmo.step8_documented',fromlist=['restore_full']).restore_full(obj,confirmed=confirm),'Respaldo documental histórico restaurado')
            if result:st.rerun()

def radar_svg(categories):
    cx,cy,r=200,140,90
    def polygon(values):
        pts=[]
        for i,v in enumerate(values):
            theta=math.radians(-90+120*i);rr=r*(float(v or 0)/100)
            pts.append(f'{cx+math.cos(theta)*rr:.1f},{cy+math.sin(theta)*rr:.1f}')
        return ' '.join(pts)
    grid=''.join(f'<polygon points="{polygon([level]*3)}" fill="none" stroke="#DDE7ED" stroke-width="1"/>' for level in (25,50,75,100))
    arms=''.join(f'<line x1="{cx}" y1="{cy}" x2="{cx+math.cos(math.radians(-90+120*i))*r:.1f}" y2="{cy+math.sin(math.radians(-90+120*i))*r:.1f}" stroke="#C9D9E2"/>' for i in range(3))
    nowpts=polygon([x['current'] for x in categories]);target=polygon([x['desired'] for x in categories])
    labels=''.join(f'<text x="{cx+math.cos(math.radians(-90+120*i))*127:.1f}" y="{cy+math.sin(math.radians(-90+120*i))*122:.1f}" text-anchor="middle" font-size="12" fill="#19394B">{x["name"]}</text>' for i,x in enumerate(categories))
    return f'<svg viewBox="0 0 400 305" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Radar madurez actual azul y deseada naranja"><rect width="400" height="305" fill="white"/>{grid}{arms}<polygon points="{target}" fill="#CE7C4240" stroke="#CE7C42" stroke-width="2.5"/><polygon points="{nowpts}" fill="#0C989B44" stroke="#0C989B" stroke-width="2.5"/>{labels}<text x="120" y="287" fill="#0C989B" font-size="12">● Actual</text><text x="225" y="287" fill="#CE7C42" font-size="12">● Deseada</text></svg>'

def results():
    head('ANÁLISIS','Resultados y brechas de madurez','Compara los niveles actuales con los deseados, por servicio y categoría, utilizando los datos registrados.')
    r=cycle_select()
    if not r:return st.info('Primero importa o registra una evaluación en la primera sección.')
    demo_warn(r)
    from .alpha05_value_ui import render_maturity
    render_maturity(r)
    z=r['summary']
    if z['assessed']==0:return st.info('El ciclo no tiene calificaciones; evita interpretar un 0% como madurez real.')
    kpis([('Madurez actual',fmt(z['current']),'Media igual de categorías'),('Madurez deseada',fmt(z['desired']),'Media igual de categorías'),('Brecha general',fmt(z['gap']),'Puntos porcentuales'),('Servicios en portafolio',z['assessed'],f"{z['not_offered']} no ofrecidos")])
    st.markdown(f'<div class="p8-overview"><b>Índice de madurez de servicios</b><div class="p8-numbers">{fmt(z["current"])}　→　{fmt(z["desired"])}　<span>Brecha {fmt(z["gap"])}</span></div><small>Periodo: {e(r["cycle"]["inicio"])} a {e(r["cycle"]["fin"])} · {z["assessed"]} servicios calificados</small></div>',unsafe_allow_html=True)
    st.caption(f"Cálculo alternativo ponderado por servicios: actual {fmt(z['weighted_current'])} · deseada {fmt(z['weighted_desired'])} · brecha {fmt(z['weighted_gap'])}. No confundir con el promedio por categorías del reporte PMO-GA.")
    left,right=st.columns([1.1,1])
    with left:
        with st.container(border=True):
            st.subheader('Madurez por categoría')
            st.dataframe(pd.DataFrame([{'Categoría':a['name'],'Evaluados':a['count'],'Disponibles':a['total'],'Actual %':round(a['current'] or 0,2) if a['count'] else None,
               'Meta %':round(a['desired'] or 0,2) if a['count'] else None,'Brecha pp':round(a['gap'] or 0,2) if a['count'] else None} for a in z['categories']]),hide_index=True,use_container_width=True)
            frame=pd.DataFrame([{'Categoría':a['name'],'Actual':a['current'],'Deseada':a['desired']} for a in z['categories']]).set_index('Categoría')
            st.bar_chart(frame,y=['Actual','Deseada'],height=210)
    with right:
        with st.container(border=True):
            st.subheader('Radar actual frente a meta')
            st.components.v1.html(radar_svg(z['categories']),height=300)
            st.caption('Las categorías sin servicios evaluados se mantienen sin madurez calculada y no se incluyen en la media.')
    st.subheader('Ranking de brechas de mejora')
    sorted_=s.ranked(r['cycle']['id'])
    st.dataframe(pd.DataFrame([{'ID':x['id'],'Servicio':x['name_es'],'Categoría':s.CATEGORIES_ES[x['category']],
             'Actual':x['actual'],'Deseado':x['deseado'],'Brecha pp':x['gap'],'Semáforo':s.gap_band(x['gap'])} for x in sorted_]),hide_index=True,use_container_width=True)
    if r['summary']['pending']:st.warning(f'{r["summary"]["pending"]} servicios aún sin evaluar. El índice es provisional y solo contempla los evaluados.')
    st.caption('Semáforo orientativo del archivo de muestra: crítico desde 30 pp; alerta desde 15 pp; moderado en brechas inferiores. No es un umbral oficial de certificación PMI.')
    from .step8_improvement_ui import render_quality
    render_quality(r)
    downloads(r)

def plan():
    head('MEJORA CONTINUA','Gestión de iniciativas de mejora','Vincula brechas de madurez, hallazgos del Paso 07, decisiones, hitos y evidencias de resultados.')
    r=cycle_select()
    if not r:return st.info('Crea primero un ciclo de madurez.')
    demo_warn(r)
    from .alpha05_value_ui import render_backlog
    render_backlog(r)
    from .step8_improvement_ui import render_plan
    render_plan(r)

def history():
    head('EVOLUCIÓN','Evolución e historial de madurez','Compara ciclos históricos sin sobrescribir calificaciones; define metas realistas y reevalúa las acciones implementadas.')
    archive=s.cycles()
    if not archive:return st.info('No existen ciclos todavía. El historial se construirá al registrar evaluaciones.')
    evaluated=[]
    for c in archive:
        r=s.report(c['id']);z=r['summary']
        evaluated.append({'Ciclo':c['nombre'],'Fecha':c['inicio'],'Estado':c['estado'],'Evaluados':z['assessed'],
            'Madurez actual %':z['current'],'Meta %':z['desired'],'Brecha pp':z['gap'],'Ejemplo':bool(c['es_demo'])})
    st.dataframe(pd.DataFrame(evaluated),hide_index=True,use_container_width=True)
    series=pd.DataFrame([x for x in reversed(evaluated) if x['Madurez actual %'] is not None])
    if len(series)>1:
        st.subheader('Evolución del índice entre ciclos')
        chart=series[['Fecha','Madurez actual %','Meta %']].set_index('Fecha')
        st.line_chart(chart,height=260)
        st.caption('Este gráfico compara evaluaciones registradas; no infiere mejoras hasta que existan nuevos datos.')
    elif len(series)==1:st.info('Una evaluación disponible. Registra un segundo ciclo para ver evolución real.')
    r=cycle_select()
    if not r:return
    demo_warn(r)
    st.subheader('Iniciar una nueva reevaluación sin sobrescribir el historial')
    with st.form('p8_reassess_form'):
        name=st.text_input('Nombre del siguiente ciclo',value='Reevaluación de madurez PMO')
        a,b=st.columns(2)
        with a:start=st.date_input('Inicio',value=date.today(), format='YYYY/MM/DD')
        with b:end=st.date_input('Fin',value=date.today()+timedelta(days=365), format='YYYY/MM/DD')
        owner=st.text_input('Responsable',value=r['cycle']['responsable'])
        copy=st.checkbox('Usar los niveles anteriores como borrador (deberán verificarse con nuevas evidencias)',value=False)
        if st.form_submit_button('Crear nuevo ciclo',type='primary'):
            key=safe_run(lambda:s.create_cycle(name,str(start),str(end),owner,source='Reevaluación',demo=bool(r['cycle']['es_demo']),copy_from=r['cycle']['id'] if copy else None),'Reevaluación creada')
            if key:st.session_state['p8_active_cycle']=key;st.rerun()
    st.caption('La madurez de los servicios es un instrumento distinto de las autoevaluaciones metodológicas PMI de los demás pasos. No constituye por sí sola una certificación.')
    from .step8_improvement_ui import render_evolution
    render_evolution()

from .step8_profile_ui import page as pmo_profile_page
PAGES={
    "Evaluación de madurez":assessment,
    "Perfil de madurez PMO":pmo_profile_page,
    "Resultados y brechas":results,
    "Plan de mejora":plan,
    "Evolución e historial":history,
}
def page(section):
    from . import step8_improvement
    step8_improvement.initialize()
    if section=="Perfil de madurez PMO":
        from .alpha05_value_ui import render_integral
        render_integral()
    PAGES.get(section,assessment)()
