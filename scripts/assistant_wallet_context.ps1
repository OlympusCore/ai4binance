function Get-AI4BinanceAssistantMessages {
    param([string]$Culture = "tr-TR")

    if ($Culture -ne "tr-TR") {
        throw "ASSISTANT_CULTURE_UNSUPPORTED"
    }

    return [ordered]@{
        AccountUnavailable = "Dogrulanmis ve guncel yerel cuzdan verisi yok; bu nedenle mevcut durum, deger veya firsat hakkinda kesin bilgi veremem."
        Definition = 'Hayir; "binance_wallet" AI4Binance icinde kanonik bir bilesen adi degil. Dogrulanan yapi salt okunur Binance Spot cuzdan snapshotidir; son snapshot {0} itibariyla {1}.'
        Status = "Son dogrulanmis Binance Spot cuzdan snapshoti {0} itibariyla {1}; toplam portfoy degeri {2} USDT."
        StatusWithoutValue = "Son dogrulanmis Binance Spot cuzdan snapshoti {0} itibariyla {1}; toplam portfoy degeri bu snapshotta yok."
        Value = "Son dogrulanmis cuzdan snapshoti {0}: toplam portfoy degeri {1} USDT. Bu, yerel salt okunur snapshot degeridir."
        ValueUnavailable = "Cuzdan snapshoti guncel, ancak toplam portfoy degeri dogrulanamadi."
        Contents = "Son dogrulanmis snapshotta pozitif bakiyeli {0} varlik var: {1}. Bireysel bakiyeler bu sohbet ozetinde gosterilmez."
        ContentsEmpty = "Son dogrulanmis snapshotta pozitif bakiyeli varlik kaydi yok."
        Opportunity = "Cuzdanin kendisi bir firsat degildir. Son dogrulanmis snapshotta {0} research-only izleme adayi var; yurutulebilir firsat yok ve canli emir yetkisi kapali."
        Ready = "hazir"
        Blocked = "engelli"
        Degraded = "kisitli"
        Unknown = "bilinmiyor"
    }
}

function ConvertTo-AI4BinanceSearchText {
    param([Parameter(Mandatory = $true)][string]$Text)

    $dotlessLowerI = [string][char]0x0131
    $normalized = $Text.Trim().ToLowerInvariant().Replace($dotlessLowerI, "i")
    $decomposed = $normalized.Normalize([Text.NormalizationForm]::FormD)
    $builder = [Text.StringBuilder]::new()
    foreach ($character in $decomposed.ToCharArray()) {
        $category = [Globalization.CharUnicodeInfo]::GetUnicodeCategory($character)
        if ($category -ne [Globalization.UnicodeCategory]::NonSpacingMark) {
            [void]$builder.Append($character)
        }
    }
    return $builder.ToString().Normalize([Text.NormalizationForm]::FormC)
}

function Test-AI4BinanceWalletQuery {
    param(
        [Parameter(Mandatory = $true)][string]$InputText,
        [string]$ContextText = ""
    )

    $normalized = ConvertTo-AI4BinanceSearchText -Text $InputText
    $context = ConvertTo-AI4BinanceSearchText -Text $ContextText
    $walletPattern = "(?:binan(?:ce)?[\\_\s-]*wallet|wallet|cuzdan|bakiye|portfoy)"
    if ($normalized -match $walletPattern) {
        return $true
    }

    $followUpPattern = "(?:ne\s+icer|neler\s+var|su\s*an|guncel|deger|firsat|dalga|sacma|cevap)"
    return $normalized -match $followUpPattern -and $context -match $walletPattern
}

function Get-AI4BinanceWalletQueryKind {
    param([Parameter(Mandatory = $true)][string]$InputText)

    $normalized = ConvertTo-AI4BinanceSearchText -Text $InputText
    if ($normalized -match "(?:firsat|opportunity|setup)") {
        return "OPPORTUNITY"
    }
    if ($normalized -match "(?:deger|bakiye|toplam|ne\s+kadar|kac)") {
        return "VALUE"
    }
    if ($normalized -match "(?:ne\s+icer|neler\s+var|envanter|varlik)") {
        return "CONTENTS"
    }
    if ($normalized -match "(?:tanimli|defined|mevcut\s+mi|var\s+mi)") {
        return "DEFINITION"
    }
    return "STATUS"
}

