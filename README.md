# Que Cocino Hoy

Aplicacion web en Python para ayudar a planificar que cocinar en casa, incluyendo:

- menu semanal (lunes a domingo) para desayuno, almuerzo, cena, lonchera y refresco,
- generacion aleatoria con reglas de no repeticion semanal previa y reutilizacion de ingredientes,
- estimacion de costo familiar en soles peruanos,
- evaluacion nutricional y advertencias por plato,
- reportes de gasto diarios, semanales, mensuales y por rango de fechas.
- descarga de menu semanal y reportes en PDF y PNG.
- seleccion de columnas a exportar en menu y reportes.
- plantillas de exportacion (`completo`, `resumen`, `finanzas`, `nutricion`) para no marcar columnas cada vez.
- comparticion por WhatsApp mediante mensaje con enlaces.
- autenticacion con login y control de acceso por roles.
- proteccion anti-fuerza-bruta local (sin proveedores externos): bloqueo temporal por IP/usuario, honeypot, nonce de formulario y desafio matematico progresivo.

## Stack tecnico

- FastAPI (backend + rutas web)
- SQLAlchemy + SQLite
- Jinja2 + Bootstrap (UI)
- Docker (listo para Azure Container Apps y futura migracion a AKS)

## Estructura

```text
app/
  config.py
  main.py
  database.py
  models.py
  seed_data.py
  services/
    auth.py
    login_guard.py
    export_table.py
    menu_export.py
    menu_generator.py
    nutrition.py
    report_export.py
    reports.py
  templates/
  static/
data/
requirements.txt
Dockerfile
```

## Ejecutar local

1. Crear entorno e instalar dependencias:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

2. Levantar el servidor:

```bash
uvicorn app.main:app --reload
```

3. Abrir:

```text
http://127.0.0.1:8000
```

La primera vez se crean tablas y se cargan platos base automaticamente.

## Ejecutar con Docker

```bash
docker build -t quecocinohoy .
docker run --rm -p 8000:8000 quecocinohoy
```

El contenedor expone `0.0.0.0` y usa `PORT` (por defecto `8000`), compatible con Azure Container Apps.

## Endpoints clave

- `GET /login` y `POST /login` autenticacion
- `POST /logout` cierre de sesion
- `GET /` inicio y generacion de menu semanal
- `GET /dishes` CRUD de platos
- `GET /menus` visualizacion del menu semanal
- `GET /reports` reportes de gasto y nutricion
- `GET /api/reports` reporte en JSON por rango de fechas
- `GET /menus/export/pdf?week_start=YYYY-MM-DD&columns=...&preset=...` descargar menu semanal en PDF
- `GET /menus/export/png?week_start=YYYY-MM-DD&columns=...&preset=...` descargar menu semanal en PNG
- `GET /reports/export/pdf?start=YYYY-MM-DD&end=YYYY-MM-DD&columns=...&preset=...` descargar reporte en PDF
- `GET /reports/export/png?start=YYYY-MM-DD&end=YYYY-MM-DD&columns=...&preset=...` descargar reporte en PNG
- `GET /menus/share/whatsapp?week_start=YYYY-MM-DD&columns=...&preset=...` abrir WhatsApp con mensaje prellenado
- `GET /users` administracion de usuarios (solo admin)
- `GET /security` configuracion de seguridad de login (solo admin)
- `GET /health` health check

## Roles y permisos

Roles actuales recomendados:

- `admin`: acceso total (inicio, menu, platos, reportes, usuarios, seguridad).
- `operations_manager`: operacion completa de menu/platos/reportes (sin usuarios/seguridad).
- `menu_operator`: inicio + menu semanal.
- `catalog_editor`: inicio + mantenimiento de platos.
- `nutrition_analyst`: inicio + menu + reportes.
- `finance_analyst`: inicio + reportes.
- `security_admin`: inicio + usuarios + seguridad.
- `viewer`: solo inicio.

