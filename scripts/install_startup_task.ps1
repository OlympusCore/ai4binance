param(
    [ValidateSet("Install", "InstallMarketHistory", "InstallVirtualMarket", "RunRuntime", "RunVirtualMarket", "RunVoice", "RunValidation", "RunAccounting", "RunAccountingWs", "RunSkillDiscovery", "RunMarketHistory", "RunFuturesMultiTf")]
    [string]$Mode = "Install",
    [switch]$EnableVoiceTask,
    [switch]$EnableValidationTask,
    [switch]$EnableAccountingTask,
    [switch]$EnableAccountingWsTask,
    [switch]$EnableSkillDiscoveryTask,
    [bool]$EnableYkbReportTask = $true,
    [string]$YkbSymbol = "HOTUSDT",
    [string]$YkbDailyTime = "09:00",
    [int]$YkbMaxReportAgeHours = 4
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "initialize_runtime_environment.ps1")
$env:PYTHONDONTWRITEBYTECODE = "1"
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$stateDirectory = Join-Path $root "runtime\state"
$serviceManifestPath = Join-Path $root "config\operations\services.json"
$serviceManifest = Get-Content -LiteralPath $serviceManifestPath -Raw | ConvertFrom-Json
$runtimeResearchDirectory = Join-Path $stateDirectory "runtime_research"
$logDirectory = Join-Path $root "runtime\logs\services"

function Get-ServiceManifestEntry {
    param([Parameter(Mandatory = $true)][string]$Service)
    $entry = $serviceManifest.services | Where-Object { $_.service -eq $Service } | Select-Object -First 1
    if ($null -eq $entry) {
        throw "Service manifest entry missing: $Service"
    }
    return $entry
}

