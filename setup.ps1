<#
.SYNOPSIS
    FinanceBuddy  One-command setup & launch (Windows PowerShell)
.DESCRIPTION
    Checks prerequisites, starts Docker infrastructure, installs Python & Node
    dependencies, runs database migrations, seeds demo data, and launches the
    API server + frontend dev server.
.EXAMPLE
    .\setup.ps1              # Full setup + launch
    .\setup.ps1 -SkipDocker  # Skip Docker (use existing postgres/redis)
    .\setup.ps1 -ResetDB     # Drop and recreate the database
#>
[CmdletBinding()]
param(
    [switch]$SkipDocker,
    [switch]$ResetDB,
    [switch]$SkipFrontend,
    [switch]$SkipBackend
)



#  Colours & helpers 
function Write-Step  { param($msg) Write-Host "`n $msg" -ForegroundColor Cyan }
function Write-Ok    { param($msg) Write-Host "   $msg" -ForegroundColor Green }
function Write-Warn  { param($msg) Write-Host "   $msg" -ForegroundColor Yellow }
function Write-Err   { param($msg) Write-Host "   $msg" -ForegroundColor Red }
function Write-Info  { param($msg) Write-Host "   $msg" -ForegroundColor Gray }

$ROOT = $PSScriptRoot
if (-not $ROOT) { $ROOT = (Get-Location).Path }
$SERVER = Join-Path $ROOT "server"
$WEB    = Join-Path (Join-Path $ROOT "apps") "web"
$VENV   = Join-Path $SERVER ".venv"

#  1. Prerequisites 
Write-Host ""
Write-Host "" -ForegroundColor Magenta
Write-Host "           FinanceBuddy  Setup & Launch              " -ForegroundColor Magenta
Write-Host "" -ForegroundColor Magenta

Write-Step "Checking prerequisites..."

# Python
$python = $null
foreach ($cmd in @("python3", "python", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python 3\.(\d+)") {
            $minor = [int]$Matches[1]
            if ($minor -ge 11) {
                $python = $cmd
                Write-Ok "Python: $ver"
                break
            }
        }
    } catch {}
}
if (-not $python) {
    Write-Err "Python 3.11+ is required but not found. Install from https://python.org"
    exit 1
}

# Node.js
try {
    $nodeVer = & node --version 2>&1
    if ($nodeVer -match "v(\d+)\.") {
        $nodeMajor = [int]$Matches[1]
        if ($nodeMajor -ge 18) {
            Write-Ok "Node.js: $nodeVer"
        } else {
            Write-Err "Node.js 18+ required (found $nodeVer). Install from https://nodejs.org"
            exit 1
        }
    }
} catch {
    Write-Err "Node.js is required but not found. Install from https://nodejs.org"
    exit 1
}

# Docker
if (-not $SkipDocker) {
    try {
        $dockerVer = & docker --version 2>&1
        Write-Ok "Docker: $dockerVer"
    } catch {
        Write-Err "Docker is required but not found. Install Docker Desktop or use -SkipDocker"
        exit 1
    }

    try {
        $composeVer = & docker compose version 2>&1
        Write-Ok "Docker Compose: $composeVer"
    } catch {
        Write-Err "Docker Compose is required. Install Docker Desktop (includes Compose)"
        exit 1
    }
}

#  2. Environment file 
Write-Step "Checking environment configuration..."

$envFile = Join-Path $ROOT ".env"
$envExample = Join-Path $ROOT ".env.example"

if (-not (Test-Path $envFile)) {
    if (Test-Path $envExample) {
        Copy-Item $envExample $envFile
        Write-Ok "Created .env from .env.example"
    } else {
        Write-Warn "No .env.example found  creating minimal .env"
        $envContent = @(
            "APP_ENV=development",
            "SECRET_KEY=$(([guid]::NewGuid().ToString() + [guid]::NewGuid().ToString()).Replace('-','').Substring(0,64))",
            "DATABASE_URL=postgresql+asyncpg://financebuddy:financebuddy@localhost:5432/financebuddy",
            "REDIS_URL=redis://localhost:6379/0",
            'CORS_ORIGINS=["http://localhost:5173","tauri://localhost","http://tauri.localhost"]',
            "DATA_ENCRYPTION_KEY=$((1..32 | ForEach-Object { '{0:x2}' -f (Get-Random -Max 256) }) -join '')"
        )
        $envContent | Set-Content $envFile -Encoding UTF8
        Write-Ok "Created minimal .env"
    }
} else {
    Write-Ok ".env already exists"
}

