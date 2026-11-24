"""Consultas 360° y explorador. No modifica datos, ni vincula por nombre."""
from contextlib import closing
from pathlib import Path
import sqlite3
from collections import Counter
from .config import database_path

# Queries fixed; identity link always explicit. No inferred links from labels.
QUERIES = {
 'Eventos': ('SELECT e.id,e.titulo,e.fecha,e.estado,a.asistio FROM p1_asistencias a JOIN p1_eventos e ON e.id=a.evento_id WHERE a.cliente_id=? ORDER BY e.fecha DESC',),
 'Interacciones': ('SELECT id,fecha,canal,motivo,descripcion,responsable,resultado FROM p1_interacciones WHERE cliente_id=? ORDER BY fecha DESC',),
 'Compromisos': ('SELECT id,interaccion_id,descripcion,responsable,vence_en,estado,cerrado_en FROM p1_compromisos WHERE cliente_id=? ORDER BY vence_en, id',),
 'Consultas': ('SELECT id,asunto,estado,creado_en,respondido_en FROM p1_consultas WHERE cliente_id=? ORDER BY creado_en DESC',),
 'Encuestas': ('SELECT fase,familiaridad,utilidad,interes,creado_en FROM p1_encuestas WHERE cliente_id=? ORDER BY creado_en DESC',),
 'Levantamientos': ('SELECT l.id,d.nombre AS diagnostico,l.metodo,l.fecha,l.estado,l.fuente FROM p2_levantamientos l JOIN p2_diagnosticos d ON d.id=l.diagnostico_id WHERE l.cliente_id=? ORDER BY l.fecha DESC',),
 'Expectativas': ('SELECT d.nombre AS diagnostico,e.posicion,e.resultado_id,e.actualizado_en FROM p2_expectativas e JOIN p2_diagnosticos d ON d.id=e.diagnostico_id WHERE e.cliente_id=? ORDER BY d.id,e.posicion',),
 'Necesidades': ('SELECT n.id,d.nombre AS diagnostico,n.problema,n.ganancia,n.resultado_id,n.estado,n.impacto,n.fuente FROM p2_necesidades n JOIN p2_diagnosticos d ON d.id=n.diagnostico_id WHERE n.cliente_id=? ORDER BY n.creado_en DESC',),
 'Propuestas': ("SELECT id,nombre,estado,beneficio,actualizado_en FROM p3_soluciones WHERE cliente_id=? AND upper(codigo) NOT LIKE 'DEMO%' AND upper(codigo) NOT LIKE 'PRACTICA%' ORDER BY actualizado_en DESC",),
 'Solicitudes': ('SELECT t.folio,t.titulo,t.estado,t.creado_en,c.nombre AS servicio FROM p6_tickets t LEFT JOIN p6_catalog c ON c.id=t.servicio_id WHERE t.cliente_id=? AND t.demo=0 ORDER BY t.creado_en DESC',),
 'Beneficios': ('SELECT id,beneficio,indicador,estado,fecha_validacion FROM p9_beneficios WHERE cliente_id=? AND es_demo=0 ORDER BY actualizado_en DESC',),
 'Retroalimentación operativa': ('SELECT folio,titulo,calificacion,calificacion_comentario,calificado_en FROM p6_tickets WHERE cliente_id=? AND demo=0 AND calificacion IS NOT NULL ORDER BY calificado_en DESC',),
}

def read_client(client_id, path=None):
    result={k:None for k in QUERIES}
    try:
        with closing(sqlite3.connect(Path(path or database_path()).resolve().as_uri()+'?mode=ro',uri=True,timeout=3)) as c:
            c.row_factory=sqlite3.Row
            c.execute('PRAGMA query_only=ON');c.execute('BEGIN')
            for label,(sql,) in QUERIES.items():
                try:result[label]=[dict(row) for row in c.execute(sql,(client_id,))]
                except sqlite3.Error: pass
    except sqlite3.Error: pass
    return result

