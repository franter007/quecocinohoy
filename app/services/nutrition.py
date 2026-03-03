from __future__ import annotations


def evaluate_nutrition(
    calories: int,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
    fiber_g: float,
    sugar_g: float,
    sodium_mg: float,
) -> tuple[bool, str, str]:
    warnings: list[str] = []
    benefits: list[str] = []

    if protein_g >= 18:
        benefits.append("Buen aporte de proteina")
    if fiber_g >= 5:
        benefits.append("Aporta fibra para mejor digestion")
    if sugar_g <= 10:
        benefits.append("Bajo en azucares simples")
    if 350 <= calories <= 650:
        benefits.append("Calorias equilibradas para una comida principal")

    if calories > 800:
        warnings.append("Calorias elevadas para consumo frecuente")
    if sugar_g > 25:
        warnings.append("Azucar alta, riesgo metabolico")
    if sodium_mg > 900:
        warnings.append("Sodio alto, puede impactar la presion arterial")
    if fat_g > 35:
        warnings.append("Grasas elevadas para consumo diario")
    if fiber_g < 3:
        warnings.append("Baja fibra, puede afectar saciedad y digestion")

    is_healthy = len(warnings) <= 1
    if not benefits:
        benefits.append("Aporte nutricional moderado")
    if not warnings:
        warnings.append("Sin advertencias relevantes para consumo habitual")

    return is_healthy, "; ".join(benefits), "; ".join(warnings)

