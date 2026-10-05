---
document_id: AI4B-FACTORY-WFLOW-002
title: AI4BINANCE Factory Plan
document_type: WORKFLOW
version: 1.0.1
status: ACTIVE
owner: Enterprise Knowledge Governance
authority_level: NORMATIVE
authority_layer: L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS
authority_scope: plan
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
machine_enforceable: true
audit_required: true
classification: INTERNAL
canonical_path: factory/plan.md
---

# Factory Plan

## ELI10

This file lists planned factory tasks, acceptance criteria, and proof commands. It is planning knowledge, not execution authority.


## Task 1: Bootstrap Factory State

Goal: Add source-controlled factory artifacts that make project state,
constraints, and stop conditions explicit.

Acceptance:

- `factory/state.md` exists and names the active phase.
- Safety defaults include `NO_TRADE`, `RESEARCH_ONLY`, and
  `LIVE_ORDER_BLOCKED`.
- Stop conditions cover secrets, live trading, provider changes, and failed
  quality gates.

Proof:

```powershell
.\.venv\Scripts\python.exe .\.agents\skills\factory\scripts\validate_factory_state.py .
```

## Task 2: Add Factory Skills

Goal: Add routeable skills for the foreman, planning, tests, explanation,
handoff, and review.

Acceptance:

- Each skill has valid YAML frontmatter with `name` and `description`.
- Skill bodies describe inputs, outputs, safety rails, and stop conditions.
- `/factory` routes phases without authorizing live execution.

Proof:

```powershell
.\.venv\Scripts\python.exe "$env:USERPROFILE\.codex\skills\.system\skill-creator\scripts\quick_validate.py" .\.agents\skills\factory
.\.venv\Scripts\python.exe "$env:USERPROFILE\.codex\skills\.system\skill-creator\scripts\quick_validate.py" .\.agents\skills\factory-plan
.\.venv\Scripts\python.exe "$env:USERPROFILE\.codex\skills\.system\skill-creator\scripts\quick_validate.py" .\.agents\skills\factory-tests
.\.venv\Scripts\python.exe "$env:USERPROFILE\.codex\skills\.system\skill-creator\scripts\quick_validate.py" .\.agents\skills\factory-explain
.\.venv\Scripts\python.exe "$env:USERPROFILE\.codex\skills\.system\skill-creator\scripts\quick_validate.py" .\.agents\skills\factory-handoff
.\.venv\Scripts\python.exe "$env:USERPROFILE\.codex\skills\.system\skill-creator\scripts\quick_validate.py" .\.agents\skills\factory-review
```

## Task 3: Add Factory Contract Test

Goal: Add deterministic tests that protect the factory contract from drifting
into unsafe automation.

Acceptance:

- Tests check required artifacts, required skill names, safety terms, and the
  validator script.
- Tests do not require network, credentials, Binance connectivity, browser
  automation, or local LLM availability.

