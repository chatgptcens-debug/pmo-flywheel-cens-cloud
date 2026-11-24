"""V0.31 · Plan de mejora, antecedentes Paso 02 y cierre documentado de Paso 01.
Formularios con componentes compartidos, sin duplicar información del directorio.
"""
from __future__ import annotations
from datetime import date
import html
import json

import streamlit as st
from .staff_picker import staff_picker
from . import assessment as ass
from . import step1_closure as c
from .clients import ValidationError
from .form_system import section_header, form_note


def _error(exc):st.error(str(exc))


def _action_tab():
    a,b=st.columns([4,1],vertical_alignment='bottom')
    with a:section_header('01','Plan de mejora','Registre brechas, responsables, plazos y verificación de resultados.')
    with b:st.caption('Estados: Pendiente, En curso, Cumplida o Cancelada.')
    actions=c.list_actions()
    waiting=sum(x['estado'] in ('Pendiente','En curso') for x in actions)
    p1,p2,p3=st.columns(3)
    from .ui import kpi
    with p1:kpi('Acciones registradas',str(len(actions)),'Todas las acciones del plan','▤','orange')
    with p2:kpi('Por atender',str(waiting),'Pendientes o en curso','◷','blue')
    with p3:kpi('Cumplidas',str(sum(x['estado']=='Cumplida' for x in actions)),'Estado registrado','✓','teal')
    with st.expander('＋ Nueva acción de mejora',expanded=not actions):
        with st.form('v31_action_create',clear_on_submit=True):
            k1,k2=st.columns(2)
            dimension=k1.selectbox('Dimensión PMI *',[x[0] for x in ass.DIMENSIONS]+['Transversal'])
            owner=k2.text_input('Responsable *')
            evaluation_options={x['id']:f"{x['periodo']} · {x['evaluador']} · {x['estado']}" for x in ass.list_assessments()}
            evidence_eval=st.selectbox('Autoevaluación asociada (opcional)',
                ['Sin vincular']+list(evaluation_options),format_func=lambda x:evaluation_options.get(x,x))
            finding=st.text_area('Hallazgo o brecha *',height=85)
            action=st.text_area('Acción propuesta *',height=85)
            p1,p2=st.columns(2)
            use_due=p1.checkbox('Definir fecha objetivo')
            due=p2.date_input('Fecha objetivo',value=date.today(),disabled=not use_due, format='YYYY/MM/DD')
            evidence=st.text_input('Referencia de evidencia (opcional)',placeholder='Archivo, enlace, acta o indicador')
            actor=st.text_input('Registrado por *')
            sent=st.form_submit_button('Guardar acción de mejora',type='primary')
        if sent:
            try:
                c.add_action(dimension,finding,action,owner,actor,due if use_due else None,
                            None if evidence_eval=='Sin vincular' else evidence_eval,evidence)
                st.success('Acción registrada y vinculada al historial.')
                st.rerun()
            except ValidationError as exc:_error(exc)
    if actions:
        st.dataframe([{'ID':x['id'][:8],'Dimensión':x['dimension'],'Hallazgo':x['hallazgo'],
            'Acción':x['accion'],'Responsable':x['responsable'],
            'Fecha objetivo':x['fecha_objetivo'] or 'Sin fecha','Estado':x['estado']}
            for x in actions],hide_index=True,use_container_width=True)
        with st.expander('Actualizar seguimiento y verificación'):
            labels={x['id']:f"{x['dimension']} · {x['accion'][:70]} · {x['estado']}" for x in actions}
            selected=st.selectbox('Acción a actualizar',list(labels),format_func=lambda k:labels[k])
            item=next(x for x in actions if x['id']==selected)
            with st.form(f'v31_action_edit_{selected}'):
                state=st.selectbox('Estado',list(c.STATUSES),index=list(c.STATUSES).index(item['estado']))
                ev=st.text_input('Evidencia',value=item['evidencia'])
                result=st.text_area('Verificación del resultado',value=item['verificacion'],
                    help='Obligatorio para marcar la acción como Cumplida.')
                actor=staff_picker('Responsable del seguimiento *')
                sent=st.form_submit_button('Guardar seguimiento',type='primary')
            if sent:
                try:
                    c.update_action(selected,state,ev,result,actor)
                    st.success('Seguimiento actualizado.')
                    st.rerun()
                except ValidationError as exc:_error(exc)
    else:st.info('Todavía no hay acciones de mejora. Regístralas a partir de las brechas identificadas.')


