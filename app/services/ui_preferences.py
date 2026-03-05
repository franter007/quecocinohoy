from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AppSetting

SHOW_NUTRITION_DETAILS_KEY_PREFIX = "ui.show_nutrition_details.user."


def _show_nutrition_key(user_id: int) -> str:
    return f"{SHOW_NUTRITION_DETAILS_KEY_PREFIX}{user_id}"


def get_show_nutrition_details(session: Session, user_id: int) -> bool:
    key = _show_nutrition_key(user_id)
    setting = session.scalar(select(AppSetting).where(AppSetting.key == key))
    if not setting:
        return False
    return setting.value.strip() in {"1", "true", "yes", "on", "si"}


def save_show_nutrition_details(session: Session, user_id: int, enabled: bool) -> None:
    key = _show_nutrition_key(user_id)
    setting = session.scalar(select(AppSetting).where(AppSetting.key == key))

    if not enabled:
        if setting:
            session.delete(setting)
            session.commit()
        return

    if setting:
        setting.value = "1"
    else:
        session.add(AppSetting(key=key, value="1"))
    session.commit()
