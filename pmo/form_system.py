"""Estándar único de formularios corporativos, compartido por los diez pasos.

Solo CSS y componentes presentacionales: preserva datos, validaciones, widgets y rutas
existentes. Nuevos formularios deberían usar section_header() y form_note().
"""
from __future__ import annotations
import html
from pathlib import Path
import streamlit as st

STYLE=Path(__file__).resolve().parent/'assets'/'forms_standard_v031.css'

def apply_form_standard():
    st.markdown('<style>\n'+STYLE.read_text(encoding='utf-8')+'\n</style>',unsafe_allow_html=True)

def section_header(step:str,title:str,caption:str=''):
    def esc(x):return html.escape(str(x))
    st.markdown('<div class="pmo31-form-head"><span>PASO '+esc(step)+' · REGISTRO CORPORATIVO</span>'
                '<h3>'+esc(title)+'</h3><p>'+esc(caption)+'</p></div>',unsafe_allow_html=True)

def form_note(message:str):
    st.markdown('<div class="pmo31-form-note">'+html.escape(str(message))+'</div>',unsafe_allow_html=True)
