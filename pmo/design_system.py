"""PMO FLYWHEEL CENS · V0.9 · Sistema de diseño corporativo.

Capa exclusivamente visual. No ejecuta consultas, callbacks, migraciones ni cálculos.
Se carga después de los estilos V0.8 para mantener la navegación y componentes
sin sustituir ninguno de los controles nativos de Streamlit.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

STYLE_PATH = Path(__file__).resolve().parent / 'assets' / 'corporate_theme.css'
PREMIUM_STYLE_PATH = Path(__file__).resolve().parent / 'assets' / 'premium_ux.css'
PRO_CSS_PATHS = tuple(Path(__file__).resolve().parent / 'assets' / 'css' / n for n in ('theme-tokens.css','sidebar-pro.css','cards-pro.css','sidebar-executive-v0381.css','panel-superior.css'))


def apply_corporate_theme() -> None:
    """Inyecta únicamente CSS corporativo, sin crear widgets ni alterar estado."""
    st.markdown('<style>\n' + STYLE_PATH.read_text(encoding='utf-8') + '\n'
                + PREMIUM_STYLE_PATH.read_text(encoding='utf-8') + '\n'
                + '\n'.join(p.read_text(encoding='utf-8') for p in PRO_CSS_PATHS) + '\n</style>',
                unsafe_allow_html=True)


# Lucide-style stroke icons rendered in existing KPI containers only.
# The original KPI values, labels and widget behavior remain unchanged.
_ICON_PATHS = {
    'users': '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
    'chart': '<path d="M3 3v18h18"/><path d="m7 16 5-5 4 3 5-7"/>',
    'target': '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
    'award': '<circle cx="12" cy="8" r="5"/><path d="m8 13-2 9 6-4 6 4-2-9"/>',
    'clock': '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    'book': '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2Z"/>',
    'layers': '<path d="m12 3-9 6 9 6 9-6-9-6Z"/><path d="m3 13 9 6 9-6"/>',
    'check': '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="m8 12 3 3 5-6"/>',
    'calendar': '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/>',
    'message': '<path d="M21 11.5a8.5 8.5 0 0 1-12.3 7.6L3 21l1.9-5.7A8.5 8.5 0 1 1 21 11.5Z"/>',
    'file': '<path d="M6 2h8l5 5v15H6zM14 2v5h5M9 12h7M9 16h7"/>',
}
_ICON_ALIASES = {
    '♙': 'users', '♧': 'users', '◈': 'layers', '▦': 'layers',
    '⌁': 'chart', '↗': 'chart', '▥': 'chart', '▤': 'file',
    '◎': 'target', '◉': 'target', '☆': 'award', '◴': 'clock',
    '▧': 'calendar', '▣': 'calendar', '☷': 'file', '✓': 'check',
    '☑': 'check', '▱': 'file', '✦': 'award', '⚙': 'layers',
    '♢': 'layers', '◇': 'layers', '□': 'layers', '✉': 'message',
    '○': 'target', '▨': 'layers', '▩': 'layers',
}

def kpi_icon(symbol: str) -> str:
    """Replaces only ornamental KPI glyphs with a consistent outline SVG."""
    key = _ICON_ALIASES.get(symbol, symbol if symbol in _ICON_PATHS else 'layers')
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" '
            'viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" '
            'aria-hidden="true">' + _ICON_PATHS[key] + '</svg>')


# Capa exclusiva de presentación para los cuadros de la matriz 30 x 26.
# Devuelve estilos de celda; jamás altera valores, orden, filtros ni cabeceras.
def matrix_intensity_style(value: object) -> str:
    """Escala legible 0–4; el 0 es neutral, no implica causalidad nula."""
    palette = {
        0: ('#F7F8FA', '#65718C'),
        1: ('#F1E7FF', '#443D6C'),
        2: ('#E3D8F5', '#302B56'),
        3: ('#D8C6EF', '#302B56'),
        4: ('#C7B2E7', '#232747'),
    }
    try:
        i = int(value)
        if str(value) not in {str(i), str(float(i))} or i not in palette:
            return ''
    except (TypeError, ValueError, OverflowError):
        return ''
    background, foreground = palette[i]
    return f'background-color: {background}; color: {foreground}; font-weight: 650;'


def matrix_status_style(value: object) -> str:
    """Distingue estados documentales sin traducir ni reclasificar su significado."""
    value = str(value)
    if value in {'X2_documentado', 'DOCUMENTADO', 'VALIDADO'}:
        return 'background-color: #EDF7F2; color: #176B4B; font-weight: 600;'
    if value in {'Nuevo_no_validado', 'PENDIENTE'}:
        return 'background-color: #FFF4E9; color: #81582A; font-weight: 600;'
    if value in {'RECHAZADO'}:
        return 'background-color: #FFF0F1; color: #A02D39; font-weight: 600;'
    return 'color: #65718C;'

# Alpha 01: reutiliza tokens institucionales sin cambiar los formularios existentes.
def apply_alpha_theme():
    css = Path(__file__).resolve().parent / 'assets' / 'css' / 'alpha01.css'
    st.markdown('<style>' + css.read_text(encoding='utf-8') + '</style>', unsafe_allow_html=True)


def alpha_heading(eyebrow, title, subtitle):
    import html
    st.markdown('<div class="alpha01-heading"><small>' + html.escape(eyebrow) + '</small><h2>' + html.escape(title) + '</h2><p>' + html.escape(subtitle) + '</p></div>', unsafe_allow_html=True)


def alpha_metric(label, value, source):
    import html
    st.markdown('<div class="alpha01-metric"><small>' + html.escape(label) + '</small><strong>' + ('—' if value is None else str(int(value))) + '</strong><p>' + html.escape(source if value is not None else 'No disponible · ' + source) + '</p></div>', unsafe_allow_html=True)
