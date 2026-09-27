param(
    [string]$Model = $(if ($env:AI4BINANCE_PROMPTER_MODEL) { $env:AI4BINANCE_PROMPTER_MODEL } else { "qwen3:8b" }),
    [int]$TimeoutSeconds = $(if ($env:AI4BINANCE_PROMPTER_TIMEOUT_SECONDS) { [int]$env:AI4BINANCE_PROMPTER_TIMEOUT_SECONDS } else { 180 }),
    [int]$MaxHistoryTurns = $(if ($env:AI4BINANCE_PROMPTER_HISTORY_TURNS) { [int]$env:AI4BINANCE_PROMPTER_HISTORY_TURNS } else { 4 })
)

$ErrorActionPreference = "Continue"
. (Join-Path $PSScriptRoot "assistant_wallet_context.ps1")
. (Join-Path $PSScriptRoot "initialize_runtime_environment.ps1")
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$stateDirectory = Join-Path $root "runtime\state"
$logDirectory = Join-Path $root "runtime\logs\services"
$healthPath = Join-Path $stateDirectory "qwen-prompter-health.json"
$llamaServerScript = Join-Path $PSScriptRoot "start_llama_server.ps1"
$llamaHost = "127.0.0.1"
$llamaPort = 8080
$llamaEndpoint = "http://$llamaHost`:$llamaPort"

$env:AI4BINANCE_ALLOW_AUTO_LIVE_ORDERS = "false"
$env:AI4BINANCE_ADVISORY_LLM_MODE = "RESEARCH_ONLY"
$env:AI4BINANCE_ORDER_AUTHORITY = "BLOCKED"
$env:AI4BINANCE_RISK_AUTHORITY = "BLOCKED"
$env:AI4BINANCE_LIVE_AUTHORITY = "BLOCKED"
$env:LLAMA_HOST = $(if ($env:LLAMA_HOST) { $env:LLAMA_HOST } else { $llamaHost })
$env:LLAMA_PORT = $(if ($env:LLAMA_PORT) { $env:LLAMA_PORT } else { "$llamaPort" })

function Get-IstanbulTimeZone {
    foreach ($timeZoneId in @("Turkey Standard Time", "Europe/Istanbul")) {
        try {
            return [TimeZoneInfo]::FindSystemTimeZoneById($timeZoneId)
        } catch {
            continue
        }
    }
    return [TimeZoneInfo]::Utc
}

function Format-IstanbulTimestamp {
    param([Parameter(Mandatory = $true)][DateTimeOffset]$Instant)

    $timeZone = Get-IstanbulTimeZone
    $converted = [TimeZoneInfo]::ConvertTime($Instant, $timeZone)
    return $converted.ToString("yyyy-MM-dd HH:mm:ss zzz")
}

function Test-SystemStatusQuery {
    param([Parameter(Mandatory = $true)][string]$InputText)
    return Invoke-AI4BinanceAssistantRequest @{ operation = "is_status_query"; input_text = $InputText }
}

function Get-SystemStatusSnapshot {
    $result = Invoke-AI4BinanceAssistantRequest @{
        operation = "runtime_status"; state_directory = $stateDirectory
        now = [DateTimeOffset]::UtcNow.ToString("o")
    }
    return ($result | ConvertTo-Json -Compress)
}

