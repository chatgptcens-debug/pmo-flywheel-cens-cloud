"""Operaciones de sensibilización vinculadas al directorio único, sin datos simulados.

MVP local. Cada evento/campaña/recurso/consulta se guarda en la misma SQLite
que el directorio. No envía correo ni autentica usuarios.
"""
from __future__ import annotations
from contextlib import closing
from datetime import date, datetime
from pathlib import Path
import sqlite3
import uuid
from typing import Any
from urllib.parse import urlparse
from .clients import ValidationError
from .storage import connect, transaction


def _require(value: Any, name: str) -> str:
    value = str(value or '').strip()
    if not value:
        raise ValidationError(f"Indique {name}.")
    return value


def _iso_date(value: date | str | None) -> str:
    if isinstance(value, date):
        return value.isoformat()
    try:
        return date.fromisoformat(str(value)).isoformat()
    except (TypeError, ValueError) as err:
        raise ValidationError("La fecha no es válida.") from err


def _audit(con: sqlite3.Connection, ent: str, eid: str, action: str, actor: str, detail: str = '') -> None:
    con.execute("INSERT INTO pmo_auditoria(entidad, entidad_id, accion, despues_json, actor) VALUES (?,?,?,?,?)",
                (ent, eid, action, detail, actor))


def _rows(sql: str, params=(), path: Path | None = None) -> list[dict[str, Any]]:
    with closing(connect(path)) as con:
        return [dict(row) for row in con.execute(sql, params).fetchall()]


def create_resource(title: str, category: str, description: str, url: str, kind: str, status: str,
                    actor: str, path: Path | None = None) -> str:
    title = _require(title, 'el título del recurso')
    category = _require(category, 'la categoría')
    actor = _require(actor, 'el responsable del registro')
    if kind not in ('Material', 'Servicio', 'Historia'):
        raise ValidationError('Tipo de recurso no válido.')
    if status not in ('Borrador', 'Publicado', 'En diseño', 'Piloto', 'Disponible', 'Suspendido'):
        raise ValidationError('Estado de recurso no permitido.')
    url = (url or '').strip()
    if url:
        parsed = urlparse(url)
        if parsed.scheme not in ('http','https') or not parsed.netloc:
            raise ValidationError('Introduzca un enlace https:// válido.')
    key = uuid.uuid4().hex
    with transaction(path) as con:
        con.execute("""INSERT INTO p1_recursos(id,titulo,categoria,descripcion,url,tipo,estado,responsable)
                       VALUES (?,?,?,?,?,?,?,?)""", (key,title,category,description.strip(),url,kind,status,actor))
        _audit(con,'recurso',key,'crear',actor)
    return key


def resources(kind: str = '', search: str = '', path: Path | None = None) -> list[dict]:
    sql = 'SELECT * FROM p1_recursos WHERE 1=1'
    args: list = []
    if kind:
        sql += ' AND tipo=?'; args.append(kind)
    if search:
        sql += ' AND (titulo LIKE ? OR descripcion LIKE ? OR categoria LIKE ?)'
        args.extend([f'%{search}%']*3)
    return _rows(sql+' ORDER BY creado_en DESC, titulo COLLATE NOCASE',args,path)


def create_event(title: str, kind: str, start: date | str, audience: str, mode: str,
                 owner: str, status: str = 'Programado', path: Path | None = None) -> str:
    title = _require(title, 'el nombre de la actividad')
    owner = _require(owner, 'el responsable')
    if status not in ('Borrador','Programado','Realizado','Cancelado'):
        raise ValidationError('Estado de evento no válido.')
    key = uuid.uuid4().hex
    with transaction(path) as con:
        con.execute('''INSERT INTO p1_eventos(id,titulo,tipo,fecha,publico,modalidad,responsable,estado)
                       VALUES (?,?,?,?,?,?,?,?)''', (key,title,kind,_iso_date(start),audience,mode,owner,status))
        _audit(con,'evento',key,'crear',owner)
    return key


def events(path: Path | None = None) -> list[dict]:
    return _rows('''SELECT e.*, COUNT(CASE WHEN a.asistio=1 THEN 1 END) AS asistentes
                    FROM p1_eventos e LEFT JOIN p1_asistencias a ON a.evento_id=e.id
                    GROUP BY e.id ORDER BY e.fecha DESC,e.creado_en DESC''',path=path)


def set_attendance(event_id: str, client_id: str, attended: bool, actor: str,
                   path: Path | None = None) -> None:
    actor = _require(actor,'el responsable del registro')
    with transaction(path) as con:
        e=con.execute('SELECT id,estado FROM p1_eventos WHERE id=?',(event_id,)).fetchone()
        c=con.execute('SELECT id FROM pmo_clientes WHERE id=?',(client_id,)).fetchone()
        if not e or not c:
            raise ValidationError('El evento o el cliente no existen.')
        if e['estado'] == 'Cancelado':
            raise ValidationError('No se permite asistencia en un evento cancelado.')
        con.execute('''INSERT INTO p1_asistencias(evento_id,cliente_id,asistio)
                       VALUES (?,?,?) ON CONFLICT(evento_id,cliente_id) DO UPDATE SET asistio=excluded.asistio''',
                    (event_id,client_id,int(bool(attended))))
        _audit(con,'asistencia',event_id,'registrar',actor,client_id)


