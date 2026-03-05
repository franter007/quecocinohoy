from __future__ import annotations

import hashlib
import hmac
import secrets
from base64 import urlsafe_b64decode, urlsafe_b64encode

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import User

ACCESS_NONE = 0
ACCESS_READ = 1
ACCESS_WRITE = 2
ACCESS_ADMIN = 3

ACCESS_TYPE_LABELS = {
    ACCESS_NONE: "Sin acceso",
    ACCESS_READ: "Lectura",
    ACCESS_WRITE: "Escritura",
    ACCESS_ADMIN: "Admin",
}
ACCESS_TYPE_STYLE = {
    ACCESS_NONE: "secondary",
    ACCESS_READ: "info",
    ACCESS_WRITE: "primary",
    ACCESS_ADMIN: "danger",
}

SECTION_HOME = "home"
SECTION_MENU = "menu"
SECTION_DISHES = "dishes"
SECTION_REPORTS = "reports"
SECTION_USERS = "users"
SECTION_SECURITY = "security"

SECTION_ORDER = (
    SECTION_HOME,
    SECTION_MENU,
    SECTION_DISHES,
    SECTION_REPORTS,
    SECTION_USERS,
    SECTION_SECURITY,
)
SECTION_LABELS = {
    SECTION_HOME: "Inicio",
    SECTION_MENU: "Menu semanal",
    SECTION_DISHES: "Platos",
    SECTION_REPORTS: "Reportes",
    SECTION_USERS: "Usuarios",
    SECTION_SECURITY: "Seguridad",
}

# Roles escalonados recomendados.
ROLE_HOME_READER = "home_reader"
ROLE_MENU_READER = "menu_reader"
ROLE_MENU_WRITER = "menu_writer"
ROLE_DISHES_WRITER = "dishes_writer"
ROLE_DISHES_ADMIN = "dishes_admin"
ROLE_REPORTS_READER = "reports_reader"
ROLE_PLATFORM_ADMIN = "platform_admin"
ROLE_ADMIN = "admin"

# Roles legacy mantenidos por compatibilidad con usuarios ya creados.
ROLE_OPERATIONS_MANAGER = "operations_manager"
ROLE_MENU_OPERATOR = "menu_operator"
ROLE_CATALOG_EDITOR = "catalog_editor"
ROLE_NUTRITION_ANALYST = "nutrition_analyst"
ROLE_FINANCE_ANALYST = "finance_analyst"
ROLE_SECURITY_ADMIN = "security_admin"
ROLE_VIEWER = "viewer"
ROLE_MENU_MAINTAINER = "menu_maintainer"
ROLE_MENU_ONLY = "menu_only"
ROLE_HOME_ONLY = "home_only"

ROLE_ORDER = (
    ROLE_HOME_READER,
    ROLE_MENU_READER,
    ROLE_MENU_WRITER,
    ROLE_DISHES_WRITER,
    ROLE_REPORTS_READER,
    ROLE_DISHES_ADMIN,
    ROLE_PLATFORM_ADMIN,
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
    ROLE_HOME_READER: "Nivel 1 - Inicio",
    ROLE_MENU_READER: "Nivel 2 - Menu Lectura",
    ROLE_MENU_WRITER: "Nivel 3 - Menu Escritura",
    ROLE_DISHES_WRITER: "Nivel 4 - Platos Escritura",
    ROLE_REPORTS_READER: "Nivel 5 - Reportes",
    ROLE_DISHES_ADMIN: "Nivel 6 - Platos Admin",
    ROLE_PLATFORM_ADMIN: "Nivel 7 - Gestion",
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
    ROLE_HOME_READER: "Solo dashboard inicial. Ejemplo: duenio de casa que solo revisa el estado semanal.",
    ROLE_MENU_READER: "Inicio + menu semanal lectura. Ejemplo: familiar que revisa el plan sin modificarlo.",
    ROLE_MENU_WRITER: "Inicio + menu con generacion/regeneracion. Ejemplo: planner que arma el menu de la semana.",
    ROLE_DISHES_WRITER: "Incluye platos en escritura (crear/editar, sin eliminar). Ejemplo: asistente de cocina.",
    ROLE_REPORTS_READER: "Incluye reportes de gasto sin borrar platos. Ejemplo: quien monitorea presupuesto familiar.",
    ROLE_DISHES_ADMIN: "Incluye admin de platos (crear/editar/eliminar). Ejemplo: responsable del catalogo culinario.",
    ROLE_PLATFORM_ADMIN: "Incluye gestion de usuarios y seguridad operativa. Ejemplo: coordinador del hogar/plataforma.",
    ROLE_ADMIN: "Control total del sistema. Ejemplo: propietario de la aplicacion.",
    ROLE_OPERATIONS_MANAGER: "Legacy: operacion diaria completa de menu, platos y reportes.",
    ROLE_MENU_OPERATOR: "Legacy: genera y consulta menu semanal.",
    ROLE_CATALOG_EDITOR: "Legacy: administra catalogo de platos.",
    ROLE_NUTRITION_ANALYST: "Legacy: consulta menu y reportes nutricionales.",
    ROLE_FINANCE_ANALYST: "Legacy: consulta reportes de costo.",
    ROLE_SECURITY_ADMIN: "Legacy: gestiona usuarios y politicas de seguridad.",
    ROLE_VIEWER: "Legacy: solo inicio.",
    ROLE_MENU_MAINTAINER: "Legacy: equivalente funcional a gestion operativa.",
    ROLE_MENU_ONLY: "Legacy: equivalente funcional a menu escritura.",
    ROLE_HOME_ONLY: "Legacy: equivalente funcional a inicio lectura.",
}

