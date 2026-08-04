param(
    [string]$Model = $(if ($env:AI4BINANCE_PROMPTER_MODEL) { $env:AI4BINANCE_PROMPTER_MODEL } else { "qwen3:8b" }),
    [int]$TimeoutSeconds = $(if ($env:AI4BINANCE_PROMPTER_TIMEOUT_SECONDS) { [int]$env:AI4BINANCE_PROMPTER_TIMEOUT_SECONDS } else { 120 }),
    [int]$MaxHistoryTurns = $(if ($env:AI4BINANCE_PROMPTER_HISTORY_TURNS) { [int]$env:AI4BINANCE_PROMPTER_HISTORY_TURNS } else { 8 })
)

$ErrorActionPreference = "Continue"
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$stateDirectory = Join-Path $root "State"
$logDirectory = Join-Path $root "Logs\services"
$healthPath = Join-Path $stateDirectory "qwen-prompter-health.json"

$env:AI4BINANCE_ALLOW_AUTO_LIVE_ORDERS = "false"
$env:AI4BINANCE_ADVISORY_LLM_MODE = "RESEARCH_ONLY"
$env:AI4BINANCE_ORDER_AUTHORITY = "BLOCKED"
$env:AI4BINANCE_RISK_AUTHORITY = "BLOCKED"
$env:AI4BINANCE_LIVE_AUTHORITY = "BLOCKED"
$env:OLLAMA_HOST = $(if ($env:OLLAMA_HOST) { $env:OLLAMA_HOST } else { "127.0.0.1:11434" })

function Write-PrompterHealth {
    param(
        [Parameter(Mandatory = $true)][string]$Status,
        [string[]]$Blockers = @(),
        [int]$ExitCode = 0
    )
    New-Item -ItemType Directory -Path $stateDirectory -Force | Out-Null
    $payload = [ordered]@{
        service = "qwen-prompter"
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
    }
    $temporary = "$healthPath.tmp"
    $payload | ConvertTo-Json -Compress | Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $healthPath -Force
}

function Get-BoundedText {
    param(
        [Parameter(Mandatory = $true)][string]$RelativePath,
        [int]$MaximumCharacters = 3000
    )
    $path = Join-Path $root $RelativePath
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        return ""
    }
    $text = Get-Content -LiteralPath $path -Raw -Encoding UTF8
    if ($text.Length -le $MaximumCharacters) {
        return $text
    }
    return $text.Substring(0, $MaximumCharacters) + "`n[TRUNCATED]"
}

function New-SystemPrompt {
    $readme = Get-BoundedText -RelativePath "Docs\README.md" -MaximumCharacters 2200
    $runtime = Get-BoundedText -RelativePath "Docs\READ_ONLY_RUNTIME.md" -MaximumCharacters 2600
    $architecture = Get-BoundedText -RelativePath "Docs\ARCHITECTURE.md" -MaximumCharacters 2600
    return @"
You are a local, visible, advisory-only Qwen3 prompt window for AI4BINANCE EnterpriseAI vNext.

Hard authority boundary:
- You are not Codex and you do not edit files, run commands, trade, place orders, cancel orders, change risk limits, read secrets, or enable live mode.
- AI4BINANCE deterministic code owns final signals, risk gates, exchange validation, sizing, execution permission, backtests, walk-forward validation, OOS evidence, and order blocking.
- For any request involving real orders, live trading, auto execution, risk increase, credential access, or exchange action, answer with LIVE_ORDER_BLOCKED and explain the missing deterministic gates.
- When evidence is incomplete, contradictory, weak, or not validated, prefer NO_TRADE. Promising but unvalidated ideas are RESEARCH_ONLY or STAGED_CANDIDATE only.
- Treat this session as local discussion and research support. Do not claim that anything was executed or changed.

Project connection:
- Project root: $root
- Safe visible health file: State\qwen-prompter-health.json
- Read-only runtime status, when present: State\runtime.json
- Market outlook artifact, when present: Artifacts\market-outlook\runtime-state.json
- Private state and Secrets are out of scope.

Response style:
- Respond in Turkish unless code, identifiers, logs, schemas, or CLI output require English.
- Be concise, source-grounded, and explicit about blockers.
- If the user asks for a trading decision, use the AI4BINANCE sections: Market Outlook, Setup Quality, Trade Plan, Execution Tagging, Blockers, Audit status.

Docs excerpt: Docs\README.md
$readme

Docs excerpt: Docs\READ_ONLY_RUNTIME.md
$runtime

Docs excerpt: Docs\ARCHITECTURE.md
$architecture
"@
}

