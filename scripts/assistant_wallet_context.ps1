# Windows transport adapter for the canonical Python assistant.
function Invoke-AI4BinanceAssistantRequest {
    param([Parameter(Mandatory = $true)][System.Collections.IDictionary]$Request)
    $repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
    $python = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
    $previousPythonPath = $env:PYTHONPATH
    $previousEncoding = $OutputEncoding
    try {
        $Request["schema_version"] = "AssistantRequest/v1"
        $env:PYTHONPATH = Join-Path $repositoryRoot "src"
        $OutputEncoding = [System.Text.UTF8Encoding]::new($false)
        $json = $Request | ConvertTo-Json -Depth 30 -Compress
        $response = $json | & $python -B -m ai4binance.local_agent.assistant_context
        if ($LASTEXITCODE -ne 0) { throw "ASSISTANT_REQUEST_FAILED" }
        return ($response | ConvertFrom-Json).result
    }
    finally {
        $env:PYTHONPATH = $previousPythonPath
        $OutputEncoding = $previousEncoding
    }
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


function Add-AI4BinanceAssistantHistory {
    param([object]$Messages, [string]$Role, [string]$Content, [int]$MaxTurns)
    $retained = Invoke-AI4BinanceAssistantRequest @{
        operation = "append_history"; messages = @($Messages); role = $Role
        content = $Content; max_turns = $MaxTurns
    }
    $Messages.Clear()
    foreach ($item in $retained) { $Messages.Add($item) }
}

function Get-AI4BinanceWalletAnswer {
    param(
        [Parameter(Mandatory = $true)][string]$InputText,
        [string]$ContextText = "",
        [Parameter(Mandatory = $true)][string]$StatePath,
        [DateTimeOffset]$Now = [DateTimeOffset]::UtcNow
    )
    return Invoke-AI4BinanceAssistantRequest @{
        operation = "wallet_answer"; input_text = $InputText
        context_text = $ContextText; state_path = $StatePath; now = $Now.ToString("o")
    }
}

function Format-AI4BinanceAssistantAnswer {
    param([Parameter(Mandatory = $true)][string]$Answer)
    return Invoke-AI4BinanceAssistantRequest @{ operation = "format_answer"; answer = $Answer }
}
