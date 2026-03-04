from __future__ import annotations

import secrets
import time
from contextlib import asynccontextmanager
from datetime import date, datetime
from io import BytesIO
import math
from pathlib import Path
from urllib.parse import quote_plus, urlencode

from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.database import Base, SessionLocal, engine, get_db
from app.models import Dish, MEAL_TYPES, User, WeeklyMenu
from app.seed_data import seed_default_dishes
from app.services.auth import (
    PERMISSION_DISHES,
    PERMISSION_HOME,
    PERMISSION_MENU,
    PERMISSION_REPORTS,
    PERMISSION_SECURITY,
    PERMISSION_USERS,
    ROLE_ADMIN,
    ROLE_LABELS,
    ROLE_ORDER,
    authenticate_user,
    ensure_admin_user,
    has_permission,
    hash_password,
    role_catalog,
    role_permissions,
)
from app.services.menu_export import (
    build_menu_pdf_bytes,
    build_menu_png_bytes,
    menu_export_choices,
    menu_export_presets,
    resolve_menu_export_columns,
)
from app.services.menu_generator import DAY_NAMES, generate_weekly_menu, get_weekly_menu, normalize_week_start
from app.services.login_guard import (
    analyze_login_risk,
    format_blocked_seconds,
    generate_math_challenge,
    get_client_ip,
    is_local_ip,
    record_login_attempt,
    suggest_failure_sleep_seconds,
)
from app.services.nutrition import evaluate_nutrition
from app.services.report_export import (
    build_report_pdf_bytes,
    build_report_png_bytes,
    report_export_choices,
    report_export_presets,
    resolve_report_export_columns,
)
from app.services.reports import build_cost_report, default_range
from app.services.runtime_settings import (
    build_security_form_fields,
    load_security_settings,
    save_security_settings,
    validate_security_form_values,
)

MEAL_LABELS = {
    "desayuno": "Desayuno",
    "almuerzo": "Almuerzo",
    "cena": "Cena",
    "lonchera": "Lonchera",
    "refresco": "Refresco",
}

# Rutas publicas que no deben forzar redireccion al login.
# Incluimos favicon/robots para evitar redirecciones secundarias que pueden
# refrescar el nonce del formulario y causar falsos "sesion expirada".
PUBLIC_PATHS = {"/login", "/health", "/favicon.ico", "/robots.txt"}
PUBLIC_PATH_PREFIXES = ("/static",)
SETTINGS = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        seed_default_dishes(session)
        ensure_admin_user(session)
    yield


app = FastAPI(title="Que Cocino Hoy", lifespan=lifespan)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def _is_public_path(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in PUBLIC_PATH_PREFIXES)


def _safe_next_path(value: str | None) -> str:
    if not value:
        return "/"
    if not value.startswith("/") or value.startswith("//"):
        return "/"
    return value


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if _is_public_path(request.url.path):
        return await call_next(request)

    user_id = request.session.get("user_id")
    if not user_id:
        next_path = request.url.path
        if request.url.query:
            next_path = f"{next_path}?{request.url.query}"
        return RedirectResponse(url=f"/login?next={quote_plus(next_path)}", status_code=303)

    try:
        lookup_user_id = int(user_id)
    except (TypeError, ValueError):
        request.session.clear()
        return RedirectResponse(url="/login", status_code=303)

    with SessionLocal() as session:
        user = session.get(User, lookup_user_id)
        if not user or not user.is_active:
            request.session.clear()
            return RedirectResponse(url="/login", status_code=303)
        request.state.current_user = {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "role": user.role,
        }

    return await call_next(request)


app.add_middleware(
    SessionMiddleware,
    secret_key=SETTINGS.session_secret_key,
    max_age=60 * 60 * 12,
    same_site="lax",
)


def parse_date(value: str | None, fallback: date) -> date:
    if not value:
        return fallback
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Fecha invalida, formato esperado YYYY-MM-DD") from exc


def _menu_rows(menu: WeeklyMenu | None) -> tuple[list[dict], float]:
    if not menu:
        return [], 0

    by_slot = {(item.day_of_week, item.meal_type): item for item in menu.items}
    rows: list[dict] = []
    total = 0.0
    for day_index, day_name in enumerate(DAY_NAMES):
        day_total = 0.0
        meals = {}
        for meal in MEAL_TYPES:
            item = by_slot.get((day_index, meal))
            meals[meal] = item
            if item:
                day_total += item.estimated_cost
        rows.append({"day_name": day_name, "meals": meals, "daily_total": round(day_total, 2)})
        total += day_total
    return rows, round(total, 2)


def _parse_bool(value: str | None) -> bool:
    return value in {"on", "true", "1", "si", "yes"}


def _current_user(request: Request) -> dict | None:
    return getattr(request.state, "current_user", None)


