param(
    [Parameter(Mandatory = $true)]
    [ValidateLength(1, 1200)]
    [string]$Text
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "initialize_runtime_environment.ps1")
Add-Type -AssemblyName System.Speech
$speaker = [System.Speech.Synthesis.SpeechSynthesizer]::new()
try {
    $speaker.Speak($Text)
}
finally {
    $speaker.Dispose()
}
