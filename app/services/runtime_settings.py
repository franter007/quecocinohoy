from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AppSetting


@dataclass(frozen=True)
class SecuritySettingDefinition:
    key: str
    label: str
    value_type: str
    default: bool | int
    description: str
    example: str
    min_value: int | None = None
    max_value: int | None = None


@dataclass(frozen=True)
class SecurityRuntimeSettings:
    login_guard_trust_localhost: bool
    login_nonce_max_age_seconds: int
    login_window_minutes: int
    challenge_combo_fails: int
    challenge_user_fails: int
    challenge_ip_fails: int
    block_combo_fails: int
    block_user_fails: int
    block_ip_fails: int
    block_combo_minutes: int
    block_user_minutes: int
    block_ip_minutes: int


_SETTINGS = get_settings()

SECURITY_SETTING_DEFINITIONS: tuple[SecuritySettingDefinition, ...] = (
    SecuritySettingDefinition(
        key="login_guard_trust_localhost",
        label="Confiar en localhost",
        value_type="bool",
        default=_SETTINGS.login_guard_trust_localhost,
        description=(
            "Si esta activo, en 127.0.0.1 y ::1 se relajan bloqueos y nonce para no "
            "interrumpir pruebas locales."
        ),
        example="Ejemplo: en desarrollo activado; en produccion desactivado.",
    ),
    SecuritySettingDefinition(
        key="login_nonce_max_age_seconds",
        label="Vigencia del formulario (segundos)",
        value_type="int",
        default=_SETTINGS.login_nonce_max_age_seconds,
        min_value=30,
        max_value=3600,
        description="Tiempo maximo para enviar el formulario de login antes de expirar.",
        example="Ejemplo: 900 = 15 minutos.",
    ),
    SecuritySettingDefinition(
        key="login_window_minutes",
        label="Ventana de analisis (minutos)",
        value_type="int",
        default=15,
        min_value=5,
        max_value=120,
        description="Periodo de tiempo usado para contar intentos fallidos recientes.",
        example="Ejemplo: 15 = evaluar solo los ultimos 15 minutos.",
    ),
    SecuritySettingDefinition(
        key="challenge_combo_fails",
        label="Desafio por combo usuario+IP (fallos)",
        value_type="int",
        default=3,
        min_value=1,
        max_value=60,
        description="Desde cuantos fallos del mismo usuario en la misma IP se pide validacion adicional.",
        example="Ejemplo: 3 = en el tercer fallo aparece operacion matematica.",
    ),
    SecuritySettingDefinition(
        key="challenge_user_fails",
        label="Desafio por usuario global (fallos)",
        value_type="int",
        default=4,
        min_value=1,
        max_value=100,
        description="Desde cuantos fallos acumulados de un usuario (en cualquier IP) se exige desafio.",
        example="Ejemplo: 4 = protege si prueban al usuario desde varias IP.",
    ),
    SecuritySettingDefinition(
        key="challenge_ip_fails",
        label="Desafio por IP global (fallos)",
        value_type="int",
        default=12,
        min_value=1,
        max_value=300,
        description="Desde cuantos fallos en una IP se activa validacion adicional para esa IP.",
        example="Ejemplo: 12 = evita prueba masiva de claves desde una misma IP.",
    ),
    SecuritySettingDefinition(
        key="block_combo_fails",
        label="Bloqueo por combo usuario+IP (fallos)",
        value_type="int",
        default=6,
        min_value=1,
        max_value=100,
        description="Cantidad de fallos para bloquear temporalmente ese usuario en esa IP.",
        example="Ejemplo: 6 fallos en ventana activa bloqueo de combo.",
    ),
    SecuritySettingDefinition(
        key="block_user_fails",
        label="Bloqueo por usuario global (fallos)",
        value_type="int",
        default=8,
        min_value=1,
        max_value=150,
        description="Cantidad de fallos acumulados de un usuario para bloquearlo temporalmente.",
        example="Ejemplo: 8 = bloqueo del usuario aunque cambie de IP.",
    ),
    SecuritySettingDefinition(
        key="block_ip_fails",
        label="Bloqueo por IP global (fallos)",
        value_type="int",
        default=30,
        min_value=1,
        max_value=500,
        description="Cantidad de fallos en una IP para aplicar bloqueo temporal a esa IP.",
        example="Ejemplo: 30 = frena ataques automatizados desde una sola IP.",
    ),
    SecuritySettingDefinition(
        key="block_combo_minutes",
        label="Duracion bloqueo combo (minutos)",
        value_type="int",
        default=15,
        min_value=1,
        max_value=240,
        description="Tiempo de bloqueo cuando supera el umbral de usuario+IP.",
        example="Ejemplo: 15 = reintento permitido tras 15 minutos.",
    ),
    SecuritySettingDefinition(
        key="block_user_minutes",
        label="Duracion bloqueo usuario (minutos)",
        value_type="int",
        default=20,
        min_value=1,
        max_value=480,
        description="Tiempo de bloqueo para el usuario al superar su umbral global.",
        example="Ejemplo: 20 = la cuenta espera 20 minutos para nuevos intentos.",
    ),
    SecuritySettingDefinition(
        key="block_ip_minutes",
        label="Duracion bloqueo IP (minutos)",
        value_type="int",
        default=20,
        min_value=1,
        max_value=480,
        description="Tiempo de bloqueo para la IP cuando excede su umbral global.",
        example="Ejemplo: 20 = desde esa IP no se permite login por 20 minutos.",
    ),
)

