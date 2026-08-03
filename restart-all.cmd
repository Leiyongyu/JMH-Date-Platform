@echo off
chcp 65001 >nul
setlocal
set "DATE_PROJECT_RESTART_SCRIPT=%~f0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$path=$env:DATE_PROJECT_RESTART_SCRIPT; $text=[IO.File]::ReadAllText($path,[Text.Encoding]::UTF8); $marker=':__POWERSHELL_BELOW__'; $index=$text.LastIndexOf($marker); if($index -lt 0){throw 'PowerShell section was not found.'}; $code=$text.Substring($index+$marker.Length); & ([ScriptBlock]::Create($code))"

set "RESTART_EXIT_CODE=%ERRORLEVEL%"
if not "%RESTART_EXIT_CODE%"=="0" (
  echo.
  echo Restart failed. Check the messages above and the log files in .run.
  pause
)
endlocal & exit /b %RESTART_EXIT_CODE%

:__POWERSHELL_BELOW__
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$scriptPath = $env:DATE_PROJECT_RESTART_SCRIPT
$projectRoot = Split-Path -Parent $scriptPath
$runtimeDir = Join-Path $projectRoot '.run'
$frontendDir = Join-Path $projectRoot 'frontend'
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
$backendPidFile = Join-Path $runtimeDir 'backend.pid'
$frontendPidFile = Join-Path $runtimeDir 'frontend.pid'
$backendPort = 8010
$frontendPort = 5174

function Get-CommandLine {
    param([int]$ProcessId)
    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
    return [string]$processInfo.CommandLine
}

function Test-ProjectProcess {
    param([int]$ProcessId, [string]$ServiceName)
    $commandLine = Get-CommandLine -ProcessId $ProcessId
    if ([string]::IsNullOrWhiteSpace($commandLine)) {
        return $false
    }

    if ($commandLine.IndexOf($projectRoot, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
        return $true
    }
    if ($ServiceName -eq 'backend' -and $commandLine.Contains('backend.main:app')) {
        return $true
    }
    return $false
}

function Stop-ProcessTreeFromPidFile {
    param([string]$PidFile, [string]$ServiceName)

    if (-not (Test-Path -LiteralPath $PidFile)) {
        return
    }

    $savedProcessId = Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($savedProcessId -match '^\d+$' -and (Get-Process -Id ([int]$savedProcessId) -ErrorAction SilentlyContinue)) {
        if (Test-ProjectProcess -ProcessId ([int]$savedProcessId) -ServiceName $ServiceName) {
            Write-Host "Stopping $ServiceName process tree (PID $savedProcessId)..." -ForegroundColor Yellow
            & taskkill.exe /PID $savedProcessId /T /F 2>$null | Out-Null
        } else {
            Write-Host "Ignoring stale $ServiceName PID $savedProcessId because it belongs to another program." -ForegroundColor DarkYellow
        }
    }
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
}

function Stop-ProjectListener {
    param([int]$Port, [string]$ServiceName)

    $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($listener in $listeners) {
        $processId = [int]$listener.OwningProcess
        if (Test-ProjectProcess -ProcessId $processId -ServiceName $ServiceName) {
            Write-Host "Stopping stale $ServiceName listener on port $Port (PID $processId)..." -ForegroundColor Yellow
            & taskkill.exe /PID $processId /T /F 2>$null | Out-Null
        } else {
            throw "Port $Port is occupied by another program (PID $processId). No unrelated process was stopped."
        }
    }
}

function Wait-HttpReady {
    param([string]$Url, [string]$ServiceName, [int]$Attempts = 45)

    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                Write-Host "$ServiceName is ready: $Url" -ForegroundColor Green
                return $true
            }
        } catch {
            Start-Sleep -Milliseconds 700
        }
    }
    return $false
}

function Show-LogTail {
    param([string]$Path, [string]$Title)
    if (Test-Path -LiteralPath $Path) {
        Write-Host "`n--- $Title ---" -ForegroundColor DarkYellow
        Get-Content -LiteralPath $Path -Tail 30 -ErrorAction SilentlyContinue
    }
}

New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null

try {
    if (-not (Test-Path -LiteralPath $pythonExe)) {
        throw "Python virtual environment was not found: $pythonExe"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $frontendDir 'node_modules'))) {
        throw "Frontend dependencies are missing. Run npm install in $frontendDir first."
    }
    $npmCommand = Get-Command npm.cmd -ErrorAction Stop

    Write-Host "`n=== Restarting Date-Project ===" -ForegroundColor Cyan
    Write-Host "Backend: http://127.0.0.1:$backendPort" -ForegroundColor DarkGray
    Write-Host "Frontend: http://127.0.0.1:$frontendPort" -ForegroundColor DarkGray

    Stop-ProcessTreeFromPidFile -PidFile $backendPidFile -ServiceName 'backend'
    Stop-ProcessTreeFromPidFile -PidFile $frontendPidFile -ServiceName 'frontend'
    Start-Sleep -Milliseconds 600
    Stop-ProjectListener -Port $backendPort -ServiceName 'backend'
    Stop-ProjectListener -Port $frontendPort -ServiceName 'frontend'

    $backendProcess = Start-Process `
        -FilePath $pythonExe `
        -ArgumentList @('-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', "$backendPort", '--reload') `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $runtimeDir 'backend.log') `
        -RedirectStandardError (Join-Path $runtimeDir 'backend-error.log') `
        -PassThru
    $backendProcess.Id | Set-Content -LiteralPath $backendPidFile -Encoding ascii

    $frontendProcess = Start-Process `
        -FilePath $npmCommand.Source `
        -ArgumentList @('run', 'dev', '--', '--host', '127.0.0.1', '--port', "$frontendPort", '--strictPort') `
        -WorkingDirectory $frontendDir `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $runtimeDir 'frontend.log') `
        -RedirectStandardError (Join-Path $runtimeDir 'frontend-error.log') `
        -PassThru
    $frontendProcess.Id | Set-Content -LiteralPath $frontendPidFile -Encoding ascii

    Write-Host "Backend process started, PID: $($backendProcess.Id)" -ForegroundColor DarkGray
    Write-Host "Frontend process started, PID: $($frontendProcess.Id)" -ForegroundColor DarkGray

    $backendReady = Wait-HttpReady -Url "http://127.0.0.1:$backendPort/api/health" -ServiceName 'Backend'
    $frontendReady = Wait-HttpReady -Url "http://127.0.0.1:$frontendPort" -ServiceName 'Frontend'

    if (-not ($backendReady -and $frontendReady)) {
        Show-LogTail -Path (Join-Path $runtimeDir 'backend-error.log') -Title 'backend-error.log'
        Show-LogTail -Path (Join-Path $runtimeDir 'frontend-error.log') -Title 'frontend-error.log'
        throw 'One or more services failed the readiness check.'
    }

    Write-Host "`nRestart complete." -ForegroundColor Green
    Write-Host "Open: http://127.0.0.1:$frontendPort" -ForegroundColor Cyan
    Write-Host "API docs: http://127.0.0.1:$backendPort/docs" -ForegroundColor Cyan
    Write-Host "Logs: $runtimeDir" -ForegroundColor DarkGray
    exit 0
} catch {
    Write-Host "`nRestart failed: $($_.Exception.Message)" -ForegroundColor Red
    Stop-ProcessTreeFromPidFile -PidFile $backendPidFile -ServiceName 'backend'
    Stop-ProcessTreeFromPidFile -PidFile $frontendPidFile -ServiceName 'frontend'
    exit 1
}
