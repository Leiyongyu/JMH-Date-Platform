<#
.SYNOPSIS
Rotate the LingXing OpenAPI credentials on this machine.

.DESCRIPTION
Reads the new "APP ID" / "AppSecret" from a plain text file and applies them to
both services that talk to LingXing:

  * Python service - rewrites LINGXING_APP_ID / LINGXING_APP_SECRET in
    Date-Project\.env, leaving every other line byte-identical.
  * Java service   - with -SetMachineEnv, stores both as machine-level
    environment variables, because application.yml deliberately keeps no
    default any more.

The secret is never printed, never logged and never passed on a command line.
Only its length and a short SHA-256 prefix are shown, so the same file applied
on two machines can be compared without revealing anything.

ASCII only on purpose: the deploy box runs PowerShell 5.1 under code page 936,
where UTF-8 text in a script can swallow line breaks.

.PARAMETER CredentialFile
Path to the file holding the new credentials. Accepted line formats, case
insensitive, ':' or '=' as separator:
    APP ID: ak_xxxxxxxxxxxx
    AppSecret: yyyyyyyy

.PARAMETER SetMachineEnv
Also write machine-level environment variables for the Java service.
Requires an elevated shell.

.PARAMETER EnvOnly
Skip the .env rewrite and only set the machine environment variables. Use it
to finish the Java half from an elevated shell after a first run already
updated .env.

.PARAMETER DryRun
Parse and validate only. Nothing is written.

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File .\rotate_lingxing_credentials.ps1 -CredentialFile "$env:USERPROFILE\Desktop\mykey.txt" -DryRun

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File .\rotate_lingxing_credentials.ps1 -CredentialFile "$env:USERPROFILE\Desktop\mykey.txt" -SetMachineEnv
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $CredentialFile,

    [switch] $SetMachineEnv,

    [switch] $EnvOnly,

    [switch] $DryRun
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Write-Step([string] $Text) { Write-Host "  $Text" }

function Get-Fingerprint([string] $Value) {
    # Short digest: enough to compare two machines, useless to an attacker.
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($Value))
        return (([System.BitConverter]::ToString($bytes)) -replace '-', '').Substring(0, 12).ToLowerInvariant()
    }
    finally { $sha.Dispose() }
}

function Read-Credentials([string] $Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Credential file not found: $Path"
    }
    $appId = $null
    $appSecret = $null
    foreach ($line in [System.IO.File]::ReadAllLines($Path, $Utf8NoBom)) {
        if ($line -match '^\s*app\s*[-_]?\s*id\s*[:=]\s*(\S.*?)\s*$') {
            $appId = $Matches[1]
        }
        elseif ($line -match '^\s*app\s*[-_]?\s*secret\s*[:=]\s*(\S.*?)\s*$') {
            $appSecret = $Matches[1]
        }
    }
    if ([string]::IsNullOrWhiteSpace($appId)) {
        throw "No 'APP ID' line found in $Path"
    }
    if ([string]::IsNullOrWhiteSpace($appSecret)) {
        throw "No 'AppSecret' line found in $Path"
    }
    # A stray quote or trailing comment would be stored verbatim and break
    # signing with an error that points nowhere near the real cause.
    foreach ($pair in @(@('APP ID', $appId), @('AppSecret', $appSecret))) {
        if ($pair[1] -match '[\s"''#]') {
            throw "$($pair[0]) contains whitespace, quotes or '#'. Clean the file and retry."
        }
    }
    return @{ AppId = $appId; AppSecret = $appSecret }
}

