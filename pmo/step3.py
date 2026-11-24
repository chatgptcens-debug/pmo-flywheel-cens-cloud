"""Paso 3 · Propuesta de valor. Persistencia SQLite aditiva y reglas independientes.

Los datos Paso 1/2 nunca se actualizan aquí; las importaciones son copias trazables.
La evaluación de viabilidad es CENS y no forma parte de la puntuación PMI.
"""
from __future__ import annotations
import csv
import hashlib
import io
import json
import re
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from contextlib import closing
from typing import Any

from .storage import connect, transaction

MODULES = ('Matriz de beneficios y valor', 'Lienzo de propuesta de valor', 'Diseño y selección de soluciones')
ZONES = {
    'servicios': 'Productos y servicios', 'generadores': 'Generadores de beneficios',
    'aliviadores': 'Aliviadores de dolores', 'ganancias': 'Beneficios esperados',
    'tareas': 'Tareas del cliente', 'dolores': 'Dolores del cliente',
}
DECISIONS = ('Adoptar', 'Adaptar o consolidar', 'Convertir en habilitador', 'Crear')
STATES = ('Borrador', 'En análisis', 'En validación', 'Validada', 'Aprobada', 'Descartada')
VALUE_TYPES = ('Por definir', 'Tangible', 'Intangible', 'Mixto')
BENEFIT_STATES = ('Esperado', 'Estimado', 'Medido')
HORIZONS = ('Implementación inicial', 'Desarrollo posterior', 'Evolución futura')
DIMENSIONS = (
 ('Síntesis de los resultados de la evaluación de necesidades', (
  '¿Se analizaron los informes, encuestas, entrevistas y comentarios del Paso 2?',
  '¿Se clasificaron las necesidades y resultados esperados en categorías comprensibles?',
  '¿Se priorizaron las necesidades utilizando criterios objetivos y alineación estratégica?',
  '¿Se documentaron las principales dificultades con información de impacto y evidencia?',
  '¿Se elaboraron visualizaciones que faciliten comprender y comunicar las necesidades?')),
 ('De los problemas a las posibles soluciones', (
  '¿Se generaron alternativas de solución mediante trabajo colaborativo?',
  '¿Se utilizó un lienzo que relaciona dificultades, necesidades y soluciones?',
  '¿Se examinó la viabilidad de las soluciones considerando capacidades, recursos e impacto?',
  '¿Se agruparon y compararon las soluciones para identificar oportunidades de alto valor?',
  '¿Las soluciones propuestas explican cómo reducirán los dolores y generarán beneficios?')),
 ('Definición de la propuesta de valor de la PMO', (
  '¿Cada solución dispone de un concepto de valor claro y relacionado con la necesidad del cliente?',
  '¿Existe un mapa visual que conecta necesidades, soluciones y objetivos organizacionales?',
  '¿Se identificaron oportunidades para conseguir resultados tempranos?',
  '¿Se definió de manera preliminar cómo podrían prestarse y evolucionar las soluciones?',
  '¿Se presentaron los conceptos a clientes relevantes para recibir observaciones y validarlos?')),
 ('Establecimiento y evolución de la propuesta de valor', (
  '¿Se establecieron acuerdos de valor con los principales grupos de clientes?',
  '¿Existe una hoja de ruta para evolucionar las propuestas según las necesidades organizacionales?',
  '¿Se identificaron y gestionaron los riesgos de incumplimiento del valor prometido?',
  '¿Se estableció una periodicidad para revisar y actualizar la propuesta de valor?',
  '¿Participan representantes de diferentes grupos de clientes en su revisión?')),
 ('Medición y perfeccionamiento de la propuesta de valor', (
  '¿Se recoge sistemáticamente la percepción de los clientes sobre el valor de las propuestas?',
  '¿Se documentan y utilizan las lecciones aprendidas en las revisiones?',
  '¿Se priorizan mejoras considerando la retroalimentación de los clientes?',
  '¿Se definieron criterios para modificar, evolucionar o retirar soluciones?',
  '¿Se mide el valor logrado frente a las expectativas y compromisos definidos?')),
)
QUESTIONS = tuple(q for _, questions in DIMENSIONS for q in questions)
SCHEMA = '''
CREATE TABLE IF NOT EXISTS p3_sources (
 id TEXT PRIMARY KEY, diagnostico_origen TEXT NOT NULL, fuente TEXT NOT NULL,
 version_origen TEXT NOT NULL DEFAULT '', version_matriz TEXT NOT NULL DEFAULT '',
 hash_sha256 TEXT NOT NULL, snapshot_json TEXT NOT NULL,
 importado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(diagnostico_origen,hash_sha256)
);
CREATE TABLE IF NOT EXISTS p3_beneficios (
 id TEXT PRIMARY KEY,
 diagnostico_origen TEXT NOT NULL DEFAULT '', necesidad_origen TEXT NOT NULL DEFAULT '',
 fuente_id TEXT REFERENCES p3_sources(id), cliente_id TEXT REFERENCES pmo_clientes(id),
 cliente TEXT NOT NULL DEFAULT '', dependencia TEXT NOT NULL DEFAULT '',
 resultado_id INTEGER CHECK(resultado_id IS NULL OR resultado_id BETWEEN 1 AND 30),
 servicios_json TEXT NOT NULL DEFAULT '[]',
 necesidad TEXT NOT NULL, entregable TEXT NOT NULL DEFAULT '', beneficio TEXT NOT NULL DEFAULT '',
 metrica TEXT NOT NULL DEFAULT '', linea_base TEXT NOT NULL DEFAULT '', meta TEXT NOT NULL DEFAULT '',
 valor TEXT NOT NULL DEFAULT '', tipo_valor TEXT NOT NULL DEFAULT 'Por definir' CHECK(tipo_valor IN ('Por definir','Tangible','Intangible','Mixto')),
 medicion TEXT NOT NULL DEFAULT 'Esperado' CHECK(medicion IN ('Esperado','Estimado','Medido')),
 estado TEXT NOT NULL DEFAULT 'Borrador' CHECK(estado IN ('Borrador','En análisis','En validación','Validada','Aprobada','Descartada')),
 estado_necesidad_origen TEXT NOT NULL DEFAULT '', evidencia TEXT NOT NULL DEFAULT '',
 responsable TEXT NOT NULL DEFAULT '', version_origen TEXT NOT NULL DEFAULT '',
 creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS p3_beneficio_origen_unico
 ON p3_beneficios(diagnostico_origen,necesidad_origen)
 WHERE diagnostico_origen<>'' AND necesidad_origen<>'';
CREATE INDEX IF NOT EXISTS idx_p3_ben_estado ON p3_beneficios(estado);
CREATE TABLE IF NOT EXISTS p3_lienzos (
 id TEXT PRIMARY KEY, nombre TEXT NOT NULL, segmento TEXT NOT NULL,
 diagnostico_origen TEXT NOT NULL DEFAULT '', version INTEGER NOT NULL DEFAULT 1,
 responsable TEXT NOT NULL, creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(segmento,diagnostico_origen,version)
);
CREATE TABLE IF NOT EXISTS p3_tarjetas (
 id TEXT PRIMARY KEY, lienzo_id TEXT NOT NULL REFERENCES p3_lienzos(id) ON DELETE CASCADE,
 zona TEXT NOT NULL CHECK(zona IN ('servicios','generadores','aliviadores','ganancias','tareas','dolores')),
 titulo TEXT NOT NULL, detalle TEXT NOT NULL DEFAULT '', beneficio_id TEXT REFERENCES p3_beneficios(id),
 referencia TEXT NOT NULL DEFAULT '', creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_p3_tarjetas_lienzo ON p3_tarjetas(lienzo_id);
CREATE TABLE IF NOT EXISTS p3_vinculos (
 id TEXT PRIMARY KEY, lienzo_id TEXT NOT NULL REFERENCES p3_lienzos(id) ON DELETE CASCADE,
 origen_id TEXT NOT NULL REFERENCES p3_tarjetas(id) ON DELETE CASCADE,
 destino_id TEXT NOT NULL REFERENCES p3_tarjetas(id) ON DELETE CASCADE,
 justificacion TEXT NOT NULL DEFAULT '', creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(lienzo_id,origen_id,destino_id), CHECK(origen_id<>destino_id)
);
CREATE TABLE IF NOT EXISTS p3_declaraciones (
 id TEXT PRIMARY KEY, lienzo_id TEXT NOT NULL REFERENCES p3_lienzos(id),
 cliente TEXT NOT NULL, necesidad TEXT NOT NULL, solucion TEXT NOT NULL,
 capacidad TEXT NOT NULL, beneficio TEXT NOT NULL, declaracion TEXT NOT NULL,
 estado TEXT NOT NULL DEFAULT 'Borrador', creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS p3_soluciones (
 id TEXT PRIMARY KEY, codigo TEXT NOT NULL UNIQUE COLLATE NOCASE, nombre TEXT NOT NULL,
 cliente_id TEXT REFERENCES pmo_clientes(id), cliente TEXT NOT NULL, segmento TEXT NOT NULL DEFAULT '',
 necesidad_id TEXT REFERENCES p3_beneficios(id), necesidades_json TEXT NOT NULL DEFAULT '[]',
 servicios_json TEXT NOT NULL DEFAULT '[]', decision TEXT NOT NULL,
 descripcion TEXT NOT NULL DEFAULT '', beneficio TEXT NOT NULL DEFAULT '', metrica TEXT NOT NULL DEFAULT '',
 impacto INTEGER CHECK(impacto IS NULL OR impacto BETWEEN 1 AND 5),
 capacidad INTEGER CHECK(capacidad IS NULL OR capacidad BETWEEN 1 AND 5),
 recursos INTEGER CHECK(recursos IS NULL OR recursos BETWEEN 1 AND 5),
 facilidad INTEGER CHECK(facilidad IS NULL OR facilidad BETWEEN 1 AND 5),
 validador TEXT NOT NULL DEFAULT '', fecha_validacion TEXT NOT NULL DEFAULT '',
 observaciones_validacion TEXT NOT NULL DEFAULT '', evidencia_validacion TEXT NOT NULL DEFAULT '',
 estado TEXT NOT NULL DEFAULT 'Borrador', horizonte TEXT NOT NULL DEFAULT 'Desarrollo posterior',
 periodo TEXT NOT NULL DEFAULT '', riesgo TEXT NOT NULL DEFAULT '',
 responsable TEXT NOT NULL DEFAULT '', lienzo_id TEXT REFERENCES p3_lienzos(id),
 version_origen TEXT NOT NULL DEFAULT '', creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 CHECK(decision IN ('Adoptar','Adaptar o consolidar','Convertir en habilitador','Crear')),
 CHECK(estado IN ('Borrador','En análisis','En validación','Validada','Aprobada','Descartada')),
 CHECK(horizonte IN ('Implementación inicial','Desarrollo posterior','Evolución futura'))
);
CREATE TABLE IF NOT EXISTS p3_evaluaciones (
 id TEXT PRIMARY KEY, version INTEGER NOT NULL UNIQUE, responsable TEXT NOT NULL,
 estado TEXT NOT NULL DEFAULT 'Borrador' CHECK(estado IN ('Borrador','Finalizada')),
 puntaje INTEGER, clasificacion TEXT, acciones_mejora TEXT NOT NULL DEFAULT '',
 creada_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, finalizada_en TEXT
);
CREATE TABLE IF NOT EXISTS p3_respuestas (
 evaluacion_id TEXT NOT NULL REFERENCES p3_evaluaciones(id),
 numero INTEGER NOT NULL CHECK(numero BETWEEN 1 AND 25),
 valor INTEGER NOT NULL CHECK(valor BETWEEN 1 AND 5),
 observacion TEXT NOT NULL DEFAULT '', evidencia TEXT NOT NULL DEFAULT '',
 responsable TEXT NOT NULL, fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(evaluacion_id,numero)
);
CREATE TABLE IF NOT EXISTS p3_auditoria (
 id INTEGER PRIMARY KEY AUTOINCREMENT, entidad TEXT NOT NULL, objeto_id TEXT NOT NULL,
 accion TEXT NOT NULL, actor TEXT NOT NULL, detalle_json TEXT NOT NULL DEFAULT '{}',
 fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
'''