function ConvertTo-AI4BinanceDateTimeOffset {
    param([Parameter(Mandatory = $true)][object]$Value)

    if ($Value -is [DateTimeOffset]) {
        return [DateTimeOffset]$Value
    }
    if ($Value -is [DateTime]) {
        $dateTime = [DateTime]$Value
        if ($dateTime.Kind -eq [DateTimeKind]::Unspecified) {
            throw "PRIVATE_ACCOUNT_STATE_TIMESTAMP_INVALID"
        }
        return [DateTimeOffset]$dateTime
    }

    $text = [string]$Value
    if ([string]::IsNullOrWhiteSpace($text) -or $text -notmatch "(?:Z|[+-]\d{2}:\d{2})$") {
        throw "PRIVATE_ACCOUNT_STATE_TIMESTAMP_INVALID"
    }
    $parsed = [DateTimeOffset]::MinValue
    if (-not [DateTimeOffset]::TryParse($text, [ref]$parsed)) {
        throw "PRIVATE_ACCOUNT_STATE_TIMESTAMP_INVALID"
    }
    return $parsed
}

function Read-AI4BinanceVerifiedAccountState {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [DateTimeOffset]$Now = [DateTimeOffset]::UtcNow,
        [int]$MaxAgeSeconds = 180,
        [int]$FutureToleranceSeconds = 30,
        [int]$MaxBytes = 2000000
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "PRIVATE_ACCOUNT_STATE_UNAVAILABLE"
    }
    $item = Get-Item -LiteralPath $Path -ErrorAction Stop
    if ($item.Length -gt $MaxBytes) {
        throw "PRIVATE_ACCOUNT_STATE_TOO_LARGE"
    }
    $raw = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 -ErrorAction Stop
    if ($raw.Contains("BINANCE_API_KEY") -or $raw.Contains("BINANCE_API_SECRET")) {
        throw "PRIVATE_ACCOUNT_STATE_FORBIDDEN_FIELDS"
    }
    try {
        $payload = $raw | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        throw "PRIVATE_ACCOUNT_STATE_INVALID_JSON"
    }
    if ($payload -isnot [System.Management.Automation.PSCustomObject]) {
        throw "PRIVATE_ACCOUNT_STATE_INVALID_SHAPE"
    }
    if ($payload.execution_allowed -isnot [bool] -or $payload.execution_allowed) {
        throw "PRIVATE_ACCOUNT_STATE_EXECUTION_AUTHORITY_INVALID"
    }
    if ([string]$payload.live_eligibility_status -ne "LIVE_ORDER_BLOCKED") {
        throw "PRIVATE_ACCOUNT_STATE_LIVE_AUTHORITY_INVALID"
    }

    $createdAt = ConvertTo-AI4BinanceDateTimeOffset -Value $payload.created_at
    $ageSeconds = ($Now.ToUniversalTime() - $createdAt.ToUniversalTime()).TotalSeconds
    if ($ageSeconds -lt (-1 * $FutureToleranceSeconds)) {
        throw "PRIVATE_ACCOUNT_STATE_TIMESTAMP_FUTURE"
    }
    if ($ageSeconds -gt $MaxAgeSeconds) {
        throw "PRIVATE_ACCOUNT_STATE_STALE"
    }
    return $payload
}

function Get-AI4BinanceWalletStatusLabel {
    param(
        [Parameter(Mandatory = $true)][string]$Status,
        [Parameter(Mandatory = $true)][System.Collections.IDictionary]$Messages
    )

    switch ($Status.Trim().ToUpperInvariant()) {
        "READY" { return $Messages.Ready }
        "BLOCKED" { return $Messages.Blocked }
        "DEGRADED" { return $Messages.Degraded }
        default { return $Messages.Unknown }
    }
}

