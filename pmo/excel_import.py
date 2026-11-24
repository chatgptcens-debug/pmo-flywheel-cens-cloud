"""Importación local y segura de plantillas .xlsx del Paso 1.

Ejecuta la misma transacción en modo vista previa (ROLLBACK) o aplicación
(COMMIT). No necesita bibliotecas adicionales para leer Excel.
"""
from __future__ import annotations

import hashlib
import json
import posixpath
import re
import sqlite3
import uuid
import zipfile
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET

from .clients import ValidationError, FIELDS, normalize, _department
from .storage import connect

MAX_FILE = 8_000_000
MAX_SHEET_ROWS = 2000
MAX_TOTAL_ROWS = 6000
MAX_XML_BYTES = 20_000_000

SHEETS: dict[str, tuple[str, ...]] = {
    'Clientes': FIELDS,
    'Eventos': ('codigo_excel', 'titulo', 'tipo', 'fecha', 'publico', 'modalidad', 'responsable', 'estado'),
    'Campanas': ('codigo_excel', 'titulo', 'audiencia', 'canal', 'fecha_inicio', 'estado', 'responsable'),
    'Biblioteca': ('codigo_excel', 'titulo', 'categoria', 'descripcion', 'url', 'tipo', 'estado', 'responsable'),
    'Consultas': ('codigo_excel', 'codigo_cliente', 'asunto', 'categoria', 'descripcion', 'responsable', 'estado', 'respuesta'),
    'Asistencias': ('codigo_cliente', 'codigo_evento', 'titulo_evento', 'fecha_evento', 'asistio'),
    'Encuestas': ('codigo_excel', 'codigo_cliente', 'codigo_evento', 'titulo_evento', 'fecha_evento',
                 'fase', 'familiaridad', 'proposito', 'servicios', 'utilidad', 'interes', 'responsable'),
}
ORDER = tuple(SHEETS)
N = {'x': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
     'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
     'p': 'http://schemas.openxmlformats.org/package/2006/relationships'}


def _needed_text(row: dict, key: str) -> str:
    v = _text(row.get(key))
    if not v:
        raise ValidationError(f'Falta {key}.')
    if len(v) > 2000:
        raise ValidationError(f'{key}: texto demasiado largo (máximo 2.000 caracteres).')
    return v


def _text(value) -> str:
    if value is None:
        return ''
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _date(value) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (int, float)) and 1 <= value <= 100_000:
        return (date(1899, 12, 30) + timedelta(days=int(value))).isoformat()
    txt = _text(value)
    try:
        return date.fromisoformat(txt[:10]).isoformat() if len(txt) >= 10 else date.fromisoformat(txt).isoformat()
    except ValueError as exc:
        raise ValidationError(f'Fecha no válida «{txt}». Use AAAA-MM-DD.') from exc


def _bool(value, name: str, default: bool = False) -> int:
    txt = _text(value).casefold()
    if not txt:
        return int(default)
    if txt in ('sí', 'si', '1', 'verdadero', 'true', 'x', 'activo'):
        return 1
    if txt in ('no', '0', 'falso', 'false', 'inactivo'):
        return 0
    raise ValidationError(f'{name}: indique Sí o No.')


def _score(value, key: str) -> int:
    txt = _text(value)
    if txt not in ('1', '2', '3', '4', '5'):
        raise ValidationError(f'{key}: valor entero obligatorio entre 1 y 5.')
    return int(txt)


def _value(cell, shared: list[str]) -> object:
    if cell.find('x:f', N) is not None:
        raise ValidationError('El Excel contiene fórmulas. Pegue los resultados como valores.')
    typ = cell.attrib.get('t')
    if typ == 'inlineStr':
        return ''.join(t.text or '' for t in cell.findall('.//x:t', N))
    val = cell.find('x:v', N)
    if val is None:
        return ''
    txt = val.text or ''
    if typ == 's':
        try:
            return shared[int(txt)]
        except (ValueError, IndexError) as exc:
            raise ValidationError('Índice de texto compartido inválido en Excel.') from exc
    if typ in ('str', 'e', 'd'):
        return txt
    if typ == 'b':
        return int(txt) == 1
    try:
        f = float(txt)
        return int(f) if f.is_integer() else f
    except ValueError:
        return txt


def _column_index(ref: str) -> int:
    letters = re.match(r'[A-Z]+', ref.upper())
    if not letters:
        raise ValidationError('Celda de Excel con referencia inválida.')
    x = 0
    for c in letters.group():
        x = x * 26 + ord(c) - 64
    return x - 1


