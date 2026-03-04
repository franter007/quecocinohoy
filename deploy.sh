#!/usr/bin/env bash
set -euo pipefail

# -----------------------------------------------------------------------------
# Deploy reutilizable para Que Cocino Hoy en Azure Container Apps + PostgreSQL.
# Disenado para ejecutarse desde Azure Cloud Shell, en la raiz del repo.
#
# Objetivo: bajo costo y cero creacion de recursos aleatorios en cada corrida.
# - Region por defecto: westus3 (puedes sobrescribir con LOCATION=...)
# - Reutiliza RG/Env/App/PG si ya existen.
# - Evita flujo --repo (GitHub Actions) para no fallar por Service Principal.
# -----------------------------------------------------------------------------

echo "== Validaciones previas =="
command -v az >/dev/null || { echo "Azure CLI no encontrado."; exit 1; }
command -v python3 >/dev/null || { echo "python3 no encontrado."; exit 1; }

if [ ! -f "Dockerfile" ] || [ ! -f "requirements.txt" ]; then
  echo "Ejecuta este script desde la raiz del repositorio (faltan Dockerfile/requirements.txt)."
  exit 1
fi

SUB_ID="$(az account show --query id -o tsv)"
if [ -z "$SUB_ID" ]; then
  echo "No hay suscripcion activa. Ejecuta: az login"
  exit 1
fi

SUB_HASH="$(echo "$SUB_ID" | tr -d '-' | cut -c1-6)"

# ----- Configuracion (sobrescribible por variable de entorno) -----
LOCATION="${LOCATION:-westus3}"
APP_BASE="${APP_BASE:-qch-${SUB_HASH}}"

RG="${RG:-rg-${APP_BASE}}"
ACA_ENV="${ACA_ENV:-acaenv-${APP_BASE}}"
ACA_APP="${ACA_APP:-aca-${APP_BASE}}"

# PostgreSQL Flexible Server requiere nombre global unico (sin guiones recomendado).
PG_SERVER="${PG_SERVER:-pgqch${SUB_HASH}}"
PG_DB="${PG_DB:-quecocinohoy}"
PG_ADMIN="${PG_ADMIN:-qchadmin}"
PG_PASS="${PG_PASS:-}"

# App secrets/config
SESSION_SECRET="${SESSION_SECRET:-$(openssl rand -hex 32)}"
ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
ADMIN_FULL_NAME="${ADMIN_FULL_NAME:-Administrador Principal}"
ADMIN_INITIAL_PASSWORD="${ADMIN_INITIAL_PASSWORD:-Admin#$(date +%s)Aa}"
LOGIN_GUARD_TRUST_LOCALHOST="${LOGIN_GUARD_TRUST_LOCALHOST:-0}"
LOGIN_NONCE_MAX_AGE_SECONDS="${LOGIN_NONCE_MAX_AGE_SECONDS:-900}"

echo "== Configuracion efectiva =="
echo "SUBSCRIPTION=$SUB_ID"
echo "LOCATION=$LOCATION"
echo "RG=$RG"
echo "ACA_ENV=$ACA_ENV"
echo "ACA_APP=$ACA_APP"
echo "PG_SERVER=$PG_SERVER"
echo "PG_DB=$PG_DB"

echo "== 1) Resource Group =="
az group create -n "$RG" -l "$LOCATION" -o none

echo "== 2) PostgreSQL Flexible Server =="
UPDATE_DB_URL=0
if az postgres flexible-server show -g "$RG" -n "$PG_SERVER" >/dev/null 2>&1; then
  echo "Servidor PostgreSQL ya existe: $PG_SERVER"
  if [ -n "$PG_PASS" ]; then
    UPDATE_DB_URL=1
  else
    echo "PG_PASS no fue enviado; se mantendra DATABASE_URL actual de la app."
    echo "Si necesitas actualizar DATABASE_URL, exporta PG_PASS y vuelve a correr."
  fi
