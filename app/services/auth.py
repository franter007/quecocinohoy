from __future__ import annotations

import hashlib
import hmac
import secrets
from base64 import urlsafe_b64decode, urlsafe_b64encode

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import User

ROLE_ADMIN = "admin"
ROLE_MENU_MAINTAINER = "menu_maintainer"
ROLE_MENU_ONLY = "menu_only"
ROLE_HOME_ONLY = "home_only"

ROLE_ORDER = (ROLE_ADMIN, ROLE_MENU_MAINTAINER, ROLE_MENU_ONLY, ROLE_HOME_ONLY)
ROLE_LABELS = {
    ROLE_ADMIN: "Administrador",
    ROLE_MENU_MAINTAINER: "Mantenimiento Menu",
    ROLE_MENU_ONLY: "Solo Menu",
    ROLE_HOME_ONLY: "Solo Home",
}

PERMISSION_HOME = "home:view"
PERMISSION_MENU = "menu:view"
PERMISSION_DISHES = "dishes:manage"
PERMISSION_REPORTS = "reports:view"
PERMISSION_USERS = "users:manage"

ROLE_PERMISSIONS = {
    ROLE_ADMIN: {PERMISSION_HOME, PERMISSION_MENU, PERMISSION_DISHES, PERMISSION_REPORTS, PERMISSION_USERS},
    ROLE_MENU_MAINTAINER: {PERMISSION_HOME, PERMISSION_MENU, PERMISSION_DISHES, PERMISSION_REPORTS},
    ROLE_MENU_ONLY: {PERMISSION_HOME, PERMISSION_MENU},
    ROLE_HOME_ONLY: {PERMISSION_HOME},
}

SETTINGS = get_settings()
DEFAULT_ADMIN_USERNAME = SETTINGS.admin_username
DEFAULT_ADMIN_FULLNAME = SETTINGS.admin_full_name
DEFAULT_ADMIN_PASSWORD = SETTINGS.admin_initial_password


def role_permissions(role: str) -> set[str]:
    return set(ROLE_PERMISSIONS.get(role, set()))


def has_permission(role: str, permission: str) -> bool:
    return permission in role_permissions(role)


def hash_password(password: str, iterations: int = 240_000) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "pbkdf2_sha256$%d$%s$%s" % (
        iterations,
        urlsafe_b64encode(salt).decode("ascii"),
        urlsafe_b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algo, iterations_s, salt_b64, digest_b64 = password_hash.split("$", 3)
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    try:
        iterations = int(iterations_s)
        salt = urlsafe_b64decode(salt_b64.encode("ascii"))
        expected = urlsafe_b64decode(digest_b64.encode("ascii"))
    except Exception:
        return False
    got = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(got, expected)


def authenticate_user(session: Session, username: str, password: str) -> User | None:
    stmt = select(User).where(User.username == username.strip())
    user = session.scalar(stmt)
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def ensure_admin_user(session: Session) -> User:
    admin = session.scalar(select(User).where(User.username == DEFAULT_ADMIN_USERNAME))
    if admin:
        return admin

    user = User(
        username=DEFAULT_ADMIN_USERNAME,
        full_name=DEFAULT_ADMIN_FULLNAME,
        role=ROLE_ADMIN,
        password_hash=hash_password(DEFAULT_ADMIN_PASSWORD),
        is_active=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user
