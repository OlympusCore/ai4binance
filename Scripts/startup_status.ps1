param(
    [switch]$RequireVoiceTask,
    [switch]$RequireQwenPrompterTask
)

$ErrorActionPreference = "Stop"
$runtimeTaskName = "AI4BINANCE-ReadOnly-Runtime"
$voiceTaskName = "AI4BINANCE-Voice-Assistant"
$qwenPrompterTaskName = "AI4BINANCE-Qwen3-Prompter"
$accountingTaskName = "AI4BINANCE-Accounting-Collector"
$accountingWsTaskName = "AI4BINANCE-Accounting-WebSocket-Collector"
$skillDiscoveryTaskName = "AI4BINANCE-Skill-Discovery"
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$stateDirectory = Join-Path $root "State"
$issues = [System.Collections.Generic.List[string]]::new()
$domainIssues = [System.Collections.Generic.List[string]]::new()

function Convert-ToDateTimeOffset {
    param([Parameter(Mandatory = $true)]$Value)
    if ($Value -is [DateTimeOffset]) {
        return $Value.ToUniversalTime()
    }
    if ($Value -is [DateTime]) {
        if ($Value.Kind -eq [DateTimeKind]::Unspecified) {
            return [DateTimeOffset]::new(
                [DateTime]::SpecifyKind($Value, [DateTimeKind]::Utc)
            ).ToUniversalTime()
        }
        return [DateTimeOffset]::new($Value.ToUniversalTime()).ToUniversalTime()
    }
    return [DateTimeOffset]::Parse([string]$Value).ToUniversalTime()
}

function Get-Ai4BinanceProcessRows {
    $processes = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -eq "python.exe" -and
            $_.CommandLine -match "(?i)-m\s+ai4binance\."
        }
    foreach ($process in $processes) {
        $commandLine = [string]$process.CommandLine
        $service = if ($commandLine -match "(?i)ai4binance\.cli\s+runtime-daemon") {
            "runtime"
        }
        elseif ($commandLine -match "(?i)ai4binance\.cli\s+accounting-collect-daemon") {
            "accounting"
        }
        elseif ($commandLine -match "(?i)ai4binance\.cli\s+accounting-ws-daemon") {
            "accounting-ws"
        }
        elseif ($commandLine -match "(?i)ai4binance\.cli\s+voice-daemon") {
            "voice"
        }
        elseif ($commandLine -match "(?i)ai4binance\.cli\s+skill-discovery-daemon") {
            "skill-discovery"
        }
        elseif ($commandLine -match "(?i)ai4binance\.mcp\.server") {
            "mcp"
        }
        else {
            "other"
        }
        $parent = $processes | Where-Object {
            [int]$_.ProcessId -eq [int]$process.ParentProcessId
        } | Select-Object -First 1
        $parentCommandLine = if ($null -ne $parent) { [string]$parent.CommandLine } else { "" }
        $interpreter = if (
            $commandLine -like "*\.venv\Scripts\python.exe*" -or
            $parentCommandLine -like "*\.venv\Scripts\python.exe*"
        ) {
            "venv"
        }
        elseif ($commandLine -like "*Python312\python.exe*") {
            "global-py312"
        }
        elseif ($commandLine -like "*Python314\python.exe*") {
            "global-py314"
        }
        else {
            "other"
        }
        [pscustomobject]@{
            Service = $service
            Interpreter = $interpreter
            ProcessId = [int]$process.ProcessId
            ParentProcessId = [int]$process.ParentProcessId
        }
    }
}

function Read-JsonState {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][int]$MaximumAgeSeconds,
        [Parameter(Mandatory = $true)][string]$Label
    )
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        $issues.Add("${Label}_STATE_MISSING")
        return $null
    }
    try {
        $payload = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
        $observedAt = Convert-ToDateTimeOffset $payload.updated_at
        $age = ([DateTimeOffset]::UtcNow - $observedAt).TotalSeconds
    }
    catch {
        $issues.Add("${Label}_STATE_INVALID")
        return $null
    }
    if ($age -lt 0 -or $age -gt $MaximumAgeSeconds) {
        $issues.Add("${Label}_STATE_STALE")
    }
    if ($payload.status -ne "RUNNING") {
        $issues.Add("${Label}_NOT_RUNNING")
    }
    if ($payload.execution_allowed -ne $false -or $payload.live_eligibility_status -ne "LIVE_ORDER_BLOCKED") {
        $issues.Add("${Label}_SAFETY_CONTRACT_INVALID")
    }
    if ([int]$payload.pid -lt 1 -or $null -eq (Get-Process -Id ([int]$payload.pid) -ErrorAction SilentlyContinue)) {
        $issues.Add("${Label}_PID_NOT_ALIVE")
    }
    return [pscustomobject]@{
        Label = $Label
        Status = $payload.status
        ProcessId = $payload.pid
        AgeSeconds = [math]::Round($age, 1)
    }
}

