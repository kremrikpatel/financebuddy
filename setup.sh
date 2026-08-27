#!/usr/bin/env bash
#
# FinanceBuddy — One-command setup & launch (macOS / Linux)
#
# Usage:
#   ./setup.sh              # Full setup + launch
#   ./setup.sh --skip-docker   # Skip Docker (use existing postgres/redis)
#   ./setup.sh --reset-db      # Drop and recreate the database
#   ./setup.sh --skip-frontend # Only start the backend API
#   ./setup.sh --skip-backend  # Only start the frontend
#
set -euo pipefail

# ── Colours & helpers ───────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
GRAY='\033[0;90m'
WHITE='\033[1;37m'
NC='\033[0m' # No colour

step()  { printf "\n${CYAN}▶ %s${NC}\n" "$1"; }
ok()    { printf "  ${GREEN}✓ %s${NC}\n" "$1"; }
warn()  { printf "  ${YELLOW}⚠ %s${NC}\n" "$1"; }
err()   { printf "  ${RED}✗ %s${NC}\n" "$1"; }
info()  { printf "  ${GRAY}ℹ %s${NC}\n" "$1"; }

# ── Parse arguments ─────────────────────────────────────────────────────────
SKIP_DOCKER=false
RESET_DB=false
SKIP_FRONTEND=false
SKIP_BACKEND=false

for arg in "$@"; do
    case "$arg" in
        --skip-docker)   SKIP_DOCKER=true ;;
        --reset-db)      RESET_DB=true ;;
        --skip-frontend) SKIP_FRONTEND=true ;;
        --skip-backend)  SKIP_BACKEND=true ;;
        -h|--help)
            echo "Usage: $0 [--skip-docker] [--reset-db] [--skip-frontend] [--skip-backend]"
            exit 0
            ;;
        *) err "Unknown argument: $arg"; exit 1 ;;
    esac
done

# ── Paths ───────────────────────────────────────────────────────────────────
ROOT="$(cd "$(dirname "$0")" && pwd)"
SERVER="$ROOT/server"
WEB="$ROOT/apps/web"
VENV="$SERVER/.venv"

# ── Cleanup on exit ─────────────────────────────────────────────────────────
PIDS=()
cleanup() {
    printf "\n\n${YELLOW}Shutting down...${NC}\n"
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
        wait "$pid" 2>/dev/null || true
    done
    printf "${GREEN}All services stopped.${NC}\n"
}
trap cleanup EXIT INT TERM

# ── 1. Prerequisites ───────────────────────────────────────────────────────
echo ""
printf "${MAGENTA}╔══════════════════════════════════════════════════════╗${NC}\n"
printf "${MAGENTA}║           FinanceBuddy — Setup & Launch              ║${NC}\n"
printf "${MAGENTA}╚══════════════════════════════════════════════════════╝${NC}\n"

step "Checking prerequisites..."

# Python
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" --version 2>&1)
        if echo "$ver" | grep -qE "Python 3\.(1[1-9]|[2-9][0-9])"; then
            PYTHON="$cmd"
            ok "Python: $ver"
            break
        fi
    fi
done
if [ -z "$PYTHON" ]; then
    err "Python 3.11+ is required but not found."
    info "Install: https://python.org (or use your package manager)"
    info "  macOS:  brew install python@3.12"
    info "  Ubuntu: sudo apt install python3.12 python3.12-venv"
    exit 1
fi

# Node.js
if command -v node &>/dev/null; then
    NODE_VER=$(node --version)
    NODE_MAJOR=$(echo "$NODE_VER" | sed 's/v//' | cut -d. -f1)
    if [ "$NODE_MAJOR" -ge 18 ]; then
        ok "Node.js: $NODE_VER"
    else
        err "Node.js 18+ required (found $NODE_VER). Install from https://nodejs.org"
        exit 1
    fi
else
    err "Node.js is required but not found. Install from https://nodejs.org"
    info "  macOS:  brew install node"
    info "  Ubuntu: curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt install -y nodejs"
    exit 1
