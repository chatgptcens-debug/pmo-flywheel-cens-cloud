"""Capa visual global para todos los st.file_uploader de PMO FLYWHEEL CENS.

No sustituye controles Streamlit, no lee archivos y no modifica validaciones,
keys, formularios, límites, permisos ni los flujos de importación.
"""
from pathlib import Path
import streamlit as st

_CSS = Path(__file__).parent / 'assets' / 'upload_professional.css'
_MATRIX_CSS = Path(__file__).parent / 'assets' / 'step2_matrix_value_ring.css'

def apply_upload_ui():
    st.markdown('<style>\n' + _CSS.read_text(encoding='utf-8') + '\n' + _MATRIX_CSS.read_text(encoding='utf-8') + '\n</style>', unsafe_allow_html=True)
