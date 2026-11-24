"""V0.34: muestra y seguimiento del levantamiento de expectativas del Paso 02.

La muestra es una herramienta de gestión, NO modifica las respuestas, los grupos,
los pesos expertos ni las ecuaciones del motor V5. No genera respuestas ficticias.
"""
from __future__ import annotations

import csv
import io
import json
from collections import Counter
from contextlib import closing
from datetime import date
from pathlib import Path
from typing import Mapping

from .clients import ValidationError, list_clients
from .client_directory import backup_clients_database
from .storage import connect, transaction
from .step2_engine_audit import readiness

STATES = ('Seleccionado', 'Convocado', 'En seguimiento', 'No participará')
ACTIVE_STATES = STATES[:3]
CHANNELS = ('', 'Presencial', 'Teams', 'Correo', 'Teléfono', 'Otro')
SCHEMA = '''
CREATE TABLE IF NOT EXISTS p2_muestra_seguimiento (
  diagnostico_id TEXT NOT NULL REFERENCES p2_diagnosticos(id),
  cliente_id TEXT NOT NULL REFERENCES pmo_clientes(id),
  estado TEXT NOT NULL CHECK (estado IN ('Seleccionado','Convocado','En seguimiento','No participará')),
  canal TEXT NOT NULL DEFAULT '',
  fecha_contacto TEXT NOT NULL DEFAULT '',
  fecha_proxima TEXT NOT NULL DEFAULT '',
  responsable TEXT NOT NULL DEFAULT '',
  observaciones TEXT NOT NULL DEFAULT '',
  registrado_por TEXT NOT NULL,
  justificacion TEXT NOT NULL,
  actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(diagnostico_id,cliente_id)
);
CREATE INDEX IF NOT EXISTS idx_p2_muestra_estado ON p2_muestra_seguimiento(diagnostico_id,estado);
'''


def ensure_schema(path: Path | None = None) -> None:
    with closing(connect(path)) as con:
        exists = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='p2_muestra_seguimiento'").fetchone()
    if not exists:
        backup_clients_database(path)
    with transaction(path) as con:
        # SQLite executescript commits its enclosing transaction, as in earlier
        # migrations; DDL here is idempotent and introduces no changes to old tables.
        con.executescript(SCHEMA)
        con.execute('INSERT OR IGNORE INTO schema_migrations(version) VALUES (34)')


def _day(value: str, label: str) -> str:
    value = str(value or '').strip()
    if value:
        try: date.fromisoformat(value)
        except ValueError as exc: raise ValidationError(f'{label}: use AAAA-MM-DD.') from exc
    return value


def _clean(text: str, label: str, limit: int, *, multiline: bool = False) -> str:
    value = str(text or '').strip()
    if len(value) > limit or '\x00' in value or (not multiline and any(c in value for c in '\r\n')):
        raise ValidationError(f'{label}: máximo {limit} caracteres y sin saltos de línea.')
    return value


def _normalize(record: Mapping) -> dict:
    state = str(record.get('estado') or '').strip()
    if state not in STATES: raise ValidationError('Estado de seguimiento no permitido.')
    channel = _clean(record.get('canal'), 'Canal', 40)
    if channel not in CHANNELS: raise ValidationError('Canal de contacto no permitido.')
    return {'cliente_id': str(record.get('cliente_id') or '').strip(), 'estado': state,
            'canal': channel,
            'fecha_contacto': _day(record.get('fecha_contacto'), 'Fecha de contacto'),
            'fecha_proxima': _day(record.get('fecha_proxima'), 'Próximo seguimiento'),
            'responsable': _clean(record.get('responsable'), 'Responsable', 150),
            'observaciones': _clean(record.get('observaciones'), 'Observaciones', 1200, multiline=True)}