def _transfer_tab():
    section_header('01','Antecedentes para el Paso 02',
       'Seleccione explícitamente las observaciones preliminares que desea preparar para diagnóstico.')
    form_note('Transferir un antecedente no significa que sea una necesidad validada. '
              'Las respuestas y la priorización corresponden al Paso 02.')
    records=c.preliminary_records()
    if records:
        labels={r['clave']:f"{r['tipo']} · {r['codigo_cliente']} · {r['texto'][:92]}" for r in records}
        st.caption(f'{len(records)} antecedentes potenciales disponibles; seleccione únicamente los pertinentes.')
        st.dataframe([{'Origen':r['tipo'],'Cliente':r['codigo_cliente'],'Dependencia':r['dependencia'],
            'Necesidad preliminar':r['texto'],'Clasificación':r['clasificacion']}
            for r in records],hide_index=True,use_container_width=True)
    else:
        labels={}
        st.info('Aún no se han registrado necesidades preliminares marcadas para Paso 02 ni en las fichas de clientes.')
    with st.form('v31_transfer_create'):
        a,b=st.columns(2)
        period=a.text_input('Periodo de transferencia *',value=str(date.today().year))
        owner=staff_picker('Responsable PMO *')
        selected=st.multiselect('Antecedentes seleccionados',options=list(labels),format_func=lambda key:labels[key],
            help='Puede preparar un paquete vacío si aún no hay antecedentes documentados.')
        notes=st.text_area('Notas de transferencia',height=80)
        sent=st.form_submit_button('Preparar paquete de antecedentes',type='primary')
    if sent:
        try:
            key=c.prepare_transfer(period,owner,selected,notes)
            st.success(f'Paquete {key[:8]} preparado con {len(selected)} antecedentes.')
            st.rerun()
        except ValidationError as exc:_error(exc)
    transfers=c.list_transfers()
    if transfers:
        st.markdown('**Historial de paquetes preparados**')
        st.dataframe([{'ID':x['id'][:8],'Periodo':x['periodo'],'Estado':x['estado'],
             'Responsable':x['responsable'],'Fecha':x['creado_en']} for x in transfers],
             hide_index=True,use_container_width=True)
        choices={x['id']:f"{x['periodo']} · {x['estado']} · {x['creado_en']}" for x in transfers}
        selected=st.selectbox('Seleccionar paquete',list(choices),format_func=lambda k:choices[k])
        package=c.get_transfer(selected)
        st.caption(f"{len(package['antecedentes'])} antecedentes · {package['nota_metodologica']}")
        st.download_button('↓ Descargar transferencia Paso 02 (JSON)',
            data=json.dumps(package,ensure_ascii=False,indent=2).encode('utf-8'),
            file_name=f'PMO_CENS_P01_Antecedentes_P02_{selected[:8]}.json',mime='application/json',
            key='v31_transfer_json')
        if package['estado']=='Preparada':
            with st.form('v31_mark_transfer'):
                actor=st.text_input('Responsable que registra la entrega *')
                confirmed=st.checkbox('Confirmo que el paquete fue entregado al responsable del Paso 02.')
                done=st.form_submit_button('Registrar entrega',type='primary')
            if done:
                if not confirmed:st.warning('Confirme la entrega para continuar.')
                else:
                    try:
                        c.mark_transferred(selected,actor)
                        st.success('Entrega registrada con auditoría.')
                        st.rerun()
                    except ValidationError as exc:_error(exc)
        st.caption('La entrega se documenta en SQLite; el aplicativo no crea necesidades en el Paso 02 automáticamente.')


