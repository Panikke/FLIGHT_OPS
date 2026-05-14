# dev.ps1 — start EGW OCC in local development mode
# Run from the repo root: .\dev.ps1
# Requires: Python 3.11+, Node 20+, yarn, MongoDB running locally

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"

function Write-Step($msg) { Write-Host "`n>> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "   [OK] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "   [!]  $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "   [X]  $msg" -ForegroundColor Red }

# ── 1. Python ──────────────────────────────────────────────────────────────────
Write-Step "Checking Python"
$py = $null
foreach ($cmd in @("python", "python3", "python3.11")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python 3\.(1[1-9]|[2-9]\d)") { $py = $cmd; break }
    } catch {}
}
if (-not $py) {
    Write-Err "Python 3.11+ not found. Install from https://www.python.org/downloads/ (tick 'Add to PATH')."
    exit 1
}
Write-Ok "$py $($( & $py --version 2>&1 ))"

# ── 2. Node / yarn ─────────────────────────────────────────────────────────────
Write-Step "Checking Node + yarn"
try {
    $nodeVer = & node --version 2>&1
    Write-Ok "node $nodeVer"
} catch {
    Write-Err "Node.js not found. Install from https://nodejs.org (LTS)."
    exit 1
}
try {
    $yarnVer = & yarn --version 2>&1
    Write-Ok "yarn $yarnVer"
} catch {
    Write-Warn "yarn not found — installing globally via npm..."
    & npm install -g yarn
}

# ── 3. MongoDB ─────────────────────────────────────────────────────────────────
Write-Step "Checking MongoDB"
$mongoRunning = $false
try {
    $result = & mongosh --quiet --eval "db.runCommand({ping:1}).ok" 2>&1
    if ($result -match "1") { $mongoRunning = $true }
} catch {}

if (-not $mongoRunning) {
    Write-Warn "mongosh ping failed. Trying to start MongoDB service..."
    try {
        Start-Service -Name "MongoDB" -ErrorAction Stop
        Start-Sleep 2
        Write-Ok "MongoDB service started."
        $mongoRunning = $true
    } catch {
        Write-Err @"
MongoDB is not running and could not be started automatically.

Options:
  A) Install MongoDB Community Edition:
     https://www.mongodb.com/try/download/community
     (tick 'Install MongoDB as a Service')

  B) Use MongoDB Atlas (free cloud tier):
     https://www.mongodb.com/cloud/atlas
     Then update MONGO_URL in backend\.env with your Atlas SRV string.

After installing, re-run this script.
"@
        exit 1
    }
}
Write-Ok "MongoDB reachable."

# ── 4. Backend .env ────────────────────────────────────────────────────────────
Write-Step "Checking backend/.env"
$envFile = Join-Path $backend ".env"
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $backend ".env.example") $envFile
    Write-Warn "Created backend\.env from example. Please set your EMERGENT_LLM_KEY:"
    Write-Warn "  Edit: $envFile"
    Write-Warn "  Get a key at: https://app.emergent.sh  (Profile → Universal Key)"
    Write-Warn "(The app runs without it — the AI Advisor will show a fallback message.)"
} else {
    $key = (Get-Content $envFile | Select-String "EMERGENT_LLM_KEY").ToString()
    if ($key -match "YOUR_KEY_HERE" -or $key -match '=""') {
        Write-Warn "EMERGENT_LLM_KEY not set in backend\.env — Advisor will use fallback."
    } else {
        Write-Ok "backend\.env looks good."
    }
}

# ── 5. Python venv + deps ──────────────────────────────────────────────────────
Write-Step "Setting up Python virtual environment"
$venv = Join-Path $backend ".venv"
if (-not (Test-Path $venv)) {
    Write-Warn "Creating .venv..."
    & $py -m venv $venv
}
$pip = Join-Path $venv "Scripts\pip.exe"
Write-Ok "venv ready."

Write-Step "Installing backend dependencies"
& $pip install --quiet --upgrade pip
& $pip install --quiet -r (Join-Path $backend "requirements.txt")
# emergentintegrations may need the extra index
try {
    & $pip install --quiet emergentintegrations --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/ 2>$null
} catch {}
Write-Ok "Backend deps installed."

# ── 6. Frontend deps ───────────────────────────────────────────────────────────
Write-Step "Installing frontend dependencies"
Push-Location $frontend
try {
    & yarn install --frozen-lockfile --silent
    Write-Ok "Frontend deps installed."
} finally {
    Pop-Location
}

# ── 7. Launch ──────────────────────────────────────────────────────────────────
Write-Step "Launching services"

$uvicorn = Join-Path $venv "Scripts\uvicorn.exe"

# Backend window
$backendCmd = "cd '$backend'; & '$uvicorn' server:app --host 127.0.0.1 --port 8001 --reload"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd `
    -WindowStyle Normal

Start-Sleep 2

# Frontend window
$frontendCmd = "cd '$frontend'; yarn start"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCmd `
    -WindowStyle Normal

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  EGW OCC is starting up!" -ForegroundColor Green
Write-Host ""
Write-Host "  Frontend : http://localhost:3000" -ForegroundColor White
Write-Host "  Backend  : http://localhost:8001/api/" -ForegroundColor White
Write-Host ""
Write-Host "  Two new terminal windows have opened." -ForegroundColor Yellow
Write-Host "  Wait ~10s for both to be ready, then" -ForegroundColor Yellow
Write-Host "  open http://localhost:3000 in your browser." -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
