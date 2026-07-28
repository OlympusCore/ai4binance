$ErrorActionPreference = "Stop"
$taskNames = @("AI4BINANCE-ReadOnly-Runtime", "AI4BINANCE-Voice-Assistant")
foreach ($taskName in $taskNames) {
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($null -ne $task) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    }
}
Write-Output "AI4BINANCE startup task is absent."
