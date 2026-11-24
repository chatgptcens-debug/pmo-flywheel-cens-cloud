"""Paso 01: relacionamiento verificable con clientes internos (V0.29).

Las interacciones son contactos realizados, no necesidades validadas. Las consultas
formales siguen almacenadas en p1_consultas; este módulo no duplica esas filas.
Toda mutación se audita y se ejecuta transaccionalmente en la SQLite del Ciclo 01.
"""
from __future__ import annotations

from contextlib import closing
from datetime import date, datetime
from pathlib import Path
import sqlite3
import uuid

from .clients import ValidationError
from .config import database_path
from .storage import connect, transaction

CHANNELS = ('Presencial', 'Teams', 'Llamada', 'Correo', 'Videoconferencia', 'Otro')
MOTIVES = ('Sensibilización', 'Consulta informal', 'Orientación', 'Retroalimentación', 'Seguimiento', 'Otro')
COMMITMENT_STATES = ('Pendiente', 'En curso', 'Cumplido', 'Cancelado')
TICKET_STATES = ('Recibida', 'En análisis', 'En gestión', 'Respondida', 'Cerrada')
PRIORITIES = ('Baja', 'Media', 'Alta')

SCHEMA = """
CREATE TABLE IF NOT EXISTS p1_interacciones (
  id TEXT PRIMARY KEY,
  cliente_id TEXT NOT NULL REFERENCES pmo_clientes(id),
  fecha TEXT NOT NULL,
  canal TEXT NOT NULL,
  motivo TEXT NOT NULL,
  descripcion TEXT NOT NULL,
  responsable TEXT NOT NULL,
  resultado TEXT NOT NULL DEFAULT '',
  necesidad_preliminar TEXT NOT NULL DEFAULT '',
  insumo_paso2 INTEGER NOT NULL DEFAULT 0 CHECK(insumo_paso2 IN (0,1)),
  registrado_por TEXT NOT NULL,
  creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_p1_interacciones_cliente ON p1_interacciones(cliente_id,fecha);
CREATE TABLE IF NOT EXISTS p1_compromisos (
  id TEXT PRIMARY KEY,
  interaccion_id TEXT NOT NULL REFERENCES p1_interacciones(id),
  cliente_id TEXT NOT NULL REFERENCES pmo_clientes(id),
  descripcion TEXT NOT NULL,
  responsable TEXT NOT NULL,
  vence_en TEXT,
  estado TEXT NOT NULL DEFAULT 'Pendiente'
    CHECK(estado IN ('Pendiente','En curso','Cumplido','Cancelado')),
  observaciones TEXT NOT NULL DEFAULT '',
  creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  cerrado_en TEXT
);
CREATE INDEX IF NOT EXISTS idx_p1_compromisos_cliente ON p1_compromisos(cliente_id);
CREATE INDEX IF NOT EXISTS idx_p1_compromisos_estado ON p1_compromisos(estado,vence_en);
"""


def _required(value: str | None, label: str, limit: int = 2000) -> str:
    text = str(value or '').strip()
    if not text:
        raise ValidationError(f'Indique {label}.')
    if len(text) > limit:
        raise ValidationError(f'{label.capitalize()}: máximo {limit} caracteres.')
    return text


def _optional(value: str | None, limit: int = 3000) -> str:
    text = str(value or '').strip()
    if len(text) > limit:
        raise ValidationError(f'El texto supera {limit} caracteres.')
    return text


def _date(value: date | str, required: bool = True) -> str | None:
    if value in (None, '') and not required:
        return None
    try:
        return (value if isinstance(value, date) else date.fromisoformat(str(value))).isoformat()
    except (TypeError, ValueError) as exc:
        raise ValidationError('Introduzca una fecha válida.') from exc


def _log(con: sqlite3.Connection, entity: str, identifier: str, action: str,
         actor: str, detail: str = '') -> None:
    con.execute('''INSERT INTO pmo_auditoria(entidad,entidad_id,accion,despues_json,actor)
                   VALUES(?,?,?,?,?)''', (entity, identifier, action, detail, actor))


