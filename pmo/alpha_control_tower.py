"""Control Tower inicial: lecturas explícitas de la base seleccionada."""
from contextlib import closing
from datetime import datetime
from pathlib import Path
import sqlite3
from .config import database_path
from .alpha_navigation import STEPS, STAGES, STEP_NAMES, go_to

# Cada indicador informa exactamente qué cuenta, no infiere aprobación ni valor.
METRICS = (
    ('Clientes activos', 'pmo_clientes', 'activo = 1', 'Directorio · activo = 1', 1),
    ('Necesidades registradas', 'p2_necesidades', '1 = 1', 'Todos los diagnósticos de esta base', 2),
    ('Corridas archivadas', 'p2_corridas', '1 = 1', 'Todas las corridas de esta base', 2),
    ('Servicios en catálogo operativo', 'p6_catalog', 'habilitado = 1 AND demo = 0', 'Catálogo Paso 06 · habilitados, no demo', 6),
    ('Solicitudes sin finalizar', 'p6_tickets', "estado <> 'Finalizado' AND demo = 0", 'Paso 06 · no finalizadas, no demo', 6),
    ('Beneficios registrados', 'p9_beneficios', 'es_demo = 0', 'Paso 09 · no demo; no implica validación', 9),
)


def read_metrics(path=None):
    """No crea archivo ni tablas. Ausencia o error de lectura se expresa con None."""
    result = {label: None for label, *_ in METRICS}
    p = Path(path or database_path()).resolve()
    try:
        with closing(sqlite3.connect(p.as_uri() + '?mode=ro', uri=True, timeout=2)) as conn:
            conn.execute('PRAGMA query_only = ON')
            conn.execute('BEGIN')
            for label, table, predicate, _, _ in METRICS:
                try:
                    result[label] = conn.execute(f'SELECT COUNT(*) FROM {table} WHERE {predicate}').fetchone()[0]
                except sqlite3.Error:
                    pass
    except sqlite3.Error:
        pass
    return result


def render(*, isolated=False, show_steps=True):
    import streamlit as st
    from .design_system import alpha_heading, alpha_metric
    alpha_heading('INICIO · CONTROL TOWER', 'Tu espacio de trabajo PMO',
                  'Consulta el estado de los registros y navega por el ciclo generador de valor.')
    st.caption(f'Base: {database_path().parent.name} · Consulta: {datetime.now():%Y-%m-%d %H:%M} (hora del equipo) · Acumulado de la base, sin filtro anual.')
    if isolated:
        st.info('Entorno aislado: no se presentan estos conteos como resultados oficiales de CENS.')
    metrics = read_metrics()
    for offset in (0, 3):
        for col, spec in zip(st.columns(3), METRICS[offset:offset+3]):
            label, _, _, source, step = spec
            with col:
                alpha_metric(label, metrics[label], source)
                st.button(f'Consultar Paso {step:02d}', key=f'alpha_metric_{offset}_{label}', on_click=go_to, args=(STEPS[step-1],), use_container_width=True)
    if show_steps:
        st.subheader('Recorrido de generación de valor')
        st.caption('Los diez pasos son accesos directos, no una secuencia obligatoria ni un indicador de avance.')
        for i, (col, stage) in enumerate(zip(st.columns(5), STAGES)):
            with col:
                st.markdown(f'**{stage}**')
                for j in range(i*2, i*2+2):
                    st.button(f'{j+1:02d} · {STEP_NAMES[j]}', key=f'alpha_home_step_{j+1}', on_click=go_to, args=(STEPS[j],), use_container_width=True)
    with st.expander('Cómo interpretar el tablero'):
        st.write('Los conteos corresponden a la base conectada. Un cero indica que no hay registros que cumplan el criterio; un guion indica información no disponible. No se deduce madurez, aprobación, valor realizado o cumplimiento de ANS de estos conteos.')
        st.write('Para consultar resultados de priorización, selecciona una corrida real en el Paso 02. Para verificar beneficios, utiliza las mediciones y evidencias del Paso 09.')
