param(
    [ValidateRange(1, 90)]
    [int]$Days = 30,
    [ValidateRange(0, 20)]
    [int]$ShowOrders = 5,
    [string]$EnvFile = (Join-Path $PSScriptRoot '..\..\.env'),
    [string]$TokenFile = (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'JMH-Secrets\ebay-test-refresh-token.dpapi'),
    [switch]$SkipOrders,
    [switch]$SkipInventory
)

$ErrorActionPreference = 'Stop'

function Get-DotEnvValue {
    param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)][string]$Name)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "配置文件不存在: $Path"
    }
    $line = Get-Content -LiteralPath $Path | Where-Object {
        $_ -match ('^\s*' + [regex]::Escape($Name) + '\s*=')
    } | Select-Object -Last 1
    if (-not $line) { throw "缺少配置 $Name" }
    $value = ($line -split '=', 2)[1].Trim()
    if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
        ($value.StartsWith("'") -and $value.EndsWith("'"))) {
        $value = $value.Substring(1, $value.Length - 2)
    }
    if ([string]::IsNullOrWhiteSpace($value) -or $value.StartsWith('YOUR_')) {
        throw "配置 $Name 为空"
    }
    return $value
}

function Invoke-EbayJson {
    param(
        [Parameter(Mandatory)][ValidateSet('GET', 'POST')][string]$Method,
        [Parameter(Mandatory)][string]$Uri,
        [hashtable]$Headers,
        [hashtable]$Body
    )
    try {
        $params = @{
            Method = $Method
            Uri = $Uri
            TimeoutSec = 30
        }
        if ($Headers) { $params.Headers = $Headers }
        if ($Body) {
            $params.Body = $Body
            $params.ContentType = 'application/x-www-form-urlencoded'
        }
        return Invoke-RestMethod @params
    }
    catch {
        $status = $null
        try { $status = [int]$_.Exception.Response.StatusCode } catch {}
        throw "eBay API 请求失败 (HTTP $status): $($_.Exception.Message)"
    }
}

try {
    $resolvedEnvFile = [IO.Path]::GetFullPath($EnvFile)
    $resolvedTokenFile = [IO.Path]::GetFullPath($TokenFile)
    $clientId = Get-DotEnvValue -Path $resolvedEnvFile -Name 'EBAY_CLIENT_ID'
    $clientSecret = Get-DotEnvValue -Path $resolvedEnvFile -Name 'EBAY_CLIENT_SECRET'

    if (-not (Test-Path -LiteralPath $resolvedTokenFile -PathType Leaf)) {
        throw "加密 Refresh Token 文件不存在: $resolvedTokenFile"
    }
    $encrypted = Get-Content -Raw -LiteralPath $resolvedTokenFile
    $secureToken = ConvertTo-SecureString $encrypted
    $refreshToken = [System.Net.NetworkCredential]::new('', $secureToken).Password
    if ([string]::IsNullOrWhiteSpace($refreshToken)) { throw 'Refresh Token 解密结果为空' }

    $pairBytes = [Text.Encoding]::ASCII.GetBytes("${clientId}:${clientSecret}")
    $basic = [Convert]::ToBase64String($pairBytes)
    $tokenResult = Invoke-EbayJson -Method POST `
        -Uri 'https://api.ebay.com/identity/v1/oauth2/token' `
        -Headers @{ Authorization = "Basic $basic" } `
        -Body @{ grant_type = 'refresh_token'; refresh_token = $refreshToken }
    $accessToken = $tokenResult.access_token
    if ([string]::IsNullOrWhiteSpace($accessToken)) { throw 'eBay 刷新响应中没有 access_token' }
    Write-Host "[OK] Access Token 刷新成功，有效期 $($tokenResult.expires_in) 秒" -ForegroundColor Green

    $bearer = @{ Authorization = "Bearer $accessToken"; Accept = 'application/json' }
    $identity = Invoke-EbayJson -Method GET -Uri 'https://apiz.ebay.com/commerce/identity/v1/user/' -Headers $bearer
    Write-Host "`n=== 店铺身份 ==="
    [pscustomobject]@{
        userId = $identity.userId
        username = $identity.username
        accountType = $identity.accountType
        registrationMarketplaceId = $identity.registrationMarketplaceId
    } | Format-List

    $privilege = Invoke-EbayJson -Method GET -Uri 'https://api.ebay.com/sell/account/v1/privilege/' -Headers $bearer
    Write-Host '=== 卖家账号 ==='
    [pscustomobject]@{
        sellerRegistrationCompleted = $privilege.sellerRegistrationCompleted
        sellingLimitQuantity = $privilege.sellingLimit.quantity
        sellingLimitAmount = $privilege.sellingLimit.amount.value
        sellingLimitCurrency = $privilege.sellingLimit.amount.currency
    } | Format-List

    if (-not $SkipOrders) {
        $end = [DateTime]::UtcNow
        $start = $end.AddDays(-$Days)
        $filter = 'creationdate:[{0}..{1}]' -f `
            $start.ToString('yyyy-MM-ddTHH:mm:ss.000Z'), `
            $end.ToString('yyyy-MM-ddTHH:mm:ss.000Z')
        $ordersUri = 'https://api.ebay.com/sell/fulfillment/v1/order?filter={0}&limit=50&offset=0' -f `
            [Uri]::EscapeDataString($filter)
        $ordersResult = Invoke-EbayJson -Method GET -Uri $ordersUri -Headers $bearer
        $orders = @($ordersResult.orders)
        Write-Host "=== 最近 $Days 天订单 ==="
        Write-Host "eBay total: $($ordersResult.total)"
        Write-Host "本页返回: $($orders.Count)"
        foreach ($order in ($orders | Select-Object -First $ShowOrders)) {
            $skus = @($order.lineItems | Where-Object sku | ForEach-Object sku | Sort-Object -Unique)
            [pscustomobject]@{
                orderId = $order.orderId
                creationDate = $order.creationDate
                paymentStatus = $order.orderPaymentStatus
                fulfillmentStatus = $order.orderFulfillmentStatus
                total = $order.pricingSummary.total.value
                currency = $order.pricingSummary.total.currency
                lineItemCount = @($order.lineItems).Count
                skus = ($skus -join ',')
            } | Format-List
        }
    }

    if (-not $SkipInventory) {
        $inventory = Invoke-EbayJson -Method GET `
            -Uri 'https://api.ebay.com/sell/inventory/v1/inventory_item?limit=100&offset=0' `
            -Headers $bearer
        $items = @($inventory.inventoryItems)
        Write-Host '=== Inventory API 库存商品 ==='
        Write-Host "eBay total: $($inventory.total)"
        Write-Host "本页返回: $($items.Count)"
        if ($items.Count -eq 0) {
            Write-Host '[INFO] 返回 0 不代表卖家中心没有商品；历史刊登可能需要 Trading API/GetMyeBaySelling。'
        }
    }

    Write-Host "`n[PASS] eBay 卖家 API 只读测试完成" -ForegroundColor Green
}
catch {
    Write-Error "[FAIL] $($_.Exception.Message)"
    exit 1
}
finally {
    $clientSecret = $null
    $refreshToken = $null
    $accessToken = $null
}
