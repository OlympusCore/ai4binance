param(
    [ValidateSet("RunIfStale", "RunNow", "RunLoop", "Install", "Status")]
    [string]$Mode = "RunIfStale",
    [string]$Symbol = "HOTUSDT",
    [string]$DailyTime = "09:00",
    [int]$MaxReportAgeHours = 4,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "initialize_runtime_environment.ps1")
$env:PYTHONDONTWRITEBYTECODE = "1"
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$stateDirectory = Join-Path $root "runtime\state"
$logDirectory = Join-Path $root "runtime\logs\services"
$tempDirectory = Join-Path $root "runtime\tmp\ykb"
$latestReportPath = Join-Path $root "runtime\artifacts\user_reports\ykb\latest.json"
$healthPath = Join-Path $stateDirectory "ykb_report_health.json"
$stdoutPath = Join-Path $logDirectory "ykb-report.stdout.log"
$stderrPath = Join-Path $logDirectory "ykb-report.stderr.log"
$taskName = "AI4BINANCE-YKB-Daily-Report"
$srcPath = Join-Path $root "src"
$script:LogFilesInitialized = $false
if ([string]::IsNullOrWhiteSpace($env:PYTHONPATH)) {
    $env:PYTHONPATH = $srcPath
}
elseif (-not (($env:PYTHONPATH -split ';') -contains $srcPath)) {
    $env:PYTHONPATH = "$srcPath;$env:PYTHONPATH"
}

function Get-IstanbulNow {
    $zone = [TimeZoneInfo]::FindSystemTimeZoneById("Turkey Standard Time")
    return [TimeZoneInfo]::ConvertTime([DateTimeOffset]::UtcNow, $zone)
}

function Convert-ToIstanbulDate {
    param([Parameter(Mandatory = $true)][object]$Value)
    if ($null -eq $Value) {
        throw "observed_at is missing"
    }
    $zone = [TimeZoneInfo]::FindSystemTimeZoneById("Turkey Standard Time")
    if ($Value -is [DateTimeOffset]) {
        $parsed = ([DateTimeOffset]$Value).ToUniversalTime()
    }
    elseif ($Value -is [DateTime]) {
        $parsed = ([DateTimeOffset]([DateTime]$Value)).ToUniversalTime()
    }
    else {
        $parsed = [DateTimeOffset]::Parse([string]$Value).ToUniversalTime()
    }
    return [TimeZoneInfo]::ConvertTime($parsed, $zone)
}

function Read-LatestReportState {
    if (-not (Test-Path -LiteralPath $latestReportPath -PathType Leaf)) {
        return [pscustomobject]@{
            Fresh      = $false
            Reason     = "ykb_report_MISSING"
            ObservedAt = ""
            AgeHours   = $null
        }
    }
    try {
        $payload = Get-Content -LiteralPath $latestReportPath -Raw | ConvertFrom-Json
        $observedAt = Convert-ToIstanbulDate $payload.observed_at
        $now = Get-IstanbulNow
        $ageHours = ($now - $observedAt).TotalHours
        $sameIstanbulDate = $observedAt.Date -eq $now.Date
        $futureTimestamp = $ageHours -lt 0
        $fresh = $sameIstanbulDate -and (-not $futureTimestamp) -and $ageHours -le $MaxReportAgeHours
        $reason = if ($fresh) {
            "ykb_report_FRESH"
        }
        elseif ($futureTimestamp) {
            "ykb_report_FUTURE_TIMESTAMP"
        }
        else {
            "ykb_report_STALE"
        }
        return [pscustomobject]@{
            Fresh      = $fresh
            Reason     = $reason
            ObservedAt = $observedAt.ToString("o")
            AgeHours   = [math]::Round($ageHours, 3)
        }
    }
    catch {
        return [pscustomobject]@{
            Fresh      = $false
            Reason     = "ykb_report_INVALID"
            ObservedAt = ""
            AgeHours   = $null
        }
    }
}

