$ErrorActionPreference = "Continue"

$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$env:AI4BINANCE_ALLOW_AUTO_LIVE_ORDERS = "false"
$env:AI4BINANCE_ADVISORY_LLM_MODE = "RESEARCH_ONLY"
$model = $(if ($env:AI4BINANCE_PROMPTER_MODEL) { $env:AI4BINANCE_PROMPTER_MODEL } else { "qwen3:8b" })
$env:OLLAMA_HOST = $(if ($env:OLLAMA_HOST) { $env:OLLAMA_HOST } else { "127.0.0.1:11434" })

$ollama = (Get-Command ollama -ErrorAction SilentlyContinue).Source
if (-not $ollama) {
    [pscustomobject]@{
        provider = "ollama"
        status = "BLOCKED"
        model = $model
        blockers = @("OLLAMA_UNAVAILABLE")
        execution_allowed = $false
        live_eligibility_status = "LIVE_ORDER_BLOCKED"
    } | ConvertTo-Json -Compress
    exit 2
}

$portOpen = Get-NetTCPConnection `
    -LocalAddress 127.0.0.1 `
    -LocalPort 11434 `
    -ErrorAction SilentlyContinue
if (-not $portOpen) {
    Start-Process -FilePath $ollama -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 5
}

try {
    $tags = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 10
    $modelNames = @($tags.models | ForEach-Object { $_.name })
    if ($modelNames -notcontains $model) {
        throw "Required Ollama model is unavailable: $model"
    }
    [pscustomobject]@{
        provider = "ollama"
        endpoint = "http://127.0.0.1:11434/api/generate"
        model = $model
        status = "READY"
        blockers = @()
        execution_allowed = $false
        live_eligibility_status = "LIVE_ORDER_BLOCKED"
    } | ConvertTo-Json -Compress
    exit 0
}
catch {
    [pscustomobject]@{
        provider = "ollama"
        status = "BLOCKED"
        model = $model
        blockers = @("OLLAMA_OR_QWEN3_8B_UNAVAILABLE")
        execution_allowed = $false
        live_eligibility_status = "LIVE_ORDER_BLOCKED"
    } | ConvertTo-Json -Compress
    exit 2
}
