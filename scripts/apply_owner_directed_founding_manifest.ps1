[CmdletBinding()]
param([switch]$Apply)

# Owner-operated Windows file update. Codex must not use this to bypass a denied write.
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$evidenceRoot = Join-Path $repositoryRoot "runtime/artifacts/governance/sole-owner/founding-migration-20261005"
$manifestPath = Join-Path $repositoryRoot "config/governance/governed_document_lock_manifest.json"
$contextSource = Join-Path $evidenceRoot "founding-owner-authority-context.json"
$contextTarget = Join-Path $repositoryRoot "runtime/artifacts/governance/document-lock/authority-context.json"
$replacementPath = Join-Path $evidenceRoot "founding-registration-with-grant.json"
$predecessorPath = Join-Path $evidenceRoot "pre-founding-manifest-original.json"

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
if (Test-Path -LiteralPath $contextTarget) {
    if ((Get-FileDigest $contextTarget) -cne (Get-FileDigest $contextSource)) {
        throw "EXISTING_AUTHORITY_CONTEXT_MUST_BE_PRESERVED"
    }
}

$originalAcl = Get-Acl -LiteralPath $manifestPath
$originalSddl = $originalAcl.GetSecurityDescriptorSddlForm([Security.AccessControl.AccessControlSections]::All)
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
    if ($permissionsChanged) {
        [IO.File]::SetAttributes($manifestPath, $originalAttributes)
        Set-Acl -LiteralPath $manifestPath -AclObject $originalAcl
    }
}
$restoredSddl = (Get-Acl -LiteralPath $manifestPath).GetSecurityDescriptorSddlForm([Security.AccessControl.AccessControlSections]::All)
if ($restoredSddl -cne $originalSddl -or [IO.File]::GetAttributes($manifestPath) -ne $originalAttributes) {
    throw "FOUNDING_MANIFEST_PROTECTION_NOT_RESTORED"
}
[Console]::Out.WriteLine("EXACT_MANIFEST_BYTES_WRITTEN_AND_ORIGINAL_PROTECTIONS_RESTORED")
[Console]::Out.WriteLine("GOVERNANCE_INSTALLATION_AND_ACTIVATION_NOT_COMPLETED")
[Console]::Out.WriteLine("RESEARCH_ONLY")
[Console]::Out.WriteLine("LIVE_ORDER_BLOCKED")
