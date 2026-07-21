#Requires -Version 5.1
<#
  Install Docker MCP Gateway as a Windows logon startup entry so :8811 stays
  available for Odysseus in Docker (http://host.docker.internal:8811/sse).

  Usage (from repo root, PowerShell):
    .\scripts\install-docker-mcp-gateway.ps1
    .\scripts\install-docker-mcp-gateway.ps1 -Port 8811
    .\scripts\install-docker-mcp-gateway.ps1 -Uninstall

  Manual start (now):
    .\scripts\start-docker-mcp-gateway.ps1

  Health check (401 = alive / auth required):
    Invoke-WebRequest http://127.0.0.1:8811/sse -UseBasicParsing
#>
param(
    [int]$Port = 8811,
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Starter = Join-Path $Root "scripts\start-docker-mcp-gateway.ps1"
$TaskName = "Odysseus-DockerMcpGateway"
$startupName = "Odysseus-DockerMcpGateway.cmd"

if (-not (Test-Path $Starter)) {
    throw "Start script not found: $Starter"
}

$startupDir = [Environment]::GetFolderPath("Startup")
$startupLink = Join-Path $startupDir $startupName
$wrapper = Join-Path $Root "scripts\.docker-mcp-gateway.cmd"

if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    if (Test-Path $startupLink) { Remove-Item $startupLink -Force }
    if (Test-Path $wrapper) { Remove-Item $wrapper -Force }
    Write-Host "Removed Docker MCP Gateway autostart ($TaskName / Startup)."
    exit 0
}

$psArgs = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Starter`" -Port $Port"
$cmdLines = @(
    "@echo off",
    "cd /d `"$Root`"",
    "start `"`" /MIN powershell.exe $psArgs"
)
Set-Content -Path $wrapper -Value ($cmdLines -join "`r`n") -Encoding ASCII

if (Test-Path $startupDir) {
    Copy-Item -Path $wrapper -Destination $startupLink -Force
    Write-Host "Installed logon startup entry: $startupLink"
    Write-Host "  Starts Docker MCP Gateway on :$Port at logon (hidden)."
    Write-Host "  Wrapper: $wrapper"
    Write-Host ""
    Write-Host "Start now (detached):"
    Write-Host "  Start-Process powershell.exe -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File `"$Starter`" -Port $Port' -WindowStyle Hidden"
    Write-Host "Health (401 = alive):"
    Write-Host "  try { Invoke-WebRequest http://127.0.0.1:$Port/sse -UseBasicParsing } catch { `$_.Exception.Response.StatusCode.value__ }"
    exit 0
}

$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$wrapper`"" -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Write-Host "Installed scheduled task: $TaskName (AtLogOn)"
