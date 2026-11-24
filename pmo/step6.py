"""Paso 6 · Operación de servicios. SQLite aditivo, sin dependencias del Paso 5.

Los ANS se calculan según la unidad congelada por solicitud: calendario o hábil.
Las calificaciones de clientes 1–10 no se mezclan con la autoevaluación PMI 1–5.
La importación del Paso 4 nunca altera su catálogo ni su matriz previa.
"""
from __future__ import annotations
import csv
import io
import json
import uuid
import re
import secrets
import hashlib
import hmac
import math
import os
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from .storage import connect, transaction
from . import step6_calendar as cal
from .staff_picker import member_id_for_name

MODULES=('Tablero Kanban','Gestión de solicitudes','Estado e indicadores','Evaluación metodológica PMI')
STAGES=('Solicitud de servicio','Servicio asignado','En proceso','Evaluación del servicio','Finalizado')
PRIORITIES=('Baja','Normal','Alta','Urgente')
ORIGINS=('Solicitud del cliente','Por evento','Por regla','Proactiva de la PMO')
PROJECT_TYPES=('No aplica','CAPEX / Infraestructura','TI / Transformación','Gestión / Proyectos menores','Otro')
COMPLEXITIES=('Sin clasificar','Alta','Media','Baja')
CATEGORIES=((35,67,'Crítico'),(68,101,'Pobre'),(102,130,'Promedio'),(131,153,'Bien'),(154,175,'Excelente'))
QUESTIONS=json.loads((Path(__file__).parent/'data'/'step6_questions.json').read_text(encoding='utf-8'))
SCHEMA='''
CREATE TABLE IF NOT EXISTS p6_catalog(
 id TEXT PRIMARY KEY,codigo TEXT NOT NULL UNIQUE COLLATE NOCASE,nombre TEXT NOT NULL,
 descripcion TEXT NOT NULL DEFAULT '',responsable TEXT NOT NULL DEFAULT '',
 sla_respuesta_h REAL CHECK(sla_respuesta_h>0 OR sla_respuesta_h IS NULL),
 sla_resolucion_h REAL CHECK(sla_resolucion_h>0 OR sla_resolucion_h IS NULL),
 version TEXT NOT NULL DEFAULT '',origen TEXT NOT NULL DEFAULT 'Manual',
 p4_id TEXT UNIQUE, demo INTEGER NOT NULL DEFAULT 0 CHECK(demo IN(0,1)),
 habilitado INTEGER NOT NULL DEFAULT 1 CHECK(habilitado IN(0,1)),
 actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS p6_tickets(
 id TEXT PRIMARY KEY, folio TEXT NOT NULL UNIQUE,
 titulo TEXT NOT NULL, descripcion TEXT NOT NULL, cliente TEXT NOT NULL,
 cliente_id TEXT REFERENCES pmo_clientes(id), dependencia TEXT NOT NULL DEFAULT '',
 correo TEXT NOT NULL DEFAULT '', servicio_id TEXT NOT NULL REFERENCES p6_catalog(id),
 origen TEXT NOT NULL,canal TEXT NOT NULL DEFAULT 'Portal PMO',prioridad TEXT NOT NULL,
 resultado_esperado TEXT NOT NULL DEFAULT '',responsable TEXT NOT NULL DEFAULT '',
 estado TEXT NOT NULL CHECK(estado IN('Solicitud de servicio','Servicio asignado','En proceso','Evaluación del servicio','Finalizado')),
 creado_en TEXT NOT NULL, asignado_en TEXT, primera_respuesta_en TEXT, iniciado_en TEXT,
 terminado_en TEXT, cerrado_en TEXT, entregable TEXT NOT NULL DEFAULT '',
 aceptacion TEXT NOT NULL DEFAULT '', calificacion INTEGER CHECK(calificacion BETWEEN 1 AND 10),
 calificacion_comentario TEXT NOT NULL DEFAULT '',calificado_en TEXT,
 excepcion_evaluacion INTEGER NOT NULL DEFAULT 0 CHECK(excepcion_evaluacion IN(0,1)),
 motivo_excepcion TEXT NOT NULL DEFAULT '',
 ans_respuesta_h REAL CHECK(ans_respuesta_h>0 OR ans_respuesta_h IS NULL),
 ans_resolucion_h REAL CHECK(ans_resolucion_h>0 OR ans_resolucion_h IS NULL),
 version_servicio TEXT NOT NULL DEFAULT '', demo INTEGER NOT NULL DEFAULT 0 CHECK(demo IN(0,1)),
 actualizado_en TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_p6_tickets_estado ON p6_tickets(estado);
CREATE INDEX IF NOT EXISTS idx_p6_tickets_servicio ON p6_tickets(servicio_id);
CREATE TABLE IF NOT EXISTS p6_tareas(id TEXT PRIMARY KEY,ticket_id TEXT NOT NULL REFERENCES p6_tickets(id),
 descripcion TEXT NOT NULL,completada INTEGER NOT NULL DEFAULT 0 CHECK(completada IN(0,1)));
CREATE TABLE IF NOT EXISTS p6_comentarios(id TEXT PRIMARY KEY,ticket_id TEXT NOT NULL REFERENCES p6_tickets(id),
 autor TEXT NOT NULL,tipo TEXT NOT NULL,comentario TEXT NOT NULL,fecha TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS p6_evidencias(id TEXT PRIMARY KEY,ticket_id TEXT NOT NULL REFERENCES p6_tickets(id),
 titulo TEXT NOT NULL,referencia TEXT NOT NULL,autor TEXT NOT NULL,fecha TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS p6_adjuntos(id TEXT PRIMARY KEY,ticket_id TEXT NOT NULL REFERENCES p6_tickets(id),
 nombre TEXT NOT NULL,mime TEXT NOT NULL,contenido_b64 TEXT NOT NULL,tamano INTEGER NOT NULL CHECK(tamano BETWEEN 1 AND 300000),
 autor TEXT NOT NULL,fecha TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS p6_historial(id INTEGER PRIMARY KEY AUTOINCREMENT,
 ticket_id TEXT NOT NULL REFERENCES p6_tickets(id),actor TEXT NOT NULL,detalle TEXT NOT NULL,fecha TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS p6_evaluaciones(id TEXT PRIMARY KEY,version INTEGER NOT NULL UNIQUE,
 responsable TEXT NOT NULL,estado TEXT NOT NULL CHECK(estado IN('Borrador','Finalizada')),
 puntaje INTEGER,clasificacion TEXT,creado_en TEXT NOT NULL,finalizado_en TEXT);
CREATE TABLE IF NOT EXISTS p6_respuestas(evaluacion_id TEXT NOT NULL REFERENCES p6_evaluaciones(id),
 numero INTEGER NOT NULL CHECK(numero BETWEEN 1 AND 35),valor INTEGER NOT NULL CHECK(valor BETWEEN 1 AND 5),
 observacion TEXT NOT NULL DEFAULT '',evidencia TEXT NOT NULL DEFAULT '',fecha TEXT NOT NULL,
 PRIMARY KEY(evaluacion_id,numero));
'''

class ValidationError(ValueError):pass

def now():return datetime.now(timezone.utc).isoformat(timespec='seconds')
def uid():return str(uuid.uuid4())
def needed(value,name):
    value=str(value if value is not None else '').strip()
    if not value:raise ValidationError(f'Se requiere {name}.')
    return value

def _validate_pmo_member(name,member_id,path=None):
    """Preserva asignaciones anteriores; vincula por ID la selección nueva."""
    if not member_id:
        return member_id_for_name(name,path)
    from . import step4
    person=step4.member(member_id,path)
    if person is None or person['nombre'].strip()!=str(name or '').strip():
        raise ValidationError('El integrante PMO seleccionado ya no coincide con el Equipo PMO del Paso 04.')
    return member_id

def positive_hours(value):
    if value is None or str(value).strip()=='':return None
    if isinstance(value,bool):raise ValidationError('El ANS debe ser numérico en horas.')
    try:x=float(value)
    except (ValueError,TypeError):raise ValidationError('El ANS debe ser numérico en horas (no días).')
    import math
    if not math.isfinite(x) or x<=0:raise ValidationError('El ANS debe ser mayor que cero.')
    return x

