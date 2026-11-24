"""Controles de fecha uniformes para PMO Flywheel CENS.

Valores guardados como AAAA-MM-DD (ISO), apariencia AAAA/MM/DD.
Los campos de fecha opcionales no suponen una fecha por defecto.
"""
from __future__ import annotations
from datetime import date, datetime
import streamlit as st

DISPLAY_FORMAT = 'YYYY/MM/DD'

def parse_iso_date(raw):
    if isinstance(raw, date):
        return raw
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10].replace('/', '-'))
    except (ValueError, TypeError):
        return None

def iso_date_input(label, value='', *, container=None, key=None, disabled=False,
                   min_value=None, max_value=None, help=None):
    """Reemplazo de los antiguos campos de texto que guardaban fecha ISO."""
    widget = container if container is not None else st
    day = widget.date_input(label, value=parse_iso_date(value), format=DISPLAY_FORMAT,
                            key=key, disabled=disabled, min_value=min_value,
                            max_value=max_value, help=help)
    return day.isoformat() if day else ''
