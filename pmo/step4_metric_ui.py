"""Ficha de definición, aprobación y captura de resultados, V0.39.14.
Un solo punto de entrada por servicio; controles nativos Streamlit."""
from __future__ import annotations
from datetime import date
from pathlib import Path
import html
import streamlit as st
from .staff_picker import staff_picker
from . import step4 as s
from . import step4_metrics as m
from .public_codes import code as public_code


def _text_option(label, options, current='', key=None, help=None):
    vals=list(options)
    if current and current not in vals:vals.append(current)
    return st.selectbox(label,vals,index=vals.index(current) if current in vals else 0,key=key,help=help)


def _number(value):
    try:return float(str(value).replace(',','.')) if str(value or '').strip() else None
    except (TypeError,ValueError):return None


def _suggest_formula(row):
    unit=str(row.get('unidad') or '').lower()
    if '%' in unit:return 'Porcentaje / Tasa'
    if 'día' in unit or 'hora' in unit:return 'Tiempo medio / Duración'
    if 'entregable' in unit:return 'Conteo absoluto'
    return 'Valor directo'


def _make_definition(sid,record,entry):
    """Devuelve valores del formulario de definición; no importa ni mide automáticamente."""
    kind=entry.get('categoria') if entry else (record or {}).get('tipo','Salida')
    formula_type=(entry or {}).get('tipo_formula') or _suggest_formula(record or {})
    rag=(entry or {}).get('rag') or {}
    with st.form('p4_metric_definition_form'):
        st.markdown('**1 · Identificación y tipología**')
        a,b=st.columns([1,1])
        with a:
            st.text_input('Servicio',value=public_code('servicio',sid),disabled=True)
            st.text_input('Código único de la métrica',value=entry['codigo'] if entry else 'Se asignará al guardar',disabled=True)
            name=st.text_input('Nombre del indicador *',value=(record or {}).get('nombre',''))
        with b:
            category=_text_option('Categoría',m.CATEGORIES,kind)
            objective=st.text_area('Objetivo',value=(entry or {}).get('objetivo') or '',height=70)

        st.markdown('**2 · Lógica matemática y reglas de negocio**')
        a,b=st.columns(2)
        with a:formula_kind=_text_option('Tipo de fórmula',m.FORMULAS,formula_type)
        with b:unit=_text_option('Unidad de medida',m.UNITS,(record or {}).get('unidad') or '%')
        formula=st.text_area('Expresión visible / descripción matemática',value=(record or {}).get('formula') or '',height=80)
        direction=_text_option('Sentido favorable',m.DIRECTIONS,'rango' if 'low' in rag else (record or {}).get('sentido','mayor'))
        st.caption('Las fórmulas se calculan con los operandos de captura; el texto es la definición auditada, no se ejecuta como código.')

        st.markdown('**3 · Línea base, meta propuesta y umbrales RAG**')
        a,b=st.columns(2)
        with a:baseline=st.number_input('Línea base verificada (opcional)',value=_number((record or {}).get('linea_base')),step=0.1,placeholder='Sin línea base verificada')
        with b:target=st.number_input('Meta (opcional; no supone aprobación)',value=_number((record or {}).get('meta')),step=0.1,placeholder='Sin meta aprobada')
        use_rag=st.checkbox('Configurar límites RAG',value=bool(rag))
        thresholds={}
        if use_rag:
            if direction=='rango':
                x,y,z=st.columns(3)
                with x:lo=st.number_input('Verde desde',value=rag.get('low'),step=0.1)
                with y:hi=st.number_input('Verde hasta',value=rag.get('high'),step=0.1)
                with z:margin=st.number_input('Margen ámbar',value=rag.get('margin'),min_value=0.0,step=0.1)
                if None not in (lo,hi,margin):thresholds={'low':float(lo),'high':float(hi),'margin':float(margin)}
            else:
                a,b=st.columns(2)
                with a:green=st.number_input('Umbral verde ('+('≥' if direction=='mayor' else '≤')+')',value=rag.get('green'),step=0.1)
                with b:amber=st.number_input('Umbral ámbar ('+('≥' if direction=='mayor' else '≤')+')',value=rag.get('amber'),step=0.1)
                if green is not None and amber is not None:thresholds={'green':float(green),'amber':float(amber)}
            st.caption('Rojo se obtiene fuera de los límites verde y ámbar. No se asigna a mediciones pasadas sin una aprobación vigente.')
        st.markdown('**4 · Gobernanza, frecuencia y fuente**')
        a,b=st.columns(2)
        with a:
            frequency=_text_option('Frecuencia',m.FREQUENCIES,(record or {}).get('frecuencia') or 'Mensual')
            source_type=_text_option('Fuente de datos · categoría',m.SOURCES,(entry or {}).get('fuente_tipo') or m.SOURCES[0])
            method=_text_option('Método de captura',m.METHODS,(entry or {}).get('metodo_captura') or m.METHODS[2])
        with b:
            role=_text_option('Rol responsable',m.ROLES,(entry or {}).get('rol_responsable') or m.ROLES[0])
            owner=staff_picker('Responsable asignado (opcional)',value=(record or {}).get('responsable') or '')
            source=st.text_input('Repositorio / fuente específica',value=(record or {}).get('fuente') or '')
        st.markdown('**5 · Evidencia y validación**')
        a,b=st.columns(2)
        with a:
            requires=_text_option('Requiere validación del cliente',('Sí','No'),(entry or {}).get('requiere_validacion') or 'No')
            validator=_text_option('Rol validador',('Por definir',*m.VALIDATORS),(entry or {}).get('rol_validador') or 'Por definir')
        with b:
            evidence=_text_option('Tipo de evidencia requerida',('Por definir',*m.EVIDENCES),(entry or {}).get('tipo_evidencia') or 'Por definir')
            stage=_text_option('Estado de la definición (no es aprobación)',('Borrador','En revisión'),
                               (entry or {}).get('estado') if (entry or {}).get('estado') in ('Borrador','En revisión') else 'En revisión')
        notes=st.text_area('Origen, supuestos y valores por concertar',value=(entry or {}).get('notas_propuesta') or '',height=90)
        submitted=st.form_submit_button('Guardar ficha de definición',type='primary',use_container_width=True)
        if submitted:
            data={'nombre':name,'categoria':category,'objetivo':objective,'tipo_formula':formula_kind,'formula':formula,
                  'unidad':unit,'sentido':direction,'linea_base':'' if baseline is None else str(baseline),
                  'meta':'' if target is None else str(target),'rag':thresholds,'frecuencia':frequency,
                  'fuente_tipo':source_type,'fuente':source,'metodo_captura':method,'rol_responsable':role,
                  'responsable':owner,'requiere_validacion':requires,'rol_validador':'' if validator=='Por definir' else validator,
                  'tipo_evidencia':'' if evidence=='Por definir' else evidence,'estado':stage,'notas_propuesta':notes}
            try:
                if record:
                    m.save_definition(record['id'],data)
                else:
                    # La inserción solo se conserva si la definición es válida.
                    base_id=s.save_metric({'servicio_id':sid,'nombre':name,'tipo':category if category!='Percepción' else 'Resultado',
                       'formula':formula,'unidad':unit,'linea_base':data['linea_base'],'meta':data['meta'],
                       'sentido':direction if direction!='rango' else 'mayor','frecuencia':frequency,
                       'responsable':owner,'fuente':source})
                    try:m.save_definition(base_id,data)
                    except Exception:
                        s.remove_metric(base_id,'Reversión de ficha incompleta')
                        raise
                st.rerun()
            except Exception as ex:st.error(str(ex))


