param(
    [ValidateSet("Once", "RunLoop", "Install", "Status")]
    [string]$Mode = "Once",
    [Parameter(Mandatory = $true)]
    [string]$SourcePath,
    [int]$PollSeconds = 60,
    [switch]$IncludeExisting
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "initialize_runtime_environment.ps1")
$env:PYTHONDONTWRITEBYTECODE = "1"
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$stateDirectory = Join-Path $root "runtime\state"
$healthPath = Join-Path $stateDirectory "internal-radar-health.json"
$radarLatestPath = Join-Path $root "runtime\artifacts\internal_radar\latest.json"
$ykbScriptPath = Join-Path $root "scripts\ykb_daily_report.ps1"
$taskName = "AI4BINANCE-Internal-Image-Radar"

function Get-IstanbulNow {
    $zone = [TimeZoneInfo]::FindSystemTimeZoneById("Turkey Standard Time")
    return [TimeZoneInfo]::ConvertTime([DateTimeOffset]::UtcNow, $zone)
}

function Write-Health {
    param([string]$Status, [string[]]$Blockers, [int]$ExitCode = 0)
    New-Item -ItemType Directory -Path $stateDirectory -Force | Out-Null
    [ordered]@{
        schema_version = 1
        service = "internal-radar"
        status = $Status
        updated_at = (Get-IstanbulNow).ToString("o")
        last_success_at = if ($ExitCode -eq 0) { (Get-IstanbulNow).ToString("o") } else { "" }
        exit_code = $ExitCode
        blockers = @($Blockers)
        execution_allowed = $false
        live_eligibility_status = "LIVE_ORDER_BLOCKED"
    } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $healthPath -Encoding UTF8
}

function Invoke-InternalRadar {
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        Write-Health -Status "FAILED" -Blockers @("REPO_PYTHON_MISSING") -ExitCode 1
        return 1
    }
    if (-not (Test-Path -LiteralPath $SourcePath -PathType Container)) {
        Write-Health -Status "FAILED" -Blockers @("INTERNAL_RADAR_SOURCE_UNAVAILABLE") -ExitCode 1
        return 1
    }
    $env:AI4BINANCE_INTERNAL_RADAR_SOURCE = (Resolve-Path -LiteralPath $SourcePath).Path
    if ($IncludeExisting) {
        $env:AI4BINANCE_INTERNAL_RADAR_INCLUDE_EXISTING = "1"
    }
    else {
        Remove-Item Env:AI4BINANCE_INTERNAL_RADAR_INCLUDE_EXISTING -ErrorAction SilentlyContinue
    }
    Push-Location -LiteralPath $root
    try {
        & $python -B -m ai4binance.internal_radar
        $exitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
    $blockers = [System.Collections.Generic.List[string]]::new()
    $blockers.Add("VISION_ANALYZER_NOT_CONFIGURED")
    $newCandidateCount = 0
    try {
        $radar = Get-Content -LiteralPath $radarLatestPath -Raw | ConvertFrom-Json
        $newCandidateCount = [int]$radar.new_candidate_count
    }
    catch {
        $blockers.Add("INTERNAL_RADAR_LATEST_EVIDENCE_UNAVAILABLE")
    }
    if ($newCandidateCount -gt 0) {
        if (-not (Test-Path -LiteralPath $ykbScriptPath -PathType Leaf)) {
            $blockers.Add("YKB_REPORT_SCRIPT_UNAVAILABLE")
        }
        else {
            & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File $ykbScriptPath -Mode RunNow
            if ($LASTEXITCODE -ne 0) {
                $blockers.Add("YKB_REPORT_REFRESH_WITH_BLOCKERS")
            }
        }
    }
    $status = if ($exitCode -eq 0 -and $blockers.Count -eq 0) { "READY" } else { "RUNNING_WITH_BLOCKERS" }
    Write-Health -Status $status -Blockers $blockers.ToArray() -ExitCode $exitCode
    return $exitCode
}

if ($Mode -eq "Once") { exit (Invoke-InternalRadar) }

if ($Mode -eq "RunLoop") {
    $mutex = [System.Threading.Mutex]::new($false, "Local\AI4BINANCE-Internal-Image-Radar")
    $hasHandle = $false
    try {
        $hasHandle = $mutex.WaitOne(0)
        if (-not $hasHandle) { exit 0 }
        while ($true) {
            [void](Invoke-InternalRadar)
            Start-Sleep -Seconds $PollSeconds
        }
    }
    finally {
        if ($hasHandle) { $mutex.ReleaseMutex() }
        $mutex.Dispose()
    }
}

if ($Mode -eq "Status") {
    if (Test-Path -LiteralPath $healthPath -PathType Leaf) {
        Get-Content -LiteralPath $healthPath -Raw | ConvertFrom-Json | Format-List
        exit 0
    }
    Write-Output "INTERNAL_RADAR_HEALTH_MISSING"
    exit 2
}

if (-not (Test-Path -LiteralPath $SourcePath -PathType Container)) {
    throw "Internal radar source directory not found: $SourcePath"
}
$powerShell = (Get-Command powershell.exe -ErrorAction Stop).Source
$arguments = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`" -Mode RunLoop -SourcePath `"$((Resolve-Path -LiteralPath $SourcePath).Path)`" -PollSeconds $PollSeconds"
$action = New-ScheduledTaskAction -Execute $powerShell -Argument $arguments -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -Hidden
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "AI4BINANCE local-only internal image radar; source images remain outside repository" -Force | Out-Null
Start-ScheduledTask -TaskName $taskName
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State
