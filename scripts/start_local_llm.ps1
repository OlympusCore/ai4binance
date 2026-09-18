param(
    [string]$Model = $(if ($env:AI4BINANCE_PROMPTER_MODEL) { $env:AI4BINANCE_PROMPTER_MODEL } else { "qwen3:8b" }),
    [int]$Port = $(if ($env:LLAMA_PORT) { [int]$env:LLAMA_PORT } else { 8080 })
)

$ErrorActionPreference = "Continue"
. (Join-Path $PSScriptRoot "initialize_runtime_environment.ps1")
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$llamaServerScript = Join-Path $PSScriptRoot "start_llama_server.ps1"
$endpoint = "http://127.0.0.1:$Port"

try {
    & $llamaServerScript | Out-Host
} catch {
    [pscustomobject]@{
        provider = "llama.cpp"
        status = "BLOCKED"
        model = $Model
        endpoint = "$endpoint/completion"
        blockers = @("LLAMA_CPP_SERVER_START_FAILED")
        execution_allowed = $false
        live_eligibility_status = "LIVE_ORDER_BLOCKED"
    } | ConvertTo-Json -Compress
    exit 2
}

$listeners = @(
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object LocalAddress, LocalPort, OwningProcess
)
$listenerPids = @($listeners | ForEach-Object { [int]$_.OwningProcess } | Sort-Object -Unique)
if ($listenerPids.Count -eq 0) {
    [pscustomobject]@{
        provider = "llama.cpp"
        status = "BLOCKED"
        model = $Model
        endpoint = "$endpoint/completion"
        blockers = @("LLAMA_CPP_PROVIDER_UNAVAILABLE")
        execution_allowed = $false
        live_eligibility_status = "LIVE_ORDER_BLOCKED"
    } | ConvertTo-Json -Compress
    exit 2
}

[pscustomobject]@{
    provider = "llama.cpp"
    endpoint = "$endpoint/completion"
    model = $Model
    status = "READY"
    provider_started = $false
    provider_pid = $listenerPids[0]
    listener_pids = $listenerPids
    blockers = @()
    execution_allowed = $false
    live_eligibility_status = "LIVE_ORDER_BLOCKED"
} | ConvertTo-Json -Compress