else
  if [ -z "$PG_PASS" ]; then
    PG_PASS="Qch#$(date +%s)Aa"
  fi

  az postgres flexible-server create \
    -g "$RG" \
    -n "$PG_SERVER" \
    -l "$LOCATION" \
    --admin-user "$PG_ADMIN" \
    --admin-password "$PG_PASS" \
    --sku-name Standard_B1ms \
    --tier Burstable \
    --storage-size 32 \
    --version 17 \
    --public-access 0.0.0.0 \
    -o none

  # Crea BD de negocio (idempotente simple).
  if ! az postgres flexible-server db show -g "$RG" -s "$PG_SERVER" -d "$PG_DB" >/dev/null 2>&1; then
    az postgres flexible-server db create -g "$RG" -s "$PG_SERVER" -d "$PG_DB" -o none
  fi

  # Permitir trafico desde servicios Azure (Container Apps).
  az postgres flexible-server firewall-rule create \
    -g "$RG" \
    -n "$PG_SERVER" \
    --rule-name allow-azure-services \
    --start-ip-address 0.0.0.0 \
    --end-ip-address 0.0.0.0 \
    -o none || true

  UPDATE_DB_URL=1
fi

echo "== 3) Container Apps Environment =="
if az containerapp env show -g "$RG" -n "$ACA_ENV" >/dev/null 2>&1; then
  echo "Container Apps Environment ya existe: $ACA_ENV"
else
  az containerapp env create \
    -g "$RG" \
    -n "$ACA_ENV" \
    -l "$LOCATION" \
    -o none
fi

echo "== 4) Build + Deploy app (sin GitHub Actions) =="
# Usa codigo local (--source .) para evitar el flujo --repo que crea service principal.
az containerapp up \
  --name "$ACA_APP" \
  --resource-group "$RG" \
  --location "$LOCATION" \
  --environment "$ACA_ENV" \
  --source . \
  --ingress external \
  --target-port 8000

echo "== 5) Variables de entorno app =="
ENV_ARGS=(
  "SESSION_SECRET_KEY=$SESSION_SECRET"
  "ADMIN_USERNAME=$ADMIN_USERNAME"
  "ADMIN_FULL_NAME=$ADMIN_FULL_NAME"
  "ADMIN_INITIAL_PASSWORD=$ADMIN_INITIAL_PASSWORD"
  "LOGIN_GUARD_TRUST_LOCALHOST=$LOGIN_GUARD_TRUST_LOCALHOST"
  "LOGIN_NONCE_MAX_AGE_SECONDS=$LOGIN_NONCE_MAX_AGE_SECONDS"
)

if [ "$UPDATE_DB_URL" -eq 1 ]; then
  PG_FQDN="$(az postgres flexible-server show -g "$RG" -n "$PG_SERVER" --query fullyQualifiedDomainName -o tsv)"
  PG_PASS_URL="$(python3 - "$PG_PASS" <<'PY'
import urllib.parse
import sys
print(urllib.parse.quote(sys.argv[1], safe=""))
PY
)"
  DATABASE_URL="postgresql+psycopg://${PG_ADMIN}:${PG_PASS_URL}@${PG_FQDN}:5432/${PG_DB}?sslmode=require"
  ENV_ARGS+=("DATABASE_URL=$DATABASE_URL")
fi

az containerapp update \
  -g "$RG" \
  -n "$ACA_APP" \
  --set-env-vars "${ENV_ARGS[@]}" \
  -o none

echo "== 6) Resultado =="
FQDN="$(az containerapp show -g "$RG" -n "$ACA_APP" --query properties.configuration.ingress.fqdn -o tsv)"
APP_URL="https://${FQDN}"

echo "APP_URL=$APP_URL"
echo "ADMIN_USER=$ADMIN_USERNAME"
echo "ADMIN_PASS=$ADMIN_INITIAL_PASSWORD"
echo "RG=$RG"
echo "ACA_ENV=$ACA_ENV"
echo "ACA_APP=$ACA_APP"
echo "PG_SERVER=$PG_SERVER"
echo "PG_DB=$PG_DB"
if [ "$UPDATE_DB_URL" -eq 1 ]; then
  echo "PG_ADMIN=$PG_ADMIN"
  echo "PG_PASS=$PG_PASS"
fi

echo "== 7) Health check =="
for i in {1..24}; do
  code="$(curl -sS -o /tmp/qch-health.json -w "%{http_code}" "$APP_URL/health" || true)"
  if [ "$code" = "200" ]; then
    echo "Health OK: $(cat /tmp/qch-health.json)"
    exit 0
  fi
  sleep 10
done

echo "No hubo 200 en /health. Revisa logs con:"
echo "az containerapp logs show -g $RG -n $ACA_APP --follow"