class ValidationError(ValueError):
    pass

def uid() -> str:
    return uuid.uuid4().hex

def required(value: Any, label: str) -> str:
    value = str(value or '').strip()
    if not value: raise ValidationError(f'Falta {label}.')
    return value

def validate_date(value: str | date, optional=False) -> str:
    if not str(value or '').strip() and optional:return ''
    try:return date.fromisoformat(str(value)).isoformat()
    except ValueError as exc:raise ValidationError('La fecha debe tener formato AAAA-MM-DD.') from exc

def _json(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,default=str)

def _rows(sql,params=(),path=None):
    with closing(connect(path)) as con:
        return [dict(x) for x in con.execute(sql,params).fetchall()]

def _row(sql,params=(),path=None):
    data=_rows(sql,params,path)
    return data[0] if data else None

def _aud(con,entity,key,action,actor,details=None):
    con.execute('INSERT INTO p3_auditoria(entidad,objeto_id,accion,actor,detalle_json) VALUES(?,?,?,?,?)',
                (entity,key,action,actor or 'PMO',_json(details or {})))

def initialize(path:Path|None=None):
    with closing(connect(path)) as con:
        con.executescript(SCHEMA)
        con.execute('INSERT OR IGNORE INTO schema_migrations(version) VALUES (7)')
        con.commit()