def _permission_flags(role: str | None) -> dict[str, bool]:
    perms = role_permissions(role or "")
    return {
        "can_view_home": PERMISSION_HOME in perms,
        "can_view_menu": PERMISSION_MENU in perms,
        "can_manage_dishes": PERMISSION_DISHES in perms,
        "can_view_reports": PERMISSION_REPORTS in perms,
        "can_manage_users": PERMISSION_USERS in perms,
        "can_manage_security": PERMISSION_SECURITY in perms,
    }


def _render(request: Request, template_name: str, context: dict, status_code: int = 200):
    user = _current_user(request)
    role = user["role"] if user else None
    base_context = {
        "request": request,
        "current_user": user,
        "role_labels": ROLE_LABELS,
        **_permission_flags(role),
    }
    base_context.update(context)
    return templates.TemplateResponse(template_name, base_context, status_code=status_code)


def _require_permission(request: Request, permission: str) -> None:
    user = _current_user(request)
    role = user["role"] if user else ""
    if not has_permission(role, permission):
        raise HTTPException(status_code=403, detail="No tienes permisos para esta accion")


def _upsert_dish(
    dish: Dish,
    name: str,
    meal_type: str,
    ingredients: str,
    cost_per_serving: float,
    calories: int,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
    fiber_g: float,
    sugar_g: float,
    sodium_mg: float,
    benefits: str,
    warnings: str,
    is_active: bool,
) -> None:
    is_healthy, auto_benefits, auto_warnings = evaluate_nutrition(
        calories=calories,
        protein_g=protein_g,
        carbs_g=carbs_g,
        fat_g=fat_g,
        fiber_g=fiber_g,
        sugar_g=sugar_g,
        sodium_mg=sodium_mg,
    )

    dish.name = name.strip()
    dish.meal_type = meal_type
    dish.ingredients = ingredients.strip()
    dish.cost_per_serving = cost_per_serving
    dish.calories = calories
    dish.protein_g = protein_g
    dish.carbs_g = carbs_g
    dish.fat_g = fat_g
    dish.fiber_g = fiber_g
    dish.sugar_g = sugar_g
    dish.sodium_mg = sodium_mg
    dish.benefits = benefits.strip() or auto_benefits
    dish.warnings = warnings.strip() or auto_warnings
    dish.is_healthy = is_healthy
    dish.is_active = is_active


def _active_admin_count(db: Session) -> int:
    return (
        db.scalar(
            select(func.count()).select_from(User).where(User.role == ROLE_ADMIN, User.is_active.is_(True))
        )
        or 0
    )


def _build_dishes_list_context(
    db: Session,
    q: str | None,
    meal_type: str | None,
    page: int,
    per_page: int,
) -> dict:
    clean_q = (q or "").strip()
    clean_meal_type = meal_type if meal_type in MEAL_TYPES else ""
    safe_page = max(1, page)
    safe_per_page = min(100, max(5, per_page))

    count_stmt = select(func.count()).select_from(Dish)
    rows_stmt = select(Dish)

    if clean_q:
        like_value = f"%{clean_q}%"
        count_stmt = count_stmt.where(Dish.name.ilike(like_value))
        rows_stmt = rows_stmt.where(Dish.name.ilike(like_value))
    if clean_meal_type:
        count_stmt = count_stmt.where(Dish.meal_type == clean_meal_type)
        rows_stmt = rows_stmt.where(Dish.meal_type == clean_meal_type)

    total_items = int(db.scalar(count_stmt) or 0)
    total_pages = max(1, math.ceil(total_items / safe_per_page)) if total_items else 1
    current_page = min(safe_page, total_pages)
    offset = (current_page - 1) * safe_per_page

    rows_stmt = (
        rows_stmt.order_by(Dish.meal_type, Dish.name)
        .offset(offset)
        .limit(safe_per_page)
    )
    dishes = list(db.scalars(rows_stmt).all())

    if total_items:
        start_item = offset + 1
        end_item = min(offset + len(dishes), total_items)
    else:
        start_item = 0
        end_item = 0

    page_start = max(1, current_page - 2)
    page_end = min(total_pages, current_page + 2)
    page_numbers = list(range(page_start, page_end + 1))
    base_query = urlencode({"q": clean_q, "meal_type": clean_meal_type, "per_page": safe_per_page})

    return {
        "dishes": dishes,
        "q": clean_q,
        "meal_type": clean_meal_type,
        "page": current_page,
        "per_page": safe_per_page,
        "total_items": total_items,
        "total_pages": total_pages,
        "has_prev": current_page > 1,
        "has_next": current_page < total_pages,
        "prev_page": current_page - 1,
        "next_page": current_page + 1,
        "page_numbers": page_numbers,
        "start_item": start_item,
        "end_item": end_item,
        "query_base": base_query,
    }


