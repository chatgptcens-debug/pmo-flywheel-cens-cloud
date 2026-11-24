"""Directorio permanente de clientes; lógica funcional independiente de Streamlit."""
from __future__ import annotations
import json
from contextlib import closing
import re
import sqlite3
import uuid
from datetime import date
from pathlib import Path
from typing import Any
from .storage import connect, transaction

FIELDS = (
    "codigo", "nombre", "dependencia", "cargo", "correo", "sede", "segmento",
    "influencia", "interes", "conocimiento", "participa_proyectos", "canal",
    "retos", "necesidades_preliminares", "beneficios_esperados", "barreras",
    "observaciones", "responsable", "primer_contacto", "relacionamiento",
    "embajador", "activo", "equipo_trabajo", "rol_especifico", "estado_gestion",
)


class ValidationError(ValueError):
    """Error recuperable con mensaje legible para personas usuarias."""


def normalize(payload: dict[str, Any]) -> dict[str, Any]:
    d: dict[str, Any] = {}
    for k in FIELDS:
        v = payload.get(k)
        d[k] = v.strip() if isinstance(v, str) else v
    d["codigo"] = str(d["codigo"] or "").upper()
    for k in ("codigo", "nombre", "dependencia"):
        if not d[k]:
            raise ValidationError(f"El campo {k} es obligatorio.")
    if len(d["codigo"]) > 40:
        raise ValidationError("El código debe tener como máximo 40 caracteres.")
    if len(d["nombre"]) > 180:
        raise ValidationError("El nombre debe tener como máximo 180 caracteres.")
    if len(d["dependencia"]) > 140:
        raise ValidationError("La dependencia debe tener como máximo 140 caracteres.")
    # En CENS la Dependencia es el equivalente organizacional de Sede.
    # Respetar una Sede explicita historica, pero nunca dejarla vacia en el ciclo nuevo.
    if not d["sede"]:
        d["sede"] = d["dependencia"]
    for k in ("equipo_trabajo", "rol_especifico", "estado_gestion"):
        if d[k] is not None and len(str(d[k])) > 1000:
            raise ValidationError(f"{k}: máximo 1.000 caracteres.")
    d["correo"] = (d["correo"] or "").lower() or None
    if d["correo"] and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", d["correo"]):
        raise ValidationError("El correo no tiene un formato válido.")
    d["influencia"] = d["influencia"] or "Sin evaluar"
    d["interes"] = d["interes"] or "Sin evaluar"
    d["relacionamiento"] = d["relacionamiento"] or "Sin contacto"
    if d["influencia"] not in ("Sin evaluar", "Baja", "Media", "Alta"):
        raise ValidationError("Nivel de influencia no permitido.")
    if d["interes"] not in ("Sin evaluar", "Bajo", "Medio", "Alto"):
        raise ValidationError("Nivel de interés no permitido.")
    d["conocimiento"] = int(d["conocimiento"]) if d["conocimiento"] not in (None, "") else None
    if d["conocimiento"] is not None and not 1 <= d["conocimiento"] <= 5:
        raise ValidationError("El conocimiento debe estar entre 1 y 5.")
    d["embajador"] = 1 if d["embajador"] else 0
    d["activo"] = 1 if d["activo"] is None or bool(d["activo"]) else 0
    if isinstance(d["primer_contacto"], date):
        d["primer_contacto"] = d["primer_contacto"].isoformat()
    if d["primer_contacto"]:
        try:
            date.fromisoformat(d["primer_contacto"])
        except (ValueError, TypeError) as exc:
            raise ValidationError("La fecha de primer contacto es inválida.") from exc
    d["primer_contacto"] = d["primer_contacto"] or None
    for k in FIELDS:
        if d[k] is None and k not in ("correo", "conocimiento", "primer_contacto"):
            d[k] = "" if k not in ("activo", "embajador") else 0
    return d


def _department(con: sqlite3.Connection, name: str) -> int:
    con.execute("INSERT OR IGNORE INTO pmo_dependencias(nombre) VALUES (?)", (name,))
    row = con.execute("SELECT id FROM pmo_dependencias WHERE nombre=? COLLATE NOCASE", (name,)).fetchone()
    return int(row["id"])


