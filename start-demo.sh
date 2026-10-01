#!/usr/bin/env bash
#
# FinanceBuddy DEMO — starts the demo stack with a seeded demo account.
# Runs docker-compose.demo.yml: its own Postgres (financebuddy_demo), Redis, API and web.
# Nothing here touches the production database.
#
# Usage:
#   ./start-demo.sh          # build + start (demo data is seeded on first start)
#   ./start-demo.sh --reset  # wipe the demo database and start fresh
#   ./start-demo.sh --down   # stop the demo stack (data kept)
set -euo pipefail
cd "$(dirname "$0")"
COMPOSE=(docker compose -f docker-compose.demo.yml --env-file .env.demo)

command -v docker >/dev/null || { echo "Docker is required." >&2; exit 1; }
[ -f .env.demo ] || { cp .env.demo.example .env.demo; echo "Created .env.demo from .env.demo.example"; }

case "${1:-}" in
  --down)  exec "${COMPOSE[@]}" down ;;
  --reset) echo "Wiping the DEMO database volume (production is untouched)..."; "${COMPOSE[@]}" down -v ;;
  "") ;;
  *) echo "Usage: $0 [--reset|--down]" >&2; exit 1 ;;
esac

echo "Building and starting the DEMO stack..."
"${COMPOSE[@]}" up -d --build

echo "Waiting for the API (migrations + demo seed run on start)..."
for _ in $(seq 1 90); do
  curl -fsS -o /dev/null --max-time 3 http://localhost:8000/api/v1/health && break
  sleep 2
done
curl -fsS -o /dev/null --max-time 3 http://localhost:8000/api/v1/health || {
  echo "API did not become healthy. Logs: docker compose -f docker-compose.demo.yml logs api" >&2; exit 1; }

cat <<EOF

  FinanceBuddy DEMO is running
  App:        http://localhost:5173
  API docs:   http://localhost:8000/docs
  Demo login: demo@financebuddy.app / DemoPass123!
  Stop:       ./start-demo.sh --down    Reset data: ./start-demo.sh --reset
EOF