def update_event_status(event_id: str, status: str, actor: str, path: Path | None = None) -> None:
    """Permite registrar un cambio de estado con auditoría; el evento no se borra."""
    if status not in ('Borrador','Programado','Realizado','Cancelado'):
        raise ValidationError('Estado de evento no permitido.')
    actor = _require(actor, 'quién actualiza el evento')
    with transaction(path) as con:
        previous=con.execute('SELECT estado FROM p1_eventos WHERE id=?',(event_id,)).fetchone()
        if previous is None:
            raise ValidationError('El evento no existe.')
        if previous['estado']=='Cancelado' and status!='Cancelado':
            raise ValidationError('Un evento cancelado no puede reabrirse sin una nueva programación.')
        con.execute('UPDATE p1_eventos SET estado=? WHERE id=?',(status,event_id))
        _audit(con,'evento',event_id,'cambiar_estado',actor,previous['estado']+' -> '+status)


def attendance_for_event(event_id: str, path: Path | None = None) -> list[dict]:
    return _rows('''SELECT a.cliente_id,c.nombre,c.codigo,a.asistio
                  FROM p1_asistencias a JOIN pmo_clientes c ON c.id=a.cliente_id
                  WHERE a.evento_id=? ORDER BY c.nombre''', (event_id,),path)


def create_campaign(title: str, audience: str, channel: str, start: date | str,
                    status: str, owner: str, path: Path | None = None) -> str:
    title=_require(title,'el nombre de la campaña')
    owner=_require(owner,'el responsable')
    if status not in ('Borrador','Programada','En ejecución','Finalizada','Cancelada'):
        raise ValidationError('Estado de campaña no válido.')
    key=uuid.uuid4().hex
    with transaction(path) as con:
        con.execute('''INSERT INTO p1_campanas(id,titulo,audiencia,canal,fecha_inicio,estado,responsable)
                       VALUES(?,?,?,?,?,?,?)''',(key,title,audience,channel,_iso_date(start),status,owner))
        _audit(con,'campana',key,'crear',owner)
    return key


def campaigns(path: Path | None = None) -> list[dict]:
    return _rows('SELECT * FROM p1_campanas ORDER BY fecha_inicio DESC, creado_en DESC',path=path)


def create_ticket(client_id: str, subject: str, category: str, detail: str,
                  owner: str, actor: str, path: Path | None = None) -> str:
    subject=_require(subject,'el asunto')
    detail=_require(detail,'la descripción')
    actor=_require(actor,'quién registra')
    key=uuid.uuid4().hex
    with transaction(path) as con:
        if not con.execute('SELECT id FROM pmo_clientes WHERE id=?',(client_id,)).fetchone():
            raise ValidationError('Seleccione un cliente registrado.')
        con.execute('''INSERT INTO p1_consultas(id,cliente_id,asunto,categoria,descripcion,responsable)
                       VALUES (?,?,?,?,?,?)''',(key,client_id,subject,category,detail,owner))
        _audit(con,'consulta',key,'crear',actor)
    return key


def tickets(status: str = '', path: Path | None = None) -> list[dict]:
    sql='''SELECT t.*,c.nombre AS cliente,c.codigo AS codigo_cliente,
                  d.nombre AS dependencia FROM p1_consultas t
                  JOIN pmo_clientes c ON c.id=t.cliente_id
                  JOIN pmo_dependencias d ON d.id=c.dependencia_id WHERE 1=1'''
    args=[]
    if status:
        sql+=' AND t.estado=?';args.append(status)
    return _rows(sql+' ORDER BY t.creado_en DESC',args,path)


def update_ticket(ticket_id: str, status: str, response: str, actor: str,
                  path: Path | None = None) -> None:
    if status not in ('Recibida','En análisis','En gestión','Respondida','Cerrada'):
        raise ValidationError('Estado de consulta no válido.')
    actor=_require(actor,'el responsable de la actualización')
    if status in ('Respondida','Cerrada') and not response.strip():
        raise ValidationError('Debe registrar una respuesta antes de cerrar o responder.')
    with transaction(path) as con:
        if not con.execute('SELECT id FROM p1_consultas WHERE id=?',(ticket_id,)).fetchone():
            raise ValidationError('Consulta inexistente.')
        con.execute('''UPDATE p1_consultas SET estado=?,respuesta=?,respondido_en=CASE WHEN ?
                       IN ('Respondida','Cerrada') THEN CURRENT_TIMESTAMP ELSE NULL END
                       WHERE id=?''',(status,response.strip(),status,ticket_id))
        _audit(con,'consulta',ticket_id,'actualizar',actor,status)