ROLE_IS_LEGACY = {
    ROLE_HOME_READER: False,
    ROLE_MENU_READER: False,
    ROLE_MENU_WRITER: False,
    ROLE_DISHES_WRITER: False,
    ROLE_DISHES_ADMIN: False,
    ROLE_REPORTS_READER: False,
    ROLE_PLATFORM_ADMIN: False,
    ROLE_ADMIN: False,
    ROLE_OPERATIONS_MANAGER: True,
    ROLE_MENU_OPERATOR: True,
    ROLE_CATALOG_EDITOR: True,
    ROLE_NUTRITION_ANALYST: True,
    ROLE_FINANCE_ANALYST: True,
    ROLE_SECURITY_ADMIN: True,
    ROLE_VIEWER: True,
    ROLE_MENU_MAINTAINER: True,
    ROLE_MENU_ONLY: True,
    ROLE_HOME_ONLY: True,
}

ROLE_ACCESS_MATRIX: dict[str, dict[str, int]] = {
    ROLE_HOME_READER: {
        SECTION_HOME: ACCESS_READ,
    },
    ROLE_MENU_READER: {
        SECTION_HOME: ACCESS_READ,
        SECTION_MENU: ACCESS_READ,
    },
    ROLE_MENU_WRITER: {
        SECTION_HOME: ACCESS_READ,
        SECTION_MENU: ACCESS_WRITE,
    },
    ROLE_DISHES_WRITER: {
        SECTION_HOME: ACCESS_READ,
        SECTION_MENU: ACCESS_WRITE,
        SECTION_DISHES: ACCESS_WRITE,
    },
    ROLE_REPORTS_READER: {
        SECTION_HOME: ACCESS_READ,
        SECTION_MENU: ACCESS_WRITE,
        SECTION_DISHES: ACCESS_WRITE,
        SECTION_REPORTS: ACCESS_READ,
    },
    ROLE_DISHES_ADMIN: {
        SECTION_HOME: ACCESS_READ,
        SECTION_MENU: ACCESS_WRITE,
        SECTION_DISHES: ACCESS_ADMIN,
        SECTION_REPORTS: ACCESS_READ,
    },
    ROLE_PLATFORM_ADMIN: {
        SECTION_HOME: ACCESS_READ,
        SECTION_MENU: ACCESS_ADMIN,
        SECTION_DISHES: ACCESS_ADMIN,
        SECTION_REPORTS: ACCESS_ADMIN,
        SECTION_USERS: ACCESS_ADMIN,
        SECTION_SECURITY: ACCESS_ADMIN,
    },
    ROLE_ADMIN: {
        SECTION_HOME: ACCESS_ADMIN,
        SECTION_MENU: ACCESS_ADMIN,
        SECTION_DISHES: ACCESS_ADMIN,
        SECTION_REPORTS: ACCESS_ADMIN,
        SECTION_USERS: ACCESS_ADMIN,
        SECTION_SECURITY: ACCESS_ADMIN,
    },
    # Compatibilidad legacy
    ROLE_OPERATIONS_MANAGER: {
        SECTION_HOME: ACCESS_READ,
        SECTION_MENU: ACCESS_WRITE,
        SECTION_DISHES: ACCESS_ADMIN,
        SECTION_REPORTS: ACCESS_READ,
    },
    ROLE_MENU_OPERATOR: {
        SECTION_HOME: ACCESS_READ,
        SECTION_MENU: ACCESS_WRITE,
    },
    ROLE_CATALOG_EDITOR: {
        SECTION_HOME: ACCESS_READ,
        SECTION_DISHES: ACCESS_WRITE,
    },
    ROLE_NUTRITION_ANALYST: {
        SECTION_HOME: ACCESS_READ,
        SECTION_MENU: ACCESS_READ,
        SECTION_REPORTS: ACCESS_READ,
    },
    ROLE_FINANCE_ANALYST: {
        SECTION_HOME: ACCESS_READ,
        SECTION_REPORTS: ACCESS_READ,
    },
    ROLE_SECURITY_ADMIN: {
        SECTION_HOME: ACCESS_READ,
        SECTION_USERS: ACCESS_ADMIN,
        SECTION_SECURITY: ACCESS_ADMIN,
    },
    ROLE_VIEWER: {
        SECTION_HOME: ACCESS_READ,
    },
    ROLE_MENU_MAINTAINER: {
        SECTION_HOME: ACCESS_READ,
        SECTION_MENU: ACCESS_WRITE,
        SECTION_DISHES: ACCESS_ADMIN,
        SECTION_REPORTS: ACCESS_READ,
    },
    ROLE_MENU_ONLY: {
        SECTION_HOME: ACCESS_READ,
        SECTION_MENU: ACCESS_WRITE,
    },
    ROLE_HOME_ONLY: {
        SECTION_HOME: ACCESS_READ,
    },
}

