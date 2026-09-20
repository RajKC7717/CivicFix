<#
.SYNOPSIS
    Start NagarNetra (PS-18 CivicFix) - API + web app, in one command.
.DESCRIPTION
    First run sets everything up: virtualenv, dependencies, ward polygons,
    synthetic corpus, trained offline classifier and seeded demo database.
    Later runs just start the two servers.

    Everything works with no API key and no internet.
.EXAMPLE
    ./run.ps1              # set up if needed, then start both servers
    ./run.ps1 -Reseed      # rebuild the demo dataset first
    ./run.ps1 -SetupOnly   # prepare everything, do not start servers
#>
param(
    [switch]$Reseed,
    [switch]$SetupOnly
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$py = Join-Path $root '.venv\Scripts\python.exe'
# Marathi and Hindi text reaches the log handlers; a cp1252 console would crash them.
$env:PYTHONIOENCODING = 'utf-8'

function Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }

Step 'Checking Python virtualenv'
if (-not (Test-Path $py)) {
    Write-Host '    creating .venv (Python 3.11)'
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) { & py -3.11 -m venv (Join-Path $root '.venv') }
    else { & python -m venv (Join-Path $root '.venv') }
    & $py -m pip install --upgrade pip -q
}

Step 'Installing backend dependencies'
& $py -m pip install -q -r (Join-Path $root 'backend\requirements-dev.txt')
& $py -m pip install -q cryptography

if (-not (Test-Path (Join-Path $root '.env'))) {
    Step 'Creating .env from .env.example'
    Copy-Item (Join-Path $root '.env.example') (Join-Path $root '.env')
}

Step 'Preparing data'
if (-not (Test-Path (Join-Path $root 'data\wards.geojson'))) {
    & $py (Join-Path $root 'scripts\build_wards.py')
}
if (-not (Test-Path (Join-Path $root 'data\synthetic_complaints.csv'))) {
    & $py (Join-Path $root 'scripts\generate_synthetic.py')
}
if (-not (Test-Path (Join-Path $root 'backend\var\models\fallback_clf.joblib'))) {
    Write-Host '    training the offline classifier (about 20s)'
    & $py (Join-Path $root 'scripts\train_fallback.py') | Out-Null
}
if ($Reseed -or -not (Test-Path (Join-Path $root 'backend\var\nagarnetra.db'))) {
    Write-Host '    seeding the demo database'
    & $py (Join-Path $root 'scripts\seed_db.py') --reset
}

Step 'Installing frontend dependencies'
Push-Location (Join-Path $root 'frontend')
if (-not (Test-Path 'node_modules')) { npm install --no-audit --no-fund }
Pop-Location

if ($SetupOnly) { Step 'Setup complete'; exit 0 }

Step 'Starting NagarNetra'
Write-Host ''
Write-Host '  Citizen app      http://localhost:5173'         -ForegroundColor Green
Write-Host '  Officer console  http://localhost:5173/admin    (officer / officer)' -ForegroundColor Green
Write-Host '  API docs         http://127.0.0.1:8000/docs'    -ForegroundColor Green
Write-Host ''
Write-Host '  Ctrl+C stops the web app; the API window closes with it.' -ForegroundColor DarkGray
Write-Host ''

$api = Start-Process -FilePath $py `
    -ArgumentList '-m','uvicorn','app.main:app','--app-dir','backend','--host','127.0.0.1','--port','8000' `
    -WorkingDirectory $root -PassThru -NoNewWindow

try {
    Push-Location (Join-Path $root 'frontend')
    npm run dev
} finally {
    Pop-Location
    if ($api -and -not $api.HasExited) { Stop-Process -Id $api.Id -Force -ErrorAction SilentlyContinue }
}
