---
document_id: AI4B-GOV-RPT-442
title: AI4BINANCE Logical Architecture Registry Report
document_type: REFERENCE
version: 1.14.0
status: ACTIVE
owner: Enterprise Governance
authority_level: INFORMATIONAL
authority_layer: L8_REPORTS_EVIDENCE_INVENTORIES
authority_scope: logical_architecture_registry
authority_effect: EVIDENCE_ONLY
content_role: DERIVED
source_of_truth: false
source_of_truth_scope: none
machine_enforceable: false
audit_required: true
classification: INTERNAL
canonical_path: docs/reports/governance/report_logical_architecture_registry.md
---

# AI4BINANCE Logical Architecture Registry Report

## ELI10

This report describes the local logical-architecture registry as a
machine-readable enforcement mirror. The registry makes declared components,
typed relations, dependency cycles, and explicit authority ceilings visible. It
does not replace governed architecture documents, authorize trading, alter risk
limits, promote a strategy, or allow live execution.

## Component Taxonomy

Every declared component has exactly one `component_kind`. The local schema and
typed model accept only `DOMAIN`, `CAPABILITY`, `SERVICE`, `GATE`, `ENGINE`,
`ORCHESTRATOR`, `RUNTIME_ACTOR`, `ADVISORY_AGENT`, `CONTROL`, `FACADE`,
`ADAPTER`, or `REGISTRY`. A kind is descriptive only: it cannot assign decision,
risk, validation, promotion, execution, or source-of-truth authority.

## Runtime Link

`src/ai4binance/governance/architecture/model.py` defines the typed,
non-authoritative component, relation, and registry contracts. Relation IDs and
their `(source, type, target)` semantics must both remain unique, preventing
parallel aliases for one declared architectural relationship.

`src/ai4binance/governance/architecture/loader.py` validates the local YAML
registry against local Draft 2020-12 schemas, rejects authority grants, requires
every declared source, contract, and test reference to resolve to a repository
file under the explicitly selected repository root, and rejects dependency
cycles. It derives the canonical domain-to-plane mapping from
`build_core_architecture()` and rejects mapping drift; this aligns the Risk
Assessment component with the Core `08_RISK` decision-and-execution plane. It
also rejects removal or semantic drift of the registered canonical
decision-chain relations and their Risk, Validation, and evidence-only authority
effects. The Deterministic Core and Decision Governance implementation effects
are fixed as part of that chain without granting either component registry-level
decision authority. Every critical decision-chain component must remain
on the declared hot path, deterministic, and free of an LLM dependency. In
direct alignment with Core rule `RR-004`, the loader rejects any declared
`ADVISORY_AGENT -> PRODUCES -> TradeDecision` shortcut. It also enforces
Decision Governance as the only declared `TradeDecision` producer, preventing
parallel final-decision paths around the canonical chain. Core rule `RR-012`
also requires every declared `TradeDecision` to remain governed by the
deterministic, default-deny Policy control. Core rule `RR-013` independently
requires every declared `TradePlan` to remain subject to an `ExecutionGateResult`;
the gate has veto effect and neither component gains execution authority. In
direct alignment with Core rule `RR-014`, the loader also rejects the forbidden
`ADVISORY_AGENT -> EXECUTES -> Order` shortcut. Core rule `RR-015` requires the
declared `ExecutionRecord` to create the `PositionLifecycle` lineage contract;
this mirror relation has no operational side effect or execution authority.
Core rule `RR-016` then requires `PositionLifecycle` to be evaluated by the
deterministic `ClosureReview` evidence contract. The review remains
non-authoritative and cannot promote, execute, or override a gate. Core rule
`RR-017` requires the review to produce a `Lesson` evidence contract. The
declared lesson remains research-only and cannot activate itself, alter a
parameter, or gain production authority. Core rule `RR-018` permits the lesson
to propose a `LearningCandidate`; proposal remains distinct from validation,
human-governed promotion, production authority, and execution. In direct
alignment with Core rule `RR-019`, the loader also rejects the forbidden
`LearningCandidate -> PROMOTES -> ProductionComponent` shortcut. Learning
candidates therefore cannot promote themselves or acquire production authority
through the enforcement mirror.

`src/ai4binance/governance/architecture/graph.py` provides deterministic
dependency and cycle analysis. It has no operational side effects.

`src/ai4binance/governance/architecture/__init__.py` exposes this bounded
registry surface. `src/ai4binance/ops/kaizen_quality.py` consumes it only as a
read-only Kaizen evidence view and binds validation to the snapshot repository
root.

## Opportunity Intelligence and Outcome Evidence Mapping

