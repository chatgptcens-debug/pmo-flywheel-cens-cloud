"""V0.39.14 · Catálogo de definición de métricas y cortes operativos independientes.

Extensión aditiva: preserva p4_metrics y las mediciones históricas heredadas.
Las propuestas SRV-011 no son mediciones ni aprobaciones institucionales.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import math
import re
import sqlite3
import uuid
from .storage import connect, transaction

CATEGORIES=('Eficiencia','Salida','Resultado','Percepción')
FORMULAS=('Porcentaje / Tasa','Tiempo medio / Duración','Conteo absoluto','Promedio / Puntaje','Net Promoter Score (NPS)','Valor directo')
UNITS=('%','Horas hábiles','Días hábiles','Entregables','Proyectos','Solicitudes','Puntos (1–5)','Puntos NPS','COP','USD','Otro')
FREQUENCIES=('Mensual','Trimestral','Por evento','Semestral','Anual')
SOURCES=('Base de datos PMIS / Aplicativo PMO','ERP / SAP','Mesa de ayuda / tickets','Encuesta digital','Repositorio documental','Otra fuente')
METHODS=('Automático (API / SQL)','Semiautomático (Excel / Snapshot)','Manual (Formulario)')
ROLES=('Administrador PMIS','Especialista de Analítica PMO','Director de Proyecto','Líder PMO','Otro rol')
VALIDATORS=('Sponsor del proyecto','Director de Proyecto','Alta Dirección','Jefe funcional','Líder PMO','Otro')
EVIDENCES=('Ticket digital','Snapshot de base de datos','Acta de validación','Encuesta registrada','Repositorio documental','Otra')
DIRECTIONS=('mayor','menor','rango')
DEF_STATES=('Borrador','En revisión','Aprobada')
SCHEMA='''
CREATE TABLE IF NOT EXISTS p4_metric_specs (
 metric_id TEXT PRIMARY KEY REFERENCES p4_metrics(id) ON DELETE CASCADE,
 codigo TEXT NOT NULL UNIQUE,
 categoria TEXT NOT NULL CHECK(categoria IN ('Eficiencia','Salida','Resultado','Percepción')),
 objetivo TEXT NOT NULL DEFAULT '',
 tipo_formula TEXT NOT NULL DEFAULT '',
 fuente_tipo TEXT NOT NULL DEFAULT '',
 metodo_captura TEXT NOT NULL DEFAULT '',
 rol_responsable TEXT NOT NULL DEFAULT '',
 requiere_validacion TEXT NOT NULL DEFAULT 'No',
 rol_validador TEXT NOT NULL DEFAULT '',
 tipo_evidencia TEXT NOT NULL DEFAULT '',
 rag_json TEXT NOT NULL DEFAULT '{}',
 estado TEXT NOT NULL DEFAULT 'Borrador' CHECK(estado IN ('Borrador','En revisión','Aprobada')),
 notas_propuesta TEXT NOT NULL DEFAULT '',
 autor_aprobacion TEXT NOT NULL DEFAULT '',
 evidencia_aprobacion TEXT NOT NULL DEFAULT '',
 aprobado_en TEXT NOT NULL DEFAULT '',
 actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS p4_metric_measurements (
 id TEXT PRIMARY KEY,
 metric_id TEXT NOT NULL REFERENCES p4_metrics(id) ON DELETE CASCADE,
 periodo TEXT NOT NULL,
 revision INTEGER NOT NULL,
 numerador REAL, denominador REAL, tercero REAL,
 resultado REAL NOT NULL,
 rag TEXT NOT NULL CHECK(rag IN ('Verde','Ámbar','Rojo','Sin umbrales')),
 evidencia_url TEXT NOT NULL DEFAULT '',
 evidencia_nombre TEXT NOT NULL DEFAULT '',
 evidencia_contenido BLOB,
 evidencia_sha256 TEXT NOT NULL DEFAULT '',
 observacion TEXT NOT NULL DEFAULT '',
 motivo_correccion TEXT NOT NULL DEFAULT '',
 registrado_por TEXT NOT NULL DEFAULT '',
 registrado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 definicion_version INTEGER NOT NULL DEFAULT 0,
 UNIQUE(metric_id,periodo,revision)
);
CREATE INDEX IF NOT EXISTS idx_p4_metric_measurements ON p4_metric_measurements(metric_id,periodo,revision);
CREATE TABLE IF NOT EXISTS p4_metric_definition_versions (
 metric_id TEXT NOT NULL REFERENCES p4_metrics(id) ON DELETE CASCADE,
 version INTEGER NOT NULL,
 snapshot_json TEXT NOT NULL,
 aprobado_por TEXT NOT NULL,
 evidencia TEXT NOT NULL,
 aprobado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(metric_id,version)
);
'''

def initialize(path=None):
    with connect(path) as con:
        con.executescript(SCHEMA)
        con.execute('INSERT OR IGNORE INTO schema_migrations(version) VALUES (14)')
        con.commit()

def _row(query,args=(),path=None):
    with connect(path) as con:
        item=con.execute(query,args).fetchone()
        return dict(item) if item else None

def specs(path=None):
    with connect(path) as con:
        return {x['metric_id']:dict(x) for x in con.execute('SELECT * FROM p4_metric_specs')}

def spec(metric_id,path=None):
    r=_row('SELECT * FROM p4_metric_specs WHERE metric_id=?',(metric_id,),path)
    if r:
        try:r['rag']=json.loads(r.get('rag_json') or '{}')
        except (ValueError,TypeError):r['rag']={}
    return r

def _service_code(con,sid):
    have=con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pmo_codigos_publicos'").fetchone()
    r=con.execute("SELECT codigo FROM pmo_codigos_publicos WHERE tipo='servicio' AND entidad_id=?",(sid,)).fetchone() if have else None
    if r:return r[0]
    legacy=con.execute('SELECT codigo FROM p4_services WHERE id=?',(sid,)).fetchone()
    if not legacy:raise ValueError('Servicio no encontrado.')
    match=re.search(r'(\d+)$',legacy[0])
    return f'SRV-{int(match.group(1)):03d}' if match else 'SRV-000'

def _next_code(con,sid):
    code=_service_code(con,sid).replace('-','')
    existing=[x[0] for x in con.execute('SELECT codigo FROM p4_metric_specs WHERE codigo LIKE ?',('MET-'+code+'-%',))]
    used={int(x.rsplit('-',1)[-1]) for x in existing if x.rsplit('-',1)[-1].isdigit()}
    n=1
    while n in used:n+=1
    return f'MET-{code}-{n:02d}'

def code_for(metric_id,path=None):
    r=spec(metric_id,path)
    return r['codigo'] if r else 'Pendiente de ficha'

def validate_rag(direction,rag):
    if direction not in DIRECTIONS:raise ValueError('Sentido favorable inválido.')
    if not isinstance(rag,dict):raise ValueError('Configuración de umbrales inválida.')
    if not rag:return
    try:
        if direction=='mayor':
            green=float(rag['green']);amber=float(rag['amber'])
            if green<=amber:raise ValueError('El límite verde debe ser mayor que el límite ámbar.')
        elif direction=='menor':
            green=float(rag['green']);amber=float(rag['amber'])
            if green>=amber:raise ValueError('El límite verde debe ser menor que el límite ámbar.')
        else:
            low=float(rag['low']);high=float(rag['high']);margin=float(rag['margin'])
            if low>=high or margin<0:raise ValueError('La banda objetivo o el margen son inválidos.')
        if any(not math.isfinite(float(v)) for v in rag.values()):raise ValueError('Umbrales no finitos.')
    except (KeyError,TypeError) as ex:raise ValueError('Configure todos los límites de clasificación RAG.') from ex

def definition_complete(legacy,data):
    return bool(legacy and all(str(legacy.get(x) or '').strip() for x in ('nombre','formula','unidad','frecuencia','fuente','responsable'))
        and all(str(data.get(x) or '').strip() for x in ('objetivo','tipo_formula','metodo_captura','rol_responsable'))
        and data.get('rag') and data.get('categoria') in CATEGORIES)

def save_definition(metric_id, data, actor='Equipo PMO',path=None):
    """Guarda ficha sin alterar registros históricos p4_metric_measurements."""
    if not metric_id:raise ValueError('Seleccione un indicador.')
    categoria=data.get('categoria','')
    if categoria not in CATEGORIES:raise ValueError('Categoría inválida.')
    direction=data.get('sentido','mayor')
    rag=data.get('rag') or {}
    validate_rag(direction,rag)
    formula_type=data.get('tipo_formula') or ''
    if formula_type not in FORMULAS:raise ValueError('Seleccione tipo de fórmula.')
    if formula_type=='Net Promoter Score (NPS)' and (direction!='mayor' or data.get('unidad')!='Puntos NPS'):
        raise ValueError('NPS requiere sentido ascendente y unidad Puntos NPS.')
    stage=data.get('estado','Borrador')
    if stage not in ('Borrador','En revisión'):raise ValueError('Solo se puede guardar en Borrador o En revisión; la aprobación requiere validación expresa.')
    campos=('objetivo','fuente_tipo','metodo_captura','rol_responsable','requiere_validacion',
            'rol_validador','tipo_evidencia','notas_propuesta')
    extra={x:str(data.get(x) or '').strip() for x in campos}
    if extra['requiere_validacion'] not in ('Sí','No'):raise ValueError('Indique si requiere validación.')
    title=str(data.get('nombre') or '').strip()
    if not title:raise ValueError('El indicador requiere nombre.')
    with transaction(path) as con:
        old=con.execute('SELECT * FROM p4_metrics WHERE id=?',(metric_id,)).fetchone()
        if not old:raise ValueError('Indicador inexistente.')
        prev=con.execute('SELECT * FROM p4_metric_specs WHERE metric_id=?',(metric_id,)).fetchone()
        # Estado Aprobada solo se conserva si nada cambia.
        tracked=['nombre','formula','unidad','sentido','frecuencia','fuente','responsable','linea_base','meta']
        new_values={k:str(data.get(k) if data.get(k) is not None else (old[k] or '')).strip() for k in tracked}
        new_values['nombre']=title;new_values['sentido']=direction
        effective_old_direction=('rango' if prev and 'low' in json.loads(prev['rag_json'] or '{}') else old['sentido'])
        revised=any(str((effective_old_direction if k=='sentido' else old[k]) or '')!=new_values[k] for k in tracked)
        if prev:
            revised|=any(str(prev[k] or '')!=extra[k] for k in campos)
            revised|=(prev['categoria']!=categoria or prev['tipo_formula']!=formula_type or (prev['rag_json'] or '{}')!=json.dumps(rag,sort_keys=True,ensure_ascii=False))
        con.execute('''UPDATE p4_metrics SET nombre=?,tipo=?,formula=?,unidad=?,linea_base=?,meta=?,sentido=?,frecuencia=?,responsable=?,fuente=?,actualizado_en=CURRENT_TIMESTAMP WHERE id=?''',
                    (new_values['nombre'],categoria if categoria!='Percepción' else 'Resultado',new_values['formula'],new_values['unidad'],new_values['linea_base'],new_values['meta'],direction if direction!='rango' else 'mayor',new_values['frecuencia'],new_values['responsable'],new_values['fuente'],metric_id))
        # rango se conserva en spec mientras p4_metrics admite solo mayor/menor
        if not prev:
            code=_next_code(con,old['servicio_id'])
        else:code=prev['codigo']
        status=('En revisión' if revised else 'Aprobada') if prev and prev['estado']=='Aprobada' else stage
        approval=(prev['autor_aprobacion'],prev['evidencia_aprobacion'],prev['aprobado_en']) if prev and not revised and status=='Aprobada' else ('','','')
        con.execute('''INSERT INTO p4_metric_specs(metric_id,codigo,categoria,objetivo,tipo_formula,fuente_tipo,metodo_captura,
         rol_responsable,requiere_validacion,rol_validador,tipo_evidencia,rag_json,estado,notas_propuesta,autor_aprobacion,evidencia_aprobacion,aprobado_en)
         VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(metric_id) DO UPDATE SET
         categoria=excluded.categoria,objetivo=excluded.objetivo,tipo_formula=excluded.tipo_formula,fuente_tipo=excluded.fuente_tipo,
         metodo_captura=excluded.metodo_captura,rol_responsable=excluded.rol_responsable,requiere_validacion=excluded.requiere_validacion,
         rol_validador=excluded.rol_validador,tipo_evidencia=excluded.tipo_evidencia,rag_json=excluded.rag_json,
         estado=excluded.estado,notas_propuesta=excluded.notas_propuesta,autor_aprobacion=excluded.autor_aprobacion,
         evidencia_aprobacion=excluded.evidencia_aprobacion,aprobado_en=excluded.aprobado_en,actualizado_en=CURRENT_TIMESTAMP''',
         (metric_id,code,categoria,extra['objetivo'],formula_type,extra['fuente_tipo'],extra['metodo_captura'],
          extra['rol_responsable'],extra['requiere_validacion'],extra['rol_validador'],extra['tipo_evidencia'],
          json.dumps(rag,sort_keys=True,ensure_ascii=False),status,extra['notas_propuesta'],*approval))
        con.execute('INSERT INTO p4_audit(entidad,objeto_id,accion,actor,detalle) VALUES(?,?,?,?,?)',
                    ('indicador',metric_id,'guardar_definicion',actor,json.dumps({'estado':status,'codigo':code},ensure_ascii=False)))
    return code

def approve_definition(metric_id,approver,evidence,path=None):
    approver=str(approver or '').strip();evidence=str(evidence or '').strip()
    if not approver or not evidence:raise ValueError('La aprobación requiere responsable y evidencia documental.')
    with transaction(path) as con:
        m=con.execute('SELECT * FROM p4_metrics WHERE id=?',(metric_id,)).fetchone()
        p=con.execute('SELECT * FROM p4_metric_specs WHERE metric_id=?',(metric_id,)).fetchone()
        if not m or not p:raise ValueError('Ficha inexistente.')
        spec_data=dict(p);spec_data['rag']=json.loads(p['rag_json'] or '{}')
        if not definition_complete(dict(m),spec_data):raise ValueError('Complete definición, fórmula, umbrales, fuente y responsable antes de aprobar.')
        validate_rag('rango' if 'low' in spec_data['rag'] else m['sentido'], spec_data['rag'])
        if not p['rag_json'] or p['rag_json']=='{}':raise ValueError('Debe definir umbrales RAG.')
        current_version=con.execute('SELECT COALESCE(MAX(version),0) FROM p4_metric_definition_versions WHERE metric_id=?',(metric_id,)).fetchone()[0]
        frozen={'metric':dict(m),'definicion':dict(p)}
        con.execute('INSERT INTO p4_metric_definition_versions(metric_id,version,snapshot_json,aprobado_por,evidencia) VALUES(?,?,?,?,?)',
                    (metric_id,current_version+1,json.dumps(frozen,ensure_ascii=False,sort_keys=True),approver,evidence))
        con.execute("UPDATE p4_metric_specs SET estado='Aprobada',autor_aprobacion=?,evidencia_aprobacion=?,aprobado_en=CURRENT_TIMESTAMP,actualizado_en=CURRENT_TIMESTAMP WHERE metric_id=?",(approver,evidence,metric_id))
        con.execute('INSERT INTO p4_audit(entidad,objeto_id,accion,actor,detalle) VALUES(?,?,?,?,?)',
                    ('indicador',metric_id,'aprobar_definicion',approver,json.dumps({'evidencia':evidence},ensure_ascii=False)))

def calculate(kind,numerator,denominator=None,third=None):
    def n(v):
        if v is None:return None
        x=float(v)
        if not math.isfinite(x):raise ValueError('Los datos deben ser números finitos.')
        return x
    a=n(numerator);b=n(denominator);c=n(third)
    if a is None:raise ValueError('Ingrese la primera variable.')
    if kind=='Conteo absoluto':
        if a<0:raise ValueError('El conteo no puede ser negativo.')
        return a
    if kind=='Valor directo':return a
    if kind in ('Porcentaje / Tasa','Tiempo medio / Duración','Promedio / Puntaje'):
        if b is None or b<=0 or a<0:raise ValueError('Numerador no negativo y denominador mayor a cero.')
        if kind=='Porcentaje / Tasa' and a>b:raise ValueError('El numerador no puede superar el denominador para un porcentaje de parte del total.')
        result=a/b*(100 if kind=='Porcentaje / Tasa' else 1)
        if kind=='Promedio / Puntaje' and not 1<=result<=5:raise ValueError('El promedio debe estar entre 1 y 5.')
        return result
    if kind=='Net Promoter Score (NPS)':
        if b is None or c is None or a<0 or b<0 or c<=0 or a+b>c:
            raise ValueError('NPS requiere promotores y detractores no negativos; su suma no puede superar los participantes.')
        return (a-b)/c*100
    raise ValueError('Tipo de fórmula no soportado.')

def rag_state(value,direction,rag):
    if not rag:return 'Sin umbrales'
    validate_rag(direction,rag)
    x=float(value)
    if direction=='mayor':return 'Verde' if x>=float(rag['green']) else 'Ámbar' if x>=float(rag['amber']) else 'Rojo'
    if direction=='menor':return 'Verde' if x<=float(rag['green']) else 'Ámbar' if x<=float(rag['amber']) else 'Rojo'
    low=float(rag['low']);high=float(rag['high']);margin=float(rag['margin'])
    return 'Verde' if low<=x<=high else 'Ámbar' if low-margin<=x<=high+margin else 'Rojo'

def measurement_list(metric_id=None,path=None,latest_only=True):
    sql='SELECT id,metric_id,periodo,revision,numerador,denominador,tercero,resultado,rag,evidencia_url,evidencia_nombre,evidencia_sha256,observacion,motivo_correccion,registrado_por,registrado_en,definicion_version FROM p4_metric_measurements'
    args=()
    if metric_id:sql+=' WHERE metric_id=?';args=(metric_id,)
    sql+=' ORDER BY periodo DESC,revision DESC'
    with connect(path) as con:rows=[dict(x) for x in con.execute(sql,args)]
    if not latest_only:return rows
    seen=set();result=[]
    for r in rows:
        marker=(r['metric_id'],r['periodo'])
        if marker in seen:continue
        seen.add(marker);result.append(r)
    return result

def register_measurement(metric_id,period,numerator,denominator=None,third=None,
                         evidence_url='',evidence_name='',evidence_bytes=None,observacion='',actor='Equipo PMO',motivo_correccion='',path=None):
    if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])',str(period)):
        raise ValueError('El periodo debe tener formato AAAA-MM.')
    evidence_url=str(evidence_url or '').strip();evidence_name=str(evidence_name or '').strip()
    if evidence_bytes is not None:
        if not isinstance(evidence_bytes,bytes) or len(evidence_bytes)>8*1024*1024:
            raise ValueError('El archivo de evidencia debe ser de máximo 8 MB.')
        if not evidence_name or not evidence_name.lower().endswith(('.pdf','.png','.jpg','.jpeg','.xlsx','.csv','.txt')):
            raise ValueError('Formato de evidencia no admitido.')
    if evidence_url and not evidence_url.startswith(('https://','http://')):raise ValueError('La evidencia URL debe ser HTTP(S).')
    if not evidence_url and not evidence_bytes:raise ValueError('Cada medición requiere evidencia (archivo o URL).')
    with transaction(path) as con:
        row=con.execute('SELECT * FROM p4_metrics WHERE id=?',(metric_id,)).fetchone()
        sp=con.execute('SELECT * FROM p4_metric_specs WHERE metric_id=?',(metric_id,)).fetchone()
        if not row or not sp:raise ValueError('La ficha de la métrica no existe.')
        if sp['estado']!='Aprobada':raise ValueError('Apruebe la definición de la métrica antes de registrar resultados oficiales.')
        definition_version=con.execute('SELECT COALESCE(MAX(version),0) FROM p4_metric_definition_versions WHERE metric_id=?',(metric_id,)).fetchone()[0]
        if definition_version<1:raise ValueError('No existe una versión aprobada de la definición.')
        result=calculate(sp['tipo_formula'],numerator,denominator,third)
        rag=json.loads(sp['rag_json'] or '{}')
        direction='rango' if 'low' in rag else row['sentido']
        ragvalue=rag_state(result,direction,rag)
        latest=con.execute('SELECT MAX(revision) FROM p4_metric_measurements WHERE metric_id=? AND periodo=?',(metric_id,period)).fetchone()[0]
        if latest and not str(motivo_correccion or '').strip():raise ValueError('Una corrección a un periodo ya medido requiere justificación.')
        if ragvalue=='Rojo' and not str(observacion or '').strip():raise ValueError('Una medición en rojo requiere observación y plan de acción.')
        ident=str(uuid.uuid4());digest=hashlib.sha256(evidence_bytes or b'').hexdigest() if evidence_bytes else ''
        con.execute('''INSERT INTO p4_metric_measurements(id,metric_id,periodo,revision,numerador,denominador,tercero,resultado,rag,evidencia_url,evidencia_nombre,evidencia_contenido,evidencia_sha256,observacion,motivo_correccion,registrado_por,definicion_version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (ident,metric_id,period,(latest or 0)+1,numerator,denominator,third,round(result,5),ragvalue,evidence_url,evidence_name,evidence_bytes,digest,str(observacion or ''),str(motivo_correccion or ''),str(actor or 'Equipo PMO'),definition_version))
        con.execute('INSERT INTO p4_audit(entidad,objeto_id,accion,actor,detalle) VALUES(?,?,?,?,?)',
                    ('medicion',ident,'registrar',actor,json.dumps({'indicador':metric_id,'periodo':period,'revision':(latest or 0)+1,'rag':ragvalue},ensure_ascii=False)))
    return {'id':ident,'resultado':round(result,5),'rag':ragvalue,'revision':(latest or 0)+1}

def evidence_bytes(record_id,path=None):
    r=_row('SELECT evidencia_nombre,evidencia_contenido FROM p4_metric_measurements WHERE id=?',(record_id,),path)
    return (r['evidencia_nombre'],r['evidencia_contenido']) if r else None
