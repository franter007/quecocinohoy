from __future__ import annotations

import hashlib
import hmac
import secrets
from base64 import urlsafe_b64decode, urlsafe_b64encode

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AppSetting, User

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

# Roles oficiales (sin legacy).
ROLE_HOME_READER = "home_reader"
ROLE_MENU_READER = "menu_reader"
ROLE_MENU_WRITER = "menu_writer"
ROLE_DISHES_WRITER = "dishes_writer"
ROLE_REPORTS_READER = "reports_reader"
ROLE_DISHES_ADMIN = "dishes_admin"
ROLE_PLATFORM_ADMIN = "platform_admin"
ROLE_ADMIN = "admin"

ROLE_ORDER = (
    ROLE_HOME_READER,
    ROLE_MENU_READER,
    ROLE_MENU_WRITER,
    ROLE_DISHES_WRITER,
    ROLE_REPORTS_READER,
    ROLE_DISHES_ADMIN,
    ROLE_PLATFORM_ADMIN,
    ROLE_ADMIN,
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
}

ROLE_DESCRIPTIONS = {
    ROLE_HOME_READER: "Solo dashboard inicial. Ejemplo: duenio de casa que revisa el estado semanal.",
    ROLE_MENU_READER: "Inicio + menu semanal lectura. Ejemplo: familiar que revisa el plan sin modificarlo.",
    ROLE_MENU_WRITER: "Inicio + menu en escritura. Ejemplo: planner que genera/regenera la semana.",
    ROLE_DISHES_WRITER: "Incluye platos en escritura (crear/editar, sin eliminar). Ejemplo: asistente de cocina.",
    ROLE_REPORTS_READER: "Incluye reportes de gasto. Ejemplo: quien monitorea presupuesto familiar.",
    ROLE_DISHES_ADMIN: "Incluye admin de platos (crear/editar/eliminar). Ejemplo: responsable del catalogo culinario.",
    ROLE_PLATFORM_ADMIN: "Incluye gestion de usuarios y seguridad operativa. Ejemplo: coordinador de la plataforma.",
    ROLE_ADMIN: "Control total del sistema. Ejemplo: propietario de la aplicacion.",
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
}

# Mapeo de roles legacy hacia roles oficiales.
LEGACY_ROLE_ALIASES: dict[str, str] = {
    "operations_manager": ROLE_DISHES_ADMIN,
    "menu_operator": ROLE_MENU_WRITER,
    "catalog_editor": ROLE_DISHES_WRITER,
    "nutrition_analyst": ROLE_MENU_READER,
    "finance_analyst": ROLE_HOME_READER,
    "security_admin": ROLE_PLATFORM_ADMIN,
    "viewer": ROLE_HOME_READER,
    "menu_maintainer": ROLE_DISHES_ADMIN,
    "menu_only": ROLE_MENU_WRITER,
    "home_only": ROLE_HOME_READER,
}

ROLE_MATRIX_SETTING_PREFIX = "rbac.role."

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


def normalize_role(role: str) -> str:
    return LEGACY_ROLE_ALIASES.get(role, role)


def _role_matrix_setting_key(role: str, section: str) -> str:
    return f"{ROLE_MATRIX_SETTING_PREFIX}{role}.{section}"


def load_effective_role_access_matrix(session: Session) -> dict[str, dict[str, int]]:
    matrix = {role: dict(sections) for role, sections in ROLE_ACCESS_MATRIX.items()}
    rows = session.scalars(select(AppSetting).where(AppSetting.key.like(f"{ROLE_MATRIX_SETTING_PREFIX}%"))).all()
    for row in rows:
        payload = row.key[len(ROLE_MATRIX_SETTING_PREFIX) :]
        role, sep, section = payload.rpartition(".")
        if not sep:
            continue
        if role not in ROLE_ORDER or section not in SECTION_ORDER:
            continue
        try:
            level = int((row.value or "").strip())
        except ValueError:
            continue
        if level < ACCESS_NONE or level > ACCESS_ADMIN:
            continue
        matrix.setdefault(role, {})[section] = level
    return matrix


