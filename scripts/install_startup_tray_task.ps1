param(
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$trayScript = Join-Path $PSScriptRoot "startup_tray_host.ps1"
$taskName = "AI4BINANCE-Startup-Tray"

if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    [pscustomobject]@{
        task_name = $taskName
        status = "UNINSTALLED"
        execution_allowed = $false
        live_eligibility_status = "LIVE_ORDER_BLOCKED"
    } | ConvertTo-Json -Compress
    exit 0
}

if (-not (Test-Path -LiteralPath $trayScript -PathType Leaf)) {
    throw "Tray host script not found: $trayScript"
}

$powerShell = (Get-Command powershell.exe -ErrorAction Stop).Source
$action = New-ScheduledTaskAction `
    -Execute $powerShell `
    -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$trayScript`" -TrayIconPath `"H:\GoogleDrive\_archive\icon_set\icon\sync.ico`"" `
    -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Days 3650) `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -Hidden

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "AI4BINANCE tray host for opening background runtime status from the notification area." `
    -Force | Out-Null

$task = Get-ScheduledTask -TaskName $taskName
[pscustomobject]@{
    task_name = $task.TaskName
    state = $task.State
    startup_trigger = "AtLogOn"
    tray_visible = $true
    execution_allowed = $false
    live_eligibility_status = "LIVE_ORDER_BLOCKED"
} | ConvertTo-Json -Compress