def _safe_member(z: zipfile.ZipFile, path: str) -> bytes:
    p = posixpath.normpath(path.lstrip('/'))
    if p.startswith('../') or p not in z.namelist():
        raise ValidationError('El archivo Excel tiene una estructura incompatible.')
    member = z.getinfo(p)
    if member.file_size > MAX_XML_BYTES:
        raise ValidationError('El Excel tiene una sección excesivamente grande.')
    return z.read(p)


def parse_xlsx(data: bytes) -> dict[str, list[tuple[int, dict]]]:
    if not data or len(data) > MAX_FILE:
        raise ValidationError('Adjunte un archivo .xlsx de máximo 8 MB.')
    if not zipfile.is_zipfile(BytesIO(data)):
        raise ValidationError('El archivo no es un Excel .xlsx válido.')
    result = {k: [] for k in ORDER}
    with zipfile.ZipFile(BytesIO(data)) as z:
        if len(z.infolist()) > 600 or sum(i.file_size for i in z.infolist()) > 55_000_000:
            raise ValidationError('El Excel supera el tamaño de procesamiento permitido.')
        if any(i.filename.endswith('vbaProject.bin') for i in z.infolist()):
            raise ValidationError('No se admiten archivos con macros.')
        try:
            book = ET.fromstring(_safe_member(z, 'xl/workbook.xml'))
            rels = ET.fromstring(_safe_member(z, 'xl/_rels/workbook.xml.rels'))
        except ET.ParseError as exc:
            raise ValidationError('No se pudo interpretar la estructura del Excel.') from exc
        relation_map = {e.get('Id'): e.get('Target') for e in rels}
        shared = []
        if 'xl/sharedStrings.xml' in z.namelist():
            root = ET.fromstring(_safe_member(z, 'xl/sharedStrings.xml'))
            shared = [''.join(t.text or '' for t in si.findall('.//x:t', N)) for si in root.findall('x:si', N)]
        used = 0
        for item in book.findall('x:sheets/x:sheet', N):
            name = item.get('name', '')
            if name not in SHEETS:
                continue
            relid = item.get(f'{{{N["r"]}}}id')
            target = relation_map.get(relid, '')
            if not target:
                raise ValidationError(f'Hoja {name}: referencia interna no disponible.')
            member_path = (target.lstrip('/') if target.startswith('/')
                           else posixpath.normpath(posixpath.join('xl', target)))
            root = ET.fromstring(_safe_member(z, member_path))
            raw_rows = []
            for row in root.findall('.//x:sheetData/x:row', N):
                nr = int(row.attrib.get('r') or len(raw_rows) + 1)
                columns = {}
                for cell in row.findall('x:c', N):
                    ix = _column_index(cell.attrib.get('r', ''))
                    if ix > 80:
                        continue
                    columns[ix] = _value(cell, shared)
                raw_rows.append((nr, columns))
            if not raw_rows:
                continue
            headings = {idx: _text(val).strip().lower() for idx, val in raw_rows[0][1].items()}
            allowed = set(SHEETS[name])
            if not (set(headings.values()) & allowed):
                raise ValidationError(f'Hoja {name}: encabezados no reconocidos. Utilice la plantilla oficial.')
            unknown = set(headings.values()) - allowed - {''}
            if unknown:
                raise ValidationError(f'Hoja {name}: columnas desconocidas: {", ".join(sorted(unknown))}.')
            if len(set(headings.values()) - {''}) != len([v for v in headings.values() if v]):
                raise ValidationError(f'Hoja {name}: encabezados repetidos.')
            for number, cols in raw_rows[1:]:
                row = {headings[ix]: val for ix, val in cols.items() if headings.get(ix) and _text(val)}
                if row:
                    result[name].append((number, row))
                    used += 1
                if len(result[name]) > MAX_SHEET_ROWS or used > MAX_TOTAL_ROWS:
                    raise ValidationError('El Excel contiene demasiados registros para una sola carga.')
    if not any(result.values()):
        raise ValidationError('No se encontraron registros en las hojas reconocidas.')
    return result


def _audit(con, ent, key, action, actor, detail=''):
    con.execute('INSERT INTO pmo_auditoria(entidad,entidad_id,accion,despues_json,actor) VALUES (?,?,?,?,?)',
                (ent, key, action, detail, actor))