function Write-PrompterHealth {
    param(
        [Parameter(Mandatory = $true)][string]$Status,
        [string[]]$Blockers = @(),
        [int]$ExitCode = 0,
        [string]$Endpoint = "",
        [object[]]$ListenerPids = @(),
        [Nullable[int]]$ProviderPid = $null
    )
    New-Item -ItemType Directory -Path $stateDirectory -Force | Out-Null
    $payload = [ordered]@{
        service = "qwen-prompter"
        provider = "llama.cpp"
        status = $Status
        model = $Model
        project_root = $root
        updated_at = [DateTimeOffset]::UtcNow.ToString("o")
        pid = $PID
        blockers = $Blockers
        advisory_mode = "RESEARCH_ONLY"
        execution_allowed = $false
        order_authority = "BLOCKED"
        risk_authority = "BLOCKED"
        live_authority = "BLOCKED"
        live_eligibility_status = "LIVE_ORDER_BLOCKED"
        exit_code = $ExitCode
        endpoint = $Endpoint
        listener_pids = @($ListenerPids)
        provider_pid = $ProviderPid
        auto_learn = [ordered]@{
            status = $Status
            mode = "RESEARCH_ONLY"
            engine = [ordered]@{
                provider = "llama.cpp"
                model = $Model
                runtime = "llama.cpp"
            }
            capabilities = @(
                "observe"
                "analyze"
                "extract_lessons"
                "detect_patterns"
                "generate_hypotheses"
                "propose_experiments"
                "propose_improvements"
            )
            authority = [ordered]@{
                modify_runtime = $false
                modify_strategy = $false
                modify_parameters = $false
                modify_risk_limits = $false
                promote_strategy = $false
                authorize_execution = $false
                deploy_code = $false
            }
            promotion = [ordered]@{
                human_approval_required = $true
            }
            execution = [ordered]@{
                live_execution = $false
            }
            learning = [ordered]@{
                model_weight_update = $false
                external_memory = $true
                evidence_registry = $true
                lesson_registry = $true
                experiment_registry = $true
            }
        }
    }
    $temporary = "$healthPath.tmp"
    $payload | ConvertTo-Json -Compress | Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $healthPath -Force
}

function Get-LlamaListeners {
    try {
        return @(
            Get-NetTCPConnection -LocalPort $llamaPort -State Listen -ErrorAction Stop |
                Select-Object LocalAddress, LocalPort, OwningProcess
        )
    } catch {
        return @()
    }
}

function Get-PrimaryListenerPid {
    param([object[]]$Listeners)

    $listener = @($Listeners | Sort-Object @{ Expression = { [string]$_.LocalAddress } }, OwningProcess | Select-Object -First 1)
    if ($listener.Count -eq 0) {
        return $null
    }
    return [int]$listener[0].OwningProcess
}

function Invoke-LlamaCompletion {
    param(
        [Parameter(Mandatory = $true)][string]$Prompt,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds
    )
    return Invoke-AI4BinanceAssistantRequest @{
        operation = "complete"; prompt = $Prompt
        endpoint = $llamaEndpoint; timeout_seconds = $TimeoutSeconds
        max_tokens = 768
    }
}

function Convert-MessagesToPrompt {
    param(
        [Parameter(Mandatory = $true)][string]$SystemPrompt,
        [Parameter(Mandatory = $true)][object[]]$Messages
    )
    return Invoke-AI4BinanceAssistantRequest @{
        operation = "build_prompt"; system_prompt = $SystemPrompt; messages = @($Messages)
    }
}

function New-SystemPrompt {
    return Invoke-AI4BinanceAssistantRequest @{ operation = "system_prompt" }
}

try {
    $Host.UI.RawUI.WindowTitle = "AI4BINANCE Qwen3 Prompter - RESEARCH_ONLY"
} catch {
    # Non-interactive hosts may not expose a console title.
}

New-Item -ItemType Directory -Path $stateDirectory, $logDirectory -Force | Out-Null
Write-PrompterHealth -Status "STARTING"

Write-Host ""
Write-Host "AI4BINANCE Qwen3 Prompter"
Write-Host "Model: $Model"
Write-Host "Provider: llama.cpp | endpoint=http://127.0.0.1:8080/completion"
Write-Host "Mode: RESEARCH_ONLY | execution_allowed=false | LIVE_ORDER_BLOCKED"
Write-Host "Authority: order=BLOCKED | risk=BLOCKED | live=BLOCKED"
Write-Host "Not: This window is for conversation and advisory use only; it does not grant order, risk, or live execution authority."
Write-Host "Commands: /reset, /status, /bye"
Write-Host ""

try {
    & $llamaServerScript | Out-Host
} catch {
    Write-PrompterHealth -Status "BLOCKED" -Blockers @("LLAMA_CPP_SERVER_START_FAILED") -ExitCode 2 -Endpoint $llamaEndpoint
    Write-Host "llama.cpp server failed to start."
    Write-Host $_.Exception.Message
    Read-Host "Press Enter to close"
    exit 2
}