BENEFIT_FIELDS=('necesidad','entregable','beneficio','metrica','linea_base','meta','valor','tipo_valor',
                'medicion','estado','cliente','dependencia','resultado_id','servicios_json','evidencia',
                'responsable','version_origen','diagnostico_origen','necesidad_origen','estado_necesidad_origen')

def _benefit_data(data):
    d={k:data.get(k, '') for k in BENEFIT_FIELDS}
    d['necesidad']=required(d['necesidad'],'la necesidad')
    for k in BENEFIT_FIELDS:
        if k not in ('resultado_id','servicios_json'):d[k]=str(d[k] or '').strip()
    d['tipo_valor']=d['tipo_valor'] or 'Por definir'
    d['medicion']=d['medicion'] or 'Esperado'
    d['estado']=d['estado'] or 'Borrador'
    if d['tipo_valor'] not in VALUE_TYPES:raise ValidationError('Tipo de valor no reconocido.')
    if d['medicion'] not in BENEFIT_STATES:raise ValidationError('Estado del beneficio no reconocido.')
    if d['estado'] not in STATES:raise ValidationError('Estado de validación no reconocido.')
    if d['medicion']=='Medido' and not (d['metrica'] and d['valor'] and d['evidencia']):
        raise ValidationError('Un beneficio medido requiere métrica, valor efectivamente medido y evidencia.')
    result=d['resultado_id']
    if result in (None,''):d['resultado_id']=None
    else:
        try:d['resultado_id']=int(result)
        except (TypeError,ValueError) as e:raise ValidationError('Código de resultado inválido.') from e
        if not 1<=d['resultado_id']<=30:raise ValidationError('Resultado esperado fuera del catálogo 1–30.')
    services=d['servicios_json'] or []
    if isinstance(services,str):
        try:services=json.loads(services)
        except json.JSONDecodeError:services=[v.strip() for v in services.split(',') if v.strip()]
    if not isinstance(services,list):raise ValidationError('Servicios de referencia: se espera una lista.')
    normalized=[]
    for v in services:
        try:i=int(v)
        except (TypeError,ValueError) as e:raise ValidationError('Servicio de referencia no numérico.') from e
        if not 1<=i<=26:raise ValidationError('Servicio de referencia fuera del catálogo 1–26.')
        if i not in normalized:normalized.append(i)
    d['servicios_json']=_json(normalized)
    return d

def benefits(path=None):return _rows('SELECT * FROM p3_beneficios ORDER BY creado_en DESC,rowid DESC',path=path)

def benefit(key,path=None):return _row('SELECT * FROM p3_beneficios WHERE id=?',(key,),path)

def save_benefit(data:dict,actor:str,key:str|None=None,path=None):
    data=_benefit_data(data)
    owner=required(actor,'responsable')
    old_key = bool(key)
    with transaction(path) as con:
        if key:
            old=con.execute('SELECT * FROM p3_beneficios WHERE id=?',(key,)).fetchone()
            if not old:raise ValidationError('Registro no encontrado.')
            # V0.39.18: un registro vinculado nunca reescribe la necesidad ni la
            # clasificación de origen del Paso 02; sus beneficios sí son editables.
            immutable={'diagnostico_origen','necesidad_origen','version_origen','estado_necesidad_origen'}
            if old['diagnostico_origen'] and old['necesidad_origen']:
                immutable.update(('necesidad','cliente','dependencia','resultado_id','servicios_json'))
            cols=[k for k in BENEFIT_FIELDS if k not in immutable]
            con.execute('UPDATE p3_beneficios SET '+','.join(f'{k}=?' for k in cols)+', actualizado_en=CURRENT_TIMESTAMP WHERE id=?',
                        tuple(data[k] for k in cols)+(key,))
        else:
            key=uid();cols=list(BENEFIT_FIELDS)
            con.execute('INSERT INTO p3_beneficios(id,'+','.join(cols)+') VALUES(?,'+','.join(['?']*len(cols))+')',
                        (key,)+tuple(data[k] for k in cols))
        _aud(con,'beneficio',key,'editar' if old_key else 'crear',owner)
    return key

def delete_benefit(key,actor,path=None):
    with transaction(path) as con:
        origin=con.execute('SELECT diagnostico_origen,necesidad_origen FROM p3_beneficios WHERE id=?',(key,)).fetchone()
        if origin and origin['diagnostico_origen'] and origin['necesidad_origen']:
            raise ValidationError('Registro vinculado al Paso 02: no se elimina desde la matriz de beneficios. Conserva su trazabilidad.')
        if con.execute('SELECT 1 FROM p3_soluciones WHERE necesidad_id=?',(key,)).fetchone():
            raise ValidationError('La necesidad está vinculada a una solución. Desvincúlela primero.')
        if con.execute('SELECT 1 FROM p3_tarjetas WHERE beneficio_id=?',(key,)).fetchone():
            raise ValidationError('La necesidad está vinculada a una tarjeta. Desvincúlela primero.')
        if not con.execute('DELETE FROM p3_beneficios WHERE id=?',(key,)).rowcount:
            raise ValidationError('Registro no encontrado.')
        _aud(con,'beneficio',key,'eliminar',actor)

def _normalize_import_need(n):
    if not isinstance(n,dict):raise ValidationError('Una necesidad importada no es un objeto JSON.')
    return {
        'necesidad':str(n.get('problema') or n.get('pain') or n.get('necesidad') or n.get('descripcion') or '').strip(),
        'entregable':'', 'beneficio':str(n.get('ganancia') or n.get('gain') or n.get('beneficio') or '').strip(),
        'tipo_valor':'Por definir', 'medicion':'Esperado', 'estado':'Borrador',
        'estado_necesidad_origen':str(n.get('estado') or n.get('status') or ''),
        'dependencia':str(n.get('dependencia') or n.get('area') or ''),
        'resultado_id':n.get('resultado_id') or n.get('outcome') or n.get('resultado') or None,
        'cliente':str(n.get('cliente') or n.get('nombre_cliente') or n.get('segmento') or ''),
        'evidencia':str(n.get('fuente') or n.get('evidence') or n.get('evidencia') or ''),
        'necesidad_origen':str(n.get('id') or n.get('codigo') or ''),
    }