def _approval_form(record,entry):
    if not record or not entry:return
    if entry['estado']=='Aprobada':
        st.success('Definición aprobada. Cualquier cambio en los compromisos reabre el proceso de revisión.')
        return
    with st.expander('Aprobar definición de la métrica · requiere evidencia',expanded=False):
        st.caption('La aprobación es una decisión registrada. No crea mediciones ni cambia el estado del servicio.')
        approver=st.text_input('Responsable que aprueba',key='p4_met_approver')
        evidence=st.text_input('Acta, expediente o URL de aprobación',key='p4_met_approve_evidence')
        confirm=st.checkbox('Confirmo que existe aprobación documentada',key='p4_met_approve_confirm')
        if st.button('Aprobar definición',disabled=not confirm,key='p4_met_approve_button'):
            try:m.approve_definition(record['id'],approver,evidence);st.rerun()
            except Exception as ex:st.error(str(ex))


def _capture_tab(sid,metrics):
    st.caption('Los resultados se registran por periodo en una tabla independiente; nunca sobrescriben la fórmula ni los cortes anteriores.')
    if not metrics:
        st.info('Primero registra una ficha de indicador.');return
    metric_id=st.selectbox('Indicador a medir',list(x['id'] for x in metrics),
        format_func=lambda ident:next(x['nombre'] for x in metrics if x['id']==ident),key='p4_met_capture_choice')
    item=next(x for x in metrics if x['id']==metric_id)
    entry=m.spec(metric_id)
    if not entry or entry['estado']!='Aprobada':
        st.warning('La definición aún no ha sido aprobada. Los valores del taller no son resultados reales de CENS.')
        return
    kind=entry['tipo_formula'];rag=entry['rag'];direction='rango' if 'low' in rag else item['sentido']
    st.markdown(f'**{m.code_for(metric_id)} · {item["nombre"]}**')
    period=st.text_input('Periodo de corte (AAAA-MM)',value=date.today().strftime('%Y-%m'),key='p4_met_capture_period')
    first=st.number_input('Numerador / dato principal',value=None,step=1.0,key='p4_met_cap_first')
    second=third=None
    if kind in ('Porcentaje / Tasa','Tiempo medio / Duración','Promedio / Puntaje','Net Promoter Score (NPS)'):
        second=st.number_input('Denominador / detractores en NPS',value=None,step=1.0,key='p4_met_cap_second')
    if kind=='Net Promoter Score (NPS)':
        st.caption('Ingrese promotores (9–10), detractores (0–6) y total de respuestas (0–10). NPS no es CSAT de 1–5.')
        third=st.number_input('Total de respuestas',value=None,step=1.0,key='p4_met_cap_third')
    estimate=None
    try:
        estimate=m.calculate(kind,first,second,third)
        semaforo=m.rag_state(estimate,direction,rag)
        st.info(f'Resultado calculado: **{estimate:.2f} {item["unidad"]}** · RAG **{semaforo}** (antes de registrar)')
    except (TypeError,ValueError):
        st.caption('Complete los operandos válidos para calcular el resultado y su semáforo.')
    evidence=st.file_uploader('Evidencia de medición (PDF, imagen, Excel, CSV o TXT)',
         type=['pdf','png','jpg','jpeg','xlsx','csv','txt'],key='p4_met_capture_file')
    url=st.text_input('O URL de evidencia',placeholder='https://...',key='p4_met_capture_url')
    observations=st.text_area('Observaciones / plan de acción (obligatorio si RAG rojo)',key='p4_met_capture_obs')
    prev=[x for x in m.measurement_list(metric_id) if x['periodo']==period]
    reason=st.text_input('Motivo de corrección (si el periodo ya tiene medición)',key='p4_met_capture_reason') if prev else ''
    actor=st.text_input('Responsable del registro',key='p4_met_capture_actor')
    if st.button('Registrar medición con evidencia',type='primary',disabled=estimate is None,key='p4_met_capture_save'):
        try:
            done=m.register_measurement(metric_id,period,first,second,third,evidence_url=url,
                evidence_name=evidence.name if evidence else '',evidence_bytes=evidence.getvalue() if evidence else None,
                observacion=observations,actor=actor or 'Equipo PMO',motivo_correccion=reason)
            st.success(f'Registrada revisión {done["revision"]} · {done["resultado"]:.2f} · {done["rag"]}')
        except Exception as ex:st.error(str(ex))
    history=m.measurement_list(metric_id,latest_only=False)
    if history:
        st.markdown('**Histórico de mediciones (incluye revisiones anteriores)**')
        for row in history[:25]:
            with st.container(border=True):
                st.markdown(f'**{html.escape(row["periodo"])}** · Revisión {row["revision"]} · {row["resultado"]:.2f} {html.escape(item.get("unidad") or "")} · {row["rag"]}')
                st.caption(f'Registrado por {row["registrado_por"]} · {row["registrado_en"]}')
                if row['observacion']:st.write(row['observacion'])
                if row.get('evidencia_nombre'):
                    item_bytes=m.evidence_bytes(row['id'])
                    if item_bytes and item_bytes[1]:
                        st.download_button('Descargar evidencia · '+row['evidencia_nombre'],item_bytes[1],file_name=row['evidencia_nombre'],key='p4_met_evidence_'+row['id'])


