from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import LoginAttempt
from app.services.runtime_settings import SecurityRuntimeSettings, load_security_settings


@dataclass
class LoginRisk:
    combo_failures: int
    username_failures: int
    ip_failures: int
    blocked_seconds: int
    challenge_required: bool


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").strip()
    if forwarded:
        candidate = forwarded.split(",")[0].strip()
        if candidate:
            return candidate
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def is_local_ip(ip_address: str) -> bool:
    return ip_address in {"127.0.0.1", "::1", "localhost"}


def _fail_count_and_last(
    session: Session,
    ip_address: str | None,
    username: str | None,
    floor: datetime,
) -> tuple[int, datetime | None]:
    conditions = [LoginAttempt.success.is_(False), LoginAttempt.created_at >= floor]
    if ip_address is not None:
        conditions.append(LoginAttempt.ip_address == ip_address)
    if username is not None:
        conditions.append(LoginAttempt.username == username)

    stmt = select(func.count(LoginAttempt.id), func.max(LoginAttempt.created_at)).where(*conditions)
    count, last = session.execute(stmt).one()
    return int(count or 0), last


def _to_utc_naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def analyze_login_risk(
    session: Session,
    ip_address: str,
    username: str | None,
    security: SecurityRuntimeSettings | None = None,
) -> LoginRisk:
    runtime = security or load_security_settings(session)

    if runtime.login_guard_trust_localhost and is_local_ip(ip_address):
        return LoginRisk(
            combo_failures=0,
            username_failures=0,
            ip_failures=0,
            blocked_seconds=0,
            challenge_required=False,
        )

    now = datetime.utcnow()
    floor = now - timedelta(minutes=runtime.login_window_minutes)
    normalized_username = (username or "").strip().lower()

    combo_failures = 0
    combo_last = None
    user_failures = 0
    user_last = None

    if normalized_username:
        combo_failures, combo_last = _fail_count_and_last(session, ip_address=ip_address, username=normalized_username, floor=floor)
        user_failures, user_last = _fail_count_and_last(session, ip_address=None, username=normalized_username, floor=floor)
        combo_last = _to_utc_naive(combo_last)
        user_last = _to_utc_naive(user_last)

    ip_failures, ip_last = _fail_count_and_last(session, ip_address=ip_address, username=None, floor=floor)
    ip_last = _to_utc_naive(ip_last)

    block_candidates: list[datetime] = []
    if combo_failures >= runtime.block_combo_fails and combo_last:
        block_candidates.append(combo_last + timedelta(minutes=runtime.block_combo_minutes))
    if user_failures >= runtime.block_user_fails and user_last:
        block_candidates.append(user_last + timedelta(minutes=runtime.block_user_minutes))
    if ip_failures >= runtime.block_ip_fails and ip_last:
        block_candidates.append(ip_last + timedelta(minutes=runtime.block_ip_minutes))

    blocked_seconds = 0
    if block_candidates:
        block_until = max(block_candidates)
        blocked_seconds = max(0, int((block_until - now).total_seconds()))

    challenge_required = (
        combo_failures >= runtime.challenge_combo_fails
        or user_failures >= runtime.challenge_user_fails
        or ip_failures >= runtime.challenge_ip_fails
    )

    return LoginRisk(
        combo_failures=combo_failures,
        username_failures=user_failures,
        ip_failures=ip_failures,
        blocked_seconds=blocked_seconds,
        challenge_required=challenge_required,
    )


def record_login_attempt(session: Session, username: str, ip_address: str, success: bool, reason: str = "") -> None:
    session.add(
        LoginAttempt(
            username=username.strip().lower(),
            ip_address=ip_address,
            success=success,
            reason=reason.strip()[:80],
        )
    )
    session.commit()


def suggest_failure_sleep_seconds(risk: LoginRisk) -> float:
    base = 0.18
    progressive = min(2.0, risk.combo_failures * 0.12 + risk.username_failures * 0.06)
    jitter = random.uniform(0.05, 0.2)
    return round(base + progressive + jitter, 2)


def format_blocked_seconds(seconds: int) -> str:
    if seconds <= 0:
        return "0 segundos"
    minutes, rem = divmod(seconds, 60)
    if minutes <= 0:
        return f"{rem} segundos"
    if rem == 0:
        return f"{minutes} minutos"
    return f"{minutes} min {rem} seg"


def generate_math_challenge() -> tuple[str, str]:
    op = random.choice(["+", "-", "*"])
    if op == "+":
        a = random.randint(8, 39)
        b = random.randint(2, 23)
        return f"Cuanto es {a} + {b}?", str(a + b)
    if op == "-":
        a = random.randint(20, 60)
        b = random.randint(2, 19)
        if b > a:
            a, b = b, a
        return f"Cuanto es {a} - {b}?", str(a - b)
    a = random.randint(3, 12)
    b = random.randint(2, 9)
    return f"Cuanto es {a} x {b}?", str(a * b)
