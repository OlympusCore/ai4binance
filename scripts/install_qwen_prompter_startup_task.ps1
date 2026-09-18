param(
    [string]$Model = $(if ($env:AI4BINANCE_PROMPTER_MODEL) { $env:AI4BINANCE_PROMPTER_MODEL } else { "qwen3:8b" }),
    [string]$TaskName = "AI4BINANCE-Qwen3-Prompter",
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$prompterScript = Join-Path $PSScriptRoot "start_qwen_prompter.ps1"

if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    [pscustomobject]@{
        task_name = $TaskName
        status = "UNINSTALLED"
        execution_allowed = $false
        live_eligibility_status = "LIVE_ORDER_BLOCKED"
    } | ConvertTo-Json -Compress
    exit 0
}

if (-not (Test-Path -LiteralPath $prompterScript -PathType Leaf)) {
    throw "Prompter script not found: $prompterScript"
}

$powerShell = (Get-Command powershell.exe -ErrorAction Stop).Source
$action = New-ScheduledTaskAction `
    -Execute $powerShell `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$prompterScript`" -Model `"$Model`"" `
    -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Days 3650)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Visible AI4BINANCE advisory-only llama.cpp Qwen3 prompter" `
    -Force | Out-Null

$task = Get-ScheduledTask -TaskName $TaskName
[pscustomobject]@{
    task_name = $task.TaskName
    state = $task.State
    model = $Model
    visible_prompt = $true
    startup_trigger = "AtLogOn"
    execution_allowed = $false
    live_eligibility_status = "LIVE_ORDER_BLOCKED"
} | ConvertTo-Json -Compress
