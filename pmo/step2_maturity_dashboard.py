"""V0.38.3: vista principal de la madurez institucional anual 0–5.

Las funciones anteriores de lectura 1–5 se conservan únicamente por
compatibilidad interna; no se invocan en el módulo Panorama y madurez.
Los resultados consolidados son independientes de PMOGA y del motor V5.
"""
from __future__ import annotations

from collections import defaultdict
from html import escape
import math

import streamlit as st

from . import step2 as p2
from .clients import ValidationError
from . import step2_maturity_annual as annual


STYLES = """
<style>
.p2m-kicker{color:#0D7887;font-size:11px;letter-spacing:1.2px;font-weight:800;text-transform:uppercase;margin-bottom:12px}
.p2m-kpi{background:#FFF;border:1px solid #E0E7EE;border-radius:15px;padding:18px 19px;min-height:135px;box-shadow:0 4px 20px rgba(20,55,75,.035)}
.p2m-label{font-size:12px;color:#627489;font-weight:650}.p2m-number{font-size:34px;line-height:1.55;font-weight:830;color:#14384A;letter-spacing:-.8px}
.p2m-note{font-size:11px;color:#8494A5}.p2m-accent{height:3px;width:33px;background:#0F9199;border-radius:4px;margin-top:7px}
.p2m-panel-title{font-size:16px;font-weight:800;color:#213C4B;margin-bottom:5px}.p2m-panel-sub{color:#71869A;font-size:12px;margin-bottom:13px}
.p2m-bar{display:grid;grid-template-columns:minmax(125px,1.1fr) minmax(125px,2fr) 65px;align-items:center;gap:10px;margin:14px 0}
.p2m-bar-name{font-size:12px;color:#385367;font-weight:650;overflow-wrap:anywhere}.p2m-track{height:10px;background:#E9F1F5;border-radius:9px;overflow:hidden}
.p2m-track>span{display:block;height:100%;background:#E59651;border-radius:9px}.p2m-bar-val{font-size:12px;color:#324B60;text-align:right;font-weight:750;font-variant-numeric:tabular-nums}
.p2m-stairs{display:flex;flex-direction:column;align-items:center;gap:7px;padding:4px 0 12px}.p2m-stair{color:white;min-height:38px;display:flex;align-items:center;justify-content:center;border-radius:7px;font-size:11px;font-weight:750;text-align:center;padding:7px 12px;max-width:100%;overflow-wrap:anywhere}
.p2m-annual-row{display:flex;justify-content:space-between;gap:12px;font-size:12px;margin:8px 0 3px;color:#385367}.p2m-annual-row b{font-variant-numeric:tabular-nums}.p2m-annual-track{height:7px;background:#E9F1F5;border-radius:8px;overflow:hidden}.p2m-annual-track span{display:block;height:100%;border-radius:8px;background:#0B81AB}.p2m-tag{font-size:11px;color:#637A8B;padding:6px 10px;border:1px solid #DFE9F0;border-radius:16px;display:inline-block;margin:3px;background:#F7FAFC}
@media(max-width:850px){.p2m-bar{grid-template-columns:minmax(85px,1fr) minmax(70px,1.3fr) 57px;gap:6px}.p2m-number{font-size:28px}}
</style>
"""


def summarize(rows):
    """Pure calculation: missing records produce no indices, never synthetic zeroes."""
    if not rows:
        return {'actual': None, 'deseado': None, 'brecha': None, 'dimensiones': 0}
    current = sum(float(r['actual']) for r in rows) / len(rows)
    desired = sum(float(r['deseado']) for r in rows) / len(rows)
    return {'actual': current, 'deseado': desired, 'brecha': desired-current, 'dimensiones': len(rows)}


def comparable_history(diagnostics, rows_by_id):
    """Comparisons need identical dimension sets and the same 1–5 source scale."""
    found = []
    for diag in diagnostics:
        vals = rows_by_id.get(diag['id'], [])
        if not vals:
            continue
        dims = frozenset(x['dimension'] for x in vals)
        stats = summarize(vals)
        found.append({'ciclo': str(diag['ciclo']), 'diagnostico': diag['nombre'],
                      'dimension_names': dims, **stats})
    return found


def _kpi(name, value, note, color='#10374B'):
    st.markdown(f'<div class="p2m-kpi"><div class="p2m-label">{escape(name)}</div>'
                f'<div class="p2m-number" style="color:{color}">{escape(value)}</div>'
                f'<div class="p2m-note">{escape(note)}</div><div class="p2m-accent"></div></div>',
                unsafe_allow_html=True)


