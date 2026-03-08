from __future__ import annotations

import random
from collections import Counter, defaultdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Dish, MEAL_TYPES, WeeklyMenu, WeeklyMenuItem

DAY_NAMES = ("Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo")
HOUSEHOLD_FACTORS = {
    "desayuno": 3.1,  # nino 2 anos + nino 5 anos + nino 12 anos + adulto
    "almuerzo": 3.1,
    "cena": 3.1,
    "lonchera": 2.1,  # normalmente lonchera para ninos
    "refresco": 3.1,
}


def normalize_week_start(target: date | None = None) -> date:
    value = target or date.today()
    return value - timedelta(days=value.weekday())


def parse_ingredients(raw: str) -> set[str]:
    return {part.strip().lower() for part in raw.split(",") if part.strip()}


def get_weekly_menu(session: Session, week_start: date) -> WeeklyMenu | None:
    stmt = (
        select(WeeklyMenu)
        .options(selectinload(WeeklyMenu.items).selectinload(WeeklyMenuItem.dish))
        .where(WeeklyMenu.week_start == week_start)
    )
    return session.scalar(stmt)


def get_previous_week_dish_ids(session: Session, week_start: date) -> dict[str, set[int]]:
    previous_start = week_start - timedelta(days=7)
    previous = get_weekly_menu(session, previous_start)
    result: dict[str, set[int]] = defaultdict(set)
    if not previous:
        return result
    for item in previous.items:
        result[item.meal_type].add(item.dish_id)
    return result


def _weight_candidate(dish: Dish, used_ingredients: set[str], times_selected: int) -> float:
    dish_ingredients = parse_ingredients(dish.ingredients)
    overlap = len(dish_ingredients.intersection(used_ingredients))

    reuse_bonus = 1 + overlap * 0.8
    cost_bonus = max(0.35, 2.4 - (dish.cost_per_serving / 5))
    health_bonus = 1.2 if dish.is_healthy else 0.9
    novelty_penalty = 1 / (1 + times_selected * 0.8)

    return max(0.05, reuse_bonus * cost_bonus * health_bonus * novelty_penalty)


def _item_cost(dish: Dish, meal_type: str) -> float:
    return round(dish.cost_per_serving * HOUSEHOLD_FACTORS.get(meal_type, 3.1), 2)


def _is_menu_complete(menu: WeeklyMenu) -> bool:
    required_slots = {(day_of_week, meal_type) for day_of_week in range(7) for meal_type in MEAL_TYPES}
    filled_slots = {
        (item.day_of_week, item.meal_type)
        for item in menu.items
        if item.dish is not None
    }
    return required_slots.issubset(filled_slots)


def generate_weekly_menu(session: Session, week_start: date, force: bool = False) -> WeeklyMenu:
    normalized = normalize_week_start(week_start)
    existing = get_weekly_menu(session, normalized)
    if existing and not force and _is_menu_complete(existing):
        return existing
    if existing:
        session.delete(existing)
        session.flush()

    dish_pool: dict[str, list[Dish]] = {}
    for meal_type in MEAL_TYPES:
        dishes = list(session.scalars(select(Dish).where(Dish.meal_type == meal_type, Dish.is_active.is_(True))).all())
        if not dishes:
            raise ValueError(f"No hay platos activos para el tipo de comida: {meal_type}")
        dish_pool[meal_type] = dishes

    previous_dish_ids = get_previous_week_dish_ids(session, normalized)
    menu = WeeklyMenu(week_start=normalized)
    session.add(menu)
    session.flush()

    used_ingredients: set[str] = set()
    selected_counts: Counter[int] = Counter()
    used_by_meal: dict[str, set[int]] = defaultdict(set)

    for day_of_week in range(7):
        for meal_type in MEAL_TYPES:
            candidates = dish_pool[meal_type]
            filtered = [dish for dish in candidates if dish.id not in previous_dish_ids.get(meal_type, set())]
            if not filtered:
                filtered = candidates

            unique_in_week = [dish for dish in filtered if dish.id not in used_by_meal[meal_type]]
            if unique_in_week:
                filtered = unique_in_week

            weights = [_weight_candidate(dish, used_ingredients, selected_counts[dish.id]) for dish in filtered]
            selected = random.choices(filtered, weights=weights, k=1)[0]

            used_ingredients.update(parse_ingredients(selected.ingredients))
            selected_counts[selected.id] += 1
            used_by_meal[meal_type].add(selected.id)

            item = WeeklyMenuItem(
                weekly_menu_id=menu.id,
                day_of_week=day_of_week,
                meal_type=meal_type,
                dish_id=selected.id,
                estimated_cost=_item_cost(selected, meal_type),
                nutrition_assessment=selected.warnings,
            )
            session.add(item)

    session.commit()
    return get_weekly_menu(session, normalized)  # type: ignore[return-value]