PERMISSION_HOME = "home:read"
PERMISSION_MENU = "menu:read"
PERMISSION_MENU_WRITE = "menu:write"
PERMISSION_DISHES = "dishes:read"
PERMISSION_DISHES_WRITE = "dishes:write"
PERMISSION_DISHES_ADMIN = "dishes:admin"
PERMISSION_REPORTS = "reports:read"
PERMISSION_USERS = "users:admin"
PERMISSION_SECURITY = "security:admin"

PERMISSION_REQUIREMENTS: dict[str, tuple[str, int]] = {
    PERMISSION_HOME: (SECTION_HOME, ACCESS_READ),
    PERMISSION_MENU: (SECTION_MENU, ACCESS_READ),
    PERMISSION_MENU_WRITE: (SECTION_MENU, ACCESS_WRITE),
    PERMISSION_DISHES: (SECTION_DISHES, ACCESS_READ),
    PERMISSION_DISHES_WRITE: (SECTION_DISHES, ACCESS_WRITE),
    PERMISSION_DISHES_ADMIN: (SECTION_DISHES, ACCESS_ADMIN),
    PERMISSION_REPORTS: (SECTION_REPORTS, ACCESS_READ),
    PERMISSION_USERS: (SECTION_USERS, ACCESS_ADMIN),
    PERMISSION_SECURITY: (SECTION_SECURITY, ACCESS_ADMIN),
}

PERMISSION_ORDER = tuple(PERMISSION_REQUIREMENTS.keys())
PERMISSION_LABELS = {
    PERMISSION_HOME: "Inicio",
    PERMISSION_MENU: "Menu semanal (lectura)",
    PERMISSION_MENU_WRITE: "Menu semanal (escritura)",
    PERMISSION_DISHES: "Platos (lectura)",
    PERMISSION_DISHES_WRITE: "Platos (escritura)",
    PERMISSION_DISHES_ADMIN: "Platos (admin)",
    PERMISSION_REPORTS: "Reportes",
    PERMISSION_USERS: "Usuarios (admin)",
    PERMISSION_SECURITY: "Seguridad (admin)",
}

SETTINGS = get_settings()
DEFAULT_ADMIN_USERNAME = SETTINGS.admin_username
DEFAULT_ADMIN_FULLNAME = SETTINGS.admin_full_name
DEFAULT_ADMIN_PASSWORD = SETTINGS.admin_initial_password


def role_access_level(role: str, section: str) -> int:
    return int(ROLE_ACCESS_MATRIX.get(role, {}).get(section, ACCESS_NONE))


def role_permissions(role: str) -> set[str]:
    granted: set[str] = set()
    for permission, (section, required_level) in PERMISSION_REQUIREMENTS.items():
        if role_access_level(role, section) >= required_level:
            granted.add(permission)
    return granted


def has_permission(role: str, permission: str) -> bool:
    requirement = PERMISSION_REQUIREMENTS.get(permission)
    if not requirement:
        return False
    section, required_level = requirement
    return role_access_level(role, section) >= required_level


def role_access_labels(role: str) -> list[str]:
    labels: list[str] = []
    for section in SECTION_ORDER:
        if role_access_level(role, section) > ACCESS_NONE:
            labels.append(SECTION_LABELS[section])
    return labels


def role_access_type(role: str) -> int:
    max_level = ACCESS_NONE
    for section in SECTION_ORDER:
        level = role_access_level(role, section)
        if level > max_level:
            max_level = level
    return max_level


def role_catalog() -> list[dict[str, object]]:
    return [
        {
            "key": role,
            "label": ROLE_LABELS.get(role, role),
            "description": ROLE_DESCRIPTIONS.get(role, ""),
            "access_labels": role_access_labels(role),
            "access_type": role_access_type(role),
            "access_type_label": ACCESS_TYPE_LABELS[role_access_type(role)],
            "access_type_style": ACCESS_TYPE_STYLE[role_access_type(role)],
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