function Update-DotEnv([string] $Path, [hashtable] $Credentials, [bool] $Apply) {
    if (-not (Test-Path -LiteralPath $Path)) {
        throw ".env not found: $Path"
    }
    $original = [System.IO.File]::ReadAllText($Path, $Utf8NoBom)
    # Keep the file's own line ending style instead of normalising it.
    $newline = if ($original -match "`r`n") { "`r`n" } else { "`n" }
    $endsWithNewline = $original.EndsWith("`n")
    $lines = $original -split "`r`n|`n"
    if ($endsWithNewline -and $lines.Length -gt 0) {
        $lines = $lines[0..($lines.Length - 2)]
    }

    $seen = @{ 'LINGXING_APP_ID' = $false; 'LINGXING_APP_SECRET' = $false }
    $result = New-Object System.Collections.Generic.List[string]
    foreach ($line in $lines) {
        if ($line -match '^\s*LINGXING_APP_ID\s*=') {
            $result.Add('LINGXING_APP_ID=' + $Credentials.AppId)
            $seen['LINGXING_APP_ID'] = $true
        }
        elseif ($line -match '^\s*LINGXING_APP_SECRET\s*=') {
            $result.Add('LINGXING_APP_SECRET=' + $Credentials.AppSecret)
            $seen['LINGXING_APP_SECRET'] = $true
        }
        else {
            $result.Add($line)
        }
    }
    foreach ($key in @('LINGXING_APP_ID', 'LINGXING_APP_SECRET')) {
        if (-not $seen[$key]) {
            throw "$key line not present in $Path - refusing to guess where it belongs."
        }
    }

    $updated = [string]::Join($newline, $result)
    if ($endsWithNewline) { $updated += $newline }

    if (-not $Apply) {
        Write-Step "[dry-run] would rewrite 2 lines in $Path"
        return
    }

    # Backups go OUTSIDE the repository on purpose: .gitignore only matches the
    # exact name ".env", so a ".env.bak-..." sibling would be committed with the
    # previous secret still in it.
    $backupDir = Join-Path $env:LOCALAPPDATA 'jmh-platform\credential-backups'
    if (-not (Test-Path -LiteralPath $backupDir)) {
        New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
    }
    $backup = Join-Path $backupDir ('Date-Project.env.bak-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    [System.IO.File]::WriteAllText($backup, $original, $Utf8NoBom)
    [System.IO.File]::WriteAllText($Path, $updated, $Utf8NoBom)
    Write-Step "rewrote 2 lines in $Path"
    Write-Step "backup: $backup"

    # Read back so a silent encoding or permission problem cannot pass as success.
    $verify = [System.IO.File]::ReadAllLines($Path, $Utf8NoBom)
    $idOk = $verify | Where-Object { $_ -eq ('LINGXING_APP_ID=' + $Credentials.AppId) }
    $secretOk = $verify | Where-Object { $_ -eq ('LINGXING_APP_SECRET=' + $Credentials.AppSecret) }
    if (-not $idOk -or -not $secretOk) {
        throw "Verification failed: $Path does not contain the new values. Restore from $backup"
    }
    Write-Step "verified by re-reading the file"
}

function Set-MachineEnvironment([hashtable] $Credentials, [bool] $Apply) {
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object System.Security.Principal.WindowsPrincipal($identity)
    $elevated = $principal.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $elevated) {
        # Returning instead of throwing: a first run without elevation has
        # already rewritten .env by this point, and throwing here would hide
        # the remaining steps printed at the end.
        Write-Warning 'Not an elevated shell - machine environment NOT set.'
        return $false
    }
    if (-not $Apply) {
        Write-Step "[dry-run] would set LINGXING_APP_ID and LINGXING_APP_SECRET at machine scope"
        return $true
    }
    [System.Environment]::SetEnvironmentVariable('LINGXING_APP_ID', $Credentials.AppId, 'Machine')
    [System.Environment]::SetEnvironmentVariable('LINGXING_APP_SECRET', $Credentials.AppSecret, 'Machine')
    Write-Step "set LINGXING_APP_ID and LINGXING_APP_SECRET at machine scope"

    $readBack = [System.Environment]::GetEnvironmentVariable('LINGXING_APP_SECRET', 'Machine')
    if ($readBack -ne $Credentials.AppSecret) {
        throw "Verification failed: machine environment variable did not take."
    }
    Write-Step "verified by reading the machine scope back"
    Write-Step "NOTE: already running processes keep the old value until restarted."
    return $true
}

$repoRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$dotEnvPath = Join-Path $repoRoot 'Date-Project\.env'
$apply = -not $DryRun

Write-Host ''
Write-Host 'LingXing credential rotation'
Write-Host '----------------------------'
$credentials = Read-Credentials -Path $CredentialFile
Write-Host 'Parsed credentials:'
Write-Step ("APP ID    length={0,-3} fingerprint={1}" -f $credentials.AppId.Length, (Get-Fingerprint $credentials.AppId))
Write-Step ("AppSecret length={0,-3} fingerprint={1}" -f $credentials.AppSecret.Length, (Get-Fingerprint $credentials.AppSecret))
if ($credentials.AppId.Length -ne 16) {
    Write-Warning ("APP ID is {0} characters, not the usual 16. Signing uses the APP ID as a 16-byte AES key, so check this before restarting." -f $credentials.AppId.Length)
}
Write-Host ''

Write-Host 'Python service (.env):'
if ($EnvOnly) {
    Write-Step 'skipped - -EnvOnly was passed'
}
else {
    Update-DotEnv -Path $dotEnvPath -Credentials $credentials -Apply $apply
}
Write-Host ''

Write-Host 'Java service (machine environment):'
$machineEnvOk = $true
if ($SetMachineEnv) {
    $machineEnvOk = Set-MachineEnvironment -Credentials $credentials -Apply $apply
}
else {
    $machineEnvOk = $false
    Write-Step 'skipped - pass -SetMachineEnv on the machine that runs the Java service'
}
Write-Host ''

if ($apply) {
    if (-not $machineEnvOk) {
        Write-Host 'STILL TO DO - the Java half. From an ELEVATED shell, in the repo root:'
        Write-Host '  powershell -NoProfile -ExecutionPolicy Bypass -File ".\Date-Project\deploy\ops\rotate_lingxing_credentials.ps1" -CredentialFile "<path to the file>" -EnvOnly -SetMachineEnv'
        Write-Host '  (-EnvOnly keeps it from rewriting .env a second time.)'
        Write-Host ''
    }
    Write-Host 'Done. Remaining steps are manual, in this order:'
    Write-Host '  1. Restart the Python service, then run, from the Date-Project folder:'
    Write-Host '       .venv\Scripts\python.exe -m backend.cli lingxing-token --refresh'
    Write-Host '     The old access_token lives in the lingxing_token table and does NOT'
    Write-Host '     expire on restart, so this step is required, not optional.'
    Write-Host '  2. Restart the Java service. Its token cache is in memory only.'
    Write-Host '  3. Verify:'
    Write-Host '       .venv\Scripts\python.exe -m backend.cli lingxing-token --show'
    Write-Host '  4. Delete the credential file once both services are confirmed working.'
}
else {
    Write-Host 'Dry run only - nothing was written.'
}
Write-Host ''
