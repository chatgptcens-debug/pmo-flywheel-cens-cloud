"""Alpha06: consultas transversales, sin escrituras ni decisiones automáticas."""
from contextlib import contextmanager, closing
from pathlib import Path
from datetime import date
import json
import sqlite3
import unicodedata
from .config import database_path
from . import v5_engine, matrix

@contextmanager
def reader(path=None):
    with closing(sqlite3.connect(Path(path or database_path()).resolve().as_uri()+'?mode=ro', uri=True, timeout=3)) as c:
        c.row_factory=sqlite3.Row
        c.execute('PRAGMA query_only=ON'); c.execute('BEGIN')
        yield c

def query(c, sql, params=()):
    try: return [dict(r) for r in c.execute(sql,params)]
    except sqlite3.Error: return None

# Fixed metadata and SQL. Never searches email, raw evidence payloads or attachment bytes.
SEARCH = {
 'Clientes': (1, "SELECT id,codigo AS codigo,nombre AS titulo,rol_especifico AS contexto FROM pmo_clientes WHERE activo=1"),
 'Eventos': (1, "SELECT id,'' AS codigo,titulo,estado AS contexto FROM p1_eventos"),
 'Necesidades': (2, "SELECT id,'' AS codigo,problema AS titulo,dependencia AS contexto FROM p2_necesidades"),
 'Diagnósticos': (2, "SELECT id,'' AS codigo,nombre AS titulo,estado AS contexto FROM p2_diagnosticos"),
 'Evidencias de necesidades': (2, "SELECT id,'' AS codigo,titulo,tipo AS contexto FROM p2_evidencias"),
 'Propuestas': (3, "SELECT id,codigo,nombre AS titulo,estado AS contexto FROM p3_soluciones WHERE upper(codigo) NOT LIKE 'DEMO%' AND upper(codigo) NOT LIKE 'PRACTICA%'"),
 'Servicios diseñados': (4, "SELECT id,codigo,nombre AS titulo,estado AS contexto FROM p4_services WHERE upper(codigo) NOT LIKE 'DEMO%' AND upper(codigo) NOT LIKE 'PRACTICA%'"),
 'Incorporación': (5, "SELECT id,codigo,nombre AS titulo,cliente AS contexto FROM p5_services WHERE demo=0"),
 'Solicitudes': (6, "SELECT id,folio AS codigo,titulo,estado AS contexto FROM p6_tickets WHERE demo=0"),
 'Monitoreo': (7, "SELECT id,folio AS codigo,titulo,estado AS contexto FROM p7_tickets WHERE origen_demo=0"),
 'Mejoras': (8, "SELECT a.id,'' AS codigo,a.titulo,a.estado AS contexto FROM p8_actions a JOIN p8_cycles c ON c.id=a.ciclo_id WHERE c.es_demo=0"),
 'Beneficios': (9, "SELECT id,'' AS codigo,beneficio AS titulo,estado AS contexto FROM p9_beneficios WHERE es_demo=0"),
 'Historias de valor': (10, "SELECT id,'' AS codigo,titulo,estado AS contexto FROM p10_historias WHERE es_demo=0"),
}

def norm(s):
    return ''.join(x for x in unicodedata.normalize('NFKD',str(s or '').casefold()) if not unicodedata.combining(x))

def search(text, categories=None, path=None, limit=200):
    tokens=norm(text).split(); hits=[]; missing=[]; total=0
    if not tokens: return hits,missing,total
    try:
        with reader(path) as c:
            for category,(step,sql) in SEARCH.items():
                if categories is not None and category not in categories: continue
                # Stream SQLite rows and normalize once per row, without persistent cache.
                initial_total, initial_hits = total, len(hits)
                try:
                    for row in c.execute(sql):
                        haystack=norm(' '.join(str(v or '') for v in row))
                        if all(t in haystack for t in tokens):
                            total+=1
                            if len(hits)<limit: hits.append({'Tipo':category,'Paso':step,'ID':row['id'],'Código':row['codigo'],'Título':row['titulo'],'Contexto':row['contexto']})
                except sqlite3.Error:
                    total=initial_total; del hits[initial_hits:]; missing.append(category)
    except sqlite3.Error: missing=['Base no disponible']
    return hits,missing,total

