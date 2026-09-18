---
document_id: AI4B-GOV-REF-TERM-TAX-001
title: AI4BINANCE Global Terminology and Taxonomy Reference
document_type: REFERENCE
version: 1.0.1
status: DRAFT
owner: Enterprise Knowledge Governance
authority_level: REFERENCE
authority_layer: L9_REFERENCES_TEMPLATES
authority_scope: global_terminology_and_taxonomy
content_role: EXPLANATORY
source_of_truth: false
machine_enforceable: false
audit_required: true
classification: INTERNAL
canonical_path: docs/references/reference_global_terminology_and_taxonomy.md
split_from:
  document_id: AI4B-GOV-STD-TERM-001
  source_file: docs/standards/standard_terminology_governance.md
parent_standard: docs/standards/standard_terminology_governance.md
---

# AI4BINANCE Global Terminology and Taxonomy Reference

> Source basis: companion reference to `docs/standards/standard_terminology_governance.md` (`document_id: AI4B-GOV-STD-TERM-001`).
> This reference mirrors the canonical terminology families and taxonomy maps so that readers can review the vocabulary layer without re-reading the full normative standard.

## ELI10

This reference keeps the terminology and taxonomy model in a simpler, reader-friendly form.
It is explanatory only and does not replace the active governed standard.

## Purpose

This reference preserves the project-wide terminology families, decision vocabulary, evidence vocabulary, risk vocabulary, lifecycle vocabulary, registry vocabulary, and taxonomy maps from the active standard.

Normative authority remains in `docs/standards/standard_terminology_governance.md`.

| Output file | Original sections |
|---|---|
| `standard_terminology_governance.md` | Sections 1-6, 7, 8, 9-12 |
| `reference_global_terminology_and_taxonomy.md` | Canonical vocabulary and taxonomy families used for review and navigation |

## 7. Canonical Clarification Family: Ontology, Taxonomy, Registry

This reference preserves the semantic boundary rules that keep core governance terms from collapsing into one another.

### Canonical Prose Definitions

- `ontology`
  A formal semantic model that defines governed entities, relationships, capabilities, or meaning-bearing structures.
- `taxonomy`
  A classification structure that organizes concept families, categories, or semantic groupings.
- `registry`
  A canonical registration surface that records governed objects, their identity, status, authority, scope, or lifecycle.

### Semantic Boundary Notes

- `ontology` is not a synonym for `taxonomy`.
- `taxonomy` is not a synonym for `registry`.
- `registry` is not a semantic model by default; it is a controlled registration surface.
- An ontology may reference taxonomy categories.
- A registry may store ontology-backed or taxonomy-backed objects without becoming the ontology or taxonomy itself.

### Approved Clarification Outcomes

For the current repository terminology baseline:

- `ontology` = `CLARIFY`
- `taxonomy` = `KEEP`
- `registry` = `CLARIFY`

## 8. Canonical Global Term Families and Taxonomy Maps

### 8.1 Global vocabulary rules

```text
Global Standard Vocabulary
        ↓
AI4BINANCE Canonical Vocabulary
        ↓
Domain Taxonomy
        ↓
Contracts / Schemas / Registries
        ↓
Code / Config / Tests / Reports
```

Rules:

1. One concept must have one canonical term.
2. A concept, a term, an enum token, and a display label are related but not identical.
3. Global terminology should prefer common industry meanings unless AI4BINANCE safety semantics require stricter meaning.
4. Discovery is not adoption.
5. Backtest success is not live approval.
6. Evidence quality, validation status, and decision state are separate concepts.
7. A high score must never override a hard blocker.

### 8.2 Canonical safety and decision vocabulary

| Preferred Term | Definition | Required Use |
|---|---|---|
| `WAIT` | No action now; pending evidence, timing, or confirmation. | Use for incomplete or mistimed setups. |
| `WATCH_ONLY` | Observe the concept without execution. | Use for non-actionable opportunities and research monitoring. |
| `NO_TRADE` | Explicit rejection of execution. | Use when blockers or vetoes are present. |
| `PAPER_ELIGIBLE` | Eligible only for paper execution. | Use only after required governance gates pass. |
| `PAPER_TRADING` | Simulated execution using non-live funds. | Use as the default execution posture. |
| `PAPER_EXECUTED` | A paper order or position has been simulated. | Use for simulated execution records only. |
| `RESEARCH_ONLY` | Output is advisory or research stage only. | Use when execution is not allowed. |
| `MANUAL_CONFIRMATION` | Human approval is required before consequential action. | Use for live or high-impact changes. |
| `LIVE_EXECUTION_DISABLED` | Live trading is prohibited. | Use as the default live safety state. |
| `READ_ONLY_API` | Data access is allowed, trading is not. | Use for least-privilege exchange access. |
| `LIVE_ORDER_BLOCKED` | Live order placement is prohibited by policy or authority. | Use when live action is not authorized. |
| `EXECUTION_NOT_ALLOWED` | Execution is blocked by mode, policy, or eligibility. | Use for any blocked execution path. |
| `ADVISORY_ONLY` | LLM or agent output is advisory, not authoritative. | Use when the model explains or recommends but cannot decide. |
| `RUNNING_WITH_BLOCKERS` | Work may continue only in degraded or limited mode. | Use when analysis can continue but governance is not clear. |
| `DATA_UNAVAILABLE` | Required data is missing. | Use instead of guessing or fabricating data. |
| `NOT_VERIFIED` | A claim or result has not been verified. | Use for unverified evidence or assumptions. |
| `LOW_CONFIDENCE` | Confidence is weak or unstable. | Use when evidence is incomplete or contradictory. |

