param(
    [int]$IntervalSeconds = 300,
    [switch]$StartNow
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$scriptPath = Join-Path $root "scripts\repository_governance_monitor.ps1"
$taskName = "AI4BINANCE-Repository-Governance-Monitor"

if ($IntervalSeconds -lt 30) {
    throw "IntervalSeconds must be at least 30."
}
if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
    throw "Repository governance monitor script not found: $scriptPath"
}

$powerShell = if (Get-Command pwsh.exe -ErrorAction SilentlyContinue) {
    (Get-Command pwsh.exe -ErrorAction Stop).Source
} else {
    (Get-Command powershell.exe -ErrorAction Stop).Source
}
$action = New-ScheduledTaskAction `
    -Execute $powerShell `
    -Argument "-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`" -IntervalSeconds $IntervalSeconds" `
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
    -Description "AI4BINANCE deterministic repository knowledge governance monitor; report-only and live-order blocked." `
    -Force | Out-Null

if ($StartNow) {
    Start-ScheduledTask -TaskName $taskName
}

Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State
