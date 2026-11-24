"""Sidebar executive presentation · PMO FLYWHEEL CENS V0.38.4.

This module renders visual markup and loads CSS; it NEVER creates or replaces
navigation widgets. `pmo.ui.sidebar` retains its original st.radio instances,
state keys, widget values, and associated functionality.
"""
from __future__ import annotations
from pathlib import Path
import html
import streamlit as st

CSS_PATH = Path(__file__).resolve().parent / 'assets' / 'css' / 'panel-flywheel.css'
SIDEBAR_V0389_CSS = Path(__file__).resolve().parent / 'assets' / 'css' / 'sidebar-panel-v0389.css'

ICON_SVG = {
    'layers': '<path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 12 9 5 9-5M3 16l9 5 9-5"/>',
    'grid': '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    'map': '<path d="m3 6 6-3 6 3 6-3v15l-6 3-6-3-6 3V6zM9 3v15M15 6v15"/>',
}

def _icon(name: str) -> str:
    path = ICON_SVG.get(name, ICON_SVG['layers'])
    return ('<svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" '
            'fill="none" stroke="currentColor" stroke-width="1.8" '
            'stroke-linejoin="round" stroke-linecap="round">' + path + '</svg>')

def apply_panel_theme() -> None:
    """Apply after legacy styles. No JavaScript, routing, state, or DB access."""
    from .sidebar_icon_catalog import nav_icon_css
    # Importante: esta capa va AL FINAL para prevalecer sobre CSS heredado.
    content = ('<style>\n' + CSS_PATH.read_text(encoding='utf-8') + '\n'
               + SIDEBAR_V0389_CSS.read_text(encoding='utf-8') + '\n'
               + nav_icon_css() + '\n</style>')
    st.markdown(content, unsafe_allow_html=True)

def render_sidebar_branding() -> None:
    svg = ('<svg aria-hidden="true" viewBox="0 0 38 38" width="40" height="40">'
           '<rect x="4" y="4" width="30" height="30" rx="7" fill="none" stroke="currentColor" stroke-width="2.5"/>'
           '<path d="M10 28 28 10" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round"/></svg>')
    st.markdown('<div class="pmo-brand pmo-brand-pro pmo-brand-panel">'
                '<span class="pmo-logo-panel">' + svg + '</span>'
                '<span class="pmo-brand-copy"><strong>PMO FLYWHEEL</strong>'
                '<small>CENS · GESTIÓN DE VALOR</small></span></div>',
                unsafe_allow_html=True)

def render_section_heading(title: str, icon: str='grid') -> None:
    st.markdown('<div class="pmo-side-label pmo-panel-section">' + _icon(icon)
                + '<span>' + html.escape(title) + '</span></div>',
                unsafe_allow_html=True)

def render_component_heading() -> None:
    st.markdown('<div class="pmo-panel-separator" role="presentation"></div>',
                unsafe_allow_html=True)
    render_section_heading('COMPONENTES DEL PASO', 'grid')

def render_sidebar_footers(step_num: int, total_steps: int = 10) -> None:
    """Position, not methodological execution. No external data or progress inference."""
    try:
        position = max(1, min(int(step_num), int(total_steps)))
        total = max(1, int(total_steps))
    except (TypeError, ValueError):
        position, total = 1, 10
    width = round(position / total * 100)
    st.markdown('<div class="pmo-sidebar-bottom pmo-panel-location">'
                '<div class="pmo-panel-location-head">' + _icon('map') +
                '<span>Ubicación en el recorrido</span></div>'
                f'<strong>Paso {position} de {total}</strong>'
                '<small>Posición metodológica en el Flywheel; no indica ejecución.</small>'
                '<div class="pmo-progress" role="img" '
                f'aria-label="Ubicación metodológica: paso {position} de {total}">'
                f'<span style="width:{width}%"></span></div></div>',
                unsafe_allow_html=True)