Roles legacy soportados por compatibilidad:

- `menu_maintainer` (equivalente funcional a `operations_manager`).
- `menu_only` (equivalente funcional a `menu_operator`).
- `home_only` (equivalente funcional a `viewer`).

Usuario inicial por defecto:

- Usuario: `admin`
- Contrasena: `admin123`

Flujo recomendado:

1. Iniciar sesion con `admin`.
2. Ir a `Usuarios` y crear cuentas por rol.
3. Probar acceso segun privilegios asignados.

Puedes cambiarlo con variables de entorno:

- `ADMIN_USERNAME`
- `ADMIN_FULL_NAME`
- `ADMIN_INITIAL_PASSWORD`
- `SESSION_SECRET_KEY`
- `LOGIN_GUARD_TRUST_LOCALHOST` (`1` por defecto para no bloquear en `127.0.0.1`; en produccion usar `0`)
- `LOGIN_NONCE_MAX_AGE_SECONDS` (por defecto `900`)

Configuracion central:

- `app/config.py` concentra valores generales (sesion, admin inicial y seguridad de login) con fallback a variables de entorno.
- La pagina `Seguridad` permite sobreescribir parametros de login en base de datos sin editar entorno.

## Seguridad administrable (pagina `/security`)

Todos estos valores muestran descripcion y ejemplo dentro de la UI:

- `Confiar en localhost`: relaja controles en `127.0.0.1` para desarrollo local.
- `Vigencia del formulario (segundos)`: tiempo maximo para enviar login antes de "sesion expirada". Ejemplo: `900`.
- `Ventana de analisis (minutos)`: periodo sobre el que se cuentan fallos recientes. Ejemplo: `15`.
- `Desafio por combo/usuario/IP`: define cuando aparece la validacion matematica.
- `Bloqueo por combo/usuario/IP`: define cuando se activa bloqueo temporal.
- `Duracion bloqueo combo/usuario/IP`: minutos de espera antes de permitir nuevos intentos.

Regla de persistencia:

- Si guardas un valor igual al default, se elimina override y el sistema vuelve al valor base.

## Reglas implementadas del PDF

- Crea/modifica/elimina/busca platos.
- Genera menu semanal con seleccion aleatoria ponderada.
- Evita repetir platos de la semana anterior (si hay alternativas).
- Favorece reutilizacion de ingredientes para optimizar compra.
- Calcula costo estimado por comida, por dia y por semana.
- Muestra beneficios y advertencias nutricionales (perjuicios).
- Permite reportes diarios, semanales, mensuales y por rango de fechas.

## Despliegue en Azure Container Apps (Cloud Shell, bajo costo)

Este repo incluye un script reutilizable: `deploy.sh`.

Que hace:

- Usa `westus3` por defecto (puedes cambiar con `LOCATION=...`).
- Crea/reutiliza Resource Group, Container Apps Environment, App y PostgreSQL.
- Despliega con `az containerapp up --source .` (evita el flujo `--repo` que intenta crear Service Principal/GitHub Actions).
- Configura variables de entorno, incluyendo `DATABASE_URL` para PostgreSQL.

Paso a paso:

1. Abre Azure Cloud Shell y clona el repo:

```bash
git clone https://github.com/franter007/quecocinohoy.git
cd quecocinohoy
```

2. Ejecuta el despliegue con defaults de bajo costo:

```bash
bash deploy.sh
```

3. Opcional: sobreescribe parametros sin editar el script:

```bash
LOCATION=westus3 APP_BASE=qch-prod PG_PASS='TuPass#Segura123' bash deploy.sh
```

Notas:

- SQLite en `data/quecocinohoy.db` no es persistente en Container Apps.
- En Azure, usa PostgreSQL (`DATABASE_URL`) para persistencia real.
- Si el servidor PostgreSQL ya existe y quieres recalcular `DATABASE_URL`, ejecuta con `PG_PASS=...`.
