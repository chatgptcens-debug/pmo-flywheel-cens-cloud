"""V0.39.17 · Navegación consolidada del Paso 02.

Solo capa de presentación y consultas: reutiliza sin alterar la persistencia,
las ponderaciones de criterio experto, snapshots, matriz PMO Value Ring y motor V5.
Las funciones de escritura siguen en los módulos históricos auditados.
"""
from __future__ import annotations

from collections import Counter
import json

import streamlit as st

from . import step2 as p2
from . import step2_engine_audit as audit32
from . import step2_sample as sample34
from . import step2_sample_ui as sample_ui34
from . import step2_participants_ui as participants_ui33
from . import step2_reference_ui as classic
from . import step2_ui as legacy
from .step2_reports import results_xlsx


# Nombres públicos únicos de captura; las vistas anteriores se conservan como aliases.
NAV = [
    ('Resumen ejecutivo', 'layout-dashboard'),
    ('Plan y contexto', 'clipboard-list'),
    ('Clientes y expectativas', 'users'),
    ('Necesidades y evidencias', 'files'),
    ('Priorización y matriz', 'chart-no-axes-combined'),
    ('Validación y MVS', 'clipboard-check'),
    ('Informes y transferencia', 'file-output'),
    ('Autoevaluación PMI', 'book-open-check'),
]

ALIASES = {
    'Panorama y madurez': 'Plan y contexto',
    'Plan de evaluación': 'Plan y contexto',
    'Clientes y levantamiento': 'Clientes y expectativas',
    'Expectativas de valor': 'Clientes y expectativas',
    'Priorización': 'Priorización y matriz',
    'Motor Excel · Priorización': 'Priorización y matriz',
    'Matriz PMO Value Ring': 'Priorización y matriz',
    'Matriz de correspondencia': 'Priorización y matriz',
    'Evidencias e informes': 'Informes y transferencia',
}

META = {
    'Resumen ejecutivo': ('DIAGNÓSTICO Y VALOR', 'Evaluación de necesidades',
        'Síntesis del diagnóstico, calidad de la información y decisiones pendientes.'),
    'Plan y contexto': ('PLANIFICACIÓN Y CONTEXTO', 'Plan y contexto del diagnóstico',
        'Alcance, población, muestra y madurez institucional anual, sin mezclar métodos de cálculo.'),
    'Clientes y expectativas': ('ESCUCHA DEL CLIENTE', 'Clientes, levantamientos y expectativas',
        'Un único lugar para consultar clientes, registrar actividades y capturar las cinco prioridades.'),
    'Necesidades y evidencias': ('BRECHAS Y SOPORTES', 'Necesidades y evidencias',
        'Dificultades, ganancias, fuentes, soportes y decisiones de validación en un mismo expediente.'),
    'Priorización y matriz': ('PRIORIZACIÓN MULTICRITERIO', 'Motor de priorización PMO',
        'Control de calidad, criterio experto, matriz 30 × 26, resultados y auditoría V5.'),
    'Validación y MVS': ('DECISIONES SUSTENTADAS', 'Validación y servicios MVS',
        'Contraste entre recomendación analítica y decisiones documentadas de la PMO.'),
    'Informes y transferencia': ('CIERRE Y TRAZABILIDAD', 'Informes y transferencia al Paso 03',
        'Una sola salida ejecutiva con fuentes, pendientes y expediente versionado de diagnóstico.'),
    'Autoevaluación PMI': ('AUTOEVALUACIÓN METODOLÓGICA', 'Autoevaluación PMI · Paso 02',
        'Instrumento metodológico independiente de la madurez institucional y del motor V5.'),
}


def _switch_subsection(key: str, label: str, values: list[str], *, default: str | None = None) -> str:
    """Renderiza solo la subsección elegida: evita crear widgets de edición duplicados."""
    if key not in st.session_state or st.session_state[key] not in values:
        st.session_state[key] = default or values[0]
    return st.radio(label, values, horizontal=True, key=key, label_visibility='collapsed')


def _go(target: str) -> None:
    st.session_state['pmo_active_p2_page'] = target