function Rotate-LogFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [long]$MaximumBytes = 5MB,
        [int]$BackupCount = 3
    )
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return
    }
    $temporaryFiles = [System.Collections.Generic.List[string]]::new()
    try {
        for ($index = $BackupCount; $index -ge 1; $index--) {
            $source = if ($index -eq 1) { $Path } else { "$Path.$($index - 1)" }
            $target = "$Path.$index"
            if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
                continue
            }
            if ((Get-Item -LiteralPath $source).Length -gt $MaximumBytes) {
                $trimmed = "$source.$PID.trimmed"
                $temporaryFiles.Add($trimmed)
                $inputStream = [System.IO.File]::Open(
                    $source,
                    [System.IO.FileMode]::Open,
                    [System.IO.FileAccess]::Read,
                    [System.IO.FileShare]::ReadWrite
                )
                try {
                    $inputStream.Position = [Math]::Max(
                        0,
                        $inputStream.Length - $MaximumBytes
                    )
                    $outputStream = [System.IO.File]::Open(
                        $trimmed,
                        [System.IO.FileMode]::Create,
                        [System.IO.FileAccess]::Write,
                        [System.IO.FileShare]::None
                    )
                    try {
                        $inputStream.CopyTo($outputStream)
                    }
                    finally {
                        $outputStream.Dispose()
                    }
                }
                finally {
                    $inputStream.Dispose()
                }
                [System.IO.File]::Delete($source)
                [System.IO.File]::Move($trimmed, $source)
            }
            if (Test-Path -LiteralPath $target -PathType Leaf) {
                [System.IO.File]::Delete($target)
            }
            [System.IO.File]::Move($source, $target)
        }
    }
    catch {
        # Logging maintenance must never prevent a safety-bounded service from
        # starting. The next restart retries rotation after transient locks.
        Write-Warning (
            "Log rotation deferred for {0}: {1}" -f `
                $Path, $_.Exception.Message
        )
    }
    finally {
        foreach ($temporary in $temporaryFiles) {
            Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
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
        service                 = $Service
        status                  = $Status
        updated_at              = [DateTimeOffset]::UtcNow.ToString("o")
        pid                     = if ($ChildProcessId -gt 0) { $ChildProcessId } else { $ProcessId }
        launcher_pid            = $ProcessId
        child_pid               = $ChildProcessId
        exit_code               = $ExitCode
        execution_allowed       = $false
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
                service                 = $Service
                status                  = "RUNNING"
                updated_at              = [DateTimeOffset]::UtcNow.ToString("o")
                pid                     = $ProcessId
                launcher_pid            = $ProcessId
                child_pid               = 0
                exit_code               = 0
                execution_allowed       = $false
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
        & $python -B @Arguments 1>> $StdoutPath 2>> $StderrPath
        return [int]$LASTEXITCODE
    }
    finally {
        Pop-Location
        Stop-Job -Job $heartbeatJob -ErrorAction SilentlyContinue
        Remove-Job -Job $heartbeatJob -Force -ErrorAction SilentlyContinue
    }
}

function Start-BoundedService {
    param(
        [Parameter(Mandatory = $true)][string]$Service,
        [Parameter(Mandatory = $true)][string]$Command,
        [string]$Module = "ai4binance.cli",
        [switch]$RestartForever
    )
    New-Item -ItemType Directory -Path $stateDirectory, $runtimeResearchDirectory, $logDirectory -Force | Out-Null
    $healthPath = Join-Path $stateDirectory "$Service-health.json"
    $stdoutPath = Join-Path $logDirectory "$Service.stdout.log"
    $stderrPath = Join-Path $logDirectory "$Service.stderr.log"
    Rotate-LogFile -Path $stdoutPath
    Rotate-LogFile -Path $stderrPath
    $pythonArguments = if ($Module -eq "ai4binance.cli") {
        @("-m", "ai4binance.cli", $Command)
    }
    else {
        @("-m", $Module, $Command)
    }
    do {
        Write-ServiceHealth -Path $healthPath -Service $Service -Status "RUNNING" -ProcessId $PID
        try {
            $exitCode = Invoke-ServicePython `
                -Service $Service `
                -HealthPath $healthPath `
                -StdoutPath $stdoutPath `
                -StderrPath $stderrPath `
                -Arguments $pythonArguments
        }
        catch {
            # Native stderr and launcher failures must reach the recovery loop.
            $exitCode = 1
        }
        if (-not $RestartForever) {
            $finalStatus = if ($exitCode -eq 0) { "STOPPED" } else { "FAILED" }
            Write-ServiceHealth -Path $healthPath -Service $Service -Status $finalStatus -ExitCode $exitCode
            exit $exitCode
        }
        Write-ServiceHealth `
            -Path $healthPath `
            -Service $Service `
            -Status "RECOVERING" `
            -ProcessId $PID `
            -ExitCode $exitCode
        Start-Sleep -Seconds 60
    } while ($true)
}

function Start-BoundedValidation {
    New-Item -ItemType Directory -Path $stateDirectory, $runtimeResearchDirectory, $logDirectory -Force | Out-Null
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

function Register-VirtualMarketTask {
    $entry = Get-ServiceManifestEntry -Service "virtual-market"
    $powerShell = (Get-Command powershell.exe -ErrorAction Stop).Source
    $action = New-ScheduledTaskAction `
        -Execute $powerShell `
        -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`" -Mode RunVirtualMarket" `
        -WorkingDirectory $root
    $logonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $principal = New-ScheduledTaskPrincipal `
        -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
    $taskSettings = New-ScheduledTaskSettingsSet `
        -MultipleInstances IgnoreNew `
        -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit ([TimeSpan]::Zero) `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -StartWhenAvailable -Hidden
    Register-ScheduledTask -TaskName ([string]$entry.task_name) `
        -Action $action -Trigger $logonTrigger `
        -Principal $principal -Settings $taskSettings `
        -Description "AI4BINANCE bounded autonomous virtual-market research loop; live orders blocked" `
        -Force | Out-Null
    return [string]$entry.task_name
}

if ($Mode -eq "RunRuntime") {
    Start-BoundedService -Service "runtime" -Command "runtime-daemon" -RestartForever
}
if ($Mode -eq "RunVirtualMarket") {
    Start-BoundedService `
        -Service "virtual-market" `
        -Command "virtual-market-daemon" `
        -RestartForever
}
if ($Mode -eq "RunVoice") {
    Start-BoundedService -Service "voice" -Command "voice-daemon"
}
if ($Mode -eq "RunValidation") {
    Start-BoundedValidation
}
if ($Mode -eq "RunAccounting") {
    Start-BoundedService `
        -Service "accounting" `
        -Command "accounting-collect-daemon" `
        -RestartForever
}
if ($Mode -eq "RunAccountingWs") {
    Start-BoundedService `
        -Service "accounting-ws" `
        -Command "accounting-ws-daemon" `
        -RestartForever
}
if ($Mode -eq "RunSkillDiscovery") {
    Start-BoundedService `
        -Service "skill-discovery" `
        -Command "skill-discovery-daemon" `
        -RestartForever
}
if ($Mode -eq "RunMarketHistory") {
    Start-BoundedService `
        -Service "market-history" `
        -Module "ai4binance.cli.market_data" `
        -Command "daemon" `
        -RestartForever
}
if ($Mode -eq "RunFuturesMultiTf") {
    Start-BoundedService `
        -Service "futures-multitf" `
        -Module "ai4binance.cli.futures_multitf" `
        -Command "daemon" `
        -RestartForever
}

if ($Mode -eq "InstallVirtualMarket") {
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw "Repository Python runtime not found: $python"
    }
    $installedVirtualMarketTask = Register-VirtualMarketTask
    Start-ScheduledTask -TaskName $installedVirtualMarketTask
    Get-ScheduledTask -TaskName $installedVirtualMarketTask |
        Select-Object TaskName, State
    exit 0
}

if ($Mode -eq "InstallMarketHistory") {
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw "Repository Python runtime not found: $python"
    }
    $marketEntry = Get-ServiceManifestEntry -Service "market-history"
    $marketPowerShell = (Get-Command powershell.exe -ErrorAction Stop).Source
    $marketAction = New-ScheduledTaskAction `
        -Execute $marketPowerShell `
        -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`" -Mode RunMarketHistory" `
        -WorkingDirectory $root
    $marketLogonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $marketPrincipal = New-ScheduledTaskPrincipal `
        -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
    $marketSettings = New-ScheduledTaskSettingsSet `
        -MultipleInstances IgnoreNew `
        -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit ([TimeSpan]::Zero) `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -StartWhenAvailable -Hidden
    Register-ScheduledTask -TaskName ([string]$marketEntry.task_name) `
        -Action $marketAction -Trigger $marketLogonTrigger `
        -Principal $marketPrincipal -Settings $marketSettings `
        -Description "AI4BINANCE public market data with resumable 30-day bootstrap" `
        -Force | Out-Null
    $multiTfEntry = Get-ServiceManifestEntry -Service "futures-multitf"
    $multiTfAction = New-ScheduledTaskAction `
        -Execute $marketPowerShell `
        -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`" -Mode RunFuturesMultiTf" `
        -WorkingDirectory $root
    Register-ScheduledTask -TaskName ([string]$multiTfEntry.task_name) `
        -Action $multiTfAction -Trigger $marketLogonTrigger `
        -Principal $marketPrincipal -Settings $marketSettings `
        -Description "AI4BINANCE resumable all-eligible-coin Multi-TF Futures research" `
        -Force | Out-Null
    Get-ScheduledTask -TaskName ([string]$marketEntry.task_name) |
        Select-Object TaskName, State
    exit 0
}

$taskName = "AI4BINANCE-ReadOnly-Runtime"
$virtualMarketTaskName = "AI4BINANCE-Virtual-Market"
$voiceTaskName = "AI4BINANCE-Voice-Assistant"
$validationTaskName = "AI4BINANCE-Research-Validation"
$accountingTaskName = "AI4BINANCE-Accounting-Collector"
$accountingWsTaskName = "AI4BINANCE-Accounting-WebSocket-Collector"
$skillDiscoveryTaskName = "AI4BINANCE-Skill-Discovery"
$marketHistoryTaskName = "AI4BINANCE-Market-History"
$futuresMultiTfTaskName = "AI4BINANCE-Futures-MultiTF-Research"
$ykbTaskName = "AI4BINANCE-YKB-Daily-Report"
$taskName = [string](Get-ServiceManifestEntry -Service "runtime").task_name
$virtualMarketTaskName = [string](Get-ServiceManifestEntry -Service "virtual-market").task_name
$accountingTaskName = [string](Get-ServiceManifestEntry -Service "accounting").task_name
$accountingWsTaskName = [string](Get-ServiceManifestEntry -Service "accounting-ws").task_name
$skillDiscoveryTaskName = [string](Get-ServiceManifestEntry -Service "skill-discovery").task_name
$marketHistoryTaskName = [string](Get-ServiceManifestEntry -Service "market-history").task_name
$futuresMultiTfTaskName = [string](Get-ServiceManifestEntry -Service "futures-multitf").task_name
$ykbTaskName = [string](Get-ServiceManifestEntry -Service "ykb-report").task_name
$credentials = Join-Path $root "secrets\bnc.env"
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

New-Item -ItemType Directory -Path $privateState, $runtimeResearchDirectory, $logDirectory -Force | Out-Null
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
    -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`" -Mode RunRuntime" `
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
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
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

$virtualMarketTaskName = Register-VirtualMarketTask

if ($EnableVoiceTask) {
    $voiceAction = New-ScheduledTaskAction `
        -Execute $powerShell `
        -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`" -Mode RunVoice" `
        -WorkingDirectory $root
    Register-ScheduledTask `
        -TaskName $voiceTaskName `
        -Action $voiceAction `
        -Trigger $trigger `
        -Principal $principal `
        -Settings $settings `
        -Description "AI4BINANCE local-interactive read-only Turkish voice assistant" `
        -Force | Out-Null
}
else {
    Unregister-ScheduledTask -TaskName $voiceTaskName -Confirm:$false -ErrorAction SilentlyContinue
}