def _backup_before_migration(path: Path) -> Path:
    """Copia coherente de SQLite antes de alterar la tabla histórica de consultas."""
    folder = path.parent / 'respaldos_migracion'
    folder.mkdir(parents=True, exist_ok=True)
    suffix = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    destination = folder / f'{path.stem}_pre_v029_{suffix}.sqlite3'
    with closing(connect(path)) as source, closing(sqlite3.connect(str(destination))) as backup:
        source.backup(backup)
    return destination


def initialize(path: Path | None = None) -> None:
    """Migración idempotente: no toca filas existentes ni el esquema de otros pasos."""
    db = Path(path) if path is not None else database_path()
    with closing(connect(db)) as con:
        ticket_exists = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='p1_consultas'").fetchone()
        has_priority = bool(ticket_exists and 'prioridad' in {
            row['name'] for row in con.execute('PRAGMA table_info(p1_consultas)')
        })
    if ticket_exists and not has_priority:
        _backup_before_migration(db)
    with closing(connect(db)) as con:
        con.executescript(SCHEMA)
        if ticket_exists and 'prioridad' not in {r['name'] for r in con.execute('PRAGMA table_info(p1_consultas)')}:
            con.execute("ALTER TABLE p1_consultas ADD COLUMN prioridad TEXT NOT NULL DEFAULT 'Media'")
        con.commit()