QUALITY={
 'Necesidades sin resultado esperado':(2,"SELECT id,problema AS titulo FROM p2_necesidades WHERE resultado_id IS NULL OR resultado_id NOT BETWEEN 1 AND 30"),
 'Propuestas aprobadas sin fecha o evidencia de validación':(3,"SELECT id,nombre AS titulo FROM p3_soluciones WHERE estado='Aprobada' AND (trim(coalesce(fecha_validacion,''))='' OR trim(coalesce(evidencia_validacion,''))='') AND upper(codigo) NOT LIKE 'DEMO%' AND upper(codigo) NOT LIKE 'PRACTICA%'"),
 'Servicios diseñados sin indicador registrado':(4,"SELECT s.id,s.nombre AS titulo FROM p4_services s WHERE upper(s.codigo) NOT LIKE 'DEMO%' AND upper(s.codigo) NOT LIKE 'PRACTICA%' AND NOT EXISTS(SELECT 1 FROM p4_metrics m WHERE m.servicio_id=s.id)"),
 'Planes aprobados sin evidencia registrada':(5,"SELECT s.id,s.nombre AS titulo FROM p5_services s JOIN p5_plans p ON p.service_id=s.id WHERE s.demo=0 AND trim(coalesce(p.approved_at,''))<>'' AND trim(coalesce(p.evidence,''))=''"),
 'Solicitudes abiertas sin responsable':(6,"SELECT id,titulo FROM p6_tickets WHERE demo=0 AND estado<>'Finalizado' AND trim(coalesce(responsable,''))=''"),
 'Indicadores de monitoreo sin valor real':(7,"SELECT id,nombre AS titulo FROM p7_metrics_ref WHERE real IS NULL"),
 'Iniciativas sin fecha meta':(8,"SELECT a.id,a.titulo FROM p8_actions a JOIN p8_cycles c ON c.id=a.ciclo_id WHERE c.es_demo=0 AND trim(coalesce(a.fecha_meta,''))=''"),
 'Beneficios sin línea base o meta':(9,"SELECT id,beneficio AS titulo FROM p9_beneficios WHERE es_demo=0 AND (linea_base IS NULL OR meta IS NULL)"),
 'Historias sin evidencia registrada':(10,"SELECT id,titulo FROM p10_historias WHERE es_demo=0 AND trim(coalesce(evidencia,''))=''"),
}

def quality(path=None):
    result={label:None for label in QUALITY}
    try:
        with reader(path) as c:
            for label,(_,sql) in QUALITY.items():result[label]=query(c,sql)
    except sqlite3.Error: pass
    return result

# Explicit origin links; proposals point to p3_beneficios, NOT directly to p2_necesidades.
def ids_json(value):
    try: v=json.loads(value or '[]')
    except (TypeError,ValueError):return set()
    if not isinstance(v,list):return set()
    return {x for r in v for x in [r if isinstance(r,str) else r.get('id') if isinstance(r,dict) else None] if isinstance(x,str) and x}

def trace(need_id,path=None):
    result={k:None for k in ('Necesidad','Cliente','Compromisos Paso 03','Propuestas','Servicios diseñados','Incorporación','Catálogo operativo','Solicitudes','Monitoreo','Mejoras','Beneficios','Reconocimiento','Percepción vinculada')}
    try:
        with reader(path) as c:
            result['Necesidad']=query(c,'SELECT id,diagnostico_id,cliente_id,problema,ganancia,estado FROM p2_necesidades WHERE id=?',(need_id,))
            if not result['Necesidad']:return result
            n=result['Necesidad'][0]
            result['Cliente']=query(c,'SELECT id,codigo,nombre,rol_especifico FROM pmo_clientes WHERE id=?',(n['cliente_id'],))
            b=query(c,'SELECT id,necesidad,beneficio,estado FROM p3_beneficios WHERE necesidad_origen=? AND diagnostico_origen=?',(need_id,n['diagnostico_id']))
            result['Compromisos Paso 03']=b
            if b is None:return result
            bids={r['id'] for r in b}
            sols=query(c,"SELECT id,codigo,nombre,estado,necesidad_id,necesidades_json FROM p3_soluciones WHERE upper(codigo) NOT LIKE 'DEMO%' AND upper(codigo) NOT LIKE 'PRACTICA%'")
            if sols is not None:result['Propuestas']=[{k:v for k,v in r.items() if k!='necesidades_json'} for r in sols if r['necesidad_id'] in bids or ids_json(r['necesidades_json']) & bids]
            def child(key, parent, sql, fk):
                if parent is None:return None
                rows=query(c,sql)
                result[key]=None if rows is None else [r for r in rows if r[fk] in {p['id'] for p in parent}]
                return result[key]
            designs=child('Servicios diseñados',result['Propuestas'],"SELECT id,codigo,nombre,estado,source_step3_id FROM p4_services WHERE upper(codigo) NOT LIKE 'DEMO%' AND upper(codigo) NOT LIKE 'PRACTICA%'",'source_step3_id')
            if designs is not None:
                rows=query(c,"SELECT s.id,s.codigo,s.nombre,CASE WHEN json_valid(s.source_json) THEN json_extract(s.source_json,'$.id') END AS p4_id,a.authorized_at FROM p5_services s LEFT JOIN p5_adoptions a ON a.service_id=s.id WHERE s.demo=0")
                result['Incorporación']=None if rows is None else [r for r in rows if r['p4_id'] in {d['id'] for d in designs}]
                rows=query(c,"SELECT DISTINCT a.id,a.titulo,a.estado,l.servicio_cens FROM p8_actions a JOIN p8_cycles cy ON cy.id=a.ciclo_id JOIN p8_service_links l ON l.ciclo_id=a.ciclo_id AND l.servicio_ref=a.servicio_ref WHERE cy.es_demo=0")
                result['Mejoras']=None if rows is None else [r for r in rows if r['servicio_cens'] in {d['id'] for d in designs}]
            catalog=child('Catálogo operativo',designs,'SELECT id,codigo,nombre,habilitado,p4_id FROM p6_catalog WHERE demo=0','p4_id')
            child('Solicitudes',catalog,'SELECT id,folio,titulo,estado,servicio_id FROM p6_tickets WHERE demo=0','servicio_id')
            if result['Solicitudes'] is not None:
                rows=query(c,'SELECT m.id,m.folio,m.titulo,m.estado,m.servicio_id FROM p7_tickets m JOIN p6_tickets t ON t.id=m.id AND t.servicio_id=m.servicio_id WHERE m.origen_demo=0 AND t.demo=0')
                result['Monitoreo']=None if rows is None else [r for r in rows if r['id'] in {t['id'] for t in result['Solicitudes']}]
            ben=child('Beneficios',b,"SELECT id,beneficio,estado,origen_p3,fecha_validacion FROM p9_beneficios WHERE es_demo=0 AND origen_archivo='SQLite Paso 3'",'origen_p3')
            if ben is not None:
                rows=query(c,"SELECT id,beneficio,vigente,fecha_validacion FROM p10_beneficios WHERE es_demo=0 AND origen='SQLite Paso 9'")
                result['Reconocimiento']=None if rows is None else [r for r in rows if r['id'] in {p['id'] for p in ben}]
                child('Percepción vinculada',result['Reconocimiento'],'SELECT id,beneficio_id,periodo,grupo,reconocimiento FROM p10_encuestas WHERE es_demo=0','beneficio_id')
    except sqlite3.Error:pass
    return result

