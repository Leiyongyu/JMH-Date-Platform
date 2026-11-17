param(
    [string]$EnvFile = (Join-Path $PSScriptRoot '..\..\.env'),
    [string]$TokenFile = (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'JMH-Secrets\ebay-test-refresh-token.dpapi'),
    [string]$OutputRoot = (Join-Path $PSScriptRoot '..\..\outputs\ebay-seller-standards'),
    [ValidateSet('CURRENT', 'PROJECTED')]
    [string[]]$Cycles = @('CURRENT', 'PROJECTED'),
    [ValidateSet('PROGRAM_US', 'PROGRAM_UK', 'PROGRAM_DE', 'PROGRAM_GLOBAL')]
    [string[]]$Programs = @('PROGRAM_US', 'PROGRAM_UK', 'PROGRAM_DE', 'PROGRAM_GLOBAL'),
    [string]$NodePath,
    [string]$ArtifactNodeModulesPath,
    [switch]$SkipExcel
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Get-DotEnvValue {
    param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)][string]$Name)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "配置文件不存在: $Path" }
    $line = Get-Content -LiteralPath $Path | Where-Object {
        $_ -match ('^\s*' + [regex]::Escape($Name) + '\s*=')
    } | Select-Object -Last 1
    if (-not $line) { throw "缺少配置 $Name" }
    $value = ($line -split '=', 2)[1].Trim()
    if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
        ($value.StartsWith("'") -and $value.EndsWith("'"))) {
        $value = $value.Substring(1, $value.Length - 2)
    }
    if ([string]::IsNullOrWhiteSpace($value) -or $value.StartsWith('YOUR_')) { throw "配置 $Name 为空" }
    return $value
}

function Invoke-HttpJson {
    param(
        [Parameter(Mandatory)][ValidateSet('GET', 'POST')][string]$Method,
        [Parameter(Mandatory)][string]$Uri,
        [hashtable]$Headers,
        [hashtable]$Body
    )
    $params = @{ Method = $Method; Uri = $Uri; TimeoutSec = 60; SkipHttpErrorCheck = $true }
    if ($Headers) { $params.Headers = $Headers }
    if ($Body) { $params.Body = $Body; $params.ContentType = 'application/x-www-form-urlencoded' }
    try { $response = Invoke-WebRequest @params }
    catch { throw "HTTP 请求失败: $($_.Exception.Message)" }
    $payload = $null
    if (-not [string]::IsNullOrWhiteSpace([string]$response.Content)) {
        try { $payload = ([string]$response.Content) | ConvertFrom-Json -Depth 100 }
        catch { $payload = [pscustomobject]@{ raw = [string]$response.Content } }
    }
    [pscustomobject]@{ StatusCode = [int]$response.StatusCode; Payload = $payload }
}

function Get-PropertyValue {
    param([object]$Object, [Parameter(Mandatory)][string[]]$Names)
    if ($null -eq $Object) { return $null }
    foreach ($name in $Names) {
        $property = $Object.PSObject.Properties[$name]
        if ($null -ne $property -and $null -ne $property.Value) { return $property.Value }
    }
    return $null
}

function ConvertTo-CompactJson {
    param([object]$Value)
    if ($null -eq $Value) { return $null }
    return ($Value | ConvertTo-Json -Depth 100 -Compress)
}

function Get-ProgramLabel {
    param([Parameter(Mandatory)][string]$Program)
    switch ($Program) {
        'PROGRAM_US' { '美国站卖家标准' }
        'PROGRAM_UK' { '英国站卖家标准' }
        'PROGRAM_DE' { '德国站卖家标准' }
        'PROGRAM_GLOBAL' { '全球/其他站点卖家标准' }
    }
}
