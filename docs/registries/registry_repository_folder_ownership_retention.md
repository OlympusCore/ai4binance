---
document_id: AI4B-REPO-REG-001
title: AI4BINANCE Folder Ownership Registry
document_type: REGISTRY
version: 1.0.3
status: ACTIVE
owner: Enterprise Knowledge Governance
authority_level: NORMATIVE
authority_layer: L5_REGISTRIES_ROADMAP
authority_scope: repository_folder_ownership_retention
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
canonical_path: docs/registries/registry_repository_folder_ownership_retention.md
machine_enforceable: true
audit_required: true
classification: INTERNAL
---

# Folder Ownership Matrix

## ELI10

This document is a folder label book. It specifies which folder is to be protected, which is a generated temporary output, and which can only be deleted after approval; thus, it prevents incorrect deletion of source files.
It indicates which folder is to be protected, which is a generated temporary output, and which can only be deleted after approval; thus, it prevents incorrect deletion of source files.
It ensures that source files are not mistakenly deleted.


This matrix keeps cleanup decisions reviewable. Generated folders may be pruned
only through an explicit cleanup mode backed by a registered retention policy;
protected and evidence folders need an owner decision first.
`runtime/` is the canonical grouping root for mutable, generated, reproducible,
and execution/run-produced outputs. If deleting a file would make the
repository undefined or remove governed authority, it does not belong under
`runtime/`.

Decision values:

- `KEEP_DOMAIN_ROOT`: expected project root, keep even when empty.
- `ARCHIVE_LOCAL`: local/evidence output; archive or prune only by policy.
- `DELETE_EMPTY`: may be removed when confirmed empty and unreferenced.
- `PROTECTED`: never broad-delete or stage content.
- `GENERATED`: reproducible output; cleanup requires explicit mode or `-Apply`.
- `LEGACY_RUNTIME_ROOT`: legacy local or evidence root; read for compatibility
  but write new runtime output under `runtime/`.
- `ACL_FORCED_GENERATED`: generated `artifacts/test_temp` cleanup may repair
  ownership/ACL only after written approval and repo-boundary verification.

