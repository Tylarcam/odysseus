# start-screenpipe.ps1 - launch Screenpipe for the archivist stack (screen capture + optional audio).
#
# Default: screen-only (--disable-audio) so Clicky and Odysseus voice can use the mic.
# Interactive: prompts on each fresh start unless -NonInteractive or Screenpipe is already healthy.
#
# Usage:
#   cd C:\Users\tylar\code\odysseus
#   .\deploy\scripts\start-screenpipe.ps1
#   .\deploy\scripts\start-screenpipe.ps1 -NonInteractive
#   .\deploy\scripts\start-screenpipe.ps1 -EnableAudio

param(
    [int]$Port = 3030,
    [string]$OcrEngine = "windows-native",
    [switch]$NonInteractive,
    [switch]$DisableAudio,
    [switch]$EnableAudio,
    [int]$WaitSeconds = 15
)

$ErrorActionPreference = "Stop"

function Import-MemoryStackEnv {
    $root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
    $envFile = Join-Path $root "memory_stack.env"
    if (-not (Test-Path $envFile)) { return $root }
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
        $parts = $_ -split '=', 2
        Set-Item -Path "env:$($parts[0].Trim())" -Value $parts[1].Trim()
    }
    return $root
}

function Test-TruthyEnv {
    param([string]$Value)
    switch -Regex ($Value) {
        '^(1|true|yes|on)$' { return $true }
        default { return $false }
    }
}

function Resolve-ScreenpipeAudioArgs {
    if ($DisableAudio) {
        return @("--disable-audio"), $false
    }
    if ($EnableAudio) {
        return @(), $true
    }

    if ($NonInteractive) {
        if (Test-TruthyEnv $env:SCREENPIPE_DISABLE_AUDIO) {
            return @("--disable-audio"), $false
        }
        if (Test-TruthyEnv $env:SCREENPIPE_ENABLE_AUDIO) {
            return @(), $true
        }
        return @("--disable-audio"), $false
    }

    Write-Host ""
    Write-Host "Screenpipe microphone capture" -ForegroundColor Cyan
    Write-Host "  Screen-only is recommended - mic audio can block Clicky and Odysseus voice." -ForegroundColor Gray
    Write-Host "  Press Enter for screen only, or type y to also record the microphone." -ForegroundColor Gray
    $answer = Read-Host "Record microphone with Screenpipe? [y/N]"
    if ($answer -match '^(y|yes)$') {
        Write-Host "Starting with microphone capture enabled." -ForegroundColor Yellow
        return @(), $true
    }
    Write-Host "Starting screen-only (no microphone)." -ForegroundColor Green
    return @("--disable-audio"), $false
}

$Root = Import-MemoryStackEnv
$screenpipeApi = if ($env:SCREENPIPE_API_URL) { $env:SCREENPIPE_API_URL.TrimEnd('/') } else { "http://localhost:$Port" }
$screenpipeRepo = if ($env:SCREENPIPE_REPO_DIR) { $env:SCREENPIPE_REPO_DIR } else { "C:\Users\tylar\code\screen-pipe" }
$screenpipeExe = Join-Path $screenpipeRepo "target\release\screenpipe.exe"

try {
    $health = Invoke-RestMethod -Uri "$screenpipeApi/health" -TimeoutSec 3
    if ($health.status) {
        $audioStatus = if ($health.audio_status) { $health.audio_status } else { "unknown" }
        Write-Host "Screenpipe already running on :$Port (audio_status: $audioStatus)" -ForegroundColor Yellow
        if ($audioStatus -ne "No data" -and $audioStatus -ne "Loading" -and $audioStatus -ne "Disabled") {
            Write-Warning "Screenpipe may be using the microphone. Restart with --disable-audio if voice apps fail."
        }
        return
    }
} catch {}

if (-not (Test-Path $screenpipeExe)) {
    Write-Warning "Screenpipe binary not found: $screenpipeExe"
    Write-Warning "Build: cd $screenpipeRepo; cargo build --release"
    exit 1
}

$audioArgs, $audioEnabled = Resolve-ScreenpipeAudioArgs
$launchArgs = @("--port", "$Port", "--ocr-engine", $OcrEngine) + $audioArgs

Write-Host "Starting Screenpipe: $screenpipeExe $($launchArgs -join ' ')" -ForegroundColor Green
Start-Process -FilePath $screenpipeExe -ArgumentList $launchArgs -WorkingDirectory (Split-Path $screenpipeExe -Parent)

if ($WaitSeconds -gt 0) {
    Write-Host ('Waiting for Screenpipe to capture ({0}s)...' -f $WaitSeconds) -ForegroundColor Gray
    Start-Sleep -Seconds $WaitSeconds
}

try {
    $health = Invoke-RestMethod -Uri "$screenpipeApi/health" -TimeoutSec 5
    $audioStatus = if ($health.audio_status) { $health.audio_status } else { "unknown" }
    $mode = if ($audioEnabled) { "screen + microphone" } else { "screen only" }
    Write-Host ('Screenpipe healthy on :{0} ({1}, audio_status: {2})' -f $Port, $mode, $audioStatus) -ForegroundColor Green
} catch {
    Write-Warning "Screenpipe started but health check on :$Port did not respond yet."
}
