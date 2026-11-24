"""Paso 8 V0.19: evaluaciones sustentadas y evidencias, sobre la misma SQLite.

Las tablas son ADITIVAS y no intervienen en la función de cálculo PMO-GA.
Los 130 criterios son resúmenes de trabajo en español, no transcripciones del PMI.
"""
from __future__ import annotations
import base64
import json
import uuid
from datetime import date, datetime, timezone
from contextlib import closing
from .storage import connect, transaction
from . import step8 as core

TIPOS = ('Documento', 'Indicador', 'Acta', 'Informe', 'Enlace', 'Otro')
ESTADOS = ('Borrador', 'Pendiente de validación', 'Validado')
MAX_BYTES = 600 * 1024
BASE_TABLES = ('p8_cycles', 'p8_ratings', 'p8_actions', 'p8_service_links', 'p8_findings', 'p8_imports')
DOC_TABLES = ('p8_revisiones', 'p8_evidencias', 'p8_revision_historial')

SCHEMA = '''
CREATE TABLE IF NOT EXISTS p8_revisiones (
 ciclo_id TEXT NOT NULL,
 servicio_ref INTEGER NOT NULL CHECK(servicio_ref BETWEEN 1 AND 26),
 justificacion TEXT NOT NULL DEFAULT '', evaluador TEXT NOT NULL DEFAULT '',
 fecha TEXT, estado TEXT NOT NULL DEFAULT 'Borrador' CHECK(estado IN ('Borrador','Pendiente de validación','Validado')),
 validado_actual INTEGER, validado_deseado INTEGER, validado_en TEXT,
 meta_justificacion TEXT NOT NULL DEFAULT '', capacidades TEXT NOT NULL DEFAULT '',
 recursos TEXT NOT NULL DEFAULT '', horizonte TEXT, responsable_meta TEXT NOT NULL DEFAULT '',
 acciones TEXT NOT NULL DEFAULT '', observaciones TEXT NOT NULL DEFAULT '',
 actualizado_en TEXT NOT NULL,
 PRIMARY KEY(ciclo_id, servicio_ref),
 FOREIGN KEY(ciclo_id, servicio_ref) REFERENCES p8_ratings(ciclo_id, servicio_ref) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS p8_evidencias (
 id TEXT PRIMARY KEY, ciclo_id TEXT NOT NULL, servicio_ref INTEGER NOT NULL,
 nivel INTEGER CHECK(nivel IS NULL OR nivel BETWEEN 1 AND 5),
 tipo TEXT NOT NULL CHECK(tipo IN ('Documento','Indicador','Acta','Informe','Enlace','Otro')),
 descripcion TEXT NOT NULL, referencia TEXT NOT NULL DEFAULT '',
 archivo_nombre TEXT NOT NULL DEFAULT '', archivo_tipo TEXT NOT NULL DEFAULT '',
 archivo BLOB, responsable TEXT NOT NULL DEFAULT '', fecha TEXT NOT NULL,
 creado_en TEXT NOT NULL,
 FOREIGN KEY(ciclo_id, servicio_ref) REFERENCES p8_ratings(ciclo_id, servicio_ref) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_p8_evidencia_servicio ON p8_evidencias(ciclo_id, servicio_ref);
CREATE TABLE IF NOT EXISTS p8_revision_historial (
 id TEXT PRIMARY KEY, ciclo_id TEXT NOT NULL, servicio_ref INTEGER NOT NULL,
 accion TEXT NOT NULL, actor TEXT NOT NULL, fecha TEXT NOT NULL,
 antes_json TEXT NOT NULL, despues_json TEXT NOT NULL,
 FOREIGN KEY(ciclo_id, servicio_ref) REFERENCES p8_ratings(ciclo_id, servicio_ref) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_p8_hist_servicio ON p8_revision_historial(ciclo_id, servicio_ref, fecha);
CREATE TRIGGER IF NOT EXISTS p8_invalidar_revision_por_cambio
AFTER UPDATE OF actual, deseado, estado ON p8_ratings
WHEN (OLD.actual IS NOT NEW.actual OR OLD.deseado IS NOT NEW.deseado OR OLD.estado IS NOT NEW.estado)
BEGIN
 UPDATE p8_revisiones SET estado='Pendiente de validación',
 validado_actual=NULL,validado_deseado=NULL,validado_en=NULL,
 actualizado_en=CURRENT_TIMESTAMP
 WHERE ciclo_id=NEW.ciclo_id AND servicio_ref=NEW.servicio_ref AND estado='Validado';
END;
'''

