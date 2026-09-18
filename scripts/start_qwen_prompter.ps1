param(
    [string]$Model = $(if ($env:AI4BINANCE_PROMPTER_MODEL) { $env:AI4BINANCE_PROMPTER_MODEL } else { "qwen3:8b" }),
    [int]$TimeoutSeconds = $(if ($env:AI4BINANCE_PROMPTER_TIMEOUT_SECONDS) { [int]$env:AI4BINANCE_PROMPTER_TIMEOUT_SECONDS } else { 180 }),
    [int]$MaxHistoryTurns = $(if ($env:AI4BINANCE_PROMPTER_HISTORY_TURNS) { [int]$env:AI4BINANCE_PROMPTER_HISTORY_TURNS } else { 4 })
)

$ErrorActionPreference = "Continue"
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

    $normalized = $InputText.Trim().ToLowerInvariant()
    return $normalized -match "(?:^|[\s/])(?:status|durum|özet|summary|system|sistem|son durum)(?:$|[\s/])"
}

function Get-SystemStatusSnapshot {
    $observedAt = [DateTimeOffset]::UtcNow
    $timestamp = Format-IstanbulTimestamp -Instant $observedAt
    $health = $null
    if (Test-Path -LiteralPath $healthPath -PathType Leaf) {
        try {
            $health = Get-Content -LiteralPath $healthPath -Raw | ConvertFrom-Json
        } catch {
            $health = $null
        }
    }
    $runtime = $null
    $runtimePath = Join-Path $stateDirectory "runtime.json"
    if (Test-Path -LiteralPath $runtimePath -PathType Leaf) {
        try {
            $runtime = Get-Content -LiteralPath $runtimePath -Raw | ConvertFrom-Json
        } catch {
            $runtime = $null
        }
    }
    $healthStatus = if ($null -ne $health) {
        "prompter=$($health.status); provider=$($health.provider); model=$($health.model); endpoint=$($health.endpoint)"
    } else {
        "prompter=unavailable"
    }
    $runtimeStatus = if ($null -ne $runtime) {
        "runtime=$($runtime.state); blockers=$((@($runtime.blockers) -join ','))"
    } else {
        "runtime=unavailable"
    }
    return @"
System status snapshot
Observed at (Europe/Istanbul): $timestamp
$healthStatus
$runtimeStatus
Guidance: answer briefly, mention blockers, and include next action only if useful.
"@
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

    Add-Type -AssemblyName System.Net.Http
    $client = [System.Net.Http.HttpClient]::new()
    $content = $null
    try {
        $client.Timeout = [TimeSpan]::FromSeconds($TimeoutSeconds)
        $body = [ordered]@{
            prompt = $Prompt
            temperature = 0
            n_predict = 768
            stop = @("### User:", "### System:", "</s>")
        } | ConvertTo-Json -Depth 20
        $content = [System.Net.Http.StringContent]::new(
            $body,
            [System.Text.Encoding]::UTF8,
            "application/json"
        )
        $response = $client.PostAsync("$llamaEndpoint/completion", $content).GetAwaiter().GetResult()
        $responseText = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        if (-not $response.IsSuccessStatusCode) {
            $statusCode = [int]$response.StatusCode
            throw "llama.cpp completion HTTP $statusCode $($response.ReasonPhrase): $responseText"
        }
        $payload = $responseText | ConvertFrom-Json
        $answer = [string]$payload.content
        if ([string]::IsNullOrWhiteSpace($answer)) {
            throw "LOCAL_LLM_EMPTY_RESPONSE"
        }
        return $answer.Trim()
    } catch [System.Threading.Tasks.TaskCanceledException] {
        throw "LLAMA_CPP_CHAT_TIMEOUT"
    } finally {
        if ($null -ne $content) {
            $content.Dispose()
        }
        $client.Dispose()
    }
}

function Convert-MessagesToPrompt {
    param(
        [Parameter(Mandatory = $true)][string]$SystemPrompt,
        [Parameter(Mandatory = $true)][object[]]$Messages
    )

    $builder = [System.Text.StringBuilder]::new()
    [void]$builder.AppendLine("### System:")
    [void]$builder.AppendLine($SystemPrompt.Trim())
    [void]$builder.AppendLine("")
    foreach ($message in $Messages) {
        $role = [string]$message.role
        $content = [string]$message.content
        if ([string]::IsNullOrWhiteSpace($content)) {
            continue
        }
        switch ($role) {
            "user" {
                [void]$builder.AppendLine("### User:")
                [void]$builder.AppendLine($content.Trim())
                [void]$builder.AppendLine("")
            }
            "assistant" {
                [void]$builder.AppendLine("### Assistant:")
                [void]$builder.AppendLine($content.Trim())
                [void]$builder.AppendLine("")
            }
        }
    }
    [void]$builder.Append("### Assistant:")
    return $builder.ToString()
}

function New-SystemPrompt {
    return @"
Sen AI4BINANCE Assistant'sin; yerel, tray-erişimli ve tavsiye odakli bir asistansin.

Kurallar:
- Sadece Turkce cevap ver.
- Ilk cumlede dogrudan cevabi ver.
- Basit durum, evet/hayir ve ozet sorularinda en fazla 2 kisa cumle kullan.
- Gereksiz baslik, uyarı ve menu dili kullanma.
- Kullanici ne eksikse onu kisa soyle, sonra tek bir oneride bulun.
- Kaynaklar eksik veya belirsizse bunu kisa belirt ve NO_TRADE / RESEARCH_ONLY ile kilitli kal.
- Dosya degistirme, komut calistirma, canli islem, risk artisi veya gizli bilgi erisimi yok.
- Sonunda kisa bir gerekce verebilirsin, ama cevabi uzatma.
- Zaman yazarsan Europe/Istanbul kullan.

Baglam:
- Project root: $root
- Safe visible health file: state\qwen-prompter-health.json
- Read-only runtime status, when present: state\runtime.json
- Market outlook artifact, when present: runtime\artifacts\decisions\market_outlook\runtime-state.json
- Reference runbook: docs\runbooks\runbook_read_only_runtime.md
- Private state and Secrets are out of scope.

Yazi stili:
- Kisa, net ve operasyonel yaz.
- Uzun aciklama yerine tek karar ver.
- Trading sorularinda sadece gerekli alanlari kullan: Market Outlook, Setup Quality, Trade Plan, Execution Tagging, Blockers, Audit status.
"@
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
        $messages.Add([ordered]@{ role = "user"; content = $inputText })
        while ($messages.Count -gt (1 + ($MaxHistoryTurns * 2))) {
            $messages.RemoveAt(1)
        }

        $effectiveSystemPrompt = $systemPrompt
        if (Test-SystemStatusQuery -InputText $inputText) {
            $effectiveSystemPrompt = $systemPrompt + "`n`n" + (Get-SystemStatusSnapshot)
        }

        $prompt = Convert-MessagesToPrompt -SystemPrompt $effectiveSystemPrompt -Messages @($messages)

        try {
            $answer = Invoke-LlamaCompletion -Prompt $prompt -TimeoutSeconds $TimeoutSeconds
            $responseWrittenAt = [DateTimeOffset]::UtcNow
            $latencySeconds = [Math]::Round(($responseWrittenAt - $promptWrittenAt).TotalSeconds, 3)
            $messages.Add([ordered]@{ role = "assistant"; content = $answer })
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