def create_interaction(client_id: str, when: date | str, channel: str, motive: str,
                       description: str, owner: str, actor: str, result: str = '',
                       preliminary_need: str = '', transfer_to_step2: bool = False,
                       commitment: str = '', commitment_owner: str = '',
                       commitment_due: date | str | None = None,
                       path: Path | None = None) -> str:
    client_id = _required(client_id, 'un cliente registrado', 80)
    day = _date(when)
    if day > date.today().isoformat():
        raise ValidationError('Una interacción realizada no puede tener fecha futura.')
    if channel not in CHANNELS or motive not in MOTIVES:
        raise ValidationError('Canal o motivo de interacción no permitido.')
    description = _required(description, 'la descripción de la interacción', 4000)
    owner = _required(owner, 'el responsable PMO', 180)
    actor = _required(actor, 'quién registra la interacción', 180)
    result = _optional(result)
    preliminary_need = _optional(preliminary_need)
    if transfer_to_step2 and not preliminary_need:
        raise ValidationError('Para marcar como insumo del Paso 02 describa una necesidad preliminar.')
    commitment = _optional(commitment)
    if commitment:
        commitment_owner = _required(commitment_owner, 'el responsable del compromiso', 180)
        commitment_due = _date(commitment_due, required=False)
    elif commitment_owner or commitment_due:
        raise ValidationError('Indique la descripción del compromiso o deje sus datos vacíos.')
    identifier = uuid.uuid4().hex
    with transaction(path) as con:
        row = con.execute('SELECT id FROM pmo_clientes WHERE id=? AND activo=1', (client_id,)).fetchone()
        if not row:
            raise ValidationError('Seleccione un cliente activo del directorio.')
        con.execute('''INSERT INTO p1_interacciones
          (id,cliente_id,fecha,canal,motivo,descripcion,responsable,resultado,
           necesidad_preliminar,insumo_paso2,registrado_por)
           VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
            (identifier, client_id, day, channel, motive, description, owner, result,
             preliminary_need, int(bool(transfer_to_step2)), actor))
        _log(con, 'interaccion', identifier, 'crear', actor, client_id)
        if commitment:
            _add_commitment(con, identifier, client_id, commitment, commitment_owner,
                            commitment_due, actor)
    return identifier


def _add_commitment(con, interaction_id, client_id, text, owner, due, actor) -> str:
    key = uuid.uuid4().hex
    con.execute('''INSERT INTO p1_compromisos
      (id,interaccion_id,cliente_id,descripcion,responsable,vence_en)
      VALUES(?,?,?,?,?,?)''', (key, interaction_id, client_id, text, owner, due))
    _log(con, 'compromiso', key, 'crear', actor, interaction_id)
    return key


def add_commitment(interaction_id: str, description: str, owner: str, actor: str,
                   due: date | str | None = None, path: Path | None = None) -> str:
    description = _required(description, 'el compromiso', 3000)
    owner = _required(owner, 'el responsable del compromiso', 180)
    actor = _required(actor, 'quién registra', 180)
    when = _date(due, required=False)
    with transaction(path) as con:
        row = con.execute('SELECT cliente_id FROM p1_interacciones WHERE id=?', (interaction_id,)).fetchone()
        if not row:
            raise ValidationError('La interacción indicada no existe.')
        return _add_commitment(con, interaction_id, row['cliente_id'], description, owner, when, actor)


def update_commitment(identifier: str, state: str, observation: str,
                      actor: str, path: Path | None = None) -> None:
    if state not in COMMITMENT_STATES:
        raise ValidationError('Estado de compromiso no válido.')
    actor = _required(actor, 'quién actualiza', 180)
    observation = _optional(observation)
    with transaction(path) as con:
        previous = con.execute('SELECT estado FROM p1_compromisos WHERE id=?', (identifier,)).fetchone()
        if not previous:
            raise ValidationError('El compromiso no existe.')
        con.execute('''UPDATE p1_compromisos SET estado=?, observaciones=?,
           actualizado_en=CURRENT_TIMESTAMP,
           cerrado_en=CASE WHEN ? IN ('Cumplido','Cancelado') THEN CURRENT_TIMESTAMP ELSE NULL END
           WHERE id=?''', (state, observation, state, identifier))
        _log(con, 'compromiso', identifier, 'actualizar', actor, f'{previous["estado"]} → {state}')


def update_consultation(ticket_id: str, status: str, priority: str,
                        owner: str, answer: str, actor: str,
                        path: Path | None = None) -> None:
    if status not in TICKET_STATES or priority not in PRIORITIES:
        raise ValidationError('Estado o prioridad de consulta no permitido.')
    actor = _required(actor, 'quién actualiza', 180)
    answer = _optional(answer, 8000)
    owner = _optional(owner, 180)
    if status in ('Respondida', 'Cerrada') and not answer:
        raise ValidationError('Las consultas respondidas o cerradas requieren una respuesta.')
    with transaction(path) as con:
        row = con.execute('SELECT id FROM p1_consultas WHERE id=?', (ticket_id,)).fetchone()
        if not row:
            raise ValidationError('La consulta no existe.')
        con.execute('''UPDATE p1_consultas SET estado=?, prioridad=?,responsable=?,respuesta=?,
           respondido_en=CASE WHEN ? IN ('Respondida','Cerrada') THEN CURRENT_TIMESTAMP ELSE NULL END
           WHERE id=?''', (status, priority, owner, answer, status, ticket_id))
        _log(con, 'consulta', ticket_id, 'actualizar', actor, f'{status}/{priority}')


def list_interactions(client_id: str = '', dependency: str = '', search: str = '',
                      channel: str = '', path: Path | None = None) -> list[dict]:
    sql = '''SELECT i.*,c.nombre AS cliente,c.codigo AS codigo_cliente,
                    d.nombre AS dependencia,c.equipo_trabajo
             FROM p1_interacciones i JOIN pmo_clientes c ON c.id=i.cliente_id
             JOIN pmo_dependencias d ON d.id=c.dependencia_id WHERE 1=1'''
    args = []
    if client_id:
        sql += ' AND i.cliente_id=?';args.append(client_id)
    if dependency:
        sql += ' AND d.nombre=?';args.append(dependency)
    if channel:
        sql += ' AND i.canal=?';args.append(channel)
    if search.strip():
        sql += ' AND (c.nombre LIKE ? OR c.codigo LIKE ? OR i.descripcion LIKE ? OR i.motivo LIKE ?)'
        args.extend([f'%{search.strip()}%'] * 4)
    sql += ' ORDER BY i.fecha DESC,i.creado_en DESC,i.id DESC'
    with closing(connect(path)) as con:
        return [dict(r) for r in con.execute(sql, args)]


def list_commitments(state: str = '', path: Path | None = None) -> list[dict]:
    sql = '''SELECT k.*,c.nombre AS cliente,c.codigo AS codigo_cliente,
                    i.fecha AS fecha_interaccion
             FROM p1_compromisos k JOIN pmo_clientes c ON c.id=k.cliente_id
             JOIN p1_interacciones i ON i.id=k.interaccion_id WHERE 1=1'''
    args = []
    if state:
        sql += ' AND k.estado=?';args.append(state)
    sql += ' ORDER BY CASE WHEN k.vence_en IS NULL THEN 1 ELSE 0 END,k.vence_en,k.creado_en'
    with closing(connect(path)) as con:
        return [dict(r) for r in con.execute(sql, args)]


def list_consultations(status: str = '', priority: str = '', search: str = '',
                       path: Path | None = None) -> list[dict]:
    sql = '''SELECT t.*,c.nombre AS cliente,c.codigo AS codigo_cliente,
                    d.nombre AS dependencia FROM p1_consultas t
             JOIN pmo_clientes c ON c.id=t.cliente_id
             JOIN pmo_dependencias d ON d.id=c.dependencia_id WHERE 1=1'''
    args = []
    if status:
        sql += ' AND t.estado=?';args.append(status)
    if priority:
        sql += ' AND t.prioridad=?';args.append(priority)
    if search.strip():
        sql += ' AND (t.asunto LIKE ? OR t.descripcion LIKE ? OR c.nombre LIKE ? OR c.codigo LIKE ?)'
        args.extend([f'%{search.strip()}%']*4)
    sql += ' ORDER BY t.creado_en DESC,t.id DESC'
    with closing(connect(path)) as con:
        return [dict(r) for r in con.execute(sql,args)]


def metrics(path: Path | None = None) -> dict:
    """Contacto = cliente activo con interacción documentada o consulta formal.

    Eventos y descargas no se contabilizan aquí para evitar métricas duplicadas.
    """
    with closing(connect(path)) as con:
        active = con.execute('SELECT COUNT(*) FROM pmo_clientes WHERE activo=1').fetchone()[0]
        contacted = con.execute('''SELECT COUNT(DISTINCT cliente_id) FROM (
           SELECT i.cliente_id FROM p1_interacciones i JOIN pmo_clientes c ON c.id=i.cliente_id WHERE c.activo=1
           UNION SELECT t.cliente_id FROM p1_consultas t JOIN pmo_clientes c ON c.id=t.cliente_id WHERE c.activo=1
        )''').fetchone()[0]
        interactions = con.execute('SELECT COUNT(*) FROM p1_interacciones').fetchone()[0]
        tickets_pending = con.execute("SELECT COUNT(*) FROM p1_consultas WHERE estado NOT IN ('Respondida','Cerrada')").fetchone()[0]
        commitments_pending = con.execute("SELECT COUNT(*) FROM p1_compromisos WHERE estado IN ('Pendiente','En curso')").fetchone()[0]
        preliminary = con.execute("SELECT COUNT(*) FROM p1_interacciones WHERE insumo_paso2=1").fetchone()[0]
    return dict(active=active,contacted=contacted,coverage=(100*contacted/active if active else None),
                interactions=interactions,tickets_pending=tickets_pending,
                commitments_pending=commitments_pending,preliminary=preliminary)


def client_timeline(client_id: str, path: Path | None = None) -> list[dict]:
    """Resumen de registros existentes, sin replicarlos en otra tabla."""
    with closing(connect(path)) as con:
        ints = [dict(r) for r in con.execute('''SELECT id,fecha,canal,motivo,descripcion,resultado,insumo_paso2
                     FROM p1_interacciones WHERE cliente_id=? ORDER BY fecha DESC''',(client_id,))]
        tickets = [dict(r) for r in con.execute('''SELECT id,creado_en AS fecha,asunto,estado,prioridad,respuesta
                     FROM p1_consultas WHERE cliente_id=? ORDER BY creado_en DESC''',(client_id,))]
        tasks = [dict(r) for r in con.execute('''SELECT id,creado_en AS fecha,descripcion,estado,vence_en
                     FROM p1_compromisos WHERE cliente_id=? ORDER BY creado_en DESC''',(client_id,))]
    timeline = ([dict(r,tipo='Interacción') for r in ints] +
                [dict(r,tipo='Consulta') for r in tickets] +
                [dict(r,tipo='Compromiso') for r in tasks])
    return sorted(timeline,key=lambda r: str(r['fecha']),reverse=True)


def create_consultation(client_id: str, subject: str, category: str, description: str,
                        owner: str, actor: str, priority: str = 'Media',
                        path: Path | None = None) -> str:
    """Alta de consulta con prioridad en una sola transacción, sin duplicar interacción."""
    subject = _required(subject, 'el asunto', 250)
    description = _required(description, 'la descripción', 4000)
    owner = _optional(owner,180)
    actor = _required(actor, 'quién registra',180)
    if priority not in PRIORITIES:
        raise ValidationError('Prioridad de consulta no válida.')
    key = uuid.uuid4().hex
    with transaction(path) as con:
        if not con.execute('SELECT 1 FROM pmo_clientes WHERE id=? AND activo=1', (client_id,)).fetchone():
            raise ValidationError('Seleccione un cliente activo.')
        con.execute('''INSERT INTO p1_consultas
          (id,cliente_id,asunto,categoria,descripcion,responsable,prioridad)
          VALUES(?,?,?,?,?,?,?)''',
          (key,client_id,subject,category,description,owner,priority))
        _log(con,'consulta',key,'crear',actor,'Nueva consulta')
    return key


def edit_interaction(identifier: str, when: date | str, channel: str, motive: str,
                     description: str, owner: str, actor: str, result: str = '',
                     preliminary_need: str = '', transfer_to_step2: bool = False,
                     path: Path | None = None) -> None:
    day = _date(when)
    if day > date.today().isoformat():
        raise ValidationError('Una interacción realizada no puede tener fecha futura.')
    if channel not in CHANNELS or motive not in MOTIVES:
        raise ValidationError('Canal o motivo no válido.')
    description = _required(description, 'la descripción',4000)
    owner = _required(owner, 'el responsable PMO',180)
    actor = _required(actor, 'quién actualiza',180)
    result = _optional(result)
    preliminary_need = _optional(preliminary_need)
    if transfer_to_step2 and not preliminary_need:
        raise ValidationError('Registre la necesidad antes de marcarla como antecedente del Paso 02.')
    with transaction(path) as con:
        if not con.execute('SELECT 1 FROM p1_interacciones WHERE id=?', (identifier,)).fetchone():
            raise ValidationError('La interacción ya no existe.')
        con.execute('''UPDATE p1_interacciones SET fecha=?,canal=?,motivo=?,descripcion=?,
          responsable=?,resultado=?,necesidad_preliminar=?,insumo_paso2=? WHERE id=?''',
          (day,channel,motive,description,owner,result,preliminary_need,int(bool(transfer_to_step2)),identifier))
        _log(con,'interaccion',identifier,'actualizar',actor)


def department_summary(path: Path | None = None) -> list[dict]:
    with closing(connect(path)) as con:
        return [dict(r) for r in con.execute('''
            SELECT d.nombre AS dependencia, COUNT(DISTINCT c.id) AS objetivo,
               COUNT(DISTINCT CASE WHEN (
                 EXISTS(SELECT 1 FROM p1_interacciones i WHERE i.cliente_id=c.id) OR
                 EXISTS(SELECT 1 FROM p1_consultas t WHERE t.cliente_id=c.id)
               ) THEN c.id END) AS contactados
            FROM pmo_dependencias d JOIN pmo_clientes c ON c.dependencia_id=d.id AND c.activo=1
            GROUP BY d.id ORDER BY d.nombre COLLATE NOCASE
        ''')]
