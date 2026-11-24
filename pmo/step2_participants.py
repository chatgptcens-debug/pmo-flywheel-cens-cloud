"""V0.33 · Segmentación controlada y ponderación de criterio experto para el Paso 02.

No modifica ni recalcula el motor de priorización V5. Los segmentos viven en el
maestro de clientes y las ponderaciones exactas se congelan en cada corrida.
"""
from __future__ import annotations

import csv
import io
import json
import re
from collections import Counter
from contextlib import closing
from pathlib import Path
from typing import Mapping

from . import step2 as p2
from .client_directory import backup_clients_database
from .clients import ValidationError, list_clients
from .v0391_clients import canonical_role, client_role
from .storage import connect, transaction


CRITERIA = ('Juicio experto documentado', 'Consenso de expertos',
            'AHP asistido y confirmado', 'Otro criterio experto')
SCHEMA = '''
CREATE TABLE IF NOT EXISTS p2_criterios_ponderacion (
  corrida_id TEXT PRIMARY KEY REFERENCES p2_corridas(id),
  diagnostico_id TEXT NOT NULL REFERENCES p2_diagnosticos(id),
  metodo TEXT NOT NULL,
  justificacion TEXT NOT NULL,
  pesos_json TEXT NOT NULL,
  responsable TEXT NOT NULL,
  creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_p2_criterios_diag
 ON p2_criterios_ponderacion(diagnostico_id,creado_en);
'''


def ensure_schema(path: Path | None = None) -> None:
    """Extensión aditiva; respaldar una base existente antes de la primera migración."""
    with closing(connect(path)) as con:
        existing = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='p2_criterios_ponderacion'").fetchone()
    if not existing:
        backup_clients_database(path)
    with transaction(path) as con:
        con.executescript(SCHEMA)
        # Explicit marker for cross-version checks; the change is additive.
        con.execute('INSERT OR IGNORE INTO schema_migrations(version) VALUES (33)')


def _segment(text: str) -> str:
    if not isinstance(text, str):
        raise ValidationError('El grupo de ponderación debe ser texto.')
    value = ' '.join(text.strip().split())
    if not value or len(value) > 100 or any(x in value for x in '<>\r\n'):
        raise ValidationError('Indique un grupo de 1 a 100 caracteres, sin saltos ni etiquetas HTML.')
    return value


def assign_segments(assignments: Mapping[str, str], actor: str, reason: str,
                    *, overwrite: bool = False, path: Path | None = None) -> dict:
    """Asignación masiva atómica con respaldo, preserva IDs y registros de otros pasos.

    La persona gestora decide el segmento: nunca se infiere por dependencia.
    """
    actor, reason = str(actor or '').strip(), str(reason or '').strip()
    if not actor or len(actor) > 150:
        raise ValidationError('Indique el responsable de la clasificación (máximo 150 caracteres).')
    if len(reason) < 8 or len(reason) > 1500:
        raise ValidationError('Documente el criterio de clasificación (8 a 1.500 caracteres).')
    if not assignments or len(assignments) > 2000:
        raise ValidationError('Seleccione entre 1 y 2.000 clientes.')
    cleaned = {str(ident): canonical_role(_segment(group)) for ident, group in assignments.items()}
    # Evitar grupos duplicados solo por mayúsculas o minúsculas.
    with closing(connect(path)) as con:
        existing = {str(row['segmento']).strip().casefold(): str(row['segmento']).strip()
                    for row in con.execute('SELECT DISTINCT segmento FROM pmo_clientes WHERE TRIM(segmento) != ?', ('',))}
    cleaned = {ident: existing.get(group.casefold(), group) for ident, group in cleaned.items()}
    if any(not ident.strip() for ident in cleaned):
        raise ValidationError('Los identificadores de clientes no pueden estar vacíos.')
    # Full validation before any write or backup.
    with closing(connect(path)) as con:
        current = {}
        for ident in cleaned:
            row = con.execute('SELECT id,codigo,segmento,activo FROM pmo_clientes WHERE id=?', (ident,)).fetchone()
            if not row:
                raise ValidationError('Cliente no encontrado o directorio desactualizado.')
            if not int(row['activo']):
                raise ValidationError('No se clasifican clientes archivados; reactive antes el registro.')
            before = str(row['segmento'] or '').strip()
            if before and before != cleaned[ident] and not overwrite:
                raise ValidationError(f"El cliente {row['codigo']} ya está clasificado como «{before}». Active sobrescritura explícita.")
            current[ident] = dict(row)
    changed = {ident: group for ident, group in cleaned.items()
               if (current[ident]['segmento'] or '').strip() != group}
    if not changed:
        return {'selected': len(cleaned), 'changed': 0, 'unchanged': len(cleaned), 'backup': None}
    backup = backup_clients_database(path)
    with transaction(path) as con:
        for ident, new_group in changed.items():
            before = current[ident]['segmento'] or ''
            con.execute('UPDATE pmo_clientes SET segmento=?,rol_especifico=?, actualizado_en=CURRENT_TIMESTAMP WHERE id=?', (new_group,new_group, ident))
            con.execute('''INSERT INTO pmo_auditoria(entidad,entidad_id,accion,antes_json,despues_json,actor)
                           VALUES (?,?,?,?,?,?)''',
                        ('cliente', ident, 'p2_segmentacion',
                         json.dumps({'segmento': before}, ensure_ascii=False),
                         json.dumps({'segmento': new_group, 'criterio': reason}, ensure_ascii=False), actor))
    return {'selected': len(cleaned), 'changed': len(changed),
            'unchanged': len(cleaned) - len(changed), 'backup': str(backup)}