#  3. Docker infrastructure 
if (-not $SkipDocker) {
    Write-Step "Starting Docker infrastructure (PostgreSQL + Redis)..."

    & docker compose -f (Join-Path $ROOT "docker-compose.yml") up -d postgres redis 2>&1 | Out-Null

    # Wait for healthy
    Write-Info "Waiting for PostgreSQL to be ready..."
    $maxWait = 60
    $waited = 0
    while ($waited -lt $maxWait) {
        try {
            $health = & docker inspect --format "{{.State.Health.Status}}" financebuddy-postgres-1 2>&1
            if ($health -eq "healthy") {
                Write-Ok "PostgreSQL is healthy"
                break
            }
        } catch {}
        Start-Sleep -Seconds 2
        $waited += 2
    }
    if ($waited -ge $maxWait) {
        Write-Warn "PostgreSQL health check timed out  continuing anyway"
    }

    Write-Info "Waiting for Redis to be ready..."
    $waited = 0
    while ($waited -lt 30) {
        try {
            $health = & docker inspect --format "{{.State.Health.Status}}" financebuddy-redis-1 2>&1
            if ($health -eq "healthy") {
                Write-Ok "Redis is healthy"
                break
            }
        } catch {}
        Start-Sleep -Seconds 2
        $waited += 2
    }
    if ($waited -ge 30) {
        Write-Warn "Redis health check timed out  continuing anyway"
    }
} else {
    Write-Info "Skipping Docker (--SkipDocker)"
}

#  4. Python virtual environment 
Write-Step "Setting up Python virtual environment..."

if (-not (Test-Path $VENV)) {
    & $python -m venv $VENV
    Write-Ok "Created virtual environment at server/.venv"
} else {
    Write-Ok "Virtual environment already exists"
}

$venvPython = Join-Path (Join-Path $VENV "Scripts") "python.exe"
$venvPip = Join-Path (Join-Path $VENV "Scripts") "pip.exe"

# Configure pip to trust PyPI hosts (workaround for SSL cert issues)
$pipDir = Join-Path $VENV "pip.ini"
$pipContent = @(
    "[global]",
    "trusted-host = pypi.org",
    "               pypi.python.org",
    "               files.pythonhosted.org"
)
$pipContent | Set-Content $pipDir -Encoding ascii

# Also set per-user pip config as fallback
$userPipDir = Join-Path $env:APPDATA "pip"
if (-not (Test-Path $userPipDir)) {
    New-Item -ItemType Directory -Path $userPipDir -Force | Out-Null
}
$userPipIni = Join-Path $userPipDir "pip.ini"
if (-not (Test-Path $userPipIni)) {
    $userPipContent = @(
        "[global]",
        "trusted-host = pypi.org",
        "               pypi.python.org",
        "               files.pythonhosted.org"
    )
    $userPipContent | Set-Content $userPipIni -Encoding ascii
    Write-Info "Created user pip.ini with trusted hosts (SSL workaround)"
}

# Upgrade pip
Write-Info "Upgrading pip..."
& $venvPython -m pip install --upgrade pip --quiet 2>&1 | Out-Null
Write-Ok "pip upgraded"

#  5. Install Python dependencies 
Write-Step "Installing Python dependencies..."

Write-Info "Installing core + dev dependencies (this may take a few minutes)..."
& $venvPip install -e "$SERVER\.[dev]" --quiet 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Warn "First install attempt failed, retrying with verbose output..."
    & $venvPip install -e "$SERVER\.[dev]"
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Failed to install Python dependencies. Check the error above."
        exit 1
    }
}
Write-Ok "Python dependencies installed"