@st.dialog('Gestionar fichas de indicadores',width='large')
def manager_dialog(service_id):
    service=s.service(service_id)
    if not service:
        st.warning('Servicio no encontrado.');return
    metrics=s.metric_list(service_id)
    st.markdown('### '+service['nombre'])
    st.caption(f'{public_code("servicio",service_id)} · {len(metrics)} fichas de métricas')
    tab1,tab2=st.tabs(['01 · Definir indicadores','02 · Registrar resultados'])
    with tab1:
        options=['Nuevo indicador',*[x['id'] for x in metrics]]
        selected=st.selectbox('Ficha a configurar',options,
            format_func=lambda x:'＋ Nuevo indicador' if x=='Nuevo indicador' else next((m.code_for(x)+' · '+r['nombre'] for r in metrics if r['id']==x),x),
            key='p4_met_manage_select')
        current=next((r for r in metrics if r['id']==selected),None)
        detail=m.spec(current['id']) if current else None
        if detail:
            st.caption(f'Estado de definición: {detail["estado"]} · Código inmutable: {detail["codigo"]}')
        if current and (current.get('real') or current.get('fecha_medicion')):
            st.info('Registro legado del formulario anterior: '+str(current.get('real') or 'Sin valor')+' · Fecha: '+str(current.get('fecha_medicion') or 'Sin fecha')+'. Se conserva sin migrarlo automáticamente a cortes oficiales.')
        _make_definition(service_id,current,detail)
        _approval_form(current,detail)
    with tab2:_capture_tab(service_id,metrics)