### 8.3 Canonical data, evidence, and provenance vocabulary

| Preferred Term | Definition | Required Use |
|---|---|---|
| `DataSource` | Origin of data used by the system. | Use for exchange, news, social, on-chain, and internal sources. |
| `RawData` | Data before normalization and quality checks. | Use for immutable ingestion evidence. |
| `Normalization` | Conversion into a canonical internal form. | Use when mapping source-specific data to internal structures. |
| `CanonicalMarketData` | Standardized market data model used internally. | Use as the shared source for downstream analysis. |
| `MarketSnapshot` | Immutable, versioned state used in one decision cycle. | Use as the shared decision input. |
| `FeatureSnapshot` | Versioned set of features derived from a market snapshot. | Use for deterministic feature reuse. |
| `Evidence` | Information that supports or opposes a conclusion. | Use for decisioning, validation, and audit. |
| `EvidenceBundle` | Structured set of evidence for a candidate or decision. | Use as the reviewable evidence container. |
| `SupportingEvidence` | Evidence that supports a candidate. | Use in positive case analysis. |
| `CounterEvidence` | Evidence that weakens or rejects a candidate. | Use in risk and rejection logic. |
| `Provenance` | Record of how an artifact was produced. | Use for traceability and auditability. |
| `Lineage` | Chain from source to output through transformation steps. | Use for replay and audit review. |
| `Traceability` | Ability to connect requirements, evidence, decision, implementation, and tests. | Use in governance and compliance contexts. |
| `AuditArtifact` | Immutable artifact created for later review. | Use for decisions, reviews, and control evidence. |

### 8.4 Canonical risk, validation, and lifecycle vocabulary

| Preferred Term | Definition | Required Use |
|---|---|---|
| `RiskAssessment` | Structured assessment of a risk condition. | Use before decision or execution eligibility. |
| `RISK_VETO` | A risk condition that blocks progression. | Use for hard blockers. |
| `GOVERNANCE_CONFLICT` | A contradiction between governed artifacts or authority levels. | Use when higher and lower authority sources disagree. |
| `Validation` | Deterministic or evidentiary check against a rule or expectation. | Use for data, strategy, model, execution, and governance checks. |
| `BacktestValidation` | Validation using historical simulation. | Use as research evidence only. |
| `WalkForwardValidation` | Rolling validation across time segments. | Use before live candidacy. |
| `OutOfSampleValidation` | Validation on unseen data. | Use as a mandatory promotion gate where applicable. |
| `RobustnessValidation` | Validation against sensitivity and stress cases. | Use before promotion. |
| `LifecycleState` | Controlled status describing governance maturity. | Use for governed object lifecycle tracking. |
| `RESEARCH` | Early analytical or experimental stage. | Use for ideas not yet validated. |
| `BACKTESTED` | Historical simulation has been completed. | Use when research simulation is available. |
| `OOS_VALIDATED` | Out-of-sample evidence exists. | Use for promotion readiness checks. |
| `STAGED_CANDIDATE` | Post-validation, pre-paper promotion state used for shadow or paper preparation. | Use after required validation and review gates pass, before paper approval. |
| `PAPER_APPROVED` | Approved for paper execution only. | Use before paper deployment or simulation. |
| `LIVE_CANDIDATE` | Candidate under review for live eligibility. | Use only when live gates are almost satisfied. |
| `LIVE_APPROVED` | Live eligibility has been approved through governed process. | Use only with explicit authorization. |
| `SUSPENDED` | Temporarily disabled due to drift, failure, or risk. | Use for quarantined or paused objects. |
| `DEPRECATED` | Superseded and no longer recommended. | Use for removed or legacy terms. |

### 8.5 Canonical registry and technology vocabulary