if ($EnableValidationTask) {
    $validationAction = New-ScheduledTaskAction `
        -Execute $powerShell `
        -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`" -Mode RunValidation" `
        -WorkingDirectory $root
    Register-ScheduledTask `
        -TaskName $validationTaskName `
        -Action $validationAction `
        -Trigger $trigger `
        -Principal $principal `
        -Settings $settings `
        -Description "AI4BINANCE public archive and research validation job" `
        -Force | Out-Null
}
else {
    Unregister-ScheduledTask -TaskName $validationTaskName -Confirm:$false -ErrorAction SilentlyContinue
}

if ((Get-ServiceManifestEntry -Service "accounting").required -or $EnableAccountingTask) {
    $accountingAction = New-ScheduledTaskAction `
        -Execute $powerShell `
        -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`" -Mode RunAccounting" `
        -WorkingDirectory $root
    Register-ScheduledTask `
        -TaskName $accountingTaskName `
        -Action $accountingAction `
        -Trigger $trigger `
        -Principal $principal `
        -Settings $settings `
        -Description "AI4BINANCE read-only Spot/Futures accounting collector" `
        -Force | Out-Null
}
else {
    Unregister-ScheduledTask -TaskName $accountingTaskName -Confirm:$false -ErrorAction SilentlyContinue
}