LOGIN_NONCE_KEY = "login_form_nonce"
LOGIN_NONCE_TS_KEY = "login_form_nonce_ts"
LOGIN_CHALLENGE_KEY = "login_math_challenge"


def _issue_login_nonce(request: Request) -> str:
    nonce = secrets.token_urlsafe(18)
    request.session[LOGIN_NONCE_KEY] = nonce
    request.session[LOGIN_NONCE_TS_KEY] = int(time.time())
    return nonce


def _validate_login_nonce(request: Request, submitted_nonce: str, max_age_seconds: int) -> bool:
    expected = request.session.get(LOGIN_NONCE_KEY)
    issued_at = request.session.get(LOGIN_NONCE_TS_KEY)
    if not expected or not issued_at:
        return False
    if not submitted_nonce or submitted_nonce != expected:
        return False
    age = int(time.time()) - int(issued_at)
    # Tolera pequeno desfase de reloj entre instancias de contenedor.
    if age < -30 or age > max_age_seconds:
        return False
    return True


def _ensure_login_challenge(request: Request) -> str:
    now = int(time.time())
    challenge = request.session.get(LOGIN_CHALLENGE_KEY)
    if not challenge or not isinstance(challenge, dict) or now - int(challenge.get("ts", 0)) > 10 * 60:
        question, answer = generate_math_challenge()
        challenge = {"q": question, "a": answer, "ts": now}
        request.session[LOGIN_CHALLENGE_KEY] = challenge
    return str(challenge.get("q", ""))


def _clear_login_challenge(request: Request) -> None:
    request.session.pop(LOGIN_CHALLENGE_KEY, None)


def _verify_login_challenge(request: Request, response: str) -> bool:
    challenge = request.session.get(LOGIN_CHALLENGE_KEY)
    if not challenge or not isinstance(challenge, dict):
        return False
    issued_ts = int(challenge.get("ts", 0))
    if int(time.time()) - issued_ts > 10 * 60:
        return False
    expected = str(challenge.get("a", "")).strip()
    provided = response.strip()
    return bool(provided and expected and provided == expected)


def _render_login(
    request: Request,
    next_path: str,
    error: str = "",
    username_value: str = "",
    challenge_required: bool = False,
    blocked_seconds: int = 0,
):
    challenge_question = _ensure_login_challenge(request) if challenge_required else ""
    if not challenge_required:
        _clear_login_challenge(request)
    form_nonce = _issue_login_nonce(request)
    retry_label = format_blocked_seconds(blocked_seconds) if blocked_seconds > 0 else ""
    return _render(
        request,
        "login.html",
        {
            "error": error,
            "next": _safe_next_path(next_path),
            "username_value": username_value,
            "show_challenge": challenge_required,
            "challenge_question": challenge_question,
            "blocked_seconds": blocked_seconds,
            "retry_label": retry_label,
            "form_nonce": form_nonce,
        },
        status_code=400 if error else 200,
    )


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str | None = None, db: Session = Depends(get_db)):
    if request.session.get("user_id"):
        return RedirectResponse(url="/", status_code=303)

    ip_address = get_client_ip(request)
    security = load_security_settings(db)
    risk = analyze_login_risk(db, ip_address=ip_address, username=None, security=security)
    return _render_login(
        request,
        next_path=_safe_next_path(next),
        challenge_required=risk.challenge_required or risk.blocked_seconds > 0,
        blocked_seconds=risk.blocked_seconds,
    )


