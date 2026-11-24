"""Importación transaccional de necesidades Pain–Gain del Paso 02 (V0.38.6).

NO es el importador de las 30 expectativas/5 prioridades. No modifica clientes,
ponderaciones, corridas ni estados de validación. Nuevos hallazgos quedan Registrada.
"""
from __future__ import annotations

import csv
import hashlib
import io
import sqlite3
import unicodedata
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from .clients import ValidationError, list_clients
from .config import database_path
from .step2 import OUTCOMES, audit, needs, required
from .storage import connect, transaction

FILE_LIMIT = 12_000_000
ROW_LIMIT = 2000
COLUMNS = (
    'Código cliente', 'Dependencia', 'Dificultad / punto crítico',
    'Resultado deseado / ganancia', 'Resultado esperado relacionado (1-30)',
    'Impacto declarado', 'Fuente / evidencia', 'Responsable'
)
REQUIRED = ('Dependencia', 'Dificultad / punto crítico', 'Resultado deseado / ganancia')


def _key(value: Any) -> str:
    text = ''.join(c for c in unicodedata.normalize('NFD', str(value or '').casefold().strip())
                   if unicodedata.category(c) != 'Mn')
    return ''.join(c for c in text if c.isalnum())


ALIASES = {
    'Código cliente': ('Codigo cliente', 'Cliente', 'Código CENS', 'Codigo CENS'),
    'Dependencia': ('Area', 'Área', 'Unidad', 'Dependencia CENS'),
    'Dificultad / punto crítico': ('Dificultad', 'Problema', 'Punto critico', 'Necesidad'),
    'Resultado deseado / ganancia': ('Resultado deseado', 'Ganancia', 'Beneficio deseado', 'Oportunidad'),
    'Resultado esperado relacionado (1-30)': ('Resultado esperado', 'Resultado id', 'Beneficio relacionado', 'Codigo beneficio'),
    'Impacto declarado': ('Impacto',),
    'Fuente / evidencia': ('Fuente', 'Evidencia', 'Referencia documental'),
    'Responsable': ('Actor', 'Registrado por'),
}


def _records(source: bytes, name: str) -> list[dict]:
    if not isinstance(source, bytes) or len(source) > FILE_LIMIT:
        raise ValidationError('Adjunte un archivo de necesidades de máximo 12 MB.')
    if name.lower().endswith('.csv'):
        try:
            content = source.decode('utf-8-sig')
        except UnicodeDecodeError as exc:
            raise ValidationError('Guarde el CSV en UTF-8.') from exc
        sample = content[:4096]
        delimiter = ';' if sample.count(';') > sample.count(',') else ','
        reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
        header = reader.fieldnames or []
        entries = [r for r in reader if any(str(v or '').strip() for v in r.values())]
    elif name.lower().endswith('.xlsx'):
        try:
            from openpyxl import load_workbook
            book = load_workbook(io.BytesIO(source), data_only=True, read_only=True)
            if 'Necesidades' not in book.sheetnames:
                raise ValidationError('El Excel debe contener la hoja «Necesidades». Descargue la plantilla.')
            sheet = book['Necesidades']
            iterator = sheet.iter_rows(values_only=True)
            header = list(next(iterator, None) or [])
            entries = [dict(zip([str(h or '') for h in header], row))
                       for row in iterator if any(v is not None and str(v).strip() for v in row)]
            book.close()
        except ValidationError:
            raise
        except Exception as exc:
            raise ValidationError('No fue posible leer el XLSX de necesidades.') from exc
    else:
        raise ValidationError('Adjunte Excel .xlsx o CSV .csv.')
    canonical = {}
    for field in COLUMNS:
        keys = {_key(field), *(_key(a) for a in ALIASES.get(field, ()))}
        matches = [i for i, heading in enumerate(header) if _key(heading) in keys]
        if len(matches) > 1:
            raise ValidationError(f'El archivo tiene columnas duplicadas para «{field}».')
        if matches:
            canonical[field] = str(header[matches[0]])
        elif field in REQUIRED:
            raise ValidationError(f'Falta la columna «{field}». Utilice la plantilla del aplicativo.')
    if not entries:
        raise ValidationError('La hoja «Necesidades» no contiene registros.')
    if len(entries) > ROW_LIMIT:
        raise ValidationError(f'Máximo {ROW_LIMIT} necesidades por carga.')
    return [{f: row.get(canonical[f]) if f in canonical else None for f in COLUMNS} for row in entries]