fi

# Docker
if [ "$SKIP_DOCKER" = false ]; then
    if command -v docker &>/dev/null; then
        ok "Docker: $(docker --version)"
    else
        err "Docker is required but not found. Use --skip-docker if postgres/redis are running elsewhere."
        exit 1
    fi

    if docker compose version &>/dev/null; then
        ok "Docker Compose: $(docker compose version --short 2>/dev/null || echo 'available')"
    else
        err "Docker Compose is required."
        exit 1
    fi
fi

# ── 2. Environment file ────────────────────────────────────────────────────
step "Checking environment configuration..."

ENV_FILE="$ROOT/.env"
ENV_EXAMPLE="$ROOT/.env.example"

if [ ! -f "$ENV_FILE" ]; then
    if [ -f "$ENV_EXAMPLE" ]; then
        cp "$ENV_EXAMPLE" "$ENV_FILE"
        ok "Created .env from .env.example"
    else
        warn "No .env.example found — creating minimal .env"
        SECRET=$(openssl rand -hex 32 2>/dev/null || head -c 32 /dev/urandom | xxd -p | tr -d '\n')
        DEK=$(openssl rand -hex 32 2>/dev/null || head -c 32 /dev/urandom | xxd -p | tr -d '\n')
        cat > "$ENV_FILE" <<EOF
APP_ENV=development
SECRET_KEY=$SECRET
DATABASE_URL=postgresql+asyncpg://financebuddy:financebuddy@localhost:5432/financebuddy
REDIS_URL=redis://localhost:6379/0
CORS_ORIGINS=["http://localhost:5173","tauri://localhost","http://tauri.localhost"]
DATA_ENCRYPTION_KEY=$DEK
EOF
        ok "Created minimal .env"
    fi
else
    ok ".env already exists"
fi

# ── 3. Docker infrastructure ───────────────────────────────────────────────
if [ "$SKIP_DOCKER" = false ]; then
    step "Starting Docker infrastructure (PostgreSQL + Redis)..."

    docker compose -f "$ROOT/docker-compose.yml" up -d postgres redis 2>&1 | tail -2

    info "Waiting for PostgreSQL to be ready..."
    MAX_WAIT=60
    WAITED=0
    while [ $WAITED -lt $MAX_WAIT ]; do
        HEALTH=$(docker inspect --format '{{.State.Health.Status}}' financebuddy-postgres-1 2>/dev/null || echo "waiting")
        if [ "$HEALTH" = "healthy" ]; then
            ok "PostgreSQL is healthy"
            break
        fi
        sleep 2
        WAITED=$((WAITED + 2))
    done
    [ $WAITED -ge $MAX_WAIT ] && warn "PostgreSQL health check timed out — continuing anyway"

    info "Waiting for Redis to be ready..."
    WAITED=0
    while [ $WAITED -lt 30 ]; do
        HEALTH=$(docker inspect --format '{{.State.Health.Status}}' financebuddy-redis-1 2>/dev/null || echo "waiting")
        if [ "$HEALTH" = "healthy" ]; then
            ok "Redis is healthy"
            break
        fi
        sleep 2
        WAITED=$((WAITED + 2))
    done
    [ $WAITED -ge 30 ] && warn "Redis health check timed out — continuing anyway"
else
    info "Skipping Docker (--skip-docker)"
fi

# ── 4. Python virtual environment ──────────────────────────────────────────
step "Setting up Python virtual environment..."

if [ ! -d "$VENV" ]; then
    $PYTHON -m venv "$VENV"
    ok "Created virtual environment at server/.venv"
else
    ok "Virtual environment already exists"
fi

# Activate venv
source "$VENV/bin/activate"

# Configure pip to trust PyPI hosts (workaround for SSL cert issues)
mkdir -p "$VENV"
cat > "$VENV/pip.conf" <<EOF
[global]
trusted-host = pypi.org
               pypi.python.org
               files.pythonhosted.org
