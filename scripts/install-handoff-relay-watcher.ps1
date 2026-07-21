# Install the handoff-relay watcher as a Windows logon task so Cursor/Claude
# handoffs claim + execute automatically — no more "Pick up handoff {id}" loop.
#
# Prerequisites:
#   - ODYSSEUS_API_TOKEN in your user env (Settings → Integrations in Odysseus)
#   - Cursor Agent CLI authenticated (`agent login`) and on PATH
#   - Odysseus reachable at ODYSSEUS_URL (default http://127.0.0.1:7000)
#
# Usage (from repo root, PowerShell):
#   .\scripts\install-handoff-relay-watcher.ps1
#   .\scripts\install-handoff-relay-watcher.ps1 -Target claude
#   .\scripts\install-handoff-relay-watcher.ps1 -Uninstall

param(
    [ValidateSet("cursor", "claude")]
    [string]$Target = "cursor",
    [int]$IntervalSeconds = 60,
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$TaskName = "Odysseus-HandoffRelay-$Target"
$Root = Split-Path -Parent $PSScriptRoot
$Watcher = Join-Path $Root "scripts\handoff-relay-watcher.ps1"

if (-not (Test-Path $Watcher)) {
    throw "Watcher not found: $Watcher"
}

$startupDir = [Environment]::GetFolderPath("Startup")
$startupLink = Join-Path $startupDir "Odysseus-HandoffRelay-$Target.cmd"

if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    if (Test-Path $startupLink) { Remove-Item $startupLink -Force }
    $wrapperPath = Join-Path $Root "scripts\.handoff-relay-$Target.cmd"
    if (Test-Path $wrapperPath) { Remove-Item $wrapperPath -Force }
    Write-Host "Removed handoff-relay autostart for target=$Target"
    exit 0
}

$token = $env:ODYSSEUS_API_TOKEN
if (-not $token) {
    Write-Warning "ODYSSEUS_API_TOKEN is not set in this shell."
    Write-Warning "Set it permanently (User env) then re-run this installer, or the task will fail at logon."
}

$url = if ($env:ODYSSEUS_URL) { $env:ODYSSEUS_URL } else { "http://127.0.0.1:7000" }

# Wrap so the task can set env vars even when they are not in the machine profile.
$wrapper = Join-Path $Root "scripts\.handoff-relay-$Target.cmd"
$psArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$Watcher`" -Target $Target -RunAgent -IntervalSeconds $IntervalSeconds"
$cmdLines = @(
    "@echo off",
    "set ODYSSEUS_URL=$url",
    "if defined ODYSSEUS_API_TOKEN_USER set ODYSSEUS_API_TOKEN=%ODYSSEUS_API_TOKEN_USER%",
    "if not defined ODYSSEUS_API_TOKEN set ODYSSEUS_API_TOKEN=$token",
    "powershell.exe $psArgs"
)
Set-Content -Path $wrapper -Value ($cmdLines -join "`r`n") -Encoding ASCII

# Prefer the user Startup folder (no admin). Fall back to Task Scheduler.
if (Test-Path $startupDir) {
    Copy-Item -Path $wrapper -Destination $startupLink -Force
    Write-Host "Installed logon startup entry: $startupLink"
    Write-Host "  Starts at logon, polls every ${IntervalSeconds}s, runs agent CLI on queued handoffs."
    Write-Host "  Wrapper: $wrapper"
    Write-Host ""
    Write-Host "Start now (new window):"
    Write-Host "  Start-Process cmd.exe -ArgumentList '/c `"$wrapper`"'"
    Write-Host "Or run in this terminal:"
    Write-Host "  .\scripts\handoff-relay-watcher.ps1 -Target $Target -RunAgent"
    exit 0
}

# Fallback: Task Scheduler (may require elevation)
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$wrapper`"" -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Auto-claim and run Odysseus $Target handoffs via agent CLI" | Out-Null

Write-Host "Installed scheduled task: $TaskName"
Write-Host "Start now: Start-ScheduledTask -TaskName '$TaskName'"