#  6. Database migrations 
Write-Step "Running database migrations..."

$alembic = Join-Path (Join-Path $VENV "Scripts") "alembic.exe"

if ($ResetDB) {
    Write-Warn "Resetting database (--ResetDB)..."
    & $venvPython -c "
import asyncio, asyncpg
async def reset():
    conn = await asyncpg.connect('postgresql://financebuddy:financebuddy@localhost:5432/financebuddy')
    await conn.execute('DROP SCHEMA public CASCADE; CREATE SCHEMA public;')
    await conn.execute('CREATE EXTENSION IF NOT EXISTS vector;')
    await conn.close()
asyncio.run(reset())
" 2>&1 | Out-Null
    Write-Ok "Database reset"
}

Push-Location $SERVER
try {
    & $alembic upgrade head
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Alembic migration failed"
        exit 1
    }
    Write-Ok "Migrations applied successfully"
} finally {
    Pop-Location
}

#  7. Seed demo data 
Write-Step "Seeding demo data..."

Push-Location $SERVER
try {
    & $venvPython -m app.seed
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "Seeding returned non-zero exit code (data may already exist)"
    } else {
        Write-Ok "Demo data seeded"
    }
} finally {
    Pop-Location
}

#  8. Install frontend dependencies 
if (-not $SkipFrontend) {
    Write-Step "Installing frontend dependencies..."

    Push-Location $WEB
    try {
        & npm install --silent 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            & npm install
            if ($LASTEXITCODE -ne 0) {
                Write-Err "npm install failed"
                exit 1
            }
        }
        Write-Ok "Frontend dependencies installed"
    } finally {
        Pop-Location
    }
}

#  9. Launch services 
Write-Host ""
Write-Host "" -ForegroundColor Green
Write-Host "              Setup Complete  Launching!             " -ForegroundColor Green
Write-Host "" -ForegroundColor Green
Write-Host ""
Write-Host "   Frontend:  http://localhost:5173" -ForegroundColor White
Write-Host "   API:       http://localhost:8000" -ForegroundColor White
Write-Host "   API Docs:  http://localhost:8000/docs" -ForegroundColor White
Write-Host "   Demo Login: demo@financebuddy.app / DemoPass123!" -ForegroundColor White
Write-Host ""
Write-Host "  Press Ctrl+C to stop all services" -ForegroundColor DarkGray
Write-Host ""

# Start backend API server as a background job
if (-not $SkipBackend) {
    $apiJob = Start-Job -Name "FinanceBuddy-API" -ScriptBlock {
        param($venvPython, $server)
        Set-Location $server
        & $venvPython -m uvicorn app.main:app --reload --port 8000 2>&1
    } -ArgumentList $venvPython, $SERVER
    Write-Ok "API server starting (background job)..."
}

# Start event worker as a background job
$workerJob = Start-Job -Name "FinanceBuddy-Worker" -ScriptBlock {
    param($venvPython, $server)
    Set-Location $server
    & $venvPython -m app.workers.event_consumer 2>&1
} -ArgumentList $venvPython, $SERVER
Write-Ok "Event worker starting (background job)..."

# Give the API a moment to start
Start-Sleep -Seconds 3

# Cleanup handler
$cleanup = {
    Write-Host "`n`nShutting down..." -ForegroundColor Yellow
    Get-Job -Name "FinanceBuddy-*" -ErrorAction SilentlyContinue | Stop-Job -PassThru | Remove-Job
    Write-Host "All services stopped." -ForegroundColor Green
}
Register-EngineEvent PowerShell.Exiting -Action $cleanup | Out-Null

if (-not $SkipFrontend) {
    # Run frontend in foreground (Ctrl+C stops everything)
    try {
        Push-Location $WEB
        & npm run dev
    } finally {
        Pop-Location
        & $cleanup
    }
} else {
    Write-Info "Frontend skipped (--SkipFrontend). API running at http://localhost:8000"
    Write-Info "Press Ctrl+C to stop..."
    try { while ($true) { Start-Sleep -Seconds 5 } }
    finally { & $cleanup }
}


