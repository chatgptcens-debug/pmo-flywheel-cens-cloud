"""Catálogo visual V0.38. No altera etiquetas ni callbacks de widgets."""
from __future__ import annotations
from .design_system import kpi_icon
STEP_ICONS = ("home", "clipboard", "target", "workflow", "rocket", "settings", "chart", "refresh", "package", "award")
STAGE_TOKENS = {"explore":"#F45116", "design":"#D82D2B", "deploy":"#007EAC", "improve":"#15A7CE", "realize":"#6930A5"}
ICON_SIZES = (16, 20, 24, 32)
STAGE_BY_STEP = ("explore", "explore", "design", "design", "deploy", "deploy", "improve", "improve", "realize", "realize")

def icon_for_kpi(symbol: str) -> str:
    return kpi_icon(symbol)
