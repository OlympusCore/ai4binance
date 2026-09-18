---
document_id: AI4B-GOV-STD-RFG-103
title: AI4BINANCE Repository Artifact Separation Governance Standard
document_type: STANDARD
version: 1.0.3
status: ACTIVE
owner: Enterprise Governance
authority_level: NORMATIVE
authority_layer: L4_REPOSITORY_STANDARDS_CONTROLS_QUALITY_POLICIES
authority_scope: repository_artifact_separation_governance
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
canonical_path: docs/standards/standard_repository_artifact_separation_governance.md
machine_enforceable: false
audit_required: true
classification: INTERNAL
---
# AI4BINANCE Repository Artifact Separation Governance Standard

## ELI10

This standard section defines source, runtime, data, generated artifact, logging, research, archive, temporary file, absolute path, and path traversal rules.

## Source Lineage

- Source file: `docs/standards/standard_repository_file_governance.md`
- Source section start: `## 12. Source / Runtime / Artifact / Report Separation`
- This file preserves a bounded section of the governed source document.

## 12. Source / Runtime / Artifact / Report Separation

The repository must maintain separation between:

```text
source code
runtime state
machine-readable generated artifacts
human-readable reports
logs
archives
```

Canonical separation:

```text
src/        = source code
tests/      = tests
runtime/data/       = downloaded inputs, prepared datasets, and local execution data
runtime/dashboard/  = generated local dashboard deployment and protected browser state
runtime/analysis/   = generated intermediate analysis output
runtime/artifacts/  = machine-readable generated evidence
runtime/audit/      = preserved formal audit and evidence trail
runtime/reports/    = human-readable runtime summaries
runtime/state/      = mutable runtime state
runtime/test/       = test-run outputs and bounded validator run bundles
runtime/logs/       = append-only operational telemetry
docs/       = governed documentation
archive/    = retired or historical content
runtime/    = local execution workspace; canonical grouping root for mutable,
             generated, reproducible, and execution/run-produced outputs
```

A human-readable report must not be treated as primary machine evidence. Machine-readable artifacts are the evidence source. Reports are derived views.

`runtime/reports/` is limited to human-readable report surfaces such as
Markdown. JSON, JSONL, XML, test logs, and other machine-consumed outputs must
be routed to `runtime/artifacts/` or `runtime/test/` according to their role.

`runtime/dashboard/` is a reproducible deployment target, not a source owner.
Its executable assets must be reproducible from tracked canonical inputs and a
hash-bearing deployment receipt. Machine-specific configuration, health, logs,
and the browser profile remain local runtime state. The browser profile is
protected private state and must not be copied, archived, or inspected by
generic hygiene workflows.

`runtime/audit/` and `runtime/tmp/` must not share cleanup semantics.
`runtime/audit/` is preserved evidence and requires owner-scoped retention or
archival handling. `runtime/tmp/` is disposable temporary output and may be
cleaned as generated runtime material.

Quality, `artifact_hygiene`, and repository-validation support workflows that
launch external PowerShell or Python helpers must remain run-scoped and fail
closed. Potentially large `stdout`/`stderr` streams must be redirected to
run-scoped files instead of retained as unbounded in-memory capture when the
helper can emit repository scans, pytest output, security output, or cleanup
inventories. Each launched helper must have an explicit caller-owned timeout.
On timeout, cancellation, or abnormal termination, the caller must terminate
the full descendant process tree and fail the run if helper descendants remain
alive after the cleanup grace window. Successful completion must not leave
orphaned PowerShell or Python helper processes bound to deleted temp roots or
stale capture files outside approved temporary or `runtime/` paths.

Any mutable, generated, reproducible, or execution/run-produced output must be
grouped under `runtime/` first and then routed into the appropriate governed
subtree. Legacy top-level roots are compatibility surfaces only and do not
replace the canonical `runtime/` grouping rule.

Repository root describes the system; `runtime/` describes what the system
produces while operating. If deleting a file would make the repository
undefined or remove governed authority, that file is not runtime output and
must remain under the governed source, policy, schema, registry, or docs
surface that defines it.

## 13. Data Directory Standard

Canonical runtime data structure:

```text
runtime/data/
├── datasets/
├── raw/
├── staged/
├── normalized/
├── curated/
├── feature_store/
├── reference/
└── cache/
```

Canonical data lifecycle:

```text
raw
→ staged
→ normalized
→ curated
→ feature_store
```

`runtime/data/raw/` should be immutable after ingestion.

Agents must not maintain duplicate local OHLCV copies such as:

```text
trend/data/
momentum/data/
volume/data/
```

All analysis components should consume a shared validated market snapshot.

## 14. Generated Artifact Standard

Machine-generated artifacts must be stored under:

```text
runtime/artifacts/
├── decisions/
├── validation/
├── research/
├── quality/
├── repository_validation/
├── assurance/
├── benchmarks/
└── context/
```

Runtime artifact filename pattern:

```text
<artifact_type>_<utc_timestamp>_<short_id>.<ext>
```

Timestamp standard:

```text
YYYYMMDDTHHMMSSZ
```

Examples:

```text
decision_20260817T180000Z_a84d61f2.json
signal_20260817T180000Z_60cad341.json
audit_20260817T180002Z_e6124bb5.json
```

Generated artifacts must not be written into `src/`, `docs/`, or `tests/`.

Runtime inventory must use bounded scans and report truncation or access
failures explicitly. Capacity observations are warnings and do not authorize
deletion. Protected state, audit logs, and maintenance archives require an
owner-scoped retention decision before archive or cleanup.

Generated coverage outputs should be grouped under:

```text
runtime/artifacts/coverage/runs/<run_id>/
```

Generated repository-validator outputs should use a deterministic run-id
directory layout:

```text
runtime/test/repository-validator/runs/<run_id>/
```

Durable repository-validator audit evidence should be grouped under:

```text
runtime/audit/repository-validator/runs/<run_id>/
```

## 15. Runtime State Standard

Runtime state must be stored under:

```text
runtime/state/
```

Recommended structure:

```text
runtime/state/
├── runtime/
├── sessions/
├── locks/
├── checkpoints/
├── paper_trading/
└── local/
```

Runtime state is mutable and must not be treated as source-of-truth documentation.

Runtime state must not grant live trading authority.

The top-level `runtime/` folder is an allowed local execution workspace for
ephemeral process files, scratch runtime outputs, and tool-local state. It is
not a source-of-truth location, must remain excluded from governed authority,
and must not supersede `runtime/state/`, `runtime/artifacts/`, `runtime/logs/`, `runtime/reports/`, or `docs/`.
Any tracked artifact under `runtime/` requires an explicit governance reason,
owner, retention rule, and validation evidence. If a file must survive deletion
to preserve repository meaning, it belongs outside `runtime/`.

Default AI4BINANCE state remains:

```text
PAPER_TRADING
MANUAL_CONFIRMATION
LIVE_EXECUTION_DISABLED
READ_ONLY_API
```

## 15.1 Backup Manifest Standard

Backup and mirror manifests are evidence contracts only. They must preserve
recovery context without creating repository authority.

The machine-readable backup manifest schema is:

```text
schemas/governance/repository_backup_manifest.schema.json
```

Required backup manifest invariants:

```yaml
authority: BACKUP_ONLY
source_of_truth: false
contains_secrets: false
may_override_repository: false
may_define_authority: false
may_promote_runtime_artifacts: false
```

Backup manifests may reference runtime context such as a local checkout path or
Drive mirror path, but those values are evidence metadata only. They must not
replace repository-relative canonical paths and must not promote runtime,
generated, cache, or report artifacts into active governance.

## 16. Logging Standard

Logs must be stored under:

```text
runtime/logs/
```

Recommended structure:

```text
runtime/logs/
├── application/
├── audit/
├── security/
├── validation/
├── data_quality/
└── runtime/
```

Logs must not contain:

- API secrets
- private keys
- seed phrases
- full credentials
- personal sensitive data unless explicitly authorized and protected
- live order authorization tokens

Logs are append-only operational telemetry. They are evidence inputs, not governance source-of-truth documents.

## 17. Research vs Production Standard

Research artifacts must be separated from production candidate artifacts.

Recommended structure:

```text
research/
├── experiments/
├── notebooks/
├── candidate_strategies/
├── parameter_candidates/
├── lessons/
└── rejected/
```

Research outputs must not automatically become production authority.

Promotion path:

```text
RESEARCH
→ BACKTEST
→ WALK_FORWARD
→ OOS
→ ROBUSTNESS
→ PAPER
→ LIVE_CANDIDATE
→ LIVE_APPROVED
```

Backtest success does not authorize live trading. Strategy candidates remain `RESEARCH_ONLY` until deterministic promotion gates pass.

## 18. Archive Standard

Archived artifacts must be stored under:

```text
archive/
```

Archive content must preserve:

- original path
- reason for archival
- archival date
- superseding artifact, if any
- owner
- retention rule
- restoration rule, if applicable

Archived content must not be imported by production code or treated as active source-of-truth.

Archive filenames may use controlled lifecycle prefixes when helpful:

```text
deprecated_
superseded_
rejected_
retired_
```

These prefixes should not be used for active governed source documents.

## 19. Temporary File Standard

Temporary files must not be stored in governed source locations.

Allowed temporary locations:

```text
tmp/
runtime/tmp/
runtime/state/local/
```

`runtime/test/` is not a general temporary root. It is the canonical location
for test-run outputs that need stable run grouping or bounded audit review,
such as `runtime/test/acl/`, `runtime/test/hypothesis/`,
`runtime/test/pytest/`, and `runtime/test/repository-validator/`.

`runtime/tmp/` remains `DELETE_SAFE` generated temp when no active process owns
the subtree. `runtime/audit/` must not be included in broad temporary cleanup
commands.

Forbidden temporary patterns in governed source paths:

```text
temp.py
new.py
old.py
copy.py
copy_of_
final_
final_v2
backup_
bak_
```

Temporary files must not be committed unless explicitly governed as test fixtures or evidence samples.

## 20. Absolute Path Prohibition

Production code must not embed machine-specific absolute paths.

Repository file paths are dynamic. Code, scripts, tasks, validators and
developer tooling must resolve the active repository root from the current
workspace, an explicit CLI `--repository-root` argument, an injected
`repository_root` value, or `${workspaceFolder}` for VS Code configuration.
Machine-specific checkout locations are runtime context only; they are not
canonical repository identity.

Forbidden examples:

```text
C:\vscode-projects\ai4binance\...
H:\BackUP\Downloads\...
/Users/name/Desktop/...
```

Use repository-relative paths, environment configuration, `${workspaceFolder}`,
or `pathlib`.

Preferred pattern:

```python
from pathlib import Path

def artifact_path(repository_root: Path, relative_path: str) -> Path:
    return repository_root / relative_path
```

Environment-specific values must be configured outside domain logic.

## 21. Path Traversal Security

User-provided or external values must not be directly concatenated into filesystem paths.

Values requiring normalization include:

```text
symbol
timeframe
exchange
workflow_id
artifact_type
provider
source_id
```

Unsafe path tokens must be blocked:

```text
../
..\
/
\
:
*
?
"
<
>
|
```

Path construction must use safe path builders and validated identifiers.

Expected normalized symbol example:

```text
HOTUSDT
```
