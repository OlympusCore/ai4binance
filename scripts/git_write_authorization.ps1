[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Prepare", "Approve", "Consume")]
    [string]$Mode,

    [Parameter(Mandatory = $false)]
    [ValidateSet("", "Commit", "Push")]
    [string]$Operation = "",

    [Parameter(Mandatory = $false)]
    [string]$RepositoryRoot = "",

    [Parameter(Mandatory = $false)]
    [ValidateSet("Interactive", "NonInteractive")]
    [string]$Channel = "NonInteractive",

    [Parameter(Mandatory = $false)]
    [string]$ChallengePath = "",

    [Parameter(Mandatory = $false)]
    [string]$ApprovalText = "",

    [Parameter(Mandatory = $false)]
    [string]$RemoteName = "",

    [Parameter(Mandatory = $false)]
    [string]$PushUpdatesPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "initialize_runtime_environment.ps1")

$script:maximumArtifactBytes = 65536
$script:maximumPendingArtifacts = 512
$script:authorizationLifetime = [TimeSpan]::FromMinutes(5)
$script:utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Write-GitAuthorizationBlock {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Reason
    )

    [Console]::Error.WriteLine($Reason)
    [Console]::Error.WriteLine("RESEARCH_ONLY")
    [Console]::Error.WriteLine("LIVE_ORDER_BLOCKED")
}

function Get-Sha256Text {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes($Value)
        return ([BitConverter]::ToString($sha256.ComputeHash($bytes))).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $sha256.Dispose()
    }
}

function Get-FileSha256 {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $stream = [IO.File]::Open(
        $Path,
        [IO.FileMode]::Open,
        [IO.FileAccess]::Read,
        [IO.FileShare]::Read
    )
    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($sha256.ComputeHash($stream))).Replace(
            "-",
            ""
        ).ToLowerInvariant()
    }
    finally {
        $sha256.Dispose()
        $stream.Dispose()
    }
}

function Invoke-GitCapture {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ResolvedRepositoryRoot,

        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,

        [Parameter(Mandatory = $true)]
        [string]$FailureCode
    )

    $output = & git -C $ResolvedRepositoryRoot @Arguments 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw $FailureCode
    }
    $text = [string](@($output) -join "`n")
    if ([string]::IsNullOrWhiteSpace($text)) {
        throw $FailureCode
    }
    return $text.Trim()
}

function Resolve-RepositoryContext {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RequestedRoot
    )

    if ([string]::IsNullOrWhiteSpace($RequestedRoot)) {
        $RequestedRoot = Join-Path $PSScriptRoot ".."
    }
    $resolvedRoot = [IO.Path]::GetFullPath(
        (Resolve-Path -LiteralPath $RequestedRoot -ErrorAction Stop).Path
    )
    $topLevel = Invoke-GitCapture `
        -ResolvedRepositoryRoot $resolvedRoot `
        -Arguments @("rev-parse", "--show-toplevel") `
        -FailureCode "GIT_WRITE_AUTHORIZATION_REPOSITORY_UNAVAILABLE"
    $resolvedTopLevel = [IO.Path]::GetFullPath($topLevel)
    if ($resolvedTopLevel -ne $resolvedRoot) {
        throw "GIT_WRITE_AUTHORIZATION_REPOSITORY_ROOT_MISMATCH"
    }
    $gitCommonDirectory = Invoke-GitCapture `
        -ResolvedRepositoryRoot $resolvedRoot `
        -Arguments @("rev-parse", "--path-format=absolute", "--git-common-dir") `
        -FailureCode "GIT_WRITE_AUTHORIZATION_GIT_COMMON_DIR_UNAVAILABLE"
    $resolvedGitCommonDirectory = [IO.Path]::GetFullPath($gitCommonDirectory)
    $stateRoot = Join-Path $resolvedGitCommonDirectory "ai4binance-git-write-authorizations"
    return [pscustomobject]@{
        RepositoryRoot = $resolvedRoot
        GitCommonDirectory = $resolvedGitCommonDirectory
        StateRoot = $stateRoot
        PendingRoot = Join-Path $stateRoot "pending"
        ApprovedRoot = Join-Path $stateRoot "approved"
        ConsumedRoot = Join-Path $stateRoot "consumed"
    }
}

function New-RandomNonce {
    $bytes = New-Object byte[] 32
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
    }
    finally {
        $generator.Dispose()
    }
    return ([BitConverter]::ToString($bytes)).Replace("-", "").ToLowerInvariant()
}

