"""V0.33 · Recorrido unificado de priorización en Paso 02.

Consolida participantes, clasificación y criterios expertos sobre el motor existente.
La matemática de V5 y la matriz protegida no se editan.
"""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import streamlit as st

from . import matrix as canonical
from . import step2 as p2
from . import step2_engine_audit as audit32
from . import step2_participants as participants33
from . import step2_participants_ui as participants_ui33
from . import step2_sample as sample34
from . import step2_sample_ui as sample_ui34
from . import step2_ui as legacy
from .form_system import section_header, form_note
from .step2_catalog import SERVICES

STYLE = Path(__file__).resolve().parent / 'assets' / 'step2_engine_v032.css'


def _nav(page: str):
    st.session_state['pmo_active_p2_page'] = page


def _csv_quality(rows: list[dict]) -> bytes:
    buff = io.StringIO()
    writer = csv.writer(buff)
    writer.writerow(['Codigo cliente', 'Nombre', 'Dependencia', 'Rol para ponderación',
                     'Estado de respuesta', 'Prioridad 1', 'Prioridad 2', 'Prioridad 3',
                     'Prioridad 4', 'Prioridad 5'])
    for x in rows:
        writer.writerow([x['codigo'], x['nombre'], x['dependencia'], x['grupo'],
                         x['estado'], *([*x['prioridades']] + [''] * 5)[:5]])
    return buff.getvalue().encode('utf-8-sig')


def _run_labels(runs: list[dict]) -> dict:
    return {r['id']: f"{r['fecha']} · {r['modelo']} · {r['actor']}" for r in runs}


def _audit_run_view(diag: str):
    runs = p2.runs(diag)
    if not runs:
        st.info('Aún no hay una corrida guardada. Valide la muestra, defina los pesos y ejecute el motor.')
        return
    labels = _run_labels(runs)
    chosen = st.selectbox('Corrida histórica para verificar', list(labels),
                          format_func=lambda ident: labels[ident], key=f'p2v032_audit_run_{diag}')
    report = p2.get_run(chosen)
    expert = participants33.expert_criterion(chosen)
    state = audit32.freshness(diag, report)
    calc = audit32.replay(report)
    c1, c2, c3 = st.columns(3)
    c1.metric('Participantes del snapshot', len(report['respuestas']))
    c2.metric('Diferencia de reproducción (pp)',
              f"{calc['max_delta_pp']:.9f}" if calc['max_delta_pp'] is not None else '—')
    c3.metric('Matriz y ranking', 'Coherentes' if calc['ok'] else 'Revisión requerida')
    if calc['ok']:
        st.success('El ranking guardado se reproduce desde las respuestas, los pesos y la matriz de esta misma corrida.')
    else:
        for message in calc['issues']: st.error(message)
    if not state['current']:
        st.warning('Esta corrida es histórica: se modificaron respuestas o pesos desde su ejecución. El ranking no se actualiza automáticamente; ejecute una nueva corrida.')
    else:
        st.caption('Las respuestas y los pesos actuales coinciden con el snapshot seleccionado.')
    st.markdown('**Criterio experto utilizado**')
    if expert:
        st.caption(f"Método: {expert['metodo']} · Responsable: {expert['responsable']}")
        st.info(expert['justificacion'])
    else:
        st.caption('Corrida histórica sin justificación experta individualizada en la V0.33.')
    st.markdown('**Datos congelados en la corrida**')
    st.caption(f"Versión: {report.get('matrix_version_id') or 'Sin versión histórica'} · "
               f"Método: {report['resultados'].get('method','—')} · Fuente: {report['origen']}")
    st.code(f"SHA256 de entradas: {calc['hash_snapshot']}", language='text')
    if calc['matrix_sha256']:
        st.caption('SHA256 de matriz V5: ' + calc['matrix_sha256'])
    st.caption('La huella sirve para comprobar identidad de datos, no reemplaza una firma digital ni certifica la matriz experimental V5.')

    sid = st.selectbox('Explorar por qué se priorizó un servicio', list(SERVICES),
                       format_func=lambda s: f'S-{s:02d} · {SERVICES[s]}',
                       key=f'p2v032_explain_{diag}')
    explanation = audit32.service_explanation(report, sid)
    st.markdown(f"**Posición {explanation['rank']} de 26 · "
                f"{explanation['service']['score']:.2f}% del ranking**")
    if explanation['drivers']:
        st.dataframe([{
            'Resultado': f"O-{x['outcome_id']:02d} · {x['outcome']}",
            'Clientes que lo eligieron': x['respondents'],
            'Relevancia (%)': round(x['result_weight_pct'], 4),
            'Intensidad 0–4': x['intensity'],
            'Aporte al servicio (%)': round(x['service_share_pct'], 4),
            'Aporte al ranking (pp)': round(x['global_share_pct'], 4),
            'Grupos': ', '.join(f'{g}: {n}' for g, n in sorted(x['groups'].items()))
        } for x in explanation['drivers']], hide_index=True, use_container_width=True)
        st.caption('Los clientes que eligieron un beneficio se cuentan una sola vez por resultado. La relevancia ponderada depende también del tamaño de cada rol y de su peso estratégico.')
    else:
        st.info('Este servicio no tiene aportes positivos en la corrida seleccionada.')
    if calc['ok']:
        manifest = {'corrida': chosen, 'fecha': report['fecha'], 'diagnostico': diag,
                    'version_matriz': report.get('matrix_version_id'),
                    'metodo': report['resultados'].get('method'),
                    'sha256_entradas': calc['hash_snapshot'],
                    'sha256_matriz_v5': calc['matrix_sha256'],
                    'diferencia_pp': calc['max_delta_pp'], 'participantes': calc['participants'],
                    'estado_al_consultar': 'coincide' if state['current'] else 'historica',
                    'advertencia': 'V5 reconstruida, no certificada por PMI/PMOGA',
                    'criterio_experto': ({'metodo':expert['metodo'], 'responsable':expert['responsable'],
                                       'justificacion': expert['justificacion']} if expert else None),
                    'pesos_expertos': report['pesos']}
        st.download_button('↓ Descargar manifiesto de auditoría JSON',
                           json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8'),
                           file_name=f'PMO_CENS_P2_AUDITORIA_{chosen[:8]}.json',
                           mime='application/json', key=f'p2v032_manifest_{diag}')