def _extract_p2(payload):
    if not isinstance(payload,dict):raise ValidationError('El expediente debe ser un objeto JSON.')
    needs=payload.get('necesidades',payload.get('pains'))
    if needs is None and isinstance(payload.get('diagnostico'),dict):
        needs=payload['diagnostico'].get('necesidades')
    if not isinstance(needs,list):raise ValidationError('El expediente no contiene una lista de necesidades reconocible.')
    diag=payload.get('diagnostico',{})
    if isinstance(diag,dict):diag_id=str(diag.get('id') or diag.get('codigo') or '').strip()
    else:diag_id=str(diag or '').strip()
    return diag_id,needs

def preview_step2_json(payload):
    did,ns=_extract_p2(payload)
    return {'diagnostico_id':did,'necesidades':len(ns),'servicios_candidatos':len(payload.get('servicios_candidatos',[])),
            'corridas':len(payload.get('corridas',[])),'version':payload.get('version','Sin especificar')}

def import_step2_json(payload:dict,source:str,actor:str,selection:list[str]|None=None,path=None):
    did,ns=_extract_p2(payload)
    source=required(source,'fuente del expediente')
    actor=required(actor,'responsable de importación')
    digest=hashlib.sha256(_json(payload).encode('utf-8')).hexdigest()
    did=did or 'JSON-'+digest[:12]
    snap=payload.copy()
    diagnostic=payload.get('diagnostico')
    diag_version=str((diagnostic or {}).get('ciclo','') if isinstance(diagnostic,dict) else '')
    matrix_version=str(payload.get('matrix_version') or payload.get('version_matriz') or '')
    if not matrix_version:
        for r in reversed(payload.get('corridas',[])):
            if isinstance(r,dict):
                matrix_version=str(r.get('matrix_version_id') or r.get('modelo') or '')
                if matrix_version:break
    from . import step2
    created=skipped=0
    selected=set(selection) if selection is not None else None
    with transaction(path) as con:
        existing=con.execute('SELECT id FROM p3_sources WHERE diagnostico_origen=? AND hash_sha256=?',(did,digest)).fetchone()
        sid=existing[0] if existing else uid()
        if not existing:
            con.execute('INSERT INTO p3_sources(id,diagnostico_origen,fuente,version_origen,version_matriz,hash_sha256,snapshot_json) VALUES (?,?,?,?,?,?,?)',
                        (sid,did,source,diag_version or str(payload.get('version','')),matrix_version,digest,_json(snap)))
        for n in ns:
            orig=_normalize_import_need(n)
            if not orig['necesidad']:raise ValidationError('Expediente incluye una necesidad sin descripción.')
            original_id=orig['necesidad_origen']
            if not original_id:raise ValidationError('La importación requiere ID estable en cada necesidad.')
            if selected is not None and original_id not in selected:continue
            if con.execute('SELECT 1 FROM p3_beneficios WHERE diagnostico_origen=? AND necesidad_origen=?',
                           (did,original_id)).fetchone():
                skipped+=1;continue
            client_id=str(n.get('cliente_id') or '') or None
            if client_id and not con.execute('SELECT 1 FROM pmo_clientes WHERE id=?',(client_id,)).fetchone():client_id=None
            if client_id and not orig['cliente']:
                client=con.execute('SELECT nombre FROM pmo_clientes WHERE id=?',(client_id,)).fetchone()
                orig['cliente']=client[0]
            orig['diagnostico_origen']=did
            orig['version_origen']=diag_version or str(payload.get('version',''))
            orig['responsable']=actor
            data=_benefit_data(orig)
            columns=list(BENEFIT_FIELDS)
            con.execute('INSERT INTO p3_beneficios(id,fuente_id,cliente_id,'+','.join(columns)+') VALUES (?,?,?,'+','.join('?' for _ in columns)+')',
                        (uid(),sid,client_id)+tuple(data[k] for k in columns))
            created+=1
        _aud(con,'expediente_p2',sid,'importar',actor,{'diagnostico':did,'nuevos':created,'omitidos':skipped,'fuente':source})
    return {'nuevos':created,'omitidos':skipped,'diagnostico':did,'version_matriz':matrix_version,'fuente_id':sid}

def import_step2_direct(diagnostic_id:str,actor:str,selection:list[str]|None=None,path=None):
    from . import step2
    payload=json.loads(step2.transfer_json(diagnostic_id,path).decode('utf-8'))
    with closing(connect(path)) as con:
        run=con.execute('SELECT matrix_version_id, resultados_json, pesos_json, fecha FROM p2_corridas WHERE diagnostico_id=? ORDER BY fecha DESC,rowid DESC LIMIT 1',(diagnostic_id,)).fetchone()
        if run:
            payload['matrix_version']=run['matrix_version_id'] or ''
            payload['ranking_historico']=json.loads(run['resultados_json'])
            payload['ponderaciones_historicas']=json.loads(run['pesos_json'])
            payload['fecha_corrida']=run['fecha']
    return import_step2_json(payload,f'Base local · Paso 2 · {diagnostic_id}',actor,selection,path)

def sources(path=None):return _rows('SELECT id,diagnostico_origen,fuente,version_origen,version_matriz,importado_en FROM p3_sources ORDER BY importado_en DESC',path=path)

def import_benefit_rows(records:list[dict],actor:str,path=None):
    actor=required(actor,'responsable')
    if not records:raise ValidationError('Archivo sin registros.')
    if len(records)>5000:raise ValidationError('Se admiten hasta 5.000 registros por archivo.')
    prepared=[_benefit_data(x) for x in records]
    with transaction(path) as con:
        for data in prepared:
            key=uid();columns=list(BENEFIT_FIELDS)
            con.execute('INSERT INTO p3_beneficios(id,'+','.join(columns)+') VALUES (?,'+','.join('?' for _ in columns)+')',
                        (key,)+tuple(data[k] for k in columns))
        _aud(con,'beneficios_excel',uid(),'importar',actor,{'filas':len(prepared)})
    return len(prepared)

# Lienzo (tres zonas de propuesta + tres de perfil)
def canvases(path=None):return _rows('SELECT * FROM p3_lienzos ORDER BY creado_en DESC,rowid DESC',path=path)
def canvas(key,path=None):return _row('SELECT * FROM p3_lienzos WHERE id=?',(key,),path)
def cards(key,path=None):return _rows('SELECT * FROM p3_tarjetas WHERE lienzo_id=? ORDER BY creado_en,rowid',(key,),path)
def links(key,path=None):return _rows('SELECT * FROM p3_vinculos WHERE lienzo_id=? ORDER BY creado_en,rowid',(key,),path)
def statements(key,path=None):return _rows('SELECT * FROM p3_declaraciones WHERE lienzo_id=? ORDER BY creado_en DESC',(key,),path)