function Write-JsonAtomic {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [object]$Payload
    )

    $parent = Split-Path -Parent $Path
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    $temporaryPath = Join-Path $parent ((New-RandomNonce) + ".tmp")
    try {
        $json = $Payload | ConvertTo-Json -Depth 12
        [IO.File]::WriteAllText($temporaryPath, $json + "`n", $script:utf8NoBom)
        [IO.File]::Move($temporaryPath, $Path)
    }
    finally {
        if (Test-Path -LiteralPath $temporaryPath -PathType Leaf) {
            Remove-Item -LiteralPath $temporaryPath -Force -ErrorAction SilentlyContinue
        }
    }
}

function Assert-PathWithinDirectory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$Directory,

        [Parameter(Mandatory = $true)]
        [string]$FailureCode
    )

    $resolvedPath = [IO.Path]::GetFullPath(
        (Resolve-Path -LiteralPath $Path -ErrorAction Stop).Path
    )
    $resolvedDirectory = [IO.Path]::GetFullPath($Directory).TrimEnd(
        [IO.Path]::DirectorySeparatorChar,
        [IO.Path]::AltDirectorySeparatorChar
    )
    $prefix = $resolvedDirectory + [IO.Path]::DirectorySeparatorChar
    if (-not $resolvedPath.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw $FailureCode
    }
    return $resolvedPath
}

function Read-StrictJsonObject {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $item = Get-Item -LiteralPath $Path -ErrorAction Stop
    if (-not $item.PSIsContainer -and $item.Length -gt 0 -and $item.Length -le $script:maximumArtifactBytes) {
        $python = Join-Path (Join-Path $PSScriptRoot "..") ".venv\Scripts\python.exe"
        if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
            throw "GIT_WRITE_AUTHORIZATION_PYTHON_UNAVAILABLE"
        }
        $pythonCode = @'
import json
import sys
from pathlib import Path


def reject_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_constant(value: str) -> object:
    raise ValueError(f"invalid JSON constant: {value}")


path = Path(sys.argv[1])
raw = path.read_bytes()
if not raw or len(raw) > 65536 or raw.startswith(b"\xef\xbb\xbf"):
    raise ValueError("authorization JSON size or encoding is invalid")
payload = json.loads(
    raw.decode("utf-8"),
    object_pairs_hook=reject_pairs,
    parse_constant=reject_constant,
)
if not isinstance(payload, dict):
    raise ValueError("authorization JSON root must be an object")
print(json.dumps(payload, ensure_ascii=True, separators=(",", ":")))
'@
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            $canonical = $pythonCode | & $python -I -B - $item.FullName 2>$null
            $pythonExitCode = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
        if ($pythonExitCode -ne 0 -or @($canonical).Count -eq 0) {
            throw "GIT_WRITE_AUTHORIZATION_JSON_INVALID"
        }
        return ([string](@($canonical) -join "`n")) | ConvertFrom-Json
    }
    throw "GIT_WRITE_AUTHORIZATION_ARTIFACT_SIZE_INVALID"
}

function Assert-ExactProperties {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Payload,

        [Parameter(Mandatory = $true)]
        [string[]]$Expected,

        [Parameter(Mandatory = $true)]
        [string]$FailureCode
    )

    $actual = @($Payload.PSObject.Properties.Name | Sort-Object)
    $expectedSorted = @($Expected | Sort-Object)
    if (($actual -join "`n") -ne ($expectedSorted -join "`n")) {
        throw $FailureCode
    }
}

function Get-GitIdentity {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ResolvedRepositoryRoot,

        [Parameter(Mandatory = $true)]
        [ValidateSet("GIT_AUTHOR_IDENT", "GIT_COMMITTER_IDENT")]
        [string]$Variable
    )

    $identity = Invoke-GitCapture `
        -ResolvedRepositoryRoot $ResolvedRepositoryRoot `
        -Arguments @("var", $Variable) `
        -FailureCode "GIT_WRITE_AUTHORIZATION_IDENTITY_UNAVAILABLE"
    if ($identity -notmatch '^(?<name>.*) <(?<email>[^<>]*)> [0-9]+ [+-][0-9]{4}$') {
        throw "GIT_WRITE_AUTHORIZATION_IDENTITY_INVALID"
    }
    $name = [string]$Matches.name
    $email = [string]$Matches.email
    return [pscustomobject]@{
        Hash = Get-Sha256Text ($name + "`n" + $email)
        Placeholder = (
            $name -ceq "Quality Gate" -or
            $email -ceq "quality@example.invalid"
        )
    }
}