def filtered_needs(rows, *, dependency=None, outcome=None, state=None, client=None, text=''):
    q=text.strip().casefold()
    return [r for r in rows if (dependency is None or r.get('dependencia')==dependency)
            and (outcome is None or r.get('resultado_id')==outcome)
            and (state is None or r.get('estado')==state)
            and (client is None or r.get('cliente_id')==client)
            and (not q or q in ' '.join(str(r.get(k) or '') for k in ('problema','ganancia','fuente','dependencia')).casefold())]

def coverage(people, records, field):
    """Denominator is active directory, not survey sample; distinct IDs only."""
    seen={r['cliente_id'] for r in records if r.get('cliente_id')}
    groups={}
    for p in people:
        if p.get('activo'):
            groups.setdefault(str(p.get(field) or 'Sin clasificar'),set()).add(p['id'])
    return [{'Grupo':g,'Activos':len(ids),'Con levantamiento':len(ids & seen),
             'Cobertura (%)':round(100*len(ids & seen)/len(ids),1)} for g,ids in sorted(groups.items())]

def render_client(client):
    import streamlit as st
    from .step2_catalog import OUTCOMES
    from .events_media import list_attachments, file_path
    cid=client['id']; records=read_client(cid)
    st.subheader('Ficha 360° del cliente')
    st.write(client['nombre']);st.caption(f"{client.get('codigo','')} · {client.get('dependencia','')} · {client.get('rol_especifico') or client.get('segmento') or 'Sin rol'}")
    st.caption('Historial acumulado por ID original. No se imputan registros por nombre ni se deduce avance metodológico.')
    for cols,keys in [(st.columns(3),('Eventos','Necesidades','Solicitudes')),(st.columns(3),('Expectativas','Propuestas','Beneficios'))]:
        for col,k in zip(cols,keys): col.metric(k,'—' if records[k] is None else len(records[k]))
    tab=st.radio('Perspectiva del cliente',['Exploración','Diseño','Despliegue','Mejora','Realización'],horizontal=True,key=f'a02_client_view_{cid}')
    sections={'Exploración':('Eventos','Interacciones','Compromisos','Consultas','Encuestas','Levantamientos','Expectativas','Necesidades'),'Diseño':('Propuestas',),'Despliegue':('Solicitudes',),'Mejora':('Retroalimentación operativa',),'Realización':('Beneficios',)}[tab]
    for k in sections:
        rows=records[k]
        with st.expander(k,expanded=k=='Necesidades'):
            if rows is None: st.warning('Fuente no disponible en esta base.')
            elif not rows: st.info('No hay registros vinculados por ID.')
            else:
                display=[{**r, **({'resultado':OUTCOMES.get(r.get('resultado_id'),'Sin asignar')} if 'resultado_id' in r else {})} for r in rows]
                st.dataframe(display,hide_index=True,use_container_width=True)
                if k=='Eventos':
                    selected=st.selectbox('Evidencias de evento',[r['id'] for r in rows],format_func=lambda id:next(r['titulo'] for r in rows if r['id']==id),key=f'a02_event_{cid}')
                    if st.checkbox('Mostrar imágenes y referencias registradas',key=f'a02_gallery_{cid}_{selected}'):
                        attachments=list_attachments('evento',selected)
                        if not attachments:st.caption('No hay adjuntos disponibles.')
                        for a in attachments:
                            p=file_path(a)
                            st.write(a.get('titulo') or a.get('nombre'))
                            if p and a.get('mime','').startswith('image/') and p.stat().st_size<=10*1024*1024:st.image(str(p),width=240)
                            else:st.caption('Consultar archivo en Eventos y campañas.' if p else 'Archivo no disponible en la copia.')
    st.caption('Los beneficios registrados no equivalen a valor validado. Las acciones de mejora y el reconocimiento sin vínculo directo por ID se consultan en Pasos 08 y 10; no se infieren relaciones.')