def _now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def initialize(path=None):
    with closing(connect(path)) as c:
        c.executescript(SCHEMA)
        c.execute('INSERT OR IGNORE INTO schema_migrations(version) VALUES(13)')
        c.commit()

def _record(c,cycle_id,ref):
    r=c.execute('SELECT * FROM p8_ratings WHERE ciclo_id=? AND servicio_ref=?',(cycle_id,int(ref))).fetchone()
    if r is None:raise core.ValidationError('No existe esta calificación en el ciclo')
    return dict(r)

def _cycle_editable(c,cycle_id):
    v=c.execute('SELECT estado FROM p8_cycles WHERE id=?',(cycle_id,)).fetchone()
    if v is None or v['estado']!='Borrador':raise core.ValidationError('El ciclo está cerrado o no existe; no puede modificarse')

def _check_date(s):
    try:return date.fromisoformat(str(s)).isoformat()
    except (ValueError,TypeError):raise core.ValidationError('La fecha de evaluación debe ser válida (AAAA-MM-DD)')

def _optional_date(s):
    return _check_date(s) if s else None

def review(cycle_id,ref,path=None):
    initialize(path)
    with closing(connect(path)) as c:
        item=c.execute('SELECT * FROM p8_revisiones WHERE ciclo_id=? AND servicio_ref=?',(cycle_id,int(ref))).fetchone()
        score=_record(c,cycle_id,ref)
        r=dict(item) if item else {'ciclo_id':cycle_id,'servicio_ref':int(ref),'estado':'Borrador',
            'justificacion':score['observacion'] or '', 'evaluador':score['revisado_por'] or '',
            'fecha':(score['revisado_en'] or '')[:10] or date.today().isoformat(),
            'meta_justificacion':'','capacidades':'','recursos':'','horizonte':None,
            'responsable_meta':'','acciones':'','observaciones':'',
            'validado_actual':None,'validado_deseado':None,'validado_en':None}
        r['vigente']=bool(r['estado']=='Validado' and score['estado']=='Evaluado'
            and score['actual']==r.get('validado_actual') and score['deseado']==r.get('validado_deseado'))
        return r

def evidences(cycle_id,ref,path=None,include_file=False):
    initialize(path)
    fields='*' if include_file else 'id,ciclo_id,servicio_ref,nivel,tipo,descripcion,referencia,archivo_nombre,archivo_tipo,responsable,fecha,creado_en'
    with closing(connect(path)) as c:
        return [dict(x) for x in c.execute(f'''SELECT {fields} FROM p8_evidencias WHERE ciclo_id=? AND servicio_ref=? ORDER BY fecha,id''',(cycle_id,int(ref)))]

def evidence_file(evidence_id,path=None):
    initialize(path)
    with closing(connect(path)) as c:
        x=c.execute('SELECT archivo,archivo_nombre,archivo_tipo FROM p8_evidencias WHERE id=?',(evidence_id,)).fetchone()
        if x is None:raise core.ValidationError('No existe la evidencia solicitada')
        return dict(x)