def rows(sql,args=(),path=None):
    with closing(connect(path)) as c:return [dict(r) for r in c.execute(sql,args).fetchall()]
def row(sql,args=(),path=None):
    with closing(connect(path)) as c:
        r=c.execute(sql,args).fetchone()
        return dict(r) if r else None

def initialize(path=None):
    with closing(connect(path)) as c:
        c.executescript(SCHEMA)
        c.executescript("""CREATE TABLE IF NOT EXISTS p6_calendar_config(
         servicio_id TEXT PRIMARY KEY REFERENCES p6_catalog(id),
         configuracion_json TEXT NOT NULL, actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );""")
        extensions = {
          'p6_catalog': {'ans_tipo': "TEXT NOT NULL DEFAULT 'Calendario'",
                         'operativo_asignado': "TEXT NOT NULL DEFAULT ''",
                         'operativo_integrante_id': 'TEXT'},
          'p6_tickets': {'ans_tipo': "TEXT NOT NULL DEFAULT 'Calendario'",
                         'ans_calendario_json': "TEXT NOT NULL DEFAULT ''",
                         'ans_respuesta_limite_en': 'TEXT', 'ans_resolucion_limite_en': 'TEXT',
                         'asignacion_fuente': "TEXT NOT NULL DEFAULT ''",
                         'responsable_integrante_id': 'TEXT'}
        }
        for table,fields in extensions.items():
            existing={r['name'] for r in c.execute(f'PRAGMA table_info({table})')}
            for field,definition in fields.items():
                if field not in existing:c.execute(f'ALTER TABLE {table} ADD COLUMN {field} {definition}')
        c.executescript("""
        CREATE TABLE IF NOT EXISTS p6_wip_limits(
          operador TEXT NOT NULL, etapa TEXT NOT NULL, limite INTEGER NOT NULL CHECK(limite>0),
          modo TEXT NOT NULL CHECK(modo IN ('Advertir','Bloquear')),
          actualizado_en TEXT NOT NULL, PRIMARY KEY(operador,etapa));
        CREATE TABLE IF NOT EXISTS p6_wip_excepciones(
          id TEXT PRIMARY KEY,ticket_id TEXT NOT NULL REFERENCES p6_tickets(id),
          operador TEXT NOT NULL,etapa TEXT NOT NULL,limite INTEGER NOT NULL,
          justificacion TEXT NOT NULL,actor TEXT NOT NULL,fecha TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS p6_escalamiento_config(
          servicio_id TEXT PRIMARY KEY REFERENCES p6_catalog(id),
          correo TEXT NOT NULL DEFAULT '',responsable TEXT NOT NULL DEFAULT '',
          habilitado INTEGER NOT NULL DEFAULT 0, actualizado_en TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS p6_alertas_ans(
          id TEXT PRIMARY KEY,ticket_id TEXT NOT NULL REFERENCES p6_tickets(id),
          tipo TEXT NOT NULL CHECK(tipo IN ('respuesta','resolucion')),
          umbral INTEGER NOT NULL CHECK(umbral IN (80,100)),
          estado TEXT NOT NULL DEFAULT 'Pendiente' CHECK(estado IN ('Pendiente','Enviada','Vista')),
          responsable TEXT NOT NULL DEFAULT '',correo TEXT NOT NULL DEFAULT '',
          fecha TEXT NOT NULL,notificado_en TEXT,detalle TEXT NOT NULL DEFAULT '',
          UNIQUE(ticket_id,tipo,umbral));
        CREATE TABLE IF NOT EXISTS p6_conocimiento(
          id TEXT PRIMARY KEY,servicio_id TEXT NOT NULL REFERENCES p6_catalog(id),
          titulo TEXT NOT NULL,cuerpo TEXT NOT NULL,referencia TEXT NOT NULL DEFAULT '',
          version TEXT NOT NULL,estado TEXT NOT NULL CHECK(estado IN ('Borrador','Publicado')),
          responsable TEXT NOT NULL,actualizado_en TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS p6_invitaciones_conformidad(
          id TEXT PRIMARY KEY,ticket_id TEXT NOT NULL REFERENCES p6_tickets(id),
          secreto_hash TEXT NOT NULL,emitida_en TEXT NOT NULL,vence_en TEXT NOT NULL,
          emitida_por TEXT NOT NULL,estado TEXT NOT NULL CHECK(estado IN ('Activa','Respondida','Revocada')),
          referencia_envio TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS p6_respuestas_cliente(
          id TEXT PRIMARY KEY,ticket_id TEXT NOT NULL REFERENCES p6_tickets(id),
          invitacion_id TEXT NOT NULL UNIQUE REFERENCES p6_invitaciones_conformidad(id),
          decision TEXT NOT NULL CHECK(decision IN ('Conforme','Solicita ajustes')),
          csat INTEGER CHECK(csat BETWEEN 1 AND 5),nps INTEGER CHECK(nps BETWEEN 0 AND 10),
          observaciones TEXT NOT NULL DEFAULT '',fecha TEXT NOT NULL,
          vigente INTEGER NOT NULL DEFAULT 1 CHECK(vigente IN(0,1)));
        """)
        extra={'tipo_proyecto':"TEXT NOT NULL DEFAULT 'No aplica'",
               'complejidad':"TEXT NOT NULL DEFAULT 'Sin clasificar'",
               'protocolo_cierre':"TEXT NOT NULL DEFAULT 'Legado'",
               'excepcion_autorizador':"TEXT NOT NULL DEFAULT ''",
               'excepcion_evidencia':"TEXT NOT NULL DEFAULT ''"}
        old_columns={r['name'] for r in c.execute('PRAGMA table_info(p6_tickets)')}
        for field,definition in extra.items():
            if field not in old_columns:c.execute(f'ALTER TABLE p6_tickets ADD COLUMN {field} {definition}')
        if 'vigente' not in {r['name'] for r in c.execute('PRAGMA table_info(p6_respuestas_cliente)')}:
            c.execute('ALTER TABLE p6_respuestas_cliente ADD COLUMN vigente INTEGER NOT NULL DEFAULT 1')
        c.execute('INSERT OR IGNORE INTO schema_migrations(version) VALUES (10)')
        c.execute('INSERT OR IGNORE INTO schema_migrations(version) VALUES (9)')
        c.commit()

def catalog(path=None):return rows('SELECT * FROM p6_catalog ORDER BY codigo',path=path)
def service(key,path=None):return row('SELECT * FROM p6_catalog WHERE id=?',(key,),path)
def get_calendar(service_id,path=None):
    record=row('SELECT configuracion_json FROM p6_calendar_config WHERE servicio_id=?',(service_id,),path)
    return json.loads(record['configuracion_json']) if record else dict(cal.DEFAULT_CONFIG)

def set_calendar(service_id,config,path=None):
    c=cal.check_calendar(config,require_confirmed=False)
    if not service(service_id,path):raise ValidationError('Servicio inexistente.')
    with transaction(path) as con:
        con.execute('''INSERT INTO p6_calendar_config(servicio_id,configuracion_json,actualizado_en)
           VALUES(?,?,?) ON CONFLICT(servicio_id) DO UPDATE SET
           configuracion_json=excluded.configuracion_json,actualizado_en=excluded.actualizado_en''',
           (service_id,json.dumps(c,ensure_ascii=False,sort_keys=True),now()))
    return c

def operational_candidates(catalog_service_id,path=None):
    """Roles R de un RACI documentado/aprobado del Paso 04; solo sugerencias.

    El responsable operativo se confirma expresamente en Catálogo Paso 06.
    Nunca se deduce de un propietario institucional ni de RACI preliminares.
    """
    srv=service(catalog_service_id,path)
    if not srv or not srv.get('p4_id'):return []
    row_=row('SELECT detalles_json FROM p4_services WHERE id=?',(srv['p4_id'],),path)
    if not row_:return []
    try:details=json.loads(row_['detalles_json'] or '{}')
    except ValueError:return []
    if not str(details.get('evidencia_raci_aprobado') or '').strip():return []
    result=[]
    for item in details.get('raci_registro') or []:
        if not isinstance(item,dict):continue
        raw=str(item.get('Responsable (R)') or '').strip()
        if raw and raw not in result:result.append(raw)
    return result

