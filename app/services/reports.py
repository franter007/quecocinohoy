from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Dish, MEAL_TYPES, WeeklyMenu, WeeklyMenuItem


def default_range() -> tuple[date, date]:
    today = date.today()
    start = today.replace(day=1)
    end = today
    return start, end


def build_cost_report(session: Session, start: date, end: date) -> dict:
    floor = start - timedelta(days=6)
    ceiling = end

    stmt = (
        select(WeeklyMenu.week_start, WeeklyMenuItem, Dish)
        .join(WeeklyMenuItem, WeeklyMenuItem.weekly_menu_id == WeeklyMenu.id)
        .join(Dish, Dish.id == WeeklyMenuItem.dish_id)
        .where(WeeklyMenu.week_start.between(floor, ceiling))
        .order_by(WeeklyMenu.week_start, WeeklyMenuItem.day_of_week)
    )

    daily_totals: dict[date, float] = defaultdict(float)
    weekly_totals: dict[str, float] = defaultdict(float)
    monthly_totals: dict[str, float] = defaultdict(float)
    meal_type_totals: dict[str, float] = defaultdict(float)
    daily_by_meal_type: dict[date, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    nutrition_daily: dict[date, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for week_start, item, dish in session.execute(stmt):
        day_date = week_start + timedelta(days=item.day_of_week)
        if day_date < start or day_date > end:
            continue

        daily_totals[day_date] += item.estimated_cost
        iso = day_date.isocalendar()
        week_key = f"{iso.year}-W{iso.week:02d}"
        monthly_key = day_date.strftime("%Y-%m")

        weekly_totals[week_key] += item.estimated_cost
        monthly_totals[monthly_key] += item.estimated_cost
        meal_type_totals[item.meal_type] += item.estimated_cost
        daily_by_meal_type[day_date][item.meal_type] += item.estimated_cost

        factor = (item.estimated_cost / dish.cost_per_serving) if dish.cost_per_serving > 0 else 1
        nutrition_daily[day_date]["calories"] += dish.calories * factor
        nutrition_daily[day_date]["protein_g"] += dish.protein_g * factor
        nutrition_daily[day_date]["carbs_g"] += dish.carbs_g * factor
        nutrition_daily[day_date]["fat_g"] += dish.fat_g * factor
        nutrition_daily[day_date]["fiber_g"] += dish.fiber_g * factor
        nutrition_daily[day_date]["sugar_g"] += dish.sugar_g * factor

    return {
        "start": start,
        "end": end,
        "total_cost": round(sum(daily_totals.values()), 2),
        "daily": [{"date": d, "total": round(total, 2)} for d, total in sorted(daily_totals.items())],
        "weekly": [{"week": w, "total": round(total, 2)} for w, total in sorted(weekly_totals.items())],
        "monthly": [{"month": m, "total": round(total, 2)} for m, total in sorted(monthly_totals.items())],
        "by_meal_type": [{"meal_type": m, "total": round(total, 2)} for m, total in sorted(meal_type_totals.items())],
        "daily_breakdown": [
            {
                "date": d,
                **{meal: round(values.get(meal, 0.0), 2) for meal in MEAL_TYPES},
            }
            for d, values in sorted(daily_by_meal_type.items())
        ],
        "nutrition_daily": [
            {
                "date": d,
                "calories": round(values["calories"], 0),
                "protein_g": round(values["protein_g"], 1),
                "carbs_g": round(values["carbs_g"], 1),
                "fat_g": round(values["fat_g"], 1),
                "fiber_g": round(values["fiber_g"], 1),
                "sugar_g": round(values["sugar_g"], 1),
            }
            for d, values in sorted(nutrition_daily.items())
        ],
    }
