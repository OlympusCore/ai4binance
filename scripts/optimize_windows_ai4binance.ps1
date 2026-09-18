param(
    [switch]$Apply,
    [switch]$SkipPowerPlan,
    [switch]$SkipLongPaths,
    [switch]$SkipDefenderExclusion,
    [switch]$SkipIndexingOptimization,
    [switch]$SkipTimeZone,
    [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$highChurnRelativePaths = @(
    ".venv",
    "artifacts",
    "backtest",
    "data",
    "logs",
    "models",
    "reports",
    "runtime",
    "runtime\\skill_staging",
    "state",
    "tools"
)

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
}

function Write-Result {
    param([Parameter(Mandatory = $true)][hashtable]$Payload)
    $json = $Payload | ConvertTo-Json -Depth 6 -Compress
    if ($OutputPath.Trim()) {
        $parent = Split-Path -Parent $OutputPath
        if ($parent) {
            New-Item -ItemType Directory -Path $parent -Force | Out-Null
        }
        $json | Set-Content -LiteralPath $OutputPath -Encoding UTF8
    }
    $json
}

function Get-AntiVirusProducts {
    try {
        return @(Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntiVirusProduct -ErrorAction Stop)
    }
    catch {
        return @()
    }
}

function Get-HighChurnPaths {
    $paths = @()
    foreach ($relativePath in $highChurnRelativePaths) {
        $candidate = Join-Path $root $relativePath
        if (Test-Path -LiteralPath $candidate -PathType Container) {
            $paths += (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    return $paths
}

function Get-ActivePowerScheme {
    $line = (& powercfg /GETACTIVESCHEME 2>$null | Select-Object -First 1)
    if ($null -eq $line) {
        return $null
    }
    $match = [regex]::Match($line, "GUID:\s*([a-f0-9\-]+)\s+\((.+)\)")
    if (-not $match.Success) {
        return $null
    }
    return @{
        guid = $match.Groups[1].Value
        name = $match.Groups[2].Value
    }
}

function Get-PreferredPowerScheme {
    $lines = @(& powercfg /L 2>$null)
    $schemes = foreach ($line in $lines) {
        $match = [regex]::Match($line, "GUID:\s*([a-f0-9\-]+)\s+\((.+?)\)")
        if ($match.Success) {
            [pscustomobject]@{
                guid = $match.Groups[1].Value
                name = $match.Groups[2].Value
            }
        }
    }
    foreach ($preferredName in @("Ultimate Performance", "Turbo", "Performance", "High performance")) {
        $match = $schemes | Where-Object { $_.name -eq $preferredName } | Select-Object -First 1
        if ($null -ne $match) {
            return @{
                guid = [string]$match.guid
                name = [string]$match.name
            }
        }
    }
    return $null
}

function Get-LongPathsEnabled {
    try {
        $value = Get-ItemPropertyValue `
            -LiteralPath "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" `
            -Name "LongPathsEnabled" `
            -ErrorAction Stop
        return [int]$value
    }
    catch {
        return $null
    }
}

function Set-LongPathsEnabled {
    Set-ItemProperty `
        -LiteralPath "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" `
        -Name "LongPathsEnabled" `
        -Type DWord `
        -Value 1
}

function Set-NotContentIndexedRecursively {
    param([Parameter(Mandatory = $true)][string]$Path)

    $items = @((Get-Item -LiteralPath $Path -Force))
    $items += Get-ChildItem -LiteralPath $Path -Force -Recurse -ErrorAction SilentlyContinue
    $flag = [System.IO.FileAttributes]::NotContentIndexed
    $changed = 0
    $failed = 0
    foreach ($item in $items) {
        try {
            if (($item.Attributes -band $flag) -eq 0) {
                $item.Attributes = $item.Attributes -bor $flag
                $changed += 1
            }
        }
        catch {
            $failed += 1
        }
    }
    return @{
        changed = $changed
        failed = $failed
    }
}

function Get-ExistingDefenderExclusions {
    try {
        return @(Get-MpPreference -ErrorAction Stop | Select-Object -ExpandProperty ExclusionPath)
    }
    catch {
        return @()
    }
}

function Get-CurrentTimeZone {
    if (-not (Get-Command Get-TimeZone -ErrorAction SilentlyContinue)) {
        return $null
    }
    try {
        $zone = Get-TimeZone
        return @{
            id = [string]$zone.Id
            name = [string]$zone.DisplayName
        }
    }
    catch {
        return $null
    }
}

function Get-PreferredTimeZone {
    return @{
        id = "Turkey Standard Time"
        name = "Europe/Istanbul"
    }
}

$isAdmin = Test-IsAdministrator
$highChurnPaths = Get-HighChurnPaths
$activePowerScheme = Get-ActivePowerScheme
$preferredPowerScheme = Get-PreferredPowerScheme
$currentTimeZone = Get-CurrentTimeZone
$preferredTimeZone = Get-PreferredTimeZone
$longPathsEnabled = Get-LongPathsEnabled
$antivirusProducts = Get-AntiVirusProducts
$antivirusNames = @($antivirusProducts | ForEach-Object { $_.displayName })
$nortonPresent = $antivirusNames | Where-Object { $_ -match "Norton" } | Select-Object -First 1

$results = [ordered]@{
    command                    = "optimize-windows-ai4binance"
    repository_root            = $root
    applied                    = $Apply.IsPresent
    administrator              = $isAdmin
    active_power_scheme        = if ($null -ne $activePowerScheme) { $activePowerScheme.name } else { "UNKNOWN" }
    preferred_power_scheme     = if ($null -ne $preferredPowerScheme) { $preferredPowerScheme.name } else { "NOT_AVAILABLE" }
    power_plan                 = "NO_CHANGE"
    system_time_zone           = if ($null -ne $currentTimeZone) { $currentTimeZone.name } else { "UNKNOWN" }
    preferred_time_zone        = $preferredTimeZone.name
    time_zone                  = "NO_CHANGE"
    assistant_profile          = [ordered]@{
        provider = "llama.cpp"
        endpoint = "http://127.0.0.1:8080/completion"
        model = "qwen3:8b"
        prompt_timezone = "Europe/Istanbul"
        timeout_seconds = 180
        history_turns = 4
        response_style = "Direct, practical, recommendation-oriented"
        response_order = "Answer first, then brief rationale, then next action"
        clarifying_question_policy = "At most one concise question when necessary"
        status_queries_supported = $true
        summary_queries_supported = $true
    }
    long_paths_enabled         = $longPathsEnabled
    long_paths                 = "NO_CHANGE"
    indexing_candidate_count   = $highChurnPaths.Count
    indexing_paths             = $highChurnPaths
    indexing_changes           = 0
    indexing_failures          = 0
    indexing_optimization      = "NO_CHANGE"
    antivirus_products         = $antivirusNames
    defender_exclusion_paths   = @()
    defender_exclusion         = "NO_CHANGE"
    norton_allowlist           = if ($nortonPresent) { "MANUAL_PRODUCT_UI_REQUIRED" } else { "NOT_REQUIRED" }
    execution_allowed          = $false
    promotion_status           = "RESEARCH_ONLY"
    live_eligibility_status    = "LIVE_ORDER_BLOCKED"
}

if ($SkipPowerPlan) {
    $results.power_plan = "SKIPPED"
}
elseif ($null -eq $preferredPowerScheme) {
    $results.power_plan = "PREFERRED_SCHEME_NOT_AVAILABLE"
}
elseif ($null -ne $activePowerScheme -and $activePowerScheme.guid -eq $preferredPowerScheme.guid) {
    $results.power_plan = "ALREADY_OPTIMAL"
}
elseif (-not $Apply) {
    $results.power_plan = "RECOMMENDED"
}
else {
    & powercfg /S $preferredPowerScheme.guid | Out-Null
    $results.power_plan = "APPLIED"
    $results.active_power_scheme = $preferredPowerScheme.name
}

if ($SkipLongPaths) {
    $results.long_paths = "SKIPPED"
}
elseif ($longPathsEnabled -eq 1) {
    $results.long_paths = "ALREADY_ENABLED"
}
elseif (-not $Apply) {
    $results.long_paths = if ($isAdmin) { "RECOMMENDED" } else { "BLOCKED_ADMIN_REQUIRED" }
}
elseif (-not $isAdmin) {
    $results.long_paths = "BLOCKED_ADMIN_REQUIRED"
}
else {
    Set-LongPathsEnabled
    $results.long_paths_enabled = 1
    $results.long_paths = "APPLIED"
}

if ($SkipTimeZone) {
    $results.time_zone = "SKIPPED"
}
elseif ($null -eq $currentTimeZone) {
    $results.time_zone = "NOT_AVAILABLE"
}
elseif ($currentTimeZone.id -eq $preferredTimeZone.id) {
    $results.time_zone = "ALREADY_OPTIMAL"
}
elseif (-not $Apply) {
    $results.time_zone = "RECOMMENDED"
}
elseif (-not $isAdmin) {
    $results.time_zone = "BLOCKED_ADMIN_REQUIRED"
}
else {
    $results.time_zone = "RECOMMENDED"
}

if ($SkipIndexingOptimization) {
    $results.indexing_optimization = "SKIPPED"
}
elseif ($highChurnPaths.Count -eq 0) {
    $results.indexing_optimization = "NO_TARGETS"
}
elseif (-not $Apply) {
    $results.indexing_optimization = "RECOMMENDED"
}
else {
    $changes = 0
    $failures = 0
    foreach ($path in $highChurnPaths) {
        $result = Set-NotContentIndexedRecursively -Path $path
        $changes += [int]$result.changed
        $failures += [int]$result.failed
    }
    $results.indexing_changes = $changes
    $results.indexing_failures = $failures
    if ($changes -gt 0 -and $failures -gt 0) {
        $results.indexing_optimization = "PARTIALLY_APPLIED"
    }
    elseif ($changes -gt 0) {
        $results.indexing_optimization = "APPLIED"
    }
    elseif ($failures -gt 0) {
        $results.indexing_optimization = "PARTIAL_ACCESS_DENIED"
    }
    else {
        $results.indexing_optimization = "ALREADY_OPTIMAL"
    }
}

if ($SkipDefenderExclusion) {
    $results.defender_exclusion = "SKIPPED"
}
elseif ($highChurnPaths.Count -eq 0) {
    $results.defender_exclusion = "NO_TARGETS"
}
elseif (-not (Get-Command Get-MpPreference -ErrorAction SilentlyContinue)) {
    $results.defender_exclusion = "DEFENDER_TOOLING_UNAVAILABLE"
}
elseif ($nortonPresent) {
    $results.defender_exclusion = "THIRD_PARTY_AV_PRESENT_MANUAL_REVIEW_REQUIRED"
}
else {
    $existingExclusions = Get-ExistingDefenderExclusions
    $missingExclusions = @($highChurnPaths | Where-Object { $_ -notin $existingExclusions })
    $results.defender_exclusion_paths = $missingExclusions
    if ($missingExclusions.Count -eq 0) {
        $results.defender_exclusion = "ALREADY_OPTIMAL"
    }
    elseif (-not $Apply) {
        $results.defender_exclusion = if ($isAdmin) { "RECOMMENDED" } else { "BLOCKED_ADMIN_REQUIRED" }
    }
    elseif (-not $isAdmin) {
        $results.defender_exclusion = "BLOCKED_ADMIN_REQUIRED"
    }
    else {
        foreach ($path in $missingExclusions) {
            Add-MpPreference -ExclusionPath $path
        }
        $results.defender_exclusion = "APPLIED"
    }
}

Write-Result -Payload $results