def radar_svg(rows):
    """Inline responsive SVG; only persisted dimension values are shown."""
    if not rows:
        return ''
    count = len(rows)
    cx, cy, radius = 240, 185, 126
    def coord(i, score):
        a = (2*math.pi*i/count) - math.pi/2
        return (cx+radius*score/5*math.cos(a), cy+radius*score/5*math.sin(a))
    def points(vals):
        return ' '.join(f'{coord(i,float(v))[0]:.1f},{coord(i,float(v))[1]:.1f}' for i,v in enumerate(vals))
    grid = ''.join(f'<polygon points="{points([level]*count)}" fill="none" stroke="#E0E8EF" stroke-width="1"/>'
                   for level in range(1,6)) if count>=3 else ''
    spokes = ''.join(f'<line x1="{cx}" y1="{cy}" x2="{coord(i,5)[0]:.1f}" y2="{coord(i,5)[1]:.1f}" stroke="#E3EAF0"/>' for i in range(count))
    actual = [float(r['actual']) for r in rows]
    desired = [float(r['deseado']) for r in rows]
    if count >= 3:
        plots = (f'<polygon points="{points(desired)}" fill="#0A929A22" stroke="#0A929A" stroke-width="2.8"/>'
                 f'<polygon points="{points(actual)}" fill="#E58C5036" stroke="#E58C50" stroke-width="2.8"/>')
    else:
        plots = ''.join(f'<circle cx="{coord(i,v)[0]:.1f}" cy="{coord(i,v)[1]:.1f}" r="7" fill="{color}"/>'
                        for values,color in ((desired,'#0A929A'),(actual,'#E58C50')) for i,v in enumerate(values))
    labels=[]
    for i,row in enumerate(rows):
        a = (2*math.pi*i/count)-math.pi/2
        x,y = cx+162*math.cos(a), cy+162*math.sin(a)
        name=escape(str(row['dimension']))
        labels.append(f'<text x="{x:.1f}" y="{y:.1f}" fill="#365064" font-size="11" font-weight="650" text-anchor="middle">{name}</text>')
    legend = ('<rect x="130" y="354" width="10" height="10" rx="2" fill="#E58C50"/><text x="145" y="363" font-size="11" fill="#506579">Actual</text>'
              '<rect x="260" y="354" width="10" height="10" rx="2" fill="#0A929A"/><text x="275" y="363" font-size="11" fill="#506579">Deseado</text>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 480 378" width="100%" role="img" '
            f'aria-label="Gráfico radar de madurez actual y deseada">{grid}{spokes}{plots}{"".join(labels)}{legend}</svg>')


def _configuration(diag, rows):
    """The same audited 1–5 repository and validation already used in V0.37."""
    existing = {r['dimension']: r for r in rows}
    with st.expander('Configurar línea base · registrar o editar dimensiones', expanded=False):
        st.caption('Escala 1–5. Los campos se guardan en el expediente seleccionado, sin afectar el histórico anual 0–5 ni el PMOGA.')
        dim = st.selectbox('Dimensión', p2.MATURITY, key='p2m_dash_dim')
        old = existing.get(dim)
        with st.form('p2m_dash_form'):
            a,b = st.columns(2)
            current = a.select_slider('Nivel actual percibido (1–5)',options=[1,2,3,4,5],value=int(old['actual']) if old else 3)
            desired = b.select_slider('Nivel deseado (1–5)',options=[1,2,3,4,5],value=int(old['deseado']) if old else 4)
            source = a.text_input('Fuente de percepción *',value=str(old['fuente']) if old else '')
            actor = b.text_input('Responsable del registro *',value=str(old['responsable']) if old else '')
            submit = st.form_submit_button('Guardar dimensión',type='primary')
        if submit:
            try:
                p2.set_maturity(diag, dim, int(current), int(desired), source, actor)
                st.success('Dimensión guardada con trazabilidad.')
                st.rerun()
            except ValidationError as ex:
                st.error(str(ex))
        if not old:
            st.caption('Los niveles visibles antes de guardar son valores iniciales del control, no datos del tablero. Ningún indicador se calcula con ellos hasta guardar.')
        st.caption('El catálogo de captura vigente tiene cuatro dimensiones. El tablero representa dinámicamente todas las dimensiones efectivamente guardadas; ampliar el catálogo requiere una modificación contractual aparte.')


def render():
    """Vista institucional anual. Independiente del diagnóstico PMOGA.

    No altera ni elimina registros 1–5 previos: simplemente deja de
    utilizarlos en la interfaz principal de Panorama y madurez.
    """
    st.markdown(STYLES, unsafe_allow_html=True)
    st.markdown('<div class="p2m-kicker">MADUREZ INSTITUCIONAL · CONSULTA ANUAL</div>', unsafe_allow_html=True)
    st.caption('Resultados consolidados por año · Escala 0–5 · Dos escenarios. '
               'Fuente independiente del diagnóstico de expectativas y del motor de priorización.')
    from .step2_maturity_annual_ui import render_history
    render_history(None, None)