def quality_snapshot(diag: str, *, path=None) -> dict:
    """Cuatro conceptos NO intercambiables: captura, fuente, evidencia y validación."""
    active = audit32.readiness(diag, path=path)
    needs = p2.needs(diag, path=path)
    refs = p2.evidence(diag, path=path)
    candidates = p2.candidates(diag, path=path)
    sample = sample34.summary(diag, path=path)
    evidence_needs = {str(x['necesidad_id']) for x in refs if x.get('necesidad_id')}
    with_source = sum(bool(str(x.get('fuente') or '').strip()) for x in needs)
    validated = sum(x['estado'] == 'Validada' for x in needs)
    return {
        'active_clients': active['active_clients'],
        'responses_complete': active['complete'],
        'responses_partial': active['partial'],
        'clients_without_role': active['no_group'],
        'needs_total': len(needs),
        'needs_with_source': with_source,
        'needs_with_evidence': sum(x['id'] in evidence_needs for x in needs),
        'evidence_references': len(refs),
        'needs_validated': validated,
        'needs_in_review': sum(x['estado'] == 'En validación' for x in needs),
        'candidates_documented': len(candidates),
        'selected_in_sample': sample['selected'],
        'sample_defined': sample['sample_defined'],
        'sample_complete': sample['complete'],
        'outside_answers': sample['outside_answers'],
    }


def quality_dashboard(diag: str, *, detailed: bool = False) -> dict:
    q = quality_snapshot(diag)
    a, b, c, d = st.columns(4, gap='small')
    a.metric('Respuestas completas', f"{q['responses_complete']} / {q['active_clients']}",
             help='Cinco prioridades distintas por cliente activo, NO necesidades validadas')
    b.metric('Necesidades con fuente', f"{q['needs_with_source']} / {q['needs_total']}",
             help='La fuente textual registrada NO equivale a una evidencia verificable')
    c.metric('Necesidades con evidencia', f"{q['needs_with_evidence']} / {q['needs_total']}",
             help='Cuenta necesidades vinculadas a referencias documentales; una evidencia puede respaldar varias necesidades')
    d.metric('Necesidades validadas', f"{q['needs_validated']} / {q['needs_total']}",
             help='Estado Validada registrado, no aprobación automática de servicios')
    st.caption('Calidad del diagnóstico: la captura completa, la fuente identificada, la evidencia y la validación son controles independientes. '
               'Los contadores no representan un puntaje de madurez PMI ni intervienen en V5.')
    if detailed:
        st.markdown('**Controles complementarios**')
        rows = [
            {'Control': 'Muestra formal', 'Resultado': f"{q['selected_in_sample']} seleccionados" if q['sample_defined'] else 'Sin definir', 'Observación': 'No equiparar con todas las respuestas del directorio'},
            {'Control': 'Respuestas parciales', 'Resultado': str(q['responses_partial']), 'Observación': 'No son válidas para una corrida V5'},
            {'Control': 'Clientes sin rol', 'Resultado': str(q['clients_without_role']), 'Observación': 'Requieren clasificación desde el directorio'},
            {'Control': 'Referencias documentales', 'Resultado': str(q['evidence_references']), 'Observación': 'Cantidad de registros del repositorio'},
            {'Control': 'Necesidades en revisión', 'Resultado': str(q['needs_in_review']), 'Observación': 'No confundir con validadas'},
            {'Control': 'Servicios con decisión', 'Resultado': str(q['candidates_documented']), 'Observación': 'Decisión declarativa, sin aprobación automática'},
        ]
        st.dataframe(rows, hide_index=True, use_container_width=True)
        if q['outside_answers']:
            st.warning('Existen respuestas fuera de la muestra definida; revise su inclusión y documentación antes de ejecutar V5.')
    return q


