"""Ficha de cuatro pestañas de madurez documentada (Streamlit, Paso 8 V0.19)."""
from __future__ import annotations
from datetime import date
import html
import streamlit as st
from . import step8 as core
from . import step8_documented as doc


def _run(func,success):
    try:
        result=func();st.success(success);return result if result is not None else True
    except (core.ValidationError,ValueError,TypeError,KeyError) as exc:
        st.error(str(exc));return None

def _date(value):
    try:return date.fromisoformat(str(value)[:10])
    except (ValueError,TypeError):return date.today()

def _select_level(text,current,key,empty=True):
    opts=([None] if empty else [])+[1,2,3,4,5]
    return st.selectbox(text,opts,index=opts.index(current) if current in opts else 0,
                        format_func=lambda x:'— Sin evaluar' if x is None else f'Nivel {x}',key=key)

def _clean(text):return html.escape(str(text or ''))

@st.dialog('Evaluación documentada de la madurez',width='large')
def service_review_dialog(cycle_id,ref):
    service=core.CAT[int(ref)]
    original=next(x for x in core.ratings(cycle_id) if x['servicio_ref']==int(ref))
    review=doc.review(cycle_id,ref)
    evs=doc.evidences(cycle_id,ref)
    cycle=core.cycle(cycle_id)
    editable=cycle['estado']=='Borrador'
    st.markdown(f'### {ref:02d} · {service["name_es"]}')
    st.caption(f'{core.CATEGORIES_ES[service["category"]]} · Criterios específicos de cinco niveles · Ciclo: {cycle["nombre"]}')
    a,b,c=st.columns(3)
    with a:st.metric('Madurez actual','—' if original['actual'] is None else f'{original["actual"]}/5')
    with b:st.metric('Madurez deseada','—' if original['deseado'] is None else f'{original["deseado"]}/5')
    with c:
        gap=original['deseado']-original['actual'] if original['estado']=='Evaluado' else None
        st.metric('Brecha','—' if gap is None else f'{gap*20:.0f} pp')
    if review['estado']=='Validado' and not review['vigente']:
        st.warning('La calificación cambió después de la validación. Debes revisar y validar nuevamente.')
    elif review['vigente']:st.success('Evaluación validada y vigente con evidencia registrada.')
    else:st.caption('Estado documental: '+review['estado'])
    t1,t2,t3,t4=st.tabs(['01 · Niveles de madurez','02 · Evaluación actual','03 · Meta de madurez','04 · Brechas y evolución'])
    with t1:
        st.info('Los cinco descriptores son síntesis técnicas específicas de cada servicio en español. La calificación requiere juicio del evaluador y evidencias; no se asigna automáticamente.')
        for level in service['levels_es']:
            idx=level['level'];mark=[]
            if idx==original['actual']:mark.append('Actual')
            if idx==original['deseado']:mark.append('Meta')
            st.markdown(f'''<div class="p8-level-card"><div class="p8-level-id">{idx}</div>
            <div><strong>Nivel {idx} · {_clean(level['title'])}</strong>
            <p>{_clean(level['description'])}</p>
            <span class="p8-level-indicator">{' · '.join(mark) if mark else 'Criterio de referencia'}</span></div></div>''',unsafe_allow_html=True)
    with t2:
        st.caption('Registra el nivel que esté suficientemente demostrado. No se asciende de nivel por el solo hecho de adjuntar un soporte.')
        if editable:
            with st.form(f'p8doc_current_{cycle_id}_{ref}'):
                status=st.selectbox('Situación del servicio',core.STATUS,index=core.STATUS.index(original['estado']))
                c1,c2=st.columns(2)
                with c1:actual=_select_level('Nivel actual (1–5)',original['actual'],f'p8dc_cur_{cycle_id}_{ref}')
                with c2:desired=_select_level('Nivel deseado (1–5)',original['deseado'],f'p8dc_des_{cycle_id}_{ref}')
                justification=st.text_area('Justificación de la calificación',value=review['justificacion'] or '',height=104)
                c3,c4=st.columns(2)
                with c3:actor=st.text_input('Responsable de la evaluación',value=review['evaluador'] or original['revisado_por'] or cycle['responsable'])
                with c4:when=st.date_input('Fecha de evaluación',value=_date(review['fecha']), format='YYYY/MM/DD')
                state=st.selectbox('Estado de revisión documental',doc.ESTADOS,index=doc.ESTADOS.index(review['estado'] if review['vigente'] or review['estado']!='Validado' else 'Pendiente de validación'))
                st.caption('Para validar: nivel actual, meta, justificación, responsable y al menos una evidencia.')
                if st.form_submit_button('Guardar evaluación y estado',type='primary',use_container_width=True):
                    if _run(lambda:doc.save_review(cycle_id,ref,status,actual if status=='Evaluado' else None,
                        desired if status=='Evaluado' else None,justification,actor,str(when),state,
                        review['meta_justificacion'],review['capacidades'],review['recursos'],review['horizonte'],
                        review['responsable_meta'],review['acciones'],review['observaciones']),
                        'Calificación documentada guardada en la base SQLite'):
                        st.rerun()
        else:st.info('El ciclo está cerrado. La ficha permanece disponible para consulta y descarga.')
        st.markdown('#### Evidencias asociadas al servicio y al ciclo')
        if evs:
            for x in evs:
                with st.container(border=True):
                    st.markdown(f'**{_clean(x["descripcion"])}** · {_clean(x["tipo"])} · Nivel {x["nivel"] if x["nivel"] is not None else "sin asociar"}')
                    st.caption(f'Fecha: {x["fecha"]} · {_clean(x["responsable"])} · Referencia: {_clean(x["referencia"] or "sin enlace")}')
                    if x['archivo_nombre']:
                        f=doc.evidence_file(x['id'])
                        if f['archivo'] is not None:
                            st.download_button('Descargar '+x['archivo_nombre'],f['archivo'],file_name=x['archivo_nombre'],
                                mime=x['archivo_tipo'] or 'application/octet-stream',key='p8doc_dl_'+x['id'])
                    if editable and st.button('Retirar evidencia',key='p8doc_del_'+x['id']):
                        if _run(lambda:doc.remove_evidence(cycle_id,ref,x['id']),'Evidencia retirada; se revisó el estado de validación'):st.rerun()
        else:st.caption('Este servicio aún no tiene evidencias documentadas en este ciclo.')
        if editable:
            with st.form(f'p8doc_add_evidence_{cycle_id}_{ref}',clear_on_submit=True):
                st.markdown('**Registrar una evidencia**')
                t,lev=st.columns(2)
                with t:kind=st.selectbox('Tipo de evidencia',doc.TIPOS)
                with lev:level=_select_level('Nivel que sustenta',original['actual'],f'p8de_lev_{cycle_id}_{ref}')
                description=st.text_input('Descripción del soporte *')
                link=st.text_input('Enlace o código de referencia (opcional)')
                attached=st.file_uploader('Adjuntar archivo pequeño (máximo 600 KB)',key=f'p8de_up_{cycle_id}_{ref}')
                if st.form_submit_button('Registrar evidencia',type='secondary',use_container_width=True):
                    blob=attached.getvalue() if attached else None
                    if _run(lambda:doc.add_evidence(cycle_id,ref,kind,description,level,link,
                          attached.name if attached else '',attached.type if attached else '',blob,
                          actor=review['evaluador'] or cycle['responsable']),
                          'Evidencia incorporada al expediente del servicio'):
                        st.rerun()
    with t3:
        if editable:
            with st.form(f'p8doc_target_{cycle_id}_{ref}'):
                st.caption('La meta no tiene que ser nivel 5. Debe responder a la estrategia y a la viabilidad de CENS.')
                target=_select_level('Nivel de madurez deseado',original['deseado'],f'p8dt_level_{cycle_id}_{ref}')
                goal=st.text_area('Justificación de la meta',value=review['meta_justificacion'] or '',height=80)
                caps=st.text_area('Capacidades por desarrollar',value=review['capacidades'] or '',height=76)
                resources=st.text_area('Recursos requeridos o dependencias',value=review['recursos'] or '',height=76)
                a,b=st.columns(2)
                with a:horizon=st.date_input('Horizonte previsto',value=_date(review['horizonte']) if review['horizonte'] else None, format='YYYY/MM/DD')
                with b:owner=st.text_input('Responsable de la evolución',value=review['responsable_meta'] or '')
                actions=st.text_area('Acciones previstas',value=review['acciones'] or '')
                if st.form_submit_button('Guardar meta y condiciones',type='primary',use_container_width=True):
                    current=original['actual']
                    status='Evaluado' if current is not None and target is not None else original['estado']
                    # Para no escribir una calificación falsa, la meta se guarda solo si ya existe nivel actual.
                    if target is not None and current is None:
                        st.error('Para registrar la meta numérica, diligencia primero el nivel actual en Evaluación actual.')
                    else:
                        if _run(lambda:doc.save_review(cycle_id,ref,status,current if status=='Evaluado' else None,
                             target if status=='Evaluado' else None,review['justificacion'],
                             review['evaluador'] or cycle['responsable'],review['fecha'],
                             'Pendiente de validación' if review['estado']=='Validado' and target!=original['deseado'] else review['estado'],
                             goal,caps,resources,str(horizon) if horizon else None,owner,actions,review['observaciones']),
                             'Meta y capacidades guardadas'):
                            st.rerun()
        else:
            st.markdown('**Meta y justificación:** '+_clean(review['meta_justificacion']))
            st.markdown('**Capacidades a fortalecer:** '+_clean(review['capacidades']))
            st.markdown('**Recursos requeridos:** '+_clean(review['recursos']))
            st.markdown('**Horizonte:** '+_clean(review['horizonte']))
    with t4:
        if gap is None:st.info('Registra y guarda ambos niveles para calcular la brecha.')
        else:
            st.markdown(f'**Brecha:** {gap} nivel(es) · **{gap*20} puntos porcentuales**')
            if gap>0:
                st.markdown('**Nivel meta:** '+_clean(service['levels_es'][original['deseado']-1]['title']))
                st.markdown('**Capacidades faltantes:** '+_clean(review['capacidades'] or 'Por documentar.'))
            elif gap==0:st.success('La meta coincide con el nivel actual; puede requerir sostenimiento y evidencia posterior.')
            else:st.warning('La meta es inferior al nivel actual; revisa si corresponde a un ajuste de alcance.')
        st.markdown('**Acciones previstas:** '+_clean(review['acciones'] or 'Por definir.'))
        st.markdown('**Observaciones:** '+_clean(review['observaciones'] or 'Sin observaciones adicionales.'))
        log=doc.history(cycle_id,ref)
        st.markdown('#### Historial de decisiones y versiones')
        if not log:st.caption('Todavía no se han guardado revisiones documentadas.')
        for item in reversed(log[-12:]):
            st.caption(f'{item["fecha"]} · {_clean(item["actor"])} · {_clean(item["accion"])}')
    st.caption('Los 130 descriptores se obtuvieron de la síntesis específica facilitada; no son una certificación PMI ni alteran el modelo de cálculo PMO-GA.')