def _identity(row: dict) -> tuple:
    return (row.get('client_id', row.get('cliente_id')) or '', _key(row['dependencia']),
            _key(row['problema']), _key(row['ganancia']))


def _extras(row: dict) -> tuple:
    return (row['resultado_id'], row['impacto'], _key(row['fuente']))


def _existing(diag: str, path: Path | None = None) -> dict[tuple, list[dict]]:
    out: dict[tuple, list[dict]] = {}
    for r in needs(diag, path=path):
        out.setdefault(_identity(r), []).append(r)
    return out


def validate_import(source: bytes, name: str, diag: str, actor: str = '',
                    path: Path | None = None) -> list[dict]:
    """Vista previa con acción por fila. No modifica SQLite."""
    with connect(path) as con:
        if not con.execute('SELECT id FROM p2_diagnosticos WHERE id=?', (diag,)).fetchone():
            raise ValidationError('El diagnóstico activo no existe.')
    rows = _records(source, name)
    people = list_clients(path=path)
    by_code = {c['codigo'].casefold(): c for c in people}
    by_name: dict[str, list] = {}
    for c in people:
        by_name.setdefault(_key(c['nombre']), []).append(c)
    existing = _existing(diag, path)
    seen: set[tuple] = set()
    preview = []
    for line, raw in enumerate(rows, 2):
        view = {'Fila': line, 'Cliente': str(raw.get(COLUMNS[0]) or '').strip(),
                'Dependencia': str(raw.get(COLUMNS[1]) or '').strip(),
                'Dificultad': str(raw.get(COLUMNS[2]) or '').strip(),
                'Resultado deseado': str(raw.get(COLUMNS[3]) or '').strip(),
                'Acción': 'Error', 'Motivo': '', '_data': None}
        try:
            client = None
            typed_client = view['Cliente']
            if typed_client:
                client = by_code.get(typed_client.casefold())
                if client is None:
                    matches = by_name.get(_key(typed_client), [])
                    if len(matches) != 1:
                        raise ValidationError('Cliente inexistente o ambiguo: use el código del directorio del Paso 01.')
                    client = matches[0]
                if not client['activo']:
                    raise ValidationError('El cliente indicado está inactivo.')
            dept = view['Dependencia'] or (str(client['dependencia']).strip() if client else '')
            problem = required(view['Dificultad'], 'dificultad / punto crítico')
            gain = required(view['Resultado deseado'], 'resultado deseado / ganancia')
            dept = required(dept, 'dependencia')
            outcome_raw = raw.get(COLUMNS[4])
            outcome = None
            if outcome_raw is not None and str(outcome_raw).strip():
                try:
                    n = float(outcome_raw)
                    if not n.is_integer():
                        raise ValueError()
                    outcome = int(n)
                except (TypeError, ValueError) as exc:
                    raise ValidationError('El resultado relacionado debe ser un código entero entre 1 y 30.') from exc
                if outcome not in OUTCOMES:
                    raise ValidationError('El resultado relacionado debe estar entre 1 y 30.')
            impact_value = str(raw.get(COLUMNS[5]) or 'Sin evaluar').strip()
            variants = {_key(n): n for n in ('Sin evaluar', 'Bajo', 'Medio', 'Alto')}
            impact = variants.get(_key(impact_value))
            if impact is None:
                raise ValidationError('Impacto permitido: Sin evaluar, Bajo, Medio o Alto.')
            source_text = str(raw.get(COLUMNS[6]) or '').strip()
            owner = required(str(raw.get(COLUMNS[7]) or actor).strip(), 'responsable del hallazgo o de la carga')
            data = {'client_id': client['id'] if client else None, 'dependencia': dept,
                    'problema': problem, 'ganancia': gain, 'resultado_id': outcome,
                    'impacto': impact, 'fuente': source_text, 'actor': owner}
            ident = _identity(data)
            if ident in seen:
                raise ValidationError('Necesidad duplicada dentro del Excel.')
            seen.add(ident)
            prior = existing.get(ident, [])
            if prior:
                if len(prior) > 1 or _extras(prior[0]) != _extras(data):
                    raise ValidationError('Existe una necesidad similar con distintos atributos; revísela antes de importar.')
                action = 'Sin cambios'
            else:
                action = 'Nuevo'
            view.update({'Acción': action, '_data': data, 'Dependencia': dept,
                         'Código cliente': client['codigo'] if client else 'Institucional / sin cliente'})
        except ValidationError as exc:
            view['Motivo'] = str(exc)
        preview.append(view)
    return preview