def overview(diag: str, item: dict) -> None:
    st.markdown('### Estado ejecutivo del diagnóstico')
    q = quality_dashboard(diag, detailed=False)
    runs = p2.runs(diag)
    decisions = p2.candidates(diag)
    a, b, c, d = st.columns(4, gap='small')
    a.metric('Corridas del motor', len(runs))
    b.metric('Servicios con decisión', len(decisions))
    c.metric('Muestra seleccionada', q['selected_in_sample'] if q['sample_defined'] else 'Sin definir')
    d.metric('Evidencias documentales', q['evidence_references'])
    if runs:
        latest = p2.get_run(runs[0]['id'])
        result = latest['resultados']
        st.markdown('**Último análisis registrado**')
        st.caption(f"{latest['fecha']} · {latest['modelo']} · "
                   f"{result['participants']} participantes · snapshot conservado")
        left, right = st.columns([1.25, 1], gap='medium')
        with left:
            classic.bars([(x['name'], x['score']) for x in result['outcomes']], 6)
        with right:
            st.dataframe([{'Servicio': x['name'], 'Relevancia (%)': round(x['score'], 2)}
                          for x in result['services'][:6]], hide_index=True, use_container_width=True)
    else:
        st.info('No hay una corrida de priorización. Registra expectativas y utiliza «Priorización y matriz» para ejecutar el motor.')
    if q['responses_complete'] and not q['sample_defined']:
        st.warning('Hay respuestas completas, pero la muestra formal del diagnóstico no ha sido definida.')
    st.caption('El panorama anual de madurez se consulta exclusivamente en «Plan y contexto»; no participa en el motor V5.')
    left, right = st.columns(2, gap='medium')
    with left:
        st.button('Revisar necesidades y evidencias', key='p2v03917_overview_needs',
            use_container_width=True, on_click=_go, args=('Necesidades y evidencias',))
    with right:
        st.button('Abrir expediente e informes', key='p2v03917_overview_report',
            use_container_width=True, on_click=_go, args=('Informes y transferencia',))


def plan_and_context(diag: str, item: dict) -> None:
    selected = _switch_subsection('p2v03917_plan_view','Sección del plan',
        ['Plan del diagnóstico', 'Muestra y seguimiento', 'Roles y participantes', 'Madurez institucional anual'])
    if selected == 'Plan del diagnóstico':
        classic.plan(diag, item)
    elif selected == 'Muestra y seguimiento':
        sample_ui34.render(diag, item)
    elif selected == 'Roles y participantes':
        participants_ui33.render(diag, item)
    else:
        st.info('Consulta independiente por año. Estos valores no se utilizan en las ponderaciones V5 ni en la autoevaluación PMI.')
        from .step2_maturity_dashboard import render
        render()


def clients_and_expectations(diag: str, item: dict) -> None:
    selected = _switch_subsection('p2v03917_clients_view','Sección de clientes',
        ['Directorio y levantamientos', 'Expectativas de valor', 'Cobertura del diagnóstico'])
    if selected == 'Directorio y levantamientos':
        classic.clients(diag, item)
    elif selected == 'Expectativas de valor':
        classic.expectations(diag, item)
    else:
        from .alpha02_clients import render_coverage
        render_coverage(diag)
    st.caption('El directorio se administra en el Paso 01. Las prioridades manuales y Excel del Paso 02 se editan exclusivamente en «Expectativas de valor».')


def needs_and_evidence(diag: str, item: dict) -> None:
    selected = _switch_subsection('p2v03917_needs_view','Sección de necesidades',
        ['Necesidades y validación', 'Repositorio de evidencias', 'Calidad de la información', 'Explorador de necesidades'])
    if selected == 'Necesidades y validación':
        classic.needs(diag, item)
    elif selected == 'Repositorio de evidencias':
        st.markdown('### Repositorio único de evidencias')
        st.caption('Una fuente mencionada en la ficha de necesidad no implica que exista una referencia documental verificable.')
        legacy._evidence_section(diag, item, show_transfer=False)
    elif selected == 'Explorador de necesidades':
        from .alpha02_clients import render_needs
        render_needs(diag)
    else:
        st.markdown('### Estado documental y de validación')
        quality_dashboard(diag, detailed=True)