def tickets(path=None):return rows('SELECT * FROM p6_tickets ORDER BY creado_en DESC,folio DESC',path=path)
def ticket(key,path=None):return row('SELECT * FROM p6_tickets WHERE id=?',(key,),path)
def tasks(key,path=None):return rows('SELECT * FROM p6_tareas WHERE ticket_id=? ORDER BY rowid',(key,),path)
def comments(key,path=None):return rows('SELECT * FROM p6_comentarios WHERE ticket_id=? ORDER BY fecha DESC',(key,),path)
def evidences(key,path=None):return rows('SELECT * FROM p6_evidencias WHERE ticket_id=? ORDER BY fecha DESC',(key,),path)
def history(key,path=None):return rows('SELECT actor,detalle,fecha FROM p6_historial WHERE ticket_id=? ORDER BY id DESC',(key,),path)
def attachments(key,path=None):return rows('SELECT id,nombre,mime,tamano,autor,fecha FROM p6_adjuntos WHERE ticket_id=? ORDER BY fecha DESC',(key,),path)


def log(c,key,actor,detail):c.execute('INSERT INTO p6_historial(ticket_id,actor,detalle,fecha) VALUES (?,?,?,?)',(key,actor or 'Equipo PMO',detail,now()))

def save_service(data,key=None,path=None):
    """Alta/edición manual de catálogo local; no modifica Paso 4."""
    name=needed(data.get('nombre'),'nombre del servicio')
    codigo=needed(data.get('codigo'),'código')
    a=positive_hours(data.get('sla_respuesta_h'));b=positive_hours(data.get('sla_resolucion_h'))
    old=service(key,path) if key else None
    mode=data.get('ans_tipo',old.get('ans_tipo','Calendario') if old else 'Calendario')
    if mode not in ('Calendario','Hábil'):raise ValidationError('Unidad ANS inválida.')
    operative=str(data.get('operativo_asignado',old.get('operativo_asignado','') if old else '') or '').strip()
    operative_id=_validate_pmo_member(operative,data.get('operativo_integrante_id'),path)
    with transaction(path) as c:
        if key:
            if not c.execute('SELECT 1 FROM p6_catalog WHERE id=?',(key,)).fetchone():raise ValidationError('Servicio inexistente')
            c.execute('''UPDATE p6_catalog SET codigo=?,nombre=?,descripcion=?,responsable=?,
             sla_respuesta_h=?,sla_resolucion_h=?,ans_tipo=?,operativo_asignado=?,operativo_integrante_id=?,actualizado_en=? WHERE id=?''',
             (codigo,name,data.get('descripcion',''),data.get('responsable',''),a,b,mode,operative,operative_id,now(),key))
        else:
            if c.execute('SELECT 1 FROM p6_catalog WHERE codigo=? COLLATE NOCASE',(codigo,)).fetchone():
                raise ValidationError('Ya existe un servicio con ese código.')
            key=uid()
            c.execute('''INSERT INTO p6_catalog(id,codigo,nombre,descripcion,responsable,sla_respuesta_h,
            sla_resolucion_h,version,origen,actualizado_en,ans_tipo,operativo_asignado,operativo_integrante_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (key,codigo,name,data.get('descripcion',''),data.get('responsable',''),a,b,
             'Registro local','Manual — habilitación por verificar',now(),mode,operative,operative_id))
    return key

def _catalog_rows(payload):
    schema=payload.get('schema')
    if schema=='PMO-FLYWHEEL-CENS-paso6-input-v1':
        return payload.get('services',[]),'Transferencia Paso 5 autorizada'
    if schema=='PMO-FLYWHEEL-CENS-paso5-input-v1':
        return payload.get('services',[]),'Expediente técnico Paso 4 (Paso 5 pendiente)'
    if schema=='PMO-CENS-P4-CATALOGO-v1':
        return [s for s in payload.get('services',[]) if s.get('estado')=='Aprobado'],'Catálogo Paso 4 (validación adicional requerida)'
    if schema=='PMO-FLYWHEEL-CENS-paso4-catalog-v1':
        return [s for s in payload.get('services',[]) if s.get('estado')=='Aprobado'],'Catálogo Paso 4'
    raise ValidationError('Expediente incompatible. Se admite JSON de transferencia del Paso 4 o su catálogo aprobado.')

def import_catalog(payload,path=None,source='JSON Paso 4'):
    items,origin=_catalog_rows(payload)
    if not isinstance(items,list):raise ValidationError('La lista de servicios es inválida.')
    created=0;skipped=0;bad=[]
    # Fila defectuosa implica operación totalmente cancelada. Solo importar servicios aprobados.
    validated=[]
    for i,s in enumerate(items,1):
        if not isinstance(s,dict):bad.append(i);continue
        if s.get('estado')!='Aprobado' or s.get('demo') or s.get('demostrativo'):bad.append(i);continue
        if payload.get('schema')=='PMO-FLYWHEEL-CENS-paso6-input-v1' and not (s.get('_paso5Transition') or {}).get('authorizedAt'):bad.append(i);continue
        code=str(s.get('codigo') or '').strip();name=str(s.get('nombre') or '').strip()
        if not code or not name:bad.append(i);continue
        validated.append((s,code,name))
    if bad:raise ValidationError(f'Servicios no aprobados, de prueba o incompletos (filas: {bad[:8]}). Importación cancelada.')
    with transaction(path) as c:
        for s,code,name in validated:
            if c.execute('SELECT 1 FROM p6_catalog WHERE codigo=? COLLATE NOCASE',(code,)).fetchone():
                skipped+=1;continue
            sid=uid();info=s.get('detalles') or {}
            # Texto del Paso 4 nunca se interpreta como horas de ANS.
            c.execute('''INSERT INTO p6_catalog(id,codigo,nombre,descripcion,responsable,version,origen,p4_id,actualizado_en)
              VALUES(?,?,?,?,?,?,?,?,?)''',(sid,code,name,s.get('descripcion',''),s.get('responsable',''),
                        str(s.get('actualizado_en') or s.get('version') or ''),origin,s.get('id') or None,now()))
            created+=1
    return {'nuevos':created,'existentes':skipped,'origen':origin,'nota':'Los ANS en horas se confirman en catálogo. Los expedientes del Paso 5 requieren autorización verificable.'}

def import_step4_direct(path=None):
    from . import step4
    return import_catalog(step4.step5_transfer(path),path)

def import_step5_direct(path=None):
    from . import step5
    return import_catalog(step5.export_step6(path),path,source='Paso 5 autorizado')

def _next_folio(c,service_code,at):
    """Código público anual por servicio; preserva PMO-0001 históricos."""
    m=re.search(r'SRV[-_ ]*0*(\d+)',str(service_code),re.I)
    token=f'SRV{int(m.group(1)):03d}' if m else 'SRVGEN'
    year=cal.local_dt(at).year
    prefix=f'TCK-{year}-{token}-'
    nums=[int(r[0][len(prefix):]) for r in c.execute('SELECT folio FROM p6_tickets WHERE folio LIKE ?',(prefix+'%',))
          if r[0].startswith(prefix) and r[0][len(prefix):].isdigit()]
    return prefix+f'{max(nums,default=0)+1:04d}'

def create_ticket(data,actor='Equipo PMO',path=None):
    title=needed(data.get('titulo'),'asunto');client=needed(data.get('cliente'),'cliente')
    desc=needed(data.get('descripcion'),'descripción')
    service_id=needed(data.get('servicio_id'),'servicio')
    priority=data.get('prioridad','Normal');origin=data.get('origen',ORIGINS[0])
    if priority not in PRIORITIES or origin not in ORIGINS:raise ValidationError('Prioridad u origen no válido.')
    project_type=data.get('tipo_proyecto','No aplica')
    complexity=data.get('complejidad','Sin clasificar')
    if project_type not in PROJECT_TYPES or complexity not in COMPLEXITIES:
        raise ValidationError('Tipo de proyecto o complejidad inválidos.')
    with transaction(path) as c:
        s=c.execute('SELECT * FROM p6_catalog WHERE id=? AND habilitado=1',(service_id,)).fetchone()
        if s is None:raise ValidationError('El servicio no existe o no está habilitado en el catálogo local.')
        resp=positive_hours(data.get('ans_respuesta_h',s['sla_respuesta_h']))
        mode=s['ans_tipo'] if 'ans_tipo' in s.keys() else 'Calendario'
        if data.get('ans_tipo') and data['ans_tipo']!=mode:
            raise ValidationError('La unidad ANS se define y valida en el catálogo; no se modifica en el ticket.')
        config=get_calendar(service_id,path) if mode=='Hábil' else None
        if mode=='Hábil':
            try:cal.check_calendar(config,True)
            except ValueError as ex:raise ValidationError(str(ex)) from ex
        resol=positive_hours(data.get('ans_resolucion_h',s['sla_resolucion_h']))
        client_id=data.get('cliente_id') or None
        if client_id and c.execute('SELECT 1 FROM pmo_clientes WHERE id=?',(client_id,)).fetchone() is None:
            raise ValidationError('El cliente del directorio no existe.')
        key=uid();t=now();folio=_next_folio(c,s['codigo'],t)
        operative=str(s['operativo_asignado'] if 'operativo_asignado' in s.keys() else '').strip()
        source='Catálogo operativo' if operative else ''
        stamp=cal.snapshot(config) if mode=='Hábil' else ''
        reply_due=cal.due_at(t,resp,config).isoformat() if mode=='Hábil' and resp is not None else None
        done_due=cal.due_at(t,resol,config).isoformat() if mode=='Hábil' and resol is not None else None
        c.execute('''INSERT INTO p6_tickets(id,folio,titulo,descripcion,cliente,cliente_id,dependencia,correo,
          servicio_id,origen,canal,prioridad,resultado_esperado,responsable,estado,creado_en,
          ans_respuesta_h,ans_resolucion_h,version_servicio,demo,actualizado_en,
          ans_tipo,ans_calendario_json,ans_respuesta_limite_en,ans_resolucion_limite_en,asignacion_fuente,
          asignado_en,tipo_proyecto,complejidad,protocolo_cierre,responsable_integrante_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
         (key,folio,title,desc,client,client_id,data.get('dependencia',''),data.get('correo',''),service_id,
          origin,data.get('canal','Portal PMO'),priority,data.get('resultado_esperado',''),operative,
          STAGES[1] if operative else STAGES[0],t,
          resp,resol,s['version'],int(bool(data.get('demo',False))),t,mode,stamp,reply_due,done_due,source,
          t if operative else None,project_type,complexity,'Conformidad',s['operativo_integrante_id']))
        log(c,key,actor,'Solicitud registrada'+(f'; asignación automática a {operative} ({source})' if operative else '; pendiente de triaje'))
    return key

def update_ticket(key,fields,actor='Equipo PMO',path=None):
    """Actualiza ficha sin permitir suplantar estados ni fechas técnicas o ANS congelados."""
    allowed={'titulo','descripcion','cliente','cliente_id','dependencia','correo','prioridad','resultado_esperado',
             'responsable','canal','entregable','aceptacion','calificacion','calificacion_comentario',
             'excepcion_evaluacion','motivo_excepcion','tipo_proyecto','complejidad','excepcion_autorizador','excepcion_evidencia'}
    unknown=set(fields)-allowed-{'responsable_integrante_id'}
    if 'responsable_integrante_id' in fields and 'responsable' not in fields:
        raise ValidationError('El ID de integrante debe actualizarse junto con el responsable visible.')
    if unknown:raise ValidationError('Campos protegidos: '+', '.join(sorted(unknown)))
    if 'prioridad' in fields and fields['prioridad'] not in PRIORITIES:raise ValidationError('Prioridad inválida')
    if 'tipo_proyecto' in fields and fields['tipo_proyecto'] not in PROJECT_TYPES:raise ValidationError('Tipo de proyecto inválido.')
    if 'complejidad' in fields and fields['complejidad'] not in COMPLEXITIES:raise ValidationError('Complejidad inválida.')
    if fields.get('cliente_id') and row('SELECT id FROM pmo_clientes WHERE id=?',(fields['cliente_id'],),path) is None:
        raise ValidationError('Cliente no registrado en Paso 01.')
    if 'calificacion' in fields and fields['calificacion'] not in (None,''):
        if isinstance(fields['calificacion'],bool) or not isinstance(fields['calificacion'],int) or not 1<=fields['calificacion']<=10:
            raise ValidationError('Calificación del cliente de 1 a 10.')
    member_id=_validate_pmo_member(fields['responsable'],fields.get('responsable_integrante_id'),path) if 'responsable' in fields else None
    with transaction(path) as c:
        old=c.execute('SELECT * FROM p6_tickets WHERE id=?',(key,)).fetchone()
        if old is None:raise ValidationError('Solicitud inexistente')
        clean={k:(int(bool(v)) if k=='excepcion_evaluacion' else v if v!='' or k!='calificacion' else None) for k,v in fields.items() if k!='responsable_integrante_id'}
        if 'calificacion' in clean and clean['calificacion'] is not None:
            clean['calificado_en']=now()
        clean['actualizado_en']=now()
        if 'responsable' in fields:clean['responsable_integrante_id']=member_id
        if 'responsable' in fields and fields['responsable']!=old['responsable'] and old['estado']=='En proceso':
            _enforce_wip(c,old,fields['responsable'],'En proceso',actor,fields.get('justificacion_wip',''))
        c.execute('UPDATE p6_tickets SET '+','.join(f'{k}=?' for k in clean)+' WHERE id=?',(*clean.values(),key))
        log(c,key,actor,'Ficha actualizada: '+', '.join(fields))

def first_response(key,actor='Equipo PMO',path=None):
    with transaction(path) as c:
        r=c.execute('SELECT estado,primera_respuesta_en FROM p6_tickets WHERE id=?',(key,)).fetchone()
        if not r:raise ValidationError('Solicitud inexistente')
        if r['estado']==STAGES[0]:raise ValidationError('Asigna primero el servicio.')
        if r['primera_respuesta_en']:raise ValidationError('La primera respuesta ya fue registrada.')
        c.execute('UPDATE p6_tickets SET primera_respuesta_en=?,actualizado_en=? WHERE id=?',(now(),now(),key))
        log(c,key,actor,'Primera respuesta registrada explícitamente')

def add_task(key,description,actor='Equipo PMO',path=None):
    desc=needed(description,'actividad')
    with transaction(path) as c:
        if not c.execute('SELECT 1 FROM p6_tickets WHERE id=?',(key,)).fetchone():raise ValidationError('Solicitud inexistente')
        c.execute('INSERT INTO p6_tareas VALUES(?,?,?,0)',(uid(),key,desc));log(c,key,actor,'Actividad agregada: '+desc)

def set_task(key,task_id,completed,actor='Equipo PMO',path=None):
    with transaction(path) as c:
        r=c.execute('SELECT 1 FROM p6_tareas WHERE id=? AND ticket_id=?',(task_id,key)).fetchone()
        if not r:raise ValidationError('Actividad inexistente')
        c.execute('UPDATE p6_tareas SET completada=? WHERE id=?',(int(bool(completed)),task_id))
        log(c,key,actor,'Actividad '+('completada' if completed else 'reabierta'))

def add_comment(key,text,actor='Equipo PMO',tipo='Equipo PMO',path=None):
    val=needed(text,'comentario')
    with transaction(path) as c:
        c.execute('INSERT INTO p6_comentarios VALUES(?,?,?,?,?,?)',(uid(),key,actor,tipo,val,now()))
        log(c,key,actor,'Comentario registrado ('+tipo+')')

def add_evidence(key,title,reference,actor='Equipo PMO',path=None):
    with transaction(path) as c:
        c.execute('INSERT INTO p6_evidencias VALUES(?,?,?,?,?,?)',(uid(),key,needed(title,'título de evidencia'),needed(reference,'referencia'),actor,now()))
        log(c,key,actor,'Evidencia referenciada')

def upload_attachment(key,filename,content,mime='application/octet-stream',actor='Equipo PMO',path=None):
    """Adjunto local opcional, tamaño máximo 300 KB. El respaldo JSON conserva su contenido."""
    import base64
    name=needed(Path(str(filename).replace('\\','/')).name,'nombre del archivo')
    if not isinstance(content,bytes) or not 1<=len(content)<=300000:
        raise ValidationError('El adjunto debe tener entre 1 B y 300 KB.')
    with transaction(path) as c:
        if not c.execute('SELECT 1 FROM p6_tickets WHERE id=?',(key,)).fetchone():raise ValidationError('Solicitud inexistente.')
        aid=uid()
        c.execute('INSERT INTO p6_adjuntos VALUES (?,?,?,?,?,?,?,?)',
           (aid,key,name,str(mime or 'application/octet-stream')[:120],base64.b64encode(content).decode('ascii'),len(content),actor,now()))
        log(c,key,actor,'Adjunto registrado: '+name)
    return aid

def attachment_content(aid,path=None):
    import base64
    obj=row('SELECT nombre,contenido_b64 FROM p6_adjuntos WHERE id=?',(aid,),path)
    if not obj:raise ValidationError('Adjunto inexistente.')
    return obj['nombre'],base64.b64decode(obj['contenido_b64'])

def transition(key,to,actor='Equipo PMO',reason='',path=None):
    if to not in STAGES:raise ValidationError('Estado no válido')
    with transaction(path) as c:
        t=c.execute('SELECT * FROM p6_tickets WHERE id=?',(key,)).fetchone()
        if t is None:raise ValidationError('Solicitud inexistente')
        a=STAGES.index(t['estado']);b=STAGES.index(to)
        if abs(a-b)!=1:raise ValidationError('Solo se puede avanzar o retroceder una etapa consecutiva.')
        changes={'estado':to,'actualizado_en':now()}
        if b>a:
            if b==2:
                _enforce_wip(c,t,t['responsable'],'En proceso',actor,reason)
            if b==1:
                if not str(t['responsable']).strip():raise ValidationError('Asigne un responsable antes de avanzar.')
                changes['asignado_en']=t['asignado_en'] or now()
            if b==2:changes['iniciado_en']=t['iniciado_en'] or now()
            if b==3:
                if not str(t['entregable']).strip():raise ValidationError('Registre el entregable antes de enviar a evaluación.')
                if c.execute('SELECT 1 FROM p6_tareas WHERE ticket_id=? AND completada=0',(key,)).fetchone():
                    raise ValidationError('Existen tareas pendientes de finalización.')
                changes['terminado_en']=now();changes['cerrado_en']=None
            if b==4:
                if t['protocolo_cierre']=='Conformidad':
                    conform=c.execute("SELECT decision FROM p6_respuestas_cliente WHERE ticket_id=? AND vigente=1 ORDER BY rowid DESC LIMIT 1",(key,)).fetchone()
                    if not conform or conform['decision']!='Conforme':
                        if not t['excepcion_evaluacion'] or not str(t['motivo_excepcion']).strip() or not str(t['excepcion_autorizador']).strip() or not str(t['excepcion_evidencia']).strip():
                            raise ValidationError('Falta conformidad verificada del cliente o excepción autorizada con evidencia. No hay cierre automático por silencio.')
                    changes['cerrado_en']=now()
                else:
                    if t['calificacion'] is None:
                        if not t['excepcion_evaluacion'] or not str(t['motivo_excepcion']).strip():
                            raise ValidationError('Registre una calificación 1–10 o la excepción justificada.')
                    elif not t['aceptacion']:
                        raise ValidationError('Registre si se cumplió el resultado esperado.')
                    changes['cerrado_en']=now()
        else:
            reason=needed(reason,'motivo de devolución')
            if b<=2:
                changes.update({'terminado_en':None,'cerrado_en':None,'calificacion':None,
                                'calificacion_comentario':'','calificado_en':None,'aceptacion':'',
                                'excepcion_evaluacion':0,'motivo_excepcion':'','excepcion_autorizador':'','excepcion_evidencia':''})
                if t['protocolo_cierre']=='Conformidad':
                    c.execute('UPDATE p6_respuestas_cliente SET vigente=0 WHERE ticket_id=?',(key,))
                    c.execute("UPDATE p6_invitaciones_conformidad SET estado='Revocada' WHERE ticket_id=? AND estado='Activa'",(key,))
            if b==3:changes['cerrado_en']=None
        c.execute('UPDATE p6_tickets SET '+','.join(f'{k}=?' for k in changes)+' WHERE id=?',(*changes.values(),key))
        log(c,key,actor,('Avance' if b>a else 'Devolución')+f': {t["estado"]} → {to}'+(f'. Motivo: {reason}' if b<a else ''))

def _dt(x):
    if not x:return None
    val=datetime.fromisoformat(str(x).replace('Z','+00:00'))
    return val if val.tzinfo else val.replace(tzinfo=timezone.utc)

def elapsed(start,end):
    if not start or not end:return None
    return max(0,(_dt(end)-_dt(start)).total_seconds()/3600)

def sla_state(item,kind,at=None):
    """Cada plazo es independiente; sin ANS nunca es cumplimiento automático."""
    response=kind in ('respuesta','response')
    limit=item.get('ans_respuesta_h' if response else 'ans_resolucion_h')
    mark=item.get('primera_respuesta_en' if response else 'terminado_en')
    if limit is None:return {'estado':'Sin ANS','evaluable':False,'horas':None,'plazo':None}
    mode=item.get('ans_tipo','Calendario')
    end=mark or at or now()
    if mode=='Hábil':
        try:
            c=json.loads(item.get('ans_calendario_json') or '{}')
            hours=cal.business_hours(item['creado_en'],end,c)
        except (ValueError,KeyError,TypeError) as ex:
            return {'estado':'Calendario inválido','evaluable':False,'horas':None,'plazo':limit,'detalle':str(ex)}
    else:hours=elapsed(item['creado_en'],end)
    state=('Cumple ANS' if hours<=limit else 'Vencido') if mark else ('Vencido' if hours>limit else 'En riesgo' if hours>=.8*limit else 'En plazo')
    percentage=round(100*hours/limit,1) if hours is not None else None
    band=(('Cumplido' if hours<=limit else 'Incumplido') if mark else 'Vencido' if percentage>=100 else
          'Rojo' if percentage>=80 else 'Ámbar' if percentage>=50 else 'Verde')
    return {'estado':state,'evaluable':bool(mark),'horas':hours,'plazo':limit,'unidad':mode,
            'porcentaje':percentage,'semaforo':band,'restantes_h':max(0,limit-hours) if hours is not None else None}

def statistics(items=None,at=None,path=None):
    all_t=tickets(path) if items is None else list(items)
    completed=[t for t in all_t if t['terminado_en']]
    finalized=[t for t in all_t if t['estado']==STAGES[4]]
    response=[sla_state(t,'respuesta',at) for t in all_t]
    resolution=[sla_state(t,'resolucion',at) for t in all_t]
    evr=[x for x in response if x['evaluable']];evs=[x for x in resolution if x['evaluable']]
    scores=[t['calificacion'] for t in all_t if t['calificacion'] is not None]
    avg=lambda v:sum(v)/len(v) if v else None
    risks=sum(t['estado'] not in STAGES[3:] and sla_state(t,'resolucion',at)['estado'] in ('En riesgo','Vencido') for t in all_t)
    return {'recibidas':len(all_t),'atendidas':len(completed),'finalizadas':len(finalized),
            'activas':len(all_t)-len(completed),
            'servicios_atendidos':len({t['servicio_id'] for t in completed}),
            'cumplimiento_respuesta':(100*sum(x['estado']=='Cumple ANS' for x in evr)/len(evr) if evr else None),
            'base_respuesta':len(evr),
            'cumplimiento_resolucion':(100*sum(x['estado']=='Cumple ANS' for x in evs)/len(evs) if evs else None),
            'base_resolucion':len(evs),'calificacion':avg(scores),'evaluaciones_recibidas':len(scores),
            'tiempo_medio':avg([elapsed(t['creado_en'],t['terminado_en']) for t in completed]),
            'riesgos':risks,'sin_ans':sum(t['ans_resolucion_h'] is None for t in all_t)}


# V0.39.23 · Reglas de capacidad, riesgo ANS, conocimiento y conformidad

def work_limits(path=None):
    return rows('SELECT * FROM p6_wip_limits ORDER BY operador,etapa',path=path)

def set_work_limit(operator,limit,stage='En proceso',mode='Advertir',path=None):
    operator=needed(operator,'operador')
    if stage not in STAGES[1:4] or mode not in ('Advertir','Bloquear'):
        raise ValidationError('Etapa o modo WIP inválido.')
    if isinstance(limit,bool) or not isinstance(limit,int) or limit<=0 or limit>100:
        raise ValidationError('Límite WIP debe ser entero de 1 a 100.')
    with transaction(path) as c:
        c.execute('''INSERT INTO p6_wip_limits VALUES(?,?,?,?,?)
          ON CONFLICT(operador,etapa) DO UPDATE SET limite=excluded.limite,
          modo=excluded.modo,actualizado_en=excluded.actualizado_en''',(operator,stage,limit,mode,now()))

def wip_summary(path=None):
    assignments=rows("SELECT responsable,estado,COUNT(*) AS abiertos FROM p6_tickets WHERE estado!='Finalizado' AND responsable!='' GROUP BY responsable,estado",path=path)
    counts={(x['responsable'],x['estado']):x['abiertos'] for x in assignments}
    return [{**l,'actual':counts.get((l['operador'],l['etapa']),0),
             'restantes':max(0,l['limite']-counts.get((l['operador'],l['etapa']),0))} for l in work_limits(path)]

def _enforce_wip(c,t,operator,stage,actor,reason=''):
    operator=str(operator or '').strip()
    if not operator:return
    rule=c.execute('SELECT * FROM p6_wip_limits WHERE operador=? AND etapa=?',(operator,stage)).fetchone()
    if not rule:return
    num=c.execute('''SELECT COUNT(*) FROM p6_tickets WHERE estado=? AND responsable=? AND id!=?''',
                  (stage,operator,t['id'])).fetchone()[0]
    if num<rule['limite']:return
    if rule['modo']=='Bloquear':
        raise ValidationError(f'Capacidad WIP agotada para {operator} ({num}/{rule["limite"]}). Reasigna o actualiza límite documentadamente.')
    if not str(reason or '').strip():
        raise ValidationError(f'WIP agotado para {operator}; registra justificación de excepción.')
    c.execute('INSERT INTO p6_wip_excepciones VALUES(?,?,?,?,?,?,?,?)',
              (uid(),t['id'],operator,stage,rule['limite'],str(reason).strip(),actor,now()))
    log(c,t['id'],actor,f'Excepción WIP {num+1}/{rule["limite"]}: {reason}')

def wip_override_ticket(key,operator,reason,actor='Equipo PMO',path=None,*,member_id=None):
    """Reasignación auditada con control WIP en caso abierto."""
    operator=needed(operator,'responsable operativo')
    member_id=_validate_pmo_member(operator,member_id,path)
    with transaction(path) as c:
        t=c.execute('SELECT * FROM p6_tickets WHERE id=?',(key,)).fetchone()
        if not t:raise ValidationError('Ticket inexistente.')
        if t['estado']=='En proceso':_enforce_wip(c,t,operator,'En proceso',actor,reason)
        c.execute('UPDATE p6_tickets SET responsable=?,responsable_integrante_id=?,actualizado_en=? WHERE id=?',(operator,member_id,now(),key))
        log(c,key,actor,'Responsable operativo actualizado a '+operator)

def set_escalation_config(service_id,recipient='',owner='',enabled=False,path=None):
    if not service(service_id,path):raise ValidationError('Servicio inexistente.')
    recipient=str(recipient or '').strip()
    if enabled and ('@' not in recipient or '.' not in recipient.split('@')[-1]):
        raise ValidationError('Para activar notificación externa registra correo válido.')
    with transaction(path) as c:
        c.execute('''INSERT INTO p6_escalamiento_config VALUES(?,?,?,?,?) ON CONFLICT(servicio_id)
         DO UPDATE SET correo=excluded.correo,responsable=excluded.responsable,
         habilitado=excluded.habilitado,actualizado_en=excluded.actualizado_en''',
         (service_id,recipient,str(owner or '').strip(),int(bool(enabled)),now()))

def escalation_config(service_id,path=None):
    return row('SELECT * FROM p6_escalamiento_config WHERE servicio_id=?',(service_id,),path) or {
        'servicio_id':service_id,'correo':'','responsable':'','habilitado':0}

def sla_alerts(ticket_id=None,path=None):
    if ticket_id:return rows('SELECT * FROM p6_alertas_ans WHERE ticket_id=? ORDER BY fecha DESC',(ticket_id,),path)
    return rows('SELECT * FROM p6_alertas_ans ORDER BY fecha DESC',path=path)

def scan_sla_alerts(at=None,path=None):
    """Detección idempotente. Invocable por aplicación o tarea programada.
    Sin SMTP no afirma que el cliente haya recibido un correo.
    """
    current=at or now();created=0
    with transaction(path) as c:
        active=[dict(t) for t in c.execute("SELECT * FROM p6_tickets WHERE estado!='Finalizado'")]
        for t in active:
            cfg=c.execute('SELECT * FROM p6_escalamiento_config WHERE servicio_id=?',(t['servicio_id'],)).fetchone()
            for kind in ('respuesta','resolucion'):
                stt=sla_state(t,kind,current)
                if stt.get('evaluable') or stt.get('porcentaje') is None:continue
                for threshold in ((100,) if stt['porcentaje']>=100 else (80,)):
                    if stt['porcentaje']<threshold:continue
                    # Escalamiento configurado solo activa correo; alertas en-app siempre.
                    owner=cfg['responsable'] if cfg else ''
                    recipient=cfg['correo'] if cfg and cfg['habilitado'] else ''
                    cur=c.execute('''INSERT OR IGNORE INTO p6_alertas_ans
                      (id,ticket_id,tipo,umbral,estado,responsable,correo,fecha,detalle)
                      VALUES(?,?,?,?,?,?,?,?,?)''',
                      (uid(),t['id'],kind,threshold,'Pendiente',owner,recipient,current,
                       f'{kind}: {stt["porcentaje"]:.1f}% de {stt["plazo"]} h {stt.get("unidad","Calendario")}'))
                    created+=cur.rowcount
                    if cur.rowcount:log(c,t['id'],'Motor ANS',f'Alerta {kind} {threshold}% registrada')
    return {'nuevas':created,'alertas':len(sla_alerts(path=path))}

def mark_alert_seen(alert_id,actor='Equipo PMO',path=None):
    with transaction(path) as c:
        if not c.execute('SELECT 1 FROM p6_alertas_ans WHERE id=?',(alert_id,)).fetchone():raise ValidationError('Alerta inexistente')
        c.execute("UPDATE p6_alertas_ans SET estado='Vista' WHERE id=?",(alert_id,))

def dispatch_sla_emails(path=None):
    """Envío opcional SMTP. Credenciales solo por variables de entorno; no se guarda secreto.
    Requiere ejecución periódica del worker, no es autónomo dentro de Streamlit.
    """
    from email.message import EmailMessage
    import smtplib
    host=os.getenv('PMO_SMTP_HOST','').strip();sender=os.getenv('PMO_SMTP_FROM','').strip()
    if not host or not sender:return {'enviadas':0,'pendientes':len(rows("SELECT id FROM p6_alertas_ans WHERE estado='Pendiente' AND correo!=''",path=path)), 'nota':'SMTP no configurado.'}
    count=0;errors=[]
    for alert in rows("SELECT a.*,t.folio,t.titulo FROM p6_alertas_ans a JOIN p6_tickets t ON t.id=a.ticket_id WHERE a.estado='Pendiente' AND a.correo!=''",path=path):
        msg=EmailMessage();msg['From']=sender;msg['To']=alert['correo'];msg['Subject']=f'PMO CENS · Alerta ANS {alert["umbral"]}% · {alert["folio"]}'
        msg.set_content(f'Caso: {alert["folio"]} — {alert["titulo"]}\\n{alert["detalle"]}\\nEscalamiento dirigido a: {alert["responsable"]}\\nConsulta el aplicativo para gestionar el caso.')
        try:
            with smtplib.SMTP(host,int(os.getenv('PMO_SMTP_PORT','587')),timeout=12) as server:
                if os.getenv('PMO_SMTP_STARTTLS','1')=='1':server.starttls()
                username=os.getenv('PMO_SMTP_USER','');pwd=os.getenv('PMO_SMTP_PASSWORD','')
                if username:server.login(username,pwd)
                server.send_message(msg)
            with transaction(path) as c:c.execute("UPDATE p6_alertas_ans SET estado='Enviada',notificado_en=? WHERE id=? AND estado='Pendiente'",(now(),alert['id']))
            count+=1
        except Exception as ex:errors.append(f'{alert["folio"]}: {type(ex).__name__}')
    return {'enviadas':count,'errores':errors}

def save_knowledge(service_id,title,body,reference='',version='1.0',status='Borrador',owner='Equipo PMO',key=None,path=None):
    if not service(service_id,path):raise ValidationError('Servicio inexistente.')
    if status not in ('Borrador','Publicado'):raise ValidationError('Estado de artículo inválido.')
    title=needed(title,'título');body=needed(body,'contenido de procedimiento');version=needed(version,'versión')
    with transaction(path) as c:
        if key:
            if not c.execute('SELECT 1 FROM p6_conocimiento WHERE id=? AND servicio_id=?',(key,service_id)).fetchone():raise ValidationError('Artículo inexistente.')
            c.execute('UPDATE p6_conocimiento SET titulo=?,cuerpo=?,referencia=?,version=?,estado=?,responsable=?,actualizado_en=? WHERE id=?',
                      (title,body,reference,version,status,owner,now(),key))
        else:
            key=uid();c.execute('INSERT INTO p6_conocimiento VALUES(?,?,?,?,?,?,?,?,?)',(key,service_id,title,body,reference,version,status,owner,now()))
    return key

def knowledge_articles(service_id,path=None,include_drafts=False):
    if include_drafts:return rows('SELECT * FROM p6_conocimiento WHERE servicio_id=? ORDER BY actualizado_en DESC',(service_id,),path)
    return rows("SELECT * FROM p6_conocimiento WHERE servicio_id=? AND estado='Publicado' ORDER BY actualizado_en DESC",(service_id,),path)

def invite_conformity(ticket_id,actor='Equipo PMO',valid_days=7,reference='',path=None):
    """Token de un solo uso, mostrado una vez; NO sustituye autenticación corporativa SSO."""
    from datetime import timedelta
    if isinstance(valid_days,bool) or not isinstance(valid_days,int) or not 1<=valid_days<=30:
        raise ValidationError('Vigencia entre 1 y 30 días.')
    secret=secrets.token_urlsafe(24);digest=hashlib.sha256(secret.encode()).hexdigest()
    with transaction(path) as c:
        t=c.execute('SELECT * FROM p6_tickets WHERE id=?',(ticket_id,)).fetchone()
        if not t or t['estado']!='Evaluación del servicio':raise ValidationError('El ticket debe estar en Evaluación del servicio.')
        c.execute("UPDATE p6_invitaciones_conformidad SET estado='Revocada' WHERE ticket_id=? AND estado='Activa'",(ticket_id,))
        c.execute('UPDATE p6_respuestas_cliente SET vigente=0 WHERE ticket_id=? AND vigente=1',(ticket_id,))
        c.execute("UPDATE p6_tickets SET aceptacion='' WHERE id=?",(ticket_id,))
        issue=now();expiry=(datetime.now(timezone.utc)+timedelta(days=valid_days)).isoformat(timespec='seconds')
        key=uid();c.execute('INSERT INTO p6_invitaciones_conformidad VALUES(?,?,?,?,?,?,?,?)',
             (key,ticket_id,digest,issue,expiry,actor,'Activa',str(reference or '')))
        log(c,ticket_id,actor,'Código de conformidad de un solo uso emitido (sin guardar código plano)')
    return secret

def conformity_invitations(ticket_id,path=None):
    return rows('SELECT id,ticket_id,emitida_en,vence_en,emitida_por,estado,referencia_envio FROM p6_invitaciones_conformidad WHERE ticket_id=? ORDER BY emitida_en DESC',(ticket_id,),path)

def client_feedback(ticket_id,path=None):
    return rows('SELECT decision,csat,nps,observaciones,fecha,vigente FROM p6_respuestas_cliente WHERE ticket_id=? ORDER BY rowid DESC',(ticket_id,),path)

def submit_conformity(ticket_id,code,decision,csat=None,nps=None,comment='',path=None):
    """Verificación por posesión del código, sin fingir identidad autenticada."""
    if decision not in ('Conforme','Solicita ajustes'):raise ValidationError('Decisión inválida.')
    if csat is not None and (type(csat) is not int or not 1<=csat<=5):raise ValidationError('CSAT debe estar entre 1 y 5.')
    if nps is not None and (type(nps) is not int or not 0<=nps<=10):raise ValidationError('NPS debe estar entre 0 y 10.')
    if not isinstance(code,str) or not code.strip():raise ValidationError('Introduce código de verificación.')
    with transaction(path) as c:
        t=c.execute('SELECT estado FROM p6_tickets WHERE id=?',(ticket_id,)).fetchone()
        if not t or t['estado']!='Evaluación del servicio':raise ValidationError('Ticket fuera de evaluación.')
        invitations=c.execute('SELECT * FROM p6_invitaciones_conformidad WHERE ticket_id=? AND estado=\'Activa\'',(ticket_id,)).fetchall()
        digest=hashlib.sha256(code.strip().encode()).hexdigest()
        valid=next((x for x in invitations if hmac.compare_digest(x['secreto_hash'],digest) and _dt(x['vence_en'])>=datetime.now(timezone.utc)),None)
        if not valid:raise ValidationError('Código inválido, vencido o ya utilizado.')
        c.execute('INSERT INTO p6_respuestas_cliente(id,ticket_id,invitacion_id,decision,csat,nps,observaciones,fecha) VALUES(?,?,?,?,?,?,?,?)',
            (uid(),ticket_id,valid['id'],decision,csat,nps,str(comment or '').strip(),now()))
        c.execute("UPDATE p6_invitaciones_conformidad SET estado='Respondida' WHERE id=?",(valid['id'],))
        c.execute('UPDATE p6_tickets SET aceptacion=?,actualizado_en=? WHERE id=?',('Sí' if decision=='Conforme' else 'No',now(),ticket_id))
        log(c,ticket_id,'Cliente · código de posesión',f'Conformidad {decision}; CSAT {csat if csat is not None else "sin dato"}; NPS {nps if nps is not None else "sin dato"}')
    return decision

def satisfaction_summary(items=None,path=None):
    target={t['id'] for t in (tickets(path) if items is None else items)}
    candidate_rows=rows('SELECT * FROM p6_respuestas_cliente WHERE vigente=1 ORDER BY rowid DESC',path=path)
    dedup={}
    for x in candidate_rows:
        if x['ticket_id'] in target:dedup.setdefault(x['ticket_id'],x)
    values=list(dedup.values())
    csat=[x['csat'] for x in values if x['csat'] is not None]
    nps=[x['nps'] for x in values if x['nps'] is not None]
    return {'csat':round(sum(csat)/len(csat),2) if csat else None,'base_csat':len(csat),
            'nps':round(100*(sum(x>=9 for x in nps)-sum(x<=6 for x in nps))/len(nps),1) if nps else None,
            'base_nps':len(nps),'conformidades':sum(x['decision']=='Conforme' for x in values),
            'ajustes':sum(x['decision']=='Solicita ajustes' for x in values)}

def classification(score):
    if score is None:return None
    for a,b,name in CATEGORIES:
        if a<=score<=b:return name
    raise ValidationError('Puntaje fuera del rango 35–175.')

def evaluation_list(path=None):return rows('SELECT * FROM p6_evaluaciones ORDER BY version DESC',path=path)
def evaluation(key,path=None):return row('SELECT * FROM p6_evaluaciones WHERE id=?',(key,),path)
def answers(key,path=None):return rows('SELECT * FROM p6_respuestas WHERE evaluacion_id=? ORDER BY numero',(key,),path)
def new_evaluation(owner,path=None):
    key=uid()
    with transaction(path) as c:
        version=c.execute('SELECT COALESCE(MAX(version),0)+1 FROM p6_evaluaciones').fetchone()[0]
        c.execute('INSERT INTO p6_evaluaciones VALUES(?,?,?,?,?,?,?,?)',(key,version,needed(owner,'responsable'),'Borrador',None,None,now(),None))
    return key

def save_answer(key,number,value,observation='',evidence='',path=None):
    if not isinstance(number,int) or not 1<=number<=35:raise ValidationError('Ítem fuera de rango.')
    if not isinstance(value,int) or not 1<=value<=5:raise ValidationError('Escala 1–5.')
    with transaction(path) as c:
        ev=c.execute('SELECT estado FROM p6_evaluaciones WHERE id=?',(key,)).fetchone()
        if ev is None or ev['estado']!='Borrador':raise ValidationError('No se puede modificar una evaluación archivada.')
        c.execute('''INSERT INTO p6_respuestas(evaluacion_id,numero,valor,observacion,evidencia,fecha)
           VALUES(?,?,?,?,?,?) ON CONFLICT(evaluacion_id,numero) DO UPDATE SET
           valor=excluded.valor,observacion=excluded.observacion,evidencia=excluded.evidencia,fecha=excluded.fecha''',
          (key,number,value,observation,evidence,now()))

def evaluation_summary(key,path=None):
    ev=evaluation(key,path)
    if not ev:raise ValidationError('Evaluación inexistente.')
    ans=answers(key,path);by={x['numero']:x for x in ans};ds=[]
    for i,dim in enumerate(QUESTIONS):
        vals=[by[j]['valor'] for j in range(i*5+1,i*5+6) if j in by]
        ds.append({'nombre':dim['name'],'respondidas':len(vals),'subtotal':sum(vals),'promedio':(sum(vals)/len(vals) if vals else None)})
    total=sum(x['valor'] for x in ans)
    return {**ev,'respondidas':len(ans),'puntaje_actual':total,'puntaje_final':total if len(ans)==35 else None,
            'clasificacion_final':classification(total) if len(ans)==35 else None,'dimensiones':ds}

def finish_evaluation(key,path=None):
    sum_=evaluation_summary(key,path)
    if sum_['respondidas']!=35:raise ValidationError('Se requieren 35 respuestas para finalizar.')
    with transaction(path) as c:
        ev=c.execute('SELECT estado FROM p6_evaluaciones WHERE id=?',(key,)).fetchone()
        if ev['estado']!='Borrador':raise ValidationError('La evaluación ya está finalizada.')
        c.execute('UPDATE p6_evaluaciones SET estado=?,puntaje=?,clasificacion=?,finalizado_en=? WHERE id=?',
          ('Finalizada',sum_['puntaje_final'],sum_['clasificacion_final'],now(),key))
    return sum_

def export_tickets_csv(path=None):
    output=io.StringIO();fieldnames=['folio','titulo','cliente','dependencia','responsable','servicio_id','prioridad','estado','creado_en','primera_respuesta_en','terminado_en','cerrado_en','ans_respuesta_h','ans_resolucion_h','ans_tipo','tipo_proyecto','complejidad','calificacion']
    writer=csv.DictWriter(output,fieldnames=fieldnames,delimiter=';',extrasaction='ignore');writer.writeheader();writer.writerows(tickets(path))
    return output.getvalue().encode('utf-8-sig')

def export_step7(path=None):
    data=[{**t,'servicio':service(t['servicio_id'],path)['nombre'],
            'ans_respuesta':sla_state(t,'respuesta')['estado'],'ans_resolucion':sla_state(t,'resolucion')['estado'],
            'tareas':tasks(t['id'],path),'comentarios':comments(t['id'],path),'evidencias':evidences(t['id'],path),
            'historial':history(t['id'],path),'adjuntos':attachments(t['id'],path),
            'conformidad':client_feedback(t['id'],path),'alertas_ans':sla_alerts(t['id'],path)} for t in tickets(path) if not t['demo']]
    return {'schema':'PMO-FLYWHEEL-CENS-paso7-input-v1','origen':'Paso 6 · CENS Streamlit',
            'exportado_en':now(),'medicion':'ANS según unidad y calendario congelados por ticket',
            'tickets':data,'resumen':statistics([t for t in tickets(path) if not t['demo']])}

def remove_demo(path=None):
    """Elimina solamente tickets y servicios demostrativos del Paso 6, preservando otros pasos."""
    with transaction(path) as c:
        ids=[r['id'] for r in c.execute('SELECT id FROM p6_tickets WHERE demo=1')]
        for table in ('p6_tareas','p6_comentarios','p6_evidencias','p6_adjuntos','p6_historial','p6_wip_excepciones','p6_alertas_ans','p6_respuestas_cliente','p6_invitaciones_conformidad'):
            for key in ids:c.execute(f'DELETE FROM {table} WHERE ticket_id=?',(key,))
        for key in ids:c.execute('DELETE FROM p6_tickets WHERE id=?',(key,))
        services=[r['id'] for r in c.execute('SELECT id FROM p6_catalog WHERE demo=1')]
        deleted=0
        for key in services:
            if not c.execute('SELECT 1 FROM p6_tickets WHERE servicio_id=?',(key,)).fetchone():
                for table in ('p6_conocimiento','p6_escalamiento_config','p6_calendar_config'):
                    c.execute(f'DELETE FROM {table} WHERE servicio_id=?',(key,))
                c.execute('DELETE FROM p6_catalog WHERE id=?',(key,));deleted+=1
    return {'tickets_eliminados':len(ids),'servicios_eliminados':deleted}

def export_backup(path=None):
    tables=['p6_catalog','p6_tickets','p6_tareas','p6_comentarios','p6_evidencias','p6_adjuntos','p6_historial','p6_evaluaciones','p6_respuestas','p6_calendar_config','p6_wip_limits','p6_wip_excepciones','p6_escalamiento_config','p6_alertas_ans','p6_conocimiento','p6_invitaciones_conformidad','p6_respuestas_cliente']
    return {'schema':'PMO-FLYWHEEL-CENS-paso6-backup-v1','exportedAt':now(),
            'tables':{name:rows(f'SELECT * FROM {name}',path=path) for name in tables}}

def restore_backup(payload,confirm=False,path=None):
    if not confirm:raise ValidationError('La restauración requiere confirmación explícita.')
    if payload.get('schema')!='PMO-FLYWHEEL-CENS-paso6-backup-v1':raise ValidationError('Respaldo incompatible.')
    order=['p6_catalog','p6_tickets','p6_tareas','p6_comentarios','p6_evidencias','p6_adjuntos','p6_historial','p6_evaluaciones','p6_respuestas','p6_calendar_config','p6_wip_limits','p6_wip_excepciones','p6_escalamiento_config','p6_alertas_ans','p6_conocimiento','p6_invitaciones_conformidad','p6_respuestas_cliente']
    if not isinstance(payload.get('tables'),dict):raise ValidationError('Tablas incompletas.')
    required=set(order)-{'p6_calendar_config','p6_wip_limits','p6_wip_excepciones','p6_escalamiento_config','p6_alertas_ans','p6_conocimiento','p6_invitaciones_conformidad','p6_respuestas_cliente'}
    provided=set(payload['tables'])
    if not required.issubset(provided) or not provided.issubset(set(order)):
        raise ValidationError('Tablas del respaldo incompletas o no admitidas.')
    # Compatibilidad: respaldos anteriores a la existencia del calendario por servicio.
    tables={**{table:[] for table in order if table not in payload['tables']},**payload['tables']}
    # Validar forma antes de borrar el estado vigente. Transacción total y FK activadas.
    for table in order:
        if not isinstance(tables[table],list):raise ValidationError('Registros del respaldo inválidos.')
    with transaction(path) as c:
        for table in reversed(order):c.execute(f'DELETE FROM {table}')
        for table in order:
            columns={r[1] for r in c.execute(f'PRAGMA table_info({table})')}
            for item in tables[table]:
                if not isinstance(item,dict) or not set(item).issubset(columns):raise ValidationError('Columnas del respaldo incompatibles.')
                if item:
                    names=tuple(item)
                    c.execute(f'INSERT INTO {table} ('+','.join(names)+') VALUES ('+','.join('?'*len(names))+')',tuple(item.values()))
    return {t:len(tables[t]) for t in order}