function Get-AI4BinanceWalletAnswer {
    param(
        [Parameter(Mandatory = $true)][string]$InputText,
        [string]$ContextText = "",
        [Parameter(Mandatory = $true)][string]$StatePath,
        [DateTimeOffset]$Now = [DateTimeOffset]::UtcNow
    )

    if (-not (Test-AI4BinanceWalletQuery -InputText $InputText -ContextText $ContextText)) {
        return [pscustomobject]@{
            handled = $false
            evidence_status = "NOT_APPLICABLE"
            query_kind = "NONE"
            message = ""
        }
    }

    $messages = Get-AI4BinanceAssistantMessages
    $queryKind = Get-AI4BinanceWalletQueryKind -InputText $InputText
    try {
        $payload = Read-AI4BinanceVerifiedAccountState -Path $StatePath -Now $Now
    }
    catch {
        return [pscustomobject]@{
            handled = $true
            evidence_status = "DATA_UNAVAILABLE"
            query_kind = $queryKind
            message = $messages.AccountUnavailable
        }
    }

    $createdAt = ConvertTo-AI4BinanceDateTimeOffset -Value $payload.created_at
    $istanbulOffset = [TimeSpan]::FromHours(3)
    $observedAt = $createdAt.ToOffset($istanbulOffset).ToString("yyyy-MM-dd HH:mm:ss zzz")
    $walletStatus = Get-AI4BinanceWalletStatusLabel -Status ([string]$payload.spot.wallet_status) -Messages $messages
    $totalValueText = [string]$payload.portfolio_analytics.total_value_usdt
    $totalValue = [decimal]::Zero
    $totalValueKnown = $false
    try {
        $totalValue = [decimal]::Parse(
            $totalValueText,
            [System.Globalization.NumberStyles]::Float,
            [System.Globalization.CultureInfo]::InvariantCulture
        )
        $totalValueKnown = $totalValue -ge [decimal]::Zero
    }
    catch {
        $totalValueKnown = $false
    }
    $formattedValue = if ($totalValueKnown) {
        $totalValue.ToString("0.00", [System.Globalization.CultureInfo]::InvariantCulture)
    }
    else {
        ""
    }

    $message = switch ($queryKind) {
        "DEFINITION" {
            $messages.Definition -f $observedAt, $walletStatus
        }
        "VALUE" {
            if ($totalValueKnown) {
                $messages.Value -f $observedAt, $formattedValue
            }
            else {
                $messages.ValueUnavailable
            }
        }
        "CONTENTS" {
            $assets = @(
                @($payload.inventory) |
                    ForEach-Object { [string]$_.asset } |
                    Where-Object { $_ -match "^[A-Z0-9]{2,20}$" } |
                    Sort-Object -Unique
            )
            if ($assets.Count -gt 0) {
                $messages.Contents -f $assets.Count, ($assets -join ", ")
            }
            else {
                $messages.ContentsEmpty
            }
        }
        "OPPORTUNITY" {
            $watchCandidates = @(
                @($payload.investment_management.recommendations) |
                    Where-Object {
                        [string]$_.category -eq "NEW_OPPORTUNITY" -and
                        [string]$_.action -eq "WATCHLIST" -and
                        $_.execution_allowed -eq $false
                    }
            )
            $messages.Opportunity -f $watchCandidates.Count
        }
        default {
            if ($totalValueKnown) {
                $messages.Status -f $observedAt, $walletStatus, $formattedValue
            }
            else {
                $messages.StatusWithoutValue -f $observedAt, $walletStatus
            }
        }
    }

    return [pscustomobject]@{
        handled = $true
        evidence_status = "VERIFIED_LOCAL_SNAPSHOT"
        query_kind = $queryKind
        message = [string]$message
    }
}

function Format-AI4BinanceAssistantAnswer {
    param([Parameter(Mandatory = $true)][string]$Answer)

    $normalized = $Answer.Trim()
    $normalized = [regex]::Replace(
        $normalized,
        "^(?is)\s*(?:(?:###\s*)?(?:assistant|asistan)\s*:\s*)+",
        ""
    )
    $turkeyMarker = [char]::ConvertFromUtf32(0x1F1F9) + [char]::ConvertFromUtf32(0x1F1F7)
    $alphaMarker = [string][char]0x03B1
    $lines = [System.Collections.Generic.List[string]]::new()
    foreach ($line in @($normalized -split "\r?\n")) {
        $lines.Add([string]$line)
    }
    while ($lines.Count -gt 0) {
        $marker = $lines[0].Trim().TrimEnd(":").Trim()
        if ($marker -notin @("", $turkeyMarker, $alphaMarker)) {
            break
        }
        $lines.RemoveAt(0)
    }
    $normalized = ($lines -join [Environment]::NewLine).Trim()
    $normalized = [regex]::Replace(
        $normalized,
        "(?im)\s*\[Europe/Istanbul time:\s*[^\]]+\]\s*$",
        ""
    ).Trim()
    if ([string]::IsNullOrWhiteSpace($normalized)) {
        throw "LOCAL_LLM_EMPTY_RESPONSE_AFTER_NORMALIZATION"
    }
    return $normalized
}