def render_engine(diag, item):
    st.markdown('<style>' + STYLE.read_text(encoding='utf-8') + '</style>', unsafe_allow_html=True)
    section_header('02', 'Motor interno de priorización',
                   'Un solo recorrido: clientes → 30 beneficios → pesos → matriz 30 × 26 → ranking de servicios.')
    info = audit32.readiness(diag)
    k = [
        ('Clientes activos', str(info['active_clients']), 'Directorio del Paso 01', '♙', ''),
        ('Clientes participantes', str(info['complete']), 'Respuesta válida: cinco beneficios', '✓', 'blue'),
        ('Respuestas parciales', str(info['partial']), 'No válidas para V5', '◷', 'orange'),
        ('Roles con respuestas', str(len(info['active_groups_with_complete'])), 'Ponderación independiente', '▤', 'purple')
    ]
    legacy.kpis(k)
    st.progress(info['complete'] / info['active_clients'] if info['active_clients'] else 0,
                text=f"{info['complete']} de {info['active_clients']} clientes activos con respuesta completa "
                     '(cobertura de captura, no efectividad ni necesidad validada)')
    for message in info['warnings']:
        st.warning(message)
    st.caption('Rol es el campo unificado de clasificación en el directorio; Dependencia y Equipo de trabajo son atributos diferentes. El experto establece los pesos de CADA ejecución; no hay porcentajes fijos.')
    sample_state = sample34.summary(diag)
    # Cobertura del diagnóstico: no confundir directorio total ni captura general
    # con la proporción de clientes invitados que han completado el instrumento.
    invitados = [r for r in sample_state['rows'] if r['activo'] and
                 r['estado_muestra'] in ('Convocado', 'En seguimiento')]
    completos_convocados = sum(r['estado_respuesta'] == 'Completa' for r in invitados)
    if invitados:
        st.metric('Cobertura del diagnóstico · muestra convocada',
                  f'{100 * completos_convocados / len(invitados):.0f}%',
                  help=f'{completos_convocados} de {len(invitados)} clientes convocados o en seguimiento tienen cinco beneficios válidos.')
    else:
        st.caption('Cobertura del diagnóstico: pendiente de definir y convocar la muestra. Las respuestas completas no se convierten automáticamente en contactos ni convocatorias.')
    if sample_state['sample_defined']:
        st.caption(f"Muestra de levantamiento: {sample_state['selected']} seleccionados; {sample_state['complete']} respuestas completas; {sample_state['pending']} pendientes.")
        if sample_state['outside_answers']:
            st.warning('Existen respuestas de clientes fuera de la muestra seleccionada. El motor incluye todas las respuestas completas del diagnóstico; revise esta diferencia antes de calcular.')

    names = ['00 · Muestra y seguimiento', '01 · Participantes', '02 · Capturar',
             '03 · Verificar', '04 · Ponderar', '05 · Resultados', '06 · Trazabilidad']
    tab_sample, tab_people, tab_input, tab_quality, tab_weights, tab_output, tab_audit = st.tabs(names)
    with tab_sample:
        sample_ui34.render(diag, item)
    with tab_people:
        participants_ui33.render(diag, item)
    with tab_input:
        st.markdown('### Respuestas de los clientes')
        st.caption('Cada persona identifica y ordena 5 beneficios distintos entre 30. El primer lugar recibe 5 puntos y el quinto 1. La muestra no se precarga con respuestas ficticias.')
        x, y = st.columns([1, 1], gap='medium')
        with x:
            st.markdown('**Carga desde Excel o CSV**')
            legacy._load_excel_section(diag, item)
        with y:
            with st.container(border=True):
                st.markdown('**Captura manual de expectativas**')
                st.caption('El formulario de los 30 resultados permite buscar, seleccionar y reordenar exactamente cinco prioridades. El registro queda vinculado al cliente existente.')
                st.button('Abrir captura individual →', on_click=_nav,
                          args=('Expectativas de valor',), key=f'p2v032_manual_{diag}',
                          use_container_width=True)
                st.markdown('**Reglas de la carga**')
                st.caption('Se valida el código de cliente, su rol, las cinco posiciones sin repetición y los posibles cambios. Una fila con error bloquea toda la importación; la confirmación es explícita.')
        form_note('La importación actualiza las prioridades del mismo cliente y diagnóstico; no crea personas nuevas ni modifica su dependencia o rol.')

    with tab_quality:
        st.markdown('### Calidad y cobertura de respuestas')
        a, b, c = st.columns(3)
        a.metric('Sin registrar prioridades', sum(x['activo'] and not x['prioridades'] for x in info['rows']))
        b.metric('Respuestas completas', info['complete'])
        c.metric('Clientes inactivos con respuestas', info['inactive_with_answers'])
        groups = sorted({x['grupo'] for x in info['rows'] if x['grupo']})
        l, r = st.columns(2)
        with l:
            filter_state = st.selectbox('Estado de captura', ['Todos', 'Completa', 'Parcial',
                   'Sin respuesta', 'Sin rol', 'Inactivo'], key=f'p2v032_filter_state_{diag}')
        with r:
            filter_group = st.selectbox('Rol', ['Todos', *groups],
                   key=f'p2v032_filter_group_{diag}')
        selected = [x for x in info['rows'] if (filter_state == 'Todos' or x['estado'] == filter_state)
                    and (filter_group == 'Todos' or x['grupo'] == filter_group)]
        st.dataframe([{'Cliente': x['codigo'], 'Dependencia': x['dependencia'],
                       'Rol': x['grupo'] or 'Sin clasificar', 'Estado': x['estado'],
                       'Prioridades': ', '.join(f'O-{o:02d}' for o in x['prioridades'])}
                      for x in selected], hide_index=True, use_container_width=True)
        st.download_button('↓ Descargar control de calidad CSV', _csv_quality(info['rows']),
                           file_name=f'PMO_CENS_P2_CALIDAD_{diag[:8]}.csv', mime='text/csv',
                           key=f'p2v032_quality_csv_{diag}')
        st.markdown('**Representación por rol**')
        if not info['groups']:
            st.info('No hay clientes activos registrados en el directorio.')
        else:
            st.dataframe([{'Rol': group, 'Clientes activos': counts['total'],
                            'Con cinco respuestas': counts['complete'],
                            'Incompletas': counts['partial'],
                            'Sin registro': counts['missing'],
                            'Cobertura (%)': round(100 * counts['complete'] / counts['total'], 1)}
                          for group, counts in sorted(info['groups'].items())],
                         hide_index=True, use_container_width=True)
        st.caption('Los porcentajes de cobertura no forman parte de las ponderaciones estratégicas del algoritmo.')

    with tab_weights:
        st.markdown('### Ponderación estratégica y versión de matriz')
        st.caption('Para V5, todos los participantes con registros deben tener cinco prioridades completas y los pesos de los roles participantes deben ser enteros y sumar exactamente 100%.')
        if info['partial']:
            st.error('Existen respuestas parciales. Complételas o elimínelas antes de ejecutar el motor V5.')
        if sample_state['sample_defined'] and sample_state['outside_answers']:
            st.error('Control de muestra: existen respuestas fuera de la muestra activa. Revise o documente su inclusión antes de procesar; el algoritmo V5 no filtra por muestra administrativa.')
        legacy._weights_section(diag, item)
        st.caption(f"Referencia V5 protegida: {canonical.V5_ID} · "
                   '290 relaciones positivas, 780 cruces · 38 escenarios de contraste. '
                   'Reconstrucción matemática no certificada por PMI/PMOGA.')
        st.button('Inspeccionar matriz 30 × 26 →', on_click=_nav,
                  args=('Matriz PMO Value Ring',), key=f'p2v032_matrix_{diag}')

    with tab_output:
        st.markdown('### Ranking y resultados analíticos')
        if p2.runs(diag):
            legacy._results_section(diag, item)
        else:
            st.info('Todavía no existe una corrida. Primero capture respuestas completas, ajuste los pesos y confirme «Guardar pesos y ejecutar análisis».')
        st.caption('La selección de servicios es analítica. Validación institucional, factibilidad y decisiones sobre servicios candidatos se registran por separado en «Validación y MVS».')
        st.button('Abrir validación de servicios →', on_click=_nav,
                  args=('Validación y MVS',), key=f'p2v032_validate_{diag}')

    with tab_audit:
        st.markdown('### Reproducibilidad y explicación del ranking')
        history = participants33.criteria_history(diag)
        if history:
            st.markdown('**Escenarios expertos registrados**')
            st.dataframe([{
                'Corrida': row['corrida_id'][:10],
                'Fecha': row['fecha_corrida'],
                'Método': row['metodo'],
                'Responsable': row['responsable'],
                'Ponderación de roles': ', '.join(f'{g}: {v}%' for g, v in sorted(json.loads(row['pesos_json']).items())),
                'Justificación': row['justificacion']
            } for row in history], hide_index=True, use_container_width=True)
        _audit_run_view(diag)
