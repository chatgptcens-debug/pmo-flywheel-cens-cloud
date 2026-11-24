"""Localización exacta de registros sin reescribir las rutas originales."""
from .alpha06_transversal import SEARCH,reader
import sqlite3
from .alpha_navigation import STEPS

COMPONENTS={
 'Clientes':'Clientes internos','Eventos':'Eventos y campañas','Necesidades':'Necesidades y evidencias','Diagnósticos':'Plan y contexto','Evidencias de necesidades':'Necesidades y evidencias','Propuestas':'Soluciones, validación y hoja de ruta','Servicios diseñados':'Catálogo y fichas de servicios','Incorporación':'Plan de incorporación','Solicitudes':'Gestión de solicitudes','Monitoreo':'Desempeño integral','Mejoras':'Plan de mejora','Beneficios':'Matriz de beneficios y compromisos','Historias de valor':'Historias y reconocimiento'}

def exact(category, record_id, path=None):
    if category not in SEARCH:return None
    try:
        with reader(path) as c:
            row=c.execute('SELECT * FROM ('+SEARCH[category][1]+') WHERE id=?',(record_id,)).fetchone()
            return dict(row) if row else None
    except sqlite3.Error:return None

def target(category,record_id,path=None):
    if exact(category,record_id,path) is None:return None
    n=SEARCH[category][0]
    key='pmo_active_page' if n==1 else f'pmo_active_p{n}_page'
    result={'pmo_active_step':STEPS[n-1],key:COMPONENTS[category]}
    if category=='Clientes':
        result.update(current_client_id=record_id,pmo_c_search='',pmo_c_department='Todas',pmo_c_status='Activos',pmo_c_select_all=False,alpha02_open_client360=True)
    if category=='Servicios diseñados':result['a03_service_pick']=record_id;result['b02_expand_service']=True
    if category=='Diagnósticos':result['p2_pending_diagnostic']=record_id
    if category in ('Necesidades','Evidencias de necesidades'):
        table='p2_necesidades' if category=='Necesidades' else 'p2_evidencias'
        try:
            with reader(path) as c:
                row=c.execute(f'SELECT diagnostico_id FROM {table} WHERE id=?',(record_id,)).fetchone()
                if row:
                    diag=row[0];result['p2_pending_diagnostic']=diag
                    if category=='Necesidades':
                        result['p2v03917_needs_view']='Explorador de necesidades'
                        for k in ('dep','out','state','client'):result[f'a02_{k}_{diag}']=None
                        result[f'a02_search_{diag}']='';result[f'a02_need_{diag}']=record_id
                    else:result['p2v03917_needs_view']='Repositorio de evidencias'
        except sqlite3.Error:pass
    return result

def open_source(category,record_id):
    import streamlit as st
    r=target(category,record_id)
    if r:
        if category=='Clientes':st.session_state['b02_grid_generation']=st.session_state.get('b02_grid_generation',0)+1
        st.session_state.update(r)
    else:st.session_state['b02_search_missing']=True
