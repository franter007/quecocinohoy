from __future__ import annotations

from app.services.nutrition_rules import NutritionRuntimeRules, default_nutrition_rules


def evaluate_nutrition(
    calories: int,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
    fiber_g: float,
    sugar_g: float,
    sodium_mg: float,
    rules: NutritionRuntimeRules | None = None,
) -> tuple[bool, str, str]:
    active_rules = rules or default_nutrition_rules()
    warnings: list[str] = []
    benefits: list[str] = []

    if protein_g >= active_rules.benefit_protein_min:
        benefits.append("Buen aporte de proteina")
    if fiber_g >= active_rules.benefit_fiber_min:
        benefits.append("Aporta fibra para mejor digestion")
    if sugar_g <= active_rules.benefit_sugar_max:
        benefits.append("Bajo en azucares simples")
    if active_rules.benefit_calories_min <= calories <= active_rules.benefit_calories_max:
        benefits.append("Calorias equilibradas para una comida principal")

    if calories > active_rules.warning_calories_gt:
        warnings.append("Calorias elevadas para consumo frecuente")
    if sugar_g > active_rules.warning_sugar_gt:
        warnings.append("Azucar alta, riesgo metabolico")
    if sodium_mg > active_rules.warning_sodium_gt:
        warnings.append("Sodio alto, puede impactar la presion arterial")
    if fat_g > active_rules.warning_fat_gt:
        warnings.append("Grasas elevadas para consumo diario")
    if fiber_g < active_rules.warning_fiber_lt:
        warnings.append("Baja fibra, puede afectar saciedad y digestion")

    is_healthy = len(warnings) <= active_rules.healthy_max_warnings
    if not benefits:
        benefits.append("Aporte nutricional moderado")
    if not warnings:
        warnings.append("Sin advertencias relevantes para consumo habitual")

    return is_healthy, "; ".join(benefits), "; ".join(warnings)
