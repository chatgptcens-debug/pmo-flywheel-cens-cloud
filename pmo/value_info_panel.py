"""Tarjeta informativa corporativa reutilizable, sin efectos en datos ni estados."""
from html import escape
import streamlit as st

def info_panel(title: str, message: str, *, detail: str = '') -> None:
    title=escape(str(title));message=escape(str(message));detail=escape(str(detail))
    st.markdown("""<style>.pmo-info-blue{background:linear-gradient(130deg,#EAF4FE,#F5F9FF);border:1px solid #C9E0F7;border-left:4px solid #2475BD;border-radius:13px;padding:15px 19px;margin:10px 0 18px;color:#17415E;box-shadow:0 4px 16px rgba(19,67,117,.035)}.pmo-info-blue strong{display:block;color:#164A72;font-size:14px;margin-bottom:4px}.pmo-info-blue p{font-size:12.5px;margin:0;line-height:1.5}.pmo-info-blue small{display:block;color:#546E85;margin-top:8px}</style>""",unsafe_allow_html=True)
    st.markdown(f'<div class="pmo-info-blue"><strong>{title}</strong><p>{message}</p>'+ (f'<small>{detail}</small>' if detail else '')+'</div>',unsafe_allow_html=True)
