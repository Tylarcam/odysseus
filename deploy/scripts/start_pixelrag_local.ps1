$ErrorActionPreference = "Stop"
$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location $Root
$env:PYTHONPATH = $Root

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

if (Test-Path "memory_stack.env") {
    Get-Content "memory_stack.env" | ForEach-Object {
        if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
        $parts = $_ -split '=', 2
        Set-Item -Path "env:$($parts[0].Trim())" -Value $parts[1].Trim()
    }
}

python -m tools.export_screenpipe
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

python -m tools.build_tiles
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (Get-Command pixelrag -ErrorAction SilentlyContinue) {
    $tilesDir = if ($env:PIXELRAG_TILES_DIR) { $env:PIXELRAG_TILES_DIR } else { "./my_index/tiles" }
    $tileArticles = @(Get-ChildItem -Path $tilesDir -Filter "*.png.tiles" -Directory -ErrorAction SilentlyContinue)
    if ($tileArticles.Count -gt 0) {
        python -m tools.pixelrag_pipeline
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } else {
        Write-Warning "No PixelRAG tile dirs - skipping index build"
    }
    $indexDir = if ($env:PIXELRAG_INDEX_DIR) { $env:PIXELRAG_INDEX_DIR } else { "./my_index" }
    $port = if ($env:PIXELRAG_SERVE_PORT) { $env:PIXELRAG_SERVE_PORT } else { "30001" }
    if (Test-Path (Join-Path $indexDir "index.faiss")) {
        $articlesJson = Join-Path $indexDir "articles.json"
        $pixelragPython = Resolve-PixelragPython
        $env:PYTHONPATH = $Root
        & $pixelragPython -m tools.pixelrag_serve_quiet --index-dir $indexDir --tiles-dir $tilesDir --articles-json $articlesJson --port $port
    } else {
        Write-Error "No FAISS index; capture screenshots first."
    }
} else {
    Write-Error "pixelrag CLI not found; tiles built. Install PixelRAG to index and serve."
}