def save_role_access_overrides(session: Session, submitted_levels: dict[str, dict[str, int]]) -> None:
    existing_rows = session.scalars(
        select(AppSetting).where(AppSetting.key.like(f"{ROLE_MATRIX_SETTING_PREFIX}%"))
    ).all()
    by_key = {row.key: row for row in existing_rows}

    for role in ROLE_ORDER:
        for section in SECTION_ORDER:
            default_level = int(ROLE_ACCESS_MATRIX.get(role, {}).get(section, ACCESS_NONE))
            desired_level = int(submitted_levels.get(role, {}).get(section, default_level))
            if desired_level < ACCESS_NONE:
                desired_level = ACCESS_NONE
            if desired_level > ACCESS_ADMIN:
                desired_level = ACCESS_ADMIN

            # El rol administrador se mantiene fijo para evitar auto-bloqueos.
            if role == ROLE_ADMIN:
                desired_level = default_level

            key = _role_matrix_setting_key(role, section)
            current = by_key.get(key)
            if desired_level == default_level:
                if current:
                    session.delete(current)
                continue

            if current:
                current.value = str(desired_level)
            else:
                session.add(AppSetting(key=key, value=str(desired_level)))

    session.commit()


def migrate_legacy_roles(session: Session) -> int:
    old_roles = tuple(LEGACY_ROLE_ALIASES.keys())
    if not old_roles:
        return 0

    users = list(session.scalars(select(User).where(User.role.in_(old_roles))).all())
    if not users:
        return 0

    migrated = 0
    for user in users:
        mapped = LEGACY_ROLE_ALIASES.get(user.role)
        if mapped and mapped != user.role:
            user.role = mapped
            migrated += 1
    if migrated > 0:
        session.commit()
    return migrated


def role_access_level(role: str, section: str, access_matrix: dict[str, dict[str, int]] | None = None) -> int:
    normalized = normalize_role(role)
    matrix = access_matrix or ROLE_ACCESS_MATRIX
    return int(matrix.get(normalized, {}).get(section, ACCESS_NONE))


def role_permissions(role: str) -> set[str]:
    granted: set[str] = set()
    for permission, (section, required_level) in PERMISSION_REQUIREMENTS.items():
        if role_access_level(role, section) >= required_level:
            granted.add(permission)
    return granted


def has_permission(role: str, permission: str, access_matrix: dict[str, dict[str, int]] | None = None) -> bool:
    requirement = PERMISSION_REQUIREMENTS.get(permission)
    if not requirement:
        return False
    section, required_level = requirement
    return role_access_level(role, section, access_matrix=access_matrix) >= required_level


def role_access_labels(role: str, access_matrix: dict[str, dict[str, int]] | None = None) -> list[str]:
    labels: list[str] = []
    for section in SECTION_ORDER:
        if role_access_level(role, section, access_matrix=access_matrix) > ACCESS_NONE:
            labels.append(SECTION_LABELS[section])
    return labels


def role_access_type(role: str, access_matrix: dict[str, dict[str, int]] | None = None) -> int:
    max_level = ACCESS_NONE
    for section in SECTION_ORDER:
        level = role_access_level(role, section, access_matrix=access_matrix)
        if level > max_level:
            max_level = level
    return max_level


def role_catalog(access_matrix: dict[str, dict[str, int]] | None = None) -> list[dict[str, object]]:
    return [
        {
            "key": role,
            "label": ROLE_LABELS.get(role, role),
            "description": ROLE_DESCRIPTIONS.get(role, ""),
            "access_labels": role_access_labels(role, access_matrix=access_matrix),
            "access_type": role_access_type(role, access_matrix=access_matrix),
            "access_type_label": ACCESS_TYPE_LABELS[role_access_type(role, access_matrix=access_matrix)],
            "access_type_style": ACCESS_TYPE_STYLE[role_access_type(role, access_matrix=access_matrix)],
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
