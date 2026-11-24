"""V1.0 Alpha03: vistas consultivas del diseño de valor y servicio.
No modifica registros, aprobaciones, ANS ni el motor V5.
"""
from contextlib import closing
from pathlib import Path
import json
import sqlite3
from .config import database_path
from .step4_ans import extract_snapshot, digest

PAIRS={'dolores':{'aliviadores','servicios'},'ganancias':{'generadores','servicios'}}


def canvas_matches(cards, links):
    """Correspondencias explícitas por ID y zona, nunca por similitud de texto."""
    by_id={c['id']:c for c in cards}
    result=[]
    for card in cards:
        if card['zona'] not in PAIRS: continue
        targets=[]
        for link in links:
            a,b=link['origen_id'],link['destino_id']
            other=b if a==card['id'] else a if b==card['id'] else None
            target=by_id.get(other)
            if target and target['zona'] in PAIRS[card['zona']]:
                targets.append({'titulo':target['titulo'],'zona':target['zona'],'justificacion':link.get('justificacion',''),'id':target['id']})
        result.append({'id':card['id'],'zona':card['zona'],'titulo':card['titulo'],'detalle':card.get('detalle',''),'relaciones':targets})
    return result


def service_views(service_id, path=None):
    """Read-only consistent snapshot; missing schema is distinct from empty records."""
    queries={
      'Diseño':('SELECT * FROM p4_services WHERE id=?',),
      'Origen Paso 03':('SELECT p.codigo,p.nombre,p.estado,p.beneficio,p.fecha_validacion FROM p3_soluciones p JOIN p4_services s ON p.id=s.source_step3_id WHERE s.id=?',),
      'Indicadores':('SELECT nombre,tipo,unidad,linea_base,meta,real,frecuencia,responsable,fecha_medicion FROM p4_metrics WHERE servicio_id=?',),
      'Competencias':('SELECT competencia,nivel FROM p4_requirements WHERE servicio_id=?',),
      'Asignaciones':('SELECT t.nombre,t.rol,a.porcentaje,t.habilidades_json FROM p4_allocations a JOIN p4_team t ON t.id=a.integrante_id WHERE a.servicio_id=? AND a.porcentaje>0',),
      'Incorporación':("SELECT s.codigo,s.nombre,p.launch_date,p.approved_at,a.authorized_at,a.active_clients FROM p5_services s LEFT JOIN p5_plans p ON p.service_id=s.id LEFT JOIN p5_adoptions a ON a.service_id=s.id WHERE s.demo=0 AND CASE WHEN json_valid(s.source_json) THEN json_extract(s.source_json,'$.id') END=?",),
      'Operación':('SELECT t.folio,t.titulo,t.estado,t.creado_en,t.cerrado_en,t.calificacion FROM p6_tickets t JOIN p6_catalog c ON c.id=t.servicio_id WHERE c.p4_id=? AND c.demo=0 AND t.demo=0 ORDER BY t.creado_en DESC',),
      'Monitoreo':('SELECT m.folio,m.estado,m.primera_respuesta_en,m.terminado_en,m.calificacion FROM p7_tickets m JOIN p6_tickets t ON t.id=m.id JOIN p6_catalog c ON c.id=t.servicio_id WHERE c.p4_id=? AND c.demo=0 AND t.demo=0 AND m.origen_demo=0 AND m.servicio_id=t.servicio_id',),
      'Madurez verificada':("SELECT c.id AS ciclo_id,c.nombre AS ciclo,c.estado AS estado_ciclo,r.servicio_ref,r.estado,r.actual,r.deseado,r.observacion,r.evidencia,v.verificador,v.verificado_en FROM p8_service_links l JOIN p8_cycles c ON c.id=l.ciclo_id JOIN p8_ratings r ON r.ciclo_id=l.ciclo_id AND r.servicio_ref=l.servicio_ref JOIN p8_mejora_correspondencias v ON v.ciclo_id=l.ciclo_id AND v.servicio_ref=l.servicio_ref AND v.servicio_cens=l.servicio_cens WHERE l.servicio_cens=? AND c.es_demo=0 AND v.estado='Verificada' ORDER BY c.inicio, c.id, r.servicio_ref",),
      'Mejoras vinculadas':("SELECT a.id,a.titulo,a.estado,a.responsable,a.fecha_meta,c.nombre AS ciclo FROM p8_service_links l JOIN p8_cycles c ON c.id=l.ciclo_id JOIN p8_actions a ON a.ciclo_id=l.ciclo_id AND a.servicio_ref=l.servicio_ref JOIN p8_mejora_correspondencias v ON v.ciclo_id=l.ciclo_id AND v.servicio_ref=l.servicio_ref AND v.servicio_cens=l.servicio_cens WHERE l.servicio_cens=? AND c.es_demo=0 AND v.estado='Verificada' ORDER BY a.fecha_meta,a.id",),
      'Beneficios':("SELECT b.id,b.beneficio,b.indicador,b.estado,b.fecha_validacion,b.servicio_id AS id_origen FROM p9_beneficios b JOIN p4_services s ON (b.servicio_id=s.id OR (s.source_step3_id<>'' AND b.servicio_id=s.source_step3_id)) WHERE s.id=? AND b.es_demo=0",),
      'Reconocimiento':("SELECT r.id,r.beneficio,r.fecha_validacion,r.vigente FROM p10_beneficios r JOIN p9_beneficios b ON b.id=r.id JOIN p4_services s ON (b.servicio_id=s.id OR (s.source_step3_id<>'' AND b.servicio_id=s.source_step3_id)) WHERE s.id=? AND b.es_demo=0 AND r.es_demo=0 AND r.origen='SQLite Paso 9'",),
    }
    data={k:None for k in queries}
    try:
        with closing(sqlite3.connect(Path(path or database_path()).resolve().as_uri()+'?mode=ro',uri=True,timeout=3)) as c:
            c.row_factory=sqlite3.Row;c.execute('PRAGMA query_only=ON');c.execute('BEGIN')
            for k,(q,) in queries.items():
                try:data[k]=[dict(row) for row in c.execute(q,(service_id,))]
                except sqlite3.Error:pass
    except sqlite3.Error:pass
    return data


