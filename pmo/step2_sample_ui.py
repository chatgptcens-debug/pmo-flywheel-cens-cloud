"""V0.34 · Gestión de muestra y seguimiento; los pesos siguen a criterio experto."""
from __future__ import annotations
from .date_widgets import iso_date_input

import streamlit as st
from .staff_picker import staff_picker

from . import step2_sample as model
from .clients import ValidationError
from .form_system import section_header, form_note


def render(diagnostic: str, item: dict) -> None:
    section_header('02', 'Muestra y seguimiento del levantamiento',
        'Seleccione participantes, registre convocatorias y controle la recepción de expectativas sin duplicar el directorio.')
    report = model.summary(diagnostic)
    a,b,c,d=st.columns(4)
    a.metric('Muestra seleccionada',report['selected'])
    b.metric('Respuestas completas de la muestra',report['complete'])
    c.metric('Pendientes de respuesta',report['pending'])
    d.metric('Seguimientos vencidos',report['overdue'])
    if not report['sample_defined']:
        st.info(f'La muestra aún no se ha definido. Seleccione participantes o cargue la plantilla CSV. El directorio de {len([r for r in report["rows"] if r["activo"]])} clientes activos no se convierte automáticamente en muestra.')
    else:
        coverage=report['complete']/report['selected'] if report['selected'] else 0
        st.progress(coverage, text=f'{report["complete"]} de {report["selected"]} clientes de la muestra con cinco respuestas válidas ({coverage:.0%}).')
    if report['unclassified']:
        st.warning(f'{report["unclassified"]} cliente(s) seleccionado(s) carecen de rol; clasifíquelos antes de importar sus expectativas.')
    if report['outside_answers'] and not report['sample_defined']:
        st.caption(f'{report["outside_answers"]} clientes cuentan con respuestas, pero todavía no existe una muestra formalmente registrada. No se atribuyen convocatorias ni contactos a partir de ellas.')
    if report['outside_answers'] and report['sample_defined']:
        codes=', '.join(report['outside_codes'][:10])
        st.warning(f'{report["outside_answers"]} cliente(s) con respuestas están fuera de la muestra activa (ej.: {codes}). '
                   'El motor actual calcula con todas las respuestas completas registradas en el diagnóstico; '
                   'esta muestra administrativa NO excluye automáticamente esas respuestas. Revise la discrepancia antes de ejecutar.')
    st.caption('Las ponderaciones no se deducen de la muestra: el experto las decide y justifica en cada corrida. '
               '“No participará” conserva historial y no borra respuestas existentes.')

    l,r=st.columns(2)
    deps=sorted({x['dependencia'] for x in report['rows'] if x['activo']})
    groups=sorted({x['grupo'] for x in report['rows'] if x['grupo']})
    dep=l.selectbox('Dependencia', ['Todas',*deps],key=f'p2v034_dep_{diagnostic}')
    grp=r.selectbox('Rol',['Todos','Sin rol',*groups],key=f'p2v034_group_{diagnostic}')
    x,y=st.columns(2)
    states=['Todos','Sin seleccionar',*model.STATES]
    state=x.selectbox('Estado de seguimiento',states,key=f'p2v034_state_{diagnostic}')
    ans=y.selectbox('Calidad de respuesta',['Todas','Completa','Parcial','Sin rol','Sin respuesta','Inactivo'],
                    key=f'p2v034_ans_{diagnostic}')
    rows=[q for q in report['rows'] if (dep=='Todas' or q['dependencia']==dep)
          and (grp=='Todos' or (grp=='Sin rol' and not q['grupo']) or q['grupo']==grp)
          and (state=='Todos' or q['estado_muestra']==state)
          and (ans=='Todas' or q['estado_respuesta']==ans)]
    st.dataframe([{'Código':q['codigo'],'Cliente':q['nombre'],'Dependencia':q['dependencia'],
        'Equipo':q['equipo'],'Rol':q['grupo'] or 'Sin rol',
        'Estado de muestra':q['estado_muestra'],'Respuesta':q['estado_respuesta'],
        'Próximo seguimiento':q['fecha_proxima'], 'Responsable':q['responsable']} for q in rows],
        hide_index=True,use_container_width=True)

    with st.expander('Registrar o actualizar participantes (selección múltiple)', expanded=False):
        eligible={q['cliente_id']:q for q in rows if q['activo']}
        if not eligible:st.info('Los filtros actuales no tienen clientes activos para seleccionar.')
        else:
            with st.form(f'p2v034_manual_{diagnostic}'):
                ids=st.multiselect('Clientes *',list(eligible),
                    format_func=lambda ident:f"{eligible[ident]['codigo']} · {eligible[ident]['nombre']}",
                    key=f'p2v034_ids_{diagnostic}')
                a,b=st.columns(2)
                new_state=a.selectbox('Estado de participación *',model.STATES)
                channel=b.selectbox('Canal de contacto (opcional)',model.CHANNELS)
                a,b=st.columns(2)
                when=iso_date_input('Fecha del contacto (opcional)',container=a)
                next_date=iso_date_input('Próximo seguimiento (opcional)',container=b)
                owner=staff_picker('Responsable del seguimiento (opcional)')
                observations=st.text_area('Observaciones (opcional)',height=80)
                actor=st.text_input('Responsable que registra *')
                reason=st.text_area('Criterio o justificación de la muestra *',height=75)
                overwrite=st.checkbox('Permitir actualizar estados de participantes ya registrados')
                confirmed=st.checkbox('Confirmo los clientes y el estado que voy a registrar')
                submit=st.form_submit_button('Guardar muestra y seguimiento',type='primary')
            if submit:
                if not confirmed:st.warning('Confirme la selección antes de guardar.')
                else:
                    all_records={q['cliente_id']:q for q in report['rows']}
                    payload=[]
                    for ident in ids:
                        previous=all_records[ident]
                        payload.append({'cliente_id':ident,'estado':new_state,
                          'canal':channel or previous['canal'],
                          'fecha_contacto':when or previous['fecha_contacto'],
                          'fecha_proxima':next_date or previous['fecha_proxima'],
                          'responsable':owner or previous['responsable'],
                          'observaciones':observations or previous['observaciones']})
                    try:
                        result=model.save_records(diagnostic,payload,actor,reason,overwrite=overwrite)
                        st.success(f"Registros actualizados: {result['changed']}; sin cambios: {result['unchanged']}.")
                        st.rerun()
                    except (ValidationError,ValueError) as exc:st.error(str(exc))

    with st.expander('Clasificar muestra desde CSV (edición en Excel)', expanded=False):
        st.caption('Descargue la plantilla real, complete la columna «estado» y guarde en CSV UTF-8. '
                   'Deje estado vacío para omitir una fila; no se crean clientes ni se modifican roles.')
        st.download_button('↓ Descargar plantilla de muestra CSV',model.template_csv(diagnostic),
            file_name=f'PMO_CENS_P2_MUESTRA_{diagnostic[:8]}.csv',mime='text/csv',
            key=f'p2v034_template_{diagnostic}')
        upload=st.file_uploader('CSV con estados y seguimiento',type=['csv'],
                                key=f'p2v034_upload_{diagnostic}')
        preview=None
        if upload is not None:
            try:
                preview=model.preview_csv(upload.getvalue())
                st.dataframe(preview['preview'],hide_index=True,use_container_width=True)
                for issue in preview['issues'][:15]:st.error(issue)
                if len(preview['issues'])>15:st.warning('Existen más incidencias; revise el archivo.')
                if not preview['issues']:st.success(f"{len(preview['records'])} filas listas para importar.")
            except (ValidationError,ValueError) as exc:st.error(str(exc))
        if preview and not preview['issues']:
            with st.form(f'p2v034_import_{diagnostic}'):
                actor=st.text_input('Responsable de la importación *')
                reason=st.text_area('Criterio de selección de la muestra *')
                overwrite=st.checkbox('Permitir modificar estados existentes')
                confirmed=st.checkbox('Confirmo que he revisado la vista previa')
                submit=st.form_submit_button('Confirmar importación',type='primary')
            if submit:
                if not confirmed:st.warning('Confirme la vista previa.')
                else:
                    try:
                        result=model.save_records(diagnostic,preview['records'],actor,reason,overwrite=overwrite)
                        st.success(f"Importación registrada: {result['changed']} cambios.");st.rerun()
                    except (ValidationError,ValueError) as exc:st.error(str(exc))

    if report['by_group']:
        st.markdown('**Cobertura de la muestra por rol**')
        st.dataframe([{'Grupo':g,'Participantes seleccionados':c['seleccionados'],
           'Respuestas completas':c['completos'],
           'Cobertura (%)':round(c['completos']*100/c['seleccionados']) if c['seleccionados'] else 0}
           for g,c in sorted(report['by_group'].items())],hide_index=True,use_container_width=True)
    form_note('La muestra es un control operativo. Para calcular V5, todas las respuestas consideradas deben ser válidas y pertenecer a grupos ponderados. '
              'No altera el algoritmo, no filtra automáticamente las corridas ni crea beneficios o necesidades validadas.')
