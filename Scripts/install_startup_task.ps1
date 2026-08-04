param(
    [ValidateSet("Install", "RunRuntime", "RunVoice", "RunValidation", "RunAccounting", "RunAccountingWs", "RunSkillDiscovery")]
    [string]$Mode = "Install",
    [switch]$EnableVoiceTask,
    [switch]$EnableValidationTask,
    [switch]$EnableAccountingTask,
    [switch]$EnableAccountingWsTask,
    [switch]$EnableSkillDiscoveryTask
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$stateDirectory = Join-Path $root "State"
$logDirectory = Join-Path $root "Logs\services"

function Rotate-LogFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [long]$MaximumBytes = 5MB,
        [int]$BackupCount = 3
    )
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return
    }
    for ($index = $BackupCount; $index -ge 1; $index--) {
        $source = if ($index -eq 1) { $Path } else { "$Path.$($index - 1)" }
        $target = "$Path.$index"
        if (Test-Path -LiteralPath $source -PathType Leaf) {
            if ((Get-Item -LiteralPath $source).Length -gt $MaximumBytes) {
                $trimmed = "$source.trimmed"
                Get-Content -LiteralPath $source -Tail 20000 |
                    Set-Content -LiteralPath $trimmed -Encoding UTF8
                Move-Item -LiteralPath $trimmed -Destination $source -Force
            }
            Move-Item -LiteralPath $source -Destination $target -Force
        }
    }
}

function Write-ServiceHealth {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Service,
        [Parameter(Mandatory = $true)][string]$Status,
        [int]$ProcessId = 0,
        [int]$ChildProcessId = 0,
        [int]$ExitCode = 0
    )
    $payload = [ordered]@{
        service = $Service
        status = $Status
        updated_at = [DateTimeOffset]::UtcNow.ToString("o")
        pid = if ($ChildProcessId -gt 0) { $ChildProcessId } else { $ProcessId }
        launcher_pid = $ProcessId
        child_pid = $ChildProcessId
        exit_code = $ExitCode
        execution_allowed = $false
        live_eligibility_status = "LIVE_ORDER_BLOCKED"
    }
    $temporary = "$Path.tmp"
    $payload | ConvertTo-Json -Compress | Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $Path -Force
}

