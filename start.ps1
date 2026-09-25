<#
.SYNOPSIS
  Start MITRA with one command: API, dashboard and (if a token is set) the Telegram bot.

.DESCRIPTION
  Installs missing dependencies, seeds demo data on first run, starts everything,
  opens the dashboard, and stops everything on Ctrl+C. Logs go to .\logs\.
  Usually run through start.cmd, which bypasses the PowerShell script policy.

.EXAMPLE
  .\start.cmd                 # normal demo start
.EXAMPLE
  .\start.cmd -Reseed         # fresh demo data (wipes lots logged during rehearsal)
.EXAMPLE
  .\start.cmd -Smoke          # start, check every part, print PASS/FAIL, stop
#>
param(
    [int]$ApiPort = 8000,
    [int]$WebPort = 5173,
    [switch]$Reseed,
    [switch]$NoBot,
    [switch]$NoBrowser,
    [switch]$Smoke
)

$ErrorActionPreference = 'Continue'   # native tools write progress to stderr; we check exit codes
$Root = $PSScriptRoot
$Backend = Join-Path $Root 'backend'
$Frontend = Join-Path $Root 'frontend'
$Logs = Join-Path $Root 'logs'
New-Item -ItemType Directory -Force $Logs | Out-Null

function Say([string]$Text, [string]$Color = 'Gray') { Write-Host $Text -ForegroundColor $Color }
function Fail([string]$Text) { Say "ERROR: $Text" Red; exit 1 }

function Require([string]$Cmd, [string]$Hint) {
    if (-not (Get-Command $Cmd -ErrorAction SilentlyContinue)) { Fail "'$Cmd' not found. $Hint" }
}

