$ErrorActionPreference = "Continue"

$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$env:AI4BINANCE_ALLOW_AUTO_LIVE_ORDERS = "false"
$env:AI4BINANCE_ADVISORY_LLM_MODE = "RESEARCH_ONLY"

$llamaPortOpen = Get-NetTCPConnection `
    -LocalAddress 127.0.0.1 `
    -LocalPort 8080 `
    -ErrorAction SilentlyContinue
if ($llamaPortOpen) {
    [pscustomobject]@{
        provider = "llama.cpp"
        endpoint = "http://127.0.0.1:8080/completion"
        status = "READY"
        execution_allowed = $false
        live_eligibility_status = "LIVE_ORDER_BLOCKED"
    } | ConvertTo-Json -Compress
    exit 0
}

$ollama = (Get-Command ollama -ErrorAction SilentlyContinue).Source
if (-not $ollama) {
    [pscustomobject]@{
        provider = "local-llm"
        status = "BLOCKED"
        blockers = @("LLAMA_CPP_UNAVAILABLE", "OLLAMA_UNAVAILABLE")
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
    Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 10 | Out-Null
    [pscustomobject]@{
        provider = "ollama"
        endpoint = "http://127.0.0.1:11434/api/generate"
        model = "qwen3:8b"
        status = "READY"
        blockers = @("LLAMA_CPP_WRAPPER_UNAVAILABLE")
        execution_allowed = $false
        live_eligibility_status = "LIVE_ORDER_BLOCKED"
    } | ConvertTo-Json -Compress
    exit 0
}
catch {
    [pscustomobject]@{
        provider = "ollama"
        status = "BLOCKED"
        blockers = @("OLLAMA_PROVIDER_UNAVAILABLE")
        execution_allowed = $false
        live_eligibility_status = "LIVE_ORDER_BLOCKED"
    } | ConvertTo-Json -Compress
    exit 2
}