function Test-LockMatchesHealth {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        $Health,
        [Parameter(Mandatory = $true)][string]$Label
    )
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        $issues.Add("${Label}_LOCK_MISSING")
        return
    }
    try {
        $lockPid = [int](Get-Content -LiteralPath $Path -Raw)
    }
    catch {
        $issues.Add("${Label}_LOCK_INVALID")
        return
    }
    if ($null -eq $Health) {
        $issues.Add("${Label}_LOCK_PID_MISMATCH")
        return
    }
    $healthPid = [int]$Health.ProcessId
    if ($lockPid -eq $healthPid) {
        return
    }
    if (-not (Test-ProcessDescendant -ProcessId $lockPid -AncestorProcessId $healthPid)) {
        $issues.Add("${Label}_LOCK_PID_MISMATCH")
    }
}

function Test-ProcessDescendant {
    param(
        [Parameter(Mandatory = $true)][int]$ProcessId,
        [Parameter(Mandatory = $true)][int]$AncestorProcessId
    )
    $currentProcessId = $ProcessId
    for ($depth = 0; $depth -lt 6; $depth++) {
        $process = Get-CimInstance Win32_Process `
            -Filter "ProcessId=$currentProcessId" `
            -ErrorAction SilentlyContinue
        if ($null -eq $process) {
            return $false
        }
        $parentProcessId = [int]$process.ParentProcessId
        if ($parentProcessId -eq $AncestorProcessId) {
            return $true
        }
        if ($parentProcessId -lt 1 -or $parentProcessId -eq $currentProcessId) {
            return $false
        }
        $currentProcessId = $parentProcessId
    }
    return $false
}

$runtimeTask = Get-ScheduledTask -TaskName $runtimeTaskName -ErrorAction SilentlyContinue
$voiceTask = Get-ScheduledTask -TaskName $voiceTaskName -ErrorAction SilentlyContinue
$qwenPrompterTask = Get-ScheduledTask -TaskName $qwenPrompterTaskName -ErrorAction SilentlyContinue
$accountingTask = Get-ScheduledTask -TaskName $accountingTaskName -ErrorAction SilentlyContinue
$accountingWsTask = Get-ScheduledTask -TaskName $accountingWsTaskName -ErrorAction SilentlyContinue
$skillDiscoveryTask = Get-ScheduledTask -TaskName $skillDiscoveryTaskName -ErrorAction SilentlyContinue
$processRows = @(Get-Ai4BinanceProcessRows)
if (
    $null -eq $runtimeTask `
        -or ($RequireVoiceTask -and $null -eq $voiceTask) `
        -or ($RequireQwenPrompterTask -and $null -eq $qwenPrompterTask)
) {
    if ($processRows.Count -gt 0) {
        [pscustomobject]@{
            OverallStatus = "DEGRADED"
            Issues = "INCONSISTENT_RUNTIME_CONTROL_PLANE,TASKS_NOT_INSTALLED"
            ProcessCount = $processRows.Count
            ExecutionAllowed = $false
            LiveEligibilityStatus = "LIVE_ORDER_BLOCKED"
        } | Format-List
        $processRows |
            Group-Object Service, Interpreter |
            Select-Object Name, Count |
            Sort-Object Name |
            Format-Table -AutoSize
    }
    else {
        Write-Output "NOT_INSTALLED"
    }
    exit 2
}

$tasks = @($runtimeTask)
if ($null -ne $voiceTask) {
    $tasks += $voiceTask
}
if ($null -ne $qwenPrompterTask) {
    $tasks += $qwenPrompterTask
}
if ($null -ne $accountingTask) {
    $tasks += $accountingTask
}
if ($null -ne $accountingWsTask) {
    $tasks += $accountingWsTask
}
if ($null -ne $skillDiscoveryTask) {
    $tasks += $skillDiscoveryTask
}

