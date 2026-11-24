"""PMO FLYWHEEL CENS: presentational components for the executive top panel.

This module deliberately does not read or write data, define Streamlit widgets,
change session state or compute KPIs. The callers supply persisted values.
"""
from __future__ import annotations

from html import escape
from .design_system import kpi_icon

_ACCENTS = frozenset({'orange', 'blue', 'purple', 'teal'})


def render_kpi_card_panel(*, label: str, value: object, subtext: str,
                          icon_name: str = 'users', theme: str = 'orange') -> str:
    """Return a safe, static KPI card with one of four visual accent colors."""
    if theme not in _ACCENTS:
        raise ValueError('Tema de tarjeta no permitido')
    # kpi_icon uses a finite, trusted SVG icon map; dynamic text is escaped.
    return (
        f'<div class="pmo-superior-kpi accent-{theme}" role="group" '
        f'aria-label="{escape(str(label), quote=True)}">'
        '<div class="pmo-superior-kpi-heading">'
        f'<span class="pmo-superior-icon {theme}" aria-hidden="true">{kpi_icon(icon_name)}</span>'
        f'<span class="pmo-superior-kpi-label">{escape(str(label))}</span>'
        '</div>'
        f'<div class="pmo-superior-kpi-value">{escape(str(value))}</div>'
        f'<div class="pmo-superior-kpi-subtext">{escape(str(subtext))}</div>'
        '</div>'
    )


def render_clients_heading() -> str:
    """Clients section heading; the toolbar remains native Streamlit buttons."""
    return (
        '<section class="pmo-superior-intro">'
        '<div class="pmo-superior-context">'
        '<span class="pmo-superior-eyebrow">PASO 01 · GENERACIÓN DE CONCIENCIA</span>'
        '<span class="pmo-superior-stage">Exploración</span>'
        '</div>'
        '<h1>Clientes internos</h1>'
        '<p>Directorio único de interesados de la PMO; integrado con los diez pasos.</p>'
        '</section>'
    )


def render_contact_note() -> str:
    """Explain the real-world evidence rule already used by the KPI calculation."""
    return (
        '<div class="pmo-superior-info" role="note">'
        '<span class="pmo-superior-info-icon" aria-hidden="true">'
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
        'stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/>'
        '<path d="M12 11v5M12 7.5h.01"/></svg></span>'
        '<span><strong>Contacto comprobado</strong> = cliente activo con al menos una interacción '
        'o consulta formal registrada. Una respuesta del Paso 02 no se cuenta como contacto; '
        'el estado manual de relacionamiento es independiente.</span></div>'
    )


def render_directory_header(record_count: int) -> str:
    """Table section caption with the actual number of records in the directory."""
    if record_count < 0:
        raise ValueError('Número de registros inválido')
    return (
        '<div class="pmo-superior-directory-head">'
        '<div class="pmo-superior-directory-title-group">'
        f'<span class="pmo-superior-icon orange" aria-hidden="true">{kpi_icon("users")}</span>'
        '<div><h2>Directorio de clientes</h2><p>Perfiles, responsables y nivel de relacionamiento.</p></div>'
        '</div>'
        f'<span class="pmo-superior-count">{int(record_count)} registros</span>'
        '</div>'
    )
