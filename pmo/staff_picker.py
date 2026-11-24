"""Selector central de responsables PMO (Paso 04), sin modificar la identidad de clientes.

Los formularios existentes persisten el nombre por compatibilidad histórica. Cuando el
modelo admite una referencia estable puede obtenerse con ``member_id_for_name``.
Los valores históricos ajenos al equipo se preservan en edición pero NO pueden
crearse desde un formulario nuevo.
"""
from __future__ import annotations

from . import step4

EMPTY = '__pmo_sin_asignar__'
LEGACY = '__pmo_responsable_historico__'


def roster(path=None):
    """Integrantes existentes; conserva IDs UUID, cargo y capacidad originales."""
    try:
        people=step4.members(path=path)
    except Exception:
        return []
    from .public_codes import code_map
    try: codes=code_map('integrante',path)
    except Exception: codes={}
    return [dict(id=p['id'],nombre=p['nombre'],rol=p['rol'],
                 codigo=codes.get(p['id'],p['id'][:8]),capacidad=p['capacidad'])
            for p in people]


def member_id_for_name(name,path=None):
    """Resuelve una persona solo si su nombre no es ambiguo (cero o varios → None)."""
    try: people=step4.members(path=path)
    except Exception: people=[]
    matches=[p['id'] for p in people if p['nombre'].strip().casefold()==str(name or '').strip().casefold()]
    return matches[0] if len(matches)==1 else None


def choice_options(current='',path=None,current_id=None):
    """Datos puros para tests y selectores, sin efectos sobre los registros históricos."""
    people=roster(path)
    opts={EMPTY:'— Seleccionar integrante del equipo PMO —'}
    for p in people:
        opts[p['id']]=f"{p['codigo']} · {p['nombre']} · {p['rol']}"
    selected=(current_id if current_id in opts else
              next((p['id'] for p in people if p['nombre'].strip().casefold()==str(current or '').strip().casefold()),EMPTY))
    if str(current or '').strip() and selected==EMPTY:
        opts[LEGACY]='Histórico no vinculado · '+str(current).strip()
        selected=LEGACY
    return opts, selected, people


def staff_picker(label,value='',*,key=None,disabled=False,help=None,required=False,optional=True,current_id=None,return_id=False,**kwargs):
    """Reemplazo controlado de ``st.text_input`` para responsables operativos.

    Devuelve el nombre en formato legado; nunca registra nuevos integrantes desde
    otra pantalla. El identificador se selecciona como valor interno de la lista.
    """
    import streamlit as st
    options,current,people=choice_options(value,current_id=current_id)
    if not people:
        st.caption('Sin integrantes en Paso 04 → Recursos y competencias → Equipo PMO. Registra allí el responsable antes de asignarlo.')
    # La selección vacía se mantiene explícita: nunca asignar automáticamente al primer integrante.
    selected=st.selectbox(label,list(options),index=list(options).index(current),
                          format_func=lambda k:options[k],key=key,disabled=disabled or not bool(people),
                          help=help or 'Directorio único de integrantes: Paso 04 → Recursos y competencias → Equipo PMO.',
                          **{k:v for k,v in kwargs.items() if k in ('label_visibility','on_change','args','kwargs')})
    if selected==LEGACY:return (str(value or '').strip(),None) if return_id else str(value or '').strip()
    if selected==EMPTY:return ('',None) if return_id else ''
    name=next(p['nombre'] for p in people if p['id']==selected)
    return (name,selected) if return_id else name