@app.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    challenge_response: str = Form(""),
    website: str = Form(""),
    form_nonce: str = Form(""),
    next: str = Form("/"),
    db: Session = Depends(get_db),
):
    next_path = _safe_next_path(next)
    clean_username = username.strip().lower()
    ip_address = get_client_ip(request)
    security = load_security_settings(db)

    if website.strip():
        record_login_attempt(db, username=clean_username, ip_address=ip_address, success=False, reason="honeypot")
        risk = analyze_login_risk(db, ip_address=ip_address, username=clean_username, security=security)
        time.sleep(suggest_failure_sleep_seconds(risk))
        return _render_login(
            request,
            next_path=next_path,
            username_value=clean_username,
            error="No se pudo iniciar sesion. Intenta nuevamente.",
            challenge_required=True,
            blocked_seconds=risk.blocked_seconds,
        )

    skip_nonce = security.login_guard_trust_localhost and is_local_ip(ip_address)
    if not skip_nonce and not _validate_login_nonce(
        request, form_nonce, security.login_nonce_max_age_seconds
    ):
        risk = analyze_login_risk(db, ip_address=ip_address, username=clean_username, security=security)
        return _render_login(
            request,
            next_path=next_path,
            username_value=clean_username,
            error="La sesion del formulario expiro. Vuelve a intentarlo.",
            challenge_required=True,
            blocked_seconds=risk.blocked_seconds,
        )

    risk_before = analyze_login_risk(db, ip_address=ip_address, username=clean_username, security=security)
    if risk_before.blocked_seconds > 0:
        return _render_login(
            request,
            next_path=next_path,
            username_value=clean_username,
            error=f"Demasiados intentos. Espera {format_blocked_seconds(risk_before.blocked_seconds)}.",
            challenge_required=True,
            blocked_seconds=risk_before.blocked_seconds,
        )

    if risk_before.challenge_required and not _verify_login_challenge(request, challenge_response):
        record_login_attempt(db, username=clean_username, ip_address=ip_address, success=False, reason="challenge_failed")
        risk_after_challenge = analyze_login_risk(db, ip_address=ip_address, username=clean_username, security=security)
        time.sleep(suggest_failure_sleep_seconds(risk_after_challenge))
        return _render_login(
            request,
            next_path=next_path,
            username_value=clean_username,
            error="Validacion adicional incorrecta. Intenta nuevamente.",
            challenge_required=True,
            blocked_seconds=risk_after_challenge.blocked_seconds,
        )

    user = authenticate_user(db, clean_username, password)
    if not user:
        record_login_attempt(db, username=clean_username, ip_address=ip_address, success=False, reason="invalid_credentials")
        risk_after = analyze_login_risk(db, ip_address=ip_address, username=clean_username, security=security)
        time.sleep(suggest_failure_sleep_seconds(risk_after))
        message = "Usuario o contrasena invalida"
        if risk_after.blocked_seconds > 0:
            message = f"Demasiados intentos. Espera {format_blocked_seconds(risk_after.blocked_seconds)}."
        return _render_login(
            request,
            next_path=next_path,
            username_value=clean_username,
            error=message,
            challenge_required=risk_after.challenge_required or risk_after.blocked_seconds > 0,
            blocked_seconds=risk_after.blocked_seconds,
        )

    record_login_attempt(db, username=clean_username, ip_address=ip_address, success=True, reason="ok")
    request.session.pop(LOGIN_NONCE_KEY, None)
    request.session.pop(LOGIN_NONCE_TS_KEY, None)
    _clear_login_challenge(request)
    request.session["user_id"] = user.id
    return RedirectResponse(url=next_path, status_code=303)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    _require_permission(request, PERMISSION_HOME)

    week_start = normalize_week_start(date.today())
    current_menu = get_weekly_menu(db, week_start)
    rows, total_cost = _menu_rows(current_menu)
    total_dishes = db.scalar(select(func.count()).select_from(Dish))
    total_menus = db.scalar(select(func.count()).select_from(WeeklyMenu))

    return _render(
        request,
        "index.html",
        {
            "meal_labels": MEAL_LABELS,
            "week_start": week_start,
            "rows": rows,
            "total_cost": total_cost,
            "current_menu": current_menu,
            "total_dishes": total_dishes or 0,
            "total_menus": total_menus or 0,
        },
    )


@app.get("/dishes", response_class=HTMLResponse)
def dishes_page(
    request: Request,
    q: str | None = None,
    meal_type: str | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=5, le=100),
    db: Session = Depends(get_db),
):
    _require_permission(request, PERMISSION_DISHES)
    list_context = _build_dishes_list_context(db, q=q, meal_type=meal_type, page=page, per_page=per_page)
    return _render(
        request,
        "dishes.html",
        {
            "meal_types": MEAL_TYPES,
            "meal_labels": MEAL_LABELS,
            "results_endpoint": "/dishes/partial",
            "base_path": "/dishes",
            **list_context,
        },
    )


@app.get("/dishes/partial", response_class=HTMLResponse)
def dishes_partial(
    request: Request,
    q: str | None = None,
    meal_type: str | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=5, le=100),
    db: Session = Depends(get_db),
):
    _require_permission(request, PERMISSION_DISHES)
    list_context = _build_dishes_list_context(db, q=q, meal_type=meal_type, page=page, per_page=per_page)
    return templates.TemplateResponse(
        "partials/dishes_table.html",
        {
            "request": request,
            "meal_labels": MEAL_LABELS,
            "base_path": "/dishes",
            **list_context,
        },
    )


@app.get("/dishes/new", response_class=HTMLResponse)
def new_dish_page(request: Request):
    _require_permission(request, PERMISSION_DISHES)
    return _render(
        request,
        "dish_form.html",
        {
            "dish": None,
            "meal_types": MEAL_TYPES,
            "meal_labels": MEAL_LABELS,
            "action": "/dishes/new",
            "title": "Nuevo Plato",
        },
    )


