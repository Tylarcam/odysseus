# start-clicky.ps1 - launch Clicky (Windows) as the Odysseus cursor overlay.
# 1. Loads memory_stack.env
# 2. Warns if the unified memory API (:40001) is down
# 3. Starts the Clicky worker adapter (tools/clicky_worker_api.py, :40002) if needed
# 4. Runs the clicky-windows WPF app pointed at the adapter (dotnet run)
#
# Usage: cd C:\Users\tylar\code\odysseus; .\deploy\scripts\start-clicky.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location $Root
$env:PYTHONPATH = $Root

function Import-MemoryStackEnv {
    if (-not (Test-Path "memory_stack.env")) { return }
    Get-Content "memory_stack.env" | ForEach-Object {
        if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
        $parts = $_ -split '=', 2
        Set-Item -Path "env:$($parts[0].Trim())" -Value $parts[1].Trim()
    }
}

Import-MemoryStackEnv

function Test-ClickyWorkerHasChatMode {
    param([string]$Port)
    try {
        $health = Invoke-RestMethod -Uri "http://localhost:$Port/health" -TimeoutSec 3
        # endpoint = single-shot model relay; agent = Odysseus agent loop (spoken ops)
        return ($health.chat_mode -in @("endpoint", "agent", "memory")) -and `
               (-not [string]::IsNullOrWhiteSpace($health.chat_model))
    } catch {
        return $false
    }
}

function Test-ClickyWorkerReady {
    param([string]$Port)
    return (Test-ClickyWorkerHasMicRoutes -Port $Port) -and (Test-ClickyWorkerHasChatMode -Port $Port)
}

function Test-ClickyWorkerHasMicRoutes {
    param([string]$Port)
    try {
        $claim = Invoke-RestMethod -Method POST -Uri "http://localhost:$Port/mic/claim" `
            -ContentType "application/json" `
            -Body '{"holder":"clicky","mode":"ptt","ttl_sec":5}' -TimeoutSec 3
        if ($claim.ok -and $claim.token) {
            Invoke-RestMethod -Method POST -Uri "http://localhost:$Port/mic/release" `
                -ContentType "application/json" `
                -Body (@{ holder = "clicky"; token = $claim.token } | ConvertTo-Json) -TimeoutSec 3 | Out-Null
        }
        return $true
    } catch {
        $code = $null
        if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
        # 409 = route exists but mic busy
        if ($code -eq 409) { return $true }
        return $false
    }
}

function Stop-ClickyWorkerOnPort {
    param([string]$Port)
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
}

Write-Host "`n=== Clicky overlay boot ===" -ForegroundColor Cyan
Write-Host "Repo: $Root"

# Prefer the repo venv python when available
$PythonExe = Join-Path $Root "venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) { $PythonExe = "python" }

# 1) Check unified memory API on :40001 (warn only - Clicky still boots)
$apiPort = if ($env:UNIFIED_MEMORY_API_PORT) { $env:UNIFIED_MEMORY_API_PORT } else { "40001" }
$apiHealthy = $false
try {
    $health = Invoke-RestMethod -Uri "http://localhost:$apiPort/health" -TimeoutSec 3
    if ($health.status -eq "ok") { $apiHealthy = $true }
} catch {}

if ($apiHealthy) {
    Write-Host "Unified memory API healthy on :$apiPort" -ForegroundColor Green
} else {
    Write-Warning "Unified memory API not responding on :$apiPort."
    Write-Warning "Start it first: .\deploy\scripts\start-archivist.ps1 (Clicky answers will be memory-less until it is up)."
}

# 2) Start the Clicky worker adapter on :40002 if not already listening (or stale)
$workerPort = if ($env:CLICKY_WORKER_PORT) { $env:CLICKY_WORKER_PORT } else { "40002" }
$workerListening = Get-NetTCPConnection -LocalPort $workerPort -State Listen -ErrorAction SilentlyContinue
$workerReady = $false

if ($workerListening) {
    if (Test-ClickyWorkerReady -Port $workerPort) {
        Write-Host "Clicky worker adapter already listening on :$workerPort" -ForegroundColor Yellow
        $workerReady = $true
    } else {
        Write-Warning "Stale Clicky worker on :$workerPort (missing /mic routes or chat mode/model). Restarting..."
        Stop-ClickyWorkerOnPort -Port $workerPort
        Start-Sleep -Seconds 1
        $workerListening = $null
    }
}

if (-not $workerReady) {
    Write-Host "Starting Clicky worker adapter on :$workerPort (background)..." -ForegroundColor Green
    Start-Process -FilePath $PythonExe -ArgumentList @("-m", "tools.clicky_worker_api") -WorkingDirectory $Root -WindowStyle Hidden

    $adapterHealthy = $false
    foreach ($attempt in 1..10) {
        Start-Sleep -Seconds 1
        try {
            $adapterHealth = Invoke-RestMethod -Uri "http://localhost:$workerPort/health" -TimeoutSec 2
            if ($adapterHealth.status -eq "ok" -and (Test-ClickyWorkerReady -Port $workerPort)) {
                $adapterHealthy = $true
                break
            }
        } catch {}
    }
    if ($adapterHealthy) {
        Write-Host "Adapter healthy on :$workerPort (local-first transcribe)" -ForegroundColor Green
    } else {
        throw "Clicky worker adapter did not become healthy on :$workerPort. Run manually: $PythonExe -m tools.clicky_worker_api"
    }
}

# 3) Launch the Clicky WPF app (foreground - it prompts for model/voice, press Enter twice for defaults)
$clickyRoot = if ($env:CLICKY_WINDOWS_DIR) { $env:CLICKY_WINDOWS_DIR } else { "C:/Users/tylar/code/clicky-windows" }
$clickyProject = Join-Path $clickyRoot "clicky-windows"
if (-not (Test-Path (Join-Path $clickyProject "ClickyWindows.csproj"))) {
    throw "ClickyWindows.csproj not found under $clickyProject. Check CLICKY_WINDOWS_DIR in memory_stack.env."
}

Write-Host "Launching Clicky from $clickyProject" -ForegroundColor Green
Write-Host "Chat routes through Odysseus ModelEndpoints (CLICKY_CHAT_* in memory_stack.env, else Default Model)." -ForegroundColor Gray
Write-Host "Mode=$($env:CLICKY_CHAT_MODE) model=$($env:CLICKY_CHAT_MODEL) endpoint=$($env:CLICKY_CHAT_ENDPOINT_ID)" -ForegroundColor Gray
Write-Host "Hold Ctrl+Alt to talk once the tray icon appears." -ForegroundColor Gray
Write-Host ""

Set-Location $clickyProject
dotnet build
if ($LASTEXITCODE -ne 0) { throw "dotnet build failed with exit code $LASTEXITCODE" }
dotnet run --no-build
if ($LASTEXITCODE -ne 0) {
    $isElevationError = $false
    if ($Error.Count -gt 0) {
        $isElevationError = ($Error[0].Exception.Message -match "requires elevation")
    }
    if ($isElevationError) {
        Write-Host ""
        Write-Warning "Clicky requires administrator privileges (app.manifest has requireAdministrator)."
        Write-Warning "Either run this terminal as Administrator, or set app.manifest to level=`"asInvoker`" and rebuild."
        Write-Warning "WH_KEYBOARD_LL global hotkeys work without elevation; asInvoker is the recommended setting."
    }
    throw "dotnet run failed with exit code $LASTEXITCODE"
}
