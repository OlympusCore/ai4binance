param([switch]$Apply)

$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$receiptRoot = Join-Path $repositoryRoot "runtime\artifacts\repository_validation\runtime_hygiene"
$stamp = [DateTimeOffset]::UtcNow.ToString("yyyyMMddTHHmmssfffZ")
$receiptPath = Join-Path $receiptRoot "runtime-layout-migration-$stamp.json"
$conflictRoot = Join-Path `
    $repositoryRoot `
    ("runtime\data\quarantine\legacy-layout-conflicts\" + $stamp)

function Assert-InRepository {
    param([Parameter(Mandatory = $true)][string]$Path)
    $full = [System.IO.Path]::GetFullPath($Path)
    if (-not $full.StartsWith($repositoryRoot + "\", [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "RUNTIME_MIGRATION_PATH_OUTSIDE_REPOSITORY"
    }
    return $full
}

function Get-RelativePath {
    param([Parameter(Mandatory = $true)][string]$Path)
    $full = Assert-InRepository -Path $Path
    return $full.Substring($repositoryRoot.Length + 1).Replace("\", "/")
}

function Test-ExclusiveRead {
    param([Parameter(Mandatory = $true)][string]$Path)
    try {
        $stream = [System.IO.File]::Open(
            $Path,
            [System.IO.FileMode]::Open,
            [System.IO.FileAccess]::Read,
            [System.IO.FileShare]::None
        )
        $stream.Dispose()
        return $true
    }
    catch {
        return $false
    }
}

function Get-Sha256 {
    param([Parameter(Mandatory = $true)][string]$Path)
    $stream = [System.IO.File]::OpenRead($Path)
    try {
        $algorithm = [System.Security.Cryptography.SHA256]::Create()
        try {
            return ([System.BitConverter]::ToString($algorithm.ComputeHash($stream))).Replace("-", "").ToLowerInvariant()
        }
        finally {
            $algorithm.Dispose()
        }
    }
    finally {
        $stream.Dispose()
    }
}

$directoryMappings = @(
    @{ source = "runtime\datasets"; destination = "runtime\data\datasets" },
    @{ source = "runtime\research\historical_replay"; destination = "runtime\artifacts\research\historical_replay" },
    @{ source = "runtime\learning"; destination = "runtime\artifacts\research\learning" },
    @{ source = "runtime\performance"; destination = "runtime\artifacts\benchmarks\performance" }
)

$rows = [System.Collections.Generic.List[object]]::new()
foreach ($mapping in $directoryMappings) {
    $sourceRoot = Join-Path $repositoryRoot $mapping.source
    if (-not (Test-Path -LiteralPath $sourceRoot -PathType Container)) {
        continue
    }
    foreach ($file in Get-ChildItem -LiteralPath $sourceRoot -File -Recurse -Force) {
        $relative = $file.FullName.Substring($sourceRoot.Length + 1)
        $destination = Join-Path (Join-Path $repositoryRoot $mapping.destination) $relative
        $rows.Add([pscustomobject]@{ source = $file.FullName; destination = $destination })
    }
}

$reportMappings = @(
    @{ source = "runtime\reports\performance"; destination = "runtime\artifacts\benchmarks\windows_optimization"; pattern = "*" },
    @{ source = "runtime\reports\trading"; destination = "runtime\artifacts\research\trading"; pattern = "*" },
    @{ source = "runtime\reports\market-history"; destination = "runtime\test\market_history"; pattern = "staged-tests.*" },
    @{ source = "runtime\reports\market-history"; destination = "runtime\artifacts\repository_validation\market_history"; pattern = "*" }
)
foreach ($mapping in $reportMappings) {
    $sourceRoot = Join-Path $repositoryRoot $mapping.source
    if (-not (Test-Path -LiteralPath $sourceRoot -PathType Container)) {
        continue
    }
    foreach ($file in Get-ChildItem -LiteralPath $sourceRoot -File -Filter $mapping.pattern -Force) {
        if ($file.Extension -eq ".md") {
            continue
        }
        if ($rows.source -contains $file.FullName) {
            continue
        }
        $destination = Join-Path (Join-Path $repositoryRoot $mapping.destination) $file.Name
        $rows.Add([pscustomobject]@{ source = $file.FullName; destination = $destination })
    }
}

$records = foreach ($row in $rows) {
    $source = Assert-InRepository -Path $row.source
    $destination = Assert-InRepository -Path $row.destination
    if (-not (Test-ExclusiveRead -Path $source)) {
        throw "RUNTIME_MIGRATION_FILE_IN_USE:$(Get-RelativePath -Path $source)"
    }
    $sourceHash = Get-Sha256 -Path $source
    $destinationHash = $null
    $status = "MIGRATE"
    $conflictPath = $null
    if (Test-Path -LiteralPath $destination -PathType Leaf) {
        $destinationHash = Get-Sha256 -Path $destination
        if ($destinationHash -ne $sourceHash) {
            $sourceRelative = Get-RelativePath -Path $source
            $runtimeRelative = $sourceRelative.Substring("runtime/".Length)
            $conflictPath = Join-Path $conflictRoot ($runtimeRelative.Replace("/", "\"))
            $status = "QUARANTINE_DESTINATION_CONFLICT"
        }
        else {
            $status = "DEDUPLICATE_IDENTICAL"
        }
    }
    [pscustomobject]@{
        source = Get-RelativePath -Path $source
        destination = Get-RelativePath -Path $destination
        bytes = [int64](Get-Item -LiteralPath $source).Length
        sha256 = $sourceHash
        destination_sha256 = $destinationHash
        conflict_path = if ($null -eq $conflictPath) {
            $null
        }
        else {
            Get-RelativePath -Path $conflictPath
        }
        migration_status = $status
        applied = $false
    }
}

if ($Apply) {
    foreach ($record in $records) {
        $source = Join-Path $repositoryRoot $record.source
        $destination = Join-Path $repositoryRoot $record.destination
        New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
        if ($record.migration_status -eq "MIGRATE") {
            Move-Item -LiteralPath $source -Destination $destination
        }
        elseif ($record.migration_status -eq "DEDUPLICATE_IDENTICAL") {
            Remove-Item -LiteralPath $source -Force -Confirm:$false
        }
        elseif ($record.migration_status -eq "QUARANTINE_DESTINATION_CONFLICT") {
            $conflictPath = Assert-InRepository -Path (
                Join-Path $repositoryRoot $record.conflict_path
            )
            New-Item `
                -ItemType Directory `
                -Path (Split-Path -Parent $conflictPath) `
                -Force |
                Out-Null
            Move-Item -LiteralPath $source -Destination $conflictPath
        }
        else {
            throw "RUNTIME_MIGRATION_STATUS_INVALID:$($record.migration_status)"
        }
        $record.applied = $true
    }
    $cleanupRoots = @(
        "runtime\datasets",
        "runtime\research",
        "runtime\learning",
        "runtime\performance",
        "runtime\reports\market-history",
        "runtime\reports\performance",
        "runtime\reports\trading"
    )
    foreach ($relative in $cleanupRoots) {
        $path = Assert-InRepository -Path (Join-Path $repositoryRoot $relative)
        if (Test-Path -LiteralPath $path -PathType Container) {
            Get-ChildItem -LiteralPath $path -Directory -Recurse -Force |
                Sort-Object FullName -Descending |
                Where-Object { @(Get-ChildItem -LiteralPath $_.FullName -Force).Count -eq 0 } |
                Remove-Item -Force -Confirm:$false
            if (@(Get-ChildItem -LiteralPath $path -Force).Count -eq 0) {
                Remove-Item -LiteralPath $path -Force -Confirm:$false
            }
        }
    }
}

$receipt = [ordered]@{
    schema_version = "1.0"
    generated_at = [DateTimeOffset]::UtcNow.ToString("o")
    applied = [bool]$Apply
    migrated_file_count = @($records).Count
    migrated_bytes = [int64](($records | Measure-Object bytes -Sum).Sum)
    conflict_count = @(
        $records |
            Where-Object { $_.migration_status -eq "QUARANTINE_DESTINATION_CONFLICT" }
    ).Count
    files = @($records)
    execution_allowed = $false
    live_eligibility_status = "LIVE_ORDER_BLOCKED"
}
New-Item -ItemType Directory -Path $receiptRoot -Force | Out-Null
$receipt | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $receiptPath -Encoding UTF8
$receipt | ConvertTo-Json -Depth 5
