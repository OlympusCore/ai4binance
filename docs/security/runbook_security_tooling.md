---
document_id: AI4B-SEC-RUN-001
title: AI4BINANCE Security Tooling
document_type: RUNBOOK
version: 1.1.0
status: ACTIVE
owner: Enterprise Knowledge Governance
authority_level: NORMATIVE
authority_layer: L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS
authority_scope: security_tooling
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
canonical_path: docs/security/runbook_security_tooling.md
machine_enforceable: true
audit_required: true
classification: INTERNAL
---

# Local Security Tooling

This runbook defines the local, reproducible, report-focused security tooling
for AI4BINANCE. Security scans produce evidence and blockers; they do not grant
trading authority, change risk parameters, remediate findings automatically, or
promote any live capability.

## ELI10

These tools work like a smoke alarm. They can detect a possible problem and
block unsafe progress, but they do not fix code, approve credentials, or place
orders. Until findings are reviewed and resolved, the system remains
`RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED`.

## Built Tools

| Tool | Scope | Installation | Authority Limit |
|---|---|---|---|
| Hypothesis | Deterministic property tests | `dev` extra | Test-only |
| Ruff | Static quality and security linting | `dev` extra | Report/block |
| Bandit | Python security scanning | `dev` extra | Report/block |
| pip-audit + truststore | Local Python dependency CVE scan with Windows trust store support | `security` extra | Report-only |
| Gitleaks 8.30.1 | Secret scanning in staged content and Git history | Local, SHA-256 verified binary | Redacted report/block |

Gitleaks is not added to the global `PATH`. The binary is pinned under
`tools/gitleaks/v8.30.1/`, kept local to the repository workspace, and ignored by
Git. Expected Windows x64 archive SHA-256 value:

```text
d29144deff3a68aa93ced33dddf84b7fdc26070add4aa0f4513094c8332afc4e
```

## Installation and Verification

```powershell
Set-Location <repository-root>
.\scripts\install_security_tooling.ps1
.\.venv\Scripts\python.exe -m pip_audit --version
.\tools\gitleaks\v8.30.1\gitleaks.exe version
```

The installation script uses the project `security` extra for `pip-audit` and
`truststore`. It downloads the official Gitleaks release, verifies the SHA-256
checksum, and writes only to the repository-local tooling directory.

## Local Git Guard

Configure the repository-local Git guard:

```powershell
.\scripts\configure_git_security.ps1
git config --show-origin --get core.hooksPath
git config --show-origin --get core.excludesFile
```

Expected local configuration:

```text
core.hooksPath=scripts/git-hooks
core.excludesFile=.git/info/exclude
```

The shared pre-commit hook runs a staged Gitleaks scan:

```powershell
.\tools\gitleaks\v8.30.1\gitleaks.exe git --staged --redact=100 --no-banner --no-color --exit-code 1 .
```

This developer guard is useful, but it is not an enforcement boundary by itself:
Git hooks can be bypassed with `--no-verify`. CI and report-based scans remain
the independent evidence layer.

## Report-Based Scanning

```powershell
.\scripts\security_tooling_audit.ps1
```

When the default PyPI vulnerability service is unavailable or slow, keep the
same local Windows trust chain and produce dependency-audit evidence through the
OSV service:

```powershell
.\scripts\security_tooling_audit.ps1 -VulnerabilityService osv -PipAuditTimeoutSeconds 10
```

Output is written to `runtime/artifacts/assurance/security_tooling/`. Gitleaks findings are fully
redacted with `--redact=100`. `pip-audit` uses the Windows certificate store
through `truststore`, skips the local editable project package, and scans
installed dependencies. No security tool is called with `--fix`.

Missing tooling, failed scans, invalid reports, dependency vulnerabilities, and
secret findings produce explicit blockers such as:

```text
GITLEAKS_NOT_INSTALLED
SECRET_SCAN_FAILED
SECRET_FINDINGS_REQUIRE_REVIEW
DEPENDENCY_AUDIT_FAILED
DEPENDENCY_VULNERABILITIES_REQUIRE_REVIEW
```

Any unresolved blocker preserves:

```text
RESEARCH_ONLY
LIVE_ORDER_BLOCKED
```

## CI Security Evidence

`.github/workflows/security_tooling.yml` runs the same report-only security audit
with full Git history checkout and uploads `runtime/artifacts/assurance/security_tooling/` as
review evidence. CI does not auto-fix findings, change dependencies silently, or
grant live execution authority.

## Secret Handling Boundaries

`.gitignore` is not a secret scanner. It prevents selected local files from
being tracked by Git, while Gitleaks inspects tracked or staged content for
secret-like material. Both controls are required and neither replaces the other.

Reviewed false positives must be handled through evidence-based exceptions only.
Do not suppress scanner rules or add baselines merely to make a gate pass.

## Uninstalled recommendations

NautilusTrader, Pandera, Graphiti, OpenLineage, vectorbt, Freqtrade, LangGraph,
Prefect, Dagster, Temporal, GraphRAG, Neo4j GraphRAG, MLflow, Evidently,
OpenTelemetry, DVC, Qlib, and Hummingbot are not installed in this slice as
general dependencies. Each can only be evaluated through measurable
contribution, license and dependency review, isolated pilot evidence, OOS
validation, and a rollback plan.

In all cases:

```text
RESEARCH_ONLY
LIVE_ORDER_BLOCKED
```