$listeners = @(Get-LlamaListeners)
if ($listeners.Count -eq 0) {
    Write-PrompterHealth -Status "BLOCKED" -Blockers @("LLAMA_CPP_PROVIDER_UNAVAILABLE") -ExitCode 2 -Endpoint $llamaEndpoint
    Write-Host "llama.cpp provider is unavailable."
    Read-Host "Press Enter to close"
    exit 2
}

$providerPid = Get-PrimaryListenerPid -Listeners $listeners
Write-PrompterHealth `
    -Status "RUNNING" `
    -Endpoint $llamaEndpoint `
    -ListenerPids @($listeners | ForEach-Object { $_.OwningProcess } | Sort-Object -Unique) `
    -ProviderPid $providerPid
Write-Host "Prompt ready. Use /bye or Ctrl+C to exit."
Write-Host ""

$systemPrompt = New-SystemPrompt
$messages = [System.Collections.Generic.List[object]]::new()
$messages.Add([ordered]@{ role = "system"; content = $systemPrompt })

$heartbeatJob = Start-Job -ScriptBlock {
    param(
        [string]$Path,
        [string]$ModelName,
        [string]$ProjectRoot,
        [int]$ProcessId,
        [string]$Endpoint,
        [object[]]$ListenerPids,
        [Nullable[int]]$ProviderPid
    )
    while ($true) {
        $payload = [ordered]@{
            service = "qwen-prompter"
            provider = "llama.cpp"
            status = "RUNNING"
            model = $ModelName
            project_root = $ProjectRoot
            updated_at = [DateTimeOffset]::UtcNow.ToString("o")
            pid = $ProcessId
            blockers = @()
            advisory_mode = "RESEARCH_ONLY"
            execution_allowed = $false
            order_authority = "BLOCKED"
            risk_authority = "BLOCKED"
            live_authority = "BLOCKED"
            live_eligibility_status = "LIVE_ORDER_BLOCKED"
            exit_code = 0
            endpoint = $Endpoint
            listener_pids = @($ListenerPids)
            provider_pid = $ProviderPid
            auto_learn = [ordered]@{
                status = "RUNNING"
                mode = "RESEARCH_ONLY"
                engine = [ordered]@{
                    provider = "llama.cpp"
                    model = $ModelName
                    runtime = "llama.cpp"
                }
                capabilities = @(
                    "observe"
                    "analyze"
                    "extract_lessons"
                    "detect_patterns"
                    "generate_hypotheses"
                    "propose_experiments"
                    "propose_improvements"
                )
                authority = [ordered]@{
                    modify_runtime = $false
                    modify_strategy = $false
                    modify_parameters = $false
                    modify_risk_limits = $false
                    promote_strategy = $false
                    authorize_execution = $false
                    deploy_code = $false
                }
                promotion = [ordered]@{
                    human_approval_required = $true
                }
                execution = [ordered]@{
                    live_execution = $false
                }
                learning = [ordered]@{
                    model_weight_update = $false
                    external_memory = $true
                    evidence_registry = $true
                    lesson_registry = $true
                    experiment_registry = $true
                }
            }
        }
        $temporary = "$Path.tmp"
        $payload | ConvertTo-Json -Compress | Set-Content -LiteralPath $temporary -Encoding UTF8
        Move-Item -LiteralPath $temporary -Destination $Path -Force
        Start-Sleep -Seconds 30
    }
} -ArgumentList $healthPath, $Model, $root, $PID, $llamaEndpoint, @($listeners | ForEach-Object { $_.OwningProcess } | Sort-Object -Unique), $providerPid