function Invoke-OllamaChat {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [Parameter(Mandatory = $true)][string]$Body,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds
    )

    Add-Type -AssemblyName System.Net.Http
    $client = [System.Net.Http.HttpClient]::new()
    $content = $null
    try {
        $client.Timeout = [TimeSpan]::FromSeconds($TimeoutSeconds)
        $content = [System.Net.Http.StringContent]::new(
            $Body,
            [System.Text.Encoding]::UTF8,
            "application/json"
        )
        $response = $client.PostAsync($Uri, $content).GetAwaiter().GetResult()
        $responseText = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        if (-not $response.IsSuccessStatusCode) {
            $statusCode = [int]$response.StatusCode
            throw "Ollama chat HTTP $statusCode $($response.ReasonPhrase): $responseText"
        }
        return $responseText | ConvertFrom-Json
    } finally {
        if ($null -ne $content) {
            $content.Dispose()
        }
        $client.Dispose()
    }
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
Write-Host "Mode: RESEARCH_ONLY | execution_allowed=false | LIVE_ORDER_BLOCKED"
Write-Host "Authority: order=BLOCKED | risk=BLOCKED | live=BLOCKED"
Write-Host "Not: Bu pencere sohbet/prompt icindir; emir, risk limiti veya canli islem yetkisi vermez."
Write-Host "Komutlar: /reset, /status, /bye"
Write-Host ""

$ollama = (Get-Command ollama -ErrorAction SilentlyContinue).Source
if (-not $ollama) {
    Write-PrompterHealth -Status "BLOCKED" -Blockers @("OLLAMA_UNAVAILABLE") -ExitCode 2
    Write-Host "Ollama bulunamadi. ollama komutu PATH icinde olmali."
    Write-Host "Bu pencere acik kalacak; kurulumdan sonra tekrar calistirabilirsin."
    Read-Host "Kapatmak icin Enter"
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
} catch {
    Write-PrompterHealth -Status "BLOCKED" -Blockers @("OLLAMA_PROVIDER_UNAVAILABLE") -ExitCode 2
    Write-Host "Ollama API hazir degil: http://127.0.0.1:11434"
    Read-Host "Kapatmak icin Enter"
    exit 2
}

$modelNames = @($tags.models | ForEach-Object { $_.name })
if ($modelNames -notcontains $Model) {
    Write-PrompterHealth -Status "BLOCKED" -Blockers @("OLLAMA_MODEL_UNAVAILABLE") -ExitCode 2
    Write-Host "Model bulunamadi: $Model"
    Write-Host "Kurmak icin: ollama pull $Model"
    Read-Host "Kapatmak icin Enter"
    exit 2
}

$systemPrompt = New-SystemPrompt
$messages = [System.Collections.Generic.List[object]]::new()
$messages.Add([ordered]@{ role = "system"; content = $systemPrompt })

Write-PrompterHealth -Status "RUNNING"
Write-Host "Prompt hazir. Cikmak icin /bye veya Ctrl+C kullan."
Write-Host ""

$prompterPid = $PID
$heartbeatJob = Start-Job -ScriptBlock {
    param(
        [string]$Path,
        [string]$ModelName,
        [string]$ProjectRoot,
        [int]$ProcessId
    )
    while ($true) {
        $payload = [ordered]@{
            service = "qwen-prompter"
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
        }
        $temporary = "$Path.tmp"
        $payload | ConvertTo-Json -Compress | Set-Content -LiteralPath $temporary -Encoding UTF8
        Move-Item -LiteralPath $temporary -Destination $Path -Force
        Start-Sleep -Seconds 30
    }
} -ArgumentList $healthPath, $Model, $root, $prompterPid

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
        Write-Host "Baglam sifirlandi; AI4BINANCE advisory-only system prompt korundu."
        continue
    }
    if ($inputText -eq "/status") {
        Get-Content -LiteralPath $healthPath -Raw
        continue
    }

    $messages.Add([ordered]@{ role = "user"; content = $inputText })
    while ($messages.Count -gt (1 + ($MaxHistoryTurns * 2))) {
        $messages.RemoveAt(1)
    }

    $body = [ordered]@{
        model = $Model
        stream = $false
        think = $false
        messages = @($messages)
        options = [ordered]@{
            temperature = 0
            num_predict = 768
        }
    } | ConvertTo-Json -Depth 20

    try {
        $response = Invoke-OllamaChat `
            -Uri "http://127.0.0.1:11434/api/chat" `
            -Body $body `
            -TimeoutSeconds $TimeoutSeconds
        $answer = [string]$response.message.content
        if ([string]::IsNullOrWhiteSpace($answer)) {
            $answer = "LOCAL_LLM_EMPTY_RESPONSE | ADVISORY_ONLY"
        }
        $messages.Add([ordered]@{ role = "assistant"; content = $answer })
        Write-Host ""
        Write-Host $answer
        Write-Host ""
    } catch {
        Write-PrompterHealth -Status "DEGRADED" -Blockers @("OLLAMA_CHAT_FAILED") -ExitCode 2
        Write-Host "OLLAMA_CHAT_FAILED | ADVISORY_ONLY | LIVE_ORDER_BLOCKED"
        Write-Host $_.Exception.Message
    }
}
}
finally {
    Stop-Job -Job $heartbeatJob -ErrorAction SilentlyContinue
    Remove-Job -Job $heartbeatJob -Force -ErrorAction SilentlyContinue
    Write-PrompterHealth -Status "STOPPED"
}
exit 0
