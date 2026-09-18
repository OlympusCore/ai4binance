---
document_id: AI4B-GOV-REG-AGT-001
title: AI4BINANCE Agent Registry
document_type: REGISTRY
version: 1.10.0
status: ACTIVE
owner: Enterprise Governance
authority_level: NORMATIVE
authority_layer: L5_REGISTRIES_ROADMAP
authority_scope: ai_orchestration_role_packages
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: ai_orchestration_role_packages
machine_enforceable: true
audit_required: true
classification: INTERNAL
canonical_path: docs/registries/registry_agent_registry.md
schema_refs:
  - schemas/governance/repository_artifact.schema.json
validated_by:
  - src/ai4binance/governance/repository_validator.py
  - tests/test_repository_validator.py
---

# AI4BINANCE Agent Registry

## ELI10

This registry is the controlled list of AI orchestration role packages and their
authority boundaries. It is not a catalog of analytical capabilities, platform
components, or runtime process instances.

## Registry Contract

Role packages remain advisory unless a deterministic contract, test evidence,
and human-governed promotion record explicitly grant a narrower capability.

## Scope and Canonical Relationships

| Concept | Canonical meaning | Source of truth | Authority boundary |
| --- | --- | --- | --- |
| AI orchestration role package | A bounded AI workflow role such as classifier, planner, worker, control reviewer, or evidence recorder. | This registry | Advisory, review, or record-only; never a trading or execution authority. |
| Platform definition | A legacy-compatible `AgentDefinition` declaration for a deterministic platform component or analysis capability. | `src/ai4binance/agents/catalog.py` | Defines dependencies and evidence metadata; does not create an autonomous agent role. |
| Analytical capability | A logical analytical method evaluated against the shared immutable market snapshot. | `ANALYSIS_DEFINITIONS` in `src/ai4binance/agents/catalog.py` | Produces bounded evidence only; final decision, risk, validation, and execution authority remain separate. |
| Capability runtime contract | An immutable `CapabilityDefinition` projection of one analytical capability, including admission and execution-lane metadata. | `build_default_capability_registry()` in `src/ai4binance/agents/catalog.py` | `runtime_eligible`, `execution_class`, and `activation_policy` describe current bounded scheduling only; they never grant trading, promotion, or live-order authority. |
| Runtime actor | A concrete in-process service or worker instance that runs an implementation. | Runtime composition and `EnterpriseOrchestrator` | Cannot widen the authority of its registered definition or role package. |

The platform catalog currently contains 49 definitions. Its 35 analysis-stage
definitions consist of 34 logical analytical capabilities plus one
`memory_advisory` definition. These counts are implementation facts validated
by `tests/test_agent_registry.py`; they are not additional entries in this
five-record role-package registry.

The capability runtime contract is a declarative projection, not a scheduler
command. `CapabilityBundleRegistry` assigns every one of the 34 logical
analytical capabilities to exactly one of six canonical runtime-planning bundles:
`market_state`, `structure_location`, `momentum_participation`, `liquidity_flow`,
`cross_market_derivatives`, and `setup_event`. It rejects missing, unknown, or
overlapping capability membership.

`CapabilityPreflightPlan` evaluates runtime eligibility, required data, timeframe,
regime, dependency, and bounded analysis-cost mode before worker creation. Every
ready dependency layer is submitted through at most one `CapabilityBundleExecutor`
task per bundle. Admitted members receive the same immutable prior-results view,
and their results are merged in canonical capability order. A rejected capability
is recorded as `NOT_APPLICABLE` with deterministic reason codes and is not
submitted to the dependency-aware bundle scheduler. Current entries, bundles, and
bundle executors remain `RESEARCH_ONLY`, `execution_allowed=false`, and
`LIVE_ORDER_BLOCKED`; bundle planning, preflight admission, and execution grouping
never grant trading, promotion, or live-order authority.

`EvidenceFusionEngine` is the canonical deterministic service for independent
evidence-cluster selection and weighted `confluence` calculation. It preserves the
existing `confluence` result identity for consumers, has no decision, risk,
promotion, or execution authority, and fails closed on unavailable eligibility
dependencies. `ConfluenceAgent` is a compatibility facade only; it delegates to
the engine and must not implement independent fusion rules.

