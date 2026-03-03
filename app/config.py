from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "si"}


@dataclass(frozen=True)
class Settings:
    session_secret_key: str
    admin_username: str
    admin_full_name: str
    admin_initial_password: str
    login_guard_trust_localhost: bool
    login_nonce_max_age_seconds: int


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        session_secret_key=os.getenv("SESSION_SECRET_KEY", "change-this-secret-key"),
        admin_username=os.getenv("ADMIN_USERNAME", "admin"),
        admin_full_name=os.getenv("ADMIN_FULL_NAME", "Administrador Principal"),
        admin_initial_password=os.getenv("ADMIN_INITIAL_PASSWORD", "admin123"),
        login_guard_trust_localhost=_as_bool(os.getenv("LOGIN_GUARD_TRUST_LOCALHOST"), True),
        login_nonce_max_age_seconds=int(os.getenv("LOGIN_NONCE_MAX_AGE_SECONDS", "900")),
    )