| Preferred Term | Definition | Required Use |
|---|---|---|
| `Registry` | Governed catalog of controlled objects. | Use for models, agents, strategies, policies, and experiments. |
| `RegistryObject` | An item recorded in a registry with lifecycle and authority metadata. | Use as the base governed object model. |
| `canonical_path` | Repository-relative canonical location of the source-of-truth artifact. | Use as the single canonical path field. |
| `source_of_truth` | Flag indicating the authoritative record for a concept or artifact. | Use only for one active source per concept. |
| `owner` | Responsible governance owner. | Use for accountability and change control. |
| `authority_level` | Declared authority tier of the artifact. | Use to resolve conflicts and precedence. |
| `TechnologyFinding` | Structured observation about a technology or standard. | Use for technology intelligence outputs. |
| `TechnologyFindingStatus` | Status of a technology finding across its lifecycle. | Use for watch, research, and adoption control. |
| `WATCH_ONLY` | Relevant but not actionable. | Use when evidence is insufficient or maturity is low. |
| `RESEARCH_CANDIDATE` | Worth further investigation. | Use after source verification and triage. |
| `EXPERIMENT_CANDIDATE` | Approved for bounded experimentation. | Use before implementation in a hot path. |
| `ADOPTION_CANDIDATE` | May be proposed for integration after validation. | Use only with evidence and governance review. |
| `BLOCKED` | Prohibited by safety, governance, legal, or architecture constraints. | Use when the item cannot proceed. |

### 8.6 Canonical taxonomy maps

#### DecisionState

```text
DecisionState
├── WAIT
├── WATCH_ONLY
├── NO_TRADE
├── PAPER_ELIGIBLE
├── PAPER_EXECUTED
├── EXECUTION_NOT_ALLOWED
└── LIVE_ORDER_BLOCKED
```

#### RiskTaxonomy

```text
Risk
├── DataRisk
├── MarketRisk
├── LiquidityRisk
├── ExecutionRisk
├── ModelRisk
├── StrategyRisk
├── GovernanceRisk
├── SecurityRisk
└── ComplianceRisk
```

#### ValidationTaxonomy

```text
Validation
├── DataValidation
├── SignalValidation
├── StrategyValidation
├── ModelValidation
├── RegimeValidation
├── BacktestValidation
├── WalkForwardValidation
├── OutOfSampleValidation
├── RobustnessValidation
├── ExecutionValidation
└── GovernanceValidation
```

#### RegistryObjectType

```text
RegistryObject
├── DataSourceRegistryEntry
├── DatasetRegistryEntry
├── FeatureRegistryEntry
├── IndicatorRegistryEntry
├── ModelRegistryEntry
├── AgentRegistryEntry
├── StrategyRegistryEntry
├── ParameterSetRegistryEntry
├── PromptRegistryEntry
├── ToolRegistryEntry
├── PolicyRegistryEntry
├── RiskRuleRegistryEntry
├── WorkflowRegistryEntry
├── ExperimentRegistryEntry
└── TechnologyRegistryEntry
```

#### LifecycleStatus

```text
DRAFT
  -> RESEARCH
  -> BACKTESTED
  -> WALK_FORWARD_VALIDATED
  -> OOS_VALIDATED
  -> STAGED_CANDIDATE
  -> ROBUSTNESS_VALIDATED
  -> PAPER_APPROVED
  -> LIVE_CANDIDATE
  -> LIVE_APPROVED

Alternative terminal or control states:
  WATCH_ONLY
  DEFERRED
  REJECTED
  BLOCKED
  QUARANTINED
  SUSPENDED
  DEPRECATED
  SUPERSEDED
```

#### TechnologyFindingStatus

```text
DISCOVERED
TRIAGED
SOURCE_VERIFIED
RELEVANCE_CONFIRMED
ARCHITECTURE_MAPPED
RISK_ASSESSED
WATCH_ONLY
RESEARCH_CANDIDATE
EXPERIMENT
BENCHMARKED
VALIDATED
ADOPTION_CANDIDATE
HUMAN_REVIEW
APPROVED
BOUNDED_IMPLEMENTATION
REJECTED
DUPLICATE
DEFERRED
QUARANTINED
DEPRECATED
BLOCKED
```

### 8.7 Key anti-patterns

| Anti-pattern | Required replacement |
|---|---|
| `Signal = trade` | `Signal -> Candidate -> Governance -> Decision` |
| `Backtest equals approval` | `Backtest -> WF -> OOS -> Robustness -> Paper` |
| `Discovery equals adoption` | `TechnologyFinding -> ExperimentCandidate -> AdoptionCandidate` |
| `LLM decided` | `DeterministicDecisionEngine produced` |
| `Unknown means probably fine` | `NOT_VERIFIED` or `DATA_UNAVAILABLE` |
| `High score overrides blockers` | `Hard gates + veto authority` |

## 9. Use Guidance

This reference can be used for:

- terminology review;
- taxonomy navigation;
- documentation review;
- terminology drift detection;
- registry normalization discussions;
- onboarding and explanation.

It must not be used to override the active standard, lower governance barriers, or reinterpret safety terms more permissively than the standard does.

## 10. Reference Boundary

If this reference conflicts with the active standard, the active standard wins.

If a term is missing here but present in the active standard, the active standard is the source of truth.

When terminology governance changes, update the standard first and refresh this reference afterwards.
