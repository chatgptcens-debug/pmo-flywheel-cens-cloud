"""V0.38.7 · Catálogos inteligentes derivados de registros reales.

No crea tablas, ni homologa grupos estratégicos, ni afecta ponderaciones/corridas.
Las opciones nuevas se incorporan al catálogo cuando el formulario original
las guarda en su tabla funcional. Mantiene todas las reglas de validación.
"""
from __future__ import annotations

from contextlib import closing
import sqlite3
import unicodedata
from pathlib import Path
from .storage import connect

# Contrato cerrado: no se forman identificadores SQL con datos del usuario.
SOURCES = {
    'dependencia': [('pmo_dependencias', 'nombre'), ('p2_necesidades', 'dependencia'),
                     ('p3_beneficios', 'dependencia'), ('p6_tickets', 'dependencia'),
                     ('p7_tickets', 'dependencia'), ('p9_beneficios', 'dependencia')],
    'segmento': [('pmo_clientes', 'segmento')],
    'cargo': [('pmo_clientes', 'cargo')],
    'equipo_trabajo': [('pmo_clientes', 'equipo_trabajo')],
    'rol_especifico': [('pmo_clientes', 'rol_especifico'), ('pmo_clientes', 'segmento')],
    'responsable': [
        ('pmo_clientes', 'responsable'), ('p1_eventos', 'responsable'),
        ('p1_campanas', 'responsable'), ('p1_consultas', 'responsable'),
        ('p2_diagnosticos', 'responsable'), ('p2_evidencias', 'responsable'),
        ('p2_servicios_candidatos', 'responsable'),
        ('p3_beneficios', 'responsable'), ('p3_lienzos', 'responsable'),
        ('p4_services', 'responsable'), ('p4_metrics', 'responsable'),
        ('p5_activities', 'owner'), ('p5_plans', 'owner'),
        ('p6_tickets', 'responsable'), ('p6_catalog', 'responsable'),
        ('p7_monitoreo', 'responsable'), ('p7_hallazgos', 'responsable'),
        ('p8_cycles', 'responsable'), ('p8_actions', 'responsable'),
        ('p9_beneficios', 'responsable'), ('p9_mediciones', 'responsable'),
        ('p10_historias', 'responsable'), ('p10_actividades', 'responsable'),
    ],
    'publico_objetivo': [('p1_eventos', 'publico'), ('p1_campanas', 'audiencia')],
}


def _key(value: str) -> str:
    """Homogeneiza comparación, NO sobrescribe la etiqueta original."""
    return ' '.join(str(value).split()).casefold()


def catalog_values(kind: str, path: Path | None = None) -> list[str]:
    if kind not in SOURCES:
        raise ValueError(f'Catálogo desconocido: {kind}')
    found: dict[str, str] = {}
    with closing(connect(path)) as con:
        for table, column in SOURCES[kind]:
            # Soporta bases heredadas sin tablas/campos opcionales.
            try:
                rows = con.execute(f'SELECT DISTINCT "{column}" AS value FROM "{table}" '
                                   f'WHERE "{column}" IS NOT NULL AND TRIM("{column}")<>\'\'').fetchall()
            except sqlite3.OperationalError as ex:
                if 'no such table' in str(ex).lower() or 'no such column' in str(ex).lower():
                    continue
                raise
            for row in rows:
                val = ' '.join(str(row['value']).split())
                # La primera variante histórica permanece como opción; nunca fusionar IDs.
                found.setdefault(val, val)
    return sorted(found.values(), key=lambda s: unicodedata.normalize('NFKD', s).casefold())


def resolve_choice(selected: str, new_value: str, options: list[str]) -> str:
    """Nuevo texto explícito tiene prioridad; igualdades se vinculan a la etiqueta existente."""
    if not str(new_value or '').strip():
        # Conservar sin homologar la denominación seleccionada, incluso si
        # existe otra variante histórica con diferente escritura.
        return str(selected or '')
    value = ' '.join(str(new_value).split())
    existing = {_key(s): s for s in options if s.strip()}
    return existing.get(_key(value), value)


def smart_choice(label: str, kind: str, *, value: str = '', key: str,
                 help: str | None = None, allow_blank: bool = True, parent=None) -> str:
    """Selector + campo opcional de alta; seguro también dentro de st.form.

    Streamlit no redibuja campos condicionales dentro de un formulario al elegir
    una opción; por eso el campo «Otro» permanece visible y no rompe el envío.
    """
    if parent is None:
        import streamlit as st
        ui = st
    else:
        ui = parent
    choices = catalog_values(kind)
    current = ' '.join(str(value or '').split())
    if current and current not in choices:
        choices = sorted([*choices, current], key=str.casefold)
    # Incluso los campos obligatorios empiezan vacíos: jamás preseleccionar
    # arbitrariamente una dependencia o un grupo de la base.
    options = ['', *choices]
    default = next((i for i, opt in enumerate(options) if opt == current), 0)
    selected = ui.selectbox(label, options, index=default, key=f'{key}_catalog',
                            format_func=lambda x: x or '— Seleccionar —', help=help)
    extra = ui.text_input('Otra opción (solo si no aparece en la lista)',
                          key=f'{key}_catalog_new',
                          placeholder='Escriba una nueva denominación, si aplica')
    return resolve_choice(selected, extra, choices)