Proof:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_factory_contracts.py --no-cov
```

## Deferred: Background Shift

`BACKGROUND_SHIFT` is intentionally deferred. It must run only while the
computer is on and the user can inspect or interrupt progress. Before
implementation, define:

- max tasks per run;
- max repair attempts;
- allowed file globs;
- forbidden file globs;
- logging format;
- approval gates;
- review handoff rules.
- behavior when the session locks, the machine sleeps, or the user interrupts.

## Deferred: Auto Loom Proof

Browser recording and narrated proof are deferred until the factory contract,
review cycle, and local proof strategy are stable.

## 2026-08-04: System Hardening And Local Qwen Work Order

Goal: Apply the approved audit diff plan in bounded slices while keeping the
deterministic trading core independent from the local advisory LLM.

Ordered slices:

1. Replace whole-file JSONL destination read-back with bounded tail read-back.
2. Reduce runtime audit overproduction with compact verified event envelopes.
3. Unify service, task, and provider health evidence.
4. Add report-only accounting reconciliation diagnostics.
5. Reduce repeated audit/test scans and add performance controls.
6. Apply safe 5S and modularity guards without deleting protected evidence.
7. Add checkpointable validation visibility.
8. Prove all advisory LLM paths use loopback Ollama `qwen3:8b`.

Acceptance:

- Every slice has focused deterministic tests and rollback remains one scoped diff.
- `scripts/quality.ps1` passes after implementation.
- Ollama is loopback-only and the selected advisory model is `qwen3:8b`.
- Signals, risk, validation, and execution permission remain deterministic.
- `execution_allowed=false`, `RESEARCH_ONLY`, and `LIVE_ORDER_BLOCKED` remain intact.

## 2026-08-08: Full System Continuity, Auto-Learn And YKB Diff Plan

Source audit:

- `reports/operations/SYSTEM_FULL_KAIZEN_LEAN_SIX_SIGMA_5S_DIFF_PLAN_20260808.md`

Ordered bounded slices:

1. Add failing proof contracts for service truth, Auto-Audit continuity,
   Auto-Learn evidence ingestion, YKB freshness, and retention.
2. Create one service manifest shared by Python and PowerShell health checks.
3. Restore Accounting REST daemon continuity with bounded fail-closed retry.
4. Add a read-only Operations Supervisor for low-frequency System Report,
   Auto-Audit, Auto-Learn, YKB, and 5S cycles.
5. Load source-hashed persisted evidence into Controlled Auto-Learn and stop at
   `RESEARCH_ONLY` or `STAGED_CANDIDATE`.
6. Share one immutable snapshot across System Report, Auto-Audit, and YKB.
7. Add verified retention/partitioning and remove live runtime state from source
   control only after fixture/provenance review.
8. Strengthen vNext evidence depth, RAG evaluation, latency/soak evidence, and
   scanner persistence.
9. Close the validation/opportunity Kaizen loop without automatic promotion.
10. Complete a seven-awake-session-day control/soak gate.

Acceptance:

- Required services start at first user logon, continue on battery while the
  machine is awake, and expose task/PID/lock/action/useful-cycle proof.
- Accounting REST does not die on an expected degraded provider cycle.
- Auto-Audit is genuinely recurring and preserves blocker history.
- Auto-Learn consumes real bounded artifacts with hashes and produces no
  duplicate writes or authority changes.
- YKB is generated hourly or on material blocker change from a shared snapshot.
- Full-refresh YKB p95 is at most 20 seconds; cached p95 is at most 5 seconds.
- Hot runtime audit growth is at most 5 MB/day after verified legacy archive.
- Full quality gate passes and live state remains `LIVE_ORDER_BLOCKED`.

Stop conditions:

- pre-logon wallet-connected execution requires a separately approved service
  identity and credential design;
- no ACL takeover, unverified evidence deletion, risk change, parameter
  promotion, external publishing, or live order authority;
- stop a slice after its bounded repair budget and preserve the blocker.

Implementation result:

- Bounded JSONL read-back and bounded accounting tail reads are implemented.
- Research runtime audit events use compact hashes, refs, stage/blocker summaries.
- System report includes service/PID/lock state and local Ollama/Qwen health.
- Interactive system-report output is bounded; full evidence remains persisted.
- Validation checkpoints bind dataset, config, implementation, and artifact hashes.
- Safe 5S cleanup ran without ACL takeover; locked stale temp folders remain blockers.
- Advisory production routing uses loopback Ollama `qwen3:8b` only.
- Full gate passed: 1533 tests, 90.05% coverage, Ruff/MyPy/Bandit/dependencies clean.

## 2026-08-09: GitHub Architecture Adoption Diff Plan

### Objective

Learning useful patterns from mature projects on GitHub, but current
AI4BINANCE yeteneklerini ikinci kez kurmamak and trading core'a gereksiz runtime,
Do not add dependency on service or live order.

This plan is only for research and diff design. All external projects are untrusted input
is evaluated as. The code, package, service, or GitHub Action installation is also
Must not be done without approval.

### Based on deposit evidence

- `src/ai4binance/events/` under deterministic event bus, simulated clock,
  hash-linked disk journal, checkpoint and replay zaten bulunuyor.
- `src/ai4binance/validation/integrity.py` temporal lineage, look-ahead and
  recursive-stability kontrollerini fail-closed uyguluyor.
- `src/ai4binance/data/archive.py` and `data/revision.py` Parquet schema,
The checksum, source, revision, and market-only data limits are already being maintained.
- `src/ai4binance/schemas.py` provides immutable OHLCV/market snapshot contracts;
  it does not include pandas in the production dependency set.
- `scripts/quality.ps1` Ruff, MyPy, Pytest, Bandit, finansal and gizlilik
  it is running leak detection. `pip-audit` and Gitleaks are still missing.
- The current trust/assurance work in the codebase is touching decision provenance,
  evidence graph, and OpenTelemetry headers. These files
  will not be used to build a second model in the same area until they are stabilized.

### Project contribution, benefit, and drawback

| GitHub project | AI4BINANCE contribution | Benefit | Drawback / risk | Decision |
| --- | --- | --- | --- | --- |
| [Hypothesis](https://github.com/HypothesisWorks/hypothesis) | Risk and execution invariant testing | Finds edge-cases without touching production code; provides reduced failing example | CI time/variability increases if deterministic profile and bounded example count are not defined | **Now, dev-only** |
| [NautilusTrader](https://github.com/nautechsystems/nautilus_trader) | Event/replay conformance reference | A strong point of comparison is the treatment of research and execution semantics within the same deterministic model | Rust/Cython core and LGPL dependency burdens the existing pure-Python core | **Adopt pattern; take dependency** |
| [OpenLineage](https://github.com/OpenLineage/OpenLineage) | Dataset -> feature -> decision export agreement | Provides a shared lineage language with Run/job/dataset and extensible facet model | Introduces instrumentation and identity mapping costs; creates remote backend privacy risks | **Local exporter pilot** |
| [Pandera](https://github.com/unionai-oss/pandera) | DataFrame schema | DataFrame schemas and statistical checks mature | Current core DataFrame/pandas based; new heavy dependency and parallel schema source produce | **Add now** |
| [Graphiti](https://github.com/getzep/graphiti) | Temporal evidence graph reference | Concepts of temporal validity, episode provenance, and hybrid retrieval are valuable | LLM/embedder and graph backend required; default telemetry and data-ownership review is needed | **Addition without completing local lite model** |
| [vectorbt](https://github.com/polakowo/vectorbt) | Broad parameter scanning and research acceleration | Can compare a large number of configurations quickly | Vectorized fill/event order can be separated from the existing backtest engine; adds pandas/NumPy/Numba surface | **Isolated parity pilot** |
| [Prefect](https://github.com/PrefectHQ/prefect) | Auto-Audit workflow reference | Scheduling, retry, caching, and event automation are ready | Introduces overlap with existing auto-audit/supervisor and adds a separate server/runtime | **Postpone until scaling needs arise** |
| [LangGraph](https://github.com/langchain-ai/langgraph) | Advisory agent workflow reference | Stateful, durable, and human-in-the-loop agent workflows are provided | Overlaps with the existing `WorkflowGraph`; trading decision can leak into LLM orchestration | **Addition outside of Advisory sandbox** |
| [MLflow](https://github.com/mlflow/mlflow) | Experiment/parameter recording and UI reference | Strong visibility into parameters, metrics, artifacts, and registry | Creates a dual source of truth and service load with existing tuning/promotion records | **Postpone until registry need is proven** |
| [Evidently](https://github.com/evidentlyai/evidently) | data/model drift reporting | Mature offline report and test suite generation | Adds pandas overhead; does not replace OOS/WF or trading-edge proof | **Baseline established, proceed with pilot** |
| [OpenTelemetry Python](https://github.com/open-telemetry/opentelemetry-python) | Trace/metric export adapter | Provides a vendor-neutral telemetry contract | Can lead to high cardinality, data leakage, and performance costs | **Optional adapter after local sink** |
| [DVC](https://github.com/treeverse/dvc) | Large dataset/model revision workflow reference | Standardizes data and experiment revision workflows | Creates overlap and additional storage processes with existing checksum manifest/revision layers | **Postpone until data volume threshold** |
| [Gitleaks](https://github.com/gitleaks/gitleaks) and [pip-audit](https://github.com/pypa/pip-audit) | Secret/dependency security proof | Completes secrets and known CVE classes that Bandit does not cover | Requires trust in external binary/action and network/advisory DBs; requires management of false positives | **Report-only security slice** |
| [GraphRAG](https://github.com/microsoft/graphrag), [Neo4j GraphRAG](https://github.com/neo4j/neo4j-graphrag-python) | Batch news/research graph reference | Provides graph-based retrieval for unstructured evidence | Heavy for hot path; adds graph DB, embedding, cost, and privacy surface area | **R&D only** |
| [Freqtrade](https://github.com/freqtrade/freqtrade), [Hummingbot](https://github.com/hummingbot/hummingbot), [Temporal](https://github.com/temporalio/sdk-python), [Dagster](https://github.com/dagster-io/dagster), [Qlib](https://github.com/microsoft/qlib) | Architecture and test reference | Examples of connectors, orchestration, and quant-R&D are extensive | Introduces core overlap, new execution surface, or distributed runtime complexity | **Reject/defer as dependency** |

### Default approval scope

User applies only `apply` then **Slice 1** is applied. Slices 2 and onwards,
do not start unless the previous slice's proof is reviewed and separately approved.

### Slice 0: Dirty-worktree and overlap preflight

Goal: Preserve the user's existing trust/assurance changes and prevent new
work from adding conflicting types in the same models.

Affected files or likely modules:

- No code change.
- Especially `src/ai4binance/ops/continuous_assurance.py`,
  `src/ai4binance/trust/`, `tests/test_continuous_assurance.py` and
  `tests/test_trust_plane.py` is checked only for read access.

Acceptance criteria:

- Start by capturing the `git status --short` record.
- Files with overlap in dirty state do not enter the scope of Slice 1.
- Existing changes are not reset, formatted, or moved.

Proof command:

```powershell
git status --short
git diff --check
```

Stop conditions:

- If the user's change requires touching the same lines, the process stops.
- If Secret, wallet, account, or private runtime content becomes visible, the process stops.

Safety notes:

- This preflight does not clone any external repositories or install packages.
- It does not modify trading, risk, parameter promotion, or live gate behavior.

### Slice 1: Hypothesis Risk Invariant Test Engine

Goal: Strengthen the existing deterministic core using property-based tests;
do not change production behavior or the runtime dependency set.

Affected files or likely modules:

- `pyproject.toml`: bounded Hypothesis version range only in the `dev` extra.
- `tests/test_property_invariants.py`: new deterministic property tests.
- Production file is only separate and minimal if a real defect is found during testing
Is considered as a correction.

Acceptance criteria:

- The result of rounding down all generated positive price/quantity values is the input
It does not miss any beats and is aligned with tick/step.
- Long trailing stop never goes back to any input; it aligns with the tick when it moves.
- Approved risk assessment `max_risk_per_trade`, `max_trade_usdt` and exposure
It will not exceed the limits.
- Event replay produces the same snapshot/hash chain for the same input; reorder,
  duplicate or tamper fail-closed becomes.
- No evaluation with any **Blocker** has produced `execution_allowed=True`
It is proven.
- Hypothesis profili `database=None`, `derandomize=True`, bounded
  `max_examples` and `deadline=None` with CI'da tekrarlanabilirdir.

Proof commands:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_property_invariants.py --no-cov -q --basetemp .\artifacts\test_temp\hypothesis-plan
.\.venv\Scripts\python.exe -m ruff check tests\test_property_invariants.py pyproject.toml
.\scripts\quality.ps1
```