def add_evidence(cycle_id,ref,tipo,descripcion,nivel=None,referencia='',filename='',filetype='',blob=None,actor='',fecha=None,path=None):
    initialize(path)
    if tipo not in TIPOS:raise core.ValidationError('Tipo de evidencia inválido')
    if not str(descripcion).strip():raise core.ValidationError('Describe la evidencia y lo que demuestra')
    if nivel is not None and int(nivel) not in range(1,6):raise core.ValidationError('Nivel de evidencia fuera de escala')
    if blob is not None and (not isinstance(blob,bytes) or len(blob)>MAX_BYTES):
        raise core.ValidationError('El archivo adjunto debe ser de máximo 600 KB')
    if filename and (len(filename)>180 or '/' in filename or '\\' in filename):
        raise core.ValidationError('Nombre de archivo inválido')
    stamp=_check_date(fecha or date.today())
    key=str(uuid.uuid4())
    with transaction(path) as c:
        _cycle_editable(c,cycle_id);_record(c,cycle_id,ref)
        c.execute('''INSERT INTO p8_evidencias(id,ciclo_id,servicio_ref,nivel,tipo,descripcion,referencia,
           archivo_nombre,archivo_tipo,archivo,responsable,fecha,creado_en) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
           (key,cycle_id,int(ref),int(nivel) if nivel is not None else None,tipo,str(descripcion).strip(),
            str(referencia).strip(),filename,str(filetype)[:100],blob,str(actor).strip(),stamp,_now()))
    return key

def remove_evidence(cycle_id,ref,evidence_id,path=None):
    initialize(path)
    with transaction(path) as c:
        _cycle_editable(c,cycle_id)
        found=c.execute('SELECT 1 FROM p8_evidencias WHERE id=? AND ciclo_id=? AND servicio_ref=?',(evidence_id,cycle_id,int(ref))).fetchone()
        if not found:raise core.ValidationError('La evidencia no pertenece a este servicio y ciclo')
        c.execute('DELETE FROM p8_evidencias WHERE id=?',(evidence_id,))
        c.execute('''UPDATE p8_revisiones SET estado='Pendiente de validación',validado_actual=NULL,
             validado_deseado=NULL,validado_en=NULL,actualizado_en=?
             WHERE ciclo_id=? AND servicio_ref=? AND estado='Validado' ''',(_now(),cycle_id,int(ref)))
    return True

def save_review(cycle_id,ref,status,current=None,desired=None,justificacion='',evaluador='',fecha=None,
                estado='Borrador',meta_justificacion='',capacidades='',recursos='',horizonte=None,
                responsable_meta='',acciones='',observaciones='',path=None):
    """Actualización atómica de puntajes y justificación. No recalcula madurez."""
    initialize(path)
    if status not in core.STATUS:raise core.ValidationError('Estado de servicio no válido')
    if estado not in ESTADOS:raise core.ValidationError('Estado de validación desconocido')
    actual=core._score(current) if status=='Evaluado' else None
    deseado=core._score(desired) if status=='Evaluado' else None
    if status=='Evaluado' and (actual is None or deseado is None):
        raise core.ValidationError('Para evaluar el servicio debes registrar los niveles actual y deseado')
    if status!='Evaluado' and (current is not None or desired is not None):
        raise core.ValidationError('Los servicios pendientes o no ofrecidos deben quedar sin puntuación')
    if status=='Evaluado' and not str(evaluador).strip():
        raise core.ValidationError('Indica quién es responsable de la evaluación')
    stamp=_check_date(fecha or date.today());h=_optional_date(horizonte)
    with transaction(path) as c:
        _cycle_editable(c,cycle_id)
        before=_record(c,cycle_id,ref)
        old=c.execute('SELECT * FROM p8_revisiones WHERE ciclo_id=? AND servicio_ref=?',(cycle_id,int(ref))).fetchone()
        if estado=='Validado':
            count=c.execute('SELECT count(*) FROM p8_evidencias WHERE ciclo_id=? AND servicio_ref=?',(cycle_id,int(ref))).fetchone()[0]
            if status!='Evaluado' or not str(justificacion).strip() or not str(evaluador).strip() or count<1:
                raise core.ValidationError('Para validar se requieren niveles actual y meta, justificación, evaluador y al menos una evidencia')
        if status!='Evaluado' and estado=='Validado':raise core.ValidationError('No se puede validar un servicio sin evaluación')
        when=_now()
        c.execute('''UPDATE p8_ratings SET estado=?,actual=?,deseado=?,observacion=?,
             revisado_por=?,revisado_en=? WHERE ciclo_id=? AND servicio_ref=?''',
             (status,actual,deseado,str(justificacion),str(evaluador).strip(),when,cycle_id,int(ref)))
        vals=(cycle_id,int(ref),str(justificacion),str(evaluador).strip(),stamp,estado,
              actual if estado=='Validado' else None,deseado if estado=='Validado' else None,
              when if estado=='Validado' else None,str(meta_justificacion),str(capacidades),str(recursos),
              h,str(responsable_meta),str(acciones),str(observaciones),when)
        c.execute('''INSERT INTO p8_revisiones(ciclo_id,servicio_ref,justificacion,evaluador,fecha,estado,
          validado_actual,validado_deseado,validado_en,meta_justificacion,capacidades,recursos,
          horizonte,responsable_meta,acciones,observaciones,actualizado_en)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(ciclo_id,servicio_ref) DO UPDATE SET
          justificacion=excluded.justificacion,evaluador=excluded.evaluador,fecha=excluded.fecha,
          estado=excluded.estado,validado_actual=excluded.validado_actual,
          validado_deseado=excluded.validado_deseado,validado_en=excluded.validado_en,
          meta_justificacion=excluded.meta_justificacion,capacidades=excluded.capacidades,
          recursos=excluded.recursos,horizonte=excluded.horizonte,
          responsable_meta=excluded.responsable_meta,acciones=excluded.acciones,
          observaciones=excluded.observaciones,actualizado_en=excluded.actualizado_en''',vals)
        after=_record(c,cycle_id,ref)
        c.execute('''INSERT INTO p8_revision_historial(id,ciclo_id,servicio_ref,accion,actor,fecha,
          antes_json,despues_json) VALUES(?,?,?,?,?,?,?,?)''',
          (str(uuid.uuid4()),cycle_id,int(ref),'Guardar evaluación documentada',str(evaluador),when,
           json.dumps({'calificacion':before,'revision':dict(old) if old else None},ensure_ascii=False,default=str),
           json.dumps({'calificacion':after,'revision':{'estado':estado,'justificacion':justificacion,'horizonte':h}},ensure_ascii=False,default=str)))
    return True

def history(cycle_id,ref,path=None):
    initialize(path)
    with closing(connect(path)) as c:
        return [dict(x) for x in c.execute('SELECT * FROM p8_revision_historial WHERE ciclo_id=? AND servicio_ref=? ORDER BY fecha,id',(cycle_id,int(ref)))]

def _dump_table(c,t):
    return [dict(r) for r in c.execute('SELECT * FROM '+t)]

def backup_full(path=None):
    initialize(path)
    with closing(connect(path)) as c:
        base={t:_dump_table(c,t) for t in BASE_TABLES}
        docs={t:_dump_table(c,t) for t in DOC_TABLES}
    for x in docs['p8_evidencias']:
        x['archivo']=base64.b64encode(x['archivo']).decode('ascii') if x['archivo'] is not None else None
    return {'schema':'PMO-FLYWHEEL-CENS-paso8-documentado-backup-v2',
            'generado_en':_now(),'tablas_base':base,'tablas_documentadas':docs}

def restore_full(obj,confirmed=False,path=None):
    if not confirmed:raise core.ValidationError('Debes confirmar la restauración del Paso 8')
    if not isinstance(obj,dict):raise core.ValidationError('Archivo de respaldo inválido')
    if obj.get('schema')=='PMO-FLYWHEEL-CENS-paso8-backup-v1':
        base=obj.get('tables');docs={t:[] for t in DOC_TABLES}
    elif obj.get('schema')=='PMO-FLYWHEEL-CENS-paso8-documentado-backup-v2':
        base=obj.get('tablas_base');docs=obj.get('tablas_documentadas')
    else:raise core.ValidationError('No se reconoce la versión del respaldo del Paso 8')
    if not isinstance(base,dict) or set(base)!=set(BASE_TABLES) or not isinstance(docs,dict) or set(docs)!=set(DOC_TABLES):
        raise core.ValidationError('Respaldo incompleto o estructura de tablas inesperada')
    initialize(path)
    # Verificar completamente la estructura y los BLOB antes de eliminar un dato.
    with closing(connect(path)) as c:
        for table,source in list(base.items())+list(docs.items()):
            if not isinstance(source,list):raise core.ValidationError('Tabla del respaldo inválida: '+table)
            col={r[1] for r in c.execute('PRAGMA table_info('+table+')')}
            for row in source:
                if not isinstance(row,dict) or not row or not set(row).issubset(col):
                    raise core.ValidationError('Columnas inesperadas en '+table)
        for item in docs['p8_evidencias']:
            if item.get('archivo') is not None:
                try:
                    decoded=base64.b64decode(item['archivo'],validate=True)
                    if len(decoded)>MAX_BYTES:raise ValueError()
                except (ValueError,TypeError):raise core.ValidationError('Adjunto de evidencia inválido o demasiado grande')
                item['archivo']=decoded
    with transaction(path) as c:
        for table in reversed(DOC_TABLES):c.execute('DELETE FROM '+table)
        for table in reversed(BASE_TABLES):c.execute('DELETE FROM '+table)
        for table in (*BASE_TABLES,*DOC_TABLES):
            source=base[table] if table in base else docs[table]
            for item in source:
                keys=list(item)
                c.execute('INSERT INTO '+table+' ('+','.join(keys)+') VALUES ('+','.join('?' for _ in keys)+')',tuple(item[x] for x in keys))
    return True

def export_documented_json(cycle_id,path=None):
    initialize(path)
    report=core.export_json(cycle_id,path)
    report['anexos_documentales']={}
    for row in core.ratings(cycle_id,path):
        ref=row['servicio_ref']
        rev=review(cycle_id,ref,path)
        evs=evidences(cycle_id,ref,path)
        if rev['estado']=='Borrador' and not evs and not rev['justificacion']:continue
        report['anexos_documentales'][str(ref)]={'revision':rev,'evidencias':evs,
          'historial':history(cycle_id,ref,path)}
    report['nota_documental']='Evidencias descritas y referenciadas, sin adjuntos binarios en este JSON. Usa el respaldo integral para conservar archivos.'
    return report
