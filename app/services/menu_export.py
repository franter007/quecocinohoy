from __future__ import annotations

from datetime import date
from typing import Any

from app.services.export_table import build_table_pdf_bytes, build_table_png_bytes

MENU_EXPORT_COLUMN_ORDER = ["day_name", "desayuno", "almuerzo", "cena", "lonchera", "refresco", "daily_total"]
MENU_EXPORT_FIXED_LABELS = {
    "day_name": "Dia",
    "daily_total": "Costo dia",
}
MENU_EXPORT_PRESETS = {
    "completo": ["day_name", "desayuno", "almuerzo", "cena", "lonchera", "refresco", "daily_total"],
    "resumen": ["day_name", "desayuno", "almuerzo", "cena", "daily_total"],
    "finanzas": ["day_name", "almuerzo", "cena", "daily_total"],
    "nutricion": ["day_name", "desayuno", "almuerzo", "cena", "lonchera", "refresco"],
}
MENU_EXPORT_PRESET_LABELS = {
    "completo": "Completo",
    "resumen": "Resumen",
    "finanzas": "Finanzas",
    "nutricion": "Nutricion",
}


def _allowed_menu_columns(meal_labels: dict[str, str]) -> list[str]:
    return [key for key in MENU_EXPORT_COLUMN_ORDER if key in MENU_EXPORT_FIXED_LABELS or key in meal_labels]


def normalize_menu_export_columns(columns: list[str] | None, meal_labels: dict[str, str]) -> list[str]:
    allowed = _allowed_menu_columns(meal_labels)
    if not columns:
        return list(MENU_EXPORT_PRESETS["completo"])
    selected = [key for key in MENU_EXPORT_COLUMN_ORDER if key in columns and key in allowed]
    return selected or list(MENU_EXPORT_PRESETS["completo"])


def resolve_menu_export_columns(columns: list[str] | None, preset: str | None, meal_labels: dict[str, str]) -> list[str]:
    allowed = [key for key in MENU_EXPORT_COLUMN_ORDER if key in MENU_EXPORT_FIXED_LABELS or key in meal_labels]
    if preset and preset in MENU_EXPORT_PRESETS:
        return [key for key in MENU_EXPORT_PRESETS[preset] if key in allowed]
    selected = normalize_menu_export_columns(columns, meal_labels)
    return [key for key in selected if key in allowed]


def menu_export_choices(meal_labels: dict[str, str]) -> list[dict[str, str]]:
    choices: list[dict[str, str]] = []
    for key in MENU_EXPORT_COLUMN_ORDER:
        if key in MENU_EXPORT_FIXED_LABELS:
            choices.append({"key": key, "label": MENU_EXPORT_FIXED_LABELS[key]})
        elif key in meal_labels:
            choices.append({"key": key, "label": meal_labels[key]})
    return choices


def menu_export_presets() -> list[dict[str, str]]:
    return [{"key": key, "label": MENU_EXPORT_PRESET_LABELS[key]} for key in MENU_EXPORT_PRESETS]


def _menu_cell_text(item: Any) -> str:
    if not item:
        return "-"
    warning = item.dish.warnings or "Sin advertencias"
    return f"{item.dish.name}\nS/ {item.estimated_cost:.2f}\n{warning}"


def _menu_value(row: dict, key: str) -> str:
    if key == "day_name":
        return row["day_name"]
    if key == "daily_total":
        return f"S/ {row['daily_total']:.2f}"
    return _menu_cell_text(row["meals"].get(key))


def _build_menu_table(
    rows: list[dict],
    meal_labels: dict[str, str],
    selected_columns: list[str],
) -> tuple[list[str], list[list[str]]]:
    headers: list[str] = []
    for key in selected_columns:
        if key in MENU_EXPORT_FIXED_LABELS:
            headers.append(MENU_EXPORT_FIXED_LABELS[key])
        else:
            headers.append(meal_labels[key])

    body = [[_menu_value(row, key) for key in selected_columns] for row in rows]
    return headers, body


def build_menu_pdf_bytes(
    week_start: date,
    rows: list[dict],
    total_cost: float,
    meal_labels: dict[str, str],
    selected_columns: list[str],
) -> bytes:
    headers, body = _build_menu_table(rows, meal_labels, selected_columns)
    return build_table_pdf_bytes(
        title="Menu semanal familiar",
        subtitle=f"Semana {week_start.isoformat()} - Total estimado: S/ {total_cost:.2f}",
        headers=headers,
        rows=body,
    )


def build_menu_png_bytes(
    week_start: date,
    rows: list[dict],
    total_cost: float,
    meal_labels: dict[str, str],
    selected_columns: list[str],
) -> bytes:
    headers, body = _build_menu_table(rows, meal_labels, selected_columns)
    return build_table_png_bytes(
        title="Menu semanal familiar",
        subtitle=f"Semana {week_start.isoformat()} | Total estimado: S/ {total_cost:.2f}",
        headers=headers,
        rows=body,
    )
