"""Interfaz Streamlit Paso 9 · cinco pantallas del prototipo integradas a SQLite."""
from __future__ import annotations
from .date_widgets import iso_date_input
import collections, html, io, json
from datetime import date
from pathlib import Path
import streamlit as st
from .staff_picker import staff_picker
from .client_picker import choose_client
import pandas as pd
from . import step9 as s
from .ui import kpi

NAV=list(s.MODULES)

def apply_step9_theme():
    st.markdown('''<style>
    .p9-info{background:#EFF9F9;border:1px solid #CDE6E9;border-radius:10px;padding:12px 15px;margin:10px 0 18px;color:#376E76;font-size:12px}
    .p9-section{background:#fff;border:1px solid #E1E8EF;border-radius:14px;padding:18px;margin:8px 0 14px}
    </style>''',unsafe_allow_html=True)

def esc(x):return html.escape(str(x or ''))
def jb(x):return json.dumps(x,ensure_ascii=False,indent=2,default=str).encode('utf-8')
def fmt(x,suffix='',places=1):return ('—' if x is None else f'{x:,.{places}f}'.replace(',','X').replace('.',',').replace('X','.'))+suffix if x is not None else '—'
def run(fn,label='Registro guardado'):
    try:
        result=fn();st.success(label);return result if result is not None else True
    except (s.ValidationError,ValueError,KeyError,TypeError,RuntimeError) as e:st.error(str(e));return None

def head(i,title,description):
    st.markdown(f'<div class="pmo-eyebrow">PASO 09 · MÓDULO {i:02d} · ENTREGA DE VALOR</div><div class="pmo-title">{esc(title)}</div><div class="pmo-subtitle">{esc(description)}</div>',unsafe_allow_html=True)

def kpis(rows):
    for idx,(col,(title,value,caption)) in enumerate(zip(st.columns(len(rows)),rows)):
        with col:kpi(title,value,caption,'chart-no-axes-column',('orange','blue','purple','teal')[idx%4])

def notice():
    st.markdown('<div class="p9-info">El valor entregado requiere medición verificable y validación explícita. Los tickets, los ANS y la satisfacción del cliente son contexto; no sustituyen la demostración del beneficio comprometido.</div>',unsafe_allow_html=True)

def _select_benefit(title='Beneficio',key='p9_benefit_select',records=None):
    options=records if records is not None else s.benefits()
    mapping={x['id']:x for x in options}
    if not mapping:st.info('No hay beneficios registrados.');return None
    chosen=st.selectbox(title,list(mapping),format_func=lambda x: f'{mapping[x]["servicio"]} · {mapping[x]["beneficio"][:65]}',key=key)
    return mapping.get(chosen)

