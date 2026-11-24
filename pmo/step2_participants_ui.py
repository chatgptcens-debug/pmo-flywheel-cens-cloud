"""V0.33 · Consola de participantes y segmentos; diseño estándar PMO CENS.

Los roles se deciden manualmente por criterio experto. No se homologan a dependencias.
"""
from __future__ import annotations

import json

import streamlit as st

from .clients import ValidationError
from .form_system import section_header, form_note
from . import step2_participants as ps


def _message(exc):
    st.error(str(exc))


def render(diagnostic: str, item: dict) -> None:
    section_header('02', 'Participantes y roles',
                   'Los roles del directorio alimentan la clasificación para ponderación; cada evaluación define sus pesos por criterio experto.')
    report = ps.metrics(diagnostic)
    a, b, c, d = st.columns(4)
    a.metric('Clientes activos', report['active'])
    b.metric('Con rol', report['classified'])
    c.metric('Sin rol', report['unclassified'])
    d.metric('Respuestas completas', report['complete'])
    if report['unclassified']:
        st.info(f"Hay {report['unclassified']} clientes activos sin rol. Solo es necesario clasificar a los participantes que responderán la evaluación; no se asignarán grupos automáticamente.")
    st.caption('El Rol es distinto de la Dependencia y del Equipo de trabajo. Los pesos se definen por evaluación mediante criterio experto, sin alterar las corridas históricas.')

    # Tabla administrativa: solo datos provenientes de la base.
    all_rows = report['rows']
    departments = sorted({x['dependencia'] for x in all_rows if x['dependencia']})
    groups = sorted(report['groups'])
    l, m, r = st.columns(3)
    dep = l.selectbox('Dependencia', ['Todas', *departments], key=f'p2v033_dep_{diagnostic}')
    grp = m.selectbox('Rol', ['Todos', 'Sin clasificar', *groups], key=f'p2v033_group_{diagnostic}')
    state = r.selectbox('Respuesta', ['Todas', 'Completa', 'Parcial', 'Sin respuesta', 'Sin rol', 'Inactivo'],
                        key=f'p2v033_state_{diagnostic}')
    selected = [x for x in all_rows if (dep == 'Todas' or x['dependencia'] == dep)
                and (grp == 'Todos' or (grp == 'Sin clasificar' and not x['grupo']) or x['grupo'] == grp)
                and (state == 'Todas' or state == x['estado'])]
    st.dataframe([{'Código': x['codigo'], 'Cliente': x['nombre'], 'Dependencia': x['dependencia'],
                   'Equipo': x['equipo'], 'Rol': x['rol'], 'Rol para ponderación': x['grupo'] or 'Sin clasificar',
                   'Respuesta': x['estado']} for x in selected],
                 hide_index=True, use_container_width=True)
    st.download_button('↓ Descargar plantilla CSV para clasificar',
                       ps.template_csv(report['rows']), file_name=f'PMO_CENS_P2_SEGMENTACION_{diagnostic[:8]}.csv',
                       mime='text/csv', key=f'p2v033_csv_{diagnostic}')
    with st.expander('Asignación individual o masiva por selección', expanded=False):
        eligible = [x for x in selected if x['activo']]
        labels = {x['id']: f"{x['codigo']} · {x['nombre']} · {x['grupo'] or 'Sin rol'}" for x in eligible}
        if not labels:
            st.info('Los filtros actuales no muestran clientes activos para clasificar.')
        else:
            with st.form(f'p2v033_manual_{diagnostic}'):
                ids = st.multiselect('Clientes a clasificar *', list(labels),
                                     format_func=lambda x: labels[x],
                                     key=f'p2v033_ids_{diagnostic}')
                known = sorted({x['grupo'] for x in report['rows'] if x['grupo']})
                opt = st.selectbox('Rol asignado *', ['Seleccionar...', *known, 'Registrar nuevo rol...'])
                novel = st.text_input('Nombre del nuevo rol *') if opt == 'Registrar nuevo rol...' else ''
                actor = st.text_input('Responsable de la clasificación *')
                reason = st.text_area('Justificación / criterio de clasificación *', height=90)
                overwrite = st.checkbox('Permitir cambiar el rol de clientes clasificados')
                confirm = st.checkbox('Confirmo que he revisado los clientes y el grupo propuesto')
                submitted = st.form_submit_button('Guardar clasificación', type='primary')
            if submitted:
                if not confirm:
                    st.warning('Debe confirmar la selección antes de guardar.')
                else:
                    try:
                        group = novel if opt == 'Registrar nuevo rol...' else opt if opt != 'Seleccionar...' else ''
                        result = ps.assign_segments({ident: group for ident in ids}, actor, reason,
                                                     overwrite=overwrite)
                        st.success(f"Clasificación guardada: {result['changed']} cliente(s) actualizados; {result['unchanged']} sin cambios.")
                        st.rerun()
                    except (ValidationError, ValueError) as ex:
                        _message(ex)
    with st.expander('Importar clasificación desde CSV (edición en Excel)', expanded=False):
        st.caption('Descargue la plantilla, edite la columna «rol» y guárdela como CSV UTF-8. También se aceptan plantillas anteriores con «segmento».')
        upload = st.file_uploader('Archivo CSV de roles', type=['csv'], key=f'p2v033_upload_{diagnostic}')
        preview = None
        if upload is not None:
            try:
                preview = ps.preview_csv(upload.getvalue())
                st.dataframe(preview['rows'], hide_index=True, use_container_width=True)
                if preview['issues']:
                    for x in preview['issues'][:15]: st.error(x)
                    if len(preview['issues']) > 15: st.warning(f'{len(preview["issues"])-15} incidencias adicionales.')
                else:
                    st.success(f"Se validaron {len(preview['assignments'])} asignaciones por código de cliente.")
            except (ValidationError, ValueError) as ex:
                _message(ex)
        if preview and not preview['issues']:
            with st.form(f'p2v033_import_{diagnostic}'):
                owner = st.text_input('Responsable de la importación *')
                reason = st.text_area('Justificación / criterio de clasificación *')
                overwrite = st.checkbox('Permitir reasignar roles existentes')
                approve = st.checkbox('Confirmo la vista previa y autorizo aplicar todas las asignaciones')
                pressed = st.form_submit_button('Confirmar importación', type='primary')
            if pressed:
                if not approve:
                    st.warning('Confirme la vista previa para importar.')
                else:
                    try:
                        out = ps.assign_segments(preview['assignments'], owner, reason, overwrite=overwrite)
                        st.success(f"Se modificaron {out['changed']} clientes; {out['unchanged']} sin cambios.")
                        st.rerun()
                    except (ValidationError, ValueError) as ex:
                        _message(ex)
    if report['groups']:
        st.markdown('**Distribución actual por roles (no equivale a ponderación)**')
        st.dataframe([{'Rol': g, 'Clientes activos': count} for g, count in report['groups'].items()],
                     hide_index=True, use_container_width=True)
    form_note('La asignación de Rol actualiza el directorio y sus categorías de ponderación, con auditoría y respaldo SQLite. Una corrida anterior nunca se recalcula.')