def _closure_tab():
    section_header('01','Informe y cierre documentado',
       'Consolide el corte, sus resultados y decisiones sin detener la sensibilización continua.')
    final=[r for r in ass.list_assessments() if r['estado']=='Finalizada']
    if not final:
        st.warning('Para documentar el cierre debe finalizar primero una autoevaluación de 25 criterios.')
    else:
        labels={r['id']:f"{r['periodo']} · {r['evaluador']} · {r['puntaje']}/125 · {r['clasificacion']}" for r in final}
        with st.form('v31_close_create'):
            selected=st.selectbox('Autoevaluación finalizada *',list(labels),format_func=lambda k:labels[k])
            ev=next(r for r in final if r['id']==selected)
            period=ev['periodo']
            a,b=st.columns(2)
            a.text_input('Periodo del cierre',value=period,disabled=True)
            owner=b.text_input('Responsable del informe *')
            synopsis=st.text_area('Síntesis ejecutiva de la sensibilización *',height=120)
            remaining=st.text_area('Brechas y actividades pendientes',height=80)
            decisions=st.text_area('Decisiones y próximos contactos',height=80)
            opts={r['id']:f"{r['periodo']} · {r['estado']} · {r['creado_en']}" for r in c.list_transfers()
                  if r['periodo']==period}
            transfer=st.selectbox('Paquete de antecedentes (opcional)',
                 ['Sin asociar']+list(opts),format_func=lambda k:opts.get(k,k))
            accepted=st.checkbox('Confirmo que revisé los resultados y que el cierre es documental, no una certificación de beneficios.')
            sent=st.form_submit_button('Documentar cierre del Paso 01',type='primary')
        if sent:
            if not accepted:st.warning('Confirme la revisión de resultados para documentar el cierre.')
            else:
                try:
                    key=c.create_closure(period,selected,owner,synopsis,remaining,decisions,
                        None if transfer=='Sin asociar' else transfer)
                    st.success(f'Cierre {key[:8]} registrado. La generación de conciencia puede continuar.')
                    st.rerun()
                except ValidationError as exc:_error(exc)
    closures=c.list_closures()
    if closures:
        st.markdown('**Expedientes de cierre**')
        st.dataframe([{'Código':x['id'][:8],'Periodo':x['periodo'],
            'Responsable':x['responsable'],'Fecha de elaboración':x['creado_en']}
            for x in closures],hide_index=True,use_container_width=True)
        labels={x['id']:f"{x['periodo']} · {x['responsable']} · {x['creado_en']}" for x in closures}
        chosen=st.selectbox('Seleccionar expediente',list(labels),format_func=lambda key:labels[key])
        item=c.get_closure(chosen)
        col1,col2=st.columns(2)
        with col1:st.download_button('↓ Informe ejecutivo (HTML imprimible)',
            data=c.report_html(item),file_name=f'PMO_CENS_Cierre_P01_{chosen[:8]}.html',mime='text/html')
        with col2:st.download_button('↓ Expediente de cierre (JSON)',
            data=json.dumps(item,ensure_ascii=False,indent=2).encode('utf-8'),
            file_name=f'PMO_CENS_Cierre_P01_{chosen[:8]}.json',mime='application/json')
        st.info('El cierre guarda una instantánea histórica. Los indicadores del tablero pueden cambiar cuando se registren nuevas actividades.')
    else:st.info('Aún no existen cierres documentados. El avance del Paso 02 no depende de una puntuación mínima de la autoevaluación.')


def render_closure():
    st.markdown('<div class="pmo-eyebrow">PASO 01 · CONTROL METODOLÓGICO</div>',unsafe_allow_html=True)
    st.markdown('<div class="pmo-title">Plan de mejora y cierre del Paso 01</div>',unsafe_allow_html=True)
    st.markdown('<div class="pmo-subtitle">Consolide evidencias, mejore la sensibilización y prepare antecedentes trazables para la evaluación de necesidades.</div>',unsafe_allow_html=True)
    a,b,c_tab=st.tabs(['Plan de mejora','Transferencia al Paso 02','Informe y cierre'])
    with a:_action_tab()
    with b:_transfer_tab()
    with c_tab:_closure_tab()
