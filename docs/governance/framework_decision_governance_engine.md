---
document_id: AI4B-DGE-RULE-001
title: AI4BINANCE Decision Governance Engine
document_type: DECISION_RULE
version: 1.0.1
status: ACTIVE
owner: Enterprise Knowledge Governance
authority_level: NORMATIVE
authority_layer: L2_GOVERNANCE_COMPLIANCE
authority_scope: decision_governance_engine
authority_effect: NORMATIVE_CONSTRAINT
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: decision_governance_engine
canonical_path: docs/governance/framework_decision_governance_engine.md
machine_enforceable: true
audit_required: true
classification: INTERNAL
---

# Decision Governance Engine

## ELI10

This file explains the Decision Governance Engine. DGE evaluates whether a candidate is governable and blocked or reviewable; it does not execute trades.

This decision rule is an `L2_GOVERNANCE_COMPLIANCE` normative constraint for
governance eligibility. It may restrict downstream decision flow, but it may
not widen or override higher-authority constitutional boundaries.


The Decision Governance Engine (DGE) is the deterministic governance layer
between opportunity candidates and execution eligibility.

## Purpose

DGE does not generate alpha and does not create a second signal engine. It
evaluates whether an existing candidate is governable, explainable,
validated, risk-controlled, and execution-feasible.

## Responsibility boundaries

| Component | Owns | Must not own |
|---|---|---|
| Strategy engine | Candidate generation | Final authorization |
| Opportunity Recovery Radar | Candidate ladder | Live execution |
| Validation layer | Technical/OOS validity evidence | Risk override |
| DGE | Governance status and blockers | Exchange execution |
| Risk manager | Financial risk constraints | LLM override |
| Portfolio manager | Inventory and concentration feasibility | Backtest mutation |
| Execution engine | Order validation and compliant execution | Signal generation |
| Local Qwen / LLM | Explanation, audit, experiments | Authorization |

## Rule hierarchy

The first DGE slice centralizes rule metadata for:

1. system safety
2. data quality
3. liquidity
4. portfolio
5. regime
6. multi-timeframe alignment
7. negative evidence
8. structure/invalidation
9. validation/OOS
10. risk
11. execution feasibility
12. human review
13. setup score
14. confidence
15. risk/reward

Hard and critical blockers override all scores.

## Canonical control evaluation

DGE consumes the shared `ControlEvaluation` primitive for decision, risk, and
validation controls:

```text
HardBlocker -> eligibility/veto channel
SoftPenalty -> score/ranking channel
```

Hard blockers are binary vetoes. They cannot be represented as large negative
numeric penalties and cannot be offset by positive signal scores, bonuses,
confidence, ranking or soft penalties. Soft penalties are bounded deterministic
adjustments that may reduce ranking or confidence, but they cannot create,
clear, downgrade or resolve a hard blocker.

Opportunity lifecycle states such as `WATCH_ONLY` and `CONFIRMATION_PENDING`
are advisory reporting states only. They help explain where a candidate is in
the governed funnel, but they do not grant execution authority or live
eligibility.

Every hard blocker declares its source, policy reference, evidence references,
scope and resolution authority. Handoff layers may carry blocker and penalty
references, but they do not classify, resolve, downgrade or reweight controls.
Unknown trading-sensitive control classification fails closed.

## Status model

```text
APPROVED
APPROVED_PAPER_ONLY
WATCH_ONLY
WAIT_FOR_RETEST
MANUAL_REVIEW
REJECTED
BLOCKED
NO_TRADE
DATA_UNAVAILABLE
LOW_CONFIDENCE
```

`APPROVED_PAPER_ONLY` is not live authorization.

Execution-surface authority binding:

```text
BINANCE_MARKET
  -> HUMAN_HAND_MANUAL_ONLY
  -> requires_manual_confirmation=true
  -> auto_execution_allowed=false

VIRTUAL_MARKET
  -> BOUNDED_AUTONOMOUS_SIMULATION
  -> requires_manual_confirmation=false
  -> auto_execution_allowed=true
```

## Score model

DGE stores separate deterministic scores:

```text
signal_score
evidence_score
data_quality_score
mtf_score
regime_score
liquidity_score
risk_score
execution_score
confidence_score
governance_score
```

`governance_score` becomes zero when hard blockers exist. A weighted score
cannot cancel a critical risk, data, liquidity, or execution violation.
No score may compensate for an active hard blocker.

## Paper/live boundary

Every current DGE decision remains:

```text
promotion_status = RESEARCH_ONLY
live_eligibility_status = LIVE_ORDER_BLOCKED
live_execution_allowed = false
```

For `BINANCE_MARKET`, DGE may produce paper eligibility but it must remain
human-hand manual only. For `VIRTUAL_MARKET`, DGE may produce bounded auto
paper eligibility only inside the governed paper path. Neither surface grants
live authorization.

Local Qwen/Ollama output may explain decisions and propose experiments only as
`ADVISORY_ONLY`.

## Next implementation slices

1. Add Recovery Radar → DGE adapter.
2. Add YAML registry loading and startup validation.
3. Add DGE event persistence.
4. Add deterministic replay command.
5. Add shadow-rule counterfactual reporting.
