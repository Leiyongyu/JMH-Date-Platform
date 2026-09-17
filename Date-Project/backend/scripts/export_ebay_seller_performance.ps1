param(
    [string]$EnvFile = (Join-Path $PSScriptRoot '..\..\.env'),
    [string]$TokenFile = (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'JMH-Secrets\ebay-test-refresh-token.dpapi'),
    [string]$OutputRoot = (Join-Path $PSScriptRoot '..\..\outputs\ebay-seller-performance'),
    [ValidateSet('CURRENT', 'PROJECTED')]
    [string[]]$EvaluationTypes = @('CURRENT', 'PROJECTED'),
    [string[]]$Marketplaces = @(
        'EBAY_US', 'EBAY_GB', 'EBAY_DE', 'EBAY_FR',
        'EBAY_IT', 'EBAY_ES', 'EBAY_AU', 'EBAY_CA'
    ),
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

function Get-PropertyValue {
    param([object]$Object, [Parameter(Mandatory)][string]$Name)
    if ($null -eq $Object) { return $null }
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) { return $null }
    return $property.Value
}

function ConvertTo-NullableDouble {
    param([object]$Value)
    if ($null -eq $Value -or [string]::IsNullOrWhiteSpace([string]$Value)) { return $null }
    $number = 0.0
    if ([double]::TryParse(
            [string]$Value,
            [Globalization.NumberStyles]::Any,
            [Globalization.CultureInfo]::InvariantCulture,
            [ref]$number)) {
        return $number
    }
    return $null
}

function Invoke-HttpJson {
    param(
        [Parameter(Mandatory)][ValidateSet('GET', 'POST')][string]$Method,
        [Parameter(Mandatory)][string]$Uri,
        [hashtable]$Headers,
        [hashtable]$Body
    )
    $params = @{
        Method = $Method
        Uri = $Uri
        TimeoutSec = 60
        SkipHttpErrorCheck = $true
    }
    if ($Headers) { $params.Headers = $Headers }
    if ($Body) {
        $params.Body = $Body
        $params.ContentType = 'application/x-www-form-urlencoded'
    }
    try { $response = Invoke-WebRequest @params }
    catch { throw "HTTP 请求失败: $($_.Exception.Message)" }

    $payload = $null
    if (-not [string]::IsNullOrWhiteSpace([string]$response.Content)) {
        try { $payload = ([string]$response.Content) | ConvertFrom-Json -Depth 100 }
        catch { $payload = [pscustomobject]@{ raw = [string]$response.Content } }
    }
    return [pscustomobject]@{
        StatusCode = [int]$response.StatusCode
        Payload = $payload
    }
}

function Get-ErrorMessage {
    param([object]$Payload)
    if ($null -eq $Payload) { return '' }
    $errors = @(Get-PropertyValue -Object $Payload -Name 'errors')
    $messages = foreach ($errorItem in $errors) {
        if ($null -eq $errorItem) { continue }
        $message = Get-PropertyValue -Object $errorItem -Name 'message'
        $longMessage = Get-PropertyValue -Object $errorItem -Name 'longMessage'
        if (-not [string]::IsNullOrWhiteSpace([string]$longMessage)) { [string]$longMessage }
        elseif (-not [string]::IsNullOrWhiteSpace([string]$message)) { [string]$message }
    }
    return ($messages -join '; ')
}

function Get-Metric {
    param([object[]]$Metrics, [Parameter(Mandatory)][string]$MetricKey)
    return @($Metrics | Where-Object { (Get-PropertyValue -Object $_ -Name 'metricKey') -eq $MetricKey } | Select-Object -First 1)[0]
}

function Get-MarketplaceLabel {
    param([Parameter(Mandatory)][string]$MarketplaceId)
    switch ($MarketplaceId) {
        'EBAY_US' { '美国站' }
        'EBAY_GB' { '英国站' }
        'EBAY_DE' { '德国站' }
        'EBAY_FR' { '法国站' }
        'EBAY_IT' { '意大利站' }
        'EBAY_ES' { '西班牙站' }
        'EBAY_AU' { '澳大利亚站' }
        'EBAY_CA' { '加拿大站' }
        default { $MarketplaceId }
    }
}

