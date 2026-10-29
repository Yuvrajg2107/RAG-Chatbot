@echo off
setlocal
cd /d "%~dp0"
where uv >nul 2>nul
if errorlevel 1 (
  echo uv is required. Install it from https://docs.astral.sh/uv/getting-started/installation/
  exit /b 1
)
uv sync --frozen
if errorlevel 1 exit /b 1
echo Open http://127.0.0.1:8000 - press Ctrl+C to stop.
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