if ((Get-ServiceManifestEntry -Service "accounting-ws").required -or $EnableAccountingWsTask) {
    $accountingWsAction = New-ScheduledTaskAction `
        -Execute $powerShell `
        -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`" -Mode RunAccountingWs" `
        -WorkingDirectory $root
    Register-ScheduledTask `
        -TaskName $accountingWsTaskName `
        -Action $accountingWsAction `
        -Trigger $trigger `
        -Principal $principal `
        -Settings $settings `
        -Description "AI4BINANCE read-only Spot/Futures WebSocket accounting collector" `
        -Force | Out-Null
}
else {
    Unregister-ScheduledTask -TaskName $accountingWsTaskName -Confirm:$false -ErrorAction SilentlyContinue
}

if ((Get-ServiceManifestEntry -Service "skill-discovery").required -or $EnableSkillDiscoveryTask) {
    $skillDiscoveryAction = New-ScheduledTaskAction `
        -Execute $powerShell `
        -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`" -Mode RunSkillDiscovery" `
        -WorkingDirectory $root
    Register-ScheduledTask `
        -TaskName $skillDiscoveryTaskName `
        -Action $skillDiscoveryAction `
        -Trigger $trigger `
        -Principal $principal `
        -Settings $settings `
        -Description "AI4BINANCE quarantine-first continuous Agent Skill discovery" `
        -Force | Out-Null
}
else {
    Unregister-ScheduledTask -TaskName $skillDiscoveryTaskName -Confirm:$false -ErrorAction SilentlyContinue
}

$marketHistoryAction = New-ScheduledTaskAction `
    -Execute $powerShell `
    -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`" -Mode RunMarketHistory" `
    -WorkingDirectory $root
Register-ScheduledTask `
    -TaskName $marketHistoryTaskName `
    -Action $marketHistoryAction `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "AI4BINANCE checksum-verified public Spot/Futures history collector" `
    -Force | Out-Null

$futuresMultiTfAction = New-ScheduledTaskAction `
    -Execute $powerShell `
    -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`" -Mode RunFuturesMultiTf" `
    -WorkingDirectory $root
Register-ScheduledTask `
    -TaskName $futuresMultiTfTaskName `
    -Action $futuresMultiTfAction `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "AI4BINANCE resumable all-eligible-coin Multi-TF Futures research" `
    -Force | Out-Null

$ykbScriptPath = Join-Path $root "scripts\ykb_daily_report.ps1"
if ($EnableYkbReportTask) {
    if (-not (Test-Path -LiteralPath $ykbScriptPath -PathType Leaf)) {
        throw "YKB report script not found: $ykbScriptPath"
    }
    & $powerShell `
        -NoProfile `
        -NonInteractive `
        -ExecutionPolicy Bypass `
        -WindowStyle Hidden `
        -File $ykbScriptPath `
        -Mode Install `
        -Symbol $YkbSymbol `
        -DailyTime $YkbDailyTime `
        -MaxReportAgeHours $YkbMaxReportAgeHours
    if ($LASTEXITCODE -ne 0) {
        throw "YKB report installation failed."
    }
}

Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State
Get-ScheduledTask -TaskName $virtualMarketTaskName -ErrorAction SilentlyContinue |
Select-Object TaskName, State
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
Get-ScheduledTask -TaskName $marketHistoryTaskName -ErrorAction SilentlyContinue |
Select-Object TaskName, State
Get-ScheduledTask -TaskName $futuresMultiTfTaskName -ErrorAction SilentlyContinue |
Select-Object TaskName, State
Get-ScheduledTask -TaskName $ykbTaskName -ErrorAction SilentlyContinue |
Select-Object TaskName, State