def _external_code(row: dict, kind: str) -> str:
    explicit = _text(row.get('codigo_excel'))
    if explicit:
        if len(explicit) > 90:
            raise ValidationError('El código de Excel supera 90 caracteres.')
        return explicit.upper()
    canonical = json.dumps(row, sort_keys=True, ensure_ascii=False, default=str)
    return 'AUTO-' + hashlib.sha256((kind + canonical).encode()).hexdigest()[:24].upper()


def _ref(con, kind, code):
    return con.execute('SELECT objeto_id FROM p1_excel_referencias WHERE entidad=? AND codigo_excel=? COLLATE NOCASE',
                       (kind, code)).fetchone()


def _store_ref(con, kind, code, target):
    con.execute('INSERT INTO p1_excel_referencias(entidad,codigo_excel,objeto_id) VALUES (?,?,?)', (kind, code, target))


def _client(con, code):
    val = _text(code).upper()
    if not val:
        raise ValidationError('Falta codigo_cliente.')
    r = con.execute('SELECT id FROM pmo_clientes WHERE codigo=? COLLATE NOCASE', (val,)).fetchone()
    if r is None:
        raise ValidationError(f'Cliente «{val}» no encontrado. Importe primero su registro en Clientes.')
    return r['id']


def _event(con, row):
    key = _text(row.get('codigo_evento'))
    if key:
        ref = _ref(con, 'Eventos', key.upper())
        if ref:
            return ref['objeto_id']
        raw = con.execute('SELECT id FROM p1_eventos WHERE id=?', (key,)).fetchone()
        if raw:
            return raw['id']
    title = _text(row.get('titulo_evento'))
    when = row.get('fecha_evento')
    if title and when:
        matches = con.execute('SELECT id FROM p1_eventos WHERE titulo=? COLLATE NOCASE AND fecha=?',
                              (title, _date(when))).fetchall()
        if len(matches) == 1:
            return matches[0]['id']
        if len(matches) > 1:
            raise ValidationError('Varios eventos coinciden en título y fecha. Indique codigo_evento.')
    raise ValidationError('Evento no encontrado. Use codigo_evento de Eventos o título y fecha exactos.')