Stop conditions:

- If a defect is found during testing, a failure example is recorded; production fix is automated
  it is not expanded.
- Focused test duration is 30 seconds or the full gate duration exceeds the current baseline by
  15% or more, the example budget and strategies are reviewed.
- If dependency resolution matches Python 3.14.7 or current dev tools, stop.

Safety notes:

- `RESEARCH_ONLY`, `NO_TRADE`, `execution_allowed=false` and
  `LIVE_ORDER_BLOCKED` invariants are a test subject; it does not expand permissions.
- Wallet state historical backtest girdisine eklenmez.

### Slice 2: Native Market Data Contract Engine

Goal: complete dataset-level manifest contracts for the existing immutable candle
and Parquet flow without adding a Pandera dependency.

Affected files or likely modules:

- `src/ai4binance/data/contracts.py`: new batch contract report model.
- `src/ai4binance/data/__init__.py`: public export.
- `src/ai4binance/data/acquisition.py`: contract call before snapshot generation.
- `tests/test_market_data_contracts.py`: ordering, duplicate, cadence, stale,
  cross-timeframe and impossible-value testleri.

Acceptance criteria:

- A unique and incrementing aware timestamp is required for each timeframe.
- Expected cadence gap, duplicate, incomplete latest candle, and stale-data
  issue blockers are reported with code.
- Cross-timeframe control does not accept future or late information.
- Invalid contracts go to `DataQuality.DATA_INVALID` and `NO_TRADE`; silent
  cleaning or forward-fill is not performed.
- Contract report carries the source, schema version, row count, and dataset hash.

Proof commands:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_market_data_contracts.py tests\test_data_acquisition.py tests\test_data_archive.py --no-cov -q --basetemp .\artifacts\test_temp\data-contract-plan
.\.venv\Scripts\python.exe -m ruff check src\ai4binance\data tests\test_market_data_contracts.py
.\.venv\Scripts\python.exe -m mypy src\ai4binance\data tests\test_market_data_contracts.py
```

Stop conditions:

- Pandas/Pandera, implicit imputation or wallet/inventory coupling if needed stop.
- If backward compatibility issues arise in the existing archive format, migration plan /no_translations
It is submitted for separate approval.

Safety notes:

- The contract only rejects or degrades data; it does not produce signals or orders.

### Slice 3: Local OpenLineage-Compatible Decision Lineage

Goal: Current dataset revision, validation, and decision provenance evidence
Map the concepts of OpenLineage run/job/dataset without using the network.

Affected files or likely modules:

- After the current trust/assurance diff is completed, shared provenance type
Is determined; parallel second type is not created.
- Potential new module:
  `src/ai4binance/governance/openlineage_mapper.py`.
- `tests/test_openlineage_mapper.py`.
- If needed, only local JSONL target for `src/ai4binance/storage/jsonl.py`.

Acceptance criteria:

- Dataset snapshot/revision, feature/validation run and DGE decision identities
Connects deterministically to the same run graph.
- Export payload is canonical ordered, schema-versioned, and hash-bound.
- Default sink is local JSONL; no HTTP/backend/credential is present.
- Missing source hash, future timestamp, or unknown evidence ref returns
  `LINEAGE_INCOMPLETE`, `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` becomes.
- Export trading decision, promotion, or execution authority is not carried.

Proof commands:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_openlineage_mapper.py tests\test_dataset_revision.py tests\test_validation_integrity.py --no-cov -q --basetemp .\artifacts\test_temp\lineage-plan
.\.venv\Scripts\python.exe -m ruff check src\ai4binance\governance\openlineage_mapper.py tests\test_openlineage_mapper.py
.\.venv\Scripts\python.exe -m mypy src\ai4binance\governance\openlineage_mapper.py tests\test_openlineage_mapper.py
```

Stop conditions:

- If dirty trust/assurance files are still not stabilized, do not start.
- Remote collector, API key, cloud backend or sensitive wallet/account field
Stop if the requirement arises.

Safety notes:

- OpenLineage SDK dependency is not added in the first pilot; local schema mapping comes first
  and round-trip is proven.

### Slice 4: Nautilus-Inspired Replay Conformance

Goal: To achieve paper lifecycle and DGE decision parity in research-to-replay, rather than embedding NautilusTrader
  within the existing event journal/clock/recovery chain.
Prove the validation.