def create_canvas(segment:str,actor:str,name:str='',origin:str='',clone_from:str|None=None,path=None):
    segment=required(segment,'cliente o segmento')
    actor=required(actor,'responsable')
    with transaction(path) as con:
        v=con.execute('SELECT COALESCE(MAX(version),0)+1 FROM p3_lienzos WHERE segmento=? AND diagnostico_origen=?',(segment,origin)).fetchone()[0]
        key=uid()
        con.execute('INSERT INTO p3_lienzos(id,nombre,segmento,diagnostico_origen,version,responsable) VALUES(?,?,?,?,?,?)',
                    (key,name or f'Lienzo · {segment} · v{v}',segment,origin,v,actor))
        if clone_from:
            src=con.execute('SELECT 1 FROM p3_lienzos WHERE id=?',(clone_from,)).fetchone()
            if not src:raise ValidationError('Lienzo original inexistente.')
            mapping={}
            for item in con.execute('SELECT * FROM p3_tarjetas WHERE lienzo_id=?',(clone_from,)).fetchall():
                new_id=uid();mapping[item['id']]=new_id
                con.execute('INSERT INTO p3_tarjetas(id,lienzo_id,zona,titulo,detalle,beneficio_id,referencia) VALUES(?,?,?,?,?,?,?)',
                            (new_id,key,item['zona'],item['titulo'],item['detalle'],item['beneficio_id'],item['referencia']))
            for item in con.execute('SELECT * FROM p3_vinculos WHERE lienzo_id=?',(clone_from,)).fetchall():
                con.execute('INSERT INTO p3_vinculos(id,lienzo_id,origen_id,destino_id,justificacion) VALUES(?,?,?,?,?)',
                            (uid(),key,mapping[item['origen_id']],mapping[item['destino_id']],item['justificacion']))
        _aud(con,'lienzo',key,'crear',actor,{'segmento':segment,'version':v,'origen':clone_from})
    return key

def save_card(lienzo:str,zona:str,titulo:str,detalle:str='',beneficio_id:str|None=None,actor='PMO',key=None,reference='',path=None):
    titulo=required(titulo,'título de la tarjeta')
    if zona not in ZONES:raise ValidationError('Zona del lienzo inválida.')
    old_key = bool(key)
    with transaction(path) as con:
        if not con.execute('SELECT 1 FROM p3_lienzos WHERE id=?',(lienzo,)).fetchone():raise ValidationError('Lienzo inexistente.')
        if beneficio_id and not con.execute('SELECT 1 FROM p3_beneficios WHERE id=?',(beneficio_id,)).fetchone():raise ValidationError('Beneficio de referencia inexistente.')
        if key:
            row=con.execute('SELECT lienzo_id FROM p3_tarjetas WHERE id=?',(key,)).fetchone()
            if not row or row[0]!=lienzo:raise ValidationError('Tarjeta inexistente en este lienzo.')
            con.execute('UPDATE p3_tarjetas SET zona=?,titulo=?,detalle=?,beneficio_id=?,referencia=? WHERE id=?',
                        (zona,titulo,detalle,beneficio_id,reference,key))
        else:
            key=uid()
            con.execute('INSERT INTO p3_tarjetas(id,lienzo_id,zona,titulo,detalle,beneficio_id,referencia) VALUES(?,?,?,?,?,?,?)',
                        (key,lienzo,zona,titulo,detalle,beneficio_id,reference))
        _aud(con,'tarjeta',key,'editar' if old_key else 'crear',actor,{'lienzo':lienzo,'zona':zona})
    return key

def move_card(key,zona,actor,path=None):
    if zona not in ZONES:raise ValidationError('Zona inválida.')
    with transaction(path) as con:
        if not con.execute('UPDATE p3_tarjetas SET zona=? WHERE id=?',(zona,key)).rowcount:raise ValidationError('Tarjeta inexistente.')
        _aud(con,'tarjeta',key,'mover',actor,{'zona':zona})

def remove_card(key,actor,path=None):
    with transaction(path) as con:
        if not con.execute('DELETE FROM p3_tarjetas WHERE id=?',(key,)).rowcount:raise ValidationError('Tarjeta inexistente.')
        _aud(con,'tarjeta',key,'eliminar',actor)

def create_link(lienzo,origin,destination,reason,actor,path=None):
    if origin==destination:raise ValidationError('No es posible vincular una tarjeta consigo misma.')
    with transaction(path) as con:
        check=con.execute('SELECT id,zona FROM p3_tarjetas WHERE id IN (?,?) AND lienzo_id=?',(origin,destination,lienzo)).fetchall()
        if len(check)!=2:raise ValidationError('Ambas tarjetas deben pertenecer al mismo lienzo.')
        if check[0]['zona']==check[1]['zona'] and check[0]['zona'] in ZONES:
            # Permit connections in same zone but no incoherent cross-canvas links.
            pass
        key=uid()
        try:con.execute('INSERT INTO p3_vinculos(id,lienzo_id,origen_id,destino_id,justificacion) VALUES(?,?,?,?,?)',
                        (key,lienzo,origin,destination,str(reason or '')))
        except Exception as ex:
            if 'UNIQUE constraint' in str(ex):raise ValidationError('La conexión ya está registrada.') from ex
            raise
        _aud(con,'vinculo',key,'crear',actor,{'origen':origin,'destino':destination})
    return key

def remove_link(key,actor,path=None):
    with transaction(path) as con:
        if not con.execute('DELETE FROM p3_vinculos WHERE id=?',(key,)).rowcount:raise ValidationError('Vínculo inexistente.')
        _aud(con,'vinculo',key,'eliminar',actor)

def canvas_coverage(lienzo,path=None):
    cs=cards(lienzo,path);ls=links(lienzo,path)
    pain=[c for c in cs if c['zona']=='dolores'];rel={l['origen_id'] for l in ls}|{l['destino_id'] for l in ls}
    return {'dolores':len(pain),'con_vinculo':sum(c['id'] in rel for c in pain),
            'sin_atender':sum(c['id'] not in rel for c in pain),
            'soluciones_sin_necesidad':sum(c['zona']=='servicios' and c['id'] not in rel for c in cs)}