function Get-LocalHooksPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ResolvedRepositoryRoot
    )

    $value = & git -C $ResolvedRepositoryRoot config --local --get core.hooksPath 2>$null
    if ($LASTEXITCODE -notin @(0, 1)) {
        throw "GIT_WRITE_AUTHORIZATION_HOOKS_PATH_UNAVAILABLE"
    }
    return ([string](@($value) -join "`n")).Trim()
}

function Read-PushUpdates {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw "GIT_WRITE_AUTHORIZATION_PUSH_UPDATES_REQUIRED"
    }
    $item = Get-Item -LiteralPath $Path -ErrorAction Stop
    if ($item.Length -le 0 -or $item.Length -gt $script:maximumArtifactBytes) {
        throw "GIT_WRITE_AUTHORIZATION_PUSH_UPDATES_SIZE_INVALID"
    }
    $updates = @()
    foreach ($line in @(Get-Content -LiteralPath $item.FullName)) {
        if ([string]::IsNullOrWhiteSpace([string]$line)) {
            continue
        }
        $parts = @(([string]$line).Trim() -split '\s+')
        if ($parts.Count -ne 4) {
            throw "GIT_WRITE_AUTHORIZATION_PUSH_UPDATE_INVALID"
        }
        if (
            $parts[0].Length -gt 1024 -or
            $parts[2].Length -gt 1024 -or
            $parts[0] -notmatch '^(refs/|\(delete\))' -or
            $parts[2] -notmatch '^refs/' -or
            $parts[1] -notmatch '^[0-9a-fA-F]{40,64}$' -or
            $parts[3] -notmatch '^[0-9a-fA-F]{40,64}$'
        ) {
            throw "GIT_WRITE_AUTHORIZATION_PUSH_UPDATE_INVALID"
        }
        $updates += [pscustomobject][ordered]@{
            local_ref = $parts[0]
            local_oid = $parts[1].ToLowerInvariant()
            remote_ref = $parts[2]
            remote_oid = $parts[3].ToLowerInvariant()
        }
    }
    if ($updates.Count -eq 0 -or $updates.Count -gt 256) {
        throw "GIT_WRITE_AUTHORIZATION_PUSH_UPDATE_COUNT_INVALID"
    }
    return @($updates | Sort-Object local_ref, remote_ref, local_oid, remote_oid)
}

function Get-GitWriteSubject {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Context,

        [Parameter(Mandatory = $true)]
        [ValidateSet("Commit", "Push")]
        [string]$SelectedOperation,

        [Parameter(Mandatory = $false)]
        [string]$SelectedRemoteName = "",

        [Parameter(Mandatory = $false)]
        [string]$SelectedPushUpdatesPath = ""
    )

    $head = Invoke-GitCapture `
        -ResolvedRepositoryRoot $Context.RepositoryRoot `
        -Arguments @("rev-parse", "--verify", "HEAD") `
        -FailureCode "GIT_WRITE_AUTHORIZATION_HEAD_UNAVAILABLE"
    $branchOutput = & git -C $Context.RepositoryRoot symbolic-ref --short -q HEAD 2>$null
    if ($LASTEXITCODE -eq 0) {
        $branch = ([string](@($branchOutput) -join "`n")).Trim()
    }
    elseif ($LASTEXITCODE -eq 1) {
        $branch = "DETACHED"
    }
    else {
        throw "GIT_WRITE_AUTHORIZATION_BRANCH_UNAVAILABLE"
    }
    $author = Get-GitIdentity $Context.RepositoryRoot "GIT_AUTHOR_IDENT"
    $committer = Get-GitIdentity $Context.RepositoryRoot "GIT_COMMITTER_IDENT"
    $stagedTree = ""
    $remoteNameValue = ""
    $remoteUrlSha256 = ""
    $updates = @()
    if ($SelectedOperation -eq "Commit") {
        $stagedTree = Invoke-GitCapture `
            -ResolvedRepositoryRoot $Context.RepositoryRoot `
            -Arguments @("write-tree") `
            -FailureCode "GIT_WRITE_AUTHORIZATION_STAGED_TREE_UNAVAILABLE"
    }
    else {
        if ([string]::IsNullOrWhiteSpace($SelectedRemoteName)) {
            throw "GIT_WRITE_AUTHORIZATION_REMOTE_REQUIRED"
        }
        $remoteUrl = Invoke-GitCapture `
            -ResolvedRepositoryRoot $Context.RepositoryRoot `
            -Arguments @("remote", "get-url", "--push", $SelectedRemoteName) `
            -FailureCode "GIT_WRITE_AUTHORIZATION_REMOTE_UNAVAILABLE"
        $remoteNameValue = $SelectedRemoteName
        $remoteUrlSha256 = Get-Sha256Text $remoteUrl
        $updates = @(Read-PushUpdates $SelectedPushUpdatesPath)
    }
    $hooksPath = Get-LocalHooksPath $Context.RepositoryRoot
    if ($hooksPath -cne "scripts/git-hooks") {
        throw "GIT_WRITE_AUTHORIZATION_HOOKS_PATH_INVALID"
    }
    return [pscustomobject][ordered]@{
        repository_root_sha256 = Get-Sha256Text $Context.RepositoryRoot
        git_common_directory_sha256 = Get-Sha256Text $Context.GitCommonDirectory
        head = $head
        branch = $branch
        hooks_path = $hooksPath
        author_identity_sha256 = $author.Hash
        committer_identity_sha256 = $committer.Hash
        placeholder_identity = [bool]($author.Placeholder -or $committer.Placeholder)
        staged_tree = $stagedTree
        remote_name = $remoteNameValue
        remote_url_sha256 = $remoteUrlSha256
        push_updates = @($updates)
    }
}