def save_records(diagnostic: str, records: list[dict], actor: str, reason: str,
                 *, overwrite: bool = False, path: Path | None = None) -> dict:
    """Valida todo antes del respaldo y ejecuta actualización masiva atómica."""
    actor = _clean(actor, 'Responsable de registro', 150)
    reason = _clean(reason, 'Justificación de muestra', 1500, multiline=True)
    if not actor: raise ValidationError('Indique quién registra la muestra.')
    if len(reason) < 8: raise ValidationError('Justifique los criterios de selección (mínimo 8 caracteres).')
    if not 1 <= len(records) <= 2000: raise ValidationError('Seleccione entre 1 y 2.000 clientes.')
    cleaned = [_normalize(rec) for rec in records]
    ids = [rec['cliente_id'] for rec in cleaned]
    if not all(ids) or len(set(ids)) != len(ids):
        raise ValidationError('Los clientes deben existir y no repetirse en la operación.')
    ensure_schema(path)
    with closing(connect(path)) as con:
        if not con.execute('SELECT 1 FROM p2_diagnosticos WHERE id=?', (diagnostic,)).fetchone():
            raise ValidationError('Diagnóstico inexistente.')
        # Consultar todo el directorio evita el límite de parámetros SQL en lotes grandes.
        clients = {r['id']:dict(r) for r in con.execute(
            'SELECT id,codigo,activo FROM pmo_clientes')}
        if any(ident not in clients or not clients[ident]['activo'] for ident in ids):
            raise ValidationError('La muestra solo admite clientes activos existentes.')
        old = {r['cliente_id']:dict(r) for r in con.execute(
            'SELECT * FROM p2_muestra_seguimiento WHERE diagnostico_id=?',(diagnostic,))}
    updates = []
    for rec in cleaned:
        before = old.get(rec['cliente_id'])
        # En una carga parcial, las columnas opcionales vacías no borran
        # contactos, responsables o evidencias administrativas existentes.
        # Se puede cambiar el estado sin volver a diligenciar los demás campos.
        if before:
            for field in ('canal', 'fecha_contacto', 'fecha_proxima',
                          'responsable', 'observaciones'):
                if not rec[field]:
                    rec[field] = before[field]
        if before and before['estado'] != rec['estado'] and not overwrite:
            raise ValidationError('Se detectó una reasignación de estado. Marque permitir actualización.')
        if before and all(before[k] == rec[k] for k in rec if k!='cliente_id'):
            continue
        updates.append((rec, before))
    if not updates:
        return {'selected':len(records), 'changed':0, 'unchanged':len(records), 'backup':None}
    backup = backup_clients_database(path)
    with transaction(path) as con:
        for rec, before in updates:
            con.execute('''INSERT INTO p2_muestra_seguimiento
              (diagnostico_id,cliente_id,estado,canal,fecha_contacto,fecha_proxima,
               responsable,observaciones,registrado_por,justificacion)
              VALUES (?,?,?,?,?,?,?,?,?,?)
              ON CONFLICT(diagnostico_id,cliente_id) DO UPDATE SET
               estado=excluded.estado,canal=excluded.canal,
               fecha_contacto=excluded.fecha_contacto,fecha_proxima=excluded.fecha_proxima,
               responsable=excluded.responsable,observaciones=excluded.observaciones,
               registrado_por=excluded.registrado_por,justificacion=excluded.justificacion,
               actualizado_en=CURRENT_TIMESTAMP''',
              (diagnostic,rec['cliente_id'],rec['estado'],rec['canal'],
               rec['fecha_contacto'],rec['fecha_proxima'],rec['responsable'],
               rec['observaciones'],actor,reason))
            con.execute('''INSERT INTO pmo_auditoria
              (entidad,entidad_id,accion,actor,antes_json,despues_json)
              VALUES (?,?,?,?,?,?)''',
              ('p2_muestra',rec['cliente_id'],'registro_muestra',actor,
               json.dumps(before,ensure_ascii=False,default=str) if before else None,
               json.dumps({'diagnostico':diagnostic,**rec,'criterio':reason},ensure_ascii=False)))
    return {'selected':len(records),'changed':len(updates),
            'unchanged':len(records)-len(updates),'backup':str(backup)}


def sample_rows(diagnostic: str, path: Path | None = None) -> list[dict]:
    ensure_schema(path)
    response = {x['id']:x for x in readiness(diagnostic,path)['rows']}
    people = list_clients(path=path)
    with closing(connect(path)) as con:
        tracked = {r['cliente_id']:dict(r) for r in con.execute(
            'SELECT * FROM p2_muestra_seguimiento WHERE diagnostico_id=?',(diagnostic,))}
    rows=[]
    for p in people:
        ident=p['id']; answers=response[ident]; followup=tracked.get(ident,{})
        rows.append({'cliente_id':ident,'codigo':p['codigo'],'nombre':p['nombre'],
            'dependencia':p['dependencia'],'equipo':p.get('equipo_trabajo') or '',
            'grupo':answers['grupo'],'activo':bool(p['activo']),
            'estado_muestra':followup.get('estado') or 'Sin seleccionar',
            'estado_respuesta':answers['estado'], 'prioridades':answers['prioridades'],
            'canal':followup.get('canal') or '',
            'fecha_contacto':followup.get('fecha_contacto') or '',
            'fecha_proxima':followup.get('fecha_proxima') or '',
            'responsable':followup.get('responsable') or '',
            'observaciones':followup.get('observaciones') or '',
            'actualizado_en':followup.get('actualizado_en') or ''})
    return rows