@app.post("/dishes/new")
def create_dish(
    request: Request,
    name: str = Form(...),
    meal_type: str = Form(...),
    ingredients: str = Form(...),
    cost_per_serving: float = Form(...),
    calories: int = Form(...),
    protein_g: float = Form(0),
    carbs_g: float = Form(0),
    fat_g: float = Form(0),
    fiber_g: float = Form(0),
    sugar_g: float = Form(0),
    sodium_mg: float = Form(0),
    benefits: str = Form(""),
    warnings: str = Form(""),
    is_active: str | None = Form(None),
    db: Session = Depends(get_db),
):
    _require_permission(request, PERMISSION_DISHES)

    if meal_type not in MEAL_TYPES:
        raise HTTPException(status_code=400, detail="Tipo de comida invalido")

    dish = Dish(name="", meal_type=meal_type, ingredients="", cost_per_serving=0, calories=0)
    _upsert_dish(
        dish=dish,
        name=name,
        meal_type=meal_type,
        ingredients=ingredients,
        cost_per_serving=cost_per_serving,
        calories=calories,
        protein_g=protein_g,
        carbs_g=carbs_g,
        fat_g=fat_g,
        fiber_g=fiber_g,
        sugar_g=sugar_g,
        sodium_mg=sodium_mg,
        benefits=benefits,
        warnings=warnings,
        is_active=_parse_bool(is_active),
    )
    db.add(dish)
    db.commit()
    return RedirectResponse(url="/dishes", status_code=303)


@app.get("/dishes/{dish_id}/edit", response_class=HTMLResponse)
def edit_dish_page(dish_id: int, request: Request, db: Session = Depends(get_db)):
    _require_permission(request, PERMISSION_DISHES)

    dish = db.get(Dish, dish_id)
    if not dish:
        raise HTTPException(status_code=404, detail="Plato no encontrado")
    return _render(
        request,
        "dish_form.html",
        {
            "dish": dish,
            "meal_types": MEAL_TYPES,
            "meal_labels": MEAL_LABELS,
            "action": f"/dishes/{dish_id}/edit",
            "title": "Editar Plato",
        },
    )


@app.post("/dishes/{dish_id}/edit")
def edit_dish(
    request: Request,
    dish_id: int,
    name: str = Form(...),
    meal_type: str = Form(...),
    ingredients: str = Form(...),
    cost_per_serving: float = Form(...),
    calories: int = Form(...),
    protein_g: float = Form(0),
    carbs_g: float = Form(0),
    fat_g: float = Form(0),
    fiber_g: float = Form(0),
    sugar_g: float = Form(0),
    sodium_mg: float = Form(0),
    benefits: str = Form(""),
    warnings: str = Form(""),
    is_active: str | None = Form(None),
    db: Session = Depends(get_db),
):
    _require_permission(request, PERMISSION_DISHES)

    if meal_type not in MEAL_TYPES:
        raise HTTPException(status_code=400, detail="Tipo de comida invalido")
    dish = db.get(Dish, dish_id)
    if not dish:
        raise HTTPException(status_code=404, detail="Plato no encontrado")

    _upsert_dish(
        dish=dish,
        name=name,
        meal_type=meal_type,
        ingredients=ingredients,
        cost_per_serving=cost_per_serving,
        calories=calories,
        protein_g=protein_g,
        carbs_g=carbs_g,
        fat_g=fat_g,
        fiber_g=fiber_g,
        sugar_g=sugar_g,
        sodium_mg=sodium_mg,
        benefits=benefits,
        warnings=warnings,
        is_active=_parse_bool(is_active),
    )
    db.commit()
    return RedirectResponse(url="/dishes", status_code=303)


@app.post("/dishes/{dish_id}/delete")
def delete_dish(request: Request, dish_id: int, db: Session = Depends(get_db)):
    _require_permission(request, PERMISSION_DISHES)

    dish = db.get(Dish, dish_id)
    if dish:
        db.delete(dish)
        db.commit()
    return RedirectResponse(url="/dishes", status_code=303)


@app.post("/menus/generate")
def generate_menu(
    request: Request,
    week_start: str = Form(""),
    force: str | None = Form(None),
    db: Session = Depends(get_db),
):
    _require_permission(request, PERMISSION_MENU)

    requested = parse_date(week_start, normalize_week_start(date.today()))
    normalized = normalize_week_start(requested)
    try:
        generate_weekly_menu(db, normalized, force=_parse_bool(force))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(url=f"/menus?week_start={normalized.isoformat()}", status_code=303)


