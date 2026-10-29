$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw 'uv is required. See https://docs.astral.sh/uv/getting-started/installation/'
}
& uv sync --frozen
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host 'Open http://127.0.0.1:8000 - press Ctrl+C to stop.'
& uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
exit $LASTEXITCODE