function Get-ProgramLabel {
    param([Parameter(Mandatory)][string]$Program)
    switch ($Program) {
        'PROGRAM_US' { '美国站卖家标准' }
        'PROGRAM_UK' { '英国站卖家标准' }
        'PROGRAM_DE' { '德国站卖家标准' }
        'PROGRAM_GLOBAL' { '全球/其他站点卖家标准' }
        default { $Program }
    }
}

function Get-ServiceMetricLabel {
    param([Parameter(Mandatory)][string]$MetricType)
    switch ($MetricType) {
        'ITEM_NOT_AS_DESCRIBED' { '物品与描述不符率' }
        'ITEM_NOT_RECEIVED' { '物品未收到率' }
        default { $MetricType }
    }
}

function Get-StandardsMetricLabel {
    param([Parameter(Mandatory)][string]$MetricKey)
    switch ($MetricKey) {
        'DEFECTIVE_TRANSACTION_RATE' { '不良交易率' }
        'DEFECTIVE_TRANSACTION_COUNT' { '不良交易数量' }
        'CLAIMS_SAF_RATE' { '未经卖家解决的纠纷率' }
        'CLAIMS_SAF_COUNT' { '未经卖家解决的纠纷数量' }
        'SHIPPING_MISS_RATE' { '延迟发货率' }
        default { $MetricKey }
    }
}

function Get-IssueLabel {
    param([string]$IssueName)
    switch ($IssueName) {
        'ARRIVED_DAMAGED' { '到货时已损坏' }
        'NOT_AS_DESCRIBED' { '物品与描述不符' }
        'DEFECTIVE_ITEM' { '物品有缺陷' }
        'MISSING_PARTS' { '缺少零件' }
        'WRONG_ITEM' { '收到错误物品' }
        'ITEM_NOT_RECEIVED' { '物品未收到' }
        default { $IssueName }
    }
}

$clientSecret = $null
$refreshToken = $null
$accessToken = $null
$runtimeDir = $null

