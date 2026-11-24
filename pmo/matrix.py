"""Gestión auditable de correspondencias resultado–servicio (Paso 2).

Matriz documental 0/1 de X2 y escenario documental experimental 0..4,
ambos procedentes de un insumo del usuario, NO intensidades oficiales PMOGA.
No reemplaza autorización corporativa, SSO ni firma electrónica.
"""
from __future__ import annotations
import csv
import io
import json
import hashlib
import math
import uuid
from datetime import date
from pathlib import Path
from .storage import connect, transaction
from .clients import ValidationError

DATA = Path(__file__).parent / 'data' / 'matriz_780.json'
DOC_ID = 'X2-DOC-2026-V1'
EXPERIMENT_ID = 'CENS-EXP-2026-V1'
V5_ID = 'CENS-V5-RECONSTRUIDA-30FOCO'
V5_HASH = '442761f2da618a6e8ed11d6355591c1a5ad59605ceff038282c4ef4cf407d8d8'
V5_DATA = Path(__file__).parent / 'data' / 'matriz_v5_reconstruida.json'
VERSION_STATES = {'REFERENCIA', 'BORRADOR', 'EN_REVISION', 'APROBADA', 'ARCHIVADA'}

def source_data():
    with DATA.open(encoding='utf-8') as f: data=json.load(f)
    out={int(r['id']) for r in data['resultados']}
    svc={int(r['id']) for r in data['servicios']}
    pairs={(int(r['resultado_id']),int(r['servicio_id'])) for r in data['correspondencias']}
    if out!=set(range(1,31)) or svc!=set(range(1,27)) or len(data['correspondencias'])!=780 or pairs!={(o,s) for o in out for s in svc}:
        raise RuntimeError('La matriz de origen no tiene los 780 pares completos y únicos.')
    if sum(int(r['intensidad_base']) for r in data['correspondencias'])!=128:
        raise RuntimeError('La fuente documental no tiene las 128 relaciones esperadas.')
    return data

def v5_source_data():
    """Valida la matriz reconstruida contra su huella publicada; no la homologa a PMOGA."""
    raw=json.loads(V5_DATA.read_text(encoding='utf-8'))
    mat=raw.get('matrix')
    if not isinstance(mat,list) or len(mat)!=30 or any(not isinstance(row,list) or len(row)!=26 for row in mat):
        raise RuntimeError('V5 requiere matriz 30 x 26 completa.')
    if any(type(value) is not int or value not in (0,1,2,3,4) for row in mat for value in row):
        raise RuntimeError('Las intensidades V5 deben ser enteras en 0..4.')
    digest=hashlib.sha256(json.dumps(mat,separators=(',',':')).encode()).hexdigest()
    if digest!=V5_HASH:
        raise RuntimeError('La matriz V5 no coincide con la huella SHA256 de referencia.')
    if sum(value>0 for row in mat for value in row)!=290:
        raise RuntimeError('La matriz V5 no contiene las 290 relaciones positivas esperadas.')
    return raw

SOURCE = source_data()
V5_SOURCE = v5_source_data()
PROVENANCE = {(int(r['resultado_id']),int(r['servicio_id'])):r for r in SOURCE['correspondencias']}
OUTCOMES = {int(x['id']):x['nombre'] for x in SOURCE['resultados']}
SERVICES = {int(x['id']):x['nombre'] for x in SOURCE['servicios']}

