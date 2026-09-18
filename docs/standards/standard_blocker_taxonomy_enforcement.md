---
document_id: AI4B-GOV-STD-BLOCKER-001
title: AI4BINANCE Blocker Taxonomy and Enforcement Standard
document_type: STANDARD
version: 2.0.0
status: ACTIVE
owner: Enterprise Governance
authority_level: NORMATIVE
authority_layer: L4_REPOSITORY_STANDARDS_CONTROLS_QUALITY_POLICIES
authority_scope: blocker_taxonomy_enforcement
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
machine_enforceable: true
audit_required: true
classification: INTERNAL
canonical_path: docs/standards/standard_blocker_taxonomy_enforcement.md
schema_refs:
  - schemas/governance/blocker.schema.json
registry_refs:
  - config/governance/blocker_registry.yaml
implemented_by:
  - src/ai4binance/governance/blockers.py
validated_by:
  - tests/test_blocker_taxonomy.py
---

# AI4BINANCE Blocker Taxonomy and Enforcement Standard

## ELI10

This standard makes blockers precise. A blocker definition explains the canonical failure. A blocker occurrence records when that failure happened. Scores, final decisions, runtime states, and execution consequences are not blocker cause codes.

## 1. Purpose

AI4BINANCE uses blockers to stop unsafe, unvalidated, unauthorized, stale, inconsistent, or weakly evidenced actions. Blockers must be canonical, machine-readable, auditable, deterministic, replayable, and fail-closed.

This standard separates:

- blocker definition;
- runtime blocker occurrence;
- cause code;
- severity;
- scope;
- authority and clearance;
- lifecycle state;
- enforcement effect;
- score penalty;
- advisory finding;
- final decision outcome.

## 2. Control Channels

DGE and all governance consumers must classify controls into one of these channels:

| Control type | Blocks? | Affects score? | Canonical channel |
|---|---:|---:|---|
| `HARD_BLOCKER` | Yes | No | Veto |
| `CONDITIONAL_BLOCKER` | Yes, inside matching scope | No | Scoped veto |
| `PENALTY` | No | Yes | Score/ranking |
| `ADVISORY_FINDING` | No | No by default | Audit/review |
| `WARNING` | No | No | Observability |

`ADVISORY_FINDING` and `PENALTY` are not the same object. A penalty is a bounded deterministic scoring adjustment. An advisory finding is audit evidence. Neither may clear, downgrade, resolve, or compensate for a blocking occurrence.

`SOFT_BLOCKER` is intentionally not a canonical class.

## 3. Blocker Definition Contract

`config/governance/blocker_registry.yaml` contains canonical `BlockerDefinition` records only. It must not store runtime occurrences.

Every definition must carry:

```yaml
definition_id: string
blocker_code: DOMAIN.CAUSE
domain: GOVERNANCE | SECURITY | DATA | EVIDENCE | RISK | VALIDATION | STRATEGY | MODEL | AGENT | EXECUTION | PORTFOLIO | MARKET | LIQUIDITY | OPERATIONS | ARCHITECTURE | CONTRACT | SCHEMA | REPOSITORY | DEPENDENCY | TEST | CONFIGURATION | COMPLIANCE | RESEARCH | PROMOTION
blocker_class: HARD_BLOCKER | CONDITIONAL_BLOCKER | ADVISORY_FINDING
severity: INFO | LOW | MEDIUM | HIGH | CRITICAL
scope: OBJECT | COMPONENT | PIPELINE_STAGE | DECISION_CYCLE | SYMBOL | MARKET | STRATEGY | MODEL | AGENT | EXPERIMENT | REPOSITORY | DEPLOYMENT | EXECUTION_MODE | GLOBAL
authority: CORE_CONSTITUTION | GOVERNANCE_ENGINE | RISK_ENGINE | VALIDATION_ENGINE | SECURITY_CONTROL | COMPLIANCE_CONTROL | DATA_QUALITY_ENGINE | REPOSITORY_VALIDATOR | EXECUTION_GATE | HUMAN_GOVERNANCE
effects: list
waiver: structured requirements
clearance: detect/clear/waive/downgrade authority matrix
semantic_key: string
description: string
policy_ref: string
policy_version: string
control_ref: string
control_version: string
producer: string
source_component: string
remediation: string
precedence: integer
security_impact: boolean
```

