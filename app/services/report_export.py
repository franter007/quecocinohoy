from __future__ import annotations

from datetime import date

from app.models import MEAL_TYPES
from app.services.export_table import build_table_pdf_bytes, build_table_png_bytes

REPORT_EXPORT_COLUMN_ORDER = [
    "date",
    "iso_week",
    "month",
    "total",
    "desayuno",
    "almuerzo",
    "cena",
    "lonchera",
    "refresco",
    "calories",
    "protein_g",
    "carbs_g",
    "fat_g",
    "fiber_g",
    "sugar_g",
]
REPORT_EXPORT_PRESETS = {
    "completo": list(REPORT_EXPORT_COLUMN_ORDER),
    "resumen": ["date", "iso_week", "month", "total", "calories"],
    "finanzas": ["date", "iso_week", "month", "total", "desayuno", "almuerzo", "cena", "lonchera", "refresco"],
    "nutricion": ["date", "calories", "protein_g", "carbs_g", "fat_g", "fiber_g", "sugar_g"],
}
REPORT_EXPORT_PRESET_LABELS = {
    "completo": "Completo",
    "resumen": "Resumen",
    "finanzas": "Finanzas",
    "nutricion": "Nutricion",
}

REPORT_EXPORT_LABELS = {
    "date": "Fecha",
    "iso_week": "Semana ISO",
    "month": "Mes",
    "total": "Gasto total",
    "desayuno": "Desayuno",
    "almuerzo": "Almuerzo",
    "cena": "Cena",
    "lonchera": "Lonchera",
    "refresco": "Refresco",
    "calories": "Calorias",
    "protein_g": "Proteina (g)",
    "carbs_g": "Carbohidratos (g)",
    "fat_g": "Grasas (g)",
    "fiber_g": "Fibra (g)",
    "sugar_g": "Azucar (g)",
}

MONEY_COLUMNS = {"total", "desayuno", "almuerzo", "cena", "lonchera", "refresco"}
DECIMAL_COLUMNS = {"protein_g", "carbs_g", "fat_g", "fiber_g", "sugar_g"}
INT_COLUMNS = {"calories"}


def normalize_report_export_columns(columns: list[str] | None) -> list[str]:
    if not columns:
        return list(REPORT_EXPORT_PRESETS["completo"])
    selected = [key for key in REPORT_EXPORT_COLUMN_ORDER if key in columns]
    return selected or list(REPORT_EXPORT_PRESETS["completo"])


def resolve_report_export_columns(columns: list[str] | None, preset: str | None) -> list[str]:
    if preset and preset in REPORT_EXPORT_PRESETS:
        return list(REPORT_EXPORT_PRESETS[preset])
    return normalize_report_export_columns(columns)


def report_export_choices() -> list[dict[str, str]]:
    return [{"key": key, "label": REPORT_EXPORT_LABELS[key]} for key in REPORT_EXPORT_COLUMN_ORDER]


def report_export_presets() -> list[dict[str, str]]:
    return [{"key": key, "label": REPORT_EXPORT_PRESET_LABELS[key]} for key in REPORT_EXPORT_PRESETS]


def _build_daily_map(report: dict) -> list[dict]:
    by_date: dict[date, dict] = {}
    for row in report.get("daily", []):
        d = row["date"]
        by_date[d] = {
            "date": d,
            "total": row["total"],
            **{meal: 0.0 for meal in MEAL_TYPES},
            "calories": 0.0,
            "protein_g": 0.0,
            "carbs_g": 0.0,
            "fat_g": 0.0,
            "fiber_g": 0.0,
            "sugar_g": 0.0,
        }

    for row in report.get("daily_breakdown", []):
        d = row["date"]
        target = by_date.get(d)
        if not target:
            continue
        for meal in MEAL_TYPES:
            target[meal] = row.get(meal, 0.0)

    for row in report.get("nutrition_daily", []):
        d = row["date"]
        target = by_date.get(d)
        if not target:
            continue
        target["calories"] = row.get("calories", 0.0)
        target["protein_g"] = row.get("protein_g", 0.0)
        target["carbs_g"] = row.get("carbs_g", 0.0)
        target["fat_g"] = row.get("fat_g", 0.0)
        target["fiber_g"] = row.get("fiber_g", 0.0)
        target["sugar_g"] = row.get("sugar_g", 0.0)

    rows = []
    for d, row in sorted(by_date.items()):
        iso = d.isocalendar()
        row["iso_week"] = f"{iso.year}-W{iso.week:02d}"
        row["month"] = d.strftime("%Y-%m")
        rows.append(row)
    return rows


def _format_value(key: str, value: object) -> str:
    if key == "date" and isinstance(value, date):
        return value.isoformat()
    if key in MONEY_COLUMNS:
        return f"S/ {float(value):.2f}"
    if key in DECIMAL_COLUMNS:
        return f"{float(value):.1f}"
    if key in INT_COLUMNS:
        return str(round(float(value)))
    return str(value)


def _build_report_table(report: dict, selected_columns: list[str]) -> tuple[list[str], list[list[str]]]:
    headers = [REPORT_EXPORT_LABELS[key] for key in selected_columns]
    rows = _build_daily_map(report)
    body: list[list[str]] = []
    for row in rows:
        body.append([_format_value(key, row.get(key, "")) for key in selected_columns])
    return headers, body


def build_report_pdf_bytes(
    start: date,
    end: date,
    report: dict,
    selected_columns: list[str],
) -> bytes:
    headers, body = _build_report_table(report, selected_columns)
    return build_table_pdf_bytes(
        title="Reporte de gastos y nutricion",
        subtitle=f"Periodo {start.isoformat()} a {end.isoformat()}",
        headers=headers,
        rows=body,
    )


def build_report_png_bytes(
    start: date,
    end: date,
    report: dict,
    selected_columns: list[str],
) -> bytes:
    headers, body = _build_report_table(report, selected_columns)
    return build_table_png_bytes(
        title="Reporte de gastos y nutricion",
        subtitle=f"Periodo {start.isoformat()} a {end.isoformat()}",
        headers=headers,
        rows=body,
    )