_DEFINITIONS_BY_KEY = {item.key: item for item in SECURITY_SETTING_DEFINITIONS}
_BOOL_TRUE_VALUES = {"1", "true", "yes", "on", "si"}
_BOOL_FALSE_VALUES = {"0", "false", "no", "off"}


def list_security_setting_definitions() -> tuple[SecuritySettingDefinition, ...]:
    return SECURITY_SETTING_DEFINITIONS


def _normalize_bool_value(raw_value: str | None) -> str | None:
    normalized = (raw_value or "").strip().lower()
    if normalized in _BOOL_TRUE_VALUES:
        return "1"
    if normalized in _BOOL_FALSE_VALUES:
        return "0"
    return None


def _serialize_value(definition: SecuritySettingDefinition, value: bool | int) -> str:
    if definition.value_type == "bool":
        return "1" if bool(value) else "0"
    return str(int(value))


def _coerce_runtime_value(definition: SecuritySettingDefinition, raw_value: str | None) -> bool | int:
    if definition.value_type == "bool":
        normalized = _normalize_bool_value(raw_value)
        if normalized is None:
            return bool(definition.default)
        return normalized == "1"

    try:
        parsed = int((raw_value or "").strip())
    except ValueError:
        parsed = int(definition.default)

    if definition.min_value is not None and parsed < definition.min_value:
        parsed = definition.min_value
    if definition.max_value is not None and parsed > definition.max_value:
        parsed = definition.max_value
    return parsed


def _load_raw_security_values(session: Session) -> dict[str, str]:
    keys = [item.key for item in SECURITY_SETTING_DEFINITIONS]
    rows = session.scalars(select(AppSetting).where(AppSetting.key.in_(keys))).all()
    return {row.key: row.value for row in rows}


def load_security_settings(session: Session) -> SecurityRuntimeSettings:
    raw_values = _load_raw_security_values(session)
    effective_values: dict[str, bool | int] = {}
    for definition in SECURITY_SETTING_DEFINITIONS:
        effective_values[definition.key] = _coerce_runtime_value(definition, raw_values.get(definition.key))
    return SecurityRuntimeSettings(**effective_values)


def build_security_form_fields(
    session: Session,
    form_values: Mapping[str, str] | None = None,
) -> list[dict]:
    raw_values = _load_raw_security_values(session)
    effective_settings = load_security_settings(session)
    fields: list[dict] = []
    for definition in SECURITY_SETTING_DEFINITIONS:
        if form_values is not None:
            current_raw = str(form_values.get(definition.key, "")).strip()
            if not current_raw:
                current_raw = _serialize_value(definition, getattr(effective_settings, definition.key))
        else:
            current_raw = raw_values.get(
                definition.key,
                _serialize_value(definition, getattr(effective_settings, definition.key)),
            )

        default_raw = _serialize_value(definition, definition.default)
        effective_raw = _serialize_value(definition, getattr(effective_settings, definition.key))
        fields.append(
            {
                "key": definition.key,
                "label": definition.label,
                "value_type": definition.value_type,
                "value": current_raw,
                "default_value": default_raw,
                "effective_value": effective_raw,
                "description": definition.description,
                "example": definition.example,
                "min_value": definition.min_value,
                "max_value": definition.max_value,
                "is_overridden": definition.key in raw_values,
            }
        )
    return fields


def validate_security_form_values(form_values: Mapping[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    cleaned: dict[str, str] = {}
    errors: dict[str, str] = {}
    for definition in SECURITY_SETTING_DEFINITIONS:
        raw_value = str(form_values.get(definition.key, "")).strip()
        if definition.value_type == "bool":
            normalized_bool = _normalize_bool_value(raw_value)
            if normalized_bool is None:
                errors[definition.key] = "Selecciona Si o No."
            else:
                cleaned[definition.key] = normalized_bool
            continue

        if not raw_value:
            errors[definition.key] = "Este valor es obligatorio."
            continue
        try:
            parsed = int(raw_value)
        except ValueError:
            errors[definition.key] = "Ingresa un numero entero."
            continue

        min_value = definition.min_value
        max_value = definition.max_value
        if min_value is not None and parsed < min_value:
            errors[definition.key] = f"Debe ser mayor o igual a {min_value}."
            continue
        if max_value is not None and parsed > max_value:
            errors[definition.key] = f"Debe ser menor o igual a {max_value}."
            continue
        cleaned[definition.key] = str(parsed)
    return cleaned, errors


def save_security_settings(session: Session, values: Mapping[str, str]) -> None:
    keys = [item.key for item in SECURITY_SETTING_DEFINITIONS]
    existing = session.scalars(select(AppSetting).where(AppSetting.key.in_(keys))).all()
    by_key = {row.key: row for row in existing}

    for key, raw_value in values.items():
        definition = _DEFINITIONS_BY_KEY.get(key)
        if not definition:
            continue

        default_serialized = _serialize_value(definition, definition.default)
        current = by_key.get(key)

        if raw_value == default_serialized:
            if current:
                session.delete(current)
            continue

        if current:
            current.value = raw_value
        else:
            session.add(AppSetting(key=key, value=raw_value))
    session.commit()