@st.dialog('Ficha de beneficio y compromiso de valor',width='large')
def benefit_form(key=None):
    original=s.benefit(key) if key else {}
    original=original or {}
    has_indicator=bool(key and s.benefit_indicator(key))
    if has_indicator:st.caption('El indicador tiene una ficha técnica vinculada. Sus parámetros se editan desde «Definir indicador».')
    with st.form('p9_benefit_form'):
        st.caption('Los compromisos se miden únicamente cuando se registran resultados. La edición de valores fundamentales invalida una verificación anterior.')
        a,b=st.columns(2)
        with a:
            approved=s.approved_services()
            options={x['id']:x for x in approved}
            historical=original.get('servicio','')
            historical_id=original.get('servicio_id','')
            # Los códigos históricos se conservan en edición; no se ofrecen para crear nuevas fichas.
            if historical_id and historical_id not in options and historical:
                options[historical_id]={'id':historical_id,'codigo':'Histórico','nombre':historical}
            if historical and not historical_id:
                options['__historical__']={'id':'__historical__','codigo':'Histórico','nombre':historical}
            if approved or historical:
                ids=list(options)
                chosen_id=st.selectbox('Servicio PMO aprobado · Paso 04 *',ids,
                    index=ids.index(historical_id) if historical_id in ids else (ids.index('__historical__') if historical and '__historical__' in ids else 0),
                    format_func=lambda k:f"{options[k]['codigo']} · {options[k]['nombre']}",
                    help='Solo se ofrecen fichas aprobadas del Paso 04. Las referencias históricas se conservan al editar.')
                service=options[chosen_id]['nombre']
                service_id=historical_id if chosen_id=='__historical__' else chosen_id
            else:
                st.warning('No hay servicios aprobados en el Paso 04. Aprueba una ficha antes de registrar nuevos compromisos.')
                service='';service_id=''
            client=choose_client(st,'Cliente beneficiario · Paso 01 *',original.get('cliente',''),key=f'p9_benefit_client_{key or "new"}',optional=False)[0]
            need=st.text_area('Necesidad identificada *',value=original.get('necesidad',''),height=76)
            deliverable=st.text_input('Entregable',value=original.get('entregable',''))
            benefit=st.text_area('Beneficio comprometido *',value=original.get('beneficio',''),height=76)
            metric=st.text_input('Indicador principal de beneficio',value=original.get('indicador',''),disabled=has_indicator)
            unit=st.text_input('Unidad',value=original.get('unidad',''),disabled=has_indicator)
        with b:
            direction=st.selectbox('Sentido esperado',s.DIRECTIONS,index=s.DIRECTIONS.index(original.get('sentido','Disminuir')) if original.get('sentido') in s.DIRECTIONS else 0,disabled=has_indicator)
            baseline=st.text_input('Línea base',value=str(original['linea_base']) if original.get('linea_base') is not None else '',disabled=has_indicator)
            target=st.text_input('Meta',value=str(original['meta']) if original.get('meta') is not None else '',disabled=has_indicator)
            source=st.text_area('Fuente y método de medición',value=original.get('fuente',''),height=80,disabled=has_indicator)
            owner=staff_picker('Responsable',value=original.get('responsable',''),disabled=has_indicator)
            impact=st.selectbox('Tipo de impacto',s.IMPACTS,index=s.IMPACTS.index(original.get('tipo_impacto','Eficiencia')) if original.get('tipo_impacto') in s.IMPACTS else 0)
            due=st.date_input('Fecha objetivo',value=date.fromisoformat(original['fecha_meta']) if original.get('fecha_meta') else date.today(), format='YYYY/MM/DD')
        st.markdown('**Cuantificación económica opcional**')
        st.caption('Los ahorros no se infieren de horas liberadas ni de cantidad de tickets.')
        u,v=st.columns(2)
        with u:
            money=st.text_input('Monto económico bruto observado (COP)',value=str(original['monto_bruto']) if original.get('monto_bruto') is not None else '')
            key_e=st.text_input('Clave económica única',value=original.get('clave_economica',''))
        with v:
            attribution=st.number_input('Contribución atribuible a la PMO (%)',min_value=0,max_value=100,value=int(original['atribucion']) if original.get('atribucion') is not None else 0)
            fin_source=st.text_input('Fuente de cuantificación económica',value=original.get('fuente_economica',''))
        notes=st.text_area('Observaciones y supuestos',value=original.get('observaciones',''))
        save=st.form_submit_button('Guardar compromiso',type='primary')
    if save:
        data={**original,'servicio':service,'servicio_id':service_id,'cliente':client,'necesidad':need,'entregable':deliverable,'beneficio':benefit,
              'indicador':metric,'unidad':unit,'sentido':direction,'linea_base':baseline,'meta':target,'fuente':source,
              'responsable':owner,'tipo_impacto':impact,'fecha_meta':due.isoformat(),'monto_bruto':money,
              'atribucion':attribution,'clave_economica':key_e,'fuente_economica':fin_source,'observaciones':notes}
        if run(lambda:s.save_benefit(data,key),'Compromiso guardado en SQLite'):st.rerun()

@st.dialog('Indicador principal de beneficio',width='large')
def indicator_form(key):
    benefit=s.benefit(key)
    if not benefit:
        st.error('Primero guarda el compromiso de beneficio.');return
    definition=s.benefit_indicator(key) or {}
    st.caption(f"Compromiso: {benefit['beneficio']} · {benefit['servicio']}")
    st.info('El indicador define cómo medir. No genera resultados ni verifica el beneficio de manera automática.')
    with st.form('p9_indicator_form'):
        a,b=st.columns(2)
        with a:
            name=st.text_input('Nombre del indicador *',value=benefit['indicador'])
            objective=st.text_area('Objetivo del indicador',value=definition.get('objetivo',''))
            ftype=st.selectbox('Tipo de fórmula',s.FORMULA_TYPES,index=s.FORMULA_TYPES.index(definition.get('tipo_formula')) if definition.get('tipo_formula') in s.FORMULA_TYPES else 0)
            formula=st.text_area('Expresión matemática / regla de cálculo',value=definition.get('expresion',''),help='Ejemplo: (proyectos completos / proyectos revisados) × 100. No se ejecuta código ingresado.')
            unit=st.text_input('Unidad de medida',value=benefit['unidad'],placeholder='% / días / entregables')
            direction=st.selectbox('Sentido favorable',s.DIRECTIONS,index=s.DIRECTIONS.index(benefit['sentido']) if benefit['sentido'] in s.DIRECTIONS else 0)
        with b:
            base=st.text_input('Línea base',value=str(benefit['linea_base']) if benefit['linea_base'] is not None else '')
            target=st.text_input('Meta',value=str(benefit['meta']) if benefit['meta'] is not None else '')
            frequency=st.selectbox('Frecuencia de medición',s.MEASUREMENT_FREQUENCIES,index=s.MEASUREMENT_FREQUENCIES.index(definition.get('frecuencia')) if definition.get('frecuencia') in s.MEASUREMENT_FREQUENCIES else 2)
            method=st.selectbox('Método de captura',s.CAPTURE_METHODS,index=s.CAPTURE_METHODS.index(definition.get('metodo_captura')) if definition.get('metodo_captura') in s.CAPTURE_METHODS else 0)
            source=st.text_area('Fuente de datos y método',value=benefit['fuente'])
            owner=staff_picker('Responsable de medición',value=benefit['responsable'])
            state=st.selectbox('Estado de definición',['Borrador','Definido'],index=1 if definition.get('estado')=='Definido' else 0)
        if st.form_submit_button('Guardar indicador',type='primary'):
            if run(lambda:s.save_benefit_indicator(key,objective,ftype,formula,frequency,method,name,unit,direction,base,target,source,owner,state),'Indicador guardado y vinculado al compromiso'):st.rerun()