The registry maps the opportunity-intelligence implementation onto three
bounded, non-authoritative components. This is an implementation and evidence
ownership record; it does not create a second decision, risk, validation, or
Virtual Market authority.

`opportunity-intelligence` owns deterministic closed-candle, multi-timeframe
research diagnostics in `src/ai4binance/opportunity_intelligence.py`. It may
produce advisory opportunity evidence only. It must not authorize a trade,
override a veto, or consume future higher-timeframe candle closes.

`opportunity-lifecycle-ledger` owns append-only opportunity lifecycle evidence
in `src/ai4binance/opportunity_ledger.py`. Compatibility replay serialization
in `src/ai4binance/historical_replay_state.py` must preserve the same
`opportunity_id` lineage without creating a second ledger or mutating historical
decisions.

`opportunity-outcome-evaluation` owns post-hoc MFE/MAE and missed-opportunity
research evaluation in `src/ai4binance/opportunity_outcomes.py`.
`src/ai4binance/research/backtesting/futures_engine.py` carries the same
opportunity lineage through deterministic Futures replay. Outcome evidence is
available only after its evaluation horizon and must never enter the candidate
generation hot path.

The source-to-test proof mapping is:

```text
src/ai4binance/opportunity_intelligence.py
  -> tests/test_opportunity_intelligence.py
src/ai4binance/opportunity_ledger.py
  -> tests/test_opportunity_intelligence.py
src/ai4binance/opportunity_outcomes.py
  -> tests/test_opportunity_intelligence.py
src/ai4binance/historical_replay_state.py
  -> tests/test_historical_replay_state.py
src/ai4binance/research/backtesting/futures_engine.py
  -> tests/test_futures_backtest_engine.py
```

All three mappings remain deterministic, LLM-free, `RESEARCH_ONLY`,
`execution_allowed=false`, and `LIVE_ORDER_BLOCKED`.

## Critical Decision, Execution, and Learning-Lineage Coverage

The bounded decision-chain coverage now declares every required relationship
carried by Core rules `RR-007`, `RR-008`, `RR-012`, `RR-013`, `RR-015`,
`RR-016`, `RR-017`, `RR-018`, `RR-021`, and `RR-022`, and independently
enforces the `RR-019` prohibited self-promotion relationship:

```text
Setup -> EVALUATED_BY -> DeterministicCore
DeterministicCore -> PRODUCES -> DecisionCandidate
DecisionCandidate -> CONSTRAINED_BY -> RiskAssessment
DecisionCandidate -> VALIDATED_BY -> Validation
DecisionGovernance -> PRODUCES -> TradeDecision
TradeDecision -> GOVERNED_BY -> Policy
TradePlan -> SUBJECT_TO -> ExecutionGateResult
ExecutionRecord -> CREATES -> PositionLifecycle
PositionLifecycle -> EVALUATED_BY -> ClosureReview
ClosureReview -> PRODUCES_LESSON -> Lesson
Lesson -> PROPOSES -> LearningCandidate
```

Forbidden:

```text
LearningCandidate -> PROMOTES -> ProductionComponent
```

`Setup`, `DecisionCandidate`, `TradeDecision`, `TradePlan`, `ExecutionRecord`,
`PositionLifecycle`, `ClosureReview`, `Lesson`, and `LearningCandidate` remain
distinct contracts. Risk, Validation, Policy, and Execution Gate retain veto
effects, while every registry entry remains explicitly non-authoritative and
live-order blocked. This declaration proves
canonical contract and relationship coverage only; it does not claim that the
runtime `TradeCandidate` path or every Risk and Validation handoff into Decision
Governance is fully wired or operationally verified.

## Boundary

The declared registry and every component must preserve:

```text
source_of_truth = false
side_effects = false
decision_authority = false
risk_override = false
validation_override = false
execution_allowed = false
live_eligibility_status = LIVE_ORDER_BLOCKED
```

Canonical architecture remains defined by the active governed architecture and
Core documents. Any future source-of-truth migration requires a separately
approved C3 governed change with current hashes and evidence.

## Verification

`tests/governance/architecture/test_logical_architecture_registry.py` covers
the local schema, stable ordering, authority-grant rejection, repository
reference integrity, canonical domain-to-plane alignment, canonical
decision-chain semantics, relation endpoint and semantic-uniqueness validation,
missing or altered canonical decision-chain and authority-effect rejection,
nondeterministic or LLM-dependent decision-chain rejection, critical hot-path
drift rejection, unauthorized `TradeDecision` producer rejection,
unauthorized advisory-agent execution rejection, unauthorized learning-candidate
self-promotion rejection, component-kind closure, and deterministic acyclic
dependency enforcement.