@app.get("/menus", response_class=HTMLResponse)
def menu_page(
    request: Request,
    week_start: str | None = None,
    columns: list[str] | None = Query(None),
    preset: str | None = None,
    db: Session = Depends(get_db),
):
    _require_permission(request, PERMISSION_MENU)

    selected_start = normalize_week_start(parse_date(week_start, normalize_week_start(date.today())))
    selected_columns = resolve_menu_export_columns(columns, preset, MEAL_LABELS)
    menu_preset_keys = {p["key"] for p in menu_export_presets()}
    if preset in menu_preset_keys:
        selected_preset = preset
    elif columns:
        selected_preset = "custom"
    else:
        selected_preset = "completo"

    menu = get_weekly_menu(db, selected_start)
    rows, total_cost = _menu_rows(menu)
    week_options = list(db.scalars(select(WeeklyMenu.week_start).order_by(WeeklyMenu.week_start.desc())).all())
    return _render(
        request,
        "weekly_menu.html",
        {
            "menu": menu,
            "rows": rows,
            "total_cost": total_cost,
            "week_start": selected_start,
            "week_options": week_options,
            "meal_labels": MEAL_LABELS,
            "menu_export_columns": menu_export_choices(MEAL_LABELS),
            "menu_export_presets": menu_export_presets(),
            "selected_menu_export_columns": selected_columns,
            "selected_menu_export_preset": selected_preset,
        },
    )