Affected files or likely modules:

- `tests/test_event_replay_conformance.py`.
- If necessary, minimum fix for `src/ai4binance/events/`
  `src/ai4binance/execution/recovery.py` or
  `src/ai4binance/governance/replay.py`.

Acceptance criteria:

- Same canonical event stream produces the same order/position and DGE
  decision state before and after restart.
- Partial write, broken hash, duplicate ID, backward time and missing checkpoint
  explicit blocker or exception with fail-closed becomes.
- Cannot enter parity outcome with wall-clock access outside of simulated clock.
- Paper/research parity proof does not guarantee live eligibility.

Proof commands:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_event_replay_conformance.py tests\test_event_journal.py tests\test_event_order_state.py tests\test_dge_recovery_replay_shadow.py --no-cov -q --basetemp .\artifacts\test_temp\replay-plan
.\scripts\quality.ps1
```

Stop conditions:

- NautilusTrader, Rust, Redis, or a new execution adapter dependency if needed
  Stay and request a separate ADR.
- If existing persisted journal schema migration is required, proceed only with backward compatibility and
  rollback plan approved.

Safety notes:

- This slice only demonstrates the current manual/paper/research behavior.

### Slice 5: Report-Only Security Completion

Goal: Complete current Ruff/Bandit/privacy/financial leak gates with Gitleaks and
pip-audit evidence; full quality gate to be dependent on network'
hale getirmemek.

Affected files or likely modules:

- `pyproject.toml`: separate security extra or reviewed dev dependency.
- `scripts/security_audit.ps1`: bounded, redacted, report-only runner.
- `tests/test_security_audit_contract.py`.
- `.github/workflows/nightly_quality_triage.yml`: only if pinned SHA and
  read-only permissions are approved.

Acceptance criteria:

- Secret scanner does not write raw secret value; only file/ref/rule/fingerprint
  gibi redacted metadata persist eder.
- Dependency audit exact environment/requirements identity and advisory source
  kaydeder.
- Green status is not applicable due to scanner unavailability; `SECURITY_EVIDENCE_UNAVAILABLE`
Generates the blocker.
- Network-dependent scan, deterministic local `scripts/quality.ps1` outside
It remains as a report-only gate.

Proof commands:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_security_audit_contract.py --no-cov -q --basetemp .\artifacts\test_temp\security-plan
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\security_audit.ps1 -ReportOnly
```

Stop conditions:

- Unpinned GitHub Action, repository content upload, secret echo or automatic
If a dependency fix is suggested, stop.
- Scanner kurulumu admin yetkisi or global PATH mutation isterse stop.

Safety notes:

- The scanner does not automatically update any dependencies and does not delete any files.

### Deferred pilots

- `vectorbt`: only on the same small fixture with the current backtest engine
fee/slippage/fill parity is measured; results without 100% parity
`RESEARCH_ONLY` mode.
- OpenTelemetry: first, the local low-cardinality telemetry contract stabilizes;
  wallet/account/order payload export edilmez.
- Evidently/MLflow: real drift baseline or experiment UI need is measured without
  servis and dependency eklenmez.
- Graphiti/GraphRAG/Neo4j: local evidence-graph-lite, privacy redaction,
Provenance must not start until the stale-source tests are completed.
- Prefect/LangGraph/Temporal/Dagster: the current local workflow/supervisor's
It is not added until the measured durability or scale requirement is not met.

### General acceptance and live compliance

- Her slice can be reverted on its own, proven with focused tests + Ruff + MyPy.
- The slice is not considered complete unless it passes the Tam `scripts/quality.ps1` gate.
- License, security policy, transitive dependencies, and Python for external dependencies
3.14.7 compatibility is also recorded.
- No slice provides signal authority, parameter promotion, wallet mutation,
  order submission or live-mode permission is not granted.
- The plan and all pilots' start status is `RESEARCH_ONLY`;
  live compatibility `LIVE_ORDER_BLOCKED`.

## 2026-08-20: Opportunity Lifecycle And Funnel Diff Plan

### Objective

Turn the governance opportunity assessment into a bounded implementation plan
that increases opportunity visibility without weakening execution gates.

This plan does not authorize implementation by itself. It converts the attached
architecture assessment into reviewable repository diffs that preserve
`PAPER_TRADING`, `MANUAL_CONFIRMATION`, `RESEARCH_ONLY`,
`execution_allowed=false`, and `LIVE_ORDER_BLOCKED`.

### Verified Current State

- `src/ai4binance/opportunity_scanner.py` already ranks Spot/Futures universe
  candidates and remains report-only.
- `src/ai4binance/opportunities.py` already contains VWAP observations,
  opportunity inbox contracts, blocker separation, and next-safe-action mapping.
- `src/ai4binance/domain.py` already owns core decision, setup tier, candidate,
  and validation status contracts.
- `src/ai4binance/strategies/engine.py` already generates research-only
  `TradeCandidate` objects from validated agent evidence.
- `src/ai4binance/strategies/registry.py` already registers 20 playbooks and
  prevents direct live eligibility.
- `tests/test_opportunity_scanner.py`, `tests/test_opportunities.py`,
  `tests/test_strategy_risk.py`, `tests/test_regime_playbooks.py`, and
  `tests/test_validation_summary.py` already cover parts of the opportunity
  surface.

### Scope

- Extend existing opportunity/scanner/inbox contracts instead of creating a
  second opportunity engine package.
- Add candidate funnel metrics and lifecycle visibility.
- Separate hard blockers from soft penalties in report contracts.
- Preserve strict handoff from opportunity discovery to risk, validation, and
  decision governance.
- Add focused tests before broader gate execution.



### Out Of Scope

- No live execution authority.
- No order submission, wallet mutation, leverage change, or risk-limit increase.
- No dependency installation.
- No new runtime agent unless a later implementation review proves that the
  existing service/module boundary is insufficient.
- No broad repository migration or file rename.

### Slice 0: Implementation Preflight

Goal: Confirm current ownership, dirty-worktree state, and import graph before
any code change.

Affected files or likely modules:

- No file change.
- Inspect `src/ai4binance/opportunity_scanner.py`,
  `src/ai4binance/opportunities.py`, `src/ai4binance/domain.py`,
  `src/ai4binance/strategies/engine.py`,
  `src/ai4binance/strategies/registry.py`,
  `src/ai4binance/cli/status.py`, and relevant tests.

Acceptance criteria:

- `git status --short --branch` is captured.
- No unrelated dirty work is overwritten or reformatted.
- Existing opportunity surfaces are used as the canonical extension point.
- Any conflicting user changes stop implementation.

Proof commands:

```powershell
git status --short --branch
rg -n "Opportunity|OpportunityScan|OpportunityInbox|CandidateStatus|WATCH_ONLY|LIVE_ORDER_BLOCKED" src tests
```

Stop conditions:

- Secrets, account credentials, private runtime data, or wallet mutation paths
  become part of the change.
- Existing user edits touch the same lines required by the planned diff.

Safety notes:

- This slice is read-only.

### Slice 1: Opportunity Lifecycle Contract

Goal: Add explicit lifecycle states for visible opportunities without changing
`TradeCandidate` execution semantics.

Affected files or likely modules:

- `src/ai4binance/opportunities.py`
- `tests/test_opportunities.py`
- Optional only if reuse is clearly better:
  `src/ai4binance/domain.py`

Acceptance criteria:

- Lifecycle states include `DISCOVERED`, `WATCH_ONLY`, `SETUP_FORMING`,
  `CONFIRMATION_PENDING`, `PAPER_ELIGIBLE`, `INVALIDATED`, and `EXPIRED`.
- Default and degraded outputs never become executable.
- Missing validation, stale evidence, invalid data, liquidity failure, spread
  failure, or unknown regime cannot be represented as `PAPER_ELIGIBLE`.
- Existing inbox outputs remain backward-compatible for current CLI/report
  consumers.

Proof commands:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_opportunities.py tests\test_validation_summary.py --no-cov -q --basetemp .\.pytest-tmp\opportunity-lifecycle
.\.venv\Scripts\python.exe -m ruff check src\ai4binance\opportunities.py tests\test_opportunities.py tests\test_validation_summary.py
```

Stop conditions:

- Lifecycle states start duplicating `Decision` or `CandidateStatus` with
  incompatible semantics.
- A lifecycle state grants execution permission or bypasses validation.

Safety notes:

- Lifecycle is visibility and workflow state only.

### Slice 2: Canonical Control Evaluation Primitive

Goal: Make hard blockers and soft penalties a shared Decision Governance /
Risk / Validation control concern before scanner-specific payload formatting.
Scanner output should explain why candidates are rejected, watchlisted, or
ranked lower without letting high score offset a hard blocker.

Affected files or likely modules:

- `src/ai4binance/governance/controls.py`
- `src/ai4binance/governance/dge_models.py`
- `src/ai4binance/governance/dge_engine.py`
- `config/governance/dge.yaml`
- `src/ai4binance/opportunity_scanner.py`
- `tests/test_governance_controls.py`
- `tests/test_dge_engine.py`
- `tests/test_dge_models.py`
- `tests/test_opportunity_scanner.py`

Acceptance criteria:

- `HardBlocker` is a binary veto condition and is never represented as a large
  negative numeric penalty.
- `SoftPenalty` is a bounded deterministic score/ranking adjustment with global
  and group caps.
- `ControlEvaluation` combines `hard_blockers`, `soft_penalties`,
  `hard_gate_passed`, `base_score`, `total_penalty`, `adjusted_score`,
  `eligibility`, and `reason_codes`.
- DGE, Risk, Validation, scanner, and handoff surfaces consume or carry the
  same control classification instead of reclassifying it locally.
- Candidate payloads distinguish `hard_blockers` from `soft_penalties`.
- Hard blockers always force `accepted=false`, `execution_allowed=false`, and
  `live_eligibility_status=LIVE_ORDER_BLOCKED`.
- Soft penalties can lower rank score but cannot override, create, clear,
  downgrade, resolve, or reweight a hard blocker.
- Unknown trading-sensitive control classification fails closed.
- A hard blocker can only be resolved by its declared resolution authority with
  evidence.
- Existing accepted/rejected symbol payload fields remain available.

Proof commands:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_governance_controls.py tests\test_dge_engine.py tests\test_dge_models.py tests\test_opportunity_scanner.py --no-cov -q --basetemp .\.pytest-tmp\control-evaluation
.\.venv\Scripts\python.exe -m ruff check src\ai4binance\governance\controls.py src\ai4binance\governance\dge_models.py src\ai4binance\governance\dge_engine.py src\ai4binance\opportunity_scanner.py tests\test_governance_controls.py tests\test_dge_engine.py tests\test_dge_models.py tests\test_opportunity_scanner.py
```

Stop conditions:

- Any score path changes an unsafe candidate into an accepted or executable
  candidate.
- A handoff, scanner, agent, LLM, or orchestrator downgrades a hard blocker to a
  soft penalty.
- Scanner starts depending on live Binance calls in unit tests.

Safety notes:

- This slice improves attribution only; it does not expand trading authority.
- Handoff may carry `blocker_refs` and `penalty_refs`, but it must not classify,
  resolve, downgrade, or reweight controls.

### Slice 3: Candidate Funnel Metrics

Goal: Add deterministic funnel counts so "no opportunity" reports explain
where the cycle narrowed.

Affected files or likely modules:

- `src/ai4binance/opportunity_scanner.py`
- `src/ai4binance/cli/status.py`
- `src/ai4binance/cli/output.py`
- `tests/test_opportunity_scanner.py`
- `tests/test_cli.py`

Acceptance criteria:

- Reports expose counts for `symbols_scanned`, `raw_candidates`,
  `data_quality_rejected`, `liquidity_rejected`, `spread_rejected`,
  `token_risk_rejected`, `watch_only`, `confirmation_pending`,
  `paper_eligible`, and `paper_executed`.
- `paper_executed` is always zero for scanner-only outputs.
- Empty input remains `RUNNING_WITH_BLOCKERS` with
  `SCANNER_INPUT_UNAVAILABLE`.
- Text and JSON CLI output stay bounded and deterministic.

Proof commands:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_opportunity_scanner.py tests\test_cli.py --no-cov -q --basetemp .\.pytest-tmp\opportunity-funnel
.\.venv\Scripts\python.exe -m ruff check src\ai4binance\opportunity_scanner.py src\ai4binance\cli\status.py src\ai4binance\cli\output.py tests\test_opportunity_scanner.py tests\test_cli.py
```

Stop conditions:

- Funnel metrics require uncontrolled runtime state, credentials, or external
  network access.
- Metrics become a second source of truth for risk or validation decisions.

Safety notes:

- Funnel metrics are diagnostic and cannot authorize execution.

### Slice 4: Strategy Family Visibility Mapping

Goal: Map existing strategy playbooks into opportunity lifecycle visibility
without adding unvalidated production strategies.

Affected files or likely modules:

- `src/ai4binance/strategies/registry.py`
- `src/ai4binance/strategies/engine.py`
- `src/ai4binance/opportunities.py`
- `tests/test_strategy_risk.py`
- `tests/test_regime_playbooks.py`
- `tests/test_opportunities.py`

Acceptance criteria:

- Implemented playbooks can surface as `WATCH_ONLY` or
  `CONFIRMATION_PENDING` when evidence is incomplete.
- Unimplemented or weak-evidence playbooks remain `RESEARCH_ONLY`.
- Missing OOS, missing walk-forward, unknown regime, or risk rejection remains
  a hard blocker for `PAPER_ELIGIBLE`.
- No playbook becomes `LIVE_ELIGIBLE` through this slice.

Proof commands:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_strategy_risk.py tests\test_regime_playbooks.py tests\test_opportunities.py --no-cov -q --basetemp .\.pytest-tmp\opportunity-strategy
.\.venv\Scripts\python.exe -m ruff check src\ai4binance\strategies src\ai4binance\opportunities.py tests\test_strategy_risk.py tests\test_regime_playbooks.py tests\test_opportunities.py
```