def render_needs(diag):
    import streamlit as st
    from . import step2 as p2
    from .step2_catalog import OUTCOMES
    from .clients import list_clients
    rows=p2.needs(diag); evidence=p2.evidence(diag)
    people=list_clients(); names={p['id']:p['nombre'] for p in people}
    st.subheader('Explorador de necesidades · consulta')
    st.caption('Solo el diagnóstico seleccionado. Los filtros no cambian registros, estados ni el motor V5.')
    a,b,c=st.columns(3)
    dep=a.selectbox('Dependencia',[None,*sorted({r['dependencia'] for r in rows if r.get('dependencia')})],format_func=lambda v:v or 'Todas',key=f'a02_dep_{diag}')
    out=b.selectbox('Resultado esperado',[None,*OUTCOMES],format_func=lambda v:OUTCOMES[v] if v else 'Todos',key=f'a02_out_{diag}')
    state=c.selectbox('Estado',[None,*sorted({r['estado'] for r in rows if r.get('estado')})],format_func=lambda v:v or 'Todos',key=f'a02_state_{diag}')
    client=st.selectbox('Cliente',[None,*sorted({r['cliente_id'] for r in rows if r.get('cliente_id')},key=lambda v:names.get(v,v))],format_func=lambda v:names.get(v,v) if v else 'Todos',key=f'a02_client_{diag}')
    text=st.text_input('Buscar problema, ganancia o fuente',key=f'a02_search_{diag}')
    subset=filtered_needs(rows,dependency=dep,outcome=out,state=state,client=client,text=text)
    linked={r.get('necesidad_id') for r in evidence if r.get('necesidad_id')}
    for col,(label,value) in zip(st.columns(3),[('Necesidades filtradas',len(subset)),('Validadas',sum(r['estado']=='Validada' for r in subset)),('Con evidencia vinculada',sum(r['id'] in linked for r in subset))]):col.metric(label,value)
    if not subset:st.info('No hay necesidades con los filtros seleccionados.');return
    counts=Counter(OUTCOMES.get(r.get('resultado_id'),'Sin asignar') for r in subset)
    st.dataframe([{'Resultado esperado':k,'Necesidades':v} for k,v in counts.most_common()],hide_index=True,use_container_width=True)
    selected=st.selectbox('Consultar necesidad',[r['id'] for r in subset],format_func=lambda v:next(r['problema'][:100] for r in subset if r['id']==v),key=f'a02_need_{diag}')
    n=next(r for r in subset if r['id']==selected)
    l,r=st.columns(2)
    with l:
        st.markdown('**Problema / dificultad**');st.write(n['problema'])
    with r:
        st.markdown('**Ganancia / resultado deseado**');st.write(n['ganancia'])
    st.write(f"Resultado asociado: {OUTCOMES.get(n.get('resultado_id'),'Sin asignar')} · Estado: {n['estado']} · Impacto: {n['impacto']}")
    st.caption('Fuente declarada: '+str(n.get('fuente') or 'Sin fuente'))
    refs=[{k:v for k,v in row.items() if k in ('titulo','tipo','url','responsable','fecha')} for row in evidence if row.get('necesidad_id')==selected]
    if refs:st.dataframe(refs,hide_index=True,use_container_width=True)
    else:st.caption('Sin evidencia enlazada directamente a esta necesidad.')

def render_coverage(diag):
    import streamlit as st
    from . import step2 as p2
    from .clients import list_clients
    from .v0391_clients import client_role
    people=[{**p,'rol_especifico':client_role(p)} for p in list_clients()]; records=p2.interviews(diag)
    st.subheader('Cobertura del diagnóstico')
    st.caption('Denominador: clientes activos del directorio completo (no la muestra). Numerador: clientes activos distintos con levantamiento registrado en este diagnóstico, sin inferir respuesta completa.')
    for field,title in [('dependencia','Dependencia'),('rol_especifico','Rol')]:
        st.markdown('**'+title+'**');st.dataframe(coverage(people,records,field),hide_index=True,use_container_width=True)
