"""Iconos SVG locales y reglas de decoracion para la navegacion existente.

Este catalogo SOLO produce CSS. No crea controles, estados, rutas o callbacks.
Claves: unicamente las claves st.radio estables ya definidas en pmo.ui.
"""
from __future__ import annotations
from urllib.parse import quote

# Trazos basados en geometria SVG simple; no incluye fuentes ni CDNs.
PATHS = {
    'file': '<path d="M6 2h9l4 4v16H6zM15 2v5h4M9 11h7M9 15h7M9 19h5"/>',
    'chart': '<path d="M3 20h18M6 17v-5h3v5M11 17V6h3v11M16 17V9h3v8"/>',
    'clipboard': '<rect x="5" y="4" width="14" height="18" rx="2"/><path d="M9 4V2h6v2M8 10h8M8 14h8M8 18h5"/>',
    'users': '<circle cx="9" cy="8" r="3"/><path d="M3 20v-2a6 6 0 0 1 12 0v2M16 6a3 3 0 0 1 0 6M17 15a5 5 0 0 1 4 5"/>',
    'target': '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><path d="m12 12 7-7"/>',
    'layers': '<path d="m12 3 9 5-9 5-9-5zM3 12l9 5 9-5M3 16l9 5 9-5"/>',
    'flag': '<path d="M5 22V3M5 4h14l-3 5 3 5H5"/>',
    'sheet': '<path d="M4 3h16v18H4zM4 9h16M10 9v12M4 15h16"/>',
    'network': '<rect x="9" y="2" width="6" height="6" rx="1"/><rect x="2" y="16" width="6" height="6" rx="1"/><rect x="16" y="16" width="6" height="6" rx="1"/><path d="M12 8v4M5 16v-4h14v4"/>',
    'check': '<circle cx="12" cy="12" r="9"/><path d="m7 12 3 3 7-7"/>',
    'shield': '<path d="M12 2 20 5v6c0 6-4 9-8 11-4-2-8-5-8-11V5zM8 12l3 3 5-6"/>',
    'folder': '<path d="M3 6h7l2 3h9v12H3z"/>',
    'book': '<path d="M3 4h8l1 2 1-2h8v16h-8l-1 2-1-2H3zM12 6v14"/>',
    'calendar': '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4M17 3v4M3 10h18"/>',
    'chat': '<path d="M4 4h16v13H9l-5 4zM8 9h8M8 13h6"/>',
    'clock': '<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/>',
    'globe': '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c6 6 6 12 0 18M12 3c-6 6-6 12 0 18"/>',
    'award': '<circle cx="12" cy="8" r="5"/><path d="m8 13-2 9 6-3 6 3-2-9"/>',
    'settings': '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2"/>',
    'trend': '<path d="M3 18h18M4 14l5-5 4 3 7-8M16 4h4v4"/>',
    'edit': '<path d="m5 17 11-11 3 3-11 11-4 1zM14 8l3 3"/>',
    'grid': '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    'rocket': '<path d="M5 16c2-6 7-11 15-12-1 8-6 13-12 15l-3-3zM11 13l-3-3M6 18l-2 4 4-2"/>',
    'package': '<path d="m12 2 9 5-9 5-9-5 9-5zM3 7v10l9 5 9-5V7M12 12v10"/>',
}

# Ordered by the real, existing module radio options. The CSS is positional only;
# no application metadata or option order is changed.
COMPONENT_ICONS = {
    'pmo_active_page': ('users','book','calendar','chat','chart','shield','clipboard'),
    'pmo_active_p2_page': ('file','chart','clipboard','users','target','layers','flag','sheet','network','check','shield','folder'),
    'pmo_active_p3_page': ('grid','target','edit'),
    'pmo_active_p4_page': ('book','chart','users','shield'),
    'pmo_active_p5_page': ('rocket','chat','target','check','shield'),
    'pmo_active_p6_page': ('grid','clipboard','chart','shield'),
    'pmo_active_p7_page': ('trend','clock','file','chat','shield'),
    'pmo_active_p8_page': ('target','chart','layers','edit','clock'),
    'pmo_active_p9_page': ('grid','chart','award','trend','shield'),
    'pmo_active_p10_page': ('chat','award','target','file','shield'),
}


def svg_data(icon_name: str) -> str:
    path = PATHS.get(icon_name, PATHS['file'])
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
           f'stroke="#F2EFFD" stroke-width="1.85" stroke-linecap="round" '
           f'stroke-linejoin="round">{path}</svg>')
    return 'data:image/svg+xml,' + quote(svg, safe='')


def nav_icon_css() -> str:
    """Generate key-scoped icon styles; no HTML-only navigation."""
    css = ['/* Iconos de componentes, enlazados exclusivamente a radios reales. */']
    for key, icons in COMPONENT_ICONS.items():
        for index, icon in enumerate(icons, start=1):
            css.append(
                f'[data-testid="stSidebar"] .st-key-{key} [role="radiogroup"] > label:nth-child({index})::before '
                '{background-image:url("' + svg_data(icon) + '")!important;}'
            )
    return '\n'.join(css)