def _insert(con, kind: str, row: dict, actor: str) -> tuple[str, str]:
    """Devuelve (acción, detalle); acción: Nuevo, Duplicado, Actualizado."""
    key = uuid.uuid4().hex
    if kind == 'Clientes':
        code = _needed_text(row, 'codigo').upper()
        if con.execute('SELECT id FROM pmo_clientes WHERE codigo=? COLLATE NOCASE', (code,)).fetchone():
            return 'Duplicado', f'Código {code} ya registrado (no se sobrescribe).'
        email = _text(row.get('correo')).lower()
        if email and con.execute('SELECT id FROM pmo_clientes WHERE correo=? COLLATE NOCASE', (email,)).fetchone():
            raise ValidationError('El correo ya pertenece a otro cliente.')
        payload = dict(row)
        for field in ('embajador', 'activo'):
            if field in payload:
                payload[field] = _bool(payload[field], field, default=(field == 'activo'))
        for field in ('primer_contacto',):
            if payload.get(field):
                payload[field] = _date(payload[field])
        if payload.get('conocimiento') not in ('', None):
            payload['conocimiento'] = _score(payload['conocimiento'], 'conocimiento')
        clean = normalize(payload)
        dep = _department(con, clean.pop('dependencia'))
        cols = [*clean, 'id', 'dependencia_id']
        con.execute(f'INSERT INTO pmo_clientes({",".join(cols)}) VALUES ({",".join("?" for _ in cols)})',
                    [*clean.values(), key, dep])
        _audit(con, 'cliente', key, 'importar_excel', actor, json.dumps({'codigo': code, 'nombre': clean['nombre']}, ensure_ascii=False))
        return 'Nuevo', code

    if kind == 'Eventos':
        title = _needed_text(row, 'titulo')
        date_text = _date(row.get('fecha'))
        owner = _needed_text(row, 'responsable')
        status = _text(row.get('estado')) or 'Programado'
        if status not in ('Borrador', 'Programado', 'Realizado', 'Cancelado'):
            raise ValidationError('Estado de evento inválido.')
        existing = con.execute('SELECT id FROM p1_eventos WHERE titulo=? COLLATE NOCASE AND fecha=?',
                               (title, date_text)).fetchall()
        if len(existing) > 1:
            raise ValidationError('Hay eventos con el mismo título y fecha; revise manualmente.')
        ext = _external_code(row, kind)
        mapped = _ref(con, kind, ext)
        if mapped:
            return 'Duplicado', f'Código {ext} ya importado.'
        if existing:
            _store_ref(con, kind, ext, existing[0]['id'])
            return 'Duplicado', 'Evento existente por título y fecha (sin cambios).'
        con.execute('INSERT INTO p1_eventos(id,titulo,tipo,fecha,publico,modalidad,responsable,estado) VALUES (?,?,?,?,?,?,?,?)',
                    (key, title, _needed_text(row, 'tipo'), date_text, _text(row.get('publico')),
                     _text(row.get('modalidad')), owner, status))
    elif kind == 'Campanas':
        title = _needed_text(row, 'titulo')
        start = _date(row.get('fecha_inicio'))
        owner = _needed_text(row, 'responsable')
        status = _text(row.get('estado')) or 'Borrador'
        if status not in ('Borrador', 'Programada', 'En ejecución', 'Finalizada', 'Cancelada'):
            raise ValidationError('Estado de campaña inválido.')
        ext = _external_code(row, kind)
        if _ref(con, kind, ext):
            return 'Duplicado', f'Código {ext} ya importado.'
        if con.execute('SELECT id FROM p1_campanas WHERE titulo=? COLLATE NOCASE AND fecha_inicio=?', (title,start)).fetchone():
            return 'Duplicado', 'La campaña ya existe con ese nombre y fecha.'
        con.execute('INSERT INTO p1_campanas(id,titulo,audiencia,canal,fecha_inicio,estado,responsable) VALUES (?,?,?,?,?,?,?)',
                    (key,title,_text(row.get('audiencia')),_text(row.get('canal')),start,status,owner))
    elif kind == 'Biblioteca':
        title = _needed_text(row, 'titulo')
        category = _needed_text(row, 'categoria')
        typ = _text(row.get('tipo')) or 'Material'
        status = _text(row.get('estado')) or 'Borrador'
        owner = _needed_text(row, 'responsable')
        if typ not in ('Material','Servicio','Historia'):
            raise ValidationError('El tipo debe ser Material, Servicio o Historia.')
        if status not in ('Borrador','Publicado','En diseño','Piloto','Disponible','Suspendido'):
            raise ValidationError('Estado de recurso inválido.')
        url = _text(row.get('url'))
        if url and not re.fullmatch(r'https?://[^\s/?#]+[^\s]*', url, flags=re.I):
            raise ValidationError('El recurso requiere una URL http:// o https:// válida.')
        ext = _external_code(row, kind)
        if _ref(con, kind, ext):
            return 'Duplicado', 'Recurso ya importado.'
        if con.execute('SELECT id FROM p1_recursos WHERE titulo=? COLLATE NOCASE AND categoria=? COLLATE NOCASE AND tipo=?',
                       (title,category,typ)).fetchone():
            return 'Duplicado', 'Ficha de biblioteca ya registrada.'
        con.execute('INSERT INTO p1_recursos(id,titulo,categoria,descripcion,url,tipo,estado,responsable) VALUES (?,?,?,?,?,?,?,?)',
                    (key,title,category,_text(row.get('descripcion')),url,typ,status,owner))
    elif kind == 'Consultas':
        cid = _client(con, row.get('codigo_cliente'))
        title = _needed_text(row, 'asunto')
        description = _needed_text(row, 'descripcion')
        status = _text(row.get('estado')) or 'Recibida'
        response = _text(row.get('respuesta'))
        if status not in ('Recibida', 'En análisis', 'En gestión', 'Respondida', 'Cerrada'):
            raise ValidationError('Estado de consulta inválido.')
        if status in ('Respondida', 'Cerrada') and not response:
            raise ValidationError('Una consulta respondida o cerrada requiere respuesta.')
        ext = _external_code(row, kind)
        if _ref(con, kind, ext):
            return 'Duplicado', 'Consulta ya importada.'
        con.execute('''INSERT INTO p1_consultas(id,cliente_id,asunto,categoria,descripcion,responsable,estado,respuesta,respondido_en)
                    VALUES (?,?,?,?,?,?,?,?,CASE WHEN ? IN ('Respondida','Cerrada') THEN CURRENT_TIMESTAMP ELSE NULL END)''',
                    (key,cid,title,_needed_text(row, 'categoria'),description,_text(row.get('responsable')),status,response,status))
    elif kind == 'Asistencias':
        cid = _client(con, row.get('codigo_cliente'))
        eid = _event(con, row)
        if con.execute("SELECT 1 FROM p1_eventos WHERE id=? AND estado='Cancelado'", (eid,)).fetchone():
            raise ValidationError('No se puede asociar asistencia a un evento cancelado.')
        attended = _bool(_needed_text(row, 'asistio'), 'asistio')
        existing = con.execute('SELECT asistio FROM p1_asistencias WHERE evento_id=? AND cliente_id=?',(eid,cid)).fetchone()
        if existing and existing['asistio'] == attended:
            return 'Duplicado', 'El estado de asistencia ya estaba registrado.'
        con.execute('''INSERT INTO p1_asistencias(evento_id,cliente_id,asistio) VALUES (?,?,?)
                      ON CONFLICT(evento_id,cliente_id) DO UPDATE SET asistio=excluded.asistio''', (eid,cid,attended))
        _audit(con, 'asistencia', eid, 'actualizar_excel' if existing else 'importar_excel', actor,
               json.dumps({'cliente_id':cid,'asistio':attended}))
        return ('Actualizado' if existing else 'Nuevo'), f'Cliente y evento vinculados · asistencia {"Sí" if attended else "No"}.'
    elif kind == 'Encuestas':
        cid = _client(con, row.get('codigo_cliente'))
        eid = _event(con, row) if row.get('codigo_evento') or row.get('titulo_evento') else None
        phase = _needed_text(row, 'fase')
        if phase not in ('Antes', 'Después'):
            raise ValidationError('Fase debe ser Antes o Después.')
        scores = [_score(row.get(v), v) for v in ('familiaridad', 'proposito','servicios','utilidad','interes')]
        owner = _needed_text(row, 'responsable')
        ext = _external_code(row, kind)
        if _ref(con, kind, ext):
            return 'Duplicado', 'Encuesta ya importada.'
        con.execute('''INSERT INTO p1_encuestas(id,cliente_id,evento_id,fase,familiaridad,proposito,servicios,utilidad,interes,responsable)
                      VALUES(?,?,?,?,?,?,?,?,?,?)''', (key,cid,eid,phase,*scores,owner))
    else:
        raise ValidationError('Sección de Excel no reconocida.')
    _store_ref(con, kind, ext, key)
    _audit(con, kind.lower(), key, 'importar_excel', actor)
    return 'Nuevo', 'Registro guardado con referencia y auditoría.'


