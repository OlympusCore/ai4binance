param(
    [switch]$SkipTimeSync,
    [switch]$SkipDefenderExclusion,
    [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$llamaRoot = Join-Path $root "tools\llama.cpp"

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
}

function Write-Result {
    param([Parameter(Mandatory = $true)][hashtable]$Payload)
    $json = $Payload | ConvertTo-Json -Compress
    if ($OutputPath.Trim()) {
        $parent = Split-Path -Parent $OutputPath
        if ($parent) {
            New-Item -ItemType Directory -Path $parent -Force | Out-Null
        }
        $json | Set-Content -LiteralPath $OutputPath -Encoding UTF8
    }
    $json
}

$isAdmin = Test-IsAdministrator
$results = @{
    command = "apply-admin-hardening"
    administrator = $isAdmin
    time_sync = "SKIPPED"
    defender_exclusion = "SKIPPED"
    norton_allowlist = "MANUAL_PRODUCT_UI_REQUIRED"
    execution_allowed = $false
    live_eligibility_status = "LIVE_ORDER_BLOCKED"
}

if (-not $isAdmin) {
    $results.time_sync = "BLOCKED_ADMIN_REQUIRED"
    $results.defender_exclusion = "BLOCKED_ADMIN_REQUIRED"
    Write-Result -Payload $results
    exit 2
}

if (-not $SkipTimeSync) {
    Set-Service -Name W32Time -StartupType Automatic
    Start-Service -Name W32Time -ErrorAction SilentlyContinue
    & w32tm.exe /config /manualpeerlist:"time.windows.com,0x9 pool.ntp.org,0x9" /syncfromflags:manual /update | Out-Null
    & w32tm.exe /resync /force | Out-Null
    $results.time_sync = "APPLIED"
}

if (-not $SkipDefenderExclusion) {
    if (Test-Path -LiteralPath $llamaRoot -PathType Container) {
        Add-MpPreference -ExclusionPath $llamaRoot
        $results.defender_exclusion = "APPLIED"
    }
    else {
        $results.defender_exclusion = "BLOCKED_LLAMA_ROOT_MISSING"
    }
}

Write-Result -Payload $results
