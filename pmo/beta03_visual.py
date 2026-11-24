"""Capa visual final; no cambia rutas, widgets de negocio ni persistencia."""
from html import escape
from pathlib import Path
from .alpha_navigation import STEP_NAMES, STAGES
from .alpha02_sidebar import COLORS
from .alpha_guidance import GUIDANCE

CSS = Path(__file__).parent / 'assets/css/beta03.css'

def apply(st):
    st.markdown('<style>'+CSS.read_text(encoding='utf-8')+'</style>',unsafe_allow_html=True)

def context_html(number, page):
    if not isinstance(number,int) or not 1<=number<=10:
        raise ValueError('Paso inválido')
    i=(number-1)//2
    return (f'<section class="b03-context" style="--b03-stage:{COLORS[i]}">'
            f'<div class="b03-number">{number:02d}</div><div class="b03-context-copy">'
            f'<small>{escape(STAGES[i].upper())} · PASO {number:02d} DE 10</small>'
            f'<h2>{escape(STEP_NAMES[number-1])}</h2><p>{escape(GUIDANCE[number]["purpose"])}</p>'
            f'<div class="b03-component">COMPONENTE ACTUAL · {escape(str(page))}</div></div></section>')

def render_context(st,number,page):
    st.markdown(context_html(number,page),unsafe_allow_html=True)