SCHEMA = """
CREATE TABLE IF NOT EXISTS pmo_matrix_versions (
 id TEXT PRIMARY KEY, fuente TEXT NOT NULL, estado TEXT NOT NULL
 CHECK(estado IN ('REFERENCIA','BORRADOR','EN_REVISION','APROBADA','ARCHIVADA')),
 descripcion TEXT NOT NULL, origen_version TEXT REFERENCES pmo_matrix_versions(id),
 creado_por TEXT NOT NULL, aprobador TEXT, aprobada_en TEXT,
 motivo_aprobacion TEXT, creada_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 actualizada_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS pmo_matrix_links (
 version_id TEXT NOT NULL REFERENCES pmo_matrix_versions(id),
 resultado_id INTEGER NOT NULL CHECK(resultado_id BETWEEN 1 AND 30),
 servicio_id INTEGER NOT NULL CHECK(servicio_id BETWEEN 1 AND 26),
 intensidad INTEGER NOT NULL CHECK(intensidad BETWEEN 0 AND 4),
 x2_documentado INTEGER NOT NULL CHECK(x2_documentado IN (0,1)),
 presente_html INTEGER NOT NULL CHECK(presente_html IN (0,1)),
 propuesta_directa INTEGER NOT NULL CHECK(propuesta_directa IN (0,1)),
 propuesta_inversa INTEGER NOT NULL CHECK(propuesta_inversa IN (0,1)),
 estado_documental TEXT NOT NULL, estado_revision TEXT NOT NULL DEFAULT 'PENDIENTE',
 justificacion TEXT NOT NULL DEFAULT '', evidencia TEXT NOT NULL DEFAULT '',
 actualizado_por TEXT NOT NULL, actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(version_id,resultado_id,servicio_id));
CREATE INDEX IF NOT EXISTS idx_pmo_matrix_links_service ON pmo_matrix_links(version_id,servicio_id);
CREATE TABLE IF NOT EXISTS pmo_matrix_audit (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 version_id TEXT NOT NULL REFERENCES pmo_matrix_versions(id),
 resultado_id INTEGER, servicio_id INTEGER,
 antes INTEGER, despues INTEGER, accion TEXT NOT NULL,
 actor TEXT NOT NULL, motivo TEXT NOT NULL, fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
"""

