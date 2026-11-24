"""Formulario del directorio conservado desde V0.1, reutilizado en la V0.2."""
from __future__ import annotations
import csv
import html
import io
from datetime import date
from typing import Any
import streamlit as st
from .clients import ValidationError, create_client, update_client
from .catalog_manager import smart_choice
from .v0391_clients import client_role, canonical_role

def _select(label: str, options: list[str], value: Any, key: str):
    choices = list(options)
    if value not in choices and value is not None and value != "":
        choices.append(str(value))
    return st.selectbox(label, choices, index=choices.index(value) if value in choices else 0, key=key)


def client_form(existing: dict[str, Any] | None = None):
    cur = existing or {}
    is_edit = existing is not None
    key = ("edit_"+cur["id"]) if is_edit else "new"
    st.markdown("#### Editar cliente" if is_edit else "#### Registrar cliente")
    st.caption("Los datos que aún no se conozcan se pueden completar posteriormente. * identifica campos obligatorios.")
    with st.form(key, clear_on_submit=not is_edit):
        st.markdown("**Identificación**")
        c1,c2 = st.columns(2)
        with c1:
            codigo = st.text_input("Código interno *", value=cur.get("codigo", ""), key=key+"code", max_chars=40)
            dep = smart_choice("Dependencia *", "dependencia", value=cur.get("dependencia", ""), key=key+"dep", allow_blank=False)
            correo = st.text_input("Correo corporativo", value=cur.get("correo") or "", key=key+"mail")
        with c2:
            nombre = st.text_input("Nombre completo *", value=cur.get("nombre", ""), key=key+"name", max_chars=180)
            cargo = smart_choice("Cargo", "cargo", value=cur.get("cargo", ""), key=key+"cargo")
            st.caption("Selecciona la Dependencia organizacional del cliente.")
        with st.expander("Estructura organizacional y gestión PMO", expanded=True):
            m1, m2, m3 = st.columns(3)
            equipo_trabajo = smart_choice("Equipo de trabajo", "equipo_trabajo", value=cur.get("equipo_trabajo", ""), key=key+"equipo", parent=m1)
            rol_especifico = smart_choice("Rol en proyectos/PMO", "rol_especifico", value=client_role(cur), key=key+"rol_especifico", parent=m2)
            estado_gestion = m3.text_input("Estado de gestión (fuente)", value=cur.get("estado_gestion", ""), key=key+"estado_gestion")
        with st.expander("Caracterización (opcional)"):
            t1,t2,t3 = st.columns(3)
            with t1:
                st.caption("El Rol se administra una sola vez en la estructura organizacional. Sus pesos se definen por criterio experto en cada corrida, sin recalcular históricos.")
                influencia = _select("Influencia", ["Sin evaluar", "Baja", "Media", "Alta"], cur.get("influencia", "Sin evaluar"), key+"inf")
            with t2:
                interes = _select("Interés", ["Sin evaluar", "Bajo", "Medio", "Alto"], cur.get("interes", "Sin evaluar"), key+"inter")
                conocimiento = _select("Conocimiento preliminar de PMO", ["Sin evaluar", "1", "2", "3", "4", "5"], str(cur.get("conocimiento")) if cur.get("conocimiento") is not None else "Sin evaluar", key+"know")
            with t3:
                participa = _select("Participación en proyectos", ["Sin evaluar", "Sí", "No"], cur.get("participa_proyectos", "Sin evaluar"), key+"proy")
                canal = _select("Canal preferido", ["", "Correo", "Teams", "Teléfono", "Presencial", "Otro"], cur.get("canal", ""), key+"canal")
        with st.expander("Necesidades y expectativas preliminares (opcional)"):
            retos = st.text_area("Retos mencionados", value=cur.get("retos", ""), key=key+"ret")
            necesidades = st.text_area("Necesidades preliminares (sin validar)", value=cur.get("necesidades_preliminares", ""), key=key+"nec")
            beneficios = st.text_area("Resultados o beneficios esperados", value=cur.get("beneficios_esperados", ""), key=key+"ben")
            barreras = st.text_area("Objeciones o barreras", value=cur.get("barreras", ""), key=key+"bar")
            observaciones = st.text_area("Observaciones", value=cur.get("observaciones", ""), key=key+"obs")
        with st.expander("Relacionamiento (opcional)"):
            responsable = smart_choice("Responsable PMO", "responsable", value=cur.get("responsable", ""), key=key+"resp")
            first = date.fromisoformat(cur["primer_contacto"]) if cur.get("primer_contacto") else None
            primer_contacto = st.date_input("Primer contacto (si ocurrió)", value=first, key=key+"date", format='YYYY/MM/DD')
            relacionamiento = _select("Estado de relacionamiento", ["Sin contacto", "Contactado", "En seguimiento", "Relacionado"], cur.get("relacionamiento", "Sin contacto"), key+"rel")
            embajador = st.checkbox("Embajador de la PMO", value=bool(cur.get("embajador", False)), key=key+"emb")
            activo = st.checkbox("Cliente activo", value=bool(cur.get("activo", True)), key=key+"act")
        actor = st.text_input("Registrado/modificado por *", placeholder="Nombre del responsable", key=key+"actor")
        sent = st.form_submit_button("Guardar cambios" if is_edit else "Registrar cliente", type="primary")
    if not sent:
        return
    payload = {
        "codigo":codigo,"nombre":nombre,"dependencia":dep,"cargo":cargo,"correo":correo,
        "sede":dep,"segmento":canonical_role(rol_especifico),"influencia":influencia,"interes":interes,
        "conocimiento":None if conocimiento=="Sin evaluar" else int(conocimiento),
        "participa_proyectos":participa,"canal":canal,"retos":retos,
        "necesidades_preliminares":necesidades,"beneficios_esperados":beneficios,
        "barreras":barreras,"observaciones":observaciones,"responsable":responsable,
        "primer_contacto":primer_contacto,"relacionamiento":relacionamiento,
        "embajador":embajador,"activo":activo,"equipo_trabajo":equipo_trabajo,
        "rol_especifico":canonical_role(rol_especifico),"estado_gestion":estado_gestion,
    }
    try:
        if is_edit:
            update_client(cur["id"], payload, actor)
            st.toast("Cliente actualizado. Se conservó el registro de cambios.")
            st.rerun()
        else:
            new_id = create_client(payload, actor)
            st.toast(f"Cliente registrado correctamente. ID: {new_id[:8]}...")
            st.rerun()
    except ValidationError as exc:
        st.error(str(exc))


def _csv_bytes(rows):
    fields = ["codigo", "nombre", "dependencia", "cargo", "correo", "sede", "segmento", "influencia", "interes", "conocimiento", "activo", "actualizado_en"]
    f = io.StringIO()
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    for r in rows:
        record = {}
        for k in fields:
            v = r.get(k)
            if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@")):
                v = "'" + v
            record[k] = v
        writer.writerow(record)
    return ("\ufeff"+f.getvalue()).encode("utf-8")

