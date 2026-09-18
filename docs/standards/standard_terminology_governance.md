---
document_id: AI4B-GOV-STD-TERM-001
title: AI4BINANCE Global Terminology and Taxonomy Standard
document_type: STANDARD
version: 1.2.1
status: ACTIVE
owner: Enterprise Knowledge Governance
authority_level: NORMATIVE
authority_layer: L4_REPOSITORY_STANDARDS_CONTROLS_QUALITY_POLICIES
authority_effect: NORMATIVE_CONSTRAINT
authority_scope: terminology_governance
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
machine_enforceable: true
audit_required: true
classification: INTERNAL
canonical_path: docs/standards/standard_terminology_governance.md
dependencies:
  - AI4B-GOV-STD-DKG-CORE-001
  - AI4B-GOV-STD-DKG-101
  - AI4B-GOV-STD-DKG-102
  - AI4B-GOV-STD-DKG-103
related_objects:
  - AI4B-GOV-STD-RFG-001
  - AI4B-GOV-FABRIC-001
companion_documents:
  terminology_reference: docs/references/reference_global_terminology_and_taxonomy.md
---
# AI4BINANCE Global Terminology and Taxonomy Standard

## ELI10

This standard makes terminology governance explicit so that one concept does not silently drift into multiple conflicting meanings across governed AI4BINANCE artifacts.
It also defines the canonical taxonomy layer that keeps global vocabulary, domain vocabularies, registries, schemas, contracts, code, and reports aligned.

## 1. Purpose

AI4BINANCE terminology governance exists to preserve semantic consistency, authority-aware naming, traceable alias handling, and fail-closed conflict visibility across governance, contracts, ontology, code-adjacent documentation, validation, and audit artifacts.

This standard governs terminology work for:

- canonical concepts;
- authoritative terms;
- abbreviations;
- aliases;
- deprecated terminology;
- prohibited terminology;
- artifact-specific term forms;
- external terminology authority references;
- semantic boundary notes;
- migration and compatibility status.

## 2. Scope Boundary

This standard governs terminology as repository knowledge.

It does not by itself:

- rename code automatically;
- authorize repository-wide rewrites;
- declare trading eligibility;
- override exchange terminology;
- replace ontology entity rules, schemas, or contracts;
- promote explanatory wording into machine authority without governed activation.

Physical path control remains governed by `docs/standards/standard_repository_file_governance.md`.

This standard is the canonical governed location for:

- the project-wide preferred vocabulary;
- terminology authority and synonym control;
- term lifecycle and migration handling;
- taxonomy families and decision-state vocabularies;
- boundary rules for ontology, taxonomy, and registry language.

## 3. Terminology Authority Model

Terminology authority must be declared per semantic family, not inferred from popularity, repeated usage, or LLM preference.

Terminology decisions must identify:

- canonical concept;
- canonical term;
- domain;
- primary authority source;
- artifact-specific permitted forms;
- compatibility requirements;
- semantic boundaries;
- verification status.

When multiple external vocabularies exist, AI4BINANCE must record the chosen authority basis and keep unresolved divergence visible as a governance blocker until resolved.

## 4. Concept and Representation Separation

A concept is not the same thing as a term, identifier, enum value, or display label.

Terminology governance must distinguish at minimum:

- concept;
- prose term;
- abbreviation;
- Python identifier;
- schema field;
- enum token;
- user-facing display label.

Multiple artifact forms may represent one concept without creating multiple concepts.

## 5. Canonical Terminology Record

Each governed terminology concept should be represented through a canonical record that captures at minimum:

```yaml
term_id: string
canonical_concept: string
definition: string
domain: string
artifact_forms:
  prose: string | null
  abbreviation: string | null
  python: string | null
  schema: string | null
  enum: string | null
  display: string | null
allowed_aliases: list[string]
deprecated_aliases: list[string]
prohibited_terms: list[string]
authority:
  type: string
  source: string
  reference: string
semantic_boundaries: list[string]
compatibility:
  migration_status: string
  verification_status: string
```

Generated views may exist, but one authoritative terminology record must remain the source of truth for each governed concept.