def participants(diagnostic: str, path: Path | None = None) -> list[dict]:
    """Matriz cruzada del directorio y respuestas; sin cambiar ninguna fuente."""
    from .step2_engine_audit import readiness
    state = readiness(diagnostic, path)
    clients = {x['id']: x for x in list_clients(path=path)}
    records = []
    for line in state['rows']:
        source = clients[line['id']]
        records.append({**line, 'equipo': source.get('equipo_trabajo', '') or '',
                        'rol': client_role(source) or source.get('cargo') or '',
                        'influencia': source.get('influencia') or ''})
    return records


def metrics(diagnostic: str, path: Path | None = None) -> dict:
    matrix = participants(diagnostic, path)
    active = [x for x in matrix if x['activo']]
    responding = [x for x in active if x['prioridades']]
    return {'total': len(matrix), 'active': len(active),
            'classified': sum(bool(x['grupo']) for x in active),
            'unclassified': sum(not x['grupo'] for x in active),
            'responding': len(responding),
            'complete': sum(x['estado'] == 'Completa' for x in active),
            'groups': dict(sorted(Counter(x['grupo'] for x in active if x['grupo']).items())),
            'by_department': dict(sorted(Counter(x['dependencia'] for x in active).items())),
            'rows': matrix}


def template_csv(rows: list[dict]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['codigo', 'nombre', 'dependencia', 'equipo', 'rol'])
    for x in rows:
        safe = lambda v: "'" + str(v) if str(v).startswith(('=', '+', '-', '@')) else str(v)
        writer.writerow([safe(x['codigo']), safe(x['nombre']), safe(x['dependencia']),
                         safe(x['equipo']), safe(x['grupo'])])
    return buf.getvalue().encode('utf-8-sig')


def preview_csv(data: bytes, path: Path | None = None) -> dict:
    """CSV editable con Excel; devuelve ID real sin aplicar cambios."""
    if not data or len(data) > 1_000_000:
        raise ValidationError('El CSV debe existir y tener máximo 1 MB.')
    try:
        source = data.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise ValidationError('Guarde el archivo CSV con codificación UTF-8.') from exc
    try:
        rdr = csv.DictReader(io.StringIO(source))
        if not rdr.fieldnames or 'codigo' not in rdr.fieldnames or not ({'rol','segmento'} & set(rdr.fieldnames)):
            raise ValidationError('La plantilla necesita las columnas codigo y rol (o segmento en plantillas anteriores).')
        entries = list(rdr)
    except csv.Error as exc:
        raise ValidationError('CSV incorrecto.') from exc
    if len(entries) > 2000:
        raise ValidationError('Máximo 2.000 filas por importación.')
    people = {r['codigo'].upper(): r for r in list_clients(path=path)}
    seen = set()
    assignments, issues, preview = {}, [], []
    for n, row in enumerate(entries, 2):
        code = str(row.get('codigo') or '').strip().lstrip("'").upper()
        group = str(row.get('rol') or row.get('segmento') or '').strip()
        if not code and not group:
            continue
        # Los segmentos en blanco se omiten: el experto puede trabajar una muestra
        # parcial sin verse obligado a clasificar los 112 clientes del directorio.
        if code and not group:
            preview.append({'fila': n, 'codigo': code, 'antes': people.get(code, {}).get('segmento', ''),
                            'propuesto': '', 'validacion': 'Omitido (sin asignación)'})
            continue
        problem = ''
        if not code:
            problem = 'Falta código.'
        elif code in seen:
            problem = 'Código duplicado en el CSV.'
        elif code not in people:
            problem = 'El cliente no existe en el directorio.'
        elif not people[code]['activo']:
            problem = 'El cliente está archivado.'
        else:
            try: group = _segment(group)
            except ValidationError as exc: problem = str(exc)
        seen.add(code)
        if problem:
            issues.append(f'Fila {n}: {problem}')
        else:
            assignments[people[code]['id']] = group
        preview.append({'fila': n, 'codigo': code, 'antes': people.get(code, {}).get('segmento', ''),
                        'propuesto': group, 'validacion': problem or 'Correcto'})
    if not assignments and not issues:
        issues.append('No se encontraron filas con asignaciones.')
    return {'assignments': assignments, 'issues': issues, 'rows': preview}