def save_statement(lienzo:str,client:str,need:str,solution:str,capability:str,benefit_text:str,actor:str,path=None):
    d={'cliente':required(client,'cliente'),'necesidad':required(need,'necesidad'),
       'solucion':required(solution,'solución'),'capacidad':required(capability,'capacidad de PMO'),
       'beneficio':required(benefit_text,'beneficio')}
    statement=f"Para {d['cliente']}, que necesita {d['necesidad']}, la PMO propone {d['solucion']}, aprovechando {d['capacidad']}, para contribuir a {d['beneficio']}."
    with transaction(path) as con:
        if not con.execute('SELECT 1 FROM p3_lienzos WHERE id=?',(lienzo,)).fetchone():raise ValidationError('Lienzo no registrado.')
        key=uid()
        con.execute('INSERT INTO p3_declaraciones(id,lienzo_id,cliente,necesidad,solucion,capacidad,beneficio,declaracion) VALUES(?,?,?,?,?,?,?,?)',
                    (key,lienzo,d['cliente'],d['necesidad'],d['solucion'],d['capacidad'],d['beneficio'],statement))
        _aud(con,'declaracion',key,'borrador',actor)
    return statement

def canvas_export_json(lienzo,path=None):
    obj=canvas(lienzo,path)
    if not obj:raise ValidationError('Lienzo inexistente.')
    return _json({'schema':'PMO-CENS-P3-LIENZO-v1','lienzo':obj,'tarjetas':cards(lienzo,path),
                  'vinculos':links(lienzo,path),'declaraciones':statements(lienzo,path)})

# Soluciones
def solutions(path=None):return _rows('SELECT * FROM p3_soluciones ORDER BY creado_en DESC,rowid DESC',path=path)
def solution(key,path=None):return _row('SELECT * FROM p3_soluciones WHERE id=?',(key,),path)
def feasibility(row):
    vals=[row.get(k) for k in ('impacto','capacidad','recursos','facilidad')]
    return round(sum(vals)/4,2) if all(type(v) is int and 1<=v<=5 for v in vals) else None

def potential_quick_win(row):
    """Señal orientativa CENS: alta viabilidad e inicio previsto, nunca aprobación."""
    score=feasibility(row)
    return bool(score is not None and score>=4.0 and row.get('horizonte')=='Implementación inicial'
                and row.get('estado')!='Descartada')

def approval_errors(row):
    errors=[]
    for name,label in [('cliente','cliente objetivo'),('necesidad_id','necesidad vinculada'),
                       ('beneficio','beneficio esperado'),('decision','decisión de diseño'),
                       ('validador','representante que valida'),('fecha_validacion','fecha de validación'),
                       ('evidencia_validacion','evidencia de validación')]:
        if not str(row.get(name) or '').strip():errors.append(label)
    return errors

def _solution_data(data):
    fields=('codigo','nombre','cliente','segmento','necesidad_id','necesidades_json','servicios_json','decision',
            'descripcion','beneficio','metrica','impacto','capacidad','recursos','facilidad',
            'validador','fecha_validacion','observaciones_validacion','evidencia_validacion','estado',
            'horizonte','periodo','riesgo','responsable','lienzo_id')
    d={k:data.get(k) for k in fields}
    d['codigo']=required(d['codigo'],'código de solución')
    d['nombre']=required(d['nombre'],'nombre de solución')
    d['cliente']=str(d['cliente'] or '').strip()
    d['decision']=required(d['decision'],'decisión de diseño')
    if d['decision'] not in DECISIONS:raise ValidationError('La decisión debe ser adoptar, adaptar, habilitador o crear.')
    d['estado']=d['estado'] or 'Borrador'
    if d['estado'] not in STATES:raise ValidationError('Estado de solución inválido.')
    d['horizonte']=d['horizonte'] or 'Desarrollo posterior'
    if d['horizonte'] not in HORIZONS:raise ValidationError('Horizonte de ruta inválido.')
    for k in ('impacto','capacidad','recursos','facilidad'):
        if d[k] in ('',None):d[k]=None
        elif isinstance(d[k],bool) or not 1<=int(d[k])<=5:raise ValidationError(f'Valor de {k} debe estar entre 1 y 5.')
        else:d[k]=int(d[k])
    for k in ('servicios_json','necesidades_json'):
        val=d[k] or []
        if isinstance(val,str):
            try:val=json.loads(val)
            except json.JSONDecodeError:val=[v.strip() for v in val.split(',') if v.strip()]
        if not isinstance(val,list):raise ValidationError('Los vínculos deben ser una lista.')
        if k=='servicios_json':
            try:val=[int(x) for x in val]
            except (TypeError,ValueError) as exc:raise ValidationError('Servicio PMI no numérico.') from exc
            if any(x<1 or x>26 for x in val):raise ValidationError('Servicios PMI válidos: 1–26.')
        d[k]=_json(val)
    d['fecha_validacion']=validate_date(d['fecha_validacion'],True)
    for k in ('segmento','descripcion','beneficio','metrica','validador','observaciones_validacion',
              'evidencia_validacion','periodo','riesgo','responsable'):
        d[k]=str(d[k] or '').strip()
    d['necesidad_id']=str(d['necesidad_id'] or '').strip() or None
    d['lienzo_id']=str(d['lienzo_id'] or '').strip() or None
    if d['estado']=='Aprobada':
        missing=approval_errors(d)
        if missing:raise ValidationError('No puede aprobar: faltan '+', '.join(missing)+'.')
    return d

def save_solution(data:dict,actor:str,key:str|None=None,path=None):
    old_key = bool(key)
    d=_solution_data(data)
    actor=required(actor,'responsable')
    with transaction(path) as con:
        if d['necesidad_id'] and not con.execute('SELECT 1 FROM p3_beneficios WHERE id=?',(d['necesidad_id'],)).fetchone():
            raise ValidationError('La necesidad relacionada no existe en el Paso 3.')
        if d['lienzo_id'] and not con.execute('SELECT 1 FROM p3_lienzos WHERE id=?',(d['lienzo_id'],)).fetchone():
            raise ValidationError('El lienzo relacionado no existe.')
        cols=list(d)
        if key:
            if not con.execute('SELECT 1 FROM p3_soluciones WHERE id=?',(key,)).fetchone():raise ValidationError('Solución inexistente.')
            con.execute('UPDATE p3_soluciones SET '+','.join(f'{k}=?' for k in cols)+',actualizado_en=CURRENT_TIMESTAMP WHERE id=?',
                        tuple(d[k] for k in cols)+(key,))
        else:
            key=uid()
            con.execute('INSERT INTO p3_soluciones(id,'+','.join(cols)+') VALUES (?,'+','.join('?' for _ in cols)+')',
                        (key,)+tuple(d[k] for k in cols))
        _aud(con,'solucion',key,'editar' if old_key else 'crear',actor,{'estado':d['estado']})
    return key