function Invoke-ServicePython {
    param(
        [Parameter(Mandatory = $true)][string]$Service,
        [Parameter(Mandatory = $true)][string]$HealthPath,
        [Parameter(Mandatory = $true)][string]$StdoutPath,
        [Parameter(Mandatory = $true)][string]$StderrPath,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    $heartbeatJob = Start-Job -ScriptBlock {
        param(
            [string]$Path,
            [string]$Service,
            [int]$ProcessId
        )
        while ($true) {
            $payload = [ordered]@{
                service = $Service
                status = "RUNNING"
                updated_at = [DateTimeOffset]::UtcNow.ToString("o")
                pid = $ProcessId
                launcher_pid = $ProcessId
                child_pid = 0
                exit_code = 0
                execution_allowed = $false
                live_eligibility_status = "LIVE_ORDER_BLOCKED"
            }
            $temporary = "$Path.tmp"
            $payload | ConvertTo-Json -Compress | Set-Content -LiteralPath $temporary -Encoding UTF8
            Move-Item -LiteralPath $temporary -Destination $Path -Force
            Start-Sleep -Seconds 30
        }
    } -ArgumentList $HealthPath, $Service, $PID
    Push-Location -LiteralPath $root
    try {
        & $python @Arguments 1>> $StdoutPath 2>> $StderrPath
        return [int]$LASTEXITCODE
    } finally {
        Pop-Location
        Stop-Job -Job $heartbeatJob -ErrorAction SilentlyContinue
        Remove-Job -Job $heartbeatJob -Force -ErrorAction SilentlyContinue
    }
}

function Start-BoundedService {
    param(
        [Parameter(Mandatory = $true)][string]$Service,
        [Parameter(Mandatory = $true)][string]$Command
    )
    New-Item -ItemType Directory -Path $stateDirectory, $logDirectory -Force | Out-Null
    $healthPath = Join-Path $stateDirectory "$Service-health.json"
    $stdoutPath = Join-Path $logDirectory "$Service.stdout.log"
    $stderrPath = Join-Path $logDirectory "$Service.stderr.log"
    Rotate-LogFile -Path $stdoutPath
    Rotate-LogFile -Path $stderrPath
    Write-ServiceHealth -Path $healthPath -Service $Service -Status "RUNNING" -ProcessId $PID
    $exitCode = Invoke-ServicePython `
        -Service $Service `
        -HealthPath $healthPath `
        -StdoutPath $stdoutPath `
        -StderrPath $stderrPath `
        -Arguments @("-m", "ai4binance.cli", $Command)
    $finalStatus = if ($exitCode -eq 0) { "STOPPED" } else { "FAILED" }
    Write-ServiceHealth -Path $healthPath -Service $Service -Status $finalStatus -ExitCode $exitCode
    exit $exitCode
}

function Start-BoundedValidation {
    New-Item -ItemType Directory -Path $stateDirectory, $logDirectory -Force | Out-Null
    $service = "validation"
    $healthPath = Join-Path $stateDirectory "$service-health.json"
    $stdoutPath = Join-Path $logDirectory "$service.stdout.log"
    $stderrPath = Join-Path $logDirectory "$service.stderr.log"
    Rotate-LogFile -Path $stdoutPath
    Rotate-LogFile -Path $stderrPath
    Write-ServiceHealth -Path $healthPath -Service $service -Status "RUNNING" -ProcessId $PID

    $archiveExitCode = Invoke-ServicePython `
        -Service $service `
        -HealthPath $healthPath `
        -StdoutPath $stdoutPath `
        -StderrPath $stderrPath `
        -Arguments @("-m", "ai4binance.cli", "archive-public")
    if ($archiveExitCode -ne 0) {
        Write-ServiceHealth -Path $healthPath -Service $service -Status "FAILED" -ExitCode $archiveExitCode
        exit $archiveExitCode
    }

    $exitCode = Invoke-ServicePython `
        -Service $service `
        -HealthPath $healthPath `
        -StdoutPath $stdoutPath `
        -StderrPath $stderrPath `
        -Arguments @("-m", "ai4binance.cli", "validate-research")
    $finalStatus = if ($exitCode -eq 0) { "STOPPED" } else { "FAILED" }
    Write-ServiceHealth -Path $healthPath -Service $service -Status $finalStatus -ExitCode $exitCode
    exit $exitCode
}

if ($Mode -eq "RunRuntime") {
    Start-BoundedService -Service "runtime" -Command "runtime-daemon"
}
if ($Mode -eq "RunVoice") {
    Start-BoundedService -Service "voice" -Command "voice-daemon"
}
if ($Mode -eq "RunValidation") {
    Start-BoundedValidation
}
if ($Mode -eq "RunAccounting") {
    Start-BoundedService -Service "accounting" -Command "accounting-collect-daemon"
}
if ($Mode -eq "RunAccountingWs") {
    Start-BoundedService -Service "accounting-ws" -Command "accounting-ws-daemon"
}
if ($Mode -eq "RunSkillDiscovery") {
    Start-BoundedService -Service "skill-discovery" -Command "skill-discovery-daemon"
}

$taskName = "AI4BINANCE-ReadOnly-Runtime"
$voiceTaskName = "AI4BINANCE-Voice-Assistant"
$validationTaskName = "AI4BINANCE-Research-Validation"
$accountingTaskName = "AI4BINANCE-Accounting-Collector"
$accountingWsTaskName = "AI4BINANCE-Accounting-WebSocket-Collector"
$skillDiscoveryTaskName = "AI4BINANCE-Skill-Discovery"
$credentials = Join-Path $root "Secrets\bnc.env"
$privateState = Join-Path $stateDirectory "private"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Repository Python runtime not found: $python"
}
if (-not (Test-Path -LiteralPath $credentials -PathType Leaf)) {
    throw "Read-only Binance credential file not found: $credentials"
}

if ($EnableVoiceTask) {
    & $python -c "import edge_tts, faster_whisper, sounddevice"
    if ($LASTEXITCODE -ne 0) {
        throw "Voice dependencies are not installed in the repository runtime."
    }
}

New-Item -ItemType Directory -Path $privateState, $logDirectory -Force | Out-Null
$owner = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
foreach ($protectedDirectory in @($privateState)) {
    & icacls.exe $protectedDirectory /inheritance:r | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Could not disable inherited ACLs on protected runtime state."
    }
    & icacls.exe $protectedDirectory /grant:r `
        "${owner}:(OI)(CI)F" `
        "*S-1-5-18:(OI)(CI)F" `
        "*S-1-5-32-544:(OI)(CI)F" `
        /T /C | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Could not restrict protected runtime state ACLs."
    }
}
& icacls.exe $credentials /inheritance:r | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Could not disable inherited ACLs on credential file."
}
& icacls.exe $credentials /grant:r `
    "${owner}:F" `
    "*S-1-5-18:F" `
    "*S-1-5-32-544:F" | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Could not restrict credential file ACLs."
}

$powerShell = (Get-Command powershell.exe -ErrorAction Stop).Source
$scriptPath = $PSCommandPath
$action = New-ScheduledTaskAction `
    -Execute $powerShell `
    -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$scriptPath`" -Mode RunRuntime" `
    -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -RestartCount 10 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 3650) `
    -StartWhenAvailable `
    -Hidden

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "AI4BINANCE read-only wallet-first research runtime" `
    -Force | Out-Null

if ($EnableVoiceTask) {
    $voiceAction = New-ScheduledTaskAction `
        -Execute $powerShell `
        -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$scriptPath`" -Mode RunVoice" `
        -WorkingDirectory $root
    Register-ScheduledTask `
        -TaskName $voiceTaskName `
        -Action $voiceAction `
        -Trigger $trigger `
        -Principal $principal `
        -Settings $settings `
        -Description "AI4BINANCE local-interactive read-only Turkish voice assistant" `
        -Force | Out-Null
} else {
    Unregister-ScheduledTask -TaskName $voiceTaskName -Confirm:$false -ErrorAction SilentlyContinue
}