@st.dialog('Registrar medición de impacto',width='large')
def measure_form(key):
    b=s.benefit(key)
    if not b:st.error('Beneficio inexistente');return
    st.write('**'+b['indicador']+'** — '+b['beneficio'])
    st.caption('La nueva medición se conserva en el historial y requiere nueva validación formal.')
    with st.form('p9_measure'):
        a,c=st.columns(2)
        with a:actual=st.text_input('Resultado observado *');when=st.date_input('Fecha de medición',value=date.today(), format='YYYY/MM/DD')
        with c:source=st.text_input('Fuente verificable *',value=b['fuente']);owner=staff_picker('Responsable *',value=b['responsable'])
        evidence=st.text_area('Evidencia o referencia de medición');notes=st.text_area('Observaciones')
        ok=st.form_submit_button('Guardar medición',type='primary')
    if ok:
        if run(lambda:s.add_measurement(key,actual,when.isoformat(),source,owner,evidence,notes),'Medición registrada'):st.rerun()

@st.dialog('Verificación formal del beneficio',width='large')
def verify_form(key):
    b=s.benefit(key);m=s.latest(key)
    if not b:return
    st.write('**'+b['beneficio']+'**')
    if not m:st.warning('No puede verificarse: falta registrar una medición.');return
    result=s.calc(b,m)
    if not result:st.warning('Complete primero línea base, meta, indicador y fuente de medición.');return
    st.info(f"Resultado observado: {fmt(m['valor'])} {b['unidad']} · Avance: {fmt(result['avance'],'%')} · Meta {'alcanzada' if result['cumple_meta'] else 'pendiente'}.")
    with st.form('p9_verify'):
        validator=st.text_input('Responsable que verifica *',value=b.get('validador',''))
        day=st.date_input('Fecha de validación',value=date.today(),min_value=date.fromisoformat(m['fecha']), format='YYYY/MM/DD')
        evidence=st.text_area('Evidencia de realización / acta *',value=b.get('evidencia_validacion',''))
        ok=st.form_submit_button('Validar beneficio',type='primary')
    if ok:
        if run(lambda:s.verify(key,validator,day.isoformat(),evidence),'Beneficio verificado con evidencia'):st.rerun()

@st.dialog('Registrar caso de valor',width='large')
def case_form():
    with st.form('p9_case_form'):
        title=st.text_input('Título del caso *')
        selected=_select_benefit('Beneficio vinculado',key='p9_case_benefit')
        summary=st.text_area('Situación, intervención y valor observado *')
        a,b=st.columns(2)
        with a:owner=staff_picker('Responsable *')
        with b:when=st.date_input('Fecha de registro',value=date.today(), format='YYYY/MM/DD')
        source=st.text_input('Fuente o referencia de evidencia')
        ok=st.form_submit_button('Guardar caso',type='primary')
    if ok:
        if run(lambda:s.add_case(title,summary,when.isoformat(),owner,selected['id'] if selected else None,source),'Caso de valor registrado'):st.rerun()