def _map_row(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def _fetch(con: sqlite3.Connection, client_id: str) -> dict[str, Any] | None:
    row = con.execute("""SELECT c.*, d.nombre AS dependencia FROM pmo_clientes c
        JOIN pmo_dependencias d ON d.id = c.dependencia_id WHERE c.id=?""", (client_id,)).fetchone()
    return _map_row(row) if row else None


def _duplicate_message(err: sqlite3.IntegrityError) -> str:
    msg = str(err).lower()
    if "correo" in msg:
        return "Ya existe un cliente con ese correo. Revise el directorio."
    if "codigo" in msg:
        return "Ya existe un cliente con ese código corporativo."
    return "No se pudo guardar por una restricción de integridad."


def create_client(payload: dict[str, Any], actor: str, path: Path | None = None) -> str:
    if not actor.strip():
        raise ValidationError("Indique quién registra la información.")
    d = normalize(payload)
    client_id = uuid.uuid4().hex
    try:
        with transaction(path) as con:
            department_id = _department(con, d.pop("dependencia"))
            cols = [*d, "id", "dependencia_id"]
            con.execute(
                f"INSERT INTO pmo_clientes({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
                [*d.values(), client_id, department_id],
            )
            after = _fetch(con, client_id)
            con.execute("""INSERT INTO pmo_auditoria(entidad,entidad_id,accion,despues_json,actor)
                           VALUES (?,?,?,?,?)""", ("cliente", client_id, "crear", json.dumps(after, ensure_ascii=False), actor.strip()))
    except sqlite3.IntegrityError as exc:
        raise ValidationError(_duplicate_message(exc)) from exc
    return client_id


def update_client(client_id: str, payload: dict[str, Any], actor: str, path: Path | None = None) -> None:
    if not actor.strip():
        raise ValidationError("Indique quién modifica la información.")
    d = normalize(payload)
    try:
        with transaction(path) as con:
            before = _fetch(con, client_id)
            if before is None:
                raise ValidationError("El cliente indicado no existe.")
            dept_id = _department(con, d.pop("dependencia"))
            assigns = ",".join(f"{col}=?" for col in d)
            con.execute(
                f"UPDATE pmo_clientes SET {assigns}, dependencia_id=?, actualizado_en=CURRENT_TIMESTAMP WHERE id=?",
                [*d.values(), dept_id, client_id],
            )
            after = _fetch(con, client_id)
            con.execute("""INSERT INTO pmo_auditoria(entidad,entidad_id,accion,antes_json,despues_json,actor)
                           VALUES (?,?,?,?,?,?)""",
                        ("cliente", client_id, "actualizar", json.dumps(before, ensure_ascii=False),
                         json.dumps(after, ensure_ascii=False), actor.strip()))
    except sqlite3.IntegrityError as exc:
        raise ValidationError(_duplicate_message(exc)) from exc


def get_client(client_id: str, path: Path | None = None) -> dict[str, Any] | None:
    with closing(connect(path)) as con:
        return _fetch(con, client_id)


def list_clients(search: str = "", dependency: str = "", status: str = "Todos", path: Path | None = None) -> list[dict[str, Any]]:
    query = """SELECT c.*, d.nombre AS dependencia FROM pmo_clientes c
          JOIN pmo_dependencias d ON c.dependencia_id=d.id WHERE 1=1"""
    args: list[Any] = []
    if search.strip():
        query += " AND (c.codigo LIKE ? OR c.nombre LIKE ? OR c.correo LIKE ? OR c.cargo LIKE ?)"
        v = f"%{search.strip()}%"
        args.extend([v] * 4)
    if dependency:
        query += " AND d.nombre=? COLLATE NOCASE"
        args.append(dependency)
    if status in ("Activos", "Inactivos"):
        query += " AND c.activo=?"
        args.append(1 if status == "Activos" else 0)
    query += " ORDER BY c.nombre COLLATE NOCASE, c.codigo"
    with closing(connect(path)) as con:
        return [_map_row(r) for r in con.execute(query, args).fetchall()]


def dependencies(path: Path | None = None) -> list[str]:
    with closing(connect(path)) as con:
        return [r["nombre"] for r in con.execute("SELECT nombre FROM pmo_dependencias ORDER BY nombre COLLATE NOCASE")]


def counts(path: Path | None = None) -> dict[str, int]:
    with closing(connect(path)) as con:
        r = con.execute("""SELECT COUNT(*) AS registrados,
           COALESCE(SUM(activo),0) AS activos,
           COUNT(DISTINCT CASE WHEN activo=1 THEN dependencia_id END) AS dependencias
           FROM pmo_clientes""").fetchone()
        return dict(r)


def audit_history(client_id: str, path: Path | None = None) -> list[dict[str, Any]]:
    with closing(connect(path)) as con:
        return [dict(r) for r in con.execute(
            "SELECT accion,actor,fecha FROM pmo_auditoria WHERE entidad='cliente' AND entidad_id=? ORDER BY id DESC",
            (client_id,)).fetchall()]