def _backup(path: Path) -> Path:
    backups = path.parent / 'respaldos'
    backups.mkdir(parents=True, exist_ok=True)
    dest = backups / f'{path.stem}_antes_importar_necesidades_{datetime.now().strftime("%Y%m%d_%H%M%S_%f")}.sqlite3'
    with sqlite3.connect(str(path)) as source, sqlite3.connect(str(dest)) as target:
        source.backup(target)
    return dest


def import_needs(source: bytes, name: str, diag: str, actor: str, confirm: bool = False,
                 path: Path | None = None) -> dict:
    """Previsualiza o importa todo el archivo en una transacción. No edita existentes."""
    actor = required(actor, 'responsable de la carga')
    preview = validate_import(source, name, diag, actor, path)
    summary = dict(Counter(row['Acción'] for row in preview))
    if not confirm:
        return {'preview': preview, 'counts': summary, 'backup': None}
    if summary.get('Error'):
        raise ValidationError('Existen filas con errores. No se ha incorporado ninguna necesidad.')
    pending = [r['_data'] for r in preview if r['Acción'] == 'Nuevo']
    if not pending:
        return {'preview': preview, 'counts': summary, 'backup': None}
    db = Path(path) if path is not None else database_path()
    backup_path = _backup(db)
    with transaction(db) as con:
        if not con.execute('SELECT id FROM p2_diagnosticos WHERE id=?', (diag,)).fetchone():
            raise ValidationError('El diagnóstico ya no existe.')
        # Check de concurrencia y de contenido en la MISMA transacción antes de insertar.
        fresh = { _identity(dict(r)) for r in con.execute(
            'SELECT cliente_id AS client_id, dependencia, problema, ganancia FROM p2_necesidades WHERE diagnostico_id=?', (diag,)) }
        for data in pending:
            if _identity(data) in fresh:
                raise ValidationError('Otra carga modificó las necesidades. Vuelva a validar el Excel.')
            key = uuid.uuid4().hex
            con.execute('''INSERT INTO p2_necesidades
                (id,diagnostico_id,cliente_id,dependencia,problema,ganancia,resultado_id,impacto,fuente,actor)
                VALUES (?,?,?,?,?,?,?,?,?,?)''',
                (key, diag, data['client_id'], data['dependencia'], data['problema'],
                 data['ganancia'], data['resultado_id'], data['impacto'], data['fuente'], data['actor']))
            audit(con, 'p2_necesidad', key, 'importar_excel', actor,
                  {'diagnostico': diag, 'fuente': name, 'datos': data, 'estado': 'Registrada'})
            fresh.add(_identity(data))
        audit(con, 'p2_importacion_necesidades', uuid.uuid4().hex, 'cargar_lote', actor,
              {'diagnostico': diag, 'archivo': name,
               'sha256': hashlib.sha256(source).hexdigest(), 'nuevos': len(pending),
               'sin_cambios': summary.get('Sin cambios', 0)})
    return {'preview': preview, 'counts': summary, 'backup': backup_path}


def public_preview(preview: list[dict]) -> list[dict]:
    """Filas para Streamlit sin IDs internos ni estructuras auxiliares."""
    return [{key: value for key, value in row.items() if not key.startswith('_')}
            for row in preview]
