#!/usr/bin/env bash
#
# FinanceBuddy PRODUCTION — starts the live stack (no demo data).
# Runs docker-compose.prod.yml with .env.production: its own Postgres, Redis (password
# protected, not published on host ports), migrations, API, event worker and web.
# First run creates .env.production with freshly generated secrets, then stops so you can
# fill in the CHANGE_ME values (public URL, CORS origins, provider keys).
#
# Usage:
#   ./start-prod.sh          # validate config, build, migrate, start
#   ./start-prod.sh --down   # stop the production stack (data kept)
set -euo pipefail
cd "$(dirname "$0")"
ENV_FILE=.env.production
COMPOSE=(docker compose -f docker-compose.prod.yml --env-file "$ENV_FILE")

command -v docker >/dev/null || { echo "Docker is required." >&2; exit 1; }
[ "${1:-}" = "--down" ] && exec "${COMPOSE[@]}" down
[ -z "${1:-}" ] || { echo "Usage: $0 [--down]" >&2; exit 1; }

secret() { openssl rand -hex 32 2>/dev/null || od -An -tx1 -N32 /dev/urandom | tr -d ' \n'; }

# First run: create the env file with generated secrets, then stop for the manual values.
if [ ! -f "$ENV_FILE" ]; then
  umask 077
  while IFS= read -r line || [ -n "$line" ]; do
    if [[ "$line" =~ ^([A-Z_]+)=GENERATE_ME$ ]]; then echo "${BASH_REMATCH[1]}=$(secret)"; else echo "$line"; fi
  done < .env.production.example > "$ENV_FILE"
  echo "Created $ENV_FILE (mode 600) with generated SECRET_KEY, DATA_ENCRYPTION_KEY, POSTGRES_PASSWORD, REDIS_PASSWORD."
  echo "BACK THIS FILE UP. Losing DATA_ENCRYPTION_KEY makes encrypted user data unrecoverable."
  echo "Now edit $ENV_FILE, replace every CHANGE_ME (PUBLIC_API_URL, CORS_ORIGINS), add provider keys, and re-run."
  exit 1
fi

# Refuse to start on placeholders or on values copied from the demo/dev setup.
problems=$(grep -E '^[A-Z_]+=(CHANGE_ME|GENERATE_ME)[[:space:]]*$' "$ENV_FILE" | cut -d= -f1 || true)
problems+=" $(grep -E '^(SECRET_KEY|DATA_ENCRYPTION_KEY|POSTGRES_PASSWORD|REDIS_PASSWORD)=.*(00112233445566778899aabbccddeeff|financebuddy_demo|change-me)' "$ENV_FILE" | cut -d= -f1 || true)"
if [ -n "${problems// /}" ]; then
  echo "Fix these in $ENV_FILE before starting production:" $problems >&2
  exit 1
fi

echo "Building and starting the PRODUCTION stack..."
"${COMPOSE[@]}" up -d --build || {
  echo "Start failed. Check: ${COMPOSE[*]} logs migrate api" >&2; exit 1; }

API_PORT=$(grep -E '^API_PORT=' "$ENV_FILE" | cut -d= -f2); API_PORT=${API_PORT:-8000}
for _ in $(seq 1 90); do
  curl -fsS -o /dev/null --max-time 3 "http://localhost:$API_PORT/api/v1/health" && break
  sleep 2
done
curl -fsS -o /dev/null --max-time 3 "http://localhost:$API_PORT/api/v1/health" || {
  echo "API did not become healthy. Logs: ${COMPOSE[*]} logs api" >&2; exit 1; }

cat <<EOF

  FinanceBuddy PRODUCTION is running (API on port $API_PORT)
  No demo account exists: the first person to sign up creates the first real account.
  Serve it over HTTPS via a reverse proxy; API docs are disabled in production.
  Stop: ./start-prod.sh --down
EOF