def remove_solution(key,actor,path=None):
    with transaction(path) as con:
        if not con.execute('DELETE FROM p3_soluciones WHERE id=?',(key,)).rowcount:raise ValidationError('Solución inexistente.')
        _aud(con,'solucion',key,'eliminar',actor)

def step4_transfer(path=None):
    ready=[];blocked=[]
    for item in solutions(path):
        if item['estado']!='Aprobada':continue
        missing=approval_errors(item)
        if missing:blocked.append({'codigo':item['codigo'],'faltan':missing});continue
        d={k:v for k,v in item.items()}
        from .public_codes import code
        d['codigo_publico']=code('solucion',item['id'],path)
        d['services']=json.loads(d.pop('servicios_json'))
        d['needs']=json.loads(d.pop('necesidades_json'))
        d['viability']=feasibility(item)
        d['benefit_measurement']='Esperado'
        ready.append(d)
    return {'schema':'PMO-FLYWHEEL-CENS-paso4-input-v1','exportedAt':datetime.now(timezone.utc).isoformat(),
            'source':{'step':'Paso 3','implementation':'Streamlit V0.12','referenceStep2':sources(path)},
            'proposals':ready,'blocked':blocked,'note':'Transferencia no modifica los datos ni implementa Paso 4.'}

# V0.39.18 · Acuerdos de valor versionados en la auditoría existente.
# No cambia la aprobación histórica, los estados ni el esquema de transferencia.
VALUE_AGREEMENT_FIELDS=('codigo','nombre','cliente','necesidad_id','beneficio','decision',
                        'validador','fecha_validacion','evidencia_validacion','estado')

def _agreement_hash(row):
    payload={k:row.get(k) for k in VALUE_AGREEMENT_FIELDS}
    return hashlib.sha256(_json(payload).encode('utf-8')).hexdigest()

def agreement_record(solution_id,path=None):
    recs=_rows("""SELECT detalle_json,actor,fecha FROM p3_auditoria
              WHERE entidad='acuerdo_valor' AND objeto_id=? AND accion='validar'
              ORDER BY id DESC LIMIT 1""",(solution_id,),path)
    if not recs:return None
    item=recs[0]
    try:details=json.loads(item['detalle_json'])
    except (ValueError,TypeError):details={}
    row=solution(solution_id,path)
    return {'version':details.get('version'),'fecha_registro':item['fecha'],'responsable':item['actor'],
            'evidencia':details.get('evidencia',''),'vigente':bool(row and details.get('hash')==_agreement_hash(row)),
            'huella_sha256':details.get('hash','')}

def register_value_agreement(solution_id,actor,confirmed=False,path=None):
    """La acción humana congela evidencia y compromisos; no infiere aceptación automática."""
    if not confirmed:raise ValidationError('Debes confirmar que la validación está sustentada documentalmente.')
    actor=required(actor,'responsable de registro')
    with transaction(path) as con:
        row=con.execute('SELECT * FROM p3_soluciones WHERE id=?',(solution_id,)).fetchone()
        if not row:raise ValidationError('Solución inexistente.')
        d=dict(row)
        if d['estado']!='Aprobada':raise ValidationError('Solo se registra el acuerdo de una solución aprobada por responsable autorizado.')
        missing=approval_errors(d)
        if missing:raise ValidationError('Acuerdo incompleto: '+', '.join(missing)+'.')
        digest=_agreement_hash(d)
        rows=con.execute("""SELECT detalle_json FROM p3_auditoria
              WHERE entidad='acuerdo_valor' AND objeto_id=? AND accion='validar'
              ORDER BY id""",(solution_id,)).fetchall()
        versions=[]
        for r in rows:
            try:versions.append(json.loads(r['detalle_json']))
            except (TypeError,ValueError):continue
        if versions and versions[-1].get('hash')==digest:return len(versions)
        version=len(versions)+1
        _aud(con,'acuerdo_valor',solution_id,'validar',actor,{'version':version,'hash':digest,
             'evidencia':d['evidencia_validacion'],'fecha_validacion':d['fecha_validacion'],
             'cliente':d['cliente'],'necesidad_id':d['necesidad_id']})
    return version

# Autoevaluación PMI: cinco dimensiones, 25 criterios, sin aprobar por puntaje.
def classification(score:int):
    if not 25<=score<=125:raise ValidationError('Puntuación de autoevaluación fuera de 25–125.')
    if score>=113:return 'Excelente'
    if score>=98:return 'Bien'
    if score>=77:return 'Promedio'
    if score>=51:return 'Pobre'
    return 'Crítico'

def evaluations(path=None):return _rows('SELECT * FROM p3_evaluaciones ORDER BY version DESC',path=path)
def evaluation(key,path=None):return _row('SELECT * FROM p3_evaluaciones WHERE id=?',(key,),path)
def assessment_answers(key,path=None):return _rows('SELECT * FROM p3_respuestas WHERE evaluacion_id=? ORDER BY numero',(key,),path)

def create_evaluation(owner,actor=None,path=None):
    owner=required(owner,'responsable de evaluación')
    with transaction(path) as con:
        version=con.execute('SELECT COALESCE(MAX(version),0)+1 FROM p3_evaluaciones').fetchone()[0]
        key=uid()
        con.execute('INSERT INTO p3_evaluaciones(id,version,responsable) VALUES (?,?,?)',(key,version,owner))
        _aud(con,'evaluacion',key,'iniciar',actor or owner,{'version':version})
    return key

def save_assessment_answer(key,num:int,rating:int|None,comment:str='',evidence:str='',actor='',path=None):
    if isinstance(num,bool) or not 1<=int(num)<=25:raise ValidationError('Pregunta fuera del instrumento de 25 criterios.')
    if rating is not None and (type(rating) is not int or not 1<=rating<=5):
        raise ValidationError('Calificación permitida: entero de 1 a 5.')
    with transaction(path) as con:
        row=con.execute('SELECT estado,responsable FROM p3_evaluaciones WHERE id=?',(key,)).fetchone()
        if not row:raise ValidationError('Evaluación inexistente.')
        if row['estado']=='Finalizada':raise ValidationError('Una evaluación finalizada es inmutable. Inicie una nueva versión.')
        if rating is None:
            con.execute('DELETE FROM p3_respuestas WHERE evaluacion_id=? AND numero=?',(key,num))
        else:
            con.execute('''INSERT INTO p3_respuestas(evaluacion_id,numero,valor,observacion,evidencia,responsable)
              VALUES(?,?,?,?,?,?) ON CONFLICT(evaluacion_id,numero) DO UPDATE SET
              valor=excluded.valor,observacion=excluded.observacion,evidencia=excluded.evidencia,
              responsable=excluded.responsable,fecha=CURRENT_TIMESTAMP''',
              (key,num,rating,comment,evidence,actor or row['responsable']))
        _aud(con,'evaluacion',key,'respuesta',actor or row['responsable'],{'numero':num,'valor':rating})

