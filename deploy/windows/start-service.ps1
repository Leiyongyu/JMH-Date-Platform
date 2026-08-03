param(
    [string]$InstallDir = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)),
    [int]$Port = 8010
)

$ErrorActionPreference = "Stop"
$projectDir = (Resolve-Path -LiteralPath $InstallDir).Path
$pythonExe = Join-Path $projectDir ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Python virtual environment not found: $pythonExe"
}
if (-not (Test-Path -LiteralPath (Join-Path $projectDir ".env"))) {
    throw "Missing .env in $projectDir"
}

Set-Location -LiteralPath $projectDir
& $pythonExe -m uvicorn backend.main:app --host 0.0.0.0 --port $Port