try {
    while ($true) {
        $inputText = Read-Host "AI4BINANCE/qwen3"
        if ([string]::IsNullOrWhiteSpace($inputText)) {
            continue
        }
        if ($inputText -in @("/bye", "/exit", "/quit")) {
            break
        }
        if ($inputText -eq "/reset") {
            $messages.Clear()
            $messages.Add([ordered]@{ role = "system"; content = $systemPrompt })
            Write-Host "Context reset; advisory-only system prompt preserved."
            continue
        }
        if ($inputText -eq "/status") {
            Get-Content -LiteralPath $healthPath -Raw
            continue
        }

        $promptWrittenAt = [DateTimeOffset]::UtcNow
        Write-Host "Prompt timestamp (Europe/Istanbul): $(Format-IstanbulTimestamp -Instant $promptWrittenAt)"
        Write-Host "Prompt timestamp (UTC): $($promptWrittenAt.ToString('o'))"
        Add-AI4BinanceAssistantHistory $messages "user" $inputText $MaxHistoryTurns

        $effectiveSystemPrompt = $systemPrompt
        if (Test-SystemStatusQuery -InputText $inputText) {
            $effectiveSystemPrompt = $systemPrompt + "`n`n" + (Get-SystemStatusSnapshot)
        }

        $prompt = Convert-MessagesToPrompt -SystemPrompt $effectiveSystemPrompt -Messages @($messages)

        try {
            $answer = Invoke-LlamaCompletion -Prompt $prompt -TimeoutSeconds $TimeoutSeconds
            $responseWrittenAt = [DateTimeOffset]::UtcNow
            $latencySeconds = [Math]::Round(($responseWrittenAt - $promptWrittenAt).TotalSeconds, 3)
            Add-AI4BinanceAssistantHistory $messages "assistant" $answer $MaxHistoryTurns
            Write-Host ""
            Write-Host "Response timestamp (Europe/Istanbul): $(Format-IstanbulTimestamp -Instant $responseWrittenAt)"
            Write-Host "Response timestamp (UTC): $($responseWrittenAt.ToString('o')) | latency=${latencySeconds}s"
            Write-Host $answer
            Write-Host ""
        } catch {
            $failureWrittenAt = [DateTimeOffset]::UtcNow
            $failureLatencySeconds = [Math]::Round(($failureWrittenAt - $promptWrittenAt).TotalSeconds, 3)
            $failureReason = if ($_.Exception.Message -eq "LLAMA_CPP_CHAT_TIMEOUT") {
                "LLAMA_CPP_CHAT_TIMEOUT | The completion request exceeded the timeout or was canceled before the model replied."
            } else {
                $_.Exception.Message
            }
            Write-PrompterHealth `
                -Status "DEGRADED" `
                -Blockers @("LLAMA_CPP_CHAT_FAILED") `
                -ExitCode 2 `
                -Endpoint $llamaEndpoint `
                -ListenerPids @($listeners | ForEach-Object { $_.OwningProcess } | Sort-Object -Unique) `
                -ProviderPid $providerPid
            Write-Host "LLAMA_CPP_CHAT_FAILED | ADVISORY_ONLY | LIVE_ORDER_BLOCKED"
            Write-Host "Prompt timestamp (Europe/Istanbul): $(Format-IstanbulTimestamp -Instant $promptWrittenAt)"
            Write-Host "Failure timestamp (Europe/Istanbul): $(Format-IstanbulTimestamp -Instant $failureWrittenAt)"
            Write-Host "Failure timestamp (UTC): $($failureWrittenAt.ToString('o')) | elapsed=${failureLatencySeconds}s"
            Write-Host $failureReason
            Start-Sleep -Seconds 5
            & $llamaServerScript | Out-Host
            $listeners = @(Get-LlamaListeners)
            $providerPid = Get-PrimaryListenerPid -Listeners $listeners
            if ($listeners.Count -gt 0) {
                Write-PrompterHealth `
                    -Status "RUNNING" `
                    -Endpoint $llamaEndpoint `
                    -ListenerPids @($listeners | ForEach-Object { $_.OwningProcess } | Sort-Object -Unique) `
                    -ProviderPid $providerPid
                Write-Host "llama.cpp provider is ready again."
            }
        }
    }
} finally {
    Stop-Job -Job $heartbeatJob -ErrorAction SilentlyContinue
    Remove-Job -Job $heartbeatJob -Force -ErrorAction SilentlyContinue
    Write-PrompterHealth -Status "STOPPED" -Endpoint $llamaEndpoint
}

exit 0
