# Probe model endpoints inside the Odysseus Docker container (uses decrypted API keys).
# Usage: .\scripts\test-endpoints-docker.ps1

$ErrorActionPreference = "Stop"
$container = "odysseus-odysseus-1"

if (-not (docker ps -q -f "name=$container")) {
    Write-Host "Container $container is not running. Start with: docker compose up -d odysseus"
    exit 1
}

docker exec -w /app -e PYTHONPATH=/app $container python scripts/probe_endpoints_incontainer.py
exit $LASTEXITCODE
