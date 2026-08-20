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

# 某些终端会同时注入大小写不同的 Path/PATH。Windows PowerShell 的
# Start-Process 会把它们视为重复字典键并拒绝启动子进程，先在当前脚本
# 进程内合并为一个键；不会修改用户或系统环境变量。
$normalizedProcessPath = [Environment]::GetEnvironmentVariable('PATH', 'Process')
[Environment]::SetEnvironmentVariable('PATH', $null, 'Process')
[Environment]::SetEnvironmentVariable('Path', $normalizedProcessPath, 'Process')

$scriptPath = $env:DATE_PROJECT_RESTART_SCRIPT
$projectRoot = Split-Path -Parent $scriptPath
$runtimeDir = Join-Path $projectRoot '.run'
$frontendDir = Join-Path $projectRoot 'frontend'
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
$backendPidFile = Join-Path $runtimeDir 'backend.pid'
$legacyFrontendPidFile = Join-Path $runtimeDir 'frontend.pid'
$backendLog = Join-Path $runtimeDir 'backend.log'
$backendErrorLog = Join-Path $runtimeDir 'backend-error.log'
$frontendBuildLog = Join-Path $runtimeDir 'frontend-build.log'
$frontendBuildErrorLog = Join-Path $runtimeDir 'frontend-build-error.log'
$backendPort = 8010
$listenHost = if ([string]::IsNullOrWhiteSpace($env:DATE_PROJECT_BIND_HOST)) {
    '0.0.0.0'
} else {
    $env:DATE_PROJECT_BIND_HOST.Trim()
}

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
    if ($commandLine.IndexOf($pythonExe, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
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
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
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
    Write-Host "Python listen address: $listenHost`:$backendPort" -ForegroundColor DarkGray
    Write-Host "Script workbench: http://127.0.0.1:$backendPort/script-tools/" -ForegroundColor DarkGray

    Write-Host "Building Python script workbench..." -ForegroundColor Cyan
    Remove-Item -LiteralPath $frontendBuildLog -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $frontendBuildErrorLog -Force -ErrorAction SilentlyContinue
    $buildProcess = Start-Process `
        -FilePath $npmCommand.Source `
        -ArgumentList @('run', 'build') `
        -WorkingDirectory $frontendDir `
        -WindowStyle Hidden `
        -RedirectStandardOutput $frontendBuildLog `
        -RedirectStandardError $frontendBuildErrorLog `
        -Wait `
        -PassThru
    if ($buildProcess.ExitCode -ne 0) {
        Show-LogTail -Path $frontendBuildLog -Title 'frontend-build.log'
        Show-LogTail -Path $frontendBuildErrorLog -Title 'frontend-build-error.log'
        throw "Frontend build failed with exit code $($buildProcess.ExitCode)."
    }
    Write-Host "Script workbench build completed." -ForegroundColor Green

    # 兼容旧版脚本：若曾启动独立 5174 前端，首次执行新版脚本时一并停止。
    Stop-ProcessTreeFromPidFile -PidFile $legacyFrontendPidFile -ServiceName 'frontend'
    Stop-ProcessTreeFromPidFile -PidFile $backendPidFile -ServiceName 'backend'
    Start-Sleep -Milliseconds 600
    Stop-ProjectListener -Port $backendPort -ServiceName 'backend'

    $backendProcess = Start-Process `
        -FilePath $pythonExe `
        -ArgumentList @('-u', '-m', 'uvicorn', 'backend.main:app', '--host', $listenHost, '--port', "$backendPort") `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $backendLog `
        -RedirectStandardError $backendErrorLog `
        -PassThru
    $backendProcess.Id | Set-Content -LiteralPath $backendPidFile -Encoding ascii

    Write-Host "Backend process started, PID: $($backendProcess.Id)" -ForegroundColor DarkGray

    $backendReady = Wait-HttpReady -Url "http://127.0.0.1:$backendPort/api/health" -ServiceName 'Backend'
    $workbenchReady = Wait-HttpReady -Url "http://127.0.0.1:$backendPort/script-tools/" -ServiceName 'Script workbench'
    $imageSopReady = Wait-HttpReady -Url "http://127.0.0.1:$backendPort/image-sop/" -ServiceName 'Image SOP'

    if (-not ($backendReady -and $workbenchReady -and $imageSopReady)) {
        Show-LogTail -Path $backendLog -Title 'backend.log'
        Show-LogTail -Path $backendErrorLog -Title 'backend-error.log'
        throw 'One or more services failed the readiness check.'
    }

    Write-Host "`nRestart complete." -ForegroundColor Green
    Write-Host "Open: http://127.0.0.1:$backendPort/script-tools/" -ForegroundColor Cyan
    Write-Host "API docs: http://127.0.0.1:$backendPort/docs" -ForegroundColor Cyan
    Write-Host "Logs: $runtimeDir" -ForegroundColor DarkGray
    exit 0
} catch {
    Write-Host "`nRestart failed: $($_.Exception.Message)" -ForegroundColor Red
    Stop-ProcessTreeFromPidFile -PidFile $backendPidFile -ServiceName 'backend'
    exit 1
}