def competency_grid(requirements, assigned):
    """None means not evaluated; no assignment or missing score is not zero."""
    result=[]
    for req in requirements:
        levels=[]
        for m in assigned:
            try: skills=json.loads(m.get('habilidades_json') or '{}')
            except (ValueError,TypeError):skills={}
            raw=skills.get(req['competencia']) if isinstance(skills,dict) else None
            level=raw if isinstance(raw,(int,float)) and not isinstance(raw,bool) and 1<=raw<=5 else None
            levels.append(level)
        known=[x for x in levels if x is not None]
        best=max(known) if known else None
        result.append({'competencia':req['competencia'],'requerido':req['nivel'],'niveles':levels,'mejor_evaluado':best,'brecha_observada':max(0,req['nivel']-best) if best is not None else None,'sin_evaluar':sum(x is None for x in levels)})
    return result


def ans_summary(d):
    versions=d.get('ans_versiones') or []
    last=versions[-1] if isinstance(versions,list) and versions and isinstance(versions[-1],dict) else {}
    current=extract_snapshot(d)
    valid=(d.get('ans_estado')=='Validado' and bool(last) and last.get('sha256')==digest(current) and isinstance(last.get('contenido'),dict) and digest(last['contenido'])==last.get('sha256'))
    return {'estado':d.get('ans_estado') or 'Borrador','vigente':valid,'version':last.get('numero'),'contenido':current,'historico':versions if isinstance(versions,list) else []}


def blueprint(d):
    raw=d.get('proceso_actividades')
    rows=[dict(r) for r in raw if isinstance(r,dict) and str(r.get('Actividad') or '').strip()] if isinstance(raw,list) else []
    def order(r):
        try:return (0,int(r.get('Orden')))
        except (ValueError,TypeError):return (1,0)
    return sorted(rows,key=order)


def render_canvas(key,cards,links):
    import streamlit as st
    from .step3 import ZONES
    with st.expander('Estudio de valor · explorar correspondencias y cobertura',expanded=False):
        st.caption('Relaciones guardadas en este lienzo y versión. Una relación no acredita beneficio materializado ni aprobación.')
        rows=canvas_matches(cards,links)
        for col,zone in zip(st.columns(2),('dolores','ganancias')):
            group=[r for r in rows if r['zona']==zone]
            col.metric('Dolores con vínculo' if zone=='dolores' else 'Ganancias con vínculo',f"{sum(bool(r['relaciones']) for r in group)}/{len(group)}")
        filter_=st.radio('Correspondencias',['Todas','Sin vínculo','Con vínculo'],horizontal=True,key=f'a03_canvas_filter_{key}')
        rows=[r for r in rows if filter_=='Todas' or bool(r['relaciones'])==(filter_=='Con vínculo')]
        if not rows:st.info('No hay tarjetas para este filtro. Agrega o conecta tarjetas mediante el lienzo existente.');return
        pick=st.selectbox('Explorar tarjeta',[r['id'] for r in rows],format_func=lambda k:next(f"{ZONES[r['zona']]} · {r['titulo']}" for r in rows if r['id']==k),key=f'a03_canvas_pick_{key}')
        row=next(r for r in rows if r['id']==pick)
        left,right=st.columns(2)
        with left:
            st.markdown('**Perfil del cliente**');st.write(row['titulo']);st.caption(row['detalle'])
        with right:
            st.markdown('**Mapa de valor · vínculos explícitos**')
            if not row['relaciones']:st.warning('Sin correspondencia registrada en las zonas compatibles.')
            for target in row['relaciones']:
                with st.container(border=True):
                    st.caption(ZONES.get(target['zona'],target['zona']));st.write(target['titulo']);st.caption(target['justificacion'] or 'Sin justificación registrada')
        st.dataframe([{'Tarjeta':r['titulo'],'Zona':ZONES.get(r['zona'],r['zona']),'Relaciones explícitas':len(r['relaciones'])} for r in rows],hide_index=True,use_container_width=True)


