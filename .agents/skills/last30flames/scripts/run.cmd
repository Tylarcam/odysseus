@echo off
REM Windows launcher for last30flames (Git Bash or bun).
REM Prefer this over bare `bash` — System32\bash.exe is WSL and breaks pipefail.
setlocal
set "SCRIPT_DIR=%~dp0"
set "SKILL_DIR=%SCRIPT_DIR%.."
cd /d "%SKILL_DIR%"

where bun >nul 2>&1
if errorlevel 1 (
  if exist "%USERPROFILE%\.bun\bin\bun.exe" (
    set "PATH=%USERPROFILE%\.bun\bin;%PATH%"
  ) else (
    echo bun is required. Install: powershell -c "irm bun.sh/install.ps1|iex" 1>&2
    exit /b 1
  )
)

if not exist "node_modules\" (
  echo Installing dependencies ^(first run^)... 1>&2
  bun install 1>&2
)

where firecrawl >nul 2>&1
if errorlevel 1 (
  echo Fetching the Firecrawl CLI via bunx ^(first run only^)... 1>&2
  bunx firecrawl-cli --version 1>&2
)

bun run scripts/index.ts %*
exit /b %ERRORLEVEL%