function Assert-ChallengeShape {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Challenge
    )

    Assert-ExactProperties $Challenge @(
        "schema_version",
        "status",
        "operation",
        "channel",
        "nonce",
        "created_at_utc",
        "expires_at_utc",
        "subject",
        "execution_allowed",
        "promotion_status",
        "live_eligibility_status"
    ) "GIT_WRITE_AUTHORIZATION_CHALLENGE_KEYS_INVALID"
    Assert-ExactProperties $Challenge.subject @(
        "repository_root_sha256",
        "git_common_directory_sha256",
        "head",
        "branch",
        "hooks_path",
        "author_identity_sha256",
        "committer_identity_sha256",
        "placeholder_identity",
        "staged_tree",
        "remote_name",
        "remote_url_sha256",
        "push_updates"
    ) "GIT_WRITE_AUTHORIZATION_SUBJECT_KEYS_INVALID"
    if (
        $Challenge.schema_version -isnot [int] -or
        [int]$Challenge.schema_version -ne 1 -or
        $Challenge.status -isnot [string] -or
        [string]$Challenge.status -ne "PENDING" -or
        $Challenge.operation -isnot [string] -or
        [string]$Challenge.operation -notin @("COMMIT", "PUSH") -or
        $Challenge.channel -isnot [string] -or
        [string]$Challenge.channel -notin @("INTERACTIVE", "NONINTERACTIVE") -or
        $Challenge.nonce -isnot [string] -or
        [string]$Challenge.nonce -notmatch '^[0-9a-f]{64}$' -or
        $Challenge.created_at_utc -isnot [string] -or
        $Challenge.expires_at_utc -isnot [string] -or
        $Challenge.execution_allowed -isnot [bool] -or
        [bool]$Challenge.execution_allowed -or
        $Challenge.promotion_status -isnot [string] -or
        [string]$Challenge.promotion_status -ne "RESEARCH_ONLY" -or
        $Challenge.live_eligibility_status -isnot [string] -or
        [string]$Challenge.live_eligibility_status -ne "LIVE_ORDER_BLOCKED"
    ) {
        throw "GIT_WRITE_AUTHORIZATION_CHALLENGE_INVALID"
    }
    $created = [DateTimeOffset]::Parse(
        [string]$Challenge.created_at_utc,
        [Globalization.CultureInfo]::InvariantCulture,
        [Globalization.DateTimeStyles]::RoundtripKind
    )
    $expires = [DateTimeOffset]::Parse(
        [string]$Challenge.expires_at_utc,
        [Globalization.CultureInfo]::InvariantCulture,
        [Globalization.DateTimeStyles]::RoundtripKind
    )
    if ($expires -le $created -or ($expires - $created) -gt $script:authorizationLifetime) {
        throw "GIT_WRITE_AUTHORIZATION_EXPIRY_INVALID"
    }
    foreach ($property in @(
        "repository_root_sha256",
        "git_common_directory_sha256",
        "author_identity_sha256",
        "committer_identity_sha256"
    )) {
        if (
            $Challenge.subject.$property -isnot [string] -or
            [string]$Challenge.subject.$property -notmatch '^[0-9a-f]{64}$'
        ) {
            throw "GIT_WRITE_AUTHORIZATION_SUBJECT_INVALID"
        }
    }
    foreach ($property in @(
        "head",
        "branch",
        "hooks_path",
        "staged_tree",
        "remote_name",
        "remote_url_sha256"
    )) {
        if ($Challenge.subject.$property -isnot [string]) {
            throw "GIT_WRITE_AUTHORIZATION_SUBJECT_INVALID"
        }
    }
    if (
        [string]$Challenge.subject.head -notmatch '^[0-9a-f]{40,64}$' -or
        [string]::IsNullOrWhiteSpace([string]$Challenge.subject.branch) -or
        [string]$Challenge.subject.hooks_path -cne "scripts/git-hooks" -or
        $Challenge.subject.placeholder_identity -isnot [bool] -or
        $null -eq $Challenge.subject.push_updates
    ) {
        throw "GIT_WRITE_AUTHORIZATION_SUBJECT_INVALID"
    }
    $updates = @($Challenge.subject.push_updates)
    if ([string]$Challenge.operation -eq "COMMIT") {
        if (
            [string]$Challenge.subject.staged_tree -notmatch '^[0-9a-f]{40,64}$' -or
            -not [string]::IsNullOrEmpty([string]$Challenge.subject.remote_name) -or
            -not [string]::IsNullOrEmpty([string]$Challenge.subject.remote_url_sha256) -or
            $updates.Count -ne 0
        ) {
            throw "GIT_WRITE_AUTHORIZATION_COMMIT_SUBJECT_INVALID"
        }
    }
    else {
        if (
            -not [string]::IsNullOrEmpty([string]$Challenge.subject.staged_tree) -or
            [string]::IsNullOrWhiteSpace([string]$Challenge.subject.remote_name) -or
            [string]$Challenge.subject.remote_url_sha256 -notmatch '^[0-9a-f]{64}$' -or
            $updates.Count -le 0 -or
            $updates.Count -gt 256
        ) {
            throw "GIT_WRITE_AUTHORIZATION_PUSH_SUBJECT_INVALID"
        }
        foreach ($update in $updates) {
            Assert-ExactProperties $update @(
                "local_ref",
                "local_oid",
                "remote_ref",
                "remote_oid"
            ) "GIT_WRITE_AUTHORIZATION_PUSH_UPDATE_KEYS_INVALID"
            if (
                $update.local_ref -isnot [string] -or
                $update.local_oid -isnot [string] -or
                $update.remote_ref -isnot [string] -or
                $update.remote_oid -isnot [string] -or
                [string]$update.local_ref -notmatch '^(refs/|\(delete\))' -or
                [string]$update.remote_ref -notmatch '^refs/' -or
                [string]$update.local_oid -notmatch '^[0-9a-f]{40,64}$' -or
                [string]$update.remote_oid -notmatch '^[0-9a-f]{40,64}$'
            ) {
                throw "GIT_WRITE_AUTHORIZATION_PUSH_UPDATE_INVALID"
            }
        }
    }
}