EOF

# ── 5. Install Python dependencies ─────────────────────────────────────────
step "Installing Python dependencies..."

info "Upgrading pip..."
pip install --upgrade pip --quiet 2>/dev/null || pip install --upgrade pip
ok "pip upgraded"

info "Installing core + dev dependencies (this may take a few minutes)..."
pip install -e "$SERVER/.[dev]" --quiet 2>/dev/null || pip install -e "$SERVER/.[dev]"
if [ $? -ne 0 ]; then
    err "Failed to install Python dependencies."
    exit 1
fi
ok "Python dependencies installed"

# ── 6. Database migrations ──────────────────────────────────────────────────
step "Running database migrations..."

if [ "$RESET_DB" = true ]; then
    warn "Resetting database (--reset-db)..."
    python -c "
import asyncio, asyncpg
async def reset():
    conn = await asyncpg.connect('postgresql://financebuddy:financebuddy@localhost:5432/financebuddy')
    await conn.execute('DROP SCHEMA public CASCADE; CREATE SCHEMA public;')
    await conn.execute('CREATE EXTENSION IF NOT EXISTS vector;')
    await conn.close()
asyncio.run(reset())
" 2>/dev/null || warn "Database reset failed (may not exist yet — this is fine)"
    ok "Database reset"
fi

cd "$SERVER"
alembic upgrade head
ok "Migrations applied successfully"
cd "$ROOT"

# ── 7. Seed demo data ──────────────────────────────────────────────────────
step "Seeding demo data..."

cd "$SERVER"
python -m app.seed && ok "Demo data seeded" || warn "Seeding returned non-zero (data may already exist)"
cd "$ROOT"

# ── 8. Install frontend dependencies ───────────────────────────────────────
if [ "$SKIP_FRONTEND" = false ]; then
    step "Installing frontend dependencies..."

    cd "$WEB"
    npm install --silent 2>/dev/null || npm install
    ok "Frontend dependencies installed"
    cd "$ROOT"
fi

# ── 9. Launch services ─────────────────────────────────────────────────────
echo ""
printf "${GREEN}╔══════════════════════════════════════════════════════╗${NC}\n"
printf "${GREEN}║              Setup Complete — Launching!             ║${NC}\n"
printf "${GREEN}╚══════════════════════════════════════════════════════╝${NC}\n"
echo ""
printf "  ${WHITE}🌐 Frontend:  http://localhost:5173${NC}\n"
printf "  ${WHITE}🔧 API:       http://localhost:8000${NC}\n"
printf "  ${WHITE}📚 API Docs:  http://localhost:8000/docs${NC}\n"
printf "  ${WHITE}👤 Demo Login: demo@financebuddy.app / DemoPass123!${NC}\n"
echo ""
printf "  ${GRAY}Press Ctrl+C to stop all services${NC}\n"
echo ""

# Start backend API server
if [ "$SKIP_BACKEND" = false ]; then
    cd "$SERVER"
    uvicorn app.main:app --reload --port 8000 &
    PIDS+=($!)
    ok "API server starting (PID ${PIDS[-1]})..."
    cd "$ROOT"
fi

# Start event worker
cd "$SERVER"
python -m app.workers.event_consumer &
PIDS+=($!)
ok "Event worker starting (PID ${PIDS[-1]})..."
cd "$ROOT"

# Give the API a moment to start
sleep 3

# Try to open browser
if [ "$SKIP_FRONTEND" = false ]; then
    if command -v open &>/dev/null; then
        open "http://localhost:5173" 2>/dev/null &
    elif command -v xdg-open &>/dev/null; then
        xdg-open "http://localhost:5173" 2>/dev/null &
    fi

    # Run frontend in foreground (Ctrl+C stops everything)
    cd "$WEB"
    exec npm run dev
else
    info "Frontend skipped (--skip-frontend). API running at http://localhost:8000"
    info "Press Ctrl+C to stop..."
    wait
fi