try {
    $resolvedEnvFile = [IO.Path]::GetFullPath($EnvFile)
    $resolvedTokenFile = [IO.Path]::GetFullPath($TokenFile)
    $resolvedOutputRoot = [IO.Path]::GetFullPath($OutputRoot)
    $clientId = Get-DotEnvValue -Path $resolvedEnvFile -Name 'EBAY_CLIENT_ID'
    $clientSecret = Get-DotEnvValue -Path $resolvedEnvFile -Name 'EBAY_CLIENT_SECRET'

    if (-not (Test-Path -LiteralPath $resolvedTokenFile -PathType Leaf)) {
        throw "加密 Refresh Token 文件不存在: $resolvedTokenFile"
    }
    $encryptedToken = Get-Content -Raw -LiteralPath $resolvedTokenFile
    $secureToken = ConvertTo-SecureString $encryptedToken
    $refreshToken = [System.Net.NetworkCredential]::new('', $secureToken).Password
    if ([string]::IsNullOrWhiteSpace($refreshToken)) { throw 'Refresh Token 解密结果为空' }

    $basic = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("${clientId}:${clientSecret}"))
    $tokenResult = Invoke-HttpJson -Method POST `
        -Uri 'https://api.ebay.com/identity/v1/oauth2/token' `
        -Headers @{ Authorization = "Basic $basic" } `
        -Body @{ grant_type = 'refresh_token'; refresh_token = $refreshToken }
    if ($tokenResult.StatusCode -ne 200) {
        throw "Access Token 刷新失败 (HTTP $($tokenResult.StatusCode)): $(Get-ErrorMessage $tokenResult.Payload)"
    }
    $accessToken = Get-PropertyValue -Object $tokenResult.Payload -Name 'access_token'
    if ([string]::IsNullOrWhiteSpace([string]$accessToken)) { throw 'eBay 刷新响应中没有 access_token' }
    Write-Host "[OK] Access Token 刷新成功，有效期 $((Get-PropertyValue $tokenResult.Payload 'expires_in')) 秒" -ForegroundColor Green

    $headers = @{
        Authorization = "Bearer $accessToken"
        Accept = 'application/json'
        'Accept-Language' = 'en-US'
    }

    $identityResult = Invoke-HttpJson -Method GET -Uri 'https://apiz.ebay.com/commerce/identity/v1/user/' -Headers $headers
    if ($identityResult.StatusCode -ne 200) {
        throw "eBay 身份接口失败 (HTTP $($identityResult.StatusCode)): $(Get-ErrorMessage $identityResult.Payload)"
    }
    $identity = $identityResult.Payload
    Write-Host "[OK] 卖家账号: $((Get-PropertyValue $identity 'username'))"

    $serviceMetricTypes = @('ITEM_NOT_AS_DESCRIBED', 'ITEM_NOT_RECEIVED')
    $rawServiceCalls = [Collections.Generic.List[object]]::new()
    $statusRows = [Collections.Generic.List[object]]::new()
    $summaryRows = [Collections.Generic.List[object]]::new()
    $detailRows = [Collections.Generic.List[object]]::new()

    foreach ($marketplaceId in $Marketplaces) {
        foreach ($evaluationType in $EvaluationTypes) {
            foreach ($metricType in $serviceMetricTypes) {
                $uri = 'https://api.ebay.com/sell/analytics/v1/customer_service_metric/{0}/{1}?evaluation_marketplace_id={2}' -f `
                    $metricType, $evaluationType, [Uri]::EscapeDataString($marketplaceId)
                $result = Invoke-HttpJson -Method GET -Uri $uri -Headers $headers
                $payload = $result.Payload
                $dimensions = @((Get-PropertyValue -Object $payload -Name 'dimensionMetrics') | Where-Object { $null -ne $_ })
                $errorMessage = Get-ErrorMessage -Payload $payload

                $rawServiceCalls.Add([pscustomobject][ordered]@{
                    request = [pscustomobject][ordered]@{
                        customerServiceMetricType = $metricType
                        evaluationType = $evaluationType
                        evaluationMarketplaceId = $marketplaceId
                        endpoint = $uri
                    }
                    statusCode = $result.StatusCode
                    response = $payload
                })
                $statusRows.Add([pscustomobject][ordered]@{
                    source = 'Customer Service Metrics API'
                    marketplaceId = $marketplaceId
                    marketplaceLabel = Get-MarketplaceLabel $marketplaceId
                    evaluationType = $evaluationType
                    metricType = $metricType
                    metricLabel = Get-ServiceMetricLabel $metricType
                    statusCode = $result.StatusCode
                    success = ($result.StatusCode -eq 200)
                    dimensionCount = $dimensions.Count
                    errorMessage = $errorMessage
                })

                if ($result.StatusCode -ne 200) {
                    Write-Host "[WARN] $marketplaceId $evaluationType $metricType -> HTTP $($result.StatusCode) $errorMessage" -ForegroundColor Yellow
                    continue
                }

                $cycle = Get-PropertyValue -Object $payload -Name 'evaluationCycle'
                $countTotal = 0.0
                $transactionTotal = 0.0
                $peerWeightedSum = 0.0
                $peerWeightTotal = 0.0
                $ratings = [Collections.Generic.List[string]]::new()

                foreach ($dimensionMetric in $dimensions) {
                    $dimension = Get-PropertyValue -Object $dimensionMetric -Name 'dimension'
                    $metrics = @((Get-PropertyValue -Object $dimensionMetric -Name 'metrics') | Where-Object { $null -ne $_ })
                    $rateMetric = Get-Metric -Metrics $metrics -MetricKey 'RATE'
                    $countMetric = Get-Metric -Metrics $metrics -MetricKey 'COUNT'
                    $transactionMetric = Get-Metric -Metrics $metrics -MetricKey 'TRANSACTION_COUNT'

                    $ratePercent = ConvertTo-NullableDouble (Get-PropertyValue -Object $rateMetric -Name 'value')
                    $count = ConvertTo-NullableDouble (Get-PropertyValue -Object $countMetric -Name 'value')
                    $transactionCount = ConvertTo-NullableDouble (Get-PropertyValue -Object $transactionMetric -Name 'value')
                    $benchmark = Get-PropertyValue -Object $rateMetric -Name 'benchmark'
                    $metadata = Get-PropertyValue -Object $benchmark -Name 'metadata'
                    $peerAveragePercent = ConvertTo-NullableDouble (Get-PropertyValue -Object $metadata -Name 'average')
                    $rating = [string](Get-PropertyValue -Object $benchmark -Name 'rating')

                    if ($null -ne $count) { $countTotal += $count }
                    if ($null -ne $transactionCount) { $transactionTotal += $transactionCount }
                    if ($null -ne $peerAveragePercent -and $null -ne $transactionCount -and $transactionCount -gt 0) {
                        $peerWeightedSum += ($peerAveragePercent / 100.0) * $transactionCount
                        $peerWeightTotal += $transactionCount
                    }
                    if (-not [string]::IsNullOrWhiteSpace($rating) -and -not $ratings.Contains($rating)) { $ratings.Add($rating) }

                    $baseDetail = [ordered]@{
                        marketplaceId = $marketplaceId
                        marketplaceLabel = Get-MarketplaceLabel $marketplaceId
                        evaluationType = $evaluationType
                        metricType = $metricType
                        metricLabel = Get-ServiceMetricLabel $metricType
                        dimensionKey = [string](Get-PropertyValue -Object $dimension -Name 'dimensionKey')
                        dimensionName = [string](Get-PropertyValue -Object $dimension -Name 'name')
                        dimensionValue = [string](Get-PropertyValue -Object $dimension -Name 'value')
                        currentRate = if ($null -eq $ratePercent) { $null } else { $ratePercent / 100.0 }
                        numerator = $count
                        denominator = $transactionCount
                        peerAverage = if ($null -eq $peerAveragePercent) { $null } else { $peerAveragePercent / 100.0 }
                        peerGap = if ($null -eq $ratePercent -or $null -eq $peerAveragePercent) { $null } else { ($ratePercent - $peerAveragePercent) / 100.0 }
                        rating = $rating
                        benchmarkBasis = [string](Get-PropertyValue -Object $benchmark -Name 'basis')
                        benchmarkAdjustment = [string](Get-PropertyValue -Object $benchmark -Name 'adjustment')
                        evaluationDate = [string](Get-PropertyValue -Object $cycle -Name 'evaluationDate')
                        lookbackStartDate = [string](Get-PropertyValue -Object $cycle -Name 'startDate')
                        lookbackEndDate = [string](Get-PropertyValue -Object $cycle -Name 'endDate')
                    }

                    $distributionRowsAdded = 0
                    $distributions = @((Get-PropertyValue -Object $countMetric -Name 'distributions') | Where-Object { $null -ne $_ })
                    foreach ($distribution in $distributions) {
                        $distributionBasis = [string](Get-PropertyValue -Object $distribution -Name 'basis')
                        $distributionData = @((Get-PropertyValue -Object $distribution -Name 'data') | Where-Object { $null -ne $_ })
                        foreach ($distributionItem in $distributionData) {
                            $issueName = [string](Get-PropertyValue -Object $distributionItem -Name 'name')
                            $issueCount = ConvertTo-NullableDouble (Get-PropertyValue -Object $distributionItem -Name 'value')
                            $row = [ordered]@{}
                            foreach ($key in $baseDetail.Keys) { $row[$key] = $baseDetail[$key] }
                            $row.distributionBasis = $distributionBasis
                            $row.issueName = $issueName
                            $row.issueLabel = Get-IssueLabel $issueName
                            $row.issueCount = $issueCount
                            $row.issueShare = if ($null -eq $issueCount -or $null -eq $count -or $count -eq 0) { $null } else { $issueCount / $count }
                            $detailRows.Add([pscustomobject]$row)
                            $distributionRowsAdded++
                        }
                    }
                    if ($distributionRowsAdded -eq 0) {
                        $row = [ordered]@{}
                        foreach ($key in $baseDetail.Keys) { $row[$key] = $baseDetail[$key] }
                        $row.distributionBasis = ''
                        $row.issueName = ''
                        $row.issueLabel = ''
                        $row.issueCount = $null
                        $row.issueShare = $null
                        $detailRows.Add([pscustomobject]$row)
                    }
                }

                $currentRate = if ($transactionTotal -gt 0) { $countTotal / $transactionTotal } else { $null }
                $peerAverage = if ($peerWeightTotal -gt 0) { $peerWeightedSum / $peerWeightTotal } else { $null }
                $summaryRows.Add([pscustomobject][ordered]@{
                    marketplaceId = $marketplaceId
                    marketplaceLabel = Get-MarketplaceLabel $marketplaceId
                    evaluationType = $evaluationType
                    metricKey = $metricType
                    metricLabel = Get-ServiceMetricLabel $metricType
                    currentValue = $currentRate
                    valueUnit = 'PERCENT'
                    numerator = $countTotal
                    denominator = $transactionTotal
                    peerAverage = $peerAverage
                    peerGap = if ($null -eq $currentRate -or $null -eq $peerAverage) { $null } else { $currentRate - $peerAverage }
                    rating = if ($ratings.Count -eq 1) { $ratings[0] } elseif ($ratings.Count -gt 1) { '见问题细分' } else { '' }
                    policyThreshold = $null
                    scopeNote = '当前值按接口返回维度的分子/分母汇总；同业平均按有基准的维度交易量加权'
                    evaluationDate = [string](Get-PropertyValue -Object $cycle -Name 'evaluationDate')
                    lookbackStartDate = [string](Get-PropertyValue -Object $cycle -Name 'startDate')
                    lookbackEndDate = [string](Get-PropertyValue -Object $cycle -Name 'endDate')
                    source = 'Customer Service Metrics API'
                })
                Write-Host "[OK] $marketplaceId $evaluationType $metricType -> $($dimensions.Count) 个细分"
            }
        }
    }

    $standardsUri = 'https://api.ebay.com/sell/analytics/v1/seller_standards_profile'
    $standardsResult = Invoke-HttpJson -Method GET -Uri $standardsUri -Headers $headers
    $standardsError = Get-ErrorMessage -Payload $standardsResult.Payload
    $standardsProfiles = @((Get-PropertyValue -Object $standardsResult.Payload -Name 'standardsProfiles') | Where-Object { $null -ne $_ })
    $statusRows.Add([pscustomobject][ordered]@{
        source = 'Seller Standards Profile API'
        marketplaceId = 'ALL_PROGRAMS'
        marketplaceLabel = '全部卖家标准区域'
        evaluationType = 'CURRENT+PROJECTED'
        metricType = 'SELLER_STANDARDS'
        metricLabel = '卖家标准指标'
        statusCode = $standardsResult.StatusCode
        success = ($standardsResult.StatusCode -eq 200)
        dimensionCount = $standardsProfiles.Count
        errorMessage = $standardsError
    })

    if ($standardsResult.StatusCode -eq 200) {
        $includedStandardsMetrics = @(
            'DEFECTIVE_TRANSACTION_RATE', 'DEFECTIVE_TRANSACTION_COUNT',
            'CLAIMS_SAF_RATE', 'CLAIMS_SAF_COUNT', 'SHIPPING_MISS_RATE'
        )
        foreach ($profile in $standardsProfiles) {
            $cycle = Get-PropertyValue -Object $profile -Name 'cycle'
            $cycleType = [string](Get-PropertyValue -Object $cycle -Name 'cycleType')
            if ($cycleType -notin $EvaluationTypes) { continue }
            $program = [string](Get-PropertyValue -Object $profile -Name 'program')
            $standardsLevel = [string](Get-PropertyValue -Object $profile -Name 'standardsLevel')
            foreach ($metric in @((Get-PropertyValue -Object $profile -Name 'metrics') | Where-Object { $null -ne $_ })) {
                $metricKey = [string](Get-PropertyValue -Object $metric -Name 'metricKey')
                if ($metricKey -notin $includedStandardsMetrics) { continue }
                $metricType = [string](Get-PropertyValue -Object $metric -Name 'type')
                $metricValue = Get-PropertyValue -Object $metric -Name 'value'
                $thresholdUpper = Get-PropertyValue -Object $metric -Name 'thresholdUpperBound'

                $currentValue = $null
                $numerator = $null
                $denominator = $null
                $policyThreshold = $null
                $valueUnit = 'COUNT'
                if ($metricType -eq 'RATE') {
                    $currentValuePercent = ConvertTo-NullableDouble (Get-PropertyValue -Object $metricValue -Name 'value')
                    $currentValue = if ($null -eq $currentValuePercent) { $null } else { $currentValuePercent / 100.0 }
                    $numerator = ConvertTo-NullableDouble (Get-PropertyValue -Object $metricValue -Name 'numerator')
                    $denominator = ConvertTo-NullableDouble (Get-PropertyValue -Object $metricValue -Name 'denominator')
                    $thresholdPercent = ConvertTo-NullableDouble (Get-PropertyValue -Object $thresholdUpper -Name 'value')
                    $policyThreshold = if ($null -eq $thresholdPercent) { $null } else { $thresholdPercent / 100.0 }
                    $valueUnit = 'PERCENT'
                }
                else {
                    $currentValue = ConvertTo-NullableDouble $metricValue
                    $policyThreshold = ConvertTo-NullableDouble $thresholdUpper
                }

                $summaryRows.Add([pscustomobject][ordered]@{
                    marketplaceId = $program
                    marketplaceLabel = Get-ProgramLabel $program
                    evaluationType = $cycleType
                    metricKey = $metricKey
                    metricLabel = Get-StandardsMetricLabel $metricKey
                    currentValue = $currentValue
                    valueUnit = $valueUnit
                    numerator = $numerator
                    denominator = $denominator
                    peerAverage = $null
                    peerGap = $null
                    rating = if ([string]::IsNullOrWhiteSpace([string](Get-PropertyValue -Object $metric -Name 'level'))) { $standardsLevel } else { [string](Get-PropertyValue -Object $metric -Name 'level') }
                    policyThreshold = $policyThreshold
                    scopeNote = 'eBay 卖家标准；该接口不返回同业平均值'
                    evaluationDate = [string](Get-PropertyValue -Object $cycle -Name 'evaluationDate')
                    lookbackStartDate = [string](Get-PropertyValue -Object $metric -Name 'lookbackStartDate')
                    lookbackEndDate = [string](Get-PropertyValue -Object $metric -Name 'lookbackEndDate')
                    source = 'Seller Standards Profile API'
                })
            }
        }
        Write-Host "[OK] Seller Standards -> $($standardsProfiles.Count) 个区域/周期档案"
    }
    else {
        Write-Host "[WARN] Seller Standards -> HTTP $($standardsResult.StatusCode) $standardsError" -ForegroundColor Yellow
    }

    $coverageRows = @(
        [pscustomobject]@{ requestedMetric = '不良交易率'; availability = '可获取'; source = 'Seller Standards Profile API'; note = '按卖家标准区域返回；无同业平均值' },
        [pscustomobject]@{ requestedMetric = '物品与描述不符退货率'; availability = '可获取'; source = 'Customer Service Metrics API'; note = '按一级品类返回当前值、同业平均和原因分布' },
        [pscustomobject]@{ requestedMetric = '物品未收到纠纷率'; availability = '可获取'; source = 'Customer Service Metrics API'; note = '按收货地区返回当前值和同业平均' },
        [pscustomobject]@{ requestedMetric = '未经卖家解决的纠纷率'; availability = '可获取'; source = 'Seller Standards Profile API'; note = '公开接口字段 CLAIMS_SAF_RATE；不要与其他履约口径混同' },
        [pscustomobject]@{ requestedMetric = '中差评率'; availability = '公开 Analytics API 未返回'; source = ''; note = '本次不造数，保留为接口缺口' },
        [pscustomobject]@{ requestedMetric = '详细卖家评分低分率'; availability = '公开 Analytics API 未返回'; source = ''; note = '本次不造数，保留为接口缺口' },
        [pscustomobject]@{ requestedMetric = '卖家责任未履约交易率'; availability = '无完全同名公开指标'; source = 'Seller Standards Profile API'; note = '最接近字段为未经卖家解决的纠纷率，但不能视为完全相同' }
    )

    $timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $outputDir = Join-Path $resolvedOutputRoot $timestamp
    New-Item -ItemType Directory -Path $outputDir -Force | Out-Null

    $rawPath = Join-Path $outputDir 'ebay-seller-performance.raw.json'
    $normalizedPath = Join-Path $outputDir 'ebay-seller-performance.normalized.json'
    $summaryCsvPath = Join-Path $outputDir 'ebay-seller-performance-summary.csv'
    $detailCsvPath = Join-Path $outputDir 'ebay-seller-performance-details.csv'
    $statusCsvPath = Join-Path $outputDir 'ebay-seller-performance-api-status.csv'
    $xlsxPath = Join-Path $outputDir 'ebay-seller-performance.xlsx'

    $rawDocument = [pscustomobject][ordered]@{
        exportedAtUtc = [DateTime]::UtcNow.ToString('o')
        account = [pscustomobject][ordered]@{
            userId = Get-PropertyValue -Object $identity -Name 'userId'
            username = Get-PropertyValue -Object $identity -Name 'username'
            accountType = Get-PropertyValue -Object $identity -Name 'accountType'
            registrationMarketplaceId = Get-PropertyValue -Object $identity -Name 'registrationMarketplaceId'
        }
        customerServiceMetricCalls = $rawServiceCalls
        sellerStandardsCall = [pscustomobject][ordered]@{
            request = [pscustomobject][ordered]@{ endpoint = $standardsUri }
            statusCode = $standardsResult.StatusCode
            response = $standardsResult.Payload
        }
    }
    $rawDocument | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $rawPath -Encoding utf8NoBOM

    $normalizedDocument = [pscustomobject][ordered]@{
        metadata = [pscustomobject][ordered]@{
            exportedAtUtc = $rawDocument.exportedAtUtc
            username = Get-PropertyValue -Object $identity -Name 'username'
            registrationMarketplaceId = Get-PropertyValue -Object $identity -Name 'registrationMarketplaceId'
            requestedMarketplaces = $Marketplaces
            requestedEvaluationTypes = $EvaluationTypes
        }
        summaryRows = $summaryRows
        detailRows = $detailRows
        statusRows = $statusRows
        coverageRows = $coverageRows
    }
    $normalizedDocument | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $normalizedPath -Encoding utf8NoBOM

    $summaryRows | ForEach-Object {
        [pscustomobject][ordered]@{
            '站点' = $_.marketplaceLabel
            '站点代码' = $_.marketplaceId
            '评估周期' = $_.evaluationType
            '项目' = $_.metricLabel
            '项目代码' = $_.metricKey
            '当前值_pct' = if ($_.valueUnit -eq 'PERCENT' -and $null -ne $_.currentValue) { [math]::Round($_.currentValue * 100, 6) } else { $null }
            '当前值_count' = if ($_.valueUnit -eq 'COUNT') { $_.currentValue } else { $null }
            '分子' = $_.numerator
            '分母' = $_.denominator
            '同业平均_pct' = if ($null -ne $_.peerAverage) { [math]::Round($_.peerAverage * 100, 6) } else { $null }
            '高于同业_百分点' = if ($null -ne $_.peerGap) { [math]::Round($_.peerGap * 100, 6) } else { $null }
            '评级' = $_.rating
            '政策阈值_pct或count' = if ($null -ne $_.policyThreshold) { if ($_.valueUnit -eq 'PERCENT') { [math]::Round($_.policyThreshold * 100, 6) } else { $_.policyThreshold } } else { $null }
            '口径说明' = $_.scopeNote
            '评估时间' = $_.evaluationDate
            '统计开始' = $_.lookbackStartDate
            '统计结束' = $_.lookbackEndDate
            '数据源' = $_.source
        }
    } | Export-Csv -LiteralPath $summaryCsvPath -NoTypeInformation -Encoding utf8BOM -UseQuotes AsNeeded

    $detailRows | ForEach-Object {
        [pscustomobject][ordered]@{
            '站点' = $_.marketplaceLabel
            '站点代码' = $_.marketplaceId
            '评估周期' = $_.evaluationType
            '项目' = $_.metricLabel
            '项目代码' = $_.metricType
            '细分类型' = $_.dimensionKey
            '细分名称' = $_.dimensionName
            '细分值' = $_.dimensionValue
            '当前值_pct' = if ($null -ne $_.currentRate) { [math]::Round($_.currentRate * 100, 6) } else { $null }
            '分子' = $_.numerator
            '分母' = $_.denominator
            '同业平均_pct' = if ($null -ne $_.peerAverage) { [math]::Round($_.peerAverage * 100, 6) } else { $null }
            '高于同业_百分点' = if ($null -ne $_.peerGap) { [math]::Round($_.peerGap * 100, 6) } else { $null }
            'eBay评级' = $_.rating
            '问题分布口径' = $_.distributionBasis
            '问题代码' = $_.issueName
            '问题细分' = $_.issueLabel
            '问题数量' = $_.issueCount
            '问题占该项目' = if ($null -ne $_.issueShare) { [math]::Round($_.issueShare, 6) } else { $null }
            '基准调整' = $_.benchmarkAdjustment
            '评估时间' = $_.evaluationDate
            '统计开始' = $_.lookbackStartDate
            '统计结束' = $_.lookbackEndDate
        }
    } | Export-Csv -LiteralPath $detailCsvPath -NoTypeInformation -Encoding utf8BOM -UseQuotes AsNeeded

    $statusRows | Select-Object source, marketplaceLabel, marketplaceId, evaluationType, metricLabel, metricType, statusCode, success, dimensionCount, errorMessage |
        Export-Csv -LiteralPath $statusCsvPath -NoTypeInformation -Encoding utf8BOM -UseQuotes AsNeeded

    if (-not $SkipExcel) {
        if ([string]::IsNullOrWhiteSpace($NodePath) -or -not (Test-Path -LiteralPath $NodePath -PathType Leaf)) {
            throw '生成 Excel 需要通过 -NodePath 传入 load_workspace_dependencies 返回的 Node.js 路径'
        }
        if ([string]::IsNullOrWhiteSpace($ArtifactNodeModulesPath) -or -not (Test-Path -LiteralPath $ArtifactNodeModulesPath -PathType Container)) {
            throw '生成 Excel 需要通过 -ArtifactNodeModulesPath 传入 load_workspace_dependencies 返回的 node_modules 路径'
        }
        $builderSource = Join-Path $PSScriptRoot 'build_ebay_seller_performance_workbook.mjs'
        if (-not (Test-Path -LiteralPath $builderSource -PathType Leaf)) { throw "Excel 生成器不存在: $builderSource" }

        $runtimeDir = Join-Path $outputDir '.artifact-runtime'
        New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
        $runtimeBuilder = Join-Path $runtimeDir 'build.mjs'
        Copy-Item -LiteralPath $builderSource -Destination $runtimeBuilder -Force
        $nodeModulesLink = Join-Path $runtimeDir 'node_modules'
        New-Item -ItemType Junction -Path $nodeModulesLink -Target ([IO.Path]::GetFullPath($ArtifactNodeModulesPath)) | Out-Null
        $previewDir = Join-Path $outputDir '.previews'
        & ([IO.Path]::GetFullPath($NodePath)) $runtimeBuilder $normalizedPath $xlsxPath $previewDir
        if ($LASTEXITCODE -ne 0) { throw "Excel 生成失败，Node 退出码: $LASTEXITCODE" }

        $resolvedRuntime = [IO.Path]::GetFullPath($runtimeDir)
        $resolvedOutput = [IO.Path]::GetFullPath($outputDir)
        if ($resolvedRuntime.StartsWith($resolvedOutput, [StringComparison]::OrdinalIgnoreCase)) {
            if (Test-Path -LiteralPath $nodeModulesLink) { Remove-Item -LiteralPath $nodeModulesLink -Force }
            if (Test-Path -LiteralPath $runtimeBuilder) { Remove-Item -LiteralPath $runtimeBuilder -Force }
            Remove-Item -LiteralPath $runtimeDir -Force
        }
    }

    $successCalls = @($statusRows | Where-Object { $_.success }).Count
    $failedCalls = @($statusRows | Where-Object { -not $_.success }).Count
    Write-Host "`n[PASS] eBay 卖家绩效导出完成" -ForegroundColor Green
    Write-Host "输出目录: $outputDir"
    Write-Host "成功接口: $successCalls；失败/无数据接口: $failedCalls"
    Write-Host "总览行数: $($summaryRows.Count)；问题细分行数: $($detailRows.Count)"
    Write-Output ([pscustomobject][ordered]@{
        outputDir = $outputDir
        rawJson = $rawPath
        normalizedJson = $normalizedPath
        summaryCsv = $summaryCsvPath
        detailsCsv = $detailCsvPath
        apiStatusCsv = $statusCsvPath
        excel = if ($SkipExcel) { $null } else { $xlsxPath }
        summaryRowCount = $summaryRows.Count
        detailRowCount = $detailRows.Count
        successfulApiCalls = $successCalls
        failedApiCalls = $failedCalls
    })
}
finally {
    $clientSecret = $null
    $refreshToken = $null
    $accessToken = $null
}