function Read-Challenge {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Context,

        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [ValidateSet("Pending", "Approved")]
        [string]$Location
    )

    $directory = if ($Location -eq "Pending") {
        $Context.PendingRoot
    }
    else {
        $Context.ApprovedRoot
    }
    $resolvedPath = Assert-PathWithinDirectory `
        -Path $Path `
        -Directory $directory `
        -FailureCode "GIT_WRITE_AUTHORIZATION_PATH_OUTSIDE_STATE_ROOT"
    $challenge = Read-StrictJsonObject $resolvedPath
    Assert-ChallengeShape $challenge
    if (
        [IO.Path]::GetFileNameWithoutExtension($resolvedPath) -cne
        [string]$challenge.nonce
    ) {
        throw "GIT_WRITE_AUTHORIZATION_NONCE_PATH_MISMATCH"
    }
    return [pscustomobject]@{
        Path = $resolvedPath
        Payload = $challenge
        Sha256 = Get-FileSha256 $resolvedPath
    }
}

function Assert-ChallengeFresh {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Challenge
    )

    $expires = [DateTimeOffset]::Parse(
        [string]$Challenge.expires_at_utc,
        [Globalization.CultureInfo]::InvariantCulture,
        [Globalization.DateTimeStyles]::RoundtripKind
    )
    if ($expires -le [DateTimeOffset]::UtcNow) {
        throw "GIT_WRITE_AUTHORIZATION_EXPIRED"
    }
}

function Assert-ChallengeCurrent {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Context,

        [Parameter(Mandatory = $true)]
        [object]$Challenge,

        [Parameter(Mandatory = $false)]
        [string]$SelectedRemoteName = "",

        [Parameter(Mandatory = $false)]
        [string]$SelectedPushUpdatesPath = ""
    )

    $selectedOperation = if ([string]$Challenge.operation -eq "COMMIT") {
        "Commit"
    }
    else {
        "Push"
    }
    $current = Get-GitWriteSubject `
        -Context $Context `
        -SelectedOperation $selectedOperation `
        -SelectedRemoteName $SelectedRemoteName `
        -SelectedPushUpdatesPath $SelectedPushUpdatesPath
    $expectedJson = $Challenge.subject | ConvertTo-Json -Compress -Depth 12
    $currentJson = $current | ConvertTo-Json -Compress -Depth 12
    if ($expectedJson -cne $currentJson) {
        throw "GIT_WRITE_AUTHORIZATION_SUBJECT_MISMATCH"
    }
}

function Remove-ExpiredPendingArtifacts {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Context
    )

    $candidates = @()
    foreach ($directory in @($Context.PendingRoot, $Context.ApprovedRoot)) {
        if (Test-Path -LiteralPath $directory -PathType Container) {
            $candidates += @(Get-ChildItem -LiteralPath $directory -File -Filter "*.json")
        }
    }
    if ($candidates.Count -gt $script:maximumPendingArtifacts) {
        throw "GIT_WRITE_AUTHORIZATION_PENDING_ARTIFACT_LIMIT_EXCEEDED"
    }
    foreach ($candidate in $candidates) {
        if ($candidate.Name.EndsWith(".approval.json", [StringComparison]::Ordinal)) {
            continue
        }
        $payload = Read-StrictJsonObject $candidate.FullName
        Assert-ChallengeShape $payload
        $expires = [DateTimeOffset]::Parse(
            [string]$payload.expires_at_utc,
            [Globalization.CultureInfo]::InvariantCulture,
            [Globalization.DateTimeStyles]::RoundtripKind
        )
        if ($expires -le [DateTimeOffset]::UtcNow) {
            Remove-Item -LiteralPath $candidate.FullName -Force
            $sidecar = $candidate.FullName + ".approval.json"
            if (Test-Path -LiteralPath $sidecar -PathType Leaf) {
                Remove-Item -LiteralPath $sidecar -Force
            }
        }
    }
}

function Invoke-Prepare {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Context
    )

    if ($Operation -notin @("Commit", "Push")) {
        throw "GIT_WRITE_AUTHORIZATION_OPERATION_REQUIRED"
    }
    foreach ($directory in @(
        $Context.PendingRoot,
        $Context.ApprovedRoot,
        $Context.ConsumedRoot
    )) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }
    Remove-ExpiredPendingArtifacts $Context
    $subject = Get-GitWriteSubject `
        -Context $Context `
        -SelectedOperation $Operation `
        -SelectedRemoteName $RemoteName `
        -SelectedPushUpdatesPath $PushUpdatesPath
    if ($Channel -eq "Interactive" -and [bool]$subject.placeholder_identity) {
        throw "GIT_WRITE_AUTHORIZATION_PLACEHOLDER_IDENTITY_BLOCKED"
    }
    $now = [DateTimeOffset]::UtcNow
    $nonce = New-RandomNonce
    $challenge = [ordered]@{
        schema_version = 1
        status = "PENDING"
        operation = $Operation.ToUpperInvariant()
        channel = $Channel.ToUpperInvariant()
        nonce = $nonce
        created_at_utc = $now.ToString("o")
        expires_at_utc = $now.Add($script:authorizationLifetime).ToString("o")
        subject = $subject
        execution_allowed = $false
        promotion_status = "RESEARCH_ONLY"
        live_eligibility_status = "LIVE_ORDER_BLOCKED"
    }
    $path = Join-Path $Context.PendingRoot ($nonce + ".json")
    Write-JsonAtomic $path $challenge
    $sha256 = Get-FileSha256 $path
    $approvalCommand = "APPROVE_AI4BINANCE_GIT_{0} {1}" -f @(
        $Operation.ToUpperInvariant(),
        $sha256
    )
    [Console]::Out.WriteLine("CHALLENGE_PATH=$path")
    [Console]::Out.WriteLine("APPROVAL_COMMAND=$approvalCommand")
}

function Invoke-Approve {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Context
    )

    if ([string]::IsNullOrWhiteSpace($ChallengePath)) {
        throw "GIT_WRITE_AUTHORIZATION_CHALLENGE_PATH_REQUIRED"
    }
    $challengeRecord = Read-Challenge $Context $ChallengePath "Pending"
    $challenge = $challengeRecord.Payload
    if ([string]$challenge.channel -ne "NONINTERACTIVE") {
        throw "GIT_WRITE_AUTHORIZATION_CHANNEL_MISMATCH"
    }
    Assert-ChallengeFresh $challenge
    $expected = "APPROVE_AI4BINANCE_GIT_{0} {1}" -f @(
        [string]$challenge.operation,
        $challengeRecord.Sha256
    )
    if ($ApprovalText -cne $expected) {
        throw "GIT_WRITE_AUTHORIZATION_EXACT_APPROVAL_REQUIRED"
    }
    $approvedPath = Join-Path $Context.ApprovedRoot (
        [string]$challenge.nonce + ".json"
    )
    New-Item -ItemType Directory -Path $Context.ApprovedRoot -Force | Out-Null
    [IO.File]::Move($challengeRecord.Path, $approvedPath)
    $approvalRecord = [ordered]@{
        schema_version = 1
        status = "APPROVED"
        operation = [string]$challenge.operation
        challenge_sha256 = $challengeRecord.Sha256
        approval_text_sha256 = Get-Sha256Text $ApprovalText
        approved_at_utc = [DateTimeOffset]::UtcNow.ToString("o")
        expires_at_utc = [string]$challenge.expires_at_utc
        execution_allowed = $false
        promotion_status = "RESEARCH_ONLY"
        live_eligibility_status = "LIVE_ORDER_BLOCKED"
    }
    try {
        Write-JsonAtomic ($approvedPath + ".approval.json") $approvalRecord
    }
    catch {
        if (Test-Path -LiteralPath $approvedPath -PathType Leaf) {
            [IO.File]::Move($approvedPath, $challengeRecord.Path)
        }
        throw
    }
    [Console]::Out.WriteLine("AUTHORIZATION_PATH=$approvedPath")
}

function Read-ApprovalSidecar {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [object]$ChallengeRecord
    )

    $sidecarPath = $Path + ".approval.json"
    $sidecar = Read-StrictJsonObject $sidecarPath
    Assert-ExactProperties $sidecar @(
        "schema_version",
        "status",
        "operation",
        "challenge_sha256",
        "approval_text_sha256",
        "approved_at_utc",
        "expires_at_utc",
        "execution_allowed",
        "promotion_status",
        "live_eligibility_status"
    ) "GIT_WRITE_AUTHORIZATION_APPROVAL_KEYS_INVALID"
    if (
        $sidecar.schema_version -isnot [int] -or
        [int]$sidecar.schema_version -ne 1 -or
        $sidecar.status -isnot [string] -or
        [string]$sidecar.status -ne "APPROVED" -or
        $sidecar.operation -isnot [string] -or
        [string]$sidecar.operation -cne [string]$ChallengeRecord.Payload.operation -or
        $sidecar.challenge_sha256 -isnot [string] -or
        [string]$sidecar.challenge_sha256 -cne [string]$ChallengeRecord.Sha256 -or
        $sidecar.approval_text_sha256 -isnot [string] -or
        [string]$sidecar.approval_text_sha256 -notmatch '^[0-9a-f]{64}$' -or
        $sidecar.approved_at_utc -isnot [string] -or
        $sidecar.expires_at_utc -isnot [string] -or
        [string]$sidecar.expires_at_utc -cne [string]$ChallengeRecord.Payload.expires_at_utc -or
        $sidecar.execution_allowed -isnot [bool] -or
        [bool]$sidecar.execution_allowed -or
        $sidecar.promotion_status -isnot [string] -or
        [string]$sidecar.promotion_status -ne "RESEARCH_ONLY" -or
        $sidecar.live_eligibility_status -isnot [string] -or
        [string]$sidecar.live_eligibility_status -ne "LIVE_ORDER_BLOCKED"
    ) {
        throw "GIT_WRITE_AUTHORIZATION_APPROVAL_INVALID"
    }
    $approvedAt = [DateTimeOffset]::Parse(
        [string]$sidecar.approved_at_utc,
        [Globalization.CultureInfo]::InvariantCulture,
        [Globalization.DateTimeStyles]::RoundtripKind
    )
    $createdAt = [DateTimeOffset]::Parse(
        [string]$ChallengeRecord.Payload.created_at_utc,
        [Globalization.CultureInfo]::InvariantCulture,
        [Globalization.DateTimeStyles]::RoundtripKind
    )
    $expiresAt = [DateTimeOffset]::Parse(
        [string]$sidecar.expires_at_utc,
        [Globalization.CultureInfo]::InvariantCulture,
        [Globalization.DateTimeStyles]::RoundtripKind
    )
    if (
        $approvedAt -lt $createdAt -or
        $approvedAt -gt $expiresAt -or
        $approvedAt -gt [DateTimeOffset]::UtcNow.AddMinutes(1)
    ) {
        throw "GIT_WRITE_AUTHORIZATION_APPROVAL_TIME_INVALID"
    }
    return [pscustomobject]@{
        Path = $sidecarPath
        Payload = $sidecar
    }
}

function Invoke-Consume {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Context
    )

    if ([string]::IsNullOrWhiteSpace($ChallengePath)) {
        throw "GIT_WRITE_AUTHORIZATION_CHALLENGE_PATH_REQUIRED"
    }
    $location = if ($Channel -eq "Interactive") { "Pending" } else { "Approved" }
    $challengeRecord = Read-Challenge $Context $ChallengePath $location
    $challenge = $challengeRecord.Payload
    if (
        -not [string]::IsNullOrWhiteSpace($Operation) -and
        $Operation.ToUpperInvariant() -cne [string]$challenge.operation
    ) {
        throw "GIT_WRITE_AUTHORIZATION_OPERATION_MISMATCH"
    }
    if ([string]$challenge.channel -cne $Channel.ToUpperInvariant()) {
        throw "GIT_WRITE_AUTHORIZATION_CHANNEL_MISMATCH"
    }
    Assert-ChallengeFresh $challenge
    $approvalSidecar = $null
    if ($Channel -eq "Interactive") {
        if ([bool]$challenge.subject.placeholder_identity) {
            throw "GIT_WRITE_AUTHORIZATION_PLACEHOLDER_IDENTITY_BLOCKED"
        }
        if ($ApprovalText.ToUpperInvariant() -cne [string]$challenge.operation) {
            throw "GIT_WRITE_AUTHORIZATION_INTERACTIVE_APPROVAL_DECLINED"
        }
    }
    else {
        $approvalSidecar = Read-ApprovalSidecar $challengeRecord.Path $challengeRecord
    }
    Assert-ChallengeCurrent `
        -Context $Context `
        -Challenge $challenge `
        -SelectedRemoteName $RemoteName `
        -SelectedPushUpdatesPath $PushUpdatesPath
    New-Item -ItemType Directory -Path $Context.ConsumedRoot -Force | Out-Null
    $consumedAt = [DateTimeOffset]::UtcNow
    $consumedStem = $consumedAt.ToString("yyyyMMddTHHmmssfffffffZ") + "-" + [string]$challenge.nonce
    $consumedChallengePath = Join-Path $Context.ConsumedRoot ($consumedStem + ".challenge.json")
    [IO.File]::Move($challengeRecord.Path, $consumedChallengePath)
    if ($null -ne $approvalSidecar) {
        [IO.File]::Move(
            $approvalSidecar.Path,
            (Join-Path $Context.ConsumedRoot ($consumedStem + ".approval.json"))
        )
    }
    $audit = [ordered]@{
        schema_version = 1
        status = "CONSUMED"
        operation = [string]$challenge.operation
        channel = [string]$challenge.channel
        nonce = [string]$challenge.nonce
        challenge_sha256 = $challengeRecord.Sha256
        consumed_at_utc = $consumedAt.ToString("o")
        subject = $challenge.subject
        execution_allowed = $false
        promotion_status = "RESEARCH_ONLY"
        live_eligibility_status = "LIVE_ORDER_BLOCKED"
    }
    Write-JsonAtomic `
        (Join-Path $Context.ConsumedRoot ($consumedStem + ".audit.json")) `
        $audit
    [Console]::Out.WriteLine("GIT_WRITE_AUTHORIZATION_CONSUMED")
    [Console]::Out.WriteLine("OPERATION=$([string]$challenge.operation)")
    [Console]::Out.WriteLine("RESEARCH_ONLY")
    [Console]::Out.WriteLine("LIVE_ORDER_BLOCKED")
}

try {
    $context = Resolve-RepositoryContext $RepositoryRoot
    switch ($Mode) {
        "Prepare" { Invoke-Prepare $context }
        "Approve" { Invoke-Approve $context }
        "Consume" { Invoke-Consume $context }
    }
    exit 0
}
catch {
    Write-GitAuthorizationBlock (
        "GIT_WRITE_AUTHORIZATION_ERROR: " + $_.Exception.Message
    )
    exit 1
}
