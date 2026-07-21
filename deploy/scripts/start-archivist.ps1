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

function Invoke-ArchivistPython {
    param([string]$Module, [string[]]$Args = @())
    & python -m $Module @Args
    if ($LASTEXITCODE -ne 0) {
        throw "python -m $Module failed with exit code $LASTEXITCODE"
    }
}

function Resolve-PixelragPython {
    if ($env:PIXELRAG_PYTHON -and (Test-Path $env:PIXELRAG_PYTHON)) {
        return $env:PIXELRAG_PYTHON
    }
    $default312 = "C:\Users\tylar\AppData\Local\Programs\Python\Python312\python.exe"
    if (Test-Path $default312) {
        return $default312
    }
    $pixelragCmd = Get-Command pixelrag -ErrorAction SilentlyContinue
    if ($pixelragCmd) {
        $scriptsDir = Split-Path $pixelragCmd.Source -Parent
        $candidates = @(
            (Join-Path $scriptsDir "python.exe"),
            (Join-Path (Split-Path $scriptsDir -Parent) "python.exe")
        )
        foreach ($candidate in $candidates) {
            if (Test-Path $candidate) { return $candidate }
        }
    }
    throw "Could not resolve Python for PixelRAG serve. Set PIXELRAG_PYTHON in memory_stack.env."
}

Import-MemoryStackEnv

Write-Host "`n=== archivist.ai boot ===" -ForegroundColor Cyan
Write-Host "Repo: $Root"

# 1) Screenpipe capture (interactive mic prompt on fresh start; default screen-only)
& (Join-Path $PSScriptRoot "start-screenpipe.ps1")

# 2) Export + tiles + notes index
Write-Host "Exporting Screenpipe -> archivist dirs..." -ForegroundColor Green
Invoke-ArchivistPython "tools.export_screenpipe"
Invoke-ArchivistPython "tools.build_tiles"
python -c "from tools.mempalace_search import build_notes_index; build_notes_index()"
if ($LASTEXITCODE -ne 0) { throw "build_notes_index failed" }

# 3) PixelRAG index + serve (background) - skip build when no tile dirs yet
$tilesDir = if ($env:PIXELRAG_TILES_DIR) { $env:PIXELRAG_TILES_DIR } else { "./my_index/tiles" }
$tileArticles = @(Get-ChildItem -Path $tilesDir -Filter "*.png.tiles" -Directory -ErrorAction SilentlyContinue)

if (Get-Command pixelrag -ErrorAction SilentlyContinue) {
    $indexDir = if ($env:PIXELRAG_INDEX_DIR) { $env:PIXELRAG_INDEX_DIR } else { "./my_index" }
    $indexFaiss = Join-Path $indexDir "index.faiss"

    if ($tileArticles.Count -eq 0) {
        Write-Warning "No PixelRAG tile directories yet - skipping index build."
        Write-Warning "Browse with Screenpipe running, then re-run export + build_tiles + pixelrag_pipeline."
    } elseif (Test-Path $indexFaiss) {
        Write-Host "FAISS index already exists - skipping rebuild (embedding takes hours on CPU)." -ForegroundColor Yellow
        Write-Host "To rebuild with new captures: python -m tools.pixelrag_pipeline" -ForegroundColor Gray
    } else {
        $buildMsg = 'Building PixelRAG index ({0} articles)...' -f $tileArticles.Count
        Write-Host $buildMsg -ForegroundColor Green
        Invoke-ArchivistPython "tools.pixelrag_pipeline"
    }

    $port = if ($env:PIXELRAG_SERVE_PORT) { $env:PIXELRAG_SERVE_PORT } else { "30001" }
    $serveListening = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($serveListening) {
        Write-Host "PixelRAG serve already listening on :$port" -ForegroundColor Yellow
    } elseif (Test-Path $indexFaiss) {
        $articlesJson = Join-Path $indexDir "articles.json"
        $pixelragPython = Resolve-PixelragPython
        Write-Host "Starting PixelRAG serve on :$port (background)..." -ForegroundColor Green
        $env:PYTHONPATH = $Root
        Start-Process -FilePath $pixelragPython -ArgumentList @(
            "-m", "tools.pixelrag_serve_quiet",
            "--index-dir", $indexDir,
            "--tiles-dir", $tilesDir,
            "--articles-json", $articlesJson,
            "--port", $port
        ) -WorkingDirectory $Root
    } else {
        Write-Warning "No FAISS index at $indexDir - PixelRAG serve skipped until tiles exist."
    }
} else {
    Write-Warning "pixelrag CLI missing. Install: pip install 'pixelrag[index,serve]'"
}

# 4) Unified memory API (foreground)
$apiPort = if ($env:UNIFIED_MEMORY_API_PORT) { $env:UNIFIED_MEMORY_API_PORT } else { "40001" }
Write-Host "Starting unified memory API on :$apiPort" -ForegroundColor Green
$queryExample = 'curl -X POST http://localhost:{0}/query -H "Content-Type: application/json" -d ''{{"query":"PixelRAG","k":3}}''' -f $apiPort
Write-Host $queryExample -ForegroundColor Gray
Write-Host ""
Invoke-ArchivistPython "tools.unified_memory_api"

# 5) OPTIONAL: Clicky cursor overlay (run in a separate terminal - this script
#    blocks on the unified memory API above). Clicky talks to the local worker
#    adapter (tools/clicky_worker_api.py on :40002), which answers /chat from
#    the unified memory API and proxies voice routes to the Cloudflare worker.
# .\deploy\scripts\start-clicky.ps1