`DataQualityGate` is the canonical deterministic snapshot-control service. It
validates continuity, freshness, minimum history, and zero-volume degradation
before analytical scheduling while preserving the existing `data_quality`
result identity. A `BLOCKED` result causes the orchestrator's existing
`EARLY_EXIT_NO_TRADE` path. The gate has no decision, risk, promotion, or
execution authority. `DataQualityAgent` is a compatibility facade only and
must not implement independent quality rules.

`RiskGate` is the canonical deterministic candidate-risk control. It verifies
that required dependencies are usable before evaluating bounded candidates with
the existing `RiskEngine`, exchange filters, and virtual-market execution
surface. It preserves the existing `risk` result identity and deterministic
blocker codes. The gate cannot authorize a decision, promotion, live order, or
risk-limit change. `RiskAgent` is a compatibility facade only and must not
implement independent risk rules.

`ValidationGate` is the canonical deterministic final-decision control. It
aggregates agent evidence and externally supplied blockers, calculates research
scores, and always preserves mandatory backtest, walk-forward, OOS, and risk
approval blockers. It returns `VALIDATION_REJECTED`, `NO_TRADE_CAPITAL_PROTECTION`,
and `execution_allowed=false`; it cannot promote a strategy or authorize an
order. `ValidationAgent` is a compatibility facade only and must not implement
independent validation rules.

`UniverseLiquidityGate` is the canonical deterministic Spot eligibility control.
It verifies the usable `data_quality` dependency, trading status, exchange
filters, positive pricing, bid/ask availability, and bounded spread before
analytical scheduling. It preserves the existing `universe_liquidity` result
identity and blocker codes. A blocked result follows the orchestrator's existing
`EARLY_EXIT_NO_TRADE` path; the gate cannot authorize a decision, promotion, or
order. `UniverseLiquidityAgent` is a compatibility facade only and must not
implement independent eligibility rules.

| agent_id | name | owner | lifecycle_status | authority_boundary | canonical_contract | validated_by |
| --- | --- | --- | --- | --- | --- | --- |
| PENDING | Pending canonical agent entry | Enterprise Governance | DRAFT | ADVISORY_ONLY | PENDING | PENDING |
| AIO-AGT-001 | AI orchestration classifier role package | Enterprise Governance | ACTIVE | ADVISORY_ONLY; cannot approve actions or widen authority | `docs/governance/framework_orchestration_ai_multi_agent.md`; `docs/reports/governance/evidence_ai_orchestration_agent_review_records.md` | `tests/test_agentic_patterns.py`; `scripts/quality.ps1` |
| AIO-AGT-002 | AI orchestration planner role package | Enterprise Governance | ACTIVE | ADVISORY_ONLY; cannot execute worker tasks directly | `docs/governance/framework_orchestration_ai_multi_agent.md`; `docs/reports/governance/evidence_ai_orchestration_agent_review_records.md` | `tests/test_agentic_patterns.py`; `scripts/quality.ps1` |
| AIO-AGT-003 | AI orchestration worker role package | Enterprise Governance | ACTIVE | ADVISORY_ONLY; bounded task output only | `docs/governance/framework_orchestration_ai_multi_agent.md`; `docs/reports/governance/evidence_ai_orchestration_agent_review_records.md` | `tests/test_agentic_patterns.py`; `scripts/quality.ps1` |
| AIO-AGT-004 | AI orchestration control reviewer role package | Quality Governance | ACTIVE | VETO_OR_REVIEW_ONLY; cannot suppress findings or approve live execution | `docs/governance/framework_orchestration_ai_multi_agent.md`; `docs/reports/governance/evidence_ai_orchestration_agent_review_records.md` | `tests/test_agentic_patterns.py`; `scripts/quality.ps1` |
| AIO-AGT-005 | AI orchestration evidence recorder role package | Audit Governance | ACTIVE | RECORD_ONLY; cannot alter decisions or evidence claims | `docs/governance/framework_orchestration_ai_multi_agent.md`; `docs/reports/governance/evidence_ai_orchestration_agent_review_records.md` | `tests/test_agentic_patterns.py`; `scripts/quality.ps1` |