function Sync-LatestHumanReport {
    if (-not (Test-Path -LiteralPath $latestReportPath -PathType Leaf)) {
        return [pscustomobject]@{
            Synced         = $false
            Reason         = "ykb_report_MISSING"
            ReportId       = ""
            Status         = ""
            Blockers       = @()
            ObservedAt     = ""
            MarkdownPath   = ""
            LatestMarkdown = ""
        }
    }
    try {
        $payload = Get-Content -LiteralPath $latestReportPath -Raw | ConvertFrom-Json
        $markdownPath = [string]$payload.latest_markdown_path
        if ([string]::IsNullOrWhiteSpace($markdownPath)) {
            $markdownPath = [string]$payload.markdown_path
        }
        if ([string]::IsNullOrWhiteSpace($markdownPath)) {
            throw "markdown_path missing"
        }
        if (-not (Test-Path -LiteralPath $markdownPath -PathType Leaf)) {
            throw "markdown_path not found: $markdownPath"
        }
        return [pscustomobject]@{
            Synced         = $true
            Reason         = "YKB_HUMAN_REPORT_READY"
            ReportId       = [string]$payload.report_id
            Status         = [string]$payload.status
            Blockers       = @($payload.blockers)
            ObservedAt     = [string]$payload.observed_at
            MarkdownPath   = $markdownPath
            LatestMarkdown = $markdownPath
        }
    }
    catch {
        return [pscustomobject]@{
            Synced         = $false
            Reason         = "YKB_HUMAN_REPORT_SYNC_FAILED"
            ReportId       = ""
            Status         = ""
            Blockers       = @()
            ObservedAt     = ""
            MarkdownPath   = ""
            LatestMarkdown = ""
        }
    }
}

function Get-RecentYkbReports {
    param([int]$MaxItems = 3)
    $reportDirectory = Join-Path $root "runtime\reports\ykb"
    if (-not (Test-Path -LiteralPath $reportDirectory -PathType Container)) {
        return @()
    }
    $history = [System.Collections.Generic.List[object]]::new()
    $culture = [System.Globalization.CultureInfo]::InvariantCulture
    Get-ChildItem -LiteralPath $reportDirectory -File -Filter "ykb_report_*_tr.md" |
    Sort-Object Name -Descending |
    ForEach-Object {
        if ($_.Name -match '^ykb_report_(\d{8}T\d{6})_TR\.md$') {
            $stamp = $Matches[1]
            $observedAt = $stamp
            try {
                $parsed = [DateTimeOffset]::ParseExact(
                    "$stamp+03:00",
                    "yyyyMMdd'T'HHmmsszzz",
                    $culture
                )
                $observedAt = $parsed.ToString("o")
            }
            catch {
                $observedAt = $stamp
            }
            $history.Add(
                [pscustomobject]@{
                    ObservedAt = $observedAt
                    FileName   = $_.Name
                }
            )
        }
    }
    return @($history | Select-Object -First $MaxItems)
}

function Write-Health {
    param(
        [Parameter(Mandatory = $true)][string]$Status,
        [AllowEmptyCollection()][string[]]$Blockers = @(),
        [int]$RefreshExitCode = 0,
        [int]$ReportExitCode = 0,
        [string]$ReportStatus = "NOT_EVALUATED",
        [AllowEmptyCollection()][string[]]$ReportBlockers = @(),
        [string]$LastReportObservedAt = "",
        [string]$LatestMarkdownPath = ""
    )
    New-Item -ItemType Directory -Path $stateDirectory -Force | Out-Null
    [string[]]$normalizedBlockers = @(
        $Blockers | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    )
    [string[]]$normalizedReportBlockers = @(
        $ReportBlockers | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    )
    $payload = [ordered]@{
        service                   = "ykb-report"
        status                    = $Status
        updated_at                = [DateTimeOffset]::UtcNow.ToString("o")
        task_name                 = $taskName
        symbol                    = $Symbol.ToUpperInvariant()
        latest_report_path        = $latestReportPath
        latest_markdown_path      = $LatestMarkdownPath
        latest_report_observed_at = $LastReportObservedAt
        refresh_exit_code         = $RefreshExitCode
        report_exit_code          = $ReportExitCode
        report_status             = $ReportStatus
        report_blockers           = $normalizedReportBlockers
        blockers                  = $normalizedBlockers
        execution_allowed         = $false
        live_eligibility_status   = "LIVE_ORDER_BLOCKED"
    }
    $temporary = "$healthPath.tmp"
    $payload | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $healthPath -Force
}