@app.get("/menus/export/pdf")
def export_menu_pdf(
    request: Request,
    week_start: str | None = None,
    columns: list[str] | None = Query(None),
    preset: str | None = None,
    db: Session = Depends(get_db),
):
    _require_permission(request, PERMISSION_MENU)

    selected_start = normalize_week_start(parse_date(week_start, normalize_week_start(date.today())))
    menu = get_weekly_menu(db, selected_start)
    if not menu:
        raise HTTPException(status_code=404, detail="No existe menu para la semana solicitada")

    rows, total_cost = _menu_rows(menu)
    selected_columns = resolve_menu_export_columns(columns, preset, MEAL_LABELS)
    payload = build_menu_pdf_bytes(
        week_start=selected_start,
        rows=rows,
        total_cost=total_cost,
        meal_labels=MEAL_LABELS,
        selected_columns=selected_columns,
    )
    filename = f"menu-semanal-{selected_start.isoformat()}.pdf"
    return StreamingResponse(
        BytesIO(payload),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/menus/export/png")
def export_menu_png(
    request: Request,
    week_start: str | None = None,
    columns: list[str] | None = Query(None),
    preset: str | None = None,
    db: Session = Depends(get_db),
):
    _require_permission(request, PERMISSION_MENU)

    selected_start = normalize_week_start(parse_date(week_start, normalize_week_start(date.today())))
    menu = get_weekly_menu(db, selected_start)
    if not menu:
        raise HTTPException(status_code=404, detail="No existe menu para la semana solicitada")

    rows, total_cost = _menu_rows(menu)
    selected_columns = resolve_menu_export_columns(columns, preset, MEAL_LABELS)
    payload = build_menu_png_bytes(
        week_start=selected_start,
        rows=rows,
        total_cost=total_cost,
        meal_labels=MEAL_LABELS,
        selected_columns=selected_columns,
    )
    filename = f"menu-semanal-{selected_start.isoformat()}.png"
    return StreamingResponse(
        BytesIO(payload),
        media_type="image/png",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/menus/share/whatsapp")
def share_menu_whatsapp(
    request: Request,
    week_start: str | None = None,
    columns: list[str] | None = Query(None),
    preset: str | None = None,
    db: Session = Depends(get_db),
):
    _require_permission(request, PERMISSION_MENU)

    selected_start = normalize_week_start(parse_date(week_start, normalize_week_start(date.today())))
    menu = get_weekly_menu(db, selected_start)
    if not menu:
        raise HTTPException(status_code=404, detail="No existe menu para la semana solicitada")

    rows, total_cost = _menu_rows(menu)
    selected_columns = resolve_menu_export_columns(columns, preset, MEAL_LABELS)
    daily_summary = ", ".join([f"{row['day_name']}: S/ {row['daily_total']:.2f}" for row in rows])

    base_url = str(request.base_url).rstrip("/")
    menu_link = f"{base_url}/menus?week_start={selected_start.isoformat()}"
    export_query = urlencode(
        {"week_start": selected_start.isoformat(), "columns": selected_columns, "preset": preset or ""},
        doseq=True,
    )
    pdf_link = f"{base_url}/menus/export/pdf?{export_query}"
    png_link = f"{base_url}/menus/export/png?{export_query}"
    text = (
        f"Menu semanal {selected_start.isoformat()}\n"
        f"Total estimado: S/ {total_cost:.2f}\n"
        f"Detalle diario: {daily_summary}\n"
        f"Web: {menu_link}\n"
        f"PDF: {pdf_link}\n"
        f"PNG: {png_link}"
    )
    return RedirectResponse(url=f"https://wa.me/?text={quote_plus(text)}", status_code=303)


@app.get("/reports", response_class=HTMLResponse)
def reports_page(
    request: Request,
    start: str | None = None,
    end: str | None = None,
    columns: list[str] | None = Query(None),
    preset: str | None = None,
    db: Session = Depends(get_db),
):
    _require_permission(request, PERMISSION_REPORTS)

    default_start, default_end = default_range()
    start_date = parse_date(start, default_start)
    end_date = parse_date(end, default_end)
    if end_date < start_date:
        start_date, end_date = end_date, start_date

    selected_columns = resolve_report_export_columns(columns, preset)
    report_preset_keys = {p["key"] for p in report_export_presets()}
    if preset in report_preset_keys:
        selected_preset = preset
    elif columns:
        selected_preset = "custom"
    else:
        selected_preset = "completo"
    report = build_cost_report(db, start_date, end_date)
    return _render(
        request,
        "reports.html",
        {
            "report": report,
            "meal_labels": MEAL_LABELS,
            "report_export_columns": report_export_choices(),
            "report_export_presets": report_export_presets(),
            "selected_report_export_columns": selected_columns,
            "selected_report_export_preset": selected_preset,
        },
    )


@app.get("/reports/export/pdf")
def export_reports_pdf(
    request: Request,
    start: str | None = None,
    end: str | None = None,
    columns: list[str] | None = Query(None),
    preset: str | None = None,
    db: Session = Depends(get_db),
):
    _require_permission(request, PERMISSION_REPORTS)

    default_start, default_end = default_range()
    start_date = parse_date(start, default_start)
    end_date = parse_date(end, default_end)
    if end_date < start_date:
        start_date, end_date = end_date, start_date

    report = build_cost_report(db, start_date, end_date)
    selected_columns = resolve_report_export_columns(columns, preset)
    payload = build_report_pdf_bytes(start_date, end_date, report, selected_columns)
    filename = f"reporte-{start_date.isoformat()}-{end_date.isoformat()}.pdf"
    return StreamingResponse(
        BytesIO(payload),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/reports/export/png")
def export_reports_png(
    request: Request,
    start: str | None = None,
    end: str | None = None,
    columns: list[str] | None = Query(None),
    preset: str | None = None,
    db: Session = Depends(get_db),
):
    _require_permission(request, PERMISSION_REPORTS)

    default_start, default_end = default_range()
    start_date = parse_date(start, default_start)
    end_date = parse_date(end, default_end)
    if end_date < start_date:
        start_date, end_date = end_date, start_date

    report = build_cost_report(db, start_date, end_date)
    selected_columns = resolve_report_export_columns(columns, preset)
    payload = build_report_png_bytes(start_date, end_date, report, selected_columns)
    filename = f"reporte-{start_date.isoformat()}-{end_date.isoformat()}.png"
    return StreamingResponse(
        BytesIO(payload),
        media_type="image/png",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/reports")
def api_reports(
    request: Request,
    start: str | None = None,
    end: str | None = None,
    db: Session = Depends(get_db),
):
    _require_permission(request, PERMISSION_REPORTS)

    default_start, default_end = default_range()
    start_date = parse_date(start, default_start)
    end_date = parse_date(end, default_end)
    if end_date < start_date:
        start_date, end_date = end_date, start_date
    return build_cost_report(db, start_date, end_date)


@app.get("/users", response_class=HTMLResponse)
def users_page(request: Request, db: Session = Depends(get_db)):
    _require_permission(request, PERMISSION_USERS)
    users = list(db.scalars(select(User).order_by(User.username)).all())
    return _render(request, "users.html", {"users": users, "role_matrix": role_catalog()})


@app.get("/users/new", response_class=HTMLResponse)
def users_new_page(request: Request):
    _require_permission(request, PERMISSION_USERS)
    role_matrix = role_catalog()
    return _render(
        request,
        "user_form.html",
        {
            "title": "Nuevo Usuario",
            "action": "/users/new",
            "user_obj": None,
            "role_options": role_matrix,
            "role_matrix": role_matrix,
            "error": "",
        },
    )


@app.post("/users/new", response_class=HTMLResponse)
def users_new_submit(
    request: Request,
    username: str = Form(...),
    full_name: str = Form(""),
    role: str = Form(...),
    password: str = Form(...),
    is_active: str | None = Form(None),
    db: Session = Depends(get_db),
):
    _require_permission(request, PERMISSION_USERS)

    clean_username = username.strip().lower()
    active_flag = _parse_bool(is_active)
    error = ""
    if not clean_username:
        error = "El usuario es obligatorio"
    elif role not in ROLE_ORDER:
        error = "Rol invalido"
    elif len(password) < 6:
        error = "La contrasena debe tener al menos 6 caracteres"
    elif db.scalar(select(User).where(User.username == clean_username)):
        error = "Ese nombre de usuario ya existe"

    if error:
        role_matrix = role_catalog()
        return _render(
            request,
            "user_form.html",
            {
                "title": "Nuevo Usuario",
                "action": "/users/new",
                "user_obj": {"username": clean_username, "full_name": full_name, "role": role, "is_active": active_flag},
                "role_options": role_matrix,
                "role_matrix": role_matrix,
                "error": error,
            },
            status_code=400,
        )

    db.add(
        User(
            username=clean_username,
            full_name=full_name.strip(),
            role=role,
            password_hash=hash_password(password),
            is_active=active_flag,
        )
    )
    db.commit()
    return RedirectResponse(url="/users", status_code=303)


@app.get("/users/{user_id}/edit", response_class=HTMLResponse)
def users_edit_page(user_id: int, request: Request, db: Session = Depends(get_db)):
    _require_permission(request, PERMISSION_USERS)

    user_obj = db.get(User, user_id)
    if not user_obj:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    role_matrix = role_catalog()
    return _render(
        request,
        "user_form.html",
        {
            "title": "Editar Usuario",
            "action": f"/users/{user_id}/edit",
            "user_obj": user_obj,
            "role_options": role_matrix,
            "role_matrix": role_matrix,
            "error": "",
        },
    )


@app.post("/users/{user_id}/edit", response_class=HTMLResponse)
def users_edit_submit(
    user_id: int,
    request: Request,
    username: str = Form(...),
    full_name: str = Form(""),
    role: str = Form(...),
    password: str = Form(""),
    is_active: str | None = Form(None),
    db: Session = Depends(get_db),
):
    _require_permission(request, PERMISSION_USERS)

    user_obj = db.get(User, user_id)
    if not user_obj:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    current = _current_user(request) or {}
    clean_username = username.strip().lower()
    active_flag = _parse_bool(is_active)
    error = ""

    if not clean_username:
        error = "El usuario es obligatorio"
    elif role not in ROLE_ORDER:
        error = "Rol invalido"
    elif len(password) > 0 and len(password) < 6:
        error = "La contrasena debe tener al menos 6 caracteres"
    else:
        existing = db.scalar(select(User).where(User.username == clean_username, User.id != user_obj.id))
        if existing:
            error = "Ese nombre de usuario ya existe"

    if not error and user_obj.role == ROLE_ADMIN and user_obj.is_active and (role != ROLE_ADMIN or not active_flag):
        if _active_admin_count(db) <= 1:
            error = "Debe existir al menos un administrador activo"

    if not error and user_obj.id == current.get("id") and (role != ROLE_ADMIN or not active_flag):
        error = "No puedes quitarte permisos de administrador ni desactivarte a ti mismo"

    if error:
        role_matrix = role_catalog()
        return _render(
            request,
            "user_form.html",
            {
                "title": "Editar Usuario",
                "action": f"/users/{user_id}/edit",
                "user_obj": {
                    "id": user_obj.id,
                    "username": clean_username,
                    "full_name": full_name.strip(),
                    "role": role,
                    "is_active": active_flag,
                },
                "role_options": role_matrix,
                "role_matrix": role_matrix,
                "error": error,
            },
            status_code=400,
        )

    user_obj.username = clean_username
    user_obj.full_name = full_name.strip()
    user_obj.role = role
    user_obj.is_active = active_flag
    if password:
        user_obj.password_hash = hash_password(password)
    db.commit()
    return RedirectResponse(url="/users", status_code=303)


@app.get("/security", response_class=HTMLResponse)
def security_page(request: Request, saved: str | None = None, db: Session = Depends(get_db)):
    _require_permission(request, PERMISSION_SECURITY)
    return _render(
        request,
        "security.html",
        {
            "security_fields": build_security_form_fields(db),
            "security_errors": {},
            "saved": saved == "1",
        },
    )


@app.post("/security", response_class=HTMLResponse)
async def security_submit(request: Request, db: Session = Depends(get_db)):
    _require_permission(request, PERMISSION_SECURITY)
    form = await request.form()
    payload = {key: str(value) for key, value in form.items()}
    cleaned_values, errors = validate_security_form_values(payload)
    if errors:
        return _render(
            request,
            "security.html",
            {
                "security_fields": build_security_form_fields(db, payload),
                "security_errors": errors,
                "saved": False,
            },
            status_code=400,
        )

    save_security_settings(db, cleaned_values)
    return RedirectResponse(url="/security?saved=1", status_code=303)


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(BASE_DIR / "static" / "favicon.ico", media_type="image/x-icon")


@app.get("/health")
def health():
    return {"status": "ok"}