def record_expert_criterion(run_id: str, diagnostic: str, weights: Mapping[str, float],
                            method: str, justification: str, actor: str,
                            path: Path | None = None) -> None:
    ensure_schema(path)
    actor, justification = str(actor or '').strip(), str(justification or '').strip()
    if not actor or len(actor) > 150:
        raise ValidationError('Indique responsable del cálculo.')
    if method not in CRITERIA:
        raise ValidationError('Seleccione el método de ponderación experta.')
    if len(justification) < 12 or len(justification) > 3000:
        raise ValidationError('Justifique los pesos elegidos (entre 12 y 3.000 caracteres).')
    with transaction(path) as con:
        r = con.execute('SELECT diagnostico_id,pesos_json FROM p2_corridas WHERE id=?', (run_id,)).fetchone()
        if not r or r['diagnostico_id'] != diagnostic:
            raise ValidationError('La corrida no pertenece a este diagnóstico.')
        frozen = json.loads(r['pesos_json'])
        if {k: float(v) for k, v in frozen.items()} != {k: float(v) for k, v in weights.items()}:
            raise ValidationError('La justificación debe referirse a los pesos exactos de la corrida.')
        if con.execute('SELECT 1 FROM p2_criterios_ponderacion WHERE corrida_id=?', (run_id,)).fetchone():
            raise ValidationError('El criterio experto de esta corrida ya fue registrado y es inmutable.')
        con.execute('''INSERT INTO p2_criterios_ponderacion
                       (corrida_id,diagnostico_id,metodo,justificacion,pesos_json,responsable)
                       VALUES (?,?,?,?,?,?)''',
                    (run_id, diagnostic, method, justification,
                     json.dumps(frozen, ensure_ascii=False, sort_keys=True), actor))
        con.execute('''INSERT INTO pmo_auditoria(entidad,entidad_id,accion,antes_json,despues_json,actor)
                       VALUES (?,?,?,?,?,?)''',
                    ('p2_corrida', run_id, 'criterio_experto', None,
                     json.dumps({'metodo': method, 'justificacion': justification,
                                 'pesos': frozen}, ensure_ascii=False), actor))


def expert_criterion(run_id: str, path: Path | None = None) -> dict | None:
    ensure_schema(path)
    with closing(connect(path)) as con:
        row = con.execute('SELECT * FROM p2_criterios_ponderacion WHERE corrida_id=?', (run_id,)).fetchone()
        return dict(row) if row else None


def criteria_history(diagnostic: str, path: Path | None = None) -> list[dict]:
    ensure_schema(path)
    with closing(connect(path)) as con:
        return [dict(x) for x in con.execute('''SELECT w.*,r.modelo,r.fecha AS fecha_corrida
                         FROM p2_criterios_ponderacion w JOIN p2_corridas r ON r.id=w.corrida_id
                         WHERE w.diagnostico_id=? ORDER BY r.fecha DESC,r.id DESC''', (diagnostic,))]


def run_expert_scenario(diagnostic: str, weights: Mapping[str, float], actor: str,
                        method: str, justification: str, matrix_version_id: str,
                        path: Path | None = None) -> str:
    """Orquesta validación y registro; no modifica las ecuaciones del motor.

    Primero valida el sustento y la clasificación; luego ejecuta V5 y conserva
    tanto el snapshot de pesos de la corrida como su justificación inmutable.
    """
    from . import matrix as canonical
    actor = str(actor or '').strip()
    justification = str(justification or '').strip()
    if not actor or len(actor) > 150:
        raise ValidationError('Responsable del cálculo obligatorio (máximo 150 caracteres).')
    if method not in CRITERIA:
        raise ValidationError('Seleccione el método experto de ponderación.')
    if not 12 <= len(justification) <= 3000:
        raise ValidationError('Justifique la ponderación entre 12 y 3.000 caracteres.')
    records = p2._participant_records(diagnostic, path)
    if matrix_version_id == canonical.V5_ID:
        if any(x['group'] == 'Sin segmento' for x in records):
            raise ValidationError('Existen participantes con respuestas sin grupo. Clasifíquelos antes de ejecutar V5.')
        if any(len(x['priorities']) != 5 for x in records):
            raise ValidationError('Existen participantes con prioridades incompletas.')
    ensure_schema(path)
    run_id = p2.run(diagnostic, dict(weights), actor, matrix_version_id=matrix_version_id, path=path)
    p2.save_weights(diagnostic, dict(weights), actor, path=path)
    record_expert_criterion(run_id, diagnostic, weights, method, justification, actor, path)
    return run_id