| Path | Owner area | Type | Decision | Retention | Notes |
| --- | --- | --- | --- | --- | --- |
| `.pytest_cache` | Quality | Generated cache | GENERATED | on demand | Recreated by Pytest; safe for `Caches` cleanup mode without ACL forcing. |
| `.mypy_cache` | Quality | Generated cache | GENERATED | on demand | Recreated by MyPy. |
| `.ruff_cache` | Quality | Generated cache | GENERATED | on demand | Recreated by Ruff. |
| `.test-tmp` | Quality | Generated temp | GENERATED | on demand | Historical test temp. |
| `.coverage` | Quality | Generated coverage | GENERATED | per quality run | Removed before full quality gate; recreated under isolated temp path. |
| `.coverage.*` | Quality | Generated coverage | GENERATED | per quality run | Remove with `Coverage` cleanup mode. |
| `coverage.xml` | Quality | Generated coverage | GENERATED | on demand | Recreated by coverage tooling. |
| `htmlcov` | Quality | Generated coverage report | GENERATED | on demand | Recreated by coverage tooling. |
| `runtime` | Runtime workspace | Local execution workspace | KEEP_DOMAIN_ROOT | manual | Canonical grouping root for mutable, generated, reproducible, and execution/run-produced outputs. Files whose deletion would make the repository undefined must stay under the governed source, policy, schema, registry, or docs surface that owns them. |
| `runtime/data` | Data acquisition | Runtime data | KEEP_DOMAIN_ROOT | manual | Canonical runtime data root. |
| `runtime/data/datasets` | Data acquisition | Prepared runtime datasets | ARCHIVE_LOCAL | dataset revision | Canonical dataset boundary; legacy `runtime/datasets` writes are forbidden. |
| `runtime/data/market-reset-*` | Data acquisition | Recovery snapshot | ARCHIVE_LOCAL | owner decision | Every reset snapshot must carry `.ai4binance-retention.json` with owner, purpose, creation/review timestamps, disposition, replacement path, and explicit deletion authorization. Generic cleanup is forbidden. |
| `runtime/analysis` | Analysis | Generated intermediate analysis | ARCHIVE_LOCAL | explicit scope | Canonical runtime analysis root for reproducible intermediate outputs. |
| `runtime/state` | Runtime state | Runtime state | KEEP_DOMAIN_ROOT | manual | Canonical runtime state root. |
| `runtime/cache` | Runtime cache | Generated cache | GENERATED | on demand | Canonical runtime cache root. |
| `runtime/logs` | Observability | Generated evidence | ARCHIVE_LOCAL | 7 days active | Canonical runtime log root. |
| `runtime/audit` | Audit | Evidence | ARCHIVE_LOCAL | manual | Canonical runtime audit root. Preserve as formal audit trail; do not treat as `DELETE_SAFE` temp. |
| `runtime/audit/repository-validator` | Audit | Evidence | ARCHIVE_LOCAL | explicit scope | Durable repository-validator audit evidence root. |
| `runtime/artifacts` | Quality and validation | Generated evidence | ARCHIVE_LOCAL | explicit scope | Canonical runtime artifact root. |
| `runtime/artifacts/maintenance_archive` | Maintenance | Generated archive | ARCHIVE_LOCAL | review after 90 days; keep latest 10 | Cleanup receipts and archives; thresholds trigger owner review only and never authorize automatic deletion. |
| `runtime/artifacts/quality/gate/runs` | Quality | Generated evidence | ARCHIVE_LOCAL | review after 30 days; keep latest 25 | Quality evidence is snapshot-bound. Thresholds trigger owner review only and never authorize automatic deletion. |
| `runtime/artifacts/user_reports` | Reporting | Generated report evidence | ARCHIVE_LOCAL | review after 30 days; keep latest 25 | Owner review is required before removal. |
| `runtime/artifacts/opportunity-radar` | Advisory radar | Generated research evidence | ARCHIVE_LOCAL | review after 14 days; keep latest 25 | Research-only evidence; owner review is required before removal. |
| `runtime/artifacts/research/learning` | Research | Machine-readable research evidence | ARCHIVE_LOCAL | explicit scope | Canonical learning evidence root. |
| `runtime/artifacts/research/historical_replay` | Research | Replay evidence and wallet epochs | ARCHIVE_LOCAL | explicit scope | Canonical historical replay evidence root. |
| `runtime/artifacts/benchmarks/performance` | Performance | Machine-readable benchmark evidence | ARCHIVE_LOCAL | explicit scope | Canonical performance benchmark root. |
| `runtime/artifacts/coverage` | Quality | Generated coverage evidence | ARCHIVE_LOCAL | per quality run | Canonical runtime coverage evidence root. |
| `runtime/reports` | Reporting | Human-readable generated report | ARCHIVE_LOCAL | explicit scope | Markdown and equivalent human-readable summaries only; machine evidence belongs under `runtime/artifacts` or `runtime/test`. |
| `runtime/reports/virtual_wallets` | Portfolio/accounting | Generated report evidence | ARCHIVE_LOCAL | review after 7 days; keep latest 25 | Owner review is required before removal; reports do not grant execution authority. |
| `runtime/dashboard` | Local dashboard | Generated deployment | GENERATED | redeploy on demand | Must be reproducible from tracked canonical source and carry a hash-bearing source manifest. |
| `runtime/dashboard/browser-profile` | Local dashboard | Protected private state | PROTECTED | never generic cleanup | Never copy, archive, inspect, or remove through generic hygiene workflows. |
| `runtime/test` | Quality | Generated test runtime | GENERATED | on demand | Canonical runtime test-output root for bounded test runs and validator run bundles. |
| `runtime/test/acl` | Quality | Generated test runtime | GENERATED | on demand | Canonical ACL test-output root. |
| `runtime/test/hypothesis` | Quality | Generated test runtime | GENERATED | on demand | Canonical Hypothesis runtime evidence root. |
| `runtime/test/pytest` | Quality | Generated test runtime | GENERATED | on demand | Canonical pytest runtime output root when stable run grouping is needed. |
| `runtime/test/repository-validator` | Quality | Generated test runtime | GENERATED | on demand | Canonical repository-validator run bundle root. |
| `runtime/test/repository-validator/runs` | Quality | Generated test runs | GENERATED | 7 days; keep latest 20 | Automatic cleanup is allowed only through `RuntimeRunRetention`; active or process-referenced runs fail closed. |
| `runtime/models` | ModelGovernance | Protected local state | PROTECTED | manual | Runtime-local model support surface. Do not broad-delete without owner review. |
| `runtime/tmp` | Temporary runtime | Generated temp | GENERATED | 2 days | Canonical runtime temp root. `RuntimeTmpRetention` may remove only stale direct children that have no active owner, process reference, reparse point, or Git worktree metadata. |
| `runtime/tmp/process` | Temporary runtime | Process-owned temp | GENERATED | 2 days | Canonical process-owned temp root. Every long-running owner should publish `.ai4binance-process-owner.json`; unreadable or active ownership fails closed. |
| `runtime/tmp/process/pytest` | Quality | Process-owned pytest temp | GENERATED | 2 days | Canonical disposable pytest basetemp root. `ProcessTempRetention` operates on stale children, never on the root as one broad target. |
| `runtime/tmp/pytest` | Quality | Legacy pytest temp | LEGACY_RUNTIME_ROOT | on demand | Compatibility-only legacy root. New writes are forbidden; `TestTempRetention` may remove it explicitly. |
| `artifacts/test_temp` | Quality | Generated temp | ACL_FORCED_GENERATED | 2 days | Legacy generated temp root. Retain only for historical cleanup and ACL recovery of stale children; do not point new pytest basetemp directories here. `-ForceAcl` is allowed only for stale direct children under this root after written approval; protected roots remain untouched. |
| `logs` | Observability | Legacy generated evidence | LEGACY_RUNTIME_ROOT | 7 days active | Read for compatibility. New writes should target `runtime/logs`. |
| `artifacts/maintenance-archive` | Maintenance | Legacy generated archive | LEGACY_RUNTIME_ROOT | manual | Contains cleanup manifests and archived logs; ignored from Git. New writes should target `runtime/artifacts`. |
| `runtime/artifacts/repository_validation/folder_structure_audit` | Maintenance | Legacy generated report | LEGACY_RUNTIME_ROOT | latest local | Ignored from Git. New writes should target `runtime/artifacts`. |
| `runtime/artifacts/research/backtest/validation` | Research validation | Generated evidence | ARCHIVE_LOCAL | explicit scope | Canonical research validation artifact root. |
| `data` | Data acquisition | Legacy domain state | LEGACY_RUNTIME_ROOT | manual | May contain reproducibility inputs. New writes should target `runtime/data`. |
| `state` | Runtime state | Legacy domain state | LEGACY_RUNTIME_ROOT | manual | Avoid deleting active runtime state. New writes should target `runtime/state`. |
| `runtime/state/private` | Private runtime state | Protected local state | PROTECTED | never broad-delete | May contain private local-only data. |
| `secrets` | Security | Protected local state | PROTECTED | never broad-delete | Only `.gitkeep` is commit-eligible. |
| `models` | Local LLM | Protected local state | PROTECTED | manual | Large local models or placeholders. New governed model metadata belongs under `config/models` or `docs/registries`. |
| `wallet` | Portfolio/accounting | Legacy domain evidence | LEGACY_RUNTIME_ROOT | manual | Wallet state must not contaminate backtests. New private state should target `runtime/state/private` only after privacy guards are updated. |
| `orders` | Execution/audit | Legacy domain evidence | LEGACY_RUNTIME_ROOT | manual | Preserve rejected order and blocker evidence. |
| `opportunities` | Advisory radar | Legacy domain evidence | LEGACY_RUNTIME_ROOT | manual | Keep blocked opportunity context auditable. |
| `alerts` | Notifications | Project folder | DELETE_EMPTY | manual | Remove only if empty and unreferenced. |
| `analysis` | Research/reporting | Legacy project folder | LEGACY_RUNTIME_ROOT | manual | Review useful reports before pruning. |
| `factory` | Agent planning | Project folder | ARCHIVE_LOCAL | manual | Governance/planning surface. |
| `futures` | Supplementary research | Project folder | DELETE_EMPTY | manual | Spot decisions remain primary. |
| `spot` | Spot domain | Project folder | KEEP_DOMAIN_ROOT | manual | Expected platform domain folder. |
| `intelligence` | Market intelligence | Project folder | DELETE_EMPTY | manual | Remove only if empty and unreferenced. |
| `news` | Sentiment/news | Project folder | DELETE_EMPTY | manual | External inputs need provenance. |
| `tools` | Local tooling | Project folder | KEEP_DOMAIN_ROOT | manual | Avoid deleting configured local LLM tools. |

Safety defaults stay unchanged: `execution_allowed=false`,
`live_eligibility_status=LIVE_ORDER_BLOCKED`.



