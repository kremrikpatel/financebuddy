<#
.SYNOPSIS
    FinanceBuddy PRODUCTION - starts the live stack (no demo data).
.DESCRIPTION
    Runs docker-compose.prod.yml with .env.production: its own Postgres, Redis (password
    protected, not published on host ports), migrations, API, event worker and web.
    First run creates .env.production with freshly generated secrets, then stops so you can
    fill in the CHANGE_ME values (public URL, CORS origins, provider keys).
.EXAMPLE
    .\start-prod.ps1          # validate config, build, migrate, start
    .\start-prod.ps1 -Down    # stop the production stack (data kept)
#>
[CmdletBinding()]
param([switch]$Down)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$envFile = ".env.production"
$compose = @("compose", "-f", "docker-compose.prod.yml", "--env-file", $envFile)

function New-Secret {
    $bytes = New-Object byte[] 32
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    -join ($bytes | ForEach-Object { $_.ToString("x2") })
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Docker is required." -ForegroundColor Red
    exit 1
}

if ($Down) {
    & docker @compose down
    exit $LASTEXITCODE
}

# First run: create the env file with generated secrets, then stop for the manual values.
if (-not (Test-Path $envFile)) {
    $lines = Get-Content ".env.production.example" | ForEach-Object {
        if ($_ -match '^([A-Z_]+)=GENERATE_ME$') { "$($Matches[1])=$(New-Secret)" } else { $_ }
    }
    [IO.File]::WriteAllLines((Join-Path $PSScriptRoot $envFile), [string[]]$lines)  # UTF-8 without BOM
    Write-Host "Created $envFile with generated SECRET_KEY, DATA_ENCRYPTION_KEY, POSTGRES_PASSWORD, REDIS_PASSWORD." -ForegroundColor Green
    Write-Host "BACK THIS FILE UP. Losing DATA_ENCRYPTION_KEY makes encrypted user data unrecoverable." -ForegroundColor Yellow
    Write-Host "Now edit $envFile, replace every CHANGE_ME (PUBLIC_API_URL, CORS_ORIGINS), add provider keys, and re-run." -ForegroundColor Yellow
    exit 1
}

# Refuse to start on placeholders or on values copied from the demo/dev setup.
$content = Get-Content $envFile
$problems = @($content | Where-Object { $_ -match '^[A-Z_]+=(CHANGE_ME|GENERATE_ME)\s*$' } | ForEach-Object { ($_ -split '=')[0] })
$devValues = @("00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff", "financebuddy_demo", "change-me")
foreach ($line in $content) {
    foreach ($dev in $devValues) {
        if ($line -match '^(SECRET_KEY|DATA_ENCRYPTION_KEY|POSTGRES_PASSWORD|REDIS_PASSWORD)=' -and $line.Contains($dev)) {
            $problems += ($line -split '=')[0]
        }
    }
}
if ($problems.Count -gt 0) {
    Write-Host "Fix these in ${envFile} before starting production: $($problems -join ', ')" -ForegroundColor Red
    exit 1
}

Write-Host "Building and starting the PRODUCTION stack..." -ForegroundColor Cyan
& docker @compose up -d --build
if ($LASTEXITCODE -ne 0) {
    Write-Host "Start failed. Check: docker compose -f docker-compose.prod.yml --env-file $envFile logs migrate api" -ForegroundColor Red
    exit 1
}

$apiPort = (($content | Where-Object { $_ -match '^API_PORT=' }) -split '=')[1]
if (-not $apiPort) { $apiPort = "8000" }
$ready = $false
for ($i = 0; $i -lt 90 -and -not $ready; $i++) {
    try {
        $ready = (Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 "http://localhost:$apiPort/api/v1/health").StatusCode -eq 200
    } catch { Start-Sleep -Seconds 2 }
}
if (-not $ready) {
    Write-Host "API did not become healthy. Logs: docker compose -f docker-compose.prod.yml --env-file $envFile logs api" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "  FinanceBuddy PRODUCTION is running (API on port $apiPort)" -ForegroundColor Green
Write-Host "  No demo account exists: the first person to sign up creates the first real account."
Write-Host "  Serve it over HTTPS via a reverse proxy; API docs are disabled in production."
Write-Host "  Stop: .\start-prod.ps1 -Down" -ForegroundColor Gray
