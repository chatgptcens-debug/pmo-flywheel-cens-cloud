"""Selector único de personas del Paso 1; no crea clientes ni reescribe referencias.

Los formularios de grupos/roles no deben forzar una persona física.
Se permite un valor histórico/manual cuando la persona aún no está en el directorio.
"""
from __future__ import annotations
from .clients import list_clients

MANUAL='__manual__'
NONE='__none__'

def options(path=None,include_inactive=False):
    records=list_clients(status='Todos' if include_inactive else 'Activos',path=path)
    return {r['id']:r for r in records}

def choose_client(st,label,current='',key='pmo_client_select',optional=True,manual=True):
    rows=options(include_inactive=bool(str(current or "").strip()))
    byname=next((id for id,r in rows.items() if r['nombre'].casefold()==str(current or '').strip().casefold()),None)
    opts=([NONE] if optional else [])+list(rows)+( [MANUAL] if manual else [])
    if not opts:
        return st.text_input(label,value=current,key=key+'_free'),None,None
    default=byname if byname else MANUAL if manual and (current or not optional) else NONE if optional else opts[0]
    if default not in opts:default=opts[0]
    index=opts.index(default)
    selected=st.selectbox(label,opts,index=index,key=key,format_func=lambda x:
        'Sin vincular' if x==NONE else 'Escribir nombre manualmente / grupo no registrado' if x==MANUAL
        else f'{rows[x]["codigo"]} · {rows[x]["nombre"]}'+(' (inactivo)' if not rows[x].get('activo') else ''))
    if selected==NONE:return '',None,None
    if selected==MANUAL:
        val=st.text_input('Nombre manual / grupo (sin vínculo al directorio)',value=current,key=key+'_manual')
        return val,None,None
    return rows[selected]['nombre'],selected,rows[selected]
