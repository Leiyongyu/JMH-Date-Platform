param(
    [ValidateSet("date-project", "platform", "all")]
    [string]$Target = "date-project"
)

$ErrorActionPreference = "Stop"

$DateProjectRemote = "https://github.com/Jiumahe-Supply-Chain/Date-Project.git"
$TempDateProjectRepo = "C:\tmp\date-project-push"

$DateProjectDir = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$PlatformDir = (Resolve-Path -LiteralPath (Join-Path $DateProjectDir "..")).Path

function Write-Section {
    param([string]$Text)
    Write-Host ""
    Write-Host "==== $Text ====" -ForegroundColor Cyan
}

function Invoke-Git {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    Push-Location $WorkingDirectory
    try {
        & git @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "git $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
}

function Get-GitOutput {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    Push-Location $WorkingDirectory
    try {
        $output = & git @Arguments
        if ($LASTEXITCODE -ne 0) {
            return ""
        }
        return ($output | Out-String).Trim()
    }
    finally {
        Pop-Location
    }
}

function Ensure-GitIdentity {
    param([string]$WorkingDirectory)

    $name = Get-GitOutput -WorkingDirectory $WorkingDirectory -Arguments @("config", "--get", "user.name")
    $email = Get-GitOutput -WorkingDirectory $WorkingDirectory -Arguments @("config", "--get", "user.email")

    if (-not $name) {
        $name = Get-GitOutput -WorkingDirectory $PlatformDir -Arguments @("config", "--get", "user.name")
    }
    if (-not $email) {
        $email = Get-GitOutput -WorkingDirectory $PlatformDir -Arguments @("config", "--get", "user.email")
    }
    if (-not $name) {
        $name = "Codex"
    }
    if (-not $email) {
        $email = "codex@local"
    }

    Invoke-Git -WorkingDirectory $WorkingDirectory -Arguments @("config", "user.name", $name)
    Invoke-Git -WorkingDirectory $WorkingDirectory -Arguments @("config", "user.email", $email)
}

function Read-CommitMessage {
    Write-Section "Commit message"
    $title = ""
    while ([string]::IsNullOrWhiteSpace($title)) {
        $title = Read-Host "Commit title, example: feat: add performance source export"
    }

    Write-Host ""
    Write-Host "Commit details, multi-line. Type END to finish:" -ForegroundColor Yellow
    $lines = New-Object System.Collections.Generic.List[string]
    while ($true) {
        $line = Read-Host
        if ($line -eq "END") {
            break
        }
        $lines.Add($line)
    }

    $body = ($lines | Where-Object { $_ -ne $null }) -join [Environment]::NewLine
    if ([string]::IsNullOrWhiteSpace($body)) {
        return $title
    }
    return ($title + [Environment]::NewLine + [Environment]::NewLine + $body)
}

function Save-CommitMessageFile {
    param([string]$Message)

    $path = Join-Path $env:TEMP ("date-project-commit-message-" + [Guid]::NewGuid().ToString("N") + ".txt")
    [System.IO.File]::WriteAllText($path, $Message, [System.Text.Encoding]::UTF8)
    return $path
}

function Has-Changes {
    param([string]$WorkingDirectory)

    $status = Get-GitOutput -WorkingDirectory $WorkingDirectory -Arguments @("status", "--porcelain")
    return -not [string]::IsNullOrWhiteSpace($status)
}

function Commit-IfChanged {
    param(
        [string]$WorkingDirectory,
        [string]$MessageFile
    )

    Invoke-Git -WorkingDirectory $WorkingDirectory -Arguments @("add", "-A")
    if (-not (Has-Changes $WorkingDirectory)) {
        Write-Host "No changes to commit." -ForegroundColor Yellow
        return $false
    }

    Ensure-GitIdentity $WorkingDirectory
    Invoke-Git -WorkingDirectory $WorkingDirectory -Arguments @("commit", "-F", $MessageFile)
    return $true
}

function Push-DateProject {
    param([string]$MessageFile)

    Write-Section "Sync and push Date-Project repository"
    Write-Host "Source: $DateProjectDir"
    Write-Host "Remote: $DateProjectRemote"

    if (Test-Path -LiteralPath $TempDateProjectRepo) {
        $resolved = (Resolve-Path -LiteralPath $TempDateProjectRepo).Path
        if ($resolved -ne $TempDateProjectRepo) {
            throw "Unexpected temp directory: $resolved"
        }
        Remove-Item -LiteralPath $TempDateProjectRepo -Recurse -Force
    }

    $tempParent = Split-Path $TempDateProjectRepo -Parent
    if (-not (Test-Path -LiteralPath $tempParent)) {
        New-Item -ItemType Directory -Path $tempParent | Out-Null
    }
    Invoke-Git -WorkingDirectory $tempParent -Arguments @("clone", $DateProjectRemote, $TempDateProjectRepo)

    $excludeDirs = @(
        ".git",
        ".agents",
        ".codex-mismatch-report",
        ".codex-sheet-qa",
        ".codex-template-inspect",
        ".idea",
        ".pytest_cache",
        ".run",
        ".venv",
        "__pycache__",
        "exports",
        "logs",
        "outputs",
        "tmp",
        "node_modules",
        "dist"
    )
    $excludeFiles = @(".env", "*.pyc", "*.pyo", "*.log")

    & robocopy $DateProjectDir $TempDateProjectRepo /MIR /XD @excludeDirs /XF @excludeFiles | Out-Host
    if ($LASTEXITCODE -le 7) {
        $global:LASTEXITCODE = 0
    }
    else {
        throw "robocopy failed, exit code: $LASTEXITCODE"
    }

    if (Test-Path -LiteralPath (Join-Path $TempDateProjectRepo ".env")) {
        throw "Safety check failed: .env was copied to temp repository"
    }

    $committed = Commit-IfChanged $TempDateProjectRepo $MessageFile
    if ($committed) {
        Invoke-Git -WorkingDirectory $TempDateProjectRepo -Arguments @("push", "origin", "main")
    }

    $head = Get-GitOutput -WorkingDirectory $TempDateProjectRepo -Arguments @("rev-parse", "--short", "HEAD")
    Write-Host "Date-Project HEAD: $head" -ForegroundColor Green
}

function Push-Platform {
    param([string]$MessageFile)

    Write-Section "Commit and push platform repository"
    Write-Host "Platform directory: $PlatformDir"

    $topLevel = Get-GitOutput -WorkingDirectory $PlatformDir -Arguments @("rev-parse", "--show-toplevel")
    if (-not $topLevel) {
        throw "Platform directory is not a Git repository: $PlatformDir"
    }

    $branch = Get-GitOutput -WorkingDirectory $PlatformDir -Arguments @("branch", "--show-current")
    if (-not $branch) {
        throw "Platform repository has no current branch to push"
    }

    $remote = Get-GitOutput -WorkingDirectory $PlatformDir -Arguments @("remote", "get-url", "origin")
    if (-not $remote) {
        throw "Platform repository has no origin remote"
    }

    Write-Host "Branch: $branch"
    Write-Host "Remote: $remote"

    $committed = Commit-IfChanged $PlatformDir $MessageFile
    if ($committed) {
        $upstream = Get-GitOutput -WorkingDirectory $PlatformDir -Arguments @("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
        if ($upstream) {
            Invoke-Git -WorkingDirectory $PlatformDir -Arguments @("push", "origin", $branch)
        }
        else {
            Invoke-Git -WorkingDirectory $PlatformDir -Arguments @("push", "-u", "origin", $branch)
        }
    }

    $head = Get-GitOutput -WorkingDirectory $PlatformDir -Arguments @("rev-parse", "--short", "HEAD")
    Write-Host "Platform HEAD: $head" -ForegroundColor Green
}

function Confirm-Target {
    Write-Section "Push target"
    switch ($Target) {
        "date-project" { Write-Host "Only Date-Project repository will be pushed." }
        "platform" { Write-Host "Only platform parent repository will be pushed." }
        "all" { Write-Host "Platform repository will be pushed first, then Date-Project repository." }
    }
    $confirm = Read-Host "Continue? Type Y to continue"
    if ($confirm -ne "Y" -and $confirm -ne "y") {
        throw "Cancelled"
    }
}

try {
    Confirm-Target
    $message = Read-CommitMessage
    $messageFile = Save-CommitMessageFile $message

    if ($Target -eq "platform" -or $Target -eq "all") {
        Push-Platform $messageFile
    }
    if ($Target -eq "date-project" -or $Target -eq "all") {
        Push-DateProject $messageFile
    }

    Write-Section "Done"
    Write-Host "Push completed." -ForegroundColor Green
}
catch {
    Write-Host ""
    Write-Host "Failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
finally {
    if ($messageFile -and (Test-Path -LiteralPath $messageFile)) {
        Remove-Item -LiteralPath $messageFile -Force
    }
}