def governance(path=None):
    queries={
      'Auditoría general': 'SELECT entidad,entidad_id,accion,actor,fecha FROM pmo_auditoria ORDER BY fecha DESC LIMIT 100',
      'Validación de propuestas': "SELECT id,codigo,nombre,estado,validador,fecha_validacion FROM p3_soluciones WHERE trim(coalesce(fecha_validacion,''))<>'' AND upper(codigo) NOT LIKE 'DEMO%' AND upper(codigo) NOT LIKE 'PRACTICA%' ORDER BY fecha_validacion DESC LIMIT 100",
      'Autorización de incorporación': "SELECT s.id,s.nombre,a.authorized_by,a.authorized_at FROM p5_adoptions a JOIN p5_services s ON s.id=a.service_id WHERE s.demo=0 AND trim(coalesce(a.authorized_at,''))<>'' ORDER BY a.authorized_at DESC LIMIT 100",
      'Compromisos de retroalimentación': 'SELECT id,observacion,accion,responsable,fecha_compromiso,estado FROM p10_retroalimentacion WHERE es_demo=0 ORDER BY fecha_compromiso LIMIT 200',
      'Decisiones MVS registradas': 'SELECT diagnostico_id,servicio_id,estado,justificacion,responsable,actualizado_en FROM p2_servicios_candidatos ORDER BY actualizado_en DESC LIMIT 100',
    }
    result={k:None for k in queries}
    try:
        with reader(path) as c:
            for k,sql in queries.items():result[k]=query(c,sql)
    except sqlite3.Error:pass
    return result

def archived_runs(path=None):
    try:
        with reader(path) as c:return query(c,'SELECT id,fecha,actor,diagnostico_id FROM p2_corridas WHERE matrix_version_id=? ORDER BY fecha DESC',(matrix.V5_ID,))
    except sqlite3.Error:return None

def snapshot(run_id,path=None):
    with reader(path) as c:
        r=query(c,'SELECT id,matrix_version_id,matriz_json,pesos_json,respuestas_json FROM p2_corridas WHERE id=?',(run_id,))
    if not r:raise ValueError('Corrida no disponible')
    return r[0]

def simulate(run,weights):
    if run['matrix_version_id']!=matrix.V5_ID:raise ValueError('Solo snapshots V5')
    m=json.loads(run['matriz_json']); mat=[[m[str(o)][str(s)] for s in range(1,27)] for o in range(1,31)]
    v5_engine.validar_matriz(mat)
    if v5_engine.hash_matriz(mat)!=matrix.V5_HASH:raise ValueError('Matriz no coincide con V5 de referencia')
    records=json.loads(run['respuestas_json']); original=json.loads(run['pesos_json'])
    def calc(w):
        relevance,_=v5_engine.relevancias_de_clientes(records,w)
        return v5_engine.calcular_servicios(relevance,mat)
    base,alt=calc(original),calc(weights)
    return [{'Servicio ID':s,'Puesto base recalculado':base['ranking_ids'].index(s)+1,'Puesto simulado':alt['ranking_ids'].index(s)+1,'Puntaje base %':base['servicios_26_pct'][s-1],'Puntaje simulado %':alt['servicios_26_pct'][s-1],'Cambio pp':alt['servicios_26_pct'][s-1]-base['servicios_26_pct'][s-1]} for s in alt['ranking_ids']]
