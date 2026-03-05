from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AppSetting


@dataclass(frozen=True)
class NutritionRuleDefinition:
    key: str
    attr: str
    label: str
    default: int
    min_value: int
    max_value: int
    description: str
    example: str


@dataclass(frozen=True)
class NutritionRuntimeRules:
    benefit_protein_min: int
    benefit_fiber_min: int
    benefit_sugar_max: int
    benefit_calories_min: int
    benefit_calories_max: int
    warning_calories_gt: int
    warning_sugar_gt: int
    warning_sodium_gt: int
    warning_fat_gt: int
    warning_fiber_lt: int
    healthy_max_warnings: int


NUTRITION_RULE_DEFINITIONS: tuple[NutritionRuleDefinition, ...] = (
    NutritionRuleDefinition(
        key="nutrition.benefit_protein_min",
        attr="benefit_protein_min",
        label="Beneficio: proteina minima (g)",
        default=18,
        min_value=0,
        max_value=120,
        description="Si el plato llega a este valor, agrega beneficio de proteina.",
        example="18 = 'Buen aporte de proteina'.",
    ),
    NutritionRuleDefinition(
        key="nutrition.benefit_fiber_min",
        attr="benefit_fiber_min",
        label="Beneficio: fibra minima (g)",
        default=5,
        min_value=0,
        max_value=80,
        description="Si el plato llega a este valor, agrega beneficio de fibra.",
        example="5 = 'Aporta fibra para mejor digestion'.",
    ),
    NutritionRuleDefinition(
        key="nutrition.benefit_sugar_max",
        attr="benefit_sugar_max",
        label="Beneficio: azucar maxima (g)",
        default=10,
        min_value=0,
        max_value=120,
        description="Si el azucar es menor o igual, agrega beneficio de azucares controlados.",
        example="10 = 'Bajo en azucares simples'.",
    ),
    NutritionRuleDefinition(
        key="nutrition.benefit_calories_min",
        attr="benefit_calories_min",
        label="Beneficio: calorias minimas",
        default=350,
        min_value=0,
        max_value=3000,
        description="Inicio del rango de calorias equilibradas para plato principal.",
        example="350 como limite inferior.",
    ),
    NutritionRuleDefinition(
        key="nutrition.benefit_calories_max",
        attr="benefit_calories_max",
        label="Beneficio: calorias maximas",
        default=650,
        min_value=0,
        max_value=3000,
        description="Fin del rango de calorias equilibradas para plato principal.",
        example="650 como limite superior.",
    ),
    NutritionRuleDefinition(
        key="nutrition.warning_calories_gt",
        attr="warning_calories_gt",
        label="Alerta: calorias mayores a",
        default=800,
        min_value=0,
        max_value=5000,
        description="Si calorias supera este valor, agrega alerta de exceso calorico.",
        example=">800 = 'Calorias elevadas'.",
    ),
    NutritionRuleDefinition(
        key="nutrition.warning_sugar_gt",
        attr="warning_sugar_gt",
        label="Alerta: azucar mayor a (g)",
        default=25,
        min_value=0,
        max_value=400,
        description="Si azucar supera este valor, agrega alerta metabolica.",
        example=">25 = 'Azucar alta'.",
    ),
    NutritionRuleDefinition(
        key="nutrition.warning_sodium_gt",
        attr="warning_sodium_gt",
        label="Alerta: sodio mayor a (mg)",
        default=900,
        min_value=0,
        max_value=10000,
        description="Si sodio supera este valor, agrega alerta de presion arterial.",
        example=">900 = 'Sodio alto'.",
    ),
    NutritionRuleDefinition(
        key="nutrition.warning_fat_gt",
        attr="warning_fat_gt",
        label="Alerta: grasa mayor a (g)",
        default=35,
        min_value=0,
        max_value=300,
        description="Si grasa supera este valor, agrega alerta por exceso de grasas.",
        example=">35 = 'Grasas elevadas'.",
    ),
    NutritionRuleDefinition(
        key="nutrition.warning_fiber_lt",
        attr="warning_fiber_lt",
        label="Alerta: fibra menor a (g)",
        default=3,
        min_value=0,
        max_value=120,
        description="Si fibra es menor a este valor, agrega alerta por baja saciedad.",
        example="<3 = 'Baja fibra'.",
    ),
    NutritionRuleDefinition(
        key="nutrition.healthy_max_warnings",
        attr="healthy_max_warnings",
        label="Saludable con maximo de alertas",
        default=1,
        min_value=0,
        max_value=10,
        description="Cantidad maxima de alertas permitidas para marcar plato como saludable.",
        example="1 = 0 o 1 alerta es 'Saludable'.",
    ),
)