if ($EnableValidationTask) {
    $validationAction = New-ScheduledTaskAction `
        -Execute $powerShell `
        -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$scriptPath`" -Mode RunValidation" `
        -WorkingDirectory $root
    Register-ScheduledTask `
        -TaskName $validationTaskName `
        -Action $validationAction `
        -Trigger $trigger `
        -Principal $principal `
        -Settings $settings `
        -Description "AI4BINANCE public archive and research validation job" `
        -Force | Out-Null
} else {
    Unregister-ScheduledTask -TaskName $validationTaskName -Confirm:$false -ErrorAction SilentlyContinue
}

if ($EnableAccountingTask) {
    $accountingAction = New-ScheduledTaskAction `
        -Execute $powerShell `
        -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$scriptPath`" -Mode RunAccounting" `
        -WorkingDirectory $root
    Register-ScheduledTask `
        -TaskName $accountingTaskName `
        -Action $accountingAction `
        -Trigger $trigger `
        -Principal $principal `
        -Settings $settings `
        -Description "AI4BINANCE read-only Spot/Futures accounting collector" `
        -Force | Out-Null
} else {
    Unregister-ScheduledTask -TaskName $accountingTaskName -Confirm:$false -ErrorAction SilentlyContinue
}

if ($EnableAccountingWsTask) {
    $accountingWsAction = New-ScheduledTaskAction `
        -Execute $powerShell `
        -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$scriptPath`" -Mode RunAccountingWs" `
        -WorkingDirectory $root
    Register-ScheduledTask `
        -TaskName $accountingWsTaskName `
        -Action $accountingWsAction `
        -Trigger $trigger `
        -Principal $principal `
        -Settings $settings `
        -Description "AI4BINANCE read-only Spot/Futures WebSocket accounting collector" `
        -Force | Out-Null
} else {
    Unregister-ScheduledTask -TaskName $accountingWsTaskName -Confirm:$false -ErrorAction SilentlyContinue
}

if ($EnableSkillDiscoveryTask) {
    $skillDiscoveryAction = New-ScheduledTaskAction `
        -Execute $powerShell `
        -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$scriptPath`" -Mode RunSkillDiscovery" `
        -WorkingDirectory $root
    Register-ScheduledTask `
        -TaskName $skillDiscoveryTaskName `
        -Action $skillDiscoveryAction `
        -Trigger $trigger `
        -Principal $principal `
        -Settings $settings `
        -Description "AI4BINANCE quarantine-first continuous Agent Skill discovery" `
        -Force | Out-Null
} else {
    Unregister-ScheduledTask -TaskName $skillDiscoveryTaskName -Confirm:$false -ErrorAction SilentlyContinue
}

Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State
Get-ScheduledTask -TaskName $voiceTaskName -ErrorAction SilentlyContinue |
    Select-Object TaskName, State
Get-ScheduledTask -TaskName $validationTaskName -ErrorAction SilentlyContinue |
    Select-Object TaskName, State
Get-ScheduledTask -TaskName $accountingTaskName -ErrorAction SilentlyContinue |
    Select-Object TaskName, State
Get-ScheduledTask -TaskName $accountingWsTaskName -ErrorAction SilentlyContinue |
    Select-Object TaskName, State
Get-ScheduledTask -TaskName $skillDiscoveryTaskName -ErrorAction SilentlyContinue |
    Select-Object TaskName, State
