[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path

Push-Location $repositoryRoot
try {
    & git rev-parse --is-inside-work-tree | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "GIT_SECURITY_NOT_A_REPOSITORY: $repositoryRoot"
    }

    $gitTopLevel = (& git rev-parse --show-toplevel).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($gitTopLevel)) {
        throw "GIT_SECURITY_REPOSITORY_ROOT_UNAVAILABLE"
    }

    $resolvedGitTopLevel = [IO.Path]::GetFullPath($gitTopLevel)

    $preCommitHookPath = Join-Path $resolvedGitTopLevel "scripts\git-hooks\pre-commit"
    if (-not (Test-Path -LiteralPath $preCommitHookPath -PathType Leaf)) {
        throw "GIT_SECURITY_PRE_COMMIT_HOOK_MISSING: $preCommitHookPath"
    }
    $prePushHookPath = Join-Path $resolvedGitTopLevel "scripts\git-hooks\pre-push"
    if (-not (Test-Path -LiteralPath $prePushHookPath -PathType Leaf)) {
        throw "GIT_SECURITY_PRE_PUSH_HOOK_MISSING: $prePushHookPath"
    }
    $qualityGateGuardPath = Join-Path (
        $resolvedGitTopLevel
    ) "scripts\check_quality_gate_git_write_guard.ps1"
    if (-not (Test-Path -LiteralPath $qualityGateGuardPath -PathType Leaf)) {
        throw "GIT_SECURITY_QUALITY_GATE_GUARD_MISSING: $qualityGateGuardPath"
    }
    $gitWriteAuthorizationPath = Join-Path (
        $resolvedGitTopLevel
    ) "scripts\git_write_authorization.ps1"
    if (-not (Test-Path -LiteralPath $gitWriteAuthorizationPath -PathType Leaf)) {
        throw "GIT_SECURITY_WRITE_AUTHORIZATION_HELPER_MISSING: $gitWriteAuthorizationPath"
    }

    $localUserName = [string](& git config --local --get "user.name" 2>$null)
    $localUserNameExitCode = $LASTEXITCODE
    $localUserEmail = [string](& git config --local --get "user.email" 2>$null)
    $localUserEmailExitCode = $LASTEXITCODE
    if ($localUserNameExitCode -notin @(0, 1) -or $localUserEmailExitCode -notin @(0, 1)) {
        throw "GIT_SECURITY_LOCAL_IDENTITY_CHECK_FAILED"
    }
    if (
        $localUserName.Trim() -ceq "Quality Gate" -or
        $localUserEmail.Trim() -ceq "quality@example.invalid"
    ) {
        throw "GIT_SECURITY_PLACEHOLDER_IDENTITY_BLOCKED"
    }

    $effectiveAuthor = [string](& git var GIT_AUTHOR_IDENT 2>$null)
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($effectiveAuthor)) {
        throw "GIT_SECURITY_EFFECTIVE_IDENTITY_UNAVAILABLE"
    }
    if (
        $effectiveAuthor -match '^Quality Gate <' -or
        $effectiveAuthor -match '<quality@example\.invalid> '
    ) {
        throw "GIT_SECURITY_PLACEHOLDER_IDENTITY_BLOCKED"
    }

    & git config --local "core.hooksPath" "scripts/git-hooks"
    if ($LASTEXITCODE -ne 0) {
        throw "GIT_SECURITY_HOOKS_PATH_CONFIG_FAILED"
    }

    & git config --local "core.excludesFile" ".git/info/exclude"
    if ($LASTEXITCODE -ne 0) {
        throw "GIT_SECURITY_EXCLUDES_FILE_CONFIG_FAILED"
    }

    $configuredHooksPath = (& git config --local --get "core.hooksPath").Trim()
    $configuredExcludesFile = (& git config --local --get "core.excludesFile").Trim()
    if ($configuredHooksPath -ne "scripts/git-hooks") {
        throw "GIT_SECURITY_HOOKS_PATH_VERIFY_FAILED: $configuredHooksPath"
    }
    if ($configuredExcludesFile -ne ".git/info/exclude") {
        throw "GIT_SECURITY_EXCLUDES_FILE_VERIFY_FAILED: $configuredExcludesFile"
    }

    Write-Output "GIT_SECURITY_CONFIGURED"
    Write-Output "REPOSITORY_ROOT=$resolvedGitTopLevel"
    Write-Output "CORE_HOOKS_PATH=$configuredHooksPath"
    Write-Output "CORE_EXCLUDES_FILE=$configuredExcludesFile"
    Write-Output "GIT_WRITE_AUTHORIZATION=EXACT_SUBJECT_BOUND_SINGLE_USE"
    Write-Output "RESEARCH_ONLY"
    Write-Output "LIVE_ORDER_BLOCKED"
}
finally {
    Pop-Location
}