def _table(st,rows):
    if rows is None:st.warning('Fuente no disponible en esta base.')
    elif not rows:st.info('Sin registros vinculados explícitamente.')
    else:st.dataframe(rows,hide_index=True,use_container_width=True)


def render_service(services):
    import streamlit as st
    if not services:return
    with st.expander('Estudio de servicios · Ficha 360°, plano de prestación y ANS',expanded=st.session_state.pop('b02_expand_service',False)):
        pick=st.selectbox('Servicio',[r['id'] for r in services],format_func=lambda k:next(f"{r['codigo']} · {r['nombre']}" for r in services if r['id']==k),key='a03_service_pick')
        data=service_views(pick); rows=data['Diseño']
        if not rows:st.warning('Ficha no disponible.');return
        svc=rows[0]
        try:d=json.loads(svc.get('detalles_json') or '{}')
        except (TypeError,ValueError):st.error('Detalle no legible. Consulte la ficha de origen.');return
        if not isinstance(d,dict):st.warning('Detalle no estructurado.');return
        st.caption(f"{svc['codigo']} · Estado del diseño: {svc['estado']} · No equivale a autorización de operación")
        st.subheader(svc['nombre']);st.write(svc['propuesta_valor'] or 'Sin propuesta de valor registrada')
        for col,k in zip(st.columns(3),('Indicadores','Operación','Beneficios')):col.metric(k,'—' if data[k] is None else len(data[k]))
        tab=st.radio('Perspectiva',['Origen y diseño','Plano del servicio','Competencias','ANS','Ciclo de vida'],horizontal=True,key=f'a03_service_tab_{pick}')
        if tab=='Origen y diseño':
            for label,k in [('Cliente destinatario','cliente'),('Necesidad','necesidad'),('Beneficio esperado','beneficio'),('Responsable','responsable'),('Modelo','modelo')]:st.write(f'{label}: {svc.get(k) or "Sin registrar"}')
            st.markdown('**Propuesta de origen · Paso 03**');_table(st,data['Origen Paso 03'])
            st.markdown('**Indicadores del catálogo**');_table(st,data['Indicadores'])
        elif tab=='Plano del servicio':
            render_blueprint(st,svc,d)
        elif tab=='Competencias':
            render_competencies(st,data['Competencias'],data['Asignaciones'])
        elif tab=='ANS':
            a=ans_summary(d);c=a['contenido'];st.write(f"Estado registrado: {a['estado']} · Última versión: {a['version'] or 'Sin versión'}")
            if a['vigente']:st.success('El contenido coincide con la última versión validada por el mecanismo ANS existente.')
            else:st.warning('No se acredita vigencia de un ANS versionado. Consulte la ficha oficial.')
            for col,label,prefix in zip(st.columns(2),('Respuesta','Entrega'),('ans_respuesta','ans_entrega')):
                col.metric(label,(c[prefix+'_valor']+' '+c[prefix+'_unidad']).strip() or 'Sin definir')
            for label,k in [('Calendario','ans_horario'),('Inicio','ans_inicio_computo'),('Fin','ans_fin_computo'),('Calidad','sla_calidad'),('Aceptación','sla_aceptacion'),('Escalamiento','sla_escalamiento'),('Revisión','periodicidad_revision')]:st.write(f'{label}: {c.get(k) or "Sin registrar"}')
            if a['historico']:
                _table(st,[{k:v.get(k) for k in ('numero','fecha_acuerdo','actor','validado_en','sha256')} for v in a['historico'] if isinstance(v,dict)])
        else:
            st.caption('Consulta histórica por vínculos de origen explícitos; excluye filas marcadas como demostrativas en Pasos 05–10. No calcula avance ni atribución causal.')
            for k in ('Incorporación','Operación','Monitoreo','Madurez verificada','Mejoras vinculadas','Beneficios','Reconocimiento'):
                st.markdown(f'**{k}**');_table(st,data[k])
            st.caption('Los beneficios con ID de la solución de origen se muestran como vínculos de propuesta, no como atribución exclusiva al servicio. Reconocimiento muestra únicamente registros transferidos desde Paso 09, no confirma reconocimiento por el cliente. Madurez y mejoras del Paso 08 se muestran solo con correspondencia verificada; se conserva el estado del ciclo y no se imputan niveles.')
        st.caption('Para editar o validar, utiliza Abrir ficha y los módulos originales. Esta vista no escribe datos.')


