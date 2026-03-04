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
ROLE_OPERATIONS_MANAGER = "operations_manager"
ROLE_MENU_OPERATOR = "menu_operator"
ROLE_CATALOG_EDITOR = "catalog_editor"
ROLE_NUTRITION_ANALYST = "nutrition_analyst"
ROLE_FINANCE_ANALYST = "finance_analyst"
ROLE_SECURITY_ADMIN = "security_admin"
ROLE_VIEWER = "viewer"

# Roles legacy mantenidos por compatibilidad con usuarios antiguos.
ROLE_MENU_MAINTAINER = "menu_maintainer"
ROLE_MENU_ONLY = "menu_only"
ROLE_HOME_ONLY = "home_only"

ROLE_ORDER = (
    ROLE_ADMIN,
    ROLE_OPERATIONS_MANAGER,
    ROLE_MENU_OPERATOR,
    ROLE_CATALOG_EDITOR,
    ROLE_NUTRITION_ANALYST,
    ROLE_FINANCE_ANALYST,
    ROLE_SECURITY_ADMIN,
    ROLE_VIEWER,
    ROLE_MENU_MAINTAINER,
    ROLE_MENU_ONLY,
    ROLE_HOME_ONLY,
)
ROLE_LABELS = {
    ROLE_ADMIN: "Administrador",
    ROLE_OPERATIONS_MANAGER: "Gestor Operaciones",
    ROLE_MENU_OPERATOR: "Operador Menu",
    ROLE_CATALOG_EDITOR: "Editor de Platos",
    ROLE_NUTRITION_ANALYST: "Analista Nutricion",
    ROLE_FINANCE_ANALYST: "Analista Finanzas",
    ROLE_SECURITY_ADMIN: "Administrador Seguridad",
    ROLE_VIEWER: "Solo Lectura Inicio",
    ROLE_MENU_MAINTAINER: "Mantenimiento Menu",
    ROLE_MENU_ONLY: "Solo Menu",
    ROLE_HOME_ONLY: "Solo Home",
}
ROLE_DESCRIPTIONS = {
    ROLE_ADMIN: "Control total del sistema, usuarios y seguridad.",
    ROLE_OPERATIONS_MANAGER: "Operacion diaria completa de menu, platos y reportes.",
    ROLE_MENU_OPERATOR: "Genera y consulta menu semanal sin editar catalogo.",
    ROLE_CATALOG_EDITOR: "Administra catalogo de platos sin acceso a reportes ni usuarios.",
    ROLE_NUTRITION_ANALYST: "Consulta menu y reportes para analisis nutricional.",
    ROLE_FINANCE_ANALYST: "Consulta reportes de costo sin gestion de menu/platos.",
    ROLE_SECURITY_ADMIN: "Gestiona usuarios y politicas de seguridad, sin operacion culinaria.",
    ROLE_VIEWER: "Acceso solo a la pantalla de inicio.",
    ROLE_MENU_MAINTAINER: "Legacy: equivalente funcional a Gestor Operaciones.",
    ROLE_MENU_ONLY: "Legacy: equivalente funcional a Operador Menu.",
    ROLE_HOME_ONLY: "Legacy: equivalente funcional a Solo Lectura Inicio.",
}
ROLE_IS_LEGACY = {
    ROLE_ADMIN: False,
    ROLE_OPERATIONS_MANAGER: False,
    ROLE_MENU_OPERATOR: False,
    ROLE_CATALOG_EDITOR: False,
    ROLE_NUTRITION_ANALYST: False,
    ROLE_FINANCE_ANALYST: False,
    ROLE_SECURITY_ADMIN: False,
    ROLE_VIEWER: False,
    ROLE_MENU_MAINTAINER: True,
    ROLE_MENU_ONLY: True,
    ROLE_HOME_ONLY: True,
}

PERMISSION_HOME = "home:view"
PERMISSION_MENU = "menu:view"
PERMISSION_DISHES = "dishes:manage"
PERMISSION_REPORTS = "reports:view"
PERMISSION_USERS = "users:manage"
PERMISSION_SECURITY = "security:manage"
PERMISSION_ORDER = (
    PERMISSION_HOME,
    PERMISSION_MENU,
    PERMISSION_DISHES,
    PERMISSION_REPORTS,
    PERMISSION_USERS,
    PERMISSION_SECURITY,
)
PERMISSION_LABELS = {
    PERMISSION_HOME: "Inicio",
    PERMISSION_MENU: "Menu semanal",
    PERMISSION_DISHES: "Platos",
    PERMISSION_REPORTS: "Reportes",
    PERMISSION_USERS: "Usuarios",
    PERMISSION_SECURITY: "Seguridad",
}

ROLE_PERMISSIONS = {
    ROLE_ADMIN: {
        PERMISSION_HOME,
        PERMISSION_MENU,
        PERMISSION_DISHES,
        PERMISSION_REPORTS,
        PERMISSION_USERS,
        PERMISSION_SECURITY,
    },
    ROLE_OPERATIONS_MANAGER: {PERMISSION_HOME, PERMISSION_MENU, PERMISSION_DISHES, PERMISSION_REPORTS},
    ROLE_MENU_OPERATOR: {PERMISSION_HOME, PERMISSION_MENU},
    ROLE_CATALOG_EDITOR: {PERMISSION_HOME, PERMISSION_DISHES},
    ROLE_NUTRITION_ANALYST: {PERMISSION_HOME, PERMISSION_MENU, PERMISSION_REPORTS},
    ROLE_FINANCE_ANALYST: {PERMISSION_HOME, PERMISSION_REPORTS},
    ROLE_SECURITY_ADMIN: {PERMISSION_HOME, PERMISSION_USERS, PERMISSION_SECURITY},
    ROLE_VIEWER: {PERMISSION_HOME},
    # Compatibilidad
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


def role_access_labels(role: str) -> list[str]:
    perms = role_permissions(role)
    return [PERMISSION_LABELS[item] for item in PERMISSION_ORDER if item in perms]


def role_catalog() -> list[dict[str, object]]:
    return [
        {
            "key": role,
            "label": ROLE_LABELS.get(role, role),
            "description": ROLE_DESCRIPTIONS.get(role, ""),
            "access_labels": role_access_labels(role),
            "is_legacy": ROLE_IS_LEGACY.get(role, False),
        }
        for role in ROLE_ORDER
    ]


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