_DEFS_BY_KEY = {item.key: item for item in NUTRITION_RULE_DEFINITIONS}


def default_nutrition_rules() -> NutritionRuntimeRules:
    values = {item.attr: item.default for item in NUTRITION_RULE_DEFINITIONS}
    return NutritionRuntimeRules(**values)


def list_nutrition_rule_definitions() -> tuple[NutritionRuleDefinition, ...]:
    return NUTRITION_RULE_DEFINITIONS


def _load_raw_values(session: Session) -> dict[str, str]:
    keys = [item.key for item in NUTRITION_RULE_DEFINITIONS]
    rows = session.scalars(select(AppSetting).where(AppSetting.key.in_(keys))).all()
    return {row.key: row.value for row in rows}


def _coerce_value(definition: NutritionRuleDefinition, raw_value: str | None) -> int:
    try:
        parsed = int((raw_value or "").strip())
    except ValueError:
        parsed = definition.default

    if parsed < definition.min_value:
        parsed = definition.min_value
    if parsed > definition.max_value:
        parsed = definition.max_value
    return parsed


def load_nutrition_rules(session: Session) -> NutritionRuntimeRules:
    raw_values = _load_raw_values(session)
    values: dict[str, int] = {}
    for definition in NUTRITION_RULE_DEFINITIONS:
        values[definition.attr] = _coerce_value(definition, raw_values.get(definition.key))
    return NutritionRuntimeRules(**values)


def build_nutrition_form_fields(
    session: Session,
    form_values: Mapping[str, str] | None = None,
) -> list[dict]:
    raw_values = _load_raw_values(session)
    effective = load_nutrition_rules(session)
    fields: list[dict] = []
    for definition in NUTRITION_RULE_DEFINITIONS:
        if form_values is not None:
            current_raw = str(form_values.get(definition.key, "")).strip()
            if not current_raw:
                current_raw = str(getattr(effective, definition.attr))
        else:
            current_raw = raw_values.get(definition.key, str(getattr(effective, definition.attr)))

        fields.append(
            {
                "key": definition.key,
                "label": definition.label,
                "value": current_raw,
                "default_value": str(definition.default),
                "effective_value": str(getattr(effective, definition.attr)),
                "description": definition.description,
                "example": definition.example,
                "min_value": definition.min_value,
                "max_value": definition.max_value,
                "is_overridden": definition.key in raw_values,
            }
        )
    return fields


def validate_nutrition_form_values(form_values: Mapping[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    cleaned: dict[str, str] = {}
    errors: dict[str, str] = {}
    for definition in NUTRITION_RULE_DEFINITIONS:
        raw_value = str(form_values.get(definition.key, "")).strip()
        if not raw_value:
            errors[definition.key] = "Este valor es obligatorio."
            continue
        try:
            parsed = int(raw_value)
        except ValueError:
            errors[definition.key] = "Ingresa un numero entero."
            continue
        if parsed < definition.min_value:
            errors[definition.key] = f"Debe ser mayor o igual a {definition.min_value}."
            continue
        if parsed > definition.max_value:
            errors[definition.key] = f"Debe ser menor o igual a {definition.max_value}."
            continue
        cleaned[definition.key] = str(parsed)

    min_calories_key = "nutrition.benefit_calories_min"
    max_calories_key = "nutrition.benefit_calories_max"
    if min_calories_key in cleaned and max_calories_key in cleaned:
        if int(cleaned[min_calories_key]) > int(cleaned[max_calories_key]):
            errors[max_calories_key] = "Debe ser mayor o igual al minimo de calorias."

    return cleaned, errors


def save_nutrition_rules(session: Session, values: Mapping[str, str]) -> None:
    keys = [item.key for item in NUTRITION_RULE_DEFINITIONS]
    existing = session.scalars(select(AppSetting).where(AppSetting.key.in_(keys))).all()
    by_key = {row.key: row for row in existing}

    for key, raw_value in values.items():
        definition = _DEFS_BY_KEY.get(key)
        if not definition:
            continue

        default_value = str(definition.default)
        current = by_key.get(key)
        if raw_value == default_value:
            if current:
                session.delete(current)
            continue

        if current:
            current.value = raw_value
        else:
            session.add(AppSetting(key=key, value=raw_value))

    session.commit()
