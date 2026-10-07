[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$MainRoot,
    [Parameter(Mandatory = $true)]
    [string[]]$WorktreePaths,
    [switch]$Apply
)

$ErrorActionPreference = "Stop"
if ($Apply) {
    $canonicalRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
    $env:PYTHONPATH = Join-Path $canonicalRoot "src"
    foreach ($targetRoot in $WorktreePaths) {
        & (Join-Path $canonicalRoot ".venv/Scripts/python.exe") -B `
            -m ai4binance.ops.quality_gate.repository_completion `
            --repository-root $targetRoot --operation preflight `
            --task-scope "Already authorized bounded repository recovery"
        if ($LASTEXITCODE -ne 0) { throw "CANONICAL_GIT_RECOVERY_TARGET_BLOCKED" }
    }
}

$rules = @(
    @{
        Path = "docs/standards/standard_repository_naming_governance.md"
        Approved = "27e65580f54f082dff90741392da467f62571851b46b64e623f2de5ef17e4559"
        Observed = "5de0bb68bb24b0b3ce9a32bd185dcf5c72ce55125db44faf665d273e2d3876ce"
    },
    @{
        Path = "docs/standards/standard_terminology_governance.md"
        Approved = "3afc73fd1c11e960c33445d184754e0a3c1a998c222660e88e14d0d4a673e954"
        Observed = "d8edb7c88c73b4ac5a956ca10053e00c6df6ec323788ceb3ec74538590e3d40c"
    }
)

# This is a bounded file restoration, not a replacement governance gate.
# Review mode performs no writes. Apply mode requires separate owner approval.
$plan = @(
    foreach ($root in $WorktreePaths) {
        $resolvedRoot = (Resolve-Path -LiteralPath $root).Path
        foreach ($rule in $rules) {
            $source = Join-Path $MainRoot $rule.Path
            $destination = Join-Path $resolvedRoot $rule.Path
            $sourceBytes = [IO.File]::ReadAllBytes($source)
            $hasher = [Security.Cryptography.SHA256]::Create()
            try {
                $sourceHash = ([BitConverter]::ToString(
                    $hasher.ComputeHash($sourceBytes)
                )).Replace("-", "").ToLowerInvariant()
            }
            finally {
                $hasher.Dispose()
            }
            if ($sourceHash -ne $rule.Approved) {
                throw "Source differs from the reviewed approved bytes: $source"
            }
            $targetItem = Get-Item -LiteralPath $destination -Force
            if ($targetItem.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Reparse-point document will not be modified: $destination"
            }
            $previousHash = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash
            if ($previousHash -ne $rule.Observed -and $previousHash -ne $rule.Approved) {
                throw "Unreviewed target changes detected; restoration stopped: $destination"
            }
            [PSCustomObject]@{
                Root = $resolvedRoot
                Path = $rule.Path
                Destination = $destination
                PreviousHash = $previousHash
                ApprovedHash = $rule.Approved
                SourceBytes = $sourceBytes
                Attributes = $targetItem.Attributes
            }
        }
    }
)

$plan | Select-Object Destination, PreviousHash, ApprovedHash, Attributes | Format-List
if (-not $Apply) {
    Write-Output "REVIEW_ONLY: No files changed. Owner approval is required before -Apply."
    return
}

$runId = [Guid]::NewGuid().ToString("N")
foreach ($item in $plan) {
    $currentHash = (Get-FileHash -LiteralPath $item.Destination -Algorithm SHA256).Hash
    if ($currentHash -ne $item.PreviousHash) {
        throw "Document changed after preflight: $($item.Destination)"
    }
    if ($currentHash -eq $item.ApprovedHash) {
        Write-Output "Approved document bytes already present: $($item.Destination)"
        continue
    }

    $backupPath = Join-Path $item.Root (
        "runtime/tmp/codex-standard-restoration/" + $runId + "/" + $item.Path
    )
    New-Item -ItemType Directory -Path (Split-Path -Parent $backupPath) -Force | Out-Null
    Copy-Item -LiteralPath $item.Destination -Destination $backupPath
    if ((Get-FileHash -LiteralPath $backupPath -Algorithm SHA256).Hash -ne $item.PreviousHash) {
        throw "Original document backup verification failed: $backupPath"
    }
    try {
        [IO.File]::SetAttributes(
            $item.Destination,
            ($item.Attributes -band (-bnot [IO.FileAttributes]::ReadOnly))
        )
        [IO.File]::WriteAllBytes($item.Destination, $item.SourceBytes)
    }
    finally {
        [IO.File]::SetAttributes($item.Destination, $item.Attributes)
    }
    if ((Get-FileHash -LiteralPath $item.Destination -Algorithm SHA256).Hash -ne $item.ApprovedHash) {
        throw "Restored document hash verification failed: $($item.Destination)"
    }
    Write-Output "Approved document bytes restored: $($item.Destination)"
    Write-Output "Original document backup: $backupPath"
}

Write-Output "RESTORATION_APPLIED: Run canonical startup validation before claiming readiness."
