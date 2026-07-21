#Requires -Version 5.1
<#
  Start the Docker MCP Gateway for Odysseus (SSE on port 8811).

  Odysseus running in Docker connects to the gateway at:
    http://host.docker.internal:8811/sse

  Usage:
    powershell -ExecutionPolicy Bypass -File .\scripts\start-docker-mcp-gateway.ps1
    powershell -ExecutionPolicy Bypass -File .\scripts\start-docker-mcp-gateway.ps1 -Port 8811

  Keep-alive (install logon Startup entry):
    powershell -ExecutionPolicy Bypass -File .\scripts\install-docker-mcp-gateway.ps1

  Health check (401 = alive / auth required):
    Invoke-WebRequest http://127.0.0.1:8811/sse -UseBasicParsing
#>
param(
    [int]$Port = 8811
)

$ErrorActionPreference = "Stop"

function Write-Step($msg) { Write-Host ("==> " + $msg) -ForegroundColor Cyan }
function Fail($msg) {
    Write-Host ("ERROR: " + $msg) -ForegroundColor Red
    exit 1
}

$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) { Fail "docker not found on PATH. Install Docker Desktop first." }

Write-Step "Checking Docker MCP CLI"
& docker mcp gateway run --help *> $null
if ($LASTEXITCODE -ne 0) {
    Fail "docker mcp is unavailable. Enable Docker Desktop MCP Toolkit, then retry."
}

Write-Step "Checking whether port $Port is already in use"
$existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Port $Port is already listening - gateway may already be running."
    Write-Host "Gateway URL: http://localhost:${Port}/sse"
    exit 0
}

$mcpDir = Join-Path $env:USERPROFILE ".docker\mcp"
$tokenFile = Join-Path $mcpDir "odysseus-gateway-token.txt"
if (-not (Test-Path $mcpDir)) {
    New-Item -ItemType Directory -Path $mcpDir | Out-Null
}

if (Test-Path $tokenFile) {
    $token = (Get-Content $tokenFile -Raw).Trim()
} else {
    Write-Step "Generating gateway auth token"
    $token = -join ((48..57) + (97..122) | Get-Random -Count 32 | ForEach-Object { [char]$_ })
    Set-Content -Path $tokenFile -Value $token -NoNewline
    Write-Host "Saved token to $tokenFile"
    Write-Host "Add this MCP server in Odysseus if needed:"
    Write-Host "  URL:  http://host.docker.internal:${Port}/sse"
    Write-Host "  Env:  {`"Authorization`": `"Bearer $token`"}"
}

$env:MCP_GATEWAY_AUTH_TOKEN = $token

Write-Step "Starting Docker MCP Gateway (SSE on port $Port)"
Write-Host "Press Ctrl+C to stop."
Write-Host "Gateway URL: http://localhost:${Port}/sse"
Write-Host ""

& docker mcp gateway run --port $Port --transport sse
