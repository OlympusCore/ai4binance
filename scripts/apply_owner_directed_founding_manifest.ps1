[CmdletBinding()]
param(
    [switch]$Apply,
    [string]$AuthorityContextPath = "",
    [string]$ReviewContextPath = "",
    [string]$PredecessorManifestPath = ""
)

# Explicitly authorized Windows file transaction; never bypass unavailable privileges.
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$evidenceRoot = Join-Path $repositoryRoot "runtime/artifacts/governance/sole-owner/founding-migration-20261005"
$manifestPath = Join-Path $repositoryRoot "config/governance/governed_document_lock_manifest.json"
$contextSource = Join-Path $evidenceRoot "founding-owner-authority-context.json"
$contextTarget = Join-Path $repositoryRoot "runtime/artifacts/governance/document-lock/authority-context.json"
$replacementPath = Join-Path $evidenceRoot "founding-registration-with-grant.json"
$predecessorPath = Join-Path $evidenceRoot "pre-founding-manifest-original.json"
$freshTransaction = -not [string]::IsNullOrWhiteSpace($AuthorityContextPath)
if ($freshTransaction) {
    foreach ($inputPath in @($AuthorityContextPath, $ReviewContextPath, $PredecessorManifestPath)) {
        $resolvedInput = [IO.Path]::GetFullPath((Join-Path $repositoryRoot $inputPath))
        $runtimeRoot = [IO.Path]::GetFullPath((Join-Path $repositoryRoot "runtime")) + [IO.Path]::DirectorySeparatorChar
        if (-not $resolvedInput.StartsWith($runtimeRoot, [StringComparison]::OrdinalIgnoreCase) -or -not [IO.File]::Exists($resolvedInput)) {
            throw "REGISTRATION_INPUT_OUTSIDE_EXISTING_RUNTIME"
        }
    }
    $contextSource = Join-Path $repositoryRoot $AuthorityContextPath
    $predecessorPath = Join-Path $repositoryRoot $PredecessorManifestPath
    $evidenceRoot = Split-Path -Parent $contextSource
    $freshContext = Get-Content -LiteralPath $contextSource -Raw | ConvertFrom-Json
    $replacementPath = [IO.Path]::GetFullPath((Join-Path $repositoryRoot $freshContext.final_manifest.path))
    $runtimeRoot = [IO.Path]::GetFullPath((Join-Path $repositoryRoot "runtime")) + [IO.Path]::DirectorySeparatorChar
    if (-not $replacementPath.StartsWith($runtimeRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "REGISTRATION_REPLACEMENT_OUTSIDE_RUNTIME"
    }
    . (Join-Path $PSScriptRoot "initialize_runtime_environment.ps1")
    & (Join-Path $repositoryRoot ".venv/Scripts/python.exe") -B -m ai4binance.governance.repository_validator `
        --repository-root $repositoryRoot --document-lock-review-context (Join-Path $repositoryRoot $ReviewContextPath)
    if ($LASTEXITCODE -ne 0) { throw "REGISTRATION_REVIEW_REJECTED" }
}

function Get-FileDigest([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

$context = Get-Content -LiteralPath $contextSource -Raw | ConvertFrom-Json
$expectedPath = [IO.Path]::GetFullPath((Join-Path $repositoryRoot $context.final_manifest.path))
if ($expectedPath -cne [IO.Path]::GetFullPath($replacementPath)) {
    throw "FOUNDING_MANIFEST_SOURCE_PATH_DRIFT"
}
$replacementHash = Get-FileDigest $replacementPath
if ($replacementHash -cne $context.final_manifest.sha256) {
    throw "FOUNDING_MANIFEST_SOURCE_HASH_DRIFT"
}
if ((Get-FileDigest $manifestPath) -cne (Get-FileDigest $predecessorPath)) {
    throw "FOUNDING_MANIFEST_BASELINE_DRIFT"
}
if (-not $freshTransaction -and (Test-Path -LiteralPath $contextTarget)) {
    if ((Get-FileDigest $contextTarget) -cne (Get-FileDigest $contextSource)) {
        throw "EXISTING_AUTHORITY_CONTEXT_MUST_BE_PRESERVED"
    }
}

$originalAcl = Get-Acl -LiteralPath $manifestPath
$securitySections = [Security.AccessControl.AccessControlSections]::Owner -bor [Security.AccessControl.AccessControlSections]::Group -bor [Security.AccessControl.AccessControlSections]::Access
$originalSddl = $originalAcl.GetSecurityDescriptorSddlForm($securitySections)
$originalAttributes = [IO.File]::GetAttributes($manifestPath)
$operatorSid = [Security.Principal.WindowsIdentity]::GetCurrent().User
$denyRules = @($originalAcl.Access | Where-Object {
    -not $_.IsInherited -and
    $_.AccessControlType -eq [Security.AccessControl.AccessControlType]::Deny -and
    $_.FileSystemRights -eq [Security.AccessControl.FileSystemRights]::Write -and
    $_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -eq $operatorSid.Value
})
if ($denyRules.Count -ne 1) {
    throw "EXACT_OWNER_WRITE_DENY_RULE_NOT_FOUND"
}

[Console]::Out.WriteLine("TARGET=config/governance/governed_document_lock_manifest.json")
[Console]::Out.WriteLine("REPLACEMENT_SHA256=$replacementHash")
if (-not $Apply) {
    [Console]::Out.WriteLine("PREVIEW_ONLY_NO_PERMISSION_CHANGES")
    exit 0
}

$receiptStem = "owner-manifest-operation-" + [DateTimeOffset]::UtcNow.ToString("yyyyMMddTHHmmssfffffffZ")
$snapshotPath = Join-Path $evidenceRoot ($receiptStem + "-protection.json")
[IO.File]::WriteAllText($snapshotPath, ([ordered]@{
    target = "config/governance/governed_document_lock_manifest.json"
    original_sddl = $originalSddl
    original_attributes = [int]$originalAttributes
    original_sha256 = Get-FileDigest $manifestPath
    replacement_sha256 = $replacementHash
    recorded_at_utc = [DateTimeOffset]::UtcNow.ToString("o")
} | ConvertTo-Json), [Text.UTF8Encoding]::new($false))

$temporaryAcl = [Security.AccessControl.FileSecurity]::new()
$temporaryAcl.SetSecurityDescriptorSddlForm($originalSddl)
$temporaryAcl.RemoveAccessRuleSpecific($denyRules[0])
$permissionsChanged = $false
try {
    if ((Get-FileDigest $manifestPath) -cne (Get-FileDigest $predecessorPath)) {
        throw "FOUNDING_MANIFEST_CONCURRENT_CHANGE"
    }
    if ($freshTransaction) {
        $reviewInput = Get-Content -LiteralPath (Join-Path $repositoryRoot $ReviewContextPath) -Raw | ConvertFrom-Json
        foreach ($document in $reviewInput.review_subject.documents) {
            if ((Get-FileDigest (Join-Path $repositoryRoot $document.path)) -cne $document.sha256) {
                throw "REGISTRATION_DOCUMENT_CONCURRENT_CHANGE"
            }
        }
        if (Test-Path -LiteralPath $contextTarget) {
            [IO.File]::WriteAllBytes((Join-Path $evidenceRoot ($receiptStem + "-predecessor-context.json")), [IO.File]::ReadAllBytes($contextTarget))
        }
    }
    Set-Acl -LiteralPath $manifestPath -AclObject $temporaryAcl
    $permissionsChanged = $true
    [IO.File]::SetAttributes($manifestPath, ($originalAttributes -band (-bnot [IO.FileAttributes]::ReadOnly)))
    [IO.File]::WriteAllBytes($manifestPath, [IO.File]::ReadAllBytes($replacementPath))
    if ((Get-FileDigest $manifestPath) -cne $replacementHash) {
        throw "FOUNDING_MANIFEST_INSTALLED_HASH_MISMATCH"
    }
    [IO.Directory]::CreateDirectory((Split-Path -Parent $contextTarget)) | Out-Null
    [IO.File]::WriteAllBytes($contextTarget, [IO.File]::ReadAllBytes($contextSource))
} finally {
    [IO.File]::SetAttributes($manifestPath, $originalAttributes)
    if ((Get-Acl -LiteralPath $manifestPath).GetSecurityDescriptorSddlForm($securitySections) -cne $originalSddl) {
        Set-Acl -LiteralPath $manifestPath -AclObject $originalAcl
    }
}
$restoredSddl = (Get-Acl -LiteralPath $manifestPath).GetSecurityDescriptorSddlForm($securitySections)
if ($restoredSddl -cne $originalSddl -or [IO.File]::GetAttributes($manifestPath) -ne $originalAttributes) {
    throw "FOUNDING_MANIFEST_PROTECTION_NOT_RESTORED"
}
[IO.File]::WriteAllText((Join-Path $evidenceRoot ($receiptStem + "-result.json")), ([ordered]@{
    target = "config/governance/governed_document_lock_manifest.json"
    replacement_sha256 = $replacementHash
    installed_sha256 = Get-FileDigest $manifestPath
    completed_at_utc = [DateTimeOffset]::UtcNow.ToString("o")
    original_protection_restored = $true
    original_sddl = $originalSddl
    original_attributes = [int]$originalAttributes
    authority_context_sha256 = Get-FileDigest $contextTarget
} | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
[Console]::Out.WriteLine("EXACT_MANIFEST_BYTES_WRITTEN_AND_ORIGINAL_PROTECTIONS_RESTORED")
[Console]::Out.WriteLine("GOVERNANCE_INSTALLATION_AND_ACTIVATION_NOT_COMPLETED")
[Console]::Out.WriteLine("RESEARCH_ONLY")
[Console]::Out.WriteLine("LIVE_ORDER_BLOCKED")
