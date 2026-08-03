param(
    [string]$InstallDir = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)),
    [string]$PythonExe = "python",
    [string]$TaskName = "JMH-Date-Project-API",
    [int]$Port = 8010
)

$ErrorActionPreference = "Stop"
$projectDir = (Resolve-Path -LiteralPath $InstallDir).Path
$envFile = Join-Path $projectDir ".env"
if (-not (Test-Path -LiteralPath $envFile)) {
    throw "Please copy .env.example to .env and fill MySQL/LingXing/token values first."
}

$venvPython = Join-Path $projectDir ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    & $PythonExe -m venv (Join-Path $projectDir ".venv")
}
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r (Join-Path $projectDir "backend\requirements.txt")

Push-Location -LiteralPath $projectDir
try {
    & $venvPython -m backend.cli init-db
}
finally {
    Pop-Location
}

$startScript = Join-Path $projectDir "deploy\windows\start-service.ps1"
$powerShellExe = (Get-Command powershell.exe).Source
$argument = "-NoProfile -ExecutionPolicy Bypass -File `"$startScript`" -InstallDir `"$projectDir`" -Port $Port"
$action = New-ScheduledTaskAction `
    -Execute $powerShellExe `
    -Argument $argument `
    -WorkingDirectory $projectDir
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal `
    -UserId "SYSTEM" `
    -LogonType ServiceAccount `
    -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet `
    -RestartCount 5 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName

Write-Host "Installed and started $TaskName on port $Port."
Write-Host "Health URL: http://127.0.0.1:$Port/api/v1/health"
