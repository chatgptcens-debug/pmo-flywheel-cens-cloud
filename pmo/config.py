"""Configuración central; almacenamiento local fuera de carpetas sincronizadas."""
from __future__ import annotations
import os
from pathlib import Path

APP_NAME = "PMO FLYWHEEL CENS"
PALETTE = {
    "navy": "#10374B", "background": "#F5F7FA", "white": "#FFFFFF",
    "teal": "#00A6A6", "orange": "#E78B36", "text": "#243746",
    "muted": "#64748B", "border": "#E2E8F0",
}


CLOUD_EDITION = True


def data_dir() -> Path:
    from .cloud_runtime import session_data_dir
    return session_data_dir()


def database_path() -> Path:
    return data_dir() / "pmo_flywheel.sqlite3"