def prioritization_and_matrix(diag: str, item: dict) -> None:
    from . import matrix_ui
    from .step2_engine_ui import _audit_run_view, _csv_quality
    st.caption('Motor de priorización PMO V5: prioridades 5–4–3–2–1, roles ponderados por criterio experto, matriz 30 × 26 y ranking. '
               'Este módulo no aprueba servicios y no modifica las corridas anteriores.')
    selected = _switch_subsection('p2v03917_priority_view','Sección del motor',
        ['Verificar captura', 'Ponderar y ejecutar', 'Matriz PMO Value Ring', 'Resultados', 'Historial y auditoría'])
    if selected == 'Verificar captura':
        st.markdown('### Calidad de las respuestas para priorizar')
        q = quality_dashboard(diag, detailed=True)
        audit = audit32.readiness(diag)
        state = st.selectbox('Estado de captura', ['Todos', 'Completa', 'Parcial', 'Sin respuesta', 'Sin grupo', 'Inactivo'],
                             key=f'p2v03917_quality_filter_{diag}')
        roles = sorted({x['grupo'] for x in audit['rows'] if x['grupo']})
        role = st.selectbox('Rol', ['Todos', *roles], key=f'p2v03917_role_filter_{diag}')
        rows = [x for x in audit['rows'] if (state == 'Todos' or x['estado'] == state)
                and (role == 'Todos' or x['grupo'] == role)]
        st.dataframe([{'Cliente': x['codigo'], 'Dependencia': x['dependencia'], 'Rol': x['grupo'] or 'Sin clasificar',
                       'Estado': x['estado'], 'Prioridades': ', '.join(f'O-{o:02d}' for o in x['prioridades'])}
                      for x in rows], hide_index=True, use_container_width=True)
        st.download_button('Descargar control de respuestas CSV', _csv_quality(audit['rows']),
            file_name=f'PMO_CENS_P2_CALIDAD_{diag[:8]}.csv', mime='text/csv', key=f'p2v03917_quality_csv_{diag}')
        if q['responses_partial'] or q['clients_without_role']:
            st.warning('Las respuestas incompletas o sin rol deben revisarse antes de procesar un nuevo escenario V5.')
        def open_expectations():
            st.session_state['p2v03917_clients_view']='Expectativas de valor'
            _go('Clientes y expectativas')
        st.button('Editar expectativas de valor', key='p2v03917_open_expectations',
                  on_click=open_expectations)
    elif selected == 'Ponderar y ejecutar':
        st.markdown('### Configuración experta de la corrida')
        st.caption('Ponderaciones variables por corrida, números enteros con suma 100% para V5; se conserva la justificación y el snapshot original.')
        legacy._weights_section(diag, item)
    elif selected == 'Matriz PMO Value Ring':
        st.markdown('### Matriz PMO Value Ring · 30 × 26')
        st.caption('Inspección y auditoría de las 780 relaciones. El motor y sus versiones permanecen intactos.')
        matrix_ui.panel(diag)
    elif selected == 'Resultados':
        from . import priority_results_ui
        priority_results_ui.render(diag)
        st.caption('Las decisiones MVS se documentan en la sección siguiente; el ranking no implica aprobación.')
    else:
        st.markdown('### Corridas y trazabilidad')
        from .step2_participants import criteria_history
        history = criteria_history(diag)
        if history:
            st.dataframe([{'Corrida':x['corrida_id'][:10], 'Fecha':x['fecha_corrida'],
                           'Método':x['metodo'], 'Responsable':x['responsable'],
                           'Justificación':x['justificacion']}
                          for x in history], hide_index=True, use_container_width=True)
        _audit_run_view(diag)


def validation(diag: str, item: dict) -> None:
    classic.validation(diag, item, show_transfer=False)
    st.caption('La validación de candidatos es una decisión documentada, no una autorización de operación ni una aprobación de los 26 servicios.')


def transfer_package(diag: str, *, path=None) -> bytes:
    """Amplía el JSON del Paso 02 sin cambiar su estructura base ni las corridas."""
    package = json.loads(p2.transfer_json(diag, path).decode('utf-8'))
    sample = sample34.summary(diag, path=path)
    package['control_calidad_v03917'] = quality_snapshot(diag, path=path)
    package['muestra_seguimiento_v03917'] = [
        {'cliente_id': r['cliente_id'], 'codigo': r['codigo'],
         'rol': r['grupo'], 'estado_muestra': r['estado_muestra'],
         'estado_respuesta': r['estado_respuesta'],
         'fecha_contacto': r['fecha_contacto'], 'fecha_proxima': r['fecha_proxima']}
        for r in sample['rows'] if r['estado_muestra'] != 'Sin seleccionar' or r['prioridades']
    ]
    package['nota_de_transferencia_v03917'] = (
        'Expediente preliminar para el Paso 03. Fuentes identificadas, evidencias y ' 
        'necesidades validadas son estados diferentes. No se aprueban servicios ni ' 
        'se recalculan corridas. El historial se conserva según la versión original.')
    return json.dumps(package, ensure_ascii=False, indent=2, default=str).encode('utf-8')