def render_blueprint(st,svc,d):
    st.markdown('**Plano de prestación · datos guardados**')
    st.caption('Vista del proceso documentado; no inventa actividades, responsables ni secuencia de aprobación.')
    st.write('Enfoque de prestación: '+str(d.get('enfoque_prestacion') or 'Por definir'))
    left,right=st.columns(2)
    with left:
        st.markdown('**Entrada · cliente**');st.write(svc.get('cliente') or 'Sin destinatario');st.write(d.get('solicitud') or 'Sin instrucciones registradas');st.caption(str(d.get('canal_solicitud') or 'Canal sin definir'))
    with right:
        st.markdown('**Activación · PMO**');st.write(d.get('activaciones') or 'Sin modos definidos');st.write(d.get('activacion_detalle') or 'Sin condiciones registradas')
    rows=blueprint(d)
    if rows:
        for r in rows:
            with st.container(border=True):
                st.caption('Orden registrado: '+str(r.get('Orden') or 'Sin definir'));st.write(r['Actividad']);st.caption('Responsable: '+str(r.get('Responsable') or 'Sin definir'));st.write('Resultado: '+str(r.get('Resultado') or 'Sin definir'))
    else:st.info('Sin actividades estructuradas. Se conserva el proceso histórico:');st.write(d.get('proceso') or 'Sin proceso registrado')
    st.markdown('**RACI y entregables**');_table(st,d.get('raci_registro') or []);_table(st,d.get('entregables_items') or [])
    st.caption('Los textos históricos de RACI y entregables se mantienen disponibles en Abrir ficha.')


def render_competencies(st,req,assigned):
    import pandas as pd
    if req is None or assigned is None:st.warning('Fuente de competencias o asignaciones no disponible.');return
    if not req:st.info('Sin competencias requeridas registradas.');return
    rows=competency_grid(req,assigned)
    st.caption('Solo integrantes con asignación positiva. Sin evaluación se muestra vacío, no como nivel cero. La brecha observada no reemplaza los controles vigentes.')
    frame=pd.DataFrame([{'Competencia':r['competencia'],'Requerido':r['requerido'],**{f"{m['nombre']} · {i+1}":v for i,(m,v) in enumerate(zip(assigned,r['niveles']))},'Mejor evaluado':r['mejor_evaluado'],'Brecha observada':r['brecha_observada'],'Sin evaluar':r['sin_evaluar']} for r in rows])
    cols=[c for c in frame.columns if c not in ('Competencia','Brecha observada','Sin evaluar')]
    # Color map without matplotlib dependency; missing values remain neutral.
    def color(v):
        if pd.isna(v):return ''
        return f'background-color:{["#fce4df","#f7ddbf","#f2e7af","#c1e5dd","#78c6b3"][max(0,min(4,int(v)-1))]};color:#183c43'
    st.dataframe(frame.style.map(color,subset=cols),hide_index=True,use_container_width=True)


def render_modalities(services):
    import streamlit as st
    with st.expander('Matriz de modalidades de prestación · catálogo',expanded=False):
        st.caption('Enfoque de prestación guardado por servicio, diferente del modelo consultivo/de apoyo. No se asignan modalidades por cliente automáticamente.')
        rows=[]
        for s in services:
            try:d=json.loads(s.get('detalles_json') or '{}')
            except (ValueError,TypeError):d={}
            if not isinstance(d,dict):d={}
            rows.append({'Código':s['codigo'],'Servicio':s['nombre'],'Cliente':s.get('cliente'),'Modelo':s.get('modelo'),'Enfoque':d.get('enfoque_prestacion') or 'Por definir','Estado diseño':s.get('estado')})
        options=['Todos',*sorted({r['Enfoque'] for r in rows})]
        selected=st.selectbox('Enfoque de prestación',options,key='a03_modality_filter')
        _table(st,[r for r in rows if selected=='Todos' or r['Enfoque']==selected])
        st.caption('Referencia PMI 2025, cap. 17. Para modificar el enfoque utiliza la ficha del servicio. Las modalidades diferenciadas por cliente quedan pendientes de un diseño de persistencia específico.')
