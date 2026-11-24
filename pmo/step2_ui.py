"""Interfaz ligera del Paso 2, alineada con el prototipo HTML del usuario.
Siete módulos de diagnóstico más autoevaluación PMI; conserva las vistas históricas y la misma SQLite.
"""
from __future__ import annotations
import io
import json
from collections import Counter
from datetime import date
import streamlit as st
from . import step2 as p2
from . import step2_excel as excel
from . import step2_diagnostic_excel as initial_excel
from .step2_reports import results_xlsx
from .clients import list_clients,ValidationError
from .catalog_manager import smart_choice
from .v0391_diagnostics import next_diagnostic_name
from .v0391_clients import role_catalog
from .step2_catalog import OUTCOMES,SERVICES
from . import matrix as canonical

NAV=[
 ('Resumen ejecutivo','▦'),
 ('Plan y contexto','☷'),
 ('Clientes y expectativas','♧'),
 ('Necesidades y evidencias','◈'),
 ('Priorización y matriz','▥'),
 ('Validación y MVS','☑'),
 ('Informes y transferencia','▱'),
 ('Autoevaluación PMI','▧'),
]


def head(section,title,subtitle):
    # El encabezado del Paso 2 comparte tipografía y tarjetas, cambia solo el número.
    from .ui import e
    st.markdown(f'<div class="pmo-eyebrow">PASO 02 · {e(section.upper())}</div><div class="pmo-title">{e(title)}</div><div class="pmo-subtitle">{e(subtitle)}</div>',unsafe_allow_html=True)


def kpis(items):
    from .ui import kpi
    for index,(col,(label,value,foot,icon,accent)) in enumerate(zip(st.columns(4),items)):
        with col:kpi(label,value,foot,icon,accent or ('orange','blue','purple','teal')[index])


def err(ex):st.error(str(ex))


def person_option(clients):
    return {r['id']:f"{r['codigo']} · {r['nombre']} ({r['segmento'] or 'Sin rol'})" for r in clients}


SECTION_META = {
 'Resumen ejecutivo': ('DIAGNÓSTICO Y VALOR','Evaluación de necesidades','Panorama integrado del diagnóstico, expectativas de valor y evidencia para las decisiones de la PMO.'),
 'Panorama y madurez': ('CONTEXTO ORGANIZACIONAL','Panorama y madurez percibida','Tablero ejecutivo de percepción registrada y consulta separada del histórico anual; sin conexión con PMOGA.'),
 'Plan de evaluación': ('DIAGNÓSTICO Y VALOR','Plan de evaluación','Definición del alcance, población objetivo, métodos de levantamiento y ciclo del diagnóstico.'),
 'Clientes y levantamiento': ('DIAGNÓSTICO Y VALOR','Clientes y levantamiento','Directorio compartido con el Paso 1, historial de participación y actividades de diagnóstico.'),
 'Expectativas de valor': ('DIAGNÓSTICO Y VALOR','Expectativas de valor','Selección de cinco resultados potenciales de la PMO, ordenados según la voz del cliente.'),
 'Necesidades y evidencias': ('DIAGNÓSTICO Y VALOR','Necesidades y evidencias','Consola Pain–Gain para registrar dificultades, beneficios deseados y sus evidencias.'),
 'Priorización': ('DIAGNÓSTICO Y VALOR','Priorización multicriterio','Ponderación por roles, resultados esperados y selección analítica de servicios.'),
 'Motor Excel · Priorización': ('DIAGNÓSTICO Y VALOR','Motor de análisis y priorización','Importación de expectativas, cálculo reproducible y consulta de rankings y contribuciones.'),
 'Matriz PMO Value Ring': ('DIAGNÓSTICO Y VALOR','Matriz PMO Value Ring 30 × 26','Inspección y control de 780 relaciones entre resultados esperados y servicios de la PMO.'),
 'Validación y MVS': ('DIAGNÓSTICO Y VALOR','Validación y servicios MVS','Análisis por roles, preselección de servicios y registro de decisiones.'),
 'Autoevaluación PMI': ('DIAGNÓSTICO Y VALOR','Autoevaluación del Paso 2','Instrumento adaptado de 25 criterios, resultados por dimensión y trazabilidad.'),
 'Evidencias e informes': ('DIAGNÓSTICO Y VALOR','Evidencias e informes','Referencias documentales, trazabilidad y paquete de información para el Paso 3.'),
}

def _onboarding_guide():
    st.markdown('<div class="p2-welcome"><div class="p2-welcome-kicker">ETAPA DE EXPLORACIÓN · PASO 02</div><div class="p2-welcome-title">Escuchar primero. Priorizar con evidencia.</div><div class="p2-welcome-desc">Inicia un diagnóstico para recoger expectativas y necesidades reales de los clientes internos. Puedes registrarlo manualmente o importar un Excel completo.</div><div class="p2-welcome-tags"><span>01 · Planear</span><span>02 · Escuchar</span><span>03 · Analizar</span><span>04 · Priorizar</span><span>05 · Validar</span></div></div>', unsafe_allow_html=True)
    col1,col2,col3=st.columns(3,gap="medium")
    with col1:
        with st.container(border=True):
            st.markdown('**01 · Diagnóstico inicial**')
            st.caption('Define responsable, ciclo y alcance. No se requieren cifras para comenzar.')
    with col2:
        with st.container(border=True):
            st.markdown('**02 · Participación y expectativas**')
            st.caption('Reutiliza clientes del Paso 1 y registra sus prioridades de valor.')
    with col3:
        with st.container(border=True):
            st.markdown('**03 · Decisiones con respaldo**')
            st.caption('Relaciona necesidades con servicios y conserva la fuente de cada cálculo.')