function Get-StartupLauncherPath {
    $startupFolder = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
    if (-not (Test-Path -LiteralPath $startupFolder -PathType Container)) {
        New-Item -ItemType Directory -Path $startupFolder -Force | Out-Null
    }
    return Join-Path $startupFolder "AI4BINANCE-YKB-Daily-Report.cmd"
}

function Write-StartupLauncher {
    param(
        [Parameter(Mandatory = $true)][string]$LauncherPath
    )

    $launcher = @(
        "@echo off",
        "setlocal",
        "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`" -Mode RunLoop -Symbol `"$Symbol`" -MaxReportAgeHours $MaxReportAgeHours",
        "endlocal"
    ) -join [Environment]::NewLine
    Set-Content -LiteralPath $LauncherPath -Value $launcher -Encoding ASCII
}

function Remove-StartupLauncher {
    $launcherPath = Get-StartupLauncherPath
    Remove-Item -LiteralPath $launcherPath -Force -ErrorAction SilentlyContinue
}

function Test-YkbScheduledTaskConfiguration {
    param(
        [Parameter(Mandatory = $true)][object]$Task,
        [Parameter(Mandatory = $true)][string]$PowerShellPath,
        [Parameter(Mandatory = $true)][string]$ExpectedArguments
    )

    try {
        $actions = @($Task.Actions)
        if ($actions.Count -ne 1) {
            return $false
        }
        $action = $actions[0]
        if (-not [string]::Equals(
                [string]$action.Execute,
                $PowerShellPath,
                [System.StringComparison]::OrdinalIgnoreCase
            )) {
            return $false
        }
        if ([string]$action.Arguments -ne $ExpectedArguments) {
            return $false
        }
        if (-not [string]::Equals(
                [string]$action.WorkingDirectory,
                $root,
                [System.StringComparison]::OrdinalIgnoreCase
            )) {
            return $false
        }

        $currentIdentity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        $expectedUserIds = @($env:USERNAME, $currentIdentity)
        $principalMatches = @(
            $expectedUserIds | Where-Object {
                [string]::Equals(
                    [string]$_,
                    [string]$Task.Principal.UserId,
                    [System.StringComparison]::OrdinalIgnoreCase
                )
            }
        ).Count -gt 0
        if (-not $principalMatches) {
            return $false
        }
        if ([string]$Task.Principal.LogonType -ne "Interactive") {
            return $false
        }
        if ([string]$Task.Principal.RunLevel -ne "Limited") {
            return $false
        }
        if ([string]$Task.Settings.MultipleInstances -ne "IgnoreNew") {
            return $false
        }
        if (-not [bool]$Task.Settings.StartWhenAvailable) {
            return $false
        }
        if (-not [bool]$Task.Settings.Hidden) {
            return $false
        }

        $triggers = @($Task.Triggers)
        $logonTriggers = @(
            $triggers | Where-Object {
                $_.CimClass.CimClassName -eq "MSFT_TaskLogonTrigger"
            }
        )
        $dailyTriggers = @(
            $triggers | Where-Object {
                $_.CimClass.CimClassName -eq "MSFT_TaskDailyTrigger"
            }
        )
        if ($triggers.Count -ne 25) {
            return $false
        }
        if ($logonTriggers.Count -ne 1 -or $dailyTriggers.Count -ne 24) {
            return $false
        }
        if (@($triggers | Where-Object { -not $_.Enabled }).Count -gt 0) {
            return $false
        }
        $logonUserMatches = @(
            $expectedUserIds | Where-Object {
                [string]::Equals(
                    [string]$_,
                    [string]$logonTriggers[0].UserId,
                    [System.StringComparison]::OrdinalIgnoreCase
                )
            }
        ).Count -gt 0
        if (-not $logonUserMatches) {
            return $false
        }
        if (@($dailyTriggers | Where-Object { $_.DaysInterval -ne 1 }).Count -gt 0) {
            return $false
        }
        $dailyHours = @(
            $dailyTriggers |
            ForEach-Object {
                ([DateTimeOffset]::Parse([string]$_.StartBoundary)).Hour
            } |
            Sort-Object -Unique
        )
        return ($dailyHours -join ",") -eq ((0..23) -join ",")
    }
    catch {
        return $false
    }
}