Stop conditions:

- Strategy registry semantics conflict with validation or promotion governance.
- A strategy family bypasses OOS, walk-forward, risk, or DGE gates.

Safety notes:

- This slice increases candidate visibility, not execution permission.

### Slice 5: Governed Report And Documentation Alignment

Goal: Align user-facing scan reports and governed documentation with the new
opportunity lifecycle and funnel metrics only after code behavior is proven.

Affected files or likely modules:

- `docs/governance/framework_decision_governance_engine.md`
- `docs/governance/policy_organization_market_strategy_validation.md`
- `docs/registries/registry_strategy_registry.md`
- `tests/test_docs_hygiene.py`
- `tests/test_repository_validator.py`

Acceptance criteria:

- Documentation states that scores cannot compensate for hard blockers.
- Opportunity lifecycle is documented as advisory/reporting state, not final
  trade authority.
- Strategy expansion remains governed by research, backtest, walk-forward,
  OOS, robustness, paper, and human promotion gates.
- Governed metadata and ELI10 requirements remain valid.

Proof commands:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_docs_hygiene.py tests\test_repository_validator.py --no-cov -q --basetemp .\.pytest-tmp\opportunity-docs
.\.venv\Scripts\python.exe -m ruff check tests\test_docs_hygiene.py tests\test_repository_validator.py
```

Stop conditions:

- Documentation creates a second source of truth for execution permission,
  risk limits, or promotion authority.
- The docs change attempts to redefine higher-authority governance.

Safety notes:

- Documentation follows implementation and tests; it does not authorize
  behavior by itself.

### Full-Gate Acceptance

After all approved slices are applied:

```powershell
.\scripts\quality.ps1
```

The change is not complete unless focused tests pass and the full quality gate
is either green or explicitly reported as `PARTIALLY_VERIFIED` with blockers.

### Default Implementation Order

1. Slice 0.
2. Slice 1.
3. Slice 2.
4. Slice 3.
5. Slice 4.
6. Slice 5.

If the user says only "apply the diff plan", start with Slice 0 and Slice 1
only. Later slices require review of the focused evidence from the previous
slice.

### Final Safety State

- `NO_TRADE` remains valid.
- `WATCH_ONLY` and `CONFIRMATION_PENDING` are opportunity visibility states.
- `PAPER_ELIGIBLE` requires validation evidence and still does not imply live
  eligibility.
- `execution_allowed=false` remains the default.
- `LIVE_ORDER_BLOCKED` remains mandatory until separately governed live gates
  are proven and approved.

## 2026-08-25: Virtual Market Hardening And First-Class Orchestration Diff Plan

### Objective

Turn `VIRTUAL_MARKET` into a first-class, bounded, testable simulation surface
while preserving the canonical separation:

- `BINANCE_MARKET` -> `HUMAN_HAND_MANUAL_ONLY`
- `VIRTUAL_MARKET` -> `BOUNDED_AUTONOMOUS_SIMULATION`
- `LIVE_ORDER` -> separately promoted and human approved only

This plan is implementation planning only. It does not grant live execution,
promotion authority, wallet mutation authority, or dependency installation
authority.

### Verified Current State

- `src/ai4binance/governance/execution_authority.py` already defines the
  canonical execution surfaces and authority profiles.
- `src/ai4binance/execution/paper.py` already enforces virtual-only paper
  submission through authority and eligibility checks.
- `src/ai4binance/application/virtual_runtime.py` already contains bounded
  virtual eligibility, independent Spot/Futures virtual portfolios, portfolio
  performance logic, evidence adaptation, and improvement publishing helpers.
- `config/research/virtual_market_acceptance.yaml` already defines a fail-closed
  anti-masking acceptance policy for Spot and USD-M Futures.
- `src/ai4binance/execution/manual_approval.py` and
  `src/ai4binance/execution/live_spot.py` already keep manual and live order
  authority on separate guarded surfaces.
- `src/ai4binance/cli/runtime.py` already exposes a read-only runtime surface
  and virtual portfolio reporting, but `VIRTUAL_MARKET` is not yet treated as a
  first-class orchestration entrypoint.

### Scope

- Strengthen the virtual execution boundary as a canonical application surface.
- Reduce authority drift risk across virtual, manual, and live execution paths.
- Make virtual runtime decomposition small enough for bounded repair and review.
- Improve fail-closed root-cause visibility for blocked virtual decisions.
- Add focused proofs before any broader quality gate.



### NEXT_SLICE

1. First-class virtual runtime command surface.
   - Add or finalize a dedicated `virtual-market-once` entrypoint boundary over
     the existing read-only runtime surface.
   - Keep the command fail-closed and preserve
     `execution_allowed=false`, `RESEARCH_ONLY`, and `LIVE_ORDER_BLOCKED`.
   - Verify the command contract through `tests/test_cli.py` and
     `tests/test_virtual_runtime.py`.
2. Virtual runtime performance split.
   - Extract portfolio-performance calculations from
     `src/ai4binance/research/virtual_runtime.py` into a bounded helper module
     such as `src/ai4binance/application/virtual_runtime_performance.py`.
   - Keep public behavior, blocker semantics, and markdown/report output
     stable.
3. Platform blocker closure map.
   - Track the remaining `PARTIAL` and `MISSING` entries that still prevent a
     truly end-to-end AI4Binance posture.
   - Prioritize `live_spot` adapter completion, connector readiness, event and
     order replay wiring, open-order reconciliation, and websocket/session
     lifecycle coverage.
4. Verification and evidence refresh.
   - Run the smallest targeted tests first after each slice, then expand to
     the broader quality gate only when the slice is green.
   - Preserve fail-closed reporting for any unresolved blocker; do not label
     incomplete evidence as readiness.
   - Completed: targeted repository validator tests passed and the governance
     inventory, evidence report snapshots, ISO crosswalk references, AIMS
     baseline control record, management review minutes, internal audit
     schedule, evidence registry/CAPA closure records, per-system
     risk-impact records, provider control review, AI system inventory, and
     compliance matrix references were refreshed for the new blocker closure
     map, repository governance findings reference the evidence registry and
     blocker closure map, the documentation map includes the blocker closure
     map plus the repository governance findings summary in the AIMS evidence
     package, the compliance matrix AIMS baseline references the repository
     governance findings report, the AI orchestration compliance row points to
     the blocker closure map and repository governance findings report, the AI
     system inventory points to the repository governance findings report, the
     SoA monitoring and measurement row includes the blocker closure map and
     repository governance findings report, the AIMS baseline control record
     monitoring row and KPI closure set include the blocker closure map and
     repository governance findings report, the operational readiness evidence
     consumers include the blocker closure map and repository governance
     findings report, the agent review scope and recorder contract include the
     blocker closure map and repository governance findings report, the risk-impact
     record binds blocker closure and repository governance findings to its
     missing-evidence control, the per-system AIMS risk-impact record for
     `AIMS-AI-003` now includes the repository governance findings report, the
     documentation map now includes the repository governance findings report
     inside the AIMS evidence package, the provider control review now includes
     the repository governance findings report, the SoA plus Clause 9 crosswalk
     include the repository governance findings report, orchestration readiness
     points to the evidence registry, the agent review record points to the
     evidence registry as the evidence reference register, and the AI
     orchestration readiness quality summary matches the refreshed repository
     artifact count and health score.

### Out Of Scope

- No live order submission.
- No direct Binance order authority.
- No wallet transfer, leverage increase, or risk-limit expansion.
- No package installation or removal.
- No broad repository refactor outside the touched slices.
- No governed Markdown edit outside currently authorized planning artifacts.

### Slice 0: Verification And Worktree Hygiene Preflight

Goal: Restore reliable local verification before changing virtual-market code.

Affected files or likely modules:

- No code change by default.
- Inspect local test runner path, temporary runtime folders, and nested Git or
  pytest-generated worktree artifacts.

Acceptance criteria:

- A reproducible local Python test invocation path is identified.
- `git status` no longer fails because of nested temporary or generated paths
  that belong outside the governed worktree surface.
- The blocker is recorded if the local environment still cannot execute tests.

Proof commands:

```powershell
# TODO: replace with the approved local test runner once confirmed
python --version
py --version
uv --version
git status --short --branch
```

Stop conditions:

- Verification requires installing tools or dependencies without explicit user
  approval.
- Temporary path cleanup would delete user work or governed evidence.

Safety notes:

- This slice does not change trading, validation, promotion, or execution
  behavior.

### Slice 1: Canonical Execution Envelope

Goal: Expose one typed application-level execution envelope derived only from
canonical authority definitions.

Affected files or likely modules:

- `src/ai4binance/governance/execution_authority.py`
- New small module if needed:
  `src/ai4binance/governance/execution_envelope.py`
- `src/ai4binance/execution/paper.py`
- `src/ai4binance/execution/manual_approval.py`
- `src/ai4binance/execution/live_spot.py`
- `tests/test_execution_authority.py`
- New focused tests:
  `tests/test_execution_envelope.py`

Acceptance criteria:

- One canonical envelope describes:
  `execution_surface`, `automation_mode`, `manual_confirmation_required`,
  `virtual_simulation_allowed`, `external_order_allowed`, and
  `live_order_allowed`.
- `paper`, `manual_approval`, and `live_spot` consume the same canonical
  envelope semantics instead of restating authority locally.
- No envelope shape can produce `execution_allowed=true` or remove
  `LIVE_ORDER_BLOCKED` on the virtual or planning surfaces.
- Unknown or contradictory authority inputs fail closed.

Proof commands:

```powershell
# TODO: replace with the approved local test runner once confirmed
python -m pytest tests/test_execution_authority.py tests/test_execution_envelope.py --no-cov -q --basetemp .\.pytest-tmp\virtual-envelope
python -m ruff check src/ai4binance/governance src/ai4binance/execution tests/test_execution_authority.py tests/test_execution_envelope.py
python -m mypy src/ai4binance/governance src/ai4binance/execution tests/test_execution_envelope.py
```

Stop conditions:

- The new envelope duplicates the canonical authority source instead of deriving
  from it.
- Any virtual or manual surface gains live or exchange order authority.

Safety notes:

- The execution envelope is descriptive and fail-closed; it is not a promotion
  or execution grant.

### Slice 2: Virtual Runtime Decomposition

Goal: Split the current `VirtualMarketRuntime` into bounded modules without
changing its external fail-closed behavior.

Affected files or likely modules:

- `src/ai4binance/application/virtual_runtime.py`
- Potential new modules:
  `src/ai4binance/application/virtual_runtime_eligibility.py`
  `src/ai4binance/application/virtual_runtime_portfolio.py`
  `src/ai4binance/application/virtual_runtime_performance.py`
  `src/ai4binance/application/virtual_runtime_evidence.py`
- `tests/test_virtual_runtime.py`

Acceptance criteria:

- Eligibility/gating, portfolio transitions, performance calculations, and
  evidence adaptation are separated into bounded modules with preserved public
  contracts.
- `VirtualMarketRuntime.evaluate()` still fails closed on eligibility,
  portfolio, DQ, and feasibility blockers.
- Public contract names, reason codes, and blocker semantics remain stable or
  receive backward-compatible adapters.
- No decomposition step introduces account coupling or live authority leakage.

Proof commands:

```powershell
# TODO: replace with the approved local test runner once confirmed
python -m pytest tests/test_virtual_runtime.py -k "eligibility or portfolio_performance or evidence_surface" --no-cov -q --basetemp .\.pytest-tmp\virtual-runtime-core
python -m ruff check src/ai4binance/application tests/test_virtual_runtime.py
python -m mypy src/ai4binance/application tests/test_virtual_runtime.py
```

Stop conditions:

- Decomposition requires changing unrelated enterprise, trust, or live trading
  modules.
- The slice widens scope into non-virtual execution behavior.

Safety notes:

- Preserve `execution_allowed=false`, `RESEARCH_ONLY`, and
  `LIVE_ORDER_BLOCKED`.

### Slice 3: First-Class Virtual Runtime Command Surface

Goal: Promote `VIRTUAL_MARKET` to a first-class runtime entrypoint with clear
read-only and simulation boundaries.

Affected files or likely modules:

- `src/ai4binance/cli/runtime.py`
- `src/ai4binance/cli/commands.py`
- `src/ai4binance/cli/parser.py`
- `tests/test_cli.py`
- `tests/test_virtual_runtime.py`

Acceptance criteria:

- A dedicated virtual runtime command exists for bounded simulation-only runs.
- The command uses canonical authority and cannot route into Binance or live
  order paths.
- User-facing output clearly states the execution surface, automation mode, and
  `LIVE_ORDER_BLOCKED`.
- Existing read-only runtime commands remain backward-compatible.

Proof commands:

```powershell
# TODO: replace with the approved local test runner once confirmed
python -m pytest tests/test_cli.py tests/test_virtual_runtime.py --no-cov -q --basetemp .\.pytest-tmp\virtual-cli
python -m ruff check src/ai4binance/cli tests/test_cli.py tests/test_virtual_runtime.py
```

Stop conditions:

- The CLI surface could dispatch live or exchange-order code paths.
- The new command requires credentials, network writes, or wallet mutation to
  produce deterministic tests.

Safety notes:

- This slice is about orchestration visibility, not live execution.

### Slice 4: Canonical Blocker And Root-Cause Reduction

Goal: Turn virtual decision blockers into one canonical root-cause reduction
surface across analysis, candidate, risk, validation, DGE, portfolio, and
feasibility domains.

Affected files or likely modules:

- `src/ai4binance/application/virtual_runtime.py`
- Potential new module:
  `src/ai4binance/governance/blocker_reduction.py`
- `src/ai4binance/governance/blockers.py`
- `tests/test_virtual_runtime.py`
- New focused tests:
  `tests/test_virtual_blocker_reduction.py`

Acceptance criteria:

- Blockers from all virtual decision stages are reduced deterministically into a
  stable ordered root-cause set.
- `NO_ACTION` outcomes carry explicit root-cause evidence instead of only a
  large mixed blocker tuple.
- Unknown blocker classifications fail closed and remain visible.
- Root-cause reduction cannot downgrade a hard blocker into a soft diagnostic.

Proof commands:

```powershell
# TODO: replace with the approved local test runner once confirmed
python -m pytest tests/test_virtual_runtime.py tests/test_virtual_blocker_reduction.py --no-cov -q --basetemp .\.pytest-tmp\virtual-root-cause
python -m ruff check src/ai4binance/governance src/ai4binance/application tests/test_virtual_blocker_reduction.py
python -m mypy src/ai4binance/governance tests/test_virtual_blocker_reduction.py
```

Stop conditions:

- Root-cause reduction changes the meaning of existing blocker taxonomy.
- The slice introduces a second blocker registry or uncontrolled remapping.

Safety notes:

- Diagnostic clarity must not change veto authority.

### Slice 5: Spot/Futures Anti-Masking Report Surface

Goal: Make anti-masking outcomes explicit to operators and reports without
changing acceptance policy semantics.

Affected files or likely modules:

- `src/ai4binance/research/virtual_market.py`
- `src/ai4binance/application/virtual_runtime.py`
- `src/ai4binance/ops/user_reports.py`
- `tests/test_virtual_market_acceptance.py`
- `tests/test_virtual_runtime.py`

Acceptance criteria:

- Reports show Spot and USD-M Futures acceptance results separately.
- Combined PnL, combined Sharpe, or combined equity cannot appear as a passing
  system gate.
- If either market fails, the system acceptance remains failed and the user
  report explains which market blocked it.
- All user reports preserve `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED`.

Proof commands:

```powershell
# TODO: replace with the approved local test runner once confirmed
python -m pytest tests/test_virtual_market_acceptance.py tests/test_virtual_runtime.py --no-cov -q --basetemp .\.pytest-tmp\virtual-anti-masking
python -m ruff check src/ai4binance/research src/ai4binance/application src/ai4binance/ops tests/test_virtual_market_acceptance.py tests/test_virtual_runtime.py
```

Stop conditions:

- Reporting becomes a second source of truth for acceptance policy.
- The slice weakens anti-masking or system acceptance rules.

Safety notes:

- This slice improves operator visibility only.

### Slice 6: Improvement Loop Hardening For Virtual Research

Goal: Keep virtual improvement publishing bounded, reviewable, and explicitly
non-promotional.

Affected files or likely modules:

- `src/ai4binance/application/virtual_runtime.py`
- `src/ai4binance/research_governance.py`
- `tests/test_virtual_runtime.py`
- `tests/test_research_governance.py`

Acceptance criteria:

- Improvement artifacts remain advisory and cannot self-promote strategies,
  parameters, or execution authority.
- Improvement publishing requires telemetry, evidence refs, and explicit
  readiness checks.
- Missing telemetry or evidence fails closed to `RESEARCH_ONLY`.
- Publishing helpers remain local-only and do not introduce remote sinks.

Proof commands:

```powershell
# TODO: replace with the approved local test runner once confirmed
python -m pytest tests/test_virtual_runtime.py tests/test_research_governance.py --no-cov -q --basetemp .\.pytest-tmp\virtual-improvement
python -m ruff check src/ai4binance/application src/ai4binance/research_governance.py tests/test_research_governance.py tests/test_virtual_runtime.py
python -m mypy src/ai4binance/research_governance.py tests/test_research_governance.py
```

Stop conditions:

- Any improvement helper starts carrying live eligibility, promotion approval,
  or wallet mutation semantics.
- The slice requires a new external service or dependency.

Safety notes:

- Improvement remains research-stage only.

### Full-Gate Acceptance

After approved slices are implemented and focused proofs are green:

```powershell
# TODO: replace with the approved local quality gate invocation once confirmed
.\scripts\quality.ps1
```

If the full gate cannot be executed in the local environment, the final result
must be reported as `PARTIALLY_VERIFIED` with the exact blocker.

### KPI And Evidence Targets

- `virtual_runtime_eval_latency_p95`
- `virtual_system_acceptance_pass_rate`
- `virtual_traceability_coverage`
- `root_cause_resolution_rate`
- `cross_market_masking_incidents`
- `authority_leak_attempt_count`
- `blocked_due_to_data_quality_rate`
- `virtual_research_candidate_conversion_rate`

### Default Implementation Order

1. Slice 0.
2. Slice 1.
3. Slice 2.
4. Slice 3.
5. Slice 4.
6. Slice 5.
7. Slice 6.

If the user says only "apply the diff plan", start with Slice 0 and Slice 1
only. Later slices require review of the focused evidence from the previous
slice.

### Final Safety State

- `BINANCE_MARKET` remains `HUMAN_HAND_MANUAL_ONLY`.
- `VIRTUAL_MARKET` remains `BOUNDED_AUTONOMOUS_SIMULATION`.
- `execution_allowed=false` remains the default planning and virtual state.
- `RESEARCH_ONLY` remains the default promotion state.
- `LIVE_ORDER_BLOCKED` remains mandatory until separately governed live gates
  are proven and human approved.