def record_survey(client_id: str, event_id: str | None, phase: str, answers: list[int],
                  actor: str, path: Path | None = None) -> str:
    if phase not in ('Antes','Después'):
        raise ValidationError('La fase de encuesta es inválida.')
    if len(answers)!=5 or any(not isinstance(v,int) or not (1<=v<=5) for v in answers):
        raise ValidationError('La encuesta debe incluir cinco respuestas entre 1 y 5.')
    actor=_require(actor,'el responsable')
    key=uuid.uuid4().hex
    with transaction(path) as con:
        if not con.execute('SELECT id FROM pmo_clientes WHERE id=?',(client_id,)).fetchone():
            raise ValidationError('El cliente no existe.')
        if event_id and not con.execute('SELECT id FROM p1_eventos WHERE id=?',(event_id,)).fetchone():
            raise ValidationError('El evento no existe.')
        con.execute('''INSERT INTO p1_encuestas(id,cliente_id,evento_id,fase,familiaridad,proposito,servicios,
                       utilidad,interes,responsable) VALUES(?,?,?,?,?,?,?,?,?,?)''',
                    (key,client_id,event_id,phase,*answers,actor))
        _audit(con,'encuesta',key,'crear',actor)
    return key


def surveys(path: Path | None = None) -> list[dict]:
    return _rows('''SELECT s.*,c.nombre AS cliente, e.titulo AS evento
                   FROM p1_encuestas s JOIN pmo_clientes c ON c.id=s.cliente_id
                   LEFT JOIN p1_eventos e ON e.id=s.evento_id ORDER BY s.creado_en DESC''', path=path)


def summary(path: Path | None = None) -> dict:
    """Solo mediciones verificables. Una falta de denominador devuelve None, nunca 0%."""
    with closing(connect(path)) as con:
        active=con.execute('SELECT COUNT(*) FROM pmo_clientes WHERE activo=1').fetchone()[0]
        reached=con.execute('''SELECT COUNT(DISTINCT a.cliente_id) FROM p1_asistencias a
               JOIN pmo_clientes c ON c.id=a.cliente_id WHERE a.asistio=1 AND c.activo=1''').fetchone()[0]
        activities=con.execute("SELECT COUNT(*) FROM p1_eventos WHERE estado='Realizado'").fetchone()[0]
        engaged=con.execute("SELECT COUNT(*) FROM pmo_clientes WHERE embajador=1 AND activo=1").fetchone()[0]
        familiar=con.execute("SELECT AVG(familiaridad) FROM p1_encuestas WHERE fase='Después'").fetchone()[0]
        sample=con.execute("SELECT COUNT(*) FROM p1_encuestas WHERE fase='Después'").fetchone()[0]
        total_ticket=con.execute('SELECT COUNT(*) FROM p1_consultas').fetchone()[0]
        answered=con.execute("SELECT COUNT(*) FROM p1_consultas WHERE estado IN ('Respondida','Cerrada')").fetchone()[0]
        asses=con.execute("SELECT id,puntaje FROM p1_autoevaluaciones WHERE estado='Finalizada' ORDER BY finalizada_en DESC LIMIT 1").fetchone()
    return dict(active=active,reached=reached,coverage=(100*reached/active if active else None),
                activities=activities,embassadors=engaged,familiarity=familiar, sample=sample,
                tickets=total_ticket,answered=answered,ticket_rate=100*answered/total_ticket if total_ticket else None,
                last_assessment=asses['puntaje'] if asses else None)


def department_coverage(path: Path | None = None) -> list[dict]:
    return _rows('''SELECT d.nombre AS dependencia, COUNT(DISTINCT c.id) AS objetivo,
                   COUNT(DISTINCT CASE WHEN a.asistio=1 THEN c.id END) AS alcanzados
                   FROM pmo_dependencias d JOIN pmo_clientes c ON c.dependencia_id=d.id AND c.activo=1
                   LEFT JOIN p1_asistencias a ON a.cliente_id=c.id
                   GROUP BY d.id HAVING objetivo>0 ORDER BY d.nombre''',path=path)


def client_history(client_id: str, path: Path | None = None) -> dict[str,int]:
    with closing(connect(path)) as con:
        ev=con.execute("SELECT COUNT(*) FROM p1_asistencias WHERE cliente_id=? AND asistio=1",(client_id,)).fetchone()[0]
        tk=con.execute("SELECT COUNT(*) FROM p1_consultas WHERE cliente_id=?",(client_id,)).fetchone()[0]
        su=con.execute("SELECT COUNT(*) FROM p1_encuestas WHERE cliente_id=?",(client_id,)).fetchone()[0]
    return dict(events=ev,tickets=tk,surveys=su)