function Initialize-Utf8Logs {
    if ($script:LogFilesInitialized) {
        return
    }
    New-Item -ItemType Directory -Path $stateDirectory, $logDirectory -Force | Out-Null
    $utf8 = [System.Text.UTF8Encoding]::new($true)
    [System.IO.File]::WriteAllText($stdoutPath, "", $utf8)
    [System.IO.File]::WriteAllText($stderrPath, "", $utf8)
    $script:LogFilesInitialized = $true
}

function Invoke-PythonUtf8Command {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$ArgumentList
    )

    $captureDirectory = Join-Path (
        $tempDirectory
    ) ("capture-" + [guid]::NewGuid().ToString("N"))
    $stdoutTemp = Join-Path $captureDirectory "stdout.tmp"
    $stderrTemp = Join-Path $captureDirectory "stderr.tmp"
    $pythonArguments = @("-B") + $ArgumentList
    try {
        New-Item -ItemType Directory -Path $captureDirectory -Force | Out-Null
        $process = Start-Process `
            -FilePath $python `
            -ArgumentList $pythonArguments `
            -WorkingDirectory $root `
            -WindowStyle Hidden `
            -PassThru `
            -Wait `
            -RedirectStandardOutput $stdoutTemp `
            -RedirectStandardError $stderrTemp

        if (Test-Path -LiteralPath $stdoutTemp) {
            $stdoutContent = Get-Content -LiteralPath $stdoutTemp -Raw -Encoding UTF8
            if (-not [string]::IsNullOrWhiteSpace($stdoutContent)) {
                [System.IO.File]::AppendAllText($stdoutPath, $stdoutContent, [System.Text.UTF8Encoding]::new($true))
            }
        }

        if (Test-Path -LiteralPath $stderrTemp) {
            $stderrContent = Get-Content -LiteralPath $stderrTemp -Raw -Encoding UTF8
            if (-not [string]::IsNullOrWhiteSpace($stderrContent)) {
                [System.IO.File]::AppendAllText($stderrPath, $stderrContent, [System.Text.UTF8Encoding]::new($true))
            }
        }

        return [int]$process.ExitCode
    }
    finally {
        Remove-Item `
            -LiteralPath $captureDirectory `
            -Recurse `
            -Force `
            -Confirm:$false `
            -ErrorAction SilentlyContinue
    }
}

function Invoke-YkbRefreshAndReport {
    Initialize-Utf8Logs
    New-Item -ItemType Directory -Path $stateDirectory, $logDirectory -Force | Out-Null
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        Write-Health -Status "FAILED" -Blockers @("REPO_PYTHON_MISSING")
        return 1
    }
    Push-Location -LiteralPath $root
    try {
        $refreshExitCode = Invoke-PythonUtf8Command -ArgumentList @(
            "-m",
            "ai4binance.cli",
            "runtime-research-refresh-once",
            "--format",
            "json"
        )
        $reportExitCode = Invoke-PythonUtf8Command -ArgumentList @(
            "-m",
            "ai4binance.cli",
            "ykb-report",
            "--symbol",
            $Symbol,
            "--format",
            "json"
        )
    }
    finally {
        Pop-Location
    }
    $state = Read-LatestReportState
    $humanReport = Sync-LatestHumanReport
    $operationalBlockers = [System.Collections.Generic.List[string]]::new()
    if ($refreshExitCode -ne 0) {
        $operationalBlockers.Add("RUNTIME_RESEARCH_REFRESH_WITH_BLOCKERS")
    }
    if ($reportExitCode -notin @(0, 2)) {
        $operationalBlockers.Add("YKB_REPORT_COMMAND_FAILED")
    }
    if (
        $reportExitCode -eq 2 -and
        $humanReport.Status -ne "RUNNING_WITH_BLOCKERS"
    ) {
        $operationalBlockers.Add("YKB_REPORT_EXIT_STATUS_MISMATCH")
    }
    if (-not $state.Fresh) {
        $operationalBlockers.Add([string]$state.Reason)
    }
    if (-not $humanReport.Synced) {
        $operationalBlockers.Add([string]$humanReport.Reason)
    }
    $status = if ($state.Fresh -and $operationalBlockers.Count -eq 0) {
        "READY"
    }
    elseif ($state.Fresh) {
        "RUNNING_WITH_BLOCKERS"
    }
    else {
        "FAILED"
    }
    Write-Health `
        -Status $status `
        -Blockers $operationalBlockers.ToArray() `
        -RefreshExitCode $refreshExitCode `
        -ReportExitCode $reportExitCode `
        -ReportStatus ([string]$humanReport.Status) `
        -ReportBlockers @($humanReport.Blockers) `
        -LastReportObservedAt ([string]$state.ObservedAt) `
        -LatestMarkdownPath ([string]$humanReport.LatestMarkdown)
    if ($humanReport.Synced) {
        Write-Output "YKB_HUMAN_REPORT_READY"
        Write-Output "report_id=$($humanReport.ReportId)"
        Write-Output "status=$($humanReport.Status)"
        Write-Output "observed_at=$($humanReport.ObservedAt)"
        Write-Output "markdown_path=$($humanReport.MarkdownPath)"
        Write-Output "latest_markdown_path=$($humanReport.LatestMarkdown)"
    }
    return $(if ($status -eq "READY") { 0 } else { 1 })
}

function Start-YkbLoop {
    $mutex = [System.Threading.Mutex]::new($false, "Local\AI4BINANCE-YKB-Daily-Report")
    $hasHandle = $false
    try {
        $hasHandle = $mutex.WaitOne(0)
        if (-not $hasHandle) {
            return 0
        }
        while ($true) {
            try {
                [void](Invoke-YkbRefreshAndReport)
            }
            catch {
                Write-Health -Status "FAILED" -Blockers @("YKB_AUTOSTART_LOOP_UNHANDLED_EXCEPTION")
            }
            Start-Sleep -Seconds 3600
        }
    }
    finally {
        if ($hasHandle) {
            try {
                $mutex.ReleaseMutex() | Out-Null
            }
            catch {
            }
        }
        $mutex.Dispose()
    }
}

if ($Mode -eq "Status") {
    $state = Read-LatestReportState
    $humanReport = Sync-LatestHumanReport
    $recentReports = Get-RecentYkbReports -MaxItems 3
    [pscustomobject]@{
        TaskName              = $taskName
        Fresh                 = $state.Fresh
        Reason                = $state.Reason
        ObservedAt            = $state.ObservedAt
        AgeHours              = $state.AgeHours
        MaxReportAgeHours     = $MaxReportAgeHours
        LatestReportPath      = $latestReportPath
        LatestMarkdownPath    = $humanReport.LatestMarkdown
        RecentReportHistory   = @(
            $recentReports |
            ForEach-Object { "$($_.ObservedAt) | $($_.FileName)" }
        )
        HealthPath            = $healthPath
        ExecutionAllowed      = $false
        LiveEligibilityStatus = "LIVE_ORDER_BLOCKED"
    } | Format-List
    exit $(if ($state.Fresh) { 0 } else { 2 })
}

if ($Mode -eq "Install") {
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw "Repository Python runtime not found: $python"
    }
    $launcherPath = Get-StartupLauncherPath
    $powerShell = ""
    $scriptPath = $PSCommandPath
    $taskArguments = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$scriptPath`" -Mode RunIfStale -Symbol `"$Symbol`" -MaxReportAgeHours $MaxReportAgeHours"
    try {
        $powerShell = (Get-Command powershell.exe -ErrorAction Stop).Source
        $action = New-ScheduledTaskAction `
            -Execute $powerShell `
            -Argument $taskArguments `
            -WorkingDirectory $root
        $logonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
        $dailyAnchor = [DateTime]::Parse($DailyTime)
        $staleCheckTriggers = for ($offset = 0; $offset -lt 24; $offset++) {
            New-ScheduledTaskTrigger -Daily -At ($dailyAnchor.AddHours($offset))
        }
        $principal = New-ScheduledTaskPrincipal `
            -UserId $env:USERNAME `
            -LogonType Interactive `
            -RunLevel Limited
        $settings = New-ScheduledTaskSettingsSet `
            -MultipleInstances IgnoreNew `
            -ExecutionTimeLimit (New-TimeSpan -Hours 6) `
            -AllowStartIfOnBatteries `
            -DontStopIfGoingOnBatteries `
            -StartWhenAvailable `
            -Hidden
        Register-ScheduledTask `
            -TaskName $taskName `
            -Action $action `
            -Trigger (@($logonTrigger) + $staleCheckTriggers) `
            -Principal $principal `
            -Settings $settings `
            -Description "AI4BINANCE local-only YKB report publisher; checks hourly while session is active and refreshes when stale" `
            -Force | Out-Null
        Remove-StartupLauncher
        Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State
        exit 0
    }
    catch {
        $registrationError = $_.Exception.Message
        $existingTask = Get-ScheduledTask `
            -TaskName $taskName `
            -ErrorAction SilentlyContinue
        $existingTaskMatches = (
            $null -ne $existingTask -and
            -not [string]::IsNullOrWhiteSpace($powerShell) -and
            (Test-YkbScheduledTaskConfiguration `
                -Task $existingTask `
                -PowerShellPath $powerShell `
                -ExpectedArguments $taskArguments)
        )
        if ($existingTaskMatches) {
            Remove-StartupLauncher
            Write-Output "YKB_SCHEDULED_TASK_READY"
            Write-Output "task_name=$taskName"
            Write-Output "mode=RunIfStale"
            Write-Output "status=EXISTING_TASK_VERIFIED"
            exit 0
        }
        Write-StartupLauncher -LauncherPath $launcherPath
        Write-Output "YKB_STARTUP_LAUNCHER_READY"
        Write-Output "launcher_path=$launcherPath"
        Write-Output "task_name=$taskName"
        Write-Output "mode=RunLoop"
        Write-Output "status=FALLBACK_INSTALLED"
        Write-Output "registration_error=$registrationError"
        exit 0
    }
}

if ($Mode -eq "RunNow") {
    exit (Invoke-YkbRefreshAndReport)
}

if ($Mode -eq "RunLoop") {
    exit (Start-YkbLoop)
}

$state = Read-LatestReportState
if ($state.Fresh -and -not $Force) {
    $humanReport = Sync-LatestHumanReport
    $status = if ($humanReport.Synced) { "READY" } else { "DEGRADED" }
    $blockers = if ($humanReport.Synced) { @() } else { @($humanReport.Reason) }
    Write-Health `
        -Status $status `
        -Blockers $blockers `
        -ReportStatus ([string]$humanReport.Status) `
        -ReportBlockers @($humanReport.Blockers) `
        -LastReportObservedAt ([string]$state.ObservedAt) `
        -LatestMarkdownPath ([string]$humanReport.LatestMarkdown)
    Write-Output "ykb_report_FRESH"
    exit $(if ($humanReport.Synced) { 0 } else { 1 })
}

exit (Invoke-YkbRefreshAndReport)