$taskRows = foreach ($task in $tasks) {
    $info = Get-ScheduledTaskInfo -TaskName $task.TaskName
    $required = $task.TaskName -eq $runtimeTaskName `
        -or $task.TaskName -eq $accountingTaskName `
        -or $task.TaskName -eq $accountingWsTaskName `
        -or $task.TaskName -eq $skillDiscoveryTaskName `
        -or ($RequireQwenPrompterTask -and $task.TaskName -eq $qwenPrompterTaskName) `
        -or ($RequireVoiceTask -and $task.TaskName -eq $voiceTaskName)
    if ($required -and $task.State -ne "Running") {
        $issues.Add("$($task.TaskName)_NOT_RUNNING")
    }
    [pscustomobject]@{
        TaskName = $task.TaskName
        State = $task.State
        LastRunTime = $info.LastRunTime
        LastTaskResult = $info.LastTaskResult
        MissedRuns = $info.NumberOfMissedRuns
        RestartCount = $task.Settings.RestartCount
    }
}

$runtimeHealth = Read-JsonState `
    -Path (Join-Path $stateDirectory "runtime-health.json") `
    -MaximumAgeSeconds 90 `
    -Label "RUNTIME"
$voiceHealth = $null
if ($RequireVoiceTask -or ($null -ne $voiceTask -and $voiceTask.State -eq "Running")) {
    $voiceHealth = Read-JsonState `
        -Path (Join-Path $stateDirectory "voice-health.json") `
        -MaximumAgeSeconds 90 `
        -Label "VOICE"
}
$qwenPrompterHealth = $null
if ($RequireQwenPrompterTask -or ($null -ne $qwenPrompterTask -and $qwenPrompterTask.State -eq "Running")) {
    $qwenPrompterHealth = Read-JsonState `
        -Path (Join-Path $stateDirectory "qwen-prompter-health.json") `
        -MaximumAgeSeconds 300 `
        -Label "QWEN_PROMPTER"
}
$accountingHealth = $null
if ($null -ne $accountingTask -and $accountingTask.State -eq "Running") {
    $accountingHealth = Read-JsonState `
        -Path (Join-Path $stateDirectory "accounting-health.json") `
        -MaximumAgeSeconds 90 `
        -Label "ACCOUNTING"
}
$accountingWsHealth = $null
if ($null -ne $accountingWsTask -and $accountingWsTask.State -eq "Running") {
    $accountingWsHealth = Read-JsonState `
        -Path (Join-Path $stateDirectory "accounting-ws-health.json") `
        -MaximumAgeSeconds 90 `
        -Label "ACCOUNTING_WS"
}
$skillDiscoveryHealth = $null
if ($null -ne $skillDiscoveryTask -and $skillDiscoveryTask.State -eq "Running") {
    $skillDiscoveryHealth = Read-JsonState `
        -Path (Join-Path $stateDirectory "skill-discovery-health.json") `
        -MaximumAgeSeconds 120 `
        -Label "SKILL_DISCOVERY"
}
Test-LockMatchesHealth `
    -Path (Join-Path $stateDirectory "runtime.lock") `
    -Health $runtimeHealth `
    -Label "RUNTIME"
if ($RequireVoiceTask -or $null -ne $voiceHealth) {
    Test-LockMatchesHealth `
        -Path (Join-Path $stateDirectory "voice.lock") `
        -Health $voiceHealth `
        -Label "VOICE"
}
if ($null -ne $accountingHealth) {
    Test-LockMatchesHealth `
        -Path (Join-Path $stateDirectory "accounting.lock") `
        -Health $accountingHealth `
        -Label "ACCOUNTING"
}
if ($null -ne $accountingWsHealth) {
    Test-LockMatchesHealth `
        -Path (Join-Path $stateDirectory "accounting-ws.lock") `
        -Health $accountingWsHealth `
        -Label "ACCOUNTING_WS"
}
if ($null -ne $skillDiscoveryHealth) {
    Test-LockMatchesHealth `
        -Path (Join-Path $stateDirectory "skill-discovery.lock") `
        -Health $skillDiscoveryHealth `
        -Label "SKILL_DISCOVERY"
}

$runtimeStatePath = Join-Path $stateDirectory "runtime.json"
$runtimeState = $null
if (-not (Test-Path -LiteralPath $runtimeStatePath -PathType Leaf)) {
    $issues.Add("RUNTIME_REPORT_MISSING")
}
else {
    try {
        $runtimeState = Get-Content -LiteralPath $runtimeStatePath -Raw | ConvertFrom-Json
        $createdAt = Convert-ToDateTimeOffset $runtimeState.created_at
        $reportAge = ([DateTimeOffset]::UtcNow - $createdAt).TotalSeconds
        if ($reportAge -lt 0 -or $reportAge -gt 180) {
            $issues.Add("RUNTIME_REPORT_STALE")
        }
        if ($runtimeState.state -ne "READY") {
            $domainIssues.Add("RUNTIME_$($runtimeState.state)")
        }
    }
    catch {
        $issues.Add("RUNTIME_REPORT_INVALID")
    }
}

$taskRows | Format-Table -AutoSize
$processRows |
    Group-Object Service, Interpreter |
    Select-Object Name, Count |
    Sort-Object Name |
    Format-Table -AutoSize
@($runtimeHealth, $voiceHealth, $qwenPrompterHealth, $accountingHealth, $accountingWsHealth, $skillDiscoveryHealth) |
    Where-Object { $null -ne $_ } |
    Format-Table -AutoSize
$overallStatus = if ($issues.Count -eq 0 -and $domainIssues.Count -eq 0) {
    "READY"
}
elseif ($issues.Count -eq 0) {
    "RUNNING_WITH_BLOCKERS"
}
else {
    "DEGRADED"
}
[pscustomobject]@{
    OverallStatus = $overallStatus
    RuntimeState = $runtimeState.state
    Blockers = @($runtimeState.blockers) -join ","
    Issues = $issues -join ","
    DomainIssues = $domainIssues -join ","
    ExecutionAllowed = $false
    LiveEligibilityStatus = "LIVE_ORDER_BLOCKED"
} | Format-List

if ($issues.Count -gt 0) {
    exit 1
}
if ($domainIssues.Count -gt 0) {
    exit 2
}