def _execute(con, parsed: dict, actor: str) -> list[dict]:
    entries = []
    for sheet in ORDER:
        for row_num, fields in parsed[sheet]:
            savepoint = 'import_item'
            con.execute(f'SAVEPOINT {savepoint}')
            try:
                action, message = _insert(con, sheet, fields, actor)
                con.execute(f'RELEASE SAVEPOINT {savepoint}')
            except (ValidationError, sqlite3.IntegrityError, ValueError, OverflowError) as exc:
                con.execute(f'ROLLBACK TO SAVEPOINT {savepoint}')
                con.execute(f'RELEASE SAVEPOINT {savepoint}')
                action, message = 'Error', str(exc)
            entries.append({'Hoja':sheet, 'Fila':row_num, 'Acción':action, 'Detalle':message})
    return entries


def import_xlsx(data: bytes, actor: str, path: Path | None = None, *, confirm: bool = False) -> list[dict]:
    actor = _text(actor)
    if not actor:
        raise ValidationError('Indique quién realiza la carga.')
    try:
        parsed = parse_xlsx(data)
    except (ET.ParseError, zipfile.BadZipFile, UnicodeDecodeError, KeyError) as exc:
        raise ValidationError("El archivo Excel está dañado o tiene una estructura incompatible.") from exc
    con = connect(path)
    try:
        con.execute('BEGIN IMMEDIATE')
        entries = _execute(con, parsed, actor)
        errors = [x for x in entries if x['Acción'] == 'Error']
        if confirm and not errors:
            con.execute('INSERT INTO p1_excel_cargas(id,huella_sha256,actor,resumen) VALUES (?,?,?,?)',
                        (uuid.uuid4().hex,hashlib.sha256(data).hexdigest(),actor,json.dumps(entries,ensure_ascii=False)))
            con.commit()
        else:
            con.rollback()
        return entries
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