## 6. Approved Decision Outcomes

Terminology review outcomes must use explicit states:

```text
KEEP
CLARIFY
RENAME
ALIAS
DEPRECATE
BLOCK
```

`RENAME` must not be used when the reviewed usage is semantically valid under a different concept boundary.

`CLARIFY` is required when two related terms are both valid but require explicit scope separation.

## 7. Canonical Clarification Family: Ontology, Taxonomy, Registry

The terms `ontology`, `taxonomy`, and `registry` must not be normalized into one shared meaning.

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

### Registry Scope Qualifiers

When prose ambiguity matters, `registry` should be qualified by scope. Preferred phrases include:

- `governed document registry`
- `policy registry`
- `workflow registry`
- `risk rule registry`
- `agent registry`
- `runtime registry`
- `config-backed registry`
- `generated local registry`

### Approved Clarification Outcomes

For the current repository terminology baseline:

- `ontology` = `CLARIFY`
- `taxonomy` = `KEEP`
- `registry` = `CLARIFY`

The clarification outcome preserves existing governed meanings and must not be interpreted as authority for a repository-wide rename program.

## 8. Canonical Global Term Families and Taxonomy Maps

This section captures the project-wide vocabulary that appears repeatedly across governance, research, runtime, and audit artifacts.

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

## 9. Verification Workflow

Terminology governance must use bounded, evidence-based review:

```text
CURRENT STATE
  ↓
AUTHORITY RESOLUTION
  ↓
TERM FAMILY INVENTORY
  ↓
PRIMARY-SOURCE VERIFICATION
  ↓
SEMANTIC MAPPING
  ↓
KEEP / CLARIFY / RENAME / ALIAS / DEPRECATE / BLOCK
  ↓
BOUNDED IMPACT ANALYSIS
  ↓
MINIMAL IMPLEMENTATION
  ↓
TARGETED TESTS
  ↓
VALIDATOR
  ↓
NEXT_STEP / NEXT_SLICE / BLOCKED
```

Each `NEXT_STEP` must stay limited to one semantic family unless a higher-authority governed decision explicitly approves a wider batch.

## 10. Prohibited Practices

The following are prohibited:

- repository-wide term rewrites without semantic-family scoping;
- alias removal without compatibility analysis;
- forcing a preferred wording when the existing usage is semantically correct;
- treating abbreviations as separate concepts by default;
- allowing duplicate active source-of-truth terminology definitions;
- silently redefining exchange, ontology, schema, or governance terms;
- using external terminology without recording authority provenance for high-impact concepts.

## 10.1 Deterministic Enforcement Projection

`config/governance/canonical_terminology_registry.yaml` is the schema-validated,
non-authoritative policy-as-code projection of this standard. It is connected to
the single `AI4B-GOV-FABRIC-001` enforcement fabric together with the distinct
repository-naming and technology-language scopes.

The projection and fabric provide deterministic repository validation only.
They do not replace this standard, grant policy eligibility, authorize
consequential change, or alter `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED`.

## 11. Minimum Acceptance Criteria

Terminology governance work is acceptable only when:

- the semantic family is explicit;
- terminology authority is declared;
- canonical concept and artifact forms are separated;
- aliases and deprecations are visible;
- compatibility impact is bounded;
- targeted validation is recorded;
- unresolved terminology conflicts fail closed.

## 12. Constitutional Lock

This standard must remain aligned with `docs/standards/standard_documentation_knowledge_governance.md`, `docs/standards/standard_governed_knowledge_metadata.md`, `docs/standards/standard_governed_knowledge_registry_change.md`, `docs/standards/standard_governed_knowledge_authority_workflow.md`, `docs/standards/standard_repository_file_governance.md`, `docs/compliance/registry_compliance_matrix.md`, `AGENTS.md`, and deterministic repository validation evidence.

The lock does not authorize live trading, broad autonomous refactors, or unguided terminology normalization.

Safe outcomes remain:

```text
RUNNING_WITH_BLOCKERS
RESEARCH_ONLY
LIVE_ORDER_BLOCKED
```