def import_panel():
    with st.expander('Importar compromisos del Paso 3 o de Excel / JSON',expanded=False):
        a,b=st.columns(2)
        with a:
            demo=st.checkbox('Permitir registros ficticios de laboratorio',value=False,key='p9_include_demo')
            if st.button('Consultar e importar Paso 3 desde SQLite',type='primary',use_container_width=True):
                result=run(lambda:s.import_from_step3(include_demo=demo),'Transferencia desde Paso 3 revisada')
                if result:st.info(f"{result['agregados']} nuevos · {result['omitidos']} omitidos · {result.get('sin_solucion_vinculada',0)} sin solución relacionada");st.rerun()
        with b:
            st.download_button('Descargar plantilla Excel',s.template_xlsx(),file_name='PMO_CENS_PASO9_PLANTILLA_BENEFICIOS.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True)
            upl=st.file_uploader('Archivo Excel, CSV o JSON',type=['xlsx','csv','json'],key='p9_import_file')
            if upl and st.button('Validar e importar archivo',use_container_width=True):
                try:
                    if upl.name.lower().endswith('.json'):result=s.import_json(json.loads(upl.getvalue()),source=upl.name,include_demo=demo)
                    else:result=s.import_records(s.parse_excel(upl.getvalue(),upl.name),source=upl.name,include_demo=demo)
                    st.success(f"Importación: {result['agregados']} nuevos; {result['omitidos']} omitidos.");st.rerun()
                except (s.ValidationError,ValueError,KeyError) as ex:st.error(str(ex))

def benefits_page():
    head(1,'Matriz de beneficios y compromisos','Recupera el valor prometido en el Paso 3 y prepara su medición verificable.')
    notice();import_panel()
    a,b,c=st.columns([1,1,1])
    with a:
        if st.button('＋ Nuevo beneficio',type='primary'):benefit_form()
    with b:st.download_button('↓ Exportar Excel',s.export_xlsx(),file_name='CENS_Paso9_Beneficios.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    with c:st.download_button('↓ Exportar CSV',s.export_csv(),file_name='CENS_Paso9_Beneficios.csv',mime='text/csv')
    m=s.overview();kpis([('Beneficios registrados',str(m['total']),'Compromisos documentados'),('Con alguna medición',str(m['medidos']),'No son necesariamente verificados'),('Beneficios verificados',str(m['verificados']),'Con evidencia y responsable'),('Cobertura de medición',fmt(m['cobertura'],'%'),'Respecto a compromisos')])
    data=s.benefits()
    if not data:st.info('Aún no hay beneficios. Importa información del Paso 3 o registra un compromiso.');return
    st.caption(f"Indicadores principales estructurados: {len(s.indicators())} · Compromisos registrados: {len(data)}. Registrar una definición no equivale a medir un resultado.")
    with st.expander('Catálogo de indicadores de beneficio · definiciones y trazabilidad',expanded=False):
        catalog={x['beneficio_id']:x for x in s.indicators()}
        table=[{'Servicio':x['servicio'],'Beneficio':x['beneficio'][:85],
          'Código':catalog[x['id']]['codigo'] if x['id'] in catalog else '—',
          'Indicador principal':x['indicador'] or 'Pendiente',
          'Tipo de fórmula':catalog[x['id']]['tipo_formula'] if x['id'] in catalog else '—',
          'Frecuencia':catalog[x['id']]['frecuencia'] if x['id'] in catalog else '—',
          'Estado':catalog[x['id']]['estado'] if x['id'] in catalog else 'Sin ficha estructurada'} for x in data]
        st.dataframe(pd.DataFrame(table),hide_index=True,use_container_width=True)
        st.caption('Una definición por compromiso. Las mediciones y verificaciones se mantienen separadas; se conservan los textos anteriores.')
    a,b=st.columns([2,1])
    with a:query=st.text_input('Buscar servicio, necesidad o beneficio',placeholder='Buscar...')
    with b:status=st.selectbox('Filtrar estado',['Todos','Pendiente','En medición','Validado'])
    visible=[v for v in data if (status=='Todos' or v['estado']==status) and query.casefold() in (v['servicio']+v['cliente']+v['necesidad']+v['beneficio']).casefold()]
    if not visible:st.info('Sin registros con esos filtros.');return
    st.dataframe(pd.DataFrame([{'Servicio':x['servicio'],'Cliente':x['cliente'],'Necesidad':x['necesidad'],'Beneficio':x['beneficio'],'Indicador':x['indicador'],'Base':x['linea_base'],'Meta':x['meta'],'Estado':x['estado'],'Origen Paso 3':x['origen_p3']} for x in visible]),hide_index=True,use_container_width=True)
    with st.container(border=True):
        b=_select_benefit('Abrir ficha de compromiso',key='p9_edit_choose',records=visible)
        if b:
            col1,col2,col3,col4=st.columns(4)
            with col1:
                if st.button('Editar compromiso',use_container_width=True):benefit_form(b['id'])
            with col2:
                if st.button('Definir indicador',use_container_width=True):indicator_form(b['id'])
            with col3:
                if st.button('Registrar medición',use_container_width=True):measure_form(b['id'])
            with col4:
                if st.button('Verificar beneficio',use_container_width=True):verify_form(b['id'])
            with st.expander('Eliminar este beneficio'):
                st.warning('Se eliminarán también sus mediciones del Paso 9, sin afectar el Paso 3.')
                if st.button('Confirmar eliminación',key='p9_confirm_delete'):
                    if run(lambda:s.delete_benefit(b['id']),'Beneficio eliminado'):st.rerun()
    if any(v['es_demo'] for v in data):st.warning('Hay compromisos ficticios en esta base; no constituyen resultados reales de CENS.')

def impact_page():
    head(2,'Medición de impacto','Compara la línea base con los resultados observados; no atribuye ahorros sin evidencia.')
    notice();m=s.overview()
    from .alpha05_value_ui import render_benefits
    render_benefits()
    kpis([('Resultados medidos',str(m['medidos']),'Con registro de resultados'),('Comparables con línea base',str(m['comparables']),'Base y meta disponibles'),('Beneficios verificados',str(m['verificados']),'Con validación formal'),('Valor económico atribuible validado',fmt(m['valor_neto'],' COP',0) if m['conceptos_economicos'] else '—','Sin doble conteo')])
    main_col,side_col=st.columns([2,1])
    with main_col:
        with st.container(border=True):
            st.subheader('Comparación de resultados')
            dim=st.selectbox('Dimensión de impacto',['Todas',*s.IMPACTS])
            details=[x for x in m['detalle'] if dim=='Todas' or x['beneficio']['tipo_impacto']==dim]
            df=[{'Servicio':x['beneficio']['servicio'],'Indicador':x['beneficio']['indicador'],'Línea base':x['beneficio']['linea_base'],'Meta':x['beneficio']['meta'],'Último resultado':x['medicion']['valor'] if x['medicion'] else None,'Variación favorable (%)':round(x['calculo']['variacion_favorable'],1) if x['calculo'] and x['calculo']['variacion_favorable'] is not None else None,'Avance (%)':round(x['calculo']['avance'],1) if x['calculo'] else None,'Meta alcanzada':'Sí' if x['calculo'] and x['calculo']['cumple_meta'] else 'No comprobada','Verificado':'Sí' if x['verificado'] else 'No'} for x in details]
            if df:st.dataframe(pd.DataFrame(df),hide_index=True,use_container_width=True)
            else:st.info('Sin beneficios comparables.')
        with st.container(border=True):
            st.subheader('Evolución de indicadores')
            selected_benefit=_select_benefit('Selecciona un beneficio',key='p9_impact_b')
            if selected_benefit:
                ms=s.measurements(selected_benefit['id'])
                if ms:
                    st.line_chart(pd.DataFrame([{'Fecha':x['fecha'],'Resultado':x['valor']} for x in ms]).set_index('Fecha'))
                    st.dataframe(pd.DataFrame(ms)[['fecha','valor','fuente','responsable','evidencia']],hide_index=True,use_container_width=True)
                else:st.caption('No hay mediciones todavía.')
                if st.button('＋ Registrar resultado',type='primary'):measure_form(selected_benefit['id'])
    with side_col:
        with st.container(border=True):
            st.subheader('Control económico')
            st.metric('Conceptos verificados únicos',m['conceptos_economicos'])
            st.metric('Contribución económica atribuible',fmt(m['valor_neto'],' COP',0) if m['conceptos_economicos'] else 'Sin datos')
            st.metric('Claves duplicadas excluidas',m['duplicados_excluidos'])
            st.caption('El valor se reconoce solo con monto observado, fuente, atribución y validación formal. La unidad de un indicador de tiempo no se transforma por sí sola en COP.')
    st.download_button('↓ Descargar mediciones CSV',s.export_csv(),file_name='CENS_Paso9_Mediciones.csv',mime='text/csv')

def realization_page():
    head(3,'Realización de beneficios','Validación expresa del resultado frente al compromiso y registro de casos de valor.')
    notice();m=s.overview()
    kpis([('Compromisos',str(m['total']),'Beneficios originales'),('Resultados verificados',str(m['verificados']),'Con evidencia y responsable'),('Metas alcanzadas',str(m['metas_cumplidas']),f"De {m['verificados']} beneficios verificados")])
    a,b=st.columns([1.2,1])
    with a:
        with st.container(border=True):
            st.subheader('Estado de realización')
            for x in m['detalle']:
                be=x['beneficio'];calc=x['calculo'];st.markdown(f"**{esc(be['beneficio'])}** · {esc(be['servicio'])}")
                st.caption(('Verificado' if x['verificado'] else 'En medición' if x['medicion'] else 'Pendiente')+' · '+ ('Meta alcanzada' if calc and calc['cumple_meta'] else 'Meta pendiente o sin datos'))
                cols=st.columns([1,1])
                with cols[0]:
                    if st.button('Medir',key='p9_m_'+be['id']):measure_form(be['id'])
                with cols[1]:
                    if st.button('Verificar',key='p9_v_'+be['id']):verify_form(be['id'])
                if x['verificado']:
                    with st.expander('Reabrir verificación para nueva revisión'):
                        st.warning('La verificación anterior dejará de estar vigente. Se conservarán las mediciones.')
                        if st.button('Retirar validación',key='p9_i_'+be['id']):
                            if run(lambda:s.invalidate(be['id']),'Validación retirada'):st.rerun()
                st.divider()
    with b:
        with st.container(border=True):
            st.subheader('Casos de valor')
            if st.button('＋ Documentar caso'):case_form()
            if s.cases():st.dataframe(pd.DataFrame([{'Título':x['titulo'],'Fecha':x['fecha'],'Responsable':x['responsable'],'Resumen':x['resumen']} for x in s.cases()]),hide_index=True,use_container_width=True)
            else:st.caption('Sin casos documentados.')

def _bar_pairs(pairs,heading):
    st.subheader(heading)
    if not pairs:st.caption('Sin datos para mostrar');return
    for label,n in pairs:
        cols=st.columns([2,4,1],vertical_alignment='center')
        with cols[0]:st.caption(label)
        with cols[1]:st.progress(min(1.0,n/max(1,max(v for _,v in pairs))))
        with cols[2]:st.caption(str(n))

def dashboard_page():
    head(4,'Tablero ejecutivo de valor','Síntesis de compromisos, valor comprobado, cumplimiento de metas y aportes por servicio.')
    from .value_info_panel import info_panel
    info_panel('Valor comprobado y trazabilidad', 'Solo los beneficios medidos, sustentados y validados se incluyen como resultados verificados. Los tickets, ANS y satisfacción corresponden a contexto operativo.')
    notice();m=s.overview()
    kpis([('Beneficios comprometidos',str(m['total']),'Registrados desde Paso 3 o ficha'),('Beneficios verificados',str(m['verificados']),'Medición y validación documental'),('Metas alcanzadas',fmt(m['cumplimiento'],'%') if m['cumplimiento'] is not None else '—','Porcentaje de compromisos verificados que cumplen meta'),('Valor económico atribuible',fmt(m['valor_neto'],' COP',0) if m['conceptos_economicos'] else '—','Bruto atribuible documentado; sin descontar costos')])
    a,b=st.columns(2)
    with a:
        with st.container(border=True):
            summary=collections.defaultdict(lambda:[0,0])
            for x in m['detalle']:
                key=x['beneficio']['servicio'];summary[key][0]+=1;summary[key][1]+=int(x['verificado'])
            _bar_pairs([(f'{name}: {v[1]}/{v[0]}',v[1]) for name,v in summary.items()],'Beneficios verificados por servicio')
            money_by=collections.defaultdict(float)
            for record in m['detalle_economico']:
                money_by[record['servicio']]+=record['valor_atribuible']
            if m['duplicados_excluidos']:
                st.warning(f"Se excluyeron {m['duplicados_excluidos']} conceptos económicos duplicados. Verifica las claves de atribución antes de reportar.")
            if money_by:
                st.caption('Montos atribuibles documentados (COP). No representa necesariamente valor neto.')
                chart=pd.DataFrame([{'Servicio':k,'COP':v} for k,v in money_by.items()]).set_index('Servicio')
                st.bar_chart(chart,use_container_width=True)
            else:st.caption('Sin montos monetarios verificables. No se atribuyen variaciones de CAPEX sin fuente y validación.')
    with b:
        with st.container(border=True):
            by=collections.Counter(x['beneficio']['tipo_impacto'] for x in m['detalle'] if x['verificado'])
            _bar_pairs(list(by.items()),'Beneficios por tipo de impacto')
            if by:
                st.bar_chart(pd.DataFrame([{'Impacto':k,'Verificados':v} for k,v in by.items()]).set_index('Impacto'),use_container_width=True)
    a,b=st.columns(2)
    with a:
        with st.container(border=True):
            dated=collections.Counter(x['beneficio']['fecha_validacion'][:7] for x in m['detalle'] if x['verificado'])
            _bar_pairs(sorted(dated.items()),'Verificaciones por mes')
            if dated:
                running=0;points=[]
                for period,count in sorted(dated.items()):
                    running+=count;points.append({'Mes':period,'Acumulado verificado':running})
                st.line_chart(pd.DataFrame(points).set_index('Mes'),use_container_width=True)
    with b:
        with st.container(border=True):
            st.subheader('Hallazgos de pasos anteriores')
            context_cols=collections.Counter(x['tipo'] for x in s.context())
            st.metric('Tickets referenciales',context_cols.get('ticket',0));st.metric('Hallazgos de monitoreo',context_cols.get('hallazgo',0))
            if st.button('Importar contexto de los Pasos 6 y 7'):
                r=run(s.import_context_from_steps,'Referencias actualizadas')
                if r:st.rerun()
            context_upload=st.file_uploader('O importar expediente JSON Paso 6 / 7',type=['json'],key='p9_context_file')
            if context_upload and st.button('Importar contexto JSON'):
                if run(lambda:s.import_context_json(json.loads(context_upload.getvalue())),'Contexto guardado'):st.rerun()
            st.caption('Tickets, cumplimiento de ANS, CSAT y NPS solo aportan contexto; nunca se contabilizan como beneficios sin medición y validación.')
    with st.container(border=True):
        st.subheader('Lectura ejecutiva y seguimiento')
        st.caption('El tablero refleja el estado vigente; las fechas del formulario documentan el periodo del informe y no reconstruyen una fotografía histórica congelada.')
        if not m['total']:st.info('La lectura ejecutiva se genera cuando hay compromisos de beneficio registrados.')
        else:st.write(f"La PMO registra **{m['total']} compromisos**, {m['medidos']} con medición y {m['verificados']} verificados. De los verificados, {m['metas_cumplidas']} alcanzaron su meta. El valor económico atribuible documentado es **{fmt(m['valor_neto'],' COP',0) if m['conceptos_economicos'] else 'no disponible'}**.")
        conf=s.report_config()
        with st.form('p9_report_conf'):
            owner=staff_picker('Responsable del informe',value=conf['responsable'])
            a,b=st.columns(2)
            with a:from_date=iso_date_input('Inicio del periodo',conf['fecha_desde'])
            with b:to_date=iso_date_input('Fecha de corte',conf['fecha_hasta'])
            notes=st.text_area('Interpretación ejecutiva, límites de atribución, decisiones y compromisos',value=conf['observaciones'],help='Documentar: 1) valor verificado y fuentes, 2) supuestos, costos y límites de atribución, 3) decisiones solicitadas y responsables.')
            if st.form_submit_button('Guardar lectura ejecutiva'):
                if run(lambda:s.save_report(owner,from_date,to_date,notes),'Configuración de informe guardada'):st.rerun()
        c1,c2,c3=st.columns(3)
        with c1:st.download_button('↓ Informe ejecutivo HTML',executive_html(m,owner,notes).encode('utf-8'),file_name='CENS_Paso9_Informe.html',mime='text/html')
        with c2:st.download_button('↓ Reporte Excel',s.export_xlsx(),file_name='CENS_Paso9_Reporte.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        with c3:st.download_button('↓ Expediente Paso 10',jb(s.export_step10()),file_name='CENS_Paso9_Expediente_Paso10.json',mime='application/json')
        st.caption('Abre el HTML en el navegador y utiliza Imprimir → Guardar como PDF.')

def executive_html(m,owner,notes):
    content=''.join(f"<tr><td>{esc(x['beneficio']['servicio'])}</td><td>{esc(x['beneficio']['beneficio'])}</td><td>{'Sí' if x['verificado'] else 'No'}</td><td>{fmt(x['calculo']['avance'],'%') if x['calculo'] else '—'}</td></tr>" for x in m['detalle'])
    return '<!doctype html><html lang="es-CO"><meta charset="utf-8"><title>PMO CENS · Informe de valor</title><style>body{font:14px Segoe UI,sans-serif;color:#10374B;max-width:1000px;margin:30px auto}h1{border-bottom:3px solid #0B9A9F;padding-bottom:13px}table{border-collapse:collapse;width:100%}td,th{padding:10px;border-bottom:1px solid #DDE5ED;text-align:left}th{background:#F4F7FA}@media print{body{margin:1cm}}</style><h1>PMO FLYWHEEL CENS · Entrega de valor</h1><p>Responsable: '+esc(owner)+'</p><p>Compromisos: '+str(m['total'])+' · Medidos: '+str(m['medidos'])+' · Verificados: '+str(m['verificados'])+' · Metas alcanzadas: '+str(m['metas_cumplidas'])+'</p><p>Valor económico atribuible: '+(fmt(m['valor_neto'],' COP',0) if m['conceptos_economicos'] else 'Sin datos validados')+'</p><h2>Resultados</h2><table><tr><th>Servicio</th><th>Beneficio</th><th>Verificado</th><th>Avance</th></tr>'+content+'</table><h2>Lectura ejecutiva</h2><p>'+esc(notes).replace('\n','<br>')+'</p><p>Las medidas de operación y satisfacción no sustituyen la validación de beneficios.</p></html>'

def assessment_page():
    head(5,'Autoevaluación metodológica PMI','25 preguntas distribuidas en cinco dimensiones, escala 1–5 e historial independiente.')
    evaluations=s.evaluations()
    current=next((x for x in evaluations if x['estado']=='Borrador'),None)
    if not current:
        st.info('Las evaluaciones archivadas son inmutables. Crea una nueva para continuar el ciclo.')
        owner=st.text_input('Responsable de la nueva evaluación',key='p9_eval_new_owner')
        if st.button('＋ Nueva autoevaluación PMI',type='primary'):
            if run(lambda:s.create_evaluation(owner),'Autoevaluación iniciada'):st.rerun()
    else:
        d=s.assessment(current['id']);kpis([('Preguntas respondidas',f"{d['respondidas']}/25",'Cinco dimensiones'),('Puntuación',str(d['puntaje']) if d['puntaje'] is not None else '—','Máximo 125'),('Clasificación',d['clasificacion'] or 'Pendiente','Solo con 25 respuestas'),('Historial',str(sum(x['estado']=='Archivada' for x in evaluations)),'Evaluaciones archivadas')])
        st.subheader('Perfil por dimensión')
        c=st.columns(5)
        for i,col in enumerate(c):
            with col:st.metric(f'D{i+1}',f"{d['dimensiones'][i]}/25" if d['dimensiones'][i] is not None else '—')
        dims=[x[0] for x in s.DIMENSIONS]
        with st.expander('Rangos y metodología'):
            st.write('Excelente 113–125 · Bien 98–112 · Promedio 77–97 · Pobre 51–76 · Crítico 25–50. El instrumento no califica satisfacción del cliente.')
        active=st.selectbox('Dimensión de evaluación',range(5),format_func=lambda i:f'Dimensión {i+1}: {dims[i]}')
        with st.form(f'p9_eval_dim_{active}'):
            values=[]
            for n in range(active*5+1,active*5+6):
                past=d['respuestas'].get(n,{})
                st.markdown('**'+str(n)+'. '+s.QUESTIONS[n-1]+'**')
                raw=st.radio('Valoración',options=[0,1,2,3,4,5],index=int(past.get('valor',0)),horizontal=True,format_func=lambda x:'Sin responder' if x==0 else str(x),key=f'p9_rate_{current["id"]}_{n}')
                a,b=st.columns(2)
                with a:obs=st.text_input('Observación',value=past.get('observacion',''),key=f'p9_obs_{current["id"]}_{n}')
                with b:ev=st.text_input('Evidencia',value=past.get('evidencia',''),key=f'p9_ev_{current["id"]}_{n}')
                values.append((n,raw or None,obs,ev))
            if st.form_submit_button('Guardar las cinco respuestas de esta dimensión',type='primary'):
                good=True
                for n,v,o,e in values:
                    if not run(lambda n=n,v=v,o=o,e=e:s.save_answer(current['id'],n,v,o,e),'Respuesta actualizada'):good=False
                if good:st.rerun()
        if d['respondidas']==25:
            st.success(f"Evaluación completa: {d['puntaje']}/125 · {d['clasificacion']}.")
            if st.button('Archivar corte metodológico PMI',type='primary'):
                if run(lambda:s.archive_evaluation(current['id']),'Evaluación archivada'):st.rerun()
    archived=[x for x in s.evaluations() if x['estado']=='Archivada']
    if archived:
        st.subheader('Historial de evaluaciones')
        st.dataframe(pd.DataFrame([{'Versión':x['version'],'Responsable':x['responsable'],'Puntaje':x['puntaje'],'Clasificación':x['clasificacion'],'Fecha':x['archivado_en']} for x in archived]),hide_index=True,use_container_width=True)
        chosen=st.selectbox('Exportar evaluación archivada',[x['id'] for x in archived],format_func=lambda k:f"Versión {next(x['version'] for x in archived if x['id']==k)}")
        st.download_button('↓ Respuestas y evidencias JSON',jb(s.assessment(chosen)),file_name='CENS_Paso9_Evaluacion_PMI.json',mime='application/json')


def backup_panel():
    with st.expander('Respaldo y restauración del Paso 9'):
        st.download_button('↓ Descargar respaldo completo JSON',jb(s.backup()),file_name='PMO_CENS_PASO9_RESPALDO.json',mime='application/json')
        uploaded=st.file_uploader('Restaurar respaldo JSON exclusivo del Paso 9',type='json',key='p9_restore_file')
        confirm=st.checkbox('Confirmo que deseo reemplazar únicamente los registros del Paso 9',key='p9_restore_confirm')
        if uploaded and st.button('Restaurar Paso 9',disabled=not confirm):
            if run(lambda:s.restore_backup(json.loads(uploaded.getvalue()),confirm),'Registros del Paso 9 restaurados'):st.rerun()

def page(name):
    if name==NAV[0]:benefits_page()
    elif name==NAV[1]:impact_page()
    elif name==NAV[2]:realization_page()
    elif name==NAV[3]:dashboard_page()
    elif name==NAV[4]:assessment_page()
    else:st.error('Sección desconocida')
    backup_panel()
