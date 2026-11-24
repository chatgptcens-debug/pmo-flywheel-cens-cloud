"""Referencias visibles persistentes y filtrado de necesidades del Paso 02.

Los UUID continúan siendo llaves internas. La tabla aditiva asocia un consecutivo
por diagnóstico con cada necesidad, sin tocar cálculos V5 ni fuentes PMOGA.
"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
import sqlite3
from .storage import connect, transaction
from .config import database_path

_SCHEMA = """CREATE TABLE IF NOT EXISTS p2_necesidades_codigos (
  necesidad_id TEXT PRIMARY KEY REFERENCES p2_necesidades(id),
  diagnostico_id TEXT NOT NULL REFERENCES p2_diagnosticos(id),
  numero INTEGER NOT NULL CHECK(numero >= 1),
  UNIQUE(diagnostico_id, numero)
)"""


def _backup(db: Path) -> Path:
    directory = db.parent / 'respaldos'
    directory.mkdir(parents=True, exist_ok=True)
    dest = directory / f'necesidades_antes_codigos_{datetime.now():%Y%m%d_%H%M%S_%f}.sqlite3'
    with sqlite3.connect(str(db)) as source, sqlite3.connect(str(dest)) as target:
        source.backup(target)
    return dest


def public_codes(diagnostic_id: str, *, path: Path | None = None) -> dict[str, str]:
    """Inicialización idempotente y segura de códigos NEC-0001 por expediente.

    La primera asignación sobre necesidades existentes requiere respaldo previo.
    Al agregar registros, el máximo consecutivo nunca se reutiliza.
    """
    db = Path(path) if path is not None else database_path()
    with connect(db) as con:
        exists = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='p2_necesidades_codigos'").fetchone()
        pending = con.execute('''SELECT n.id FROM p2_necesidades n
            LEFT JOIN p2_necesidades_codigos c ON c.necesidad_id=n.id
            WHERE n.diagnostico_id=? AND c.necesidad_id IS NULL
            ORDER BY n.creado_en ASC,n.rowid ASC''', (diagnostic_id,)).fetchall() if exists else con.execute(
            'SELECT id FROM p2_necesidades WHERE diagnostico_id=? ORDER BY creado_en ASC,rowid ASC',
            (diagnostic_id,)).fetchall()
    if pending:
        _backup(db)
    with transaction(db) as con:
        con.execute(_SCHEMA)
        number = con.execute('SELECT COALESCE(MAX(numero),0) FROM p2_necesidades_codigos WHERE diagnostico_id=?',
                             (diagnostic_id,)).fetchone()[0]
        remaining = con.execute('''SELECT n.id FROM p2_necesidades n
            LEFT JOIN p2_necesidades_codigos c ON c.necesidad_id=n.id
            WHERE n.diagnostico_id=? AND c.necesidad_id IS NULL
            ORDER BY n.creado_en ASC,n.rowid ASC''', (diagnostic_id,)).fetchall()
        for row in remaining:
            number += 1
            con.execute('INSERT INTO p2_necesidades_codigos(necesidad_id,diagnostico_id,numero) VALUES (?,?,?)',
                        (row['id'], diagnostic_id, number))
        mapping = con.execute('SELECT necesidad_id,numero FROM p2_necesidades_codigos WHERE diagnostico_id=?',
                              (diagnostic_id,)).fetchall()
    return {row['necesidad_id']: f"NEC-{row['numero']:04d}" for row in mapping}


def filter_needs(entries: list[dict], *, status: str = 'Todas',
                 department: str = 'Todas', segment: str = 'Todos',
                 result: int | str = -1, client: str = 'Todos', search: str = '') -> list[dict]:
    """Filtros de interfaz sin escritura o modificación de registros."""
    query = search.casefold().strip()
    selected = []
    for row in entries:
        if status not in ('Todas', None) and row['estado'] != status: continue
        if department != 'Todas' and row['dependencia'] != department: continue
        rgroup = row.get('segmento') or 'Sin segmento / cliente'
        if segment != 'Todos' and rgroup != segment: continue
        if result != -1 and (row.get('resultado_id') or 0) != result: continue
        if client != 'Todos' and (row.get('cliente_id') or '__general__') != client: continue
        if query:
            haystack = ' '.join(str(row.get(k) or '') for k in (
                'codigo_publico','problema','ganancia','dependencia','cliente','cliente_codigo','fuente'))
            if query not in haystack.casefold(): continue
        selected.append(row)
    return selected
