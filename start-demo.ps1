<#
.SYNOPSIS
    FinanceBuddy DEMO - starts the demo stack with a seeded demo account.
.DESCRIPTION
    Runs docker-compose.demo.yml: its own Postgres (financebuddy_demo), Redis, API and web.
    Nothing here touches the production database. Sign in with
    demo@financebuddy.app / DemoPass123!
.EXAMPLE
    .\start-demo.ps1          # build + start (demo data is seeded on first start)
    .\start-demo.ps1 -Reset   # wipe the demo database and start fresh
    .\start-demo.ps1 -Down    # stop the demo stack (data kept)
#>
[CmdletBinding()]
param([switch]$Reset, [switch]$Down)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$compose = @("compose", "-f", "docker-compose.demo.yml", "--env-file", ".env.demo")

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Docker is required: install Docker Desktop." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path ".env.demo")) {
    Copy-Item ".env.demo.example" ".env.demo"
    Write-Host "Created .env.demo from .env.demo.example" -ForegroundColor Green
}

if ($Down) {
    & docker @compose down
    exit $LASTEXITCODE
}
if ($Reset) {
    Write-Host "Wiping the DEMO database volume (production is untouched)..." -ForegroundColor Yellow
    & docker @compose down -v
}

Write-Host "Building and starting the DEMO stack..." -ForegroundColor Cyan
& docker @compose up -d --build
if ($LASTEXITCODE -ne 0) { Write-Host "docker compose failed." -ForegroundColor Red; exit 1 }

Write-Host "Waiting for the API (migrations + demo seed run on start)..." -ForegroundColor Gray
$ready = $false
for ($i = 0; $i -lt 90 -and -not $ready; $i++) {
    try {
        $ready = (Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 "http://localhost:8000/api/v1/health").StatusCode -eq 200
    } catch { Start-Sleep -Seconds 2 }
}
if (-not $ready) {
    Write-Host "API did not become healthy. Logs: docker compose -f docker-compose.demo.yml logs api" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "  FinanceBuddy DEMO is running" -ForegroundColor Green
Write-Host "  App:        http://localhost:5173"
Write-Host "  API docs:   http://localhost:8000/docs"
Write-Host "  Demo login: demo@financebuddy.app / DemoPass123!"
Write-Host "  Stop:       .\start-demo.ps1 -Down    Reset data: .\start-demo.ps1 -Reset" -ForegroundColor Gray