def assessment_summary(key,path=None):
    ev=evaluation(key,path)
    if not ev:raise ValidationError('Evaluación inexistente.')
    answers=assessment_answers(key,path)
    by_num={r['numero']:r for r in answers}
    dimensions=[]
    for index,(title,qs) in enumerate(DIMENSIONS):
        selected=[by_num.get(i) for i in range(index*5+1,index*5+6)]
        count=sum(bool(r) for r in selected)
        dimensions.append({'nombre':title,'respondidas':count,'subtotal':sum(r['valor'] for r in selected if r),
                           'promedio':round(sum(r['valor'] for r in selected if r)/count,2) if count else None,
                           'con_evidencia':sum(bool(r and r['evidencia'].strip()) for r in selected)})
    count=len(answers);score=sum(r['valor'] for r in answers)
    return {'id':key,'version':ev['version'],'estado':ev['estado'],'responsable':ev['responsable'],
            'respondidas':count,'avance_pct':count*4,'puntaje_parcial':score,
            'puntaje':score if count==25 else None,'clasificacion':classification(score) if count==25 else None,
            'con_evidencia':sum(bool(r['evidencia'].strip()) for r in answers),'dimensiones':dimensions,
            'fecha':ev['finalizada_en'] or ev['creada_en']}

def finish_evaluation(key,actor,improvements='',path=None):
    with transaction(path) as con:
        current=con.execute('SELECT estado FROM p3_evaluaciones WHERE id=?',(key,)).fetchone()
        if not current:raise ValidationError('Evaluación inexistente.')
        if current['estado']=='Finalizada':raise ValidationError('Evaluación ya finalizada.')
        ratings=[x[0] for x in con.execute('SELECT valor FROM p3_respuestas WHERE evaluacion_id=?',(key,))]
        if len(ratings)!=25:raise ValidationError(f'Faltan {25-len(ratings)} criterios por evaluar.')
        score=sum(ratings)
        con.execute('UPDATE p3_evaluaciones SET estado=?,puntaje=?,clasificacion=?,acciones_mejora=?,finalizada_en=CURRENT_TIMESTAMP WHERE id=?',
                    ('Finalizada',score,classification(score),str(improvements or ''),key))
        _aud(con,'evaluacion',key,'finalizar',actor,{'puntaje':score,'clasificacion':classification(score)})
    return score

def assessment_export(key,path=None):
    return {'schema':'PMO-CENS-P3-EVALUACION-v1','resumen':assessment_summary(key,path),
            'respuestas':[{**dict(r),'pregunta':QUESTIONS[r['numero']-1]} for r in assessment_answers(key,path)],
            'historico':[{'version':x['version'],'estado':x['estado'],'puntaje':x['puntaje'],'clasificacion':x['clasificacion'],
                          'fecha':x['finalizada_en'] or x['creada_en']} for x in evaluations(path)]}

def service_candidates_from_source(source_id:str,path=None):
    """Solo lectura del ranking/candidatos importados del Paso 2."""
    row=_row('SELECT snapshot_json FROM p3_sources WHERE id=?',(source_id,),path)
    if not row:raise ValidationError('Fuente del Paso 2 no encontrada.')
    payload=json.loads(row['snapshot_json'])
    from .step2_catalog import SERVICES
    result=[];seen=set()
    for item in payload.get('servicios_candidatos',[]):
        if not isinstance(item,dict):continue
        try:sid=int(item.get('servicio_id') or item.get('id'))
        except (ValueError,TypeError):continue
        if sid in SERVICES and sid not in seen:
            result.append({'id':sid,'nombre':SERVICES[sid], 'estado_origen':item.get('estado',''),
                           'justificacion_origen':item.get('justificacion','')})
            seen.add(sid)
    if not result:
        historic=payload.get('ranking_historico',{})
        for item in historic.get('services',[]) if isinstance(historic,dict) else []:
            try:sid=int(item.get('id'))
            except (ValueError,TypeError,AttributeError):continue
            if sid in SERVICES and sid not in seen:
                result.append({'id':sid,'nombre':SERVICES[sid], 'estado_origen':'Ranking',
                               'justificacion_origen':'Servicio de referencia del ranking histórico del Paso 2'})
                seen.add(sid)
    return result

def import_service_candidates(source_id:str,selected_ids:list[int],decision:str,actor:str,path=None):
    """Genera borradores, nunca soluciones aprobadas; no modifica el motor V5."""
    actor=required(actor,'responsable de las soluciones')
    if decision not in DECISIONS:raise ValidationError('Seleccione una decisión preliminar válida.')
    source=_row('SELECT * FROM p3_sources WHERE id=?',(source_id,),path)
    if not source:raise ValidationError('Fuente no registrada.')
    valid={x['id']:x for x in service_candidates_from_source(source_id,path)}
    requested=[int(x) for x in selected_ids]
    if not set(requested)<=set(valid):raise ValidationError('Se seleccionó un servicio no registrado en el expediente del Paso 2.')
    created=skipped=0
    with transaction(path) as con:
        for sid in sorted(set(requested)):
            code=f'P3-{source_id[:7]}-S{sid:02d}'
            if con.execute('SELECT 1 FROM p3_soluciones WHERE codigo=?',(code,)).fetchone():skipped+=1;continue
            fields={'codigo':code,'nombre':valid[sid]['nombre'],'cliente':'','segmento':'',
                    'decision':decision,'descripcion':'Concepto importado del Paso 2, sujeto a diseño y validación. '+str(valid[sid]['justificacion_origen'] or ''),
                    'servicios_json':[sid],'beneficio':'','metrica':'','estado':'Borrador',
                    'horizonte':'Desarrollo posterior','responsable':actor}
            d=_solution_data(fields)
            cols=list(d)
            con.execute('INSERT INTO p3_soluciones(id,'+','.join(cols)+',version_origen) VALUES (?,'+','.join('?' for _ in cols)+',?)',
                        (uid(),)+tuple(d[k] for k in cols)+(source['version_matriz'] or source['version_origen'],))
            created+=1
        _aud(con,'soluciones','batch','importar_candidatos',actor,{'fuente':source_id,'creados':created,'omitidos':skipped})
    return {'nuevos':created,'omitidos':skipped}