def initialize(path:Path|None=None):
    with transaction(path) as con:
        con.executescript(SCHEMA)
        for ident,source_key,source_label in [
            (DOC_ID,'intensidad_base','PMI X2 documental, vínculos 0–1 (fuente aportada)'),
            (EXPERIMENT_ID,'intensidad_escenario_experimental','Simulación de concordancia documental CENS, 0–4 (no PMOGA)')]:
            if con.execute('SELECT 1 FROM pmo_matrix_versions WHERE id=?',(ident,)).fetchone():continue
            con.execute('INSERT INTO pmo_matrix_versions(id,fuente,estado,descripcion,creado_por) VALUES (?,?,?,?,?)',
                        (ident,source_label,'REFERENCIA','Fuente de partida suministrada por el usuario; no consta aprobación corporativa.','Carga inicial'))
            for p,r in PROVENANCE.items():
                con.execute('''INSERT INTO pmo_matrix_links(version_id,resultado_id,servicio_id,intensidad,
                    x2_documentado,presente_html,propuesta_directa,propuesta_inversa,estado_documental,
                    estado_revision,actualizado_por) VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                    (ident,p[0],p[1],int(r[source_key]),int(r['recomendado_pmi_x2']),
                     int(r['presente_html_previo']),int(r['propuesto_tabla_directa']),
                     int(r['propuesto_lista_inversa']),r['estado_documental'],
                     'DOCUMENTADO' if r['recomendado_pmi_x2'] else 'PENDIENTE' if r['requiere_revision'] else 'NO_DOCUMENTADO', 'Carga inicial'))
        # Tercera matriz de referencia: reconstrucción matemática a partir de 30 FOCO.
        # No modifica las versiones anteriores ni sus 780 celdas.
        if not con.execute('SELECT 1 FROM pmo_matrix_versions WHERE id=?',(V5_ID,)).fetchone():
            con.execute('INSERT INTO pmo_matrix_versions(id,fuente,estado,descripcion,creado_por) VALUES (?,?,?,?,?)',
                (V5_ID,'Reconstrucción matemática V5 · 30 FOCO + 8 históricos (no certificada)',
                 'REFERENCIA','290 relaciones positivas, intensidades 0–4. Reproduce 38 escenarios observados; no es una matriz publicada ni certificada por PMI/PMOGA. SHA256: '+V5_HASH,
                 'Insumos aportados para evaluación técnica'))
            for oid,row in enumerate(V5_SOURCE['matrix'],start=1):
                for sid,value in enumerate(row,start=1):
                    r=PROVENANCE[oid,sid]
                    con.execute("""INSERT INTO pmo_matrix_links(version_id,resultado_id,servicio_id,intensidad,
                        x2_documentado,presente_html,propuesta_directa,propuesta_inversa,estado_documental,
                        estado_revision,actualizado_por) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                        (V5_ID,oid,sid,value,int(r['recomendado_pmi_x2']),int(r['presente_html_previo']),
                         int(r['propuesto_tabla_directa']),int(r['propuesto_lista_inversa']),r['estado_documental'],
                         'DOCUMENTADO' if r['recomendado_pmi_x2'] else 'PENDIENTE' if r['requiere_revision'] else 'NO_DOCUMENTADO',
                         'Referencia de reconstrucción V5'))
        con.execute('INSERT OR IGNORE INTO schema_migrations(version) VALUES (5)')
        con.execute('INSERT OR IGNORE INTO schema_migrations(version) VALUES (7)')
        # No se vuelve a escribir una versión preexistente ni se borra información.
        cols=[r['name'] for r in con.execute('PRAGMA table_info(p2_corridas)')]
        if 'matrix_version_id' not in cols:
            con.execute('ALTER TABLE p2_corridas ADD COLUMN matrix_version_id TEXT REFERENCES pmo_matrix_versions(id)')

def versions(path:Path|None=None):
    with connect(path) as con:
        return [dict(r) for r in con.execute('SELECT * FROM pmo_matrix_versions ORDER BY creada_en,id')]

def version(ident:str,path:Path|None=None):
    with connect(path) as con:
        row=con.execute('SELECT * FROM pmo_matrix_versions WHERE id=?',(ident,)).fetchone()
        if not row:raise ValidationError('La versión de matriz no existe.')
        return dict(row)

def links(ident:str,path:Path|None=None):
    version(ident,path)
    with connect(path) as con:
        return [dict(r) for r in con.execute('SELECT * FROM pmo_matrix_links WHERE version_id=? ORDER BY resultado_id,servicio_id',(ident,))]

def matrix(ident:str,path:Path|None=None):
    records=links(ident,path)
    if len(records)!=780:raise ValidationError('La versión no contiene los 780 cruces. No puede calcularse.')
    return {o:{s:int(next(r['intensidad'] for r in records if r['resultado_id']==o and r['servicio_id']==s)) for s in range(1,27)} for o in range(1,31)}

def clone(parent:str,ident:str,actor:str,description:str,path:Path|None=None):
    ident=ident.strip();actor=actor.strip();description=description.strip()
    if not ident or not actor or not description:raise ValidationError('Código, descripción y responsable son obligatorios.')
    if len(ident)>80 or len(description)>500:raise ValidationError('Código o descripción demasiado largos.')
    if ident in (DOC_ID,EXPERIMENT_ID,V5_ID):raise ValidationError('Código reservado para fuentes de referencia.')
    with transaction(path) as con:
        source=con.execute('SELECT * FROM pmo_matrix_versions WHERE id=?',(parent,)).fetchone()
        if not source:raise ValidationError('No existe la versión de origen.')
        if con.execute('SELECT 1 FROM pmo_matrix_versions WHERE id=?',(ident,)).fetchone():raise ValidationError('Ya existe una matriz con este código.')
        con.execute('INSERT INTO pmo_matrix_versions(id,fuente,estado,descripcion,origen_version,creado_por) VALUES (?,?,?,?,?,?)',
                    (ident,'Adaptación interna CENS','BORRADOR',description,parent,actor))
        con.execute('''INSERT INTO pmo_matrix_links(version_id,resultado_id,servicio_id,intensidad,x2_documentado,
          presente_html,propuesta_directa,propuesta_inversa,estado_documental,estado_revision,justificacion,
          evidencia,actualizado_por) SELECT ?,resultado_id,servicio_id,intensidad,x2_documentado,
          presente_html,propuesta_directa,propuesta_inversa,estado_documental,estado_revision,justificacion,
          evidencia,? FROM pmo_matrix_links WHERE version_id=?''',(ident,actor,parent))
        n=con.execute('SELECT COUNT(*) FROM pmo_matrix_links WHERE version_id=?',(ident,)).fetchone()[0]
        if n!=780:raise ValidationError('La versión de origen no es completa.')
        _log(con,ident,None,None,None,None,'CREAR_VERSION',actor,'Clonada de '+parent)
    return ident

def _log(con,vid,oid,sid,before,after,action,actor,reason):
    con.execute('INSERT INTO pmo_matrix_audit(version_id,resultado_id,servicio_id,antes,despues,accion,actor,motivo) VALUES (?,?,?,?,?,?,?,?)',
                (vid,oid,sid,before,after,action,actor,reason))

def edit(vid:str,oid:int,sid:int,strength:int,actor:str,reason:str,evidence:str='',review:str='PENDIENTE',path:Path|None=None):
    if type(oid)!=int or oid not in OUTCOMES or type(sid)!=int or sid not in SERVICES:
        raise ValidationError('Identificadores válidos: resultados 1–30 y servicios 1–26.')
    if type(strength)!=int or strength not in range(5):raise ValidationError('La intensidad debe ser un entero entre 0 y 4.')
    if review not in ('PENDIENTE','VALIDADO','RECHAZADO','DOCUMENTADO','NO_DOCUMENTADO'):
        raise ValidationError('Estado de revisión no permitido.')
    actor,reason=actor.strip(),reason.strip()
    if not actor or not reason:raise ValidationError('Responsable y justificación obligatorios.')
    with transaction(path) as con:
        v=con.execute('SELECT * FROM pmo_matrix_versions WHERE id=?',(vid,)).fetchone()
        if not v or v['estado']!='BORRADOR':raise ValidationError('Solo pueden editarse versiones en BORRADOR. Cree una nueva versión.')
        old=con.execute('SELECT intensidad FROM pmo_matrix_links WHERE version_id=? AND resultado_id=? AND servicio_id=?',(vid,oid,sid)).fetchone()
        if not old:raise ValidationError('La pareja no existe.')
        con.execute('''UPDATE pmo_matrix_links SET intensidad=?,estado_revision=?,justificacion=?,evidencia=?,
                     actualizado_por=?,actualizado_en=CURRENT_TIMESTAMP WHERE version_id=? AND resultado_id=? AND servicio_id=?''',
                    (strength,review,reason,evidence.strip(),actor,vid,oid,sid))
        con.execute('UPDATE pmo_matrix_versions SET actualizada_en=CURRENT_TIMESTAMP WHERE id=?',(vid,))
        _log(con,vid,oid,sid,int(old[0]),strength,'EDITAR_CELDA',actor,reason)

def change_status(vid:str,status:str,actor:str,reason:str,path:Path|None=None):
    if status not in ('BORRADOR','EN_REVISION','APROBADA','ARCHIVADA'):raise ValidationError('Estado de versión inválido.')
    if not actor.strip() or not reason.strip():raise ValidationError('Responsable y justificación obligatorios.')
    with transaction(path) as con:
        v=con.execute('SELECT * FROM pmo_matrix_versions WHERE id=?',(vid,)).fetchone()
        if not v or v['estado']=='REFERENCIA':raise ValidationError('Las matrices de referencia no cambian de estado.')
        if v['estado'] in ('APROBADA','ARCHIVADA'):
            if status!='ARCHIVADA' or v['estado']!='APROBADA':raise ValidationError('Una versión publicada permanece inmutable.')
        elif (v['estado'],status) not in {('BORRADOR','EN_REVISION'),('EN_REVISION','BORRADOR'),('EN_REVISION','APROBADA'),('BORRADOR','ARCHIVADA')}:
            raise ValidationError('Transición de estado no permitida.')
        if status=='APROBADA':
            # Documento de revisión y autor responsable (declarativo, sin validación de identidad)
            n=con.execute('SELECT COUNT(*) FROM pmo_matrix_links WHERE version_id=?',(vid,)).fetchone()[0]
            if n!=780:raise ValidationError('Se requieren 780 celdas completas.')
        con.execute('''UPDATE pmo_matrix_versions SET estado=?,actualizada_en=CURRENT_TIMESTAMP,
           aprobador=CASE WHEN ?='APROBADA' THEN ? ELSE aprobador END,
           aprobada_en=CASE WHEN ?='APROBADA' THEN CURRENT_TIMESTAMP ELSE aprobada_en END,
           motivo_aprobacion=CASE WHEN ?='APROBADA' THEN ? ELSE motivo_aprobacion END WHERE id=?''',
                    (status,status,actor,status,status,reason,vid))
        _log(con,vid,None,None,None,None,'CAMBIO_ESTADO:'+status,actor,reason)

def history(vid:str,path:Path|None=None):
    with connect(path) as con:
        return [dict(r) for r in con.execute('SELECT * FROM pmo_matrix_audit WHERE version_id=? ORDER BY id DESC',(vid,))]

def comparison(a:str,b:str,path:Path|None=None):
    ma,mb=matrix(a,path),matrix(b,path)
    return [{'resultado_id':o,'servicio_id':s,'antes':ma[o][s],'despues':mb[o][s],'delta':mb[o][s]-ma[o][s]}
            for o in range(1,31) for s in range(1,27) if ma[o][s]!=mb[o][s]]

def replace_from_import(vid:str,uploaded:dict,actor:str,reason:str,zero_missing:bool=False,path:Path|None=None):
    """Carga atómica. Ausencias requieren política explícita de llevar a cero."""
    from .step2 import validate_matrix
    data=validate_matrix(uploaded)
    pairs={(int(o),int(s)) for o,d in data.items() for s in d}
    expected={(o,s) for o in range(1,31) for s in range(1,27)}
    if pairs!=expected and not zero_missing:raise ValidationError('Archivo disperso: para asignar cero a las ausencias confirme esa política explícitamente.')
    full={(o,s):int(data.get(o,{}).get(s,0)) for o,s in expected}
    if not any(full.values()):raise ValidationError('Matriz completamente en cero; no se permite.')
    if not actor.strip() or not reason.strip():raise ValidationError('Responsable y motivo de importación son obligatorios.')
    with transaction(path) as con:
        v=con.execute('SELECT estado FROM pmo_matrix_versions WHERE id=?',(vid,)).fetchone()
        if not v or v[0]!='BORRADOR':raise ValidationError('La matriz debe estar en borrador para importar.')
        old={(r[0],r[1]):r[2] for r in con.execute('SELECT resultado_id,servicio_id,intensidad FROM pmo_matrix_links WHERE version_id=?',(vid,))}
        if len(old)!=780:raise ValidationError('La versión destino no es completa.')
        for (o,s),value in sorted(full.items()):
            if old[(o,s)]==value:continue
            con.execute('UPDATE pmo_matrix_links SET intensidad=?,estado_revision=?,justificacion=?,actualizado_por=?,actualizado_en=CURRENT_TIMESTAMP WHERE version_id=? AND resultado_id=? AND servicio_id=?',
                        (value,'PENDIENTE',reason,actor,vid,o,s))
            _log(con,vid,o,s,old[(o,s)],value,'IMPORTAR',actor,reason)
        con.execute('UPDATE pmo_matrix_versions SET actualizada_en=CURRENT_TIMESTAMP WHERE id=?',(vid,))
    return sum(old[x]!=full[x] for x in expected)

def export_csv(vid:str,path:Path|None=None)->bytes:
    result=io.StringIO();w=csv.writer(result);w.writerow(['Outcome ID','Service ID','Strength','X2 documentado','Estado revisión'])
    for l in links(vid,path):w.writerow([l['resultado_id'],l['servicio_id'],l['intensidad'],l['x2_documentado'],l['estado_revision']])
    return result.getvalue().encode('utf-8-sig')

def read_uploaded_matrix(content:bytes,name:str,wide_sheet:str='MATRIZ_PMI_0_1'):
    """Lee CSV/XLSX largo o una hoja 30x26 (caso Excel de revisión del usuario)."""
    from .step2_excel import import_matrix
    if not name.lower().endswith('.xlsx'):
        return import_matrix(content,name)
    from openpyxl import load_workbook
    try:wb=load_workbook(io.BytesIO(content),read_only=True,data_only=True)
    except Exception as ex:raise ValidationError('No se pudo leer el Excel de matriz.') from ex
    try:
        if wide_sheet in wb.sheetnames:
            ws=wb[wide_sheet];rows=ws.iter_rows(values_only=True);headers=next(rows,None)
            if not headers:raise ValidationError('La matriz no tiene encabezados.')
            ids=[]
            for cell in headers[1:]:
                try:
                    s=int(cell)
                    if s not in SERVICES or s in ids:raise ValueError()
                except (TypeError,ValueError) as ex:raise ValidationError('Los encabezados deben incluir los servicios 1–26 sin repeticiones.') from ex
                ids.append(s)
            if len(ids)!=26:raise ValidationError('Se esperan 26 columnas de servicios en el mapa.')
            result={}
            for ix,row in enumerate(rows,2):
                if not row or all(v is None for v in row):continue
                try:
                    outcome=int(row[0]);assert outcome in OUTCOMES and outcome not in result
                    result[outcome]={}
                    for sid,val in zip(ids,row[1:27]):
                        num=float(val)
                        if not math.isfinite(num) or not num.is_integer() or int(num) not in range(5):raise ValueError()
                        result[outcome][sid]=int(num)
                except (AssertionError,TypeError,ValueError) as ex:raise ValidationError(f'Fila {ix} del mapa: resultado o intensidad inválida.') from ex
            if len(result)!=30:raise ValidationError('Se esperan 30 filas de resultados en el mapa.')
            return result
    finally:wb.close()
    return import_matrix(content,name)