def service_review_catalog(r):
    st.markdown('#### Fichas documentadas de los 26 servicios')
    st.caption('Abre una ficha para consultar los cinco criterios, sustentar el nivel, registrar evidencias y definir su evolución.')
    data={x['servicio_ref']:x for x in r['ratings']}
    category=st.selectbox('Filtrar catálogo por categoría',['Todas',*list(core.CATEGORIES_ES.values())],key='p8doc_filter_category')
    q=st.text_input('Buscar por código o nombre del servicio',key='p8doc_service_search')
    state_filter=st.selectbox('Filtrar estado de evaluación',['Todos','Evaluados','Pendientes','No ofrecidos','Validados con evidencia'],key='p8doc_status_filter')
    for service in core.CATALOG:
        if category!='Todas' and core.CATEGORIES_ES[service['category']]!=category:continue
        if q and q.casefold() not in f'{service["id"]:02d} {service["name_es"]}'.casefold():continue
        row=data[service['id']]
        doc_state=doc.review(r['cycle']['id'],service['id'])
        if state_filter=='Evaluados' and row['estado']!='Evaluado':continue
        if state_filter=='Pendientes' and row['estado']!='Pendiente':continue
        if state_filter=='No ofrecidos' and row['estado']!='No ofrecido':continue
        if state_filter=='Validados con evidencia' and not doc_state['vigente']:continue
        c1,c2,c3=st.columns([3.1,1.5,1.3],vertical_alignment='center')
        with c1:
            st.markdown(f'**{service["id"]:02d} · {service["name_es"]}**')
            st.caption(core.CATEGORIES_ES[service['category']])
        with c2:
            st.caption(f"{row['actual'] or '—'} / {row['deseado'] or '—'} · {('Validado' if doc_state['vigente'] else doc_state['estado'] if doc_state['estado']!='Validado' else 'Validación pendiente')}")
        with c3:
            if st.button('Evaluar madurez',key=f'p8doc_open_{r["cycle"]["id"]}_{service["id"]}',use_container_width=True):
                service_review_dialog(r['cycle']['id'],service['id'])
        st.divider()