def _creation_panel(available):
    # V0.35.1: el instalador preserva una SQLite local anterior. Si aún no
    # contiene el diagnóstico, ofrecer su carga segura sin reiniciar el ciclo.
    if not available:
        st.info("Cloud: crea un diagnóstico ficticio; la recuperación de datos institucionales no está habilitada.")
    st.markdown('<div class="p2-panel-label">CONFIGURACIÓN DEL DIAGNÓSTICO</div>',unsafe_allow_html=True)
    choice=st.radio('¿Cómo quieres crear o alimentar el diagnóstico?',
                    ['Manual','Importar Excel'],horizontal=True,key='p2_create_method')
    if choice=='Manual':
        with st.form('p2_diagnostic_form',clear_on_submit=True):
            a,b=st.columns(2)
            name=a.text_input('Nombre del diagnóstico (automático)',value=next_diagnostic_name(str(date.today().year)),disabled=True,help='La numeración se reinicia cada año y conserva el ID permanente.')
            cycle=b.text_input('Ciclo anual *',value=str(date.today().year))
            owner=a.text_input('Responsable *')
            population=b.number_input('Población objetivo (opcional)',min_value=0,value=0)
            scope=st.text_input('Alcance')
            submitted=st.form_submit_button('Crear diagnóstico',type='primary')
        if submitted:
            try:
                new=p2.create_diagnostic(next_diagnostic_name(cycle),cycle,owner,scope=scope,population=int(population) if population else None)
                st.session_state['p2_pending_diagnostic']=new
                st.success('Se creó el expediente del diagnóstico.');st.rerun()
            except ValidationError as ex:err(ex)
    else:
        st.markdown('**Carga opcional:** crea el diagnóstico inicial desde el Excel o complementa uno que ya existe. No crea personas en el Paso 1.')
        st.download_button('↓ Plantilla vacía del diagnóstico',data=initial_excel.template_bytes(),
            file_name='PLANTILLA_PASO2_DIAGNOSTICO_V0.6.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',key='p2_blank_diag_excel')
        demo_path=__import__('pathlib').Path(__file__).resolve().parents[1]/'plantillas'/'EJEMPLO_PASO2_DIAGNOSTICO_FICTICIO_V0.6.xlsx'
        if demo_path.is_file():
            st.download_button('↓ Excel ficticio completo de ejemplo',data=demo_path.read_bytes(),
                file_name=demo_path.name,mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',key='p2_fake_diag_excel')
        modes=['Crear un nuevo diagnóstico']+(['Completar un diagnóstico existente'] if available else [])
        mode=st.radio('Modo de importación',modes,horizontal=True,key='p2_import_mode')
        existing_id=None
        if mode=='Completar un diagnóstico existente':
            known={r['id']:f"{r['ciclo']} · {r['nombre']}" for r in available}
            existing_id=st.selectbox('Diagnóstico que recibirá los registros',list(known),format_func=lambda k:known[k],key='p2_import_target')
            st.caption('El Excel no cambia el nombre ni el ciclo del diagnóstico existente. Los registros se incorporarán al expediente seleccionado.')
        st.caption('Hojas admitidas: Diagnostico, Madurez, Levantamientos, Expectativas, Necesidades, Evidencias y Pesos. Solo la primera es obligatoria para crear un diagnóstico nuevo.')
        file=st.file_uploader('Selecciona el Excel del Paso 2',type=['xlsx'],key=f"p2_full_xlsx_{st.session_state.get('p2_import_upload_serial',0)}")
        if file is not None:
            try:
                check=initial_excel.preview(file.getvalue(),file.name,existing_id)
                vals=[{'Sección':k,'Filas válidas':v} for k,v in check['counts'].items()]
                st.dataframe(vals,hide_index=True,use_container_width=True)
                st.caption(f"Total: {check['total']} filas · Acciones: {check['actions']}")
                if check['errors']:
                    st.error(f"Se encontraron {len(check['errors'])} errores. No se guardará ninguna fila hasta corregirlos.")
                    for message in check['errors'][:35]:st.write('• '+message)
                    if len(check['errors'])>35:st.caption('Se muestran los primeros 35 errores.')
                else:
                    st.success('Validación satisfactoria. El Excel puede cargarse de manera integral.')
                    with st.form('p2_confirm_bulk'):
                        actor=st.text_input('Responsable de la carga *',key='p2_excel_actor')
                        confirmed=st.checkbox('Revisé la vista previa y confirmo la carga en este diagnóstico.',key='p2_excel_authorized')
                        sent=st.form_submit_button('Confirmar e importar Excel',type='primary')
                    if sent and not confirmed:
                        st.warning('Marque la confirmación para importar.')
                    if sent and confirmed:
                        result=initial_excel.import_workbook(file.getvalue(),file.name,actor,existing_id)
                        st.session_state['p2_pending_diagnostic']=result['diagnostic_id']
                        st.session_state['p2_import_upload_serial']=st.session_state.get('p2_import_upload_serial',0)+1
                        st.success('Importación completada; registros vinculados al diagnóstico.')
                        st.rerun()
            except (ValidationError,ValueError) as ex:err(ex)
            except Exception as ex:
                st.error(f'La importación no pudo completarse: {ex}')


def _context_strip(item,summary):
    from .ui import e
    population = item.get('poblacion_objetivo')
    values = [('Ciclo',item['ciclo']),('Responsable',item['responsable']),
              ('Estado',item['estado']),('Población objetivo',str(population) if population else 'Sin definir')]
    cells=''.join(f'<div class="p2-context-item"><span>{e(k)}</span><strong>{e(v)}</strong></div>' for k,v in values)
    st.markdown(f'<div class="p2-context">{cells}</div>',unsafe_allow_html=True)
    st.markdown('<div class="p2-flow"><span>PLANIFICAR</span><b>→</b><span>ESCUCHAR</span><b>→</b><span>ANALIZAR</span><b>→</b><span>PRIORIZAR</span><b>→</b><span>VALIDAR</span></div>',unsafe_allow_html=True)


# Cada módulo tiene su propia orientación cuando aún no existe un diagnóstico.
# La ausencia de datos no debe redirigir silenciosamente las doce vistas al Resumen.
EMPTY_SECTION_GUIDANCE = {
    'Panorama y madurez': ('Línea base pendiente', 'Crea el diagnóstico para registrar prácticas, herramientas y la percepción de madurez de los clientes.'),
    'Plan de evaluación': ('Planificación pendiente', 'Crea el expediente para definir alcance, responsables, población objetivo y métodos de levantamiento.'),
    'Clientes y levantamiento': ('Levantamiento pendiente', 'Una vez creado el diagnóstico podrás vincular clientes existentes y registrar entrevistas y reuniones, sin duplicarlos.'),
    'Expectativas de valor': ('Expectativas pendientes', 'Crea el diagnóstico para registrar los cinco beneficios distintos y ordenados por cada cliente.'),
    'Necesidades y evidencias': ('Necesidades pendientes', 'Con un diagnóstico activo podrás documentar dificultades, resultados deseados y fuentes de evidencia.'),
    'Priorización': ('Priorización pendiente', 'Primero vincula respuestas válidas a un diagnóstico; los pesos de roles se definirán para cada escenario por criterio experto.'),
    'Motor Excel · Priorización': ('Motor preparado', 'Crea el diagnóstico para acceder al control de muestra, captura, verificación, ponderación experta y ranking V5.'),
    'Matriz PMO Value Ring': ('Matriz pendiente de contexto', 'La matriz de 30 beneficios por 26 servicios se consulta dentro de un diagnóstico activo. No se modifican sus coeficientes.'),
    'Validación y MVS': ('Validación pendiente', 'Con el diagnóstico creado podrás contrastar resultados y documentar servicios candidatos sin aprobarlos automáticamente.'),
    'Autoevaluación PMI': ('Autoevaluación pendiente', 'Crea un diagnóstico para registrar los 25 criterios de evaluación, sus calificaciones y evidencias.'),
    'Evidencias e informes': ('Expediente pendiente', 'Crea el diagnóstico para adjuntar referencias, revisar el historial y generar informes de transferencia.'),
}


SECTION_META['Matriz de correspondencia'] = SECTION_META['Matriz PMO Value Ring']
EMPTY_SECTION_GUIDANCE['Matriz de correspondencia'] = EMPTY_SECTION_GUIDANCE['Matriz PMO Value Ring']
EMPTY_SECTION_GUIDANCE.update({
    'Plan y contexto': EMPTY_SECTION_GUIDANCE['Plan de evaluación'],
    'Clientes y expectativas': EMPTY_SECTION_GUIDANCE['Clientes y levantamiento'],
    'Priorización y matriz': EMPTY_SECTION_GUIDANCE['Motor Excel · Priorización'],
    'Informes y transferencia': EMPTY_SECTION_GUIDANCE['Evidencias e informes'],
})


def _empty_diagnostic_section(section: str) -> None:
    """Presenta el módulo seleccionado, no un falso resumen ejecutivo."""
    if section == 'Resumen ejecutivo':
        _onboarding_guide()
        return
    title, description = EMPTY_SECTION_GUIDANCE[section]
    with st.container(border=True):
        st.markdown(f'### {title}')
        st.write(description)
        st.caption('Este componente quedará disponible al crear o importar el diagnóstico. No se generan datos simulados.')


def page(section:str):
    from .step2_design import apply_step2_theme
    from .step2_reference_ui import VIEWS as LEGACY_VIEWS
    from .step2_consolidated_ui import VIEWS as NEW_VIEWS, META as NEW_META, ALIASES
    VIEWS = {**LEGACY_VIEWS, **NEW_VIEWS}
    SECTION_META.update(NEW_META)
    apply_step2_theme()
    # La navegación depende de la sección elegida, incluso si todavía no hay diagnósticos.
    if section not in SECTION_META or section not in VIEWS:
        st.error('La sección seleccionada no está disponible en el Paso 02.')
        return
    # Vista anual autónoma: no requiere diagnóstico PMOGA ni modifica sus tablas.
    if section == 'Panorama y madurez':
        head(*SECTION_META[section])
        from .step2_maturity_dashboard import render
        render()
        return
    available=p2.list_diagnostics()
    head(*SECTION_META[section])
    if st.session_state.get('p2_restore_v035_flash'):
        st.success(st.session_state.pop('p2_restore_v035_flash'))
    if not available:
        st.info('No hay un diagnóstico activo en esta base. El expediente se configura una sola vez en «Plan de evaluación».')
        if section in ('Plan de evaluación', 'Plan y contexto'):
            with st.container(border=True):
                _creation_panel(available)
            if section == 'Plan y contexto':
                with st.expander('Madurez institucional anual · consulta independiente', expanded=False):
                    from .step2_maturity_dashboard import render
                    render()
        else:
            if st.button('Abrir Plan de evaluación para crear o recuperar diagnóstico', key='p2_open_plan_no_diag'):
                st.session_state['pmo_active_p2_page']='Plan y contexto'
                st.rerun()
            _empty_diagnostic_section(section)
        return
    names={r['id']:f"{r['ciclo']} · {r['nombre']}" for r in available}
    prior=st.session_state.pop('p2_pending_diagnostic',None) or st.session_state.get('p2_selected_diagnostic')
    if prior in names and prior!=st.session_state.get('p2_selected_diagnostic'):
        st.session_state['p2_selected_diagnostic']=prior
    if prior not in names:st.session_state['p2_selected_diagnostic']=available[0]['id']
    if section in ('Plan de evaluación', 'Plan y contexto'):
        left,add,upload=st.columns([5,1.1,1.45],vertical_alignment='bottom',gap='small')
    else:
        left=st.container()
    with left:
        selected=st.selectbox('Diagnóstico activo',list(names),format_func=lambda k:names[k],key='p2_selected_diagnostic')
    if section in ('Plan de evaluación', 'Plan y contexto'):
        with add:
            if st.button('＋ Nuevo diagnóstico',use_container_width=True,key='p2_show_new'):
                st.session_state['p2_show_form']=True
                st.session_state['p2_create_method']='Manual'
                st.rerun()
        with upload:
            if st.button('⇧ Importar diagnóstico',use_container_width=True,key='p2_show_upload'):
                st.session_state['p2_show_form']=True
                st.session_state['p2_create_method']='Importar Excel'
                st.rerun()
        if st.session_state.get('p2_show_form'):
            with st.container(border=True):
                c1,c2=st.columns([5,1],vertical_alignment='center')
                with c1:st.markdown('**Crear o completar diagnóstico**')
                with c2:
                    if st.button('Cerrar ✕',key='p2_hide_form',use_container_width=True):
                        st.session_state['p2_show_form']=False
                        st.rerun()
                _creation_panel(available)
    item=next(r for r in available if r['id']==selected)
    VIEWS[section](selected,item)


def _maturity_cycle_summary(item):
    """Madurez institucional del mismo año del ciclo seleccionado.

    Es solo una consulta read-only por año: nunca alimenta el PMOGA ni V5.
    """
    import re
    from html import escape as esc
    from . import step2_maturity_annual as annual
    cycle = str(item.get('ciclo') or '').strip()
    years = re.findall(r'(?<!\d)(?:19|20)\d{2}(?!\d)', cycle)
    defined_year = int(years[0]) if len(set(years)) == 1 else None
    recorded = annual.history()
    assigned = annual.associated_year(item['id']) if defined_year is None else None
    year = defined_year or assigned
    if year is None:
        choices=sorted({int(x['ano']) for x in recorded['periodos']})
        if not choices:
            st.info('El ciclo no especifica un año y todavía no hay mediciones anuales. '
                    'Carga primero los resultados en «Panorama y madurez».')
            return
        with st.container(border=True):
            st.markdown('**Asociar el expediente con un año de medición**')
            st.caption(f'El campo de ciclo es «{cycle}» y no identifica un año. '
                       'Selecciona el periodo institucional correcto; la asociación se guarda una sola vez.')
            sel=st.selectbox('Año de madurez correspondiente a este expediente',choices,
                             index=len(choices)-1,key=f'p2_annual_association_{item["id"]}')
            actor=st.text_input('Responsable de la asociación *',key=f'p2_annual_association_actor_{item["id"]}')
            if st.button('Guardar asociación del año',key=f'p2_annual_association_save_{item["id"]}'):
                try:
                    annual.associate_year(item['id'],int(sel),actor)
                    st.success(f'Año {sel} asociado a este expediente con respaldo y auditoría.')
                    st.rerun()
                except (ValidationError,ValueError,OSError) as ex:
                    st.error(str(ex))
        return
    data = annual.snapshot_for_year(recorded, year)
    if data is None or (data['con'] is None and data['sin'] is None):
        st.info(f'No existe una medición institucional de madurez registrada para {year}. '
                'Puedes incorporarla en «Panorama y madurez». No se utiliza la medición de otro año.')
        return
    from .step2_maturity_dashboard import STYLES
    st.markdown(STYLES,unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown(f'**Medición de madurez percibida · {year}**')
        st.caption('Escala 0–5 · Registro institucional consolidado. Consulta contextual por año, '
                   'sin conexión de cálculo con las preferencias, necesidades o motor V5.')
        a,b=st.columns(2, gap='medium')
        with a:
            con=data['con']
            st.metric('Índice con enfoques y metodologías',f"{con['indice']:.2f} / 5" if con and con.get('indice') is not None else 'Sin dato')
        with b:
            sin=data['sin']
            st.metric('Índice sin enfoques y metodologías',f"{sin['indice']:.2f} / 5" if sin and sin.get('indice') is not None else 'Sin dato')
        st.markdown('**Cinco dimensiones del modelo institucional**')
        dims=data['dimensiones']
        for dim in annual.DIMENSIONS[annual.CON]:
            value=dims.get(dim)
            label=esc(dim)
            if value is None:
                st.markdown(f'<div class="p2m-annual-row"><span>{label}</span><span>Sin dato</span></div>', unsafe_allow_html=True)
            else:
                width=max(0,min(100,float(value)/5*100))
                st.markdown(f'<div class="p2m-annual-row"><span>{label}</span><b>{float(value):.2f} / 5</b></div>'
                            f'<div class="p2m-annual-track"><span style="width:{width:.2f}%"></span></div>', unsafe_allow_html=True)
        st.caption('Los valores se presentan tal como están registrados. '
                   'El resumen no recalcula índices ni crea datos faltantes.')


def overview(diag,item):
    st.markdown('<div class="p2-section-label">PANORAMA DE LA EVALUACIÓN</div>',unsafe_allow_html=True)
    data=p2.summary(diag)
    kpis([('Clientes levantados',str(data['clientes_levantados']),'Clientes únicos con actividad','♙',''),
          ('Dependencias representadas',str(data['areas']),'Dependencias con levantamientos','◎','blue'),
          ('Necesidades validadas',str(data['necesidades_validadas']),'Decisiones registradas','✓','orange'),
          ('Expectativas registradas',str(data['clientes_expectativas']),'Clientes con al menos una prioridad','▦','purple')])
    _maturity_cycle_summary(item)
    st.markdown('<div class="p2-section-label">RESULTADOS Y ESTADO DEL DIAGNÓSTICO</div>',unsafe_allow_html=True)
    left,right=st.columns([1.6,1])
    with left:
        with st.container(border=True):
            st.subheader('Resultados prioritarios')
            runs=p2.runs(diag)
            if not runs:
                st.info('No hay una corrida de priorización. Registra expectativas y ejecuta el motor Excel.')
            else:
                run=p2.get_run(runs[0]['id']);r=run['resultados']
                st.caption(f"Último análisis: {run['fecha']} · {r['participants']} participantes · {run['modelo']}")
                import pandas as pd
                st.bar_chart(pd.DataFrame([{'Resultado':x['name'],'Relevancia %':x['score']} for x in r['outcomes'][:8]]).set_index('Resultado'),horizontal=True)
                st.dataframe([{'#':i+1,'Servicio':x['name'],'Relevancia (%)':round(x['score'],2)} for i,x in enumerate(r['services'][:5])],hide_index=True,use_container_width=True)
    with right:
        with st.container(border=True):
            st.subheader('Estado del diagnóstico')
            st.metric('Necesidades pendientes',data['necesidades_pendientes'])
            st.metric('Evidencias documentales',data['evidencias'])
            st.metric('Corridas del motor',len(p2.runs(diag)))
            valid=p2.candidates(diag)
            st.metric('Servicios candidatos en validación o validados',sum(x['estado'] in ('En validación','Validado') for x in valid))
    st.markdown('**Trazabilidad propuesta** 　Cliente → Expectativa → Necesidad validada → Priorización → Insumo del Paso 3')
    st.caption('Los servicios de mayor relevancia no se aprueban automáticamente. La decisión corresponde a la validación con clientes.')


def planning(diag,item):
    rows=p2.maturity(diag)
    if rows:
        current=sum(int(x['actual']) for x in rows)/len(rows)
        desired=sum(int(x['deseado']) for x in rows)/len(rows)
        kpis([('Percepción actual',f'{current:.1f}/5','Promedio de dimensiones registradas','◉',''),
              ('Nivel deseado',f'{desired:.1f}/5','Promedio de valores deseados','◎','blue'),
              ('Brecha percibida',f'{desired-current:+.1f}','Diferencia en escala 1–5','↗','orange'),
              ('Dimensiones',f'{len(rows)}/4','Cuatro dimensiones del modelo CENS','▦','purple')])
    else:
        kpis([('Percepción actual','Sin datos','Requiere registro','◉',''),
              ('Nivel deseado','Sin datos','Requiere registro','◎','blue'),
              ('Brecha percibida','Sin datos','No es calculable','↗','orange'),
              ('Dimensiones','0/4','Sin valores iniciales','▦','purple')])
    tab1,tab2=st.tabs(['Plan del diagnóstico','Madurez percibida'])
    with tab1:
        with st.container(border=True):
            with st.form('p2_edit_diagnostic'):
                a,b=st.columns(2)
                name=a.text_input('Nombre (automático)',item['nombre'],disabled=True);owner=b.text_input('Responsable',item['responsable'])
                population=a.number_input('Población objetivo',min_value=0,value=int(item['poblacion_objetivo'] or 0))
                status=b.selectbox('Estado', ['En diseño','Programado','En levantamiento','En análisis','Cerrado'],index=['En diseño','Programado','En levantamiento','En análisis','Cerrado'].index(item['estado']))
                objective=st.text_area('Objetivo',item['objetivo'])
                scope=st.text_area('Alcance',item['alcance'])
                actor=st.text_input('Responsable de actualización *')
                sent=st.form_submit_button('Guardar plan',type='primary')
            if sent:
                try:p2.update_diagnostic(diag,name,owner,objective,scope,int(population) if population else None,status,actor);st.success('Plan actualizado.');st.rerun()
                except ValidationError as ex:err(ex)
        st.caption('Secuencia: planificar → escuchar clientes → analizar evidencias → priorizar → validar. Los métodos se registran en levantamientos.')
    with tab2:
        st.info('Este análisis es de **percepción registrada**, no una evaluación certificada de madurez de la organización.')
        current={x['dimension']:x for x in p2.maturity(diag)}
        dimension=st.selectbox('Dimensión',p2.MATURITY,key='p2_mat_dim')
        with st.form('maturity_form'):
            a,b=st.columns(2)
            old=current.get(dimension)
            actual=b.select_slider('Nivel actual (1–5)',options=[1,2,3,4,5],value=old['actual'] if old else 3,key=f'p2_mat_actual_{diag}_{dimension}')
            desired=a.select_slider('Nivel deseado (1–5)',options=[1,2,3,4,5],value=old['deseado'] if old else 4,key=f'p2_mat_desired_{diag}_{dimension}')
            source=b.text_input('Fuente de la percepción *',value=old['fuente'] if old else '',key=f'p2_mat_source_{diag}_{dimension}')
            actor=st.text_input('Responsable *');sent=st.form_submit_button('Guardar dimensión',type='primary')
        if sent:
            try:p2.set_maturity(diag,dimension,int(actual),int(desired),source,actor);st.success('Percepción registrada.');st.rerun()
            except ValidationError as ex:err(ex)
        if current:
            import pandas as pd
            df=pd.DataFrame([{'Dimensión':r['dimension'],'Actual':r['actual'],'Deseado':r['deseado'],'Brecha':r['deseado']-r['actual'],'Fuente':r['fuente']} for r in current.values()])
            st.dataframe(df,hide_index=True,use_container_width=True)
            st.bar_chart(df.set_index('Dimensión')[['Actual','Deseado']])
        else:st.caption('Sin datos de madurez percibida. No se precargan valores del prototipo.')


def collecting(diag,item):
    people=list_clients(status='Activos')
    if not people:
        st.warning('Aún no hay clientes activos. Regístralos en Paso 1 antes de levantar información.')
        return
    labels=person_option(people)
    tab1,tab2=st.tabs(['Directorio compartido','Actividades de levantamiento'])
    with tab1:
        from .ui import e
        a,b=st.columns([1.57,1],gap='medium')
        with a:
            with st.container(border=True):
                st.markdown('**Directorio compartido**')
                st.caption('Perfiles identificados en el Paso 1 · selecciona una fila para consultar la ficha.')
                query=st.text_input('Buscar cliente',placeholder='Nombre, código, dependencia o rol',key='p2_client_search')
                filtered=[p for p in people if query.casefold() in ' '.join(str(p.get(f) or '') for f in ('nombre','codigo','dependencia','segmento','cargo','equipo_trabajo')).casefold()]
                if filtered:
                    table=st.dataframe([{'Código':p['codigo'],'Nombre':p['nombre'],'Dependencia':p['dependencia'],
                               'Rol':p['segmento'] or 'Sin clasificar','Equipo de trabajo':p.get('equipo_trabajo') or 'Sin registrar'} for p in filtered],
                         hide_index=True,use_container_width=True,
                         height=min(420,72+len(filtered)*36),selection_mode='single-row',on_select='rerun',key='p2_client_directory')
                    picked=table.selection.rows
                    default=next((i for i,c in enumerate(filtered) if c['id']==st.session_state.get('pmo_step2_client')),0)
                    row_idx=picked[0] if picked and picked[0]<len(filtered) else default
                    person=filtered[row_idx]
                else:
                    st.info('No hay clientes que coincidan con la búsqueda.')
                    person=None
        with b:
            with st.container(border=True):
                st.markdown('**Ficha del cliente**')
                st.caption('Una única identidad para todos los pasos del Flywheel')
                if not person:
                    st.info('Selecciona una fila del directorio.')
                else:
                    initials=''.join(p[:1] for p in person['nombre'].split()[:2]).upper()
                    st.markdown(f'<div class="pmo-client-hero"><div class="pmo-initial">{e(initials)}</div>'
                        f'<div class="pmo-person-title">{e(person["nombre"])}</div>'
                        f'<div class="pmo-minor">{e(person["cargo"])} · {e(person["dependencia"])}</div></div>',
                        unsafe_allow_html=True)
                    fields=[('Código',person['codigo']),('Rol',person['segmento'] or 'Sin clasificar'),
                            ('Dependencia',person['dependencia'] or 'Sin registrar'),('Equipo de trabajo',person.get('equipo_trabajo') or 'Sin registrar'),('Correo',person['correo'] or 'Sin registrar')]
                    for label,value in fields:
                        st.markdown(f'<div class="pmo-pair"><span>{e(label)}</span><b>{e(value)}</b></div>',
                                    unsafe_allow_html=True)
                    prior_count=len(p2.expectations(diag,person['id']))
                    interviews_count=sum(int(x['cliente_id']==person['id']) for x in p2.interviews(diag))
                    st.caption(f'En este diagnóstico: {prior_count} prioridades · {interviews_count} levantamientos')
                    st.markdown('**Necesidad preliminar**')
                    st.markdown(f'<div class="pmo-soft">{e(person.get("necesidades_preliminares") or "Sin antecedentes preliminares")}</div>',unsafe_allow_html=True)
        st.caption('El registro de levantamientos se encuentra en la siguiente pestaña; el directorio no se duplica.')
    with tab2:
        with st.expander('＋ Registrar levantamiento',expanded=False):
            with st.form('create_interview'):
                c1,c2=st.columns(2)
                default_client=st.session_state.get('pmo_step2_client')
                selected=c1.selectbox('Cliente *',list(labels),index=list(labels).index(default_client) if default_client in labels else 0,format_func=lambda i:labels[i])
                method=c2.selectbox('Método',['Entrevista','Encuesta','Grupo focal','Revisión documental'])
                when=c1.date_input('Fecha',value=date.today(), format='YYYY/MM/DD');state=c2.selectbox('Estado',['Programada','En curso','Completada','Cancelada'])
                note=st.text_area('Notas y resultados del levantamiento');source=st.text_input('Referencia / enlace de evidencia')
                actor=st.text_input('Responsable *');sent=st.form_submit_button('Guardar levantamiento',type='primary')
            if sent:
                try:p2.create_interview(diag,selected,method,when,state,note,source,actor);st.success('Levantamiento registrado.');st.rerun()
                except ValidationError as ex:err(ex)
        rows=p2.interviews(diag)
        if rows:st.dataframe([{'Fecha':x['fecha'],'Cliente':x['cliente'],'Código':x['codigo_cliente'],'Método':x['metodo'],'Estado':x['estado'],'Fuente':x['fuente']} for x in rows],hide_index=True,use_container_width=True)
        else:st.info('No se han registrado levantamientos en este diagnóstico.')


def needs(diag,item):
    t1,t2=st.tabs(['Expectativas de valor','Necesidades y evidencias'])
    people=list_clients(status='Activos');labels=person_option(people)
    with t1:
        st.caption('Selecciona y ordena hasta cinco resultados de valor por cliente. El ranking utiliza cinco prioridades completas y distintas.')
        with st.expander('Explorar el catálogo de 30 resultados esperados',expanded=False):
            from .ui import e
            cards=''.join(f'<div class="p2-outcome-card"><div class="p2-outcome-id">O-{n:02d}</div>'
                          f'<div class="p2-outcome-name">{e(title)}</div></div>' for n,title in OUTCOMES.items())
            st.markdown(f'<div class="p2-outcome-grid">{cards}</div>',unsafe_allow_html=True)
            st.caption('El catálogo es una referencia de consulta. Las prioridades se guardan en el formulario, no al hacer clic en una tarjeta.')
        if not people:st.warning('Primero registra clientes activos en Paso 1.')
        else:
            selected=st.selectbox('Cliente a evaluar',list(labels),format_func=lambda i:labels[i],key='p2_expect_client',index=list(labels).index(st.session_state.get('pmo_step2_client')) if st.session_state.get('pmo_step2_client') in labels else 0)
            current=p2.expectations(diag,selected)
            existing=[x['resultado_id'] for x in current]
            opt={0:'Sin seleccionar',**{k:f'{k:02d} · {v}' for k,v in OUTCOMES.items()}}
            with st.form('p2_expectations_form'):
                st.markdown('**Orden de importancia: 1 = más importante, 5 = menos importante**')
                cols=st.columns([1,1]);selected_ids=[]
                for i in range(5):
                    with cols[i%2]:
                        old=existing[i] if i<len(existing) else 0
                        val=st.selectbox(f'Prioridad {i+1}',list(opt),index=list(opt).index(old),format_func=lambda x:opt[x],key=f'p2_priority_{diag}_{selected}_{i}')
                        if val:selected_ids.append(val)
                actor=st.text_input('Responsable del registro *',key='p2_exp_actor')
                sent=st.form_submit_button('Guardar las prioridades',type='primary')
            if sent:
                try:
                    p2.save_priorities(diag,selected,selected_ids,actor)
                    st.success('Expectativas guardadas. Para calcular se requieren cinco resultados distintos.');st.rerun()
                except ValidationError as ex:err(ex)
            if selected_ids and len(set(selected_ids))!=len(selected_ids):st.warning('La selección actual contiene resultados repetidos. Corrígela antes de guardar.')
        records=p2.expectations(diag)
        summary={}
        for x in records:summary.setdefault((x['cliente_id'],x['nombre'],x['segmento']),[]).append(x['resultado_id'])
        if summary:
            st.markdown('**Expectativas registradas**')
            st.dataframe([{'Cliente':name,'Grupo':group or 'Sin clasificar','Prioridades':', '.join(f'{n:02d}' for n in values),'Completas':'Sí' if len(values)==5 else 'No'} for (_,name,group),values in summary.items()],hide_index=True,use_container_width=True)
        else:st.info('No hay expectativas registradas.')
    with t2:
        with st.expander('＋ Registrar necesidad',expanded=False):
            with st.form('p2_new_need'):
                a,b=st.columns(2)
                client=a.selectbox('Cliente que manifiesta la necesidad',['Sin cliente específico',*list(labels)],format_func=lambda x:labels.get(x,'Sin cliente específico'))
                actual=next((x for x in people if x['id']==client),None)
                dep=smart_choice('Dependencia *','dependencia',value=actual['dependencia'] if actual else '',key='p2_need_department',help='Dependencia declarada como fuente; no modifica la ficha del cliente.',parent=b,allow_blank=False)
                problem=st.text_area('Dificultad / punto crítico *');gain=st.text_area('Resultado deseado / ganancia *')
                outcome=a.selectbox('Resultado esperado relacionado',[0,*OUTCOMES],format_func=lambda n:'Sin asignar' if n==0 else f'{n:02d} · {OUTCOMES[n]}')
                impact=b.selectbox('Impacto declarado',['Sin evaluar','Bajo','Medio','Alto'])
                source=st.text_input('Referencia de evidencia o fuente');actor=st.text_input('Responsable *')
                sent=st.form_submit_button('Guardar necesidad',type='primary')
            if sent:
                try:p2.create_need(diag,None if client=='Sin cliente específico' else client,dep,problem,gain,outcome or None,impact,source,actor);st.success('Necesidad registrada.');st.rerun()
                except ValidationError as ex:err(ex)
        entries=p2.needs(diag)
        if not entries:st.info('No hay necesidades registradas.')
        else:
            from .ui import e
            levels=Counter(x['estado'] for x in entries)
            st.caption(' · '.join(f'{s}: {levels.get(s,0)}' for s in ('Registrada','En validación','Validada','Descartada')))
            ids={x['id']:x for x in entries}
            chosen=st.selectbox('Consultar necesidad',list(ids),format_func=lambda n:f"{n[:8]} · {ids[n]['problema'][:95]} · {ids[n]['estado']}",key='p2_need_detail')
            q=ids[chosen]
            left,right=st.columns(2)
            with left:
                st.markdown('**Dificultad identificada**')
                st.markdown(f'<div class="p2-pain"><div class="p2-panel-cap">DOLOR · SITUACIÓN ACTUAL</div>{e(q["problema"])}</div>',unsafe_allow_html=True)
            with right:
                st.markdown('**Ganancia o resultado esperado**')
                st.markdown(f'<div class="p2-gain"><div class="p2-panel-cap">GANANCIA · RESULTADO DESEADO</div>{e(q["ganancia"])}</div>',unsafe_allow_html=True)
            st.caption(f"Dependencia: {q['dependencia']} · Estado: {q['estado']} · Impacto: {q['impacto']} · Fuente: {q['fuente'] or 'Pendiente'}")
            with st.expander('Registrar validación de la necesidad'):
                with st.form('p2_need_validate'):
                    status=st.selectbox('Decisión',['Registrada','En validación','Validada','Descartada'],index=['Registrada','En validación','Validada','Descartada'].index(q['estado']))
                    reason=st.text_area('Justificación / acta o decisión registrada');actor=st.text_input('Responsable que registra *')
                    sent=st.form_submit_button('Guardar decisión',type='primary')
                if sent:
                    try:p2.update_need_status(q['id'],status,actor,reason);st.success('Estado actualizado con registro de auditoría.');st.rerun()
                    except ValidationError as ex:err(ex)
            st.dataframe([{'Código':codes.get(x['id'],'Sin código'),'Dependencia':x['dependencia'],'Resultado':OUTCOMES.get(x['resultado_id'],'Sin asignar'),'Impacto':x['impacto'],'Estado':x['estado']} for x in entries],hide_index=True,use_container_width=True)
            st.caption('Una validación registrada es declarativa: la versión local todavía no autentica a quien aprueba.')


def _weights_defaults(groups, saved):
    if saved and set(saved)==set(groups):return {g:float(saved[g]) for g in groups}
    names=list(groups)
    if not names:return {}
    n=len(names);base=round(100/n,2)
    return {g:(base if i<n-1 else round(100-base*(n-1),2)) for i,g in enumerate(names)}


def ranking(diag,item):
    st.markdown('<div class="p2-mini-guide"><span>01 · CAPTURA DE DATOS</span><i>→</i>'
                '<span>02 · PONDERACIÓN</span><i>→</i><span>03 · PROCESAMIENTO</span><i>→</i>'
                '<span>04 · RESULTADOS</span><i>→</i><span>05 · MATRIZ 30 × 26</span></div>',unsafe_allow_html=True)
    t1,t2,t3,t4=st.tabs(['Cargar expectativas Excel','Ponderación y procesamiento','Resultados e historial','Matriz PMO Value Ring'])
    with t1:
        people=list_clients(status='Activos')
        st.download_button('↓ Plantilla Excel de expectativas',excel.template_bytes(people),file_name='PMO_CENS_PASO2_EXPECTATIVAS.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        st.caption('Se genera con códigos reales del directorio; debes llenar cinco prioridades distintas entre 1 y 30. No modifica clientes ni grupos del Paso 1.')
        attachment=st.file_uploader('Excel o CSV con expectativas',type=['xlsx','csv'],key='p2_upload_expect')
        if attachment is not None:
            try:
                preview=excel.import_priorities(attachment.getvalue(),attachment.name,diag,actor='Vista previa',confirm=False)
                totals=Counter(x['Acción'] for x in preview)
                st.caption(f"Nuevos: {totals['Nuevo']} · Actualizaciones: {totals['Actualizar']} · Sin cambios: {totals['Sin cambios']} · Errores: {totals['Error']}")
                st.dataframe([{k:(str(v) if k=='Prioridades' else v) for k,v in x.items() if k!='ID cliente'} for x in preview],hide_index=True,use_container_width=True)
                actor=st.text_input('Responsable de la carga *')
                if totals['Error']:st.error('Corrige primero las filas inválidas. No se guardará información parcialmente.')
                elif st.button('Confirmar importación',disabled=not actor.strip(),type='primary',key='p2_confirm_xlsx'):
                    try:
                        excel.import_priorities(attachment.getvalue(),attachment.name,diag,actor=actor,confirm=True)
                        st.success('Importación completa y auditada.');st.rerun()
                    except ValidationError as ex:err(ex)
            except ValidationError as ex:err(ex)
    with t2:
        st.info('Los pesos varían según el juicio experto en cada escenario y se documentan con cada corrida.')
        _weights_section(diag,item)
    with t3:
        reports=p2.runs(diag)
        if not reports:st.info('No existe un análisis guardado todavía.')
        else:
            labels={r['id']:f"{r['fecha']} · {r['modelo']} · {r['actor']}" for r in reports}
            selected=st.selectbox('Análisis guardado',list(labels),format_func=lambda i:labels[i],key='p2_select_run')
            report=p2.get_run(selected);r=report['resultados']
            kpis([('Clientes procesados',str(r['participants']),'Cinco expectativas completas','♙',''),('Roles',str(len(r['groups'])),'Roles con respuestas válidas','◎','blue'),('Servicios analizados','26','Catálogo del motor Excel','▦','orange'),('Concentración Top 5',f"{r['top5']:.1f}%",'Participación del ranking','✓','purple')])
            sub1,sub2,sub3=st.tabs(['Resultados esperados','Servicios PMO','Grupos y método'])
            with sub1:
                import pandas as pd
                st.bar_chart(pd.DataFrame([{'Resultado':x['name'],'Relevancia %':x['score']} for x in r['outcomes'][:12]]).set_index('Resultado'),horizontal=True)
                st.dataframe([{'Código':x['id'],'Resultado':x['name'],'Relevancia %':round(x['score'],3)} for x in r['outcomes']],hide_index=True,use_container_width=True)
            with sub2:
                import pandas as pd
                st.bar_chart(pd.DataFrame([{'Servicio':x['name'],'Relevancia %':x['score']} for x in r['services'][:10]]).set_index('Servicio'),horizontal=True)
                st.dataframe([{'Código':x['id'],'Servicio':x['name'],'Relevancia %':round(x['score'],3),'Acumulado %':round(x['cumulative'],2),'Clasificación analítica':x.get('category','—')} for x in r['services']],hide_index=True,use_container_width=True)
                st.markdown('**¿Por qué este servicio alcanzó esa posición?**')
                service_id=st.selectbox('Servicio a explicar',list(SERVICES),format_func=lambda sid:f'S-{sid:02d} · {SERVICES[sid]}',key='p2_explain_service')
                contributions=r.get('contributions',{}).get(str(service_id),[])
                if contributions:
                    st.dataframe([{'Resultado':f"O-{x['outcome_id']:02d} · {x['outcome']}",'Relevancia resultado (%)':round(x['result_weight_pct'],3),
                        'Intensidad':x['intensity'],'Puntos aportados a servicio (%)':round(x['service_share_pct'],3),
                        'Aporte ranking global (pp)':round(x['global_share_pct'],4)} for x in contributions],hide_index=True,use_container_width=True)
                elif 'contributions' not in r:st.caption('Corrida anterior a esta actualización: conserva su snapshot pero no incluye desglose precomputado.')
                else:st.info('El servicio no recibió una contribución positiva en este escenario.')
            with sub3:
                st.dataframe([{'Grupo':g,'Participantes':v['participants'],'Peso %':v['weight']} for g,v in r['groups'].items()],hide_index=True,use_container_width=True)
                st.caption(f"Modelo: {report['modelo']} · Método: {r['method']} · Fuente: {report['origen']}. Respuestas parciales excluidas: {r['excluded_partial']}")
            st.download_button('↓ Descargar resultados en Excel',results_xlsx(report),file_name=f'PMO_CENS_P2_ANALISIS_{selected[:8]}.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            if r.get('v5_validation'):
                check=r['v5_validation']
                st.caption(f"Control V5: SHA256 {check['matrix_sha256']} · Conformidad con motor de referencia: {check['max_internal_delta_pp']:.3g} pp · Referencia histórica: 30 FOCO + 8 independientes.")
            st.warning('El ranking es analítico y depende de la matriz y los pesos seleccionados. La V5 es una reconstrucción numérica no certificada por PMI/PMOGA, y ninguna de estas salidas aprueba automáticamente servicios.')
    with t4:
        from .matrix_ui import panel
        panel(diag)




def validation(diag,item):
    entries=p2.needs(diag);valid=[x for x in entries if x['estado']=='Validada']
    candidates=p2.candidates(diag)
    kpis([('Necesidades identificadas',str(len(entries)),'Hallazgos de distintas fuentes','◎',''),
          ('Necesidades validadas',str(len(valid)),'Decisiones registradas','✓','blue'),
          ('Servicios preseleccionados',str(sum(x['estado']=='Preseleccionado' for x in candidates)),
           'Aún requieren revisión','▦','orange'),
          ('Servicios validados',str(sum(x['estado']=='Validado' for x in candidates)),
           'Con justificación registrada','◉','purple')])
    if valid:st.dataframe([{'Dependencia':x['dependencia'],'Problema':x['problema'],'Ganancia':x['ganancia'],'Resultado':OUTCOMES.get(x['resultado_id'],'—')} for x in valid],hide_index=True,use_container_width=True)
    else:st.info('No se han validado necesidades. Puedes preseleccionar candidatos, pero no marcarlos como validados todavía.')
    runs=p2.runs(diag)
    if runs:
        data=p2.get_run(runs[0]['id'])['resultados']
        st.markdown('**Servicios más relevantes, según último análisis**')
        st.dataframe([{'Servicio':x['name'],'Relevancia %':round(x['score'],2)} for x in data['services'][:8]],hide_index=True,use_container_width=True)
    with st.expander('＋ Registrar decisión sobre servicio candidato',expanded=False):
        with st.form('p2_select_candidate'):
            a,b=st.columns(2)
            svc=a.selectbox('Servicio *',list(SERVICES),format_func=lambda i:f'{i:02d} · {SERVICES[i]}')
            status=b.selectbox('Estado',['Preseleccionado','En validación','Validado','Descartado'])
            reason=st.text_area('Justificación y referencia de validación *')
            actor=st.text_input('Responsable *')
            sent=st.form_submit_button('Guardar decisión',type='primary')
        if sent:
            try:p2.set_candidate(diag,svc,status,reason,actor);st.success('Decisión registrada.');st.rerun()
            except ValidationError as ex:err(ex)
    candidates=p2.candidates(diag)
    if candidates:
        st.dataframe([{'Servicio':SERVICES.get(x['servicio_id'],'—'),'Estado':x['estado'],'Justificación':x['justificacion'],'Responsable':x['responsable']} for x in candidates],hide_index=True,use_container_width=True)
    st.caption('Preselección ≠ aprobación de un servicio. Para la futura etapa de propuesta de valor se transferirán referencias y antecedentes, no obligaciones automáticas.')


def audit_evidence(diag,item):
    t1,t2=st.tabs(['Autoevaluación adaptada','Evidencias e informe'])
    with t1:
        with st.expander('＋ Nueva autoevaluación',expanded=False):
            with st.form('p2_eval_create'):
                evaluator=st.text_input('Evaluador *')
                sent=st.form_submit_button('Crear borrador',type='primary')
            if sent:
                try:p2.start_assessment(diag,evaluator);st.success('Evaluación creada.');st.rerun()
                except ValidationError as ex:err(ex)
        ass=p2.assessments(diag)
        if not ass:
            st.info('No hay autoevaluaciones. Las 25 preguntas de esta versión son descriptores originales adaptados para CENS, no las preguntas oficiales del PMI.')
        else:
            labels={x['id']:f"{x['evaluador']} · {x['estado']} · {x['creado_en']}" for x in ass}
            aid=st.selectbox('Evaluación',list(labels),format_func=lambda i:labels[i])
            current=next(x for x in ass if x['id']==aid)
            answers=p2.answers(aid);completed=len(answers)==25
            st.progress(len(answers)/25,text=f'{len(answers)}/25 criterios respondidos')
            st.caption(f"Instrumento: {current['instrumento']} · Estado: {current['estado']}")
            if current['estado']=='Finalizada':st.success(f"Resultado: {current['puntaje']}/125 · {current['clasificacion']}")
            left,right=st.columns([1,2])
            with left:
                dimension=st.radio('Dimensiones',list(range(5)),format_func=lambda i:f"{i+1:02d} · {p2.AUDIT_DIMENSIONS[i][0]}")
                if current['estado']=='Borrador':
                    if st.button('Finalizar evaluación',disabled=not completed):
                        try:p2.finish_assessment(aid,current['evaluador']);st.success('Evaluación finalizada.');st.rerun()
                        except ValidationError as ex:err(ex)
            with right:
                st.markdown(f'**{p2.AUDIT_DIMENSIONS[dimension][0]}**')
                with st.form(f'p2_assess_{aid}_{dimension}'):
                    values=[]
                    for i,q in enumerate(p2.AUDIT_DIMENSIONS[dimension][1],1):
                        num=dimension*5+i;existing=answers.get(num,{});rating=existing.get('valor')
                        st.markdown(f'**{num:02d}. {q}**')
                        sel=st.selectbox('Valoración', [0,1,2,3,4,5],index=rating if rating else 0,
                                         format_func=lambda v:'Sin responder' if v==0 else str(v),key=f'p2_a_{aid}_{num}',disabled=current['estado']=='Finalizada')
                        note=st.text_input('Justificación',value=existing.get('observacion',''),key=f'p2_an_{aid}_{num}',disabled=current['estado']=='Finalizada')
                        ev=st.text_input('Enlace o código de evidencia',value=existing.get('evidencia',''),key=f'p2_ae_{aid}_{num}',disabled=current['estado']=='Finalizada')
                        values.append((num,sel or None,note,ev))
                    sent=st.form_submit_button('Guardar dimensión',type='primary',disabled=current['estado']=='Finalizada')
                if sent:
                    try:
                        for num,sel,note,ev in values:p2.save_answer(aid,num,sel,note,ev,current['evaluador'])
                        st.success('Respuestas guardadas.');st.rerun()
                    except ValidationError as ex:err(ex)
    with t2:
        with st.expander('＋ Registrar evidencia documental'):
            with st.form('p2_evidence_create'):
                title=st.text_input('Descripción *');kind=st.selectbox('Tipo',['Entrevista','Encuesta','Grupo focal','Acta','Informe','Lecciones aprendidas','Otro'])
                ns=p2.needs(diag)
                from .needs_console import public_codes
                need_codes=public_codes(diag) if ns else {}
                n_id=st.selectbox('Necesidad asociada (opcional)',['Sin asociar',*[x['id'] for x in ns]],format_func=lambda i:'Sin asociar' if i=='Sin asociar' else f"{need_codes.get(i,'Sin código')} · "+next(x['problema'][:80] for x in ns if x['id']==i))
                source=st.text_input('Enlace del documento (https://)');when=st.date_input('Fecha',value=date.today(), format='YYYY/MM/DD')
                actor=st.text_input('Responsable *');sent=st.form_submit_button('Guardar referencia',type='primary')
            if sent:
                try:p2.create_evidence(diag,title,kind,when,actor,None if n_id=='Sin asociar' else n_id,url=source);st.success('Evidencia referenciada.');st.rerun()
                except ValidationError as ex:err(ex)
        all_evidence=p2.evidence(diag)
        if all_evidence:
            st.dataframe([{'Fecha':x['fecha'],'Descripción':x['titulo'],'Tipo':x['tipo'],'Necesidad':need_codes.get(x['necesidad_id'],'Sin asociar'),'Enlace':x['url']} for x in all_evidence],hide_index=True,use_container_width=True)
        else:st.info('No hay evidencias documentadas todavía.')
        st.download_button('↓ Exportar expediente JSON para Paso 3',p2.transfer_json(diag),file_name=f'PMO_CENS_PASO2_EXPEDIENTE_{diag[:8]}.json',mime='application/json')
        st.caption('El archivo es un insumo para el Paso 3 futuro. No crea propuestas ni valida servicios automáticamente. Los vínculos documentales no transfieren permisos de SharePoint.')


# Funciones reutilizadas de las secciones de V0.7, ahora mostradas directamente por pantalla.
def _plan_form(diag,item):
    with st.container(border=True):
        with st.form('p2_edit_diagnostic'):
            a,b=st.columns(2)
            name=a.text_input('Nombre (automático)',item['nombre'],disabled=True);owner=b.text_input('Responsable',item['responsable'])
            population=a.number_input('Población objetivo',min_value=0,value=int(item['poblacion_objetivo'] or 0))
            status=b.selectbox('Estado', ['En diseño','Programado','En levantamiento','En análisis','Cerrado'],index=['En diseño','Programado','En levantamiento','En análisis','Cerrado'].index(item['estado']))
            objective=st.text_area('Objetivo',item['objetivo'])
            scope=st.text_area('Alcance',item['alcance'])
            actor=st.text_input('Responsable de actualización *')
            sent=st.form_submit_button('Guardar plan',type='primary')
        if sent:
            try:p2.update_diagnostic(diag,name,owner,objective,scope,int(population) if population else None,status,actor);st.success('Plan actualizado.');st.rerun()
            except ValidationError as ex:err(ex)
    st.caption('Secuencia: planificar → escuchar clientes → analizar evidencias → priorizar → validar. Los métodos se registran en levantamientos.')


def _maturity_form(diag,item):
    st.info('Este análisis es de **percepción registrada**, no una evaluación certificada de madurez de la organización.')
    current={x['dimension']:x for x in p2.maturity(diag)}
    dimension=st.selectbox('Dimensión',p2.MATURITY,key='p2_mat_dim')
    with st.form('maturity_form'):
        a,b=st.columns(2)
        old=current.get(dimension)
        actual=b.select_slider('Nivel actual (1–5)',options=[1,2,3,4,5],value=old['actual'] if old else 3,key=f'p2_mat_actual_{diag}_{dimension}')
        desired=a.select_slider('Nivel deseado (1–5)',options=[1,2,3,4,5],value=old['deseado'] if old else 4,key=f'p2_mat_desired_{diag}_{dimension}')
        source=b.text_input('Fuente de la percepción *',value=old['fuente'] if old else '',key=f'p2_mat_source_{diag}_{dimension}')
        actor=st.text_input('Responsable *');sent=st.form_submit_button('Guardar dimensión',type='primary')
    if sent:
        try:p2.set_maturity(diag,dimension,int(actual),int(desired),source,actor);st.success('Percepción registrada.');st.rerun()
        except ValidationError as ex:err(ex)
    if current:
        import pandas as pd
        df=pd.DataFrame([{'Dimensión':r['dimension'],'Actual':r['actual'],'Deseado':r['deseado'],'Brecha':r['deseado']-r['actual'],'Fuente':r['fuente']} for r in current.values()])
        st.dataframe(df,hide_index=True,use_container_width=True)
        st.bar_chart(df.set_index('Dimensión')[['Actual','Deseado']])
    else:st.caption('Sin datos de madurez percibida. No se precargan valores del prototipo.')


def _clients_section(diag,item):
    people=list_clients(status='Activos')
    if not people:
        st.warning('Registra primero clientes activos en el Paso 1.')
        return
    labels=person_option(people)
    from .ui import e
    a,b=st.columns([1.57,1],gap='medium')
    with a:
        with st.container(border=True):
            st.markdown('**Directorio compartido**')
            st.caption('Perfiles identificados en el Paso 1 · selecciona una fila para consultar la ficha.')
            query=st.text_input('Buscar cliente',placeholder='Nombre, código, dependencia o rol',key='p2_client_search')
            filtered=[p for p in people if query.casefold() in ' '.join(str(p.get(f) or '') for f in ('nombre','codigo','dependencia','segmento','cargo','equipo_trabajo')).casefold()]
            if filtered:
                table=st.dataframe([{'Código':p['codigo'],'Nombre':p['nombre'],'Dependencia':p['dependencia'],
                           'Rol':p['segmento'] or 'Sin clasificar','Equipo de trabajo':p.get('equipo_trabajo') or 'Sin registrar'} for p in filtered],
                     hide_index=True,use_container_width=True,
                     height=min(420,72+len(filtered)*36),selection_mode='single-row',on_select='rerun',key='p2_client_directory')
                picked=table.selection.rows
                default=next((i for i,c in enumerate(filtered) if c['id']==st.session_state.get('pmo_step2_client')),0)
                row_idx=picked[0] if picked and picked[0]<len(filtered) else default
                person=filtered[row_idx]
            else:
                st.info('No hay clientes que coincidan con la búsqueda.')
                person=None
    with b:
        with st.container(border=True):
            st.markdown('**Ficha del cliente**')
            st.caption('Una única identidad para todos los pasos del Flywheel')
            if not person:
                st.info('Selecciona una fila del directorio.')
            else:
                initials=''.join(p[:1] for p in person['nombre'].split()[:2]).upper()
                st.markdown(f'<div class="pmo-client-hero"><div class="pmo-initial">{e(initials)}</div>'
                    f'<div class="pmo-person-title">{e(person["nombre"])}</div>'
                    f'<div class="pmo-minor">{e(person["cargo"])} · {e(person["dependencia"])}</div></div>',
                    unsafe_allow_html=True)
                fields=[('Código',person['codigo']),('Rol',person['segmento'] or 'Sin clasificar'),
                        ('Dependencia',person['dependencia'] or 'Sin registrar'),('Equipo de trabajo',person.get('equipo_trabajo') or 'Sin registrar'),('Correo',person['correo'] or 'Sin registrar')]
                for label,value in fields:
                    st.markdown(f'<div class="pmo-pair"><span>{e(label)}</span><b>{e(value)}</b></div>',
                                unsafe_allow_html=True)
                prior_count=len(p2.expectations(diag,person['id']))
                interviews_count=sum(int(x['cliente_id']==person['id']) for x in p2.interviews(diag))
                st.caption(f'En este diagnóstico: {prior_count} prioridades · {interviews_count} levantamientos')
                st.markdown('**Necesidad preliminar**')
                st.markdown(f'<div class="pmo-soft">{e(person.get("necesidades_preliminares") or "Sin antecedentes preliminares")}</div>',unsafe_allow_html=True)
    st.caption('El registro de levantamientos se encuentra en la siguiente pestaña; el directorio no se duplica.')


def _interviews_section(diag,item):
    people=list_clients(status='Activos')
    if not people:
        st.info('No hay clientes activos para registrar levantamientos.')
        return
    labels=person_option(people)
    with st.expander('＋ Registrar levantamiento',expanded=False):
        with st.form('create_interview'):
            c1,c2=st.columns(2)
            default_client=st.session_state.get('pmo_step2_client')
            selected=c1.selectbox('Cliente *',list(labels),index=list(labels).index(default_client) if default_client in labels else 0,format_func=lambda i:labels[i])
            method=c2.selectbox('Método',['Entrevista','Encuesta','Grupo focal','Revisión documental'])
            when=c1.date_input('Fecha',value=date.today(), format='YYYY/MM/DD');state=c2.selectbox('Estado',['Programada','En curso','Completada','Cancelada'])
            note=st.text_area('Notas y resultados del levantamiento');source=st.text_input('Referencia / enlace de evidencia')
            actor=st.text_input('Responsable *');sent=st.form_submit_button('Guardar levantamiento',type='primary')
        if sent:
            try:p2.create_interview(diag,selected,method,when,state,note,source,actor);st.success('Levantamiento registrado.');st.rerun()
            except ValidationError as ex:err(ex)
    rows=p2.interviews(diag)
    if rows:st.dataframe([{'Fecha':x['fecha'],'Cliente':x['cliente'],'Código':x['codigo_cliente'],'Método':x['metodo'],'Estado':x['estado'],'Fuente':x['fuente']} for x in rows],hide_index=True,use_container_width=True)
    else:st.info('No se han registrado levantamientos en este diagnóstico.')


def _expectations_section(diag,item):
    people=list_clients(status='Activos')
    labels=person_option(people)
    st.caption('Selecciona y ordena hasta cinco resultados de valor por cliente. El ranking utiliza cinco prioridades completas y distintas.')
    with st.expander('Explorar el catálogo de 30 resultados esperados',expanded=False):
        from .ui import e
        cards=''.join(f'<div class="p2-outcome-card"><div class="p2-outcome-id">O-{n:02d}</div>'
                      f'<div class="p2-outcome-name">{e(title)}</div></div>' for n,title in OUTCOMES.items())
        st.markdown(f'<div class="p2-outcome-grid">{cards}</div>',unsafe_allow_html=True)
        st.caption('El catálogo es una referencia de consulta. Las prioridades se guardan en el formulario, no al hacer clic en una tarjeta.')
    if not people:st.warning('Primero registra clientes activos en Paso 1.')
    else:
        selected=st.selectbox('Cliente a evaluar',list(labels),format_func=lambda i:labels[i],key='p2_expect_client',index=list(labels).index(st.session_state.get('pmo_step2_client')) if st.session_state.get('pmo_step2_client') in labels else 0)
        current=p2.expectations(diag,selected)
        existing=[x['resultado_id'] for x in current]
        opt={0:'Sin seleccionar',**{k:f'{k:02d} · {v}' for k,v in OUTCOMES.items()}}
        with st.form('p2_expectations_form'):
            st.markdown('**Orden de importancia: 1 = más importante, 5 = menos importante**')
            cols=st.columns([1,1]);selected_ids=[]
            for i in range(5):
                with cols[i%2]:
                    old=existing[i] if i<len(existing) else 0
                    val=st.selectbox(f'Prioridad {i+1}',list(opt),index=list(opt).index(old),format_func=lambda x:opt[x],key=f'p2_priority_{diag}_{selected}_{i}')
                    if val:selected_ids.append(val)
            actor=st.text_input('Responsable del registro *',key='p2_exp_actor')
            sent=st.form_submit_button('Guardar las prioridades',type='primary')
        if sent:
            try:
                p2.save_priorities(diag,selected,selected_ids,actor)
                st.success('Expectativas guardadas. Para calcular se requieren cinco resultados distintos.');st.rerun()
            except ValidationError as ex:err(ex)
        if selected_ids and len(set(selected_ids))!=len(selected_ids):st.warning('La selección actual contiene resultados repetidos. Corrígela antes de guardar.')
    records=p2.expectations(diag)
    summary={}
    for x in records:summary.setdefault((x['cliente_id'],x['nombre'],x['segmento']),[]).append(x['resultado_id'])
    if summary:
        st.markdown('**Expectativas registradas**')
        st.dataframe([{'Cliente':name,'Grupo':group or 'Sin clasificar','Prioridades':', '.join(f'{n:02d}' for n in values),'Completas':'Sí' if len(values)==5 else 'No'} for (_,name,group),values in summary.items()],hide_index=True,use_container_width=True)
    else:st.info('No hay expectativas registradas.')


def _needs_section(diag,item,display_entries=None,public_code_map=None):
    people=list_clients(status='Activos')
    labels=person_option(people)
    # V0.38.6: la carga masiva pertenece a este módulo, no a las expectativas
    # de 30 beneficios ni al expediente general. Ninguna fila se valida sola.
    with st.expander('⇧ Importar necesidades desde Excel o CSV', expanded=False):
        from pathlib import Path as _Path
        from . import step2_needs_excel as needs_excel
        st.caption('Importa dificultades y resultados deseados al diagnóstico seleccionado. '
                   'Las filas nuevas quedan **Registradas**, pendientes de revisión. '
                   'No altera los clientes, las 39 preferencias, las ponderaciones ni las corridas V5.')
        template=_Path(__file__).resolve().parent.parent/'plantillas'/'PLANTILLA_NECESIDADES_PASO02_V0386.xlsx'
        if template.is_file():
            st.download_button('↓ Descargar plantilla Excel de necesidades',
                               data=template.read_bytes(),file_name=template.name,
                               mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                               key='p2_download_need_template_v0386')
        else:
            st.warning('No se encontró la plantilla. Revise la instalación del paquete.')
        uploader=st.file_uploader('Archivo de necesidades (.xlsx o .csv)',type=['xlsx','csv'],
                                  key='p2_needs_import_file_v0386')
        actor_bulk=st.text_input('Responsable de la carga *',
                                 key='p2_needs_import_actor_v0386',
                                 help='Se registra en la auditoría. Puede complementar los responsables de cada fila.')
        if uploader is not None:
            try:
                data=uploader.getvalue()
                result=needs_excel.import_needs(data,uploader.name,diag,actor_bulk or 'Vista previa',confirm=False)
                count=result['counts']
                st.caption(f"Nuevas: {count.get('Nuevo',0)} · Sin cambios: {count.get('Sin cambios',0)} · "
                           f"Errores: {count.get('Error',0)}")
                st.dataframe(needs_excel.public_preview(result['preview']),
                             hide_index=True,use_container_width=True)
                if not actor_bulk.strip():
                    st.info('Indique el responsable de la carga para habilitar la confirmación.')
                if count.get('Error',0):
                    st.error('Corrija las filas señaladas en el Excel. No se importará una carga parcial.')
                elif not count.get('Nuevo',0):
                    st.info('Todas las necesidades del archivo ya figuran en este diagnóstico.')
                else:
                    confirm=st.checkbox('Confirmo la incorporación de las necesidades nuevas a este diagnóstico. '
                                        'Se generará un respaldo y no se validarán automáticamente.',
                                        key='p2_needs_import_confirmation_v0386')
                    if st.button('Confirmar carga de necesidades',type='primary',
                                 disabled=not (confirm and actor_bulk.strip()),
                                 key='p2_needs_import_apply_v0386'):
                        done=needs_excel.import_needs(data,uploader.name,diag,actor_bulk,confirm=True)
                        st.success(f"Se registraron {done['counts'].get('Nuevo',0)} necesidades. "
                                   f"Respaldo: {done['backup']}")
                        st.rerun()
            except (ValidationError, OSError, ValueError) as ex:
                err(ex)
    with st.expander('＋ Registrar necesidad',expanded=False):
        with st.form('p2_new_need'):
            a,b=st.columns(2)
            client=a.selectbox('Cliente que manifiesta la necesidad',['Sin cliente específico',*list(labels)],format_func=lambda x:labels.get(x,'Sin cliente específico'))
            actual=next((x for x in people if x['id']==client),None)
            dep=smart_choice('Dependencia *','dependencia',value=actual['dependencia'] if actual else '',key='p2_need_department',help='Dependencia declarada como fuente; no modifica la ficha del cliente.',parent=b,allow_blank=False)
            problem=st.text_area('Dificultad / punto crítico *');gain=st.text_area('Resultado deseado / ganancia *')
            outcome=a.selectbox('Resultado esperado relacionado',[0,*OUTCOMES],format_func=lambda n:'Sin asignar' if n==0 else f'{n:02d} · {OUTCOMES[n]}')
            impact=b.selectbox('Impacto declarado',['Sin evaluar','Bajo','Medio','Alto'])
            source=st.text_input('Referencia de evidencia o fuente');actor=st.text_input('Responsable *')
            sent=st.form_submit_button('Guardar necesidad',type='primary')
        if sent:
            try:p2.create_need(diag,None if client=='Sin cliente específico' else client,dep,problem,gain,outcome or None,impact,source,actor);st.success('Necesidad registrada.');st.rerun()
            except ValidationError as ex:err(ex)
    all_entries=p2.needs(diag)
    entries=all_entries if display_entries is None else display_entries
    if not entries:
        st.info('No hay necesidades que coincidan con los filtros para consultar o validar.' if all_entries else 'No hay necesidades registradas.')
    else:
        from .ui import e
        from .needs_console import public_codes
        codes=public_code_map if public_code_map is not None else public_codes(diag)
        levels=Counter(x['estado'] for x in all_entries)
        st.caption(' · '.join(f'{state}: {levels.get(state,0)}' for state in ('Registrada','En validación','Validada','Descartada')))
        ids={x['id']:x for x in entries}
        if st.session_state.get('p2_need_detail') not in ids:
            st.session_state['p2_need_detail']=next(iter(ids))
        chosen=st.selectbox('Consultar necesidad',list(ids),format_func=lambda n:f"{codes.get(n,'Sin código')} · {ids[n]['problema'][:86]} · {ids[n]['estado']}",key='p2_need_detail')
        q=ids[chosen]
        left,right=st.columns(2)
        with left:
            st.markdown('**Dificultad identificada**')
            st.markdown(f'<div class="p2-pain"><div class="p2-panel-cap">DOLOR · SITUACIÓN ACTUAL</div>{e(q["problema"])}</div>',unsafe_allow_html=True)
        with right:
            st.markdown('**Ganancia o resultado esperado**')
            st.markdown(f'<div class="p2-gain"><div class="p2-panel-cap">GANANCIA · RESULTADO DESEADO</div>{e(q["ganancia"])}</div>',unsafe_allow_html=True)
        st.caption(f"Dependencia: {q['dependencia']} · Estado: {q['estado']} · Impacto: {q['impacto']} · Fuente: {q['fuente'] or 'Pendiente'}")
        with st.expander('Registrar validación de la necesidad'):
            with st.form('p2_need_validate'):
                status=st.selectbox('Decisión',['Registrada','En validación','Validada','Descartada'],index=['Registrada','En validación','Validada','Descartada'].index(q['estado']))
                reason=st.text_area('Justificación / acta o decisión registrada');actor=st.text_input('Responsable que registra *')
                sent=st.form_submit_button('Guardar decisión',type='primary')
            if sent:
                try:p2.update_need_status(q['id'],status,actor,reason);st.success('Estado actualizado con registro de auditoría.');st.rerun()
                except ValidationError as ex:err(ex)
        st.dataframe([{'Código':codes.get(x['id'],'Sin código'),'Dependencia':x['dependencia'],'Resultado':OUTCOMES.get(x['resultado_id'],'Sin asignar'),'Impacto':x['impacto'],'Estado':x['estado']} for x in entries],hide_index=True,use_container_width=True)
        st.caption('Una validación registrada es declarativa: la versión local todavía no autentica a quien aprueba.')


def _load_excel_section(diag,item):
    people=list_clients(status='Activos')
    st.download_button('↓ Plantilla Excel de expectativas',excel.template_bytes(people),file_name='PMO_CENS_PASO2_EXPECTATIVAS.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    st.caption('Se genera con códigos reales del directorio; debes llenar cinco prioridades distintas entre 1 y 30. No modifica clientes ni grupos del Paso 1.')
    attachment=st.file_uploader('Excel o CSV con expectativas',type=['xlsx','csv'],key='p2_upload_expect')
    if attachment is not None:
        try:
            preview=excel.import_priorities(attachment.getvalue(),attachment.name,diag,actor='Vista previa',confirm=False)
            totals=Counter(x['Acción'] for x in preview)
            st.caption(f"Nuevos: {totals['Nuevo']} · Actualizaciones: {totals['Actualizar']} · Sin cambios: {totals['Sin cambios']} · Errores: {totals['Error']}")
            st.dataframe([{k:(str(v) if k=='Prioridades' else v) for k,v in x.items() if k!='ID cliente'} for x in preview],hide_index=True,use_container_width=True)
            actor=st.text_input('Responsable de la carga *')
            if totals['Error']:st.error('Corrige primero las filas inválidas. No se guardará información parcialmente.')
            elif st.button('Confirmar importación',disabled=not actor.strip(),type='primary',key='p2_confirm_xlsx'):
                try:
                    excel.import_priorities(attachment.getvalue(),attachment.name,diag,actor=actor,confirm=True)
                    st.success('Importación completa y auditada.');st.rerun()
                except ValidationError as ex:err(ex)
        except ValidationError as ex:err(ex)


def _weights_section(diag,item):
    from . import step2_participants as expert33
    expert33.ensure_schema()
    gr=p2.groups_with_participants(diag)
    active={g:c for g,c in gr.items() if any(x['group']==g and len(x['priorities'])==5 for x in p2._participant_records(diag))}
    partial=len([x for x in p2._participant_records(diag) if len(x['priorities'])!=5])
    if partial:st.warning(f'{partial} persona(s) tienen una lista incompleta de expectativas y se excluirán del cálculo.')
    all_known_roles=role_catalog()
    with st.expander(f'Catálogo dinámico de roles del directorio ({len(all_known_roles)})',expanded=False):
        st.dataframe([{'Rol':role,'Clientes activos':count,'Respuestas completas habilitadas':active.get(role,0)}
                      for role,count in all_known_roles.items()],hide_index=True,use_container_width=True)
        st.caption('Un rol nuevo aparece en este catálogo al guardar la ficha del cliente. Para asignarle peso necesita al menos una respuesta completa.')
    if not active:
        st.info('Se requieren cinco prioridades distintas por participante para ejecutar el análisis. Regístralas manualmente o importa un Excel.')
    else:
        saved=p2.saved_weights(diag)
        st.caption('Todos los roles del directorio se actualizan automáticamente. Solo los roles con respuestas completas pueden recibir ponderación. Los porcentajes son VARIABLES por evaluación y requieren criterio experto documentado.')
        selectable=[v for v in canonical.versions() if v['estado']!='ARCHIVADA']
        choices={v['id']:v for v in selectable}
        chosen=st.selectbox('Matriz para este cálculo',list(choices),index=list(choices).index(canonical.V5_ID),
            format_func=lambda vid:f"{vid} · {choices[vid]['estado']} · {choices[vid]['fuente']}",key='p2_selected_matrix_version')
        v5_mode=(chosen==canonical.V5_ID)
        if v5_mode:
            st.info('**V5 · Lógica contrastada:** 30 pruebas FOCO y ocho escenarios históricos. La matriz fue reconstruida matemáticamente, NO certificada por PMI/PMOGA. Para procesar exige cinco resultados por participante y pesos enteros asignados expresamente; no se autocompletan.')
            default={g:int(saved[g]) if saved and set(saved)==set(active) and float(saved[g]).is_integer() else 0 for g in active}
        else:
            default=_weights_defaults(active,saved)
            st.caption('La matriz documental X2 es apropiada como línea base; el escenario CENS 0–4 anterior expresa concordancia documental, no coeficientes oficiales.')
        with st.form('p2_weight_form'):
            vals={}
            all_roles=role_catalog()
            for g in sorted(set(active)|set(all_roles),key=str.casefold):
                num=active.get(g,0)
                a,b,c=st.columns([3,1,1],vertical_alignment='center')
                a.markdown(f'**{g}**');c.caption(f'{all_roles.get(g,0)} clientes · {num} con respuesta completa')
                if not num:
                    b.number_input('Peso entero %' if v5_mode else 'Peso %',min_value=0,max_value=100,value=0,disabled=True,key=f'p2_weight_unavailable_{diag}_{g}',help='El rol aparece automáticamente desde el directorio, pero necesita respuestas completas para ponderarse.')
                elif v5_mode:
                    vals[g]=b.number_input('Peso entero %',min_value=0,max_value=100,value=default[g],step=1,key=f'p2_weight_v5_{diag}_{g}')
                else:
                    vals[g]=b.number_input('Peso %',min_value=0.,max_value=100.,value=float(default[g]),step=1.,format='%.2f',key=f'p2_weight_{diag}_{g}')
            total=sum(vals.values());st.caption(f'Total configurado: {total:.2f}% (obligatorio 100%)')
            method=st.selectbox('Método de criterio experto *', list(expert33.CRITERIA),
                                key=f'p2v033_method_{diag}')
            justification=st.text_area('Sustento de la ponderación *',
                           placeholder='Explique por qué este escenario asigna estos pesos a cada grupo. Se conservará con la corrida.',
                           key=f'p2v033_rationale_{diag}')
            owner=st.text_input('Responsable del cálculo *')
            submitted=st.form_submit_button('Guardar escenario experto y ejecutar análisis',type='primary')
        with st.expander('Asistente AHP de ponderación (opcional)'):
            if len(active)>8:
                st.caption('El asistente AHP admite un máximo de ocho grupos. Utilice ponderación manual para muestras mayores.')
            elif len(active)<2:
                st.caption('El AHP se utiliza para comparar dos o más grupos. Un único grupo tiene 100%.')
            else:
                st.caption('Compare la importancia relativa entre grupos. 1 = igual importancia; 3, 5, 7, 9 = preferencia creciente. El resultado es orientativo y requiere confirmación.')
                names=list(active)
                with st.form(f'p2_ahp_{diag}'):
                    comp={}
                    for ix,a in enumerate(names):
                        for b in names[ix+1:]:
                            value=st.select_slider(f'{a} / {b}', options=[-9,-7,-5,-3,-1,1,3,5,7,9],value=1,
                               format_func=lambda v:f'{a} ×{v}' if v>0 else f'{b} ×{abs(v)}',key=f'p2_ahp_cmp_{diag}_{a}_{b}')
                            comp[(a,b)]=(float(value) if value>0 else 1/float(abs(value)))
                    pressed=st.form_submit_button('Calcular sugerencia AHP')
                if pressed:
                    try:
                        recommendation,ratio=p2.ahp_weights(names,comp)
                        st.session_state[f'p2_ahp_result_{diag}']=(recommendation,ratio)
                    except ValidationError as ex:err(ex)
                result=st.session_state.get(f'p2_ahp_result_{diag}')
                if result:
                    recommended,ratio=result
                    st.dataframe([{'Grupo':g,'Peso sugerido %':v} for g,v in recommended.items()],hide_index=True,use_container_width=True)
                    st.caption(f'Consistencia aproximada (CR): {ratio:.3f}. Se recomienda revisar juicios si CR es mayor a 0,10.')
                    def _use_ahp():
                        if v5_mode:
                            # Distribución Hamilton: redondeo a enteros que suma exactamente 100.
                            import math as _math
                            base={g:_math.floor(float(v)) for g,v in recommended.items()}
                            needed=100-sum(base.values())
                            for group in sorted(recommended,key=lambda g:(-(float(recommended[g])-base[g]),g))[:needed]:base[group]+=1
                            for group,v in base.items():st.session_state[f'p2_weight_v5_{diag}_{group}']=int(v)
                        else:
                            for group,v in recommended.items():st.session_state[f'p2_weight_{diag}_{group}']=float(v)
                    st.button('Usar estos pesos en el formulario anterior',on_click=_use_ahp,help='Los pesos solo se guardan cuando confirmes y ejecutes el análisis.')
        if submitted:
            try:
                key=expert33.run_expert_scenario(diag,vals,owner,method,justification,chosen)
                st.success('Corrida generada con pesos variables, justificación experta y snapshot conservados.')
                st.session_state['p2_last_run']=key
                st.rerun()
            except ValidationError as ex:err(ex)
    st.caption('Metodología: 5–4–3–2–1 puntos; normalización por grupo; ponderación estratégica; correspondencia resultado–servicio; renormalización de servicios.')


def _results_section(diag,item):
    reports=p2.runs(diag)
    if not reports:st.info('No existe un análisis guardado todavía.')
    else:
        labels={r['id']:f"{r['fecha']} · {r['modelo']} · {r['actor']}" for r in reports}
        selected=st.selectbox('Análisis guardado',list(labels),format_func=lambda i:labels[i],key='p2_select_run')
        report=p2.get_run(selected);r=report['resultados']
        kpis([('Clientes procesados',str(r['participants']),'Cinco expectativas completas','♙',''),('Roles',str(len(r['groups'])),'Roles con respuestas válidas','◎','blue'),('Servicios analizados','26','Catálogo del motor Excel','▦','orange'),('Concentración Top 5',f"{r['top5']:.1f}%",'Participación del ranking','✓','purple')])
        sub1,sub2,sub3=st.tabs(['Resultados esperados','Servicios PMO','Grupos y método'])
        with sub1:
            import pandas as pd
            st.bar_chart(pd.DataFrame([{'Resultado':x['name'],'Relevancia %':x['score']} for x in r['outcomes'][:12]]).set_index('Resultado'),horizontal=True)
            st.dataframe([{'Código':x['id'],'Resultado':x['name'],'Relevancia %':round(x['score'],3)} for x in r['outcomes']],hide_index=True,use_container_width=True)
        with sub2:
            import pandas as pd
            st.bar_chart(pd.DataFrame([{'Servicio':x['name'],'Relevancia %':x['score']} for x in r['services'][:10]]).set_index('Servicio'),horizontal=True)
            st.dataframe([{'Código':x['id'],'Servicio':x['name'],'Relevancia %':round(x['score'],3),'Acumulado %':round(x['cumulative'],2),'Clasificación analítica':x.get('category','—')} for x in r['services']],hide_index=True,use_container_width=True)
            st.markdown('**¿Por qué este servicio alcanzó esa posición?**')
            service_id=st.selectbox('Servicio a explicar',list(SERVICES),format_func=lambda sid:f'S-{sid:02d} · {SERVICES[sid]}',key='p2_explain_service')
            contributions=r.get('contributions',{}).get(str(service_id),[])
            if contributions:
                st.dataframe([{'Resultado':f"O-{x['outcome_id']:02d} · {x['outcome']}",'Relevancia resultado (%)':round(x['result_weight_pct'],3),
                    'Intensidad':x['intensity'],'Puntos aportados a servicio (%)':round(x['service_share_pct'],3),
                    'Aporte ranking global (pp)':round(x['global_share_pct'],4)} for x in contributions],hide_index=True,use_container_width=True)
            elif 'contributions' not in r:st.caption('Corrida anterior a esta actualización: conserva su snapshot pero no incluye desglose precomputado.')
            else:st.info('El servicio no recibió una contribución positiva en este escenario.')
        with sub3:
            st.dataframe([{'Grupo':g,'Participantes':v['participants'],'Peso %':v['weight']} for g,v in r['groups'].items()],hide_index=True,use_container_width=True)
            st.caption(f"Modelo: {report['modelo']} · Método: {r['method']} · Fuente: {report['origen']}. Respuestas parciales excluidas: {r['excluded_partial']}")
        st.download_button('↓ Descargar resultados en Excel',results_xlsx(report),file_name=f'PMO_CENS_P2_ANALISIS_{selected[:8]}.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        if r.get('v5_validation'):
            check=r['v5_validation']
            st.caption(f"Control V5: SHA256 {check['matrix_sha256']} · Conformidad con motor de referencia: {check['max_internal_delta_pp']:.3g} pp · Referencia histórica: 30 FOCO + 8 independientes.")
        st.warning('El ranking es analítico y depende de la matriz y los pesos seleccionados. La V5 es una reconstrucción numérica no certificada por PMI/PMOGA, y ninguna de estas salidas aprueba automáticamente servicios.')


def _assessment_section(diag,item):
    with st.expander('＋ Nueva autoevaluación',expanded=False):
        with st.form('p2_eval_create'):
            evaluator=st.text_input('Evaluador *')
            sent=st.form_submit_button('Crear borrador',type='primary')
        if sent:
            try:p2.start_assessment(diag,evaluator);st.success('Evaluación creada.');st.rerun()
            except ValidationError as ex:err(ex)
    ass=p2.assessments(diag)
    if not ass:
        st.info('No hay autoevaluaciones. Las 25 preguntas de esta versión son descriptores originales adaptados para CENS, no las preguntas oficiales del PMI.')
    else:
        labels={x['id']:f"{x['evaluador']} · {x['estado']} · {x['creado_en']}" for x in ass}
        aid=st.selectbox('Evaluación',list(labels),format_func=lambda i:labels[i])
        current=next(x for x in ass if x['id']==aid)
        answers=p2.answers(aid);completed=len(answers)==25
        st.progress(len(answers)/25,text=f'{len(answers)}/25 criterios respondidos')
        st.caption(f"Instrumento: {current['instrumento']} · Estado: {current['estado']}")
        if current['estado']=='Finalizada':st.success(f"Resultado: {current['puntaje']}/125 · {current['clasificacion']}")
        left,right=st.columns([1,2])
        with left:
            dimension=st.radio('Dimensiones',list(range(5)),format_func=lambda i:f"{i+1:02d} · {p2.AUDIT_DIMENSIONS[i][0]}")
            if current['estado']=='Borrador':
                if st.button('Finalizar evaluación',disabled=not completed):
                    try:p2.finish_assessment(aid,current['evaluador']);st.success('Evaluación finalizada.');st.rerun()
                    except ValidationError as ex:err(ex)
        with right:
            st.markdown(f'**{p2.AUDIT_DIMENSIONS[dimension][0]}**')
            with st.form(f'p2_assess_{aid}_{dimension}'):
                values=[]
                for i,q in enumerate(p2.AUDIT_DIMENSIONS[dimension][1],1):
                    num=dimension*5+i;existing=answers.get(num,{});rating=existing.get('valor')
                    st.markdown(f'**{num:02d}. {q}**')
                    sel=st.selectbox('Valoración', [0,1,2,3,4,5],index=rating if rating else 0,
                                     format_func=lambda v:'Sin responder' if v==0 else str(v),key=f'p2_a_{aid}_{num}',disabled=current['estado']=='Finalizada')
                    note=st.text_input('Justificación',value=existing.get('observacion',''),key=f'p2_an_{aid}_{num}',disabled=current['estado']=='Finalizada')
                    ev=st.text_input('Enlace o código de evidencia',value=existing.get('evidencia',''),key=f'p2_ae_{aid}_{num}',disabled=current['estado']=='Finalizada')
                    values.append((num,sel or None,note,ev))
                sent=st.form_submit_button('Guardar dimensión',type='primary',disabled=current['estado']=='Finalizada')
            if sent:
                try:
                    for num,sel,note,ev in values:p2.save_answer(aid,num,sel,note,ev,current['evaluador'])
                    st.success('Respuestas guardadas.');st.rerun()
                except ValidationError as ex:err(ex)


def _evidence_section(diag,item, *, show_transfer=True):
    with st.expander('＋ Registrar evidencia documental'):
        with st.form('p2_evidence_create'):
            title=st.text_input('Descripción *');kind=st.selectbox('Tipo',['Entrevista','Encuesta','Grupo focal','Acta','Informe','Lecciones aprendidas','Otro'])
            ns=p2.needs(diag)
            from .needs_console import public_codes
            need_codes=public_codes(diag) if ns else {}
            n_id=st.selectbox('Necesidad asociada (opcional)',['Sin asociar',*[x['id'] for x in ns]],format_func=lambda i:'Sin asociar' if i=='Sin asociar' else f"{need_codes.get(i,'Sin código')} · "+next(x['problema'][:80] for x in ns if x['id']==i))
            source=st.text_input('Enlace del documento (https://)');when=st.date_input('Fecha',value=date.today(), format='YYYY/MM/DD')
            actor=st.text_input('Responsable *');sent=st.form_submit_button('Guardar referencia',type='primary')
        if sent:
            try:p2.create_evidence(diag,title,kind,when,actor,None if n_id=='Sin asociar' else n_id,url=source);st.success('Evidencia referenciada.');st.rerun()
            except ValidationError as ex:err(ex)
    all_evidence=p2.evidence(diag)
    if all_evidence:
        st.dataframe([{'Fecha':x['fecha'],'Descripción':x['titulo'],'Tipo':x['tipo'],'Necesidad':need_codes.get(x['necesidad_id'],'Sin asociar'),'Enlace':x['url']} for x in all_evidence],hide_index=True,use_container_width=True)
    else:st.info('No hay evidencias documentadas todavía.')
    if show_transfer:
        st.download_button('↓ Exportar expediente JSON para Paso 3',p2.transfer_json(diag),file_name=f'PMO_CENS_PASO2_EXPEDIENTE_{diag[:8]}.json',mime='application/json')
    st.caption('Las referencias documentales se gestionan aquí. La transferencia se descarga desde «Informes y transferencia» y no crea aprobaciones ni permisos de SharePoint.')