def reports_and_transfer(diag: str, item: dict) -> None:
    st.markdown('### Expediente ejecutivo único')
    q = quality_dashboard(diag, detailed=True)
    runs = p2.runs(diag)
    candidates = p2.candidates(diag)
    validations = Counter(str(x['estado']) for x in candidates)
    a, b, c = st.columns(3)
    a.metric('Corridas auditables', len(runs))
    b.metric('Servicios con decisión', len(candidates))
    c.metric('Referencias registradas', q['evidence_references'])
    with st.expander('Resumen de decisiones y preparación del Paso 03', expanded=True):
        decisions = [
            {'Control': 'Expectativas válidas', 'Estado': f"{q['responses_complete']} completas", 'Alcance': 'Cinco preferencias por persona activa'},
            {'Control': 'Necesidades', 'Estado': f"{q['needs_validated']} validadas / {q['needs_total']} registradas", 'Alcance': 'Las fuentes textuales no constituyen soporte documental'},
            {'Control': 'Evidencia documental', 'Estado': f"{q['evidence_references']} referencias", 'Alcance': 'Revisar trazabilidad por necesidad'},
            {'Control': 'Priorización V5', 'Estado': f'{len(runs)} corridas', 'Alcance': 'Snapshots históricos con ponderación experta'},
            {'Control': 'Validación MVS', 'Estado': f'{len(candidates)} decisiones', 'Alcance': ', '.join(f'{k}: {v}' for k,v in sorted(validations.items())) or 'Sin decisiones'},
        ]
        st.dataframe(decisions, hide_index=True, use_container_width=True)
        if q['responses_complete'] and not runs:
            st.warning('Existen respuestas completas, pero todavía no hay un ranking guardado para sustentar la propuesta.')
        if q['needs_with_source'] and not q['evidence_references']:
            st.warning('Se registraron fuentes en necesidades, pero todavía no hay referencias en el repositorio documental.')
        if not q['needs_validated']:
            st.warning('No se han validado necesidades. Los servicios recomendados no deben interpretarse como decisiones aprobadas.')
    st.markdown('### Exportación y transferencia')
    st.caption('El paquete JSON conserva los identificadores reales, las referencias, las corridas y decisiones. La transferencia es un insumo para los lienzos del Paso 03, no una aprobación automática.')
    st.download_button('Descargar expediente del diagnóstico · JSON', transfer_package(diag),
        file_name=f'PMO_CENS_P2_EXPEDIENTE_{diag[:8]}.json', mime='application/json',
        key=f'p2v03917_transfer_{diag}', type='primary')
    if runs:
        chosen = st.selectbox('Corrida para informe Excel', [x['id'] for x in runs],
            format_func=lambda ident: next(f"{x['fecha']} · {x['modelo']} · {x['actor']}" for x in runs if x['id']==ident),
            key=f'p2v03917_export_run_{diag}')
        report = p2.get_run(chosen)
        st.download_button('Descargar resultados de la corrida · Excel', results_xlsx(report),
            file_name=f'PMO_CENS_P2_RESULTADOS_{chosen[:8]}.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            key=f'p2v03917_export_xlsx_{diag}')
    st.info('El Paso 03 ya dispone de lienzos de valor y soluciones editables. Revise los datos y las decisiones antes de transferirlos a su flujo institucional.')


VIEWS = {
    'Resumen ejecutivo': overview,
    'Plan y contexto': plan_and_context,
    'Clientes y expectativas': clients_and_expectations,
    'Necesidades y evidencias': needs_and_evidence,
    'Priorización y matriz': prioritization_and_matrix,
    'Validación y MVS': validation,
    'Informes y transferencia': reports_and_transfer,
}
