param(
    [ValidateSet("Once", "RunLoop", "Install", "Status")]
    [string]$Mode = "Once",
    [int]$PollSeconds = 30
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "initialize_runtime_environment.ps1")
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$taskName = "AI4BINANCE-Primary-Local-Reasoning"
$healthPath = Join-Path $root "runtime\state\primary-local-reasoning-health.json"
$lockPath = Join-Path $root "runtime\state\primary-local-reasoning.lock"
$serverScript = Join-Path $PSScriptRoot "start_llama_server.ps1"

function Test-PrimaryListener {
    return @(
        Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue |
            Where-Object { $_.LocalAddress -in @("127.0.0.1", "::1") }
    )
}

function Write-PrimaryHealth {
    param([string]$Status, [string[]]$Blockers = @(), [int]$ExitCode = 0)
    New-Item -ItemType Directory -Path (Split-Path $healthPath -Parent) -Force | Out-Null
    $listeners = @(Test-PrimaryListener)
    [ordered]@{
        service = "primary-local-reasoning"
        role = "PRIMARY_LOCAL_REASONING_AGENT"
        model_id = "local-llamacpp-qwen3-8b"
        provider = "llama.cpp"
        runtime_model = "qwen3:8b"
        activation_mode = "BACKGROUND_ALWAYS_ON"
        endpoint = "http://127.0.0.1:8080"
        status = $Status
        updated_at = [DateTimeOffset]::UtcNow.ToString("o")
        pid = $PID
        listener_pids = @($listeners | ForEach-Object { $_.OwningProcess } | Sort-Object -Unique)
        blockers = @($Blockers)
        execution_allowed = $false
        promotion_status = "RESEARCH_ONLY"
        live_eligibility_status = "LIVE_ORDER_BLOCKED"
        exit_code = $ExitCode
    } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $healthPath -Encoding UTF8
}

function Write-PrimaryLock {
    New-Item -ItemType Directory -Path (Split-Path $lockPath -Parent) -Force | Out-Null
    $temporary = "$lockPath.$PID.tmp"
    [System.IO.File]::WriteAllText(
        $temporary,
        [string]$PID,
        [System.Text.Encoding]::ASCII
    )
    Move-Item -LiteralPath $temporary -Destination $lockPath -Force
}

function Remove-PrimaryLock {
    if (-not (Test-Path -LiteralPath $lockPath -PathType Leaf)) {
        return
    }
    try {
        $ownerPid = [int](Get-Content -LiteralPath $lockPath -Raw -Encoding ASCII)
        if ($ownerPid -eq $PID) {
            Remove-Item -LiteralPath $lockPath -Force
        }
    }
    catch {
    }
}

function Start-PrimaryProvider {
    try {
        & $serverScript | Out-Null
    } catch {
        Write-PrimaryHealth -Status "BLOCKED" -Blockers @("PRIMARY_LOCAL_REASONING_PROVIDER_START_FAILED") -ExitCode 2
        return $false
    }
    if (@(Test-PrimaryListener).Count -eq 0) {
        Write-PrimaryHealth -Status "BLOCKED" -Blockers @("PRIMARY_LOCAL_REASONING_PROVIDER_UNAVAILABLE") -ExitCode 2
        return $false
    }
    Write-PrimaryHealth -Status "RUNNING"
    return $true
}

if ($Mode -eq "Status") {
    if (Test-Path -LiteralPath $healthPath -PathType Leaf) {
        Get-Content -LiteralPath $healthPath -Raw
        exit 0
    }
    Write-Output "PRIMARY_LOCAL_REASONING_HEALTH_MISSING"
    exit 2
}

if ($Mode -eq "Install") {
    $powerShell = (Get-Command powershell.exe -ErrorAction Stop).Source
    $action = New-ScheduledTaskAction -Execute $powerShell -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`" -Mode RunLoop" -WorkingDirectory $root
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -Hidden
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "AI4BINANCE local-only PRIMARY_LOCAL_REASONING_AGENT; advisory-only and live orders blocked" -Force | Out-Null
    Start-ScheduledTask -TaskName $taskName
    Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State
    exit 0
}

if ($Mode -eq "Once") { exit $(if (Start-PrimaryProvider) { 0 } else { 2 }) }

$mutex = [System.Threading.Mutex]::new($false, "Local\AI4BINANCE-Primary-Local-Reasoning")
$hasHandle = $false
try {
    $hasHandle = $mutex.WaitOne(0)
    if (-not $hasHandle) { exit 0 }
    Write-PrimaryLock
    while ($true) {
        [void](Start-PrimaryProvider)
        Start-Sleep -Seconds $PollSeconds
    }
}
finally {
    Remove-PrimaryLock
    if ($hasHandle) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