`SECURITY_CRITICAL` is not a severity. Security criticality is represented by `domain: SECURITY`, `severity: CRITICAL`, and `security_impact: true`.

## 4. Blocker Occurrence Contract

Runtime and audit stores must record `BlockerOccurrence` objects. A runtime occurrence references exactly one canonical definition.

Every occurrence must carry:

```yaml
occurrence_id: string
definition_id: string
blocker_code: DOMAIN.CAUSE
domain: string
blocker_class: string
severity: string
scope: string
scope_ref: string | null
authority: string
effects: list
lifecycle_state: DETECTED | CONFIRMED | ACTIVE | MITIGATED | PENDING_VERIFICATION | RESOLVED | WAIVED | SUPERSEDED | FALSE_POSITIVE
evidence_refs: list
detected_at: string
policy_ref: string
policy_version: string
control_ref: string
control_version: string
producer: string
source_component: string
remediation: string
correlation_id: string | null
cycle_id: string | null
snapshot_id: string | null
fingerprint: string
occurrence_count: integer
first_seen_at: string
last_seen_at: string
root_cause_codes: list
resolution_evidence: list
waiver: structured requirements | null
```

`is_blocking` is a derived property:

```text
blocker_class in {HARD_BLOCKER, CONDITIONAL_BLOCKER}
AND scope_matches(action)
AND lifecycle_state in {DETECTED, CONFIRMED, ACTIVE}
```

Do not persist a contradictory `hard_gate` boolean in authoritative blocker payloads.

## 5. Cause Code Namespace

Canonical blocker codes must use `DOMAIN.CAUSE` format. The canonical registry is `config/governance/blocker_registry.yaml`.

Allowed domain prefixes include:

```text
GOV SEC DATA EVID RISK VAL STRAT MODEL AGENT EXEC PORT MARKET LIQ OPS ARCH CONTRACT SCHEMA REPO DEP TEST CONFIG COMPLIANCE RESEARCH PROMOTION
```

Legacy upper-snake names may appear only as migration aliases in the registry. New authoritative artifacts must emit canonical codes.

## 6. Forbidden Cause Codes

The following values are not cause codes and must not be emitted as `blocker_code`:

```text
RUNNING_WITH_BLOCKERS
LIVE_ORDER_BLOCKED
RESEARCH_ONLY
NO_TRADE
BLOCKED
CRITICAL
SECURITY_CRITICAL
```

These are states, effects, decisions, or severities.

## 7. Effect Taxonomy

Effects describe the required system consequence:

```text
QUALITY_GATE_BLOCKED
RUNNING_WITH_BLOCKERS
RESEARCH_ONLY
CANDIDATE_BLOCKED
DECISION_CYCLE_BLOCKED
STRATEGY_BLOCKED
SYMBOL_BLOCKED
MARKET_BLOCKED
EXPERIMENT_BLOCKED
BACKTEST_BLOCKED
PAPER_ORDER_BLOCKED
LIVE_ORDER_BLOCKED
PROMOTION_BLOCKED
DEPLOYMENT_BLOCKED
GOVERNANCE_REVIEW_REQUIRED
EXECUTION_NOT_ALLOWED
```

`LIVE_ORDER_BLOCKED`, `NO_TRADE`, and `RUNNING_WITH_BLOCKERS` are outcomes, effects, or system states, never root-cause blocker codes.

## 8. Fingerprint and Deduplication

Runtime blocker deduplication must use a stable fingerprint derived from:

```text
blocker_code
+ scope
+ scope_ref
+ policy_version
+ control_version
+ material_evidence_identity
```

Repeated detection of the same material blocker updates `last_seen_at` and `occurrence_count` rather than creating duplicate independent root causes.

## 9. Authority and Clearance

Clearance is definition-specific and must not be inferred from enum order. Each definition declares:

```yaml
clearance:
  detect_authorities: []
  clear_authorities: []
  waive_authorities: []
  downgrade_authorities: []
```

LLMs and advisory agents may propose blocker candidates, but they must not clear, waive, downgrade, or override authoritative blockers.

`GOV.BYPASS_ATTEMPT`, `GOV.CORE_CONSTITUTION_CONFLICT`, `SEC.SECRET_EXPOSURE`, and `EXEC.LIVE_EXECUTION_UNAUTHORIZED` are not waivable.

## 10. Waiver Model

Waivers are structured requirements, not a single enum. A waiver must declare:

```yaml
waiver:
  allowed: true
  required_authorities: []
  requires_written_approval: true
  requires_justification: true
  requires_evidence: true
  requires_expiry: true
  max_duration_hours: 24
  execution_scope_allowed: false
```

For non-waivable blockers:

```yaml
waiver:
  allowed: false
```

Expired or revoked waivers must reopen to `ACTIVE`.

## 11. Lifecycle Rules

Allowed transitions are:

```text
DETECTED
   -> CONFIRMED
   -> FALSE_POSITIVE

CONFIRMED
   -> ACTIVE

ACTIVE
   -> MITIGATED
   -> WAIVED
   -> SUPERSEDED

MITIGATED
   -> PENDING_VERIFICATION

PENDING_VERIFICATION
   -> RESOLVED
   -> ACTIVE

WAIVED
   -> ACTIVE
   -> SUPERSEDED
```

`MITIGATED` is not `RESOLVED`. `ACTIVE` must not transition directly to `RESOLVED`. `RESOLVED` requires resolution evidence.

## 12. Precedence and Root Cause

Precedence defines primary blocker selection, reporting order, and remediation order. It does not suppress lower-precedence blockers.

Preferred precedence:

```text
P0 CORE / SECURITY / AUTHORITY
P1 DATA / CONTRACT / SCHEMA
P2 EVIDENCE
P3 VALIDATION
P4 RISK / PORTFOLIO
P5 MARKET / LIQUIDITY
P6 EXECUTION
P7 STRATEGY / MODEL / AGENT
P8 RESEARCH / PROMOTION
P9 REPOSITORY / TEST / OPERATIONS
```

Derived outcomes such as `NO_TRADE`, `PAPER_ORDER_BLOCKED`, or `LIVE_ORDER_BLOCKED` must be represented as effects or decisions, not duplicate blockers.

## 13. Invariants

`B-001`: Every active blocker must have a canonical blocker code.

`B-002`: A blocker code must represent a cause, never a system state, severity, decision outcome, or execution consequence.

`B-003`: Definitions and occurrences must be separate contracts.

`B-004`: Every definition must declare policy/control lineage, producer, source component, waiver, clearance, effects, and remediation.

`B-005`: Every occurrence must declare definition id, policy/control lineage, evidence refs, lifecycle state, fingerprint, and occurrence timestamps.

`B-006`: `HARD_BLOCKER` must not be compensated by aggregate scores.

`B-007`: `CONDITIONAL_BLOCKER` must block every action inside its declared matching scope.

`B-008`: Only explicitly declared clearance authorities may clear a blocker.

`B-009`: `ACTIVE` must not transition directly to `RESOLVED`.

`B-010`: `NOT_WAIVABLE` semantics must be represented as `waiver.allowed: false`.

`B-011`: LLMs and advisory agents must not clear, waive, downgrade, or override authoritative blockers.

`B-012`: `LIVE_ORDER_BLOCKED` must be an effect, never a blocker cause.

`B-013`: `NO_TRADE` must remain a deterministic decision outcome, not a blocker identifier.

`B-014`: Repository health, strategy score, signal score, confidence, or evidence score must not mask active hard blockers.

`B-015`: Duplicate semantic blocker codes must fail governance validation.

`B-016`: Unknown blocker codes must fail closed.

`B-017`: Any governance conflict affecting execution authority must imply `LIVE_ORDER_BLOCKED`.

`B-018`: New authoritative blocker payloads must not use migration aliases.
