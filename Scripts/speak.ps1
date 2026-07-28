param(
    [Parameter(Mandatory = $true)]
    [ValidateLength(1, 1200)]
    [string]$Text
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech
$speaker = [System.Speech.Synthesis.SpeechSynthesizer]::new()
try {
    $speaker.Speak($Text)
}
finally {
    $speaker.Dispose()
}