function Test-PortBusy([int]$Port) {
    [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Wait-Http([string]$Url, [int]$Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest $Url -UseBasicParsing -TimeoutSec 3
            if ($r.StatusCode -eq 200) { return $true }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    return $false
}

function Start-Part([string]$Name, [string]$Exe, [string[]]$ArgList, [string]$Dir) {
    $out = Join-Path $Logs "$Name.log"
    $err = Join-Path $Logs "$Name.err.log"
    $p = Start-Process -FilePath $Exe -ArgumentList $ArgList -WorkingDirectory $Dir `
        -RedirectStandardOutput $out -RedirectStandardError $err -PassThru -WindowStyle Hidden
    return [pscustomobject]@{ Name = $Name; Process = $p; Log = $err }
}

function Stop-Parts($Parts) {
    foreach ($part in $Parts) {
        if ($part -and -not $part.Process.HasExited) {
            & taskkill.exe /PID $part.Process.Id /T /F 2>$null | Out-Null
        }
    }
}

function Test-TokenSet {
    if ($env:TELEGRAM_TOKEN) { return $true }
    $envFile = Join-Path $Backend '.env'
    return (Test-Path $envFile) -and (Select-String -Path $envFile -Pattern '^\s*TELEGRAM_TOKEN\s*=\s*\S' -Quiet)
}

# ---------------------------------------------------------------- checks
Say ''
Say 'MITRA - Material Intelligence, Traceability & Recovery Architecture' Cyan
Require 'uv' 'Install it: powershell -c "irm https://astral.sh/uv/install.ps1 | iex"  (then open a new terminal)'
Require 'pnpm' 'Install Node.js 18+ from https://nodejs.org, then run: npm install -g pnpm'
foreach ($port in @($ApiPort, $WebPort)) {
    if (Test-PortBusy $port) {
        Fail "Port $port is already in use. Is MITRA already running? Close it, or pick other ports: .\start.cmd -ApiPort 8001 -WebPort 5174"
    }
}

# ---------------------------------------------------------------- setup
Say '[1/4] Backend: installing Python packages (first run can take a few minutes)...'
Push-Location $Backend
& uv sync --quiet
if ($LASTEXITCODE -ne 0) { Pop-Location; Fail 'uv sync failed (see output above).' }
$db = Join-Path $Backend 'data\mitra.db'
if ($Reseed -or -not (Test-Path $db)) {
    Say '      Seeding demo data (40 collectors, 400 lots)...'
    & uv run python -m app.seed | Out-Host
    if ($LASTEXITCODE -ne 0) { Pop-Location; Fail 'Seeding the database failed.' }
}
Pop-Location

Say '[2/4] Dashboard: installing packages...'
if (-not (Test-Path (Join-Path $Frontend 'node_modules'))) {
    Push-Location $Frontend
    & pnpm install --silent
    $code = $LASTEXITCODE
    Pop-Location
    if ($code -ne 0) { Fail 'pnpm install failed (see output above).' }
}

# ---------------------------------------------------------------- start
$env:MITRA_API_URL = "http://127.0.0.1:$ApiPort"   # used by the dashboard proxy and the bot
$parts = @()
$exitCode = 0
try {
    Say "[3/4] Starting API on port $ApiPort..."
    $parts += Start-Part 'api' 'uv' @('run', 'uvicorn', 'app.main:app', '--port', "$ApiPort") $Backend
    if (-not (Wait-Http "http://127.0.0.1:$ApiPort/health" 60)) { throw "API did not start. See $Logs\api.err.log" }

    Say "      Starting dashboard on port $WebPort..."
    $parts += Start-Part 'dashboard' 'cmd.exe' @('/c', "pnpm dev --port $WebPort --strictPort") $Frontend
    if (-not (Wait-Http "http://localhost:$WebPort/" 60)) { throw "Dashboard did not start. See $Logs\dashboard.log" }

    $botStatus = 'skipped: no TELEGRAM_TOKEN in backend\.env (offline demo: see README)'
    if ($NoBot -or $Smoke) {
        $botStatus = 'not started (-NoBot)'
    } elseif (Test-TokenSet) {
        Say '[4/4] Starting Telegram bot...'
        $parts += Start-Part 'bot' 'uv' @('run', 'python', '-m', 'app.bot.telegram_bot') $Backend
        $botStatus = "running (log: logs\bot.err.log)"
    } else {
        Say '[4/4] Telegram bot skipped (no token).' DarkYellow
    }

    if ($Smoke) {
        Say ''
        Say 'Smoke test' Cyan
        $checks = [ordered]@{
            'API health'              = "http://127.0.0.1:$ApiPort/health"
            'Collectors (via proxy)'  = "http://localhost:$WebPort/api/collectors"
            'Ministry summary'        = "http://localhost:$WebPort/api/ministry/summary"
            'Material flow (Sankey)'  = "http://localhost:$WebPort/api/flow/sankey"
            'Passport #1'             = "http://localhost:$WebPort/api/passport/1"
            'EPR report PDF'          = "http://localhost:$WebPort/api/epr/report?format=pdf"
            'Photo classifier status' = "http://localhost:$WebPort/api/classify/status"
            'Dashboard page'          = "http://localhost:$WebPort/"
        }
        foreach ($name in $checks.Keys) {
            try {
                $r = Invoke-WebRequest $checks[$name] -UseBasicParsing -TimeoutSec 60
                $ok = $r.StatusCode -eq 200
                $detail = "HTTP $($r.StatusCode), $($r.RawContentLength) bytes"
            } catch { $ok = $false; $detail = $_.Exception.Message }
            if (-not $ok) { $exitCode = 1 }
            Say ("  {0,-5} {1,-25} {2}" -f $(if ($ok) { 'PASS' } else { 'FAIL' }), $name, $detail) $(if ($ok) { 'Green' } else { 'Red' })
        }
        $cv = Invoke-RestMethod "http://127.0.0.1:$ApiPort/api/classify/status"
        Say "  info  Photo classifier: $($cv.reason)"
        Say $(if ($exitCode -eq 0) { 'SMOKE TEST PASSED' } else { 'SMOKE TEST FAILED' }) $(if ($exitCode -eq 0) { 'Green' } else { 'Red' })
    } else {

    Say ''
    Say 'MITRA is running' Green
    Say "  Dashboard   http://localhost:$WebPort"
    Say "  API docs    http://localhost:$ApiPort/docs"
    Say "  Telegram    $botStatus"
    Say "  Logs        $Logs"
    Say 'Press Ctrl+C to stop everything.' Cyan
    if (-not $NoBrowser) { Start-Process "http://localhost:$WebPort/#map" }

    while ($true) {
        foreach ($part in $parts) {
            if ($part.Process.HasExited) {
                Say "`n$($part.Name) stopped unexpectedly. Last lines of $($part.Log):" Red
                Get-Content $part.Log -Tail 15 -ErrorAction SilentlyContinue | Out-Host
                throw "$($part.Name) stopped"
            }
        }
        Start-Sleep -Seconds 1
    }
    }  # end of normal (non-smoke) run
} catch {
    Say "ERROR: $($_.Exception.Message)" Red
    $exitCode = 1
} finally {
    Say 'Stopping MITRA...' DarkGray
    Stop-Parts $parts
}
exit $exitCode