def summary(diagnostic: str, path: Path | None = None) -> dict:
    rows=sample_rows(diagnostic,path)
    targets=[r for r in rows if r['activo'] and r['estado_muestra'] in ACTIVE_STATES]
    complete=[r for r in targets if r['estado_respuesta']=='Completa']
    awaiting=[r for r in targets if r['estado_respuesta'] != 'Completa']
    outside=[r for r in rows if r['activo'] and r['prioridades']
             and r['estado_muestra'] not in ACTIVE_STATES]
    pending_group=[r for r in targets if not r['grupo']]
    today=date.today().isoformat()
    overdue=[r for r in targets if r['fecha_proxima'] and r['fecha_proxima']<today
             and r['estado_respuesta']!='Completa']
    by_group={}
    for r in targets:
        group=r['grupo'] or 'Sin grupo'
        item=by_group.setdefault(group,{'seleccionados':0,'completos':0})
        item['seleccionados']+=1
        if r['estado_respuesta']=='Completa':item['completos']+=1
    return {'rows':rows,'selected':len(targets),'complete':len(complete),
            'pending':len(awaiting),'unclassified':len(pending_group),
            'outside_answers':len(outside),'outside_codes':[r['codigo'] for r in outside],
            'overdue':len(overdue),'excluded':sum(r['estado_muestra']=='No participará' for r in rows),
            'by_group':by_group,'status_counts':dict(Counter(r['estado_muestra'] for r in rows)),
            'sample_defined':any(r['estado_muestra']!='Sin seleccionar' for r in rows)}


def template_csv(diagnostic: str, path:Path|None=None) -> bytes:
    out=io.StringIO(); writer=csv.writer(out)
    writer.writerow(['codigo','estado','canal','fecha_contacto','fecha_proxima','responsable','observaciones'])
    def safe(s):
        value=str(s or '')
        return "'"+value if value.startswith(('=','+','-','@')) else value
    for r in sample_rows(diagnostic,path):
        if r['activo']:
            writer.writerow([safe(r['codigo']),r['estado_muestra'] if r['estado_muestra']!='Sin seleccionar' else '',
                r['canal'],r['fecha_contacto'],r['fecha_proxima'],safe(r['responsable']),safe(r['observaciones'])])
    return out.getvalue().encode('utf-8-sig')


def preview_csv(data:bytes, path:Path|None=None) -> dict:
    if not data or len(data)>1_000_000:raise ValidationError('El CSV debe tener entre 1 byte y 1 MB.')
    try: content=data.decode('utf-8-sig')
    except UnicodeDecodeError as exc:raise ValidationError('CSV en UTF-8 requerido.') from exc
    try:
        rdr=csv.DictReader(io.StringIO(content))
        required={'codigo','estado'}
        if not rdr.fieldnames or not required.issubset(set(rdr.fieldnames)):
            raise ValidationError('CSV debe tener columnas codigo y estado.')
        raw=list(rdr)
    except csv.Error as exc:raise ValidationError('El CSV no se pudo leer.') from exc
    if len(raw)>2000:raise ValidationError('Máximo 2.000 filas.')
    clients={str(x['codigo']).upper():x for x in list_clients(path=path)}
    records=[]; issues=[]; preview=[]; seen=set()
    for ix,entry in enumerate(raw,2):
        code=str(entry.get('codigo') or '').strip().lstrip("'").upper()
        status=str(entry.get('estado') or '').strip()
        if not code and not status:continue
        if not status:
            preview.append({'Fila':ix,'Código':code,'Estado':'Omitido (sin estado)'})
            continue
        reason=''
        if not code:reason='Falta código'
        elif code in seen:reason='Código repetido'
        elif code not in clients:reason='Código inexistente'
        elif not clients[code]['activo']:reason='Cliente inactivo'
        elif status not in STATES:reason='Estado inválido'
        seen.add(code)
        if not reason:
            try:
                rec=_normalize({'cliente_id':clients[code]['id'],'estado':status,
                    'canal':entry.get('canal'),'fecha_contacto':entry.get('fecha_contacto'),
                    'fecha_proxima':entry.get('fecha_proxima'),'responsable':entry.get('responsable'),
                    'observaciones':entry.get('observaciones')})
                records.append(rec)
            except ValidationError as exc:reason=str(exc)
        if reason:issues.append(f'Fila {ix}: {reason}')
        preview.append({'Fila':ix,'Código':code,'Estado':status,'Validación':reason or 'Correcto'})
    if not records and not issues:issues.append('No hay estados para importar.')
    return {'records':records,'issues':issues,'preview':preview}
