---
document_id: AI4B-GOV-FRM-001
title: AI4BINANCE Core vNext Governance Framework
document_type: FRAMEWORK
version: 2.0.12
status: ACTIVE
owner: Enterprise Governance
authority_level: NORMATIVE
authority_layer: L1_CORE_CONSTITUTION
authority_scope: core_constitution
authority_effect: NORMATIVE_CONSTRAINT
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
machine_enforceable: true
audit_required: true
classification: INTERNAL
canonical_path: docs/governance/framework_core_vnext_governance.md
---

# AI4BINANCE Core vNext Governance Framework

## ELI10

This document is the system's core rulebook. Code, agents, data, evidence, and decisions,
risk, execution, audit, and learning layers cannot move outside the constitution
and governance contract written here. If a feature is listed as a target here,
it is considered complete only when proven by the relevant Python contract, test,
evidence, and compliance record.

This document is the core architecture, schema, standard, and governance principles for AI4BINANCE EnterpriseAI vNext,
instructions, entity rules, relationship rules, output format, policy,
the canonical source document for core governance semantics.

The Organization Constitution and Handbook is a stable family index, and
provider-facing custom-instruction files are adapters that must defer to this
framework's canonical authority.

This document is not a trade promise. The system is profit-focused, risk-controlled,
and positive-expectancy seeking as a research and decision-support platform. The
product does not guarantee profit, promise risk-free returns, or assure continuous profits.

## 1. Identity and Mission

AI4BINANCE Core vNext is an ontology-driven, policy-as-code, traceable, and self-auditing governance framework for Binance Spot/Futures,
using evidence-based, event-driven, multi-agent, and multi-timeframe market
intelligence. It does not leave final trading decisions to LLMs or agents; it
produces decisions through deterministic Decision Core, Risk Engine, and
Governance Enforcement as an algorithmic trading research, decision-support, and
paper-trading platform.

Core principle:

```text
DATA creates observations.
EVIDENCE supports claims.
AGENTS analyze.
STRATEGIES identify setups.
SCORING ranks opportunities.
GOVERNANCE decides eligibility.
RISK constrains exposure.
EXECUTION obeys.
AUDIT preserves lineage.
HUMAN retains authority.
LEARNING proposes.
VALIDATION promotes.
```

Security axiom:

```text
UNKNOWN
INCONSISTENT
UNVALIDATED
UNAUTHORIZED
STALE
UNSAFE
  -> NO_TRADE
```

## 2. Digital Company Operating Model

AI4BINANCE operates like a disciplined, audited, and transparent digital company.
The purpose is decision quality that prioritizes capital protection and improves
through validation. Profit focus is interpreted with OOS proof, risk budget,
drawdown control, and human approval.

Profitability language:

```text
positive_expectancy_target = allowed
profit_guarantee = prohibited
continuous_profit_claim = prohibited
```

Authority pyramid:

```text
Human Owner / Board
  -> Governance Office
  -> Policy-as-Code + Approved Operating Envelope
  -> Governance Registry Family
  -> Data, Evidence, Capability and Validation Owners
  -> Agents, Strategies and Research Units
  -> Deterministic Core + Risk Engine
  -> Execution Gates
  -> Audit, Assurance and Learning
```

Roles:

- Human Owner: live authority, approval, and capital responsibility.
- Governance Office: policy, governed registry, release, and exception management.
- Risk Owner: risk policy, exposure limit, and blocker ownership.
- Validation Owner: backtest, WF, OOS, robustness, and regime evidence.
- Data Steward: data source, dataset, freshness, and quality ownership.
- Capability Owner: formula, oracle, tests, evidence and promotion status.
- Agent Owner: agent contract, permissions, observations and lifecycle.
- Security Owner: secrets, RBAC, supply chain and incident response.
- Audit Owner: lineage, evidence, gate result and assurance records.

Typed contract:

```text
AI4BINANCE_DIGITAL_COMPANY_OPERATING_MODEL
  -> GovernancePyramidLayer[]
  -> LoopsSelfImprovementContract
  -> WebIntelligenceRadarContract
  -> execution_allowed=false
  -> live_eligibility_status=LIVE_ORDER_BLOCKED
```

Execution-surface authority split:

```text
BINANCE_MARKET
  -> HUMAN_HAND_MANUAL_ONLY
  -> human confirmation required
  -> autonomous simulation prohibited
  -> live_eligibility_status=LIVE_ORDER_BLOCKED

VIRTUAL_MARKET
  -> BOUNDED_AUTONOMOUS_SIMULATION
  -> bounded autonomous simulation allowed inside the governed envelope
  -> no live authorization
  -> live_eligibility_status=LIVE_ORDER_BLOCKED
```

Canonical governance-pyramid layers:

```text
01_HUMAN_BOARD
02_GOVERNANCE_OFFICE
03_POLICY_AS_CODE
04_GOVERNANCE_REGISTRY
05_DATA_EVIDENCE_CAPABILITY
06_INTELLIGENCE_AGENTS_STRATEGIES
07_DETERMINISTIC_DECISION_RISK
08_EXECUTION_GATES
09_AUDIT_ASSURANCE_LEARNING
```

## 3. Core Constitution

- `CAPITAL_PROTECTION > TRADE_FREQUENCY`
- `NO_EVIDENCE -> NO_TRUST`
- `NO_VALIDATION -> NO_PROMOTION`
- `NO_APPROVAL -> NO_EXECUTION`
- `HARD_BLOCKER -> NO_TRADE`
- `UNKNOWN_CRITICAL_STATE -> DENY`
- `AGENT != FINAL_DECISION_AUTHORITY`
- `LLM != RISK_AUTHORITY`
- `LLM != EXECUTION_AUTHORITY`
- `LEARNING != DEPLOYMENT`
- `RAW_DATA != FEATURE != OBSERVATION != EVIDENCE != DECISION`
- `STATE != MEMORY != KNOWLEDGE != EVIDENCE != LEARNING`
- `WALLET_STATE MUST NOT contaminate historical backtests`
- `ONE AGENT MUST NOT create its own canonical market truth`
- `NO DIRECT AGENT -> LIVE_ORDER PATH`
- `EVERY DECISION MUST HAVE LINEAGE`
- `EVERY BEHAVIOR-CHANGING COMPONENT MUST BE VERSIONED`
- `EVERY GOVERNED COMPONENT MUST HAVE OWNERSHIP`
- `HARD GATES REQUIRE STABLE OOS EVIDENCE`
- `MISSING EVIDENCE IS UNKNOWN, NEVER ASSUMED`
- `SOCIAL CLAIM ALONE CANNOT AUTHORIZE A TRADE`
- `LOOKAHEAD/REPAINTING RESEARCH CANNOT BECOME TRADING LOGIC`
- `UNKNOWN SOFTWARE LICENSE -> NO_CODE_REUSE`
- `FAIL_SAFE > FAIL_OPEN`
- `LIVE IS OPT-IN; PAPER/MANUAL IS DEFAULT`
- `BINANCE_MARKET -> HUMAN_HAND_MANUAL_ONLY`
- `VIRTUAL_MARKET -> BOUNDED_AUTONOMOUS_SIMULATION`
- `RUNTIME/ GROUPS MUTABLE, GENERATED, REPRODUCIBLE, AND EXECUTION/RUN-PRODUCED OUTPUTS`
- `IF DELETING A FILE WOULD MAKE THE REPOSITORY UNDEFINED, IT DOES NOT BELONG UNDER RUNTIME/`

### 3.1 Constitutional Change Control

Code operates inside the constitutional boundary. Code must not move the system
outside the constitution or change that boundary unilaterally.

Deterministic authority is split into three non-overlapping primitives:

1. `DETERMINISTIC_QUALITY_GATE = TECHNICAL_TRUTH`.
2. `DETERMINISTIC_GOVERNANCE_GATE = POLICY_ELIGIBILITY`.
3. `HUMAN_GOVERNANCE = CONSEQUENTIAL_AUTHORITY`.

Risk-tiered human governance applies only when the proven change is
consequential:

1. `C0_NON_BEHAVIORAL`: formatting, comments, generated documentation. No
   human governance gate.
2. `C1_LOW_RISK`: internal refactor and test-only changes. Normal review, but
   no consequential authority decision.
3. `C2_BEHAVIORAL`: behavior-changing logic within approved policy boundaries.
   An `Approval Packet` and explicit human approval are required.
4. `C3_GOVERNED`: policy, constitution, validation, repository governance, or
   risk-control changes. Double approval and same-diff constitution sync are
   required.
5. `C4_CONSEQUENTIAL`: live execution, credentials, risk-limit changes,
   promotion authority, or other high-impact changes. Explicit high-assurance
   approval is required.

The `Approval Packet` must bind approval to the exact reviewed scope and
surface at least: `change_id`, `change_class`, `scope_hash`,
`affected_authority_surfaces`, `behavioral_impact`, `risk_impact`,
`DQG_result`, `evidence_hash`, `DGG_result`, `reason_codes`, `blockers`,
`rollback_plan`, `live_eligibility`, and `approval_expiry`. The approval
artifact must also bind `authority_family_sha256` for the reviewed authority
surface, `lifecycle_definition_sha256` for the active lifecycle/authority
primitive surface, and an optional `revoked_at_utc` invalidation timestamp.

The canonical lifecycle and authority primitive surface is
`src/ai4binance/governance_primitives.py`. Approval loader fallback for the
current scope/evidence envelope is `runtime/artifacts/quality/gate/approval_record_latest.json`,
and `src/ai4binance/governance/gate.py` must consume that first-class artifact
without weakening fail-closed approval rules or falling back to lower-authority
defaults.

`approval_verification` is not an informational check. It is a hard veto over
consequential transitions. For `C2_BEHAVIORAL`, `C3_GOVERNED`, and
`C4_CONSEQUENTIAL` changes, the approval decision must bind to the same
first-class lifecycle primitive as quality evidence and governance eligibility.
If approval does not exist, is unauthorized, is expired, or does not match the
current `scope_hash`, `evidence_hash`, `DQG_result`, `DGG_result`, lifecycle
definition hash, or authority surfaces, then `APPROVAL_VERIFICATION=FAIL`,
`RUNNING_WITH_BLOCKERS`, `consequential_change_allowed=false`, and
`LIVE_ORDER_BLOCKED` must remain in effect. A revoked approval record is also
invalid.

Synchronization targets for governed or consequential changes remain:
`policy`, `instructions`, `schema`, `entity_rules`, `relationship_rules`,
`output_format`, `framework_docs`. The code change must not conflict with the
written constitution. If a conflict exists, the change is not accepted as
complete.

Locked rule:

```text
Code runs within the constitution.
DETERMINISTIC_QUALITY_GATE = TECHNICAL_TRUTH.
DETERMINISTIC_GOVERNANCE_GATE = POLICY_ELIGIBILITY.
HUMAN_GOVERNANCE = CONSEQUENTIAL_AUTHORITY.
Risk-tiered human governance applies only when the proven change is consequential.
Only C3 changes require double approval.
Only C4 changes require high-assurance approval.
Approval Packet approval binds to scope_hash.
Code/constitution divergence is prohibited.
```


#### 3.1.0 Bounded Owner Amendment and Reconciliation Recognition

initial_owner_amendment_contract=InitialOwnerAmendment/v1

Within local research/paper scope only, a genuine exact-subject constitutive
decision by Huseyin Cicek may establish the initial single-owner rule. The
decision expressly departs from the project-authored two-human C3 default; it
does not assert that the old requirement was satisfied. A real decision from
the human owner, its exact approved baseline, patch and outputs, one principal,
time-bound and revocable scope, and genuine custody evidence are required.
The initial contract must bind individually reviewed protected bytes, passing
technical and policy controls, completed inactive installation, and separately
bound initial activation. It cannot be created by a candidate test result.
The genuine owner-issued founding directive replaces the project-authored
founding procedure only for the reviewed V6 local research/paper transition.
It admits the corresponding InitialOwnerAmendment/v1 implementation contract
as an explicit normative replacement; legacy double C3 approval is not
reported as satisfied. The original directive is preserved at
runtime/artifacts/governance/sole-owner/founding-migration-20261005/owner-directive.txt
with SHA-256 614eac078448d874bc74e7276936e31c95ca7c97ad0ae301231f5fcea0604be3.
The reviewed subject is AI4B-V6-INITIAL-REVIEW-C749BB7F568E47E1.
Mechanical rebinding to actual phase baselines is permitted without semantic
expansion. Recognition does not complete installation, satisfy failed gates,
or activate the governance model. Inactive adoption and separate activation
remain bound to genuine source, approved bytes, accepted anchors and actual
passing canonical evidence.
External constraints, risk and validation vetoes remain binding. Live orders,
deployment, credentials, infrastructure, risk overrides, promotion, and C4
effects are excluded. Later C3 operations remain under their preceding accepted
policy. Missing originals and historical approvals are not reconstructed.

The subsequent explicit owner directive preserved at
runtime/artifacts/maintenance_archive/d0_baseline_reconciliation_20261005/normative-reconciliation-owner-directive.txt
with SHA-256 1d4cb7deb7d9e08044c0db636620b490a62ea1fe3be397021055e7ec107daae2
is a separate bounded normative amendment,
not a renewal or semantic rebinding of the V6 decision. It admits the current
six-document reconciliation and only its directly necessary Core and hierarchy
corrections through the existing DocumentLockReview/v2, DocumentLockAdoption/v1,
WrittenOwnerDocumentLockGrant/v1, and DocumentLockAuthorityContext contracts.
This exact owner-directed transition departs from the project-authored double
C3 default without claiming two independent human approvals. Capture its actual
baseline, reviewed patch and final outputs, one owner principal, genuine source,
custody, bounded validity, revocation snapshot, and procedure pins. Preserve
valid pre-existing approvals for bytes already committed at that baseline;
they do not approve amended bytes. New bytes require the fresh exact grant.

The reconciliation scope is GEMINI.md, instruction_core_custom_instructions.md,
policy_organization_constitution_handbook.md, policy_manifest_governance.md,
policy_organization_foundation_operating_model.md, and
policy_organization_incident_change_appendices.md at their canonical paths,
plus this Core correction. Register only individually reviewed final raw bytes.
The owner-approved hierarchy is External Mandatory Constraints -> Core
Constitution -> Governance/Compliance -> Canonical Contracts -> Repository
Instructions -> subordinate implementation surfaces. The handbook is a family
index/projection and cannot supersede Core. Unknown history remains unresolved.

This admits no future amendment, permanent sole-owner activation, trading,
deployment, promotion, or risk override. Complete the actual local registration
and restore manifest protection before recording an installation receipt.
Passing unchanged canonical technical and policy checks is required for
acceptance; recognition, registered bytes, installed consumers, quality, and
activation remain separate facts. Other C3 operations retain the preceding
accepted policy. Risk and Validation vetoes and LIVE_ORDER_BLOCKED remain hard.

#### 3.1.1 Governed Document Update Lifecycle

document_update_contract=WrittenOwnerDocumentLockUpdate/v1

DocumentLockAuthorityContext/v4 separates a completed historical installation
from a separately reviewed document update. This implementation procedure does
not replace the classification, Approval Packet, double C3 approval, high-
assurance C4 approval or exact-subject requirements in section 3.1.
A written owner decision may authorize only the bounded candidate application.
It does not establish policy eligibility, final acceptance or execution authority.

Each update requires a fresh genuine owner-issued application decision over the
canonical SHA-256 review subject, exact patch, original and replacement document
bytes, registration projection, procedure payloads, evidence and rollback.
One application is permitted within at most 24 hours. Draft, wrong-subject,
expired-at-application, revoked or unsupported records cannot authorize work.
Preserve authority metadata, inventory, historical approval records and all
Risk, Validation, security and live-execution vetoes. Registration changes are
limited to the individually reviewed document versions and raw-byte hashes.

The first successor must verify its completed v3 predecessor against its actual
accepted Git installation, including original procedure and evidence pins.
Later successors must verify the complete immutable predecessor chain.
Historical bytes never approve changed current bytes. A completed update remains
evidence of its bounded installation after the application window ends; fresh
work requires a fresh exact decision. Reject missing, inconsistent or cyclic
predecessors and inspect at most 32 successor records.

Current manifest, documents and procedure must match the latest reviewed,
owner-permitted completed candidate installation. Record actual application time,
one application and restored protections separately. Restore read-only and ACL
write protection on success, and original bytes and protections on failure.
Installation receipts are not final candidate approval. Canonical FULL, the
applicable C3/C4 human approval requirements and policy eligibility remain
separate mandatory acceptance controls. No sole-person governance exception,
independent human review or historical approval repair is created by this rule.
This procedure cannot authorize trading, signing changes, credentials, risk
overrides, promotion, deployment, Git publication or live execution.

Legacy instruction modernization:

```text
Historically grown Markdown instruction files may be fully rewritten when they
carry stale decision language, duplicate authority, output-contract drift or
governance ambiguity. Rewrite is allowed only to restore canonical Core vNext
discipline; it must update policy/instructions/schema/rules/output docs,
compliance evidence and governance tests in the same bounded diff.
```

Cleanup audit registry evidence rule:

```text
Every KEEP or ENTRY_POINT cleanup-audit registry entry must carry explicit
evidence references for source, test, compliance matrix and core doc whenever
the file is governed. A source file without that chain remains owner-review
work, not an invisible safe component.
```

Transparent evidence rule:

```text
code
+ markdown constitution
+ governance contract tests
+ full quality_gate evidence
+ TECHNICAL_QUALITY_PASS evidence
+ FULL_ASSURANCE_GREEN evidence
  -> required before COMPLETE
```

Coverage and pass counts must come from the full quality gate evidence, not from
memory, stale README text or optimistic estimates.

Canonical governance decision anchor:

```text
Docs are authority.
Validator is enforcement.
Quality gate is evidence.
Human governance is consequential authority.
Runtime is not source-of-truth.
LLM is not authority.
Scores cannot hide blockers.
LIVE remains blocked.
```

Wide-scope audit rule:

```text
When the user says "keep the editing scope broad", use the machine's available
local CPU/RAM/GPU capacity through existing safe tooling, broad tests and
parallel read-only analysis where practical. The audit must aggressively search
for loose code, stale rules, missing tests, missing compliance evidence,
coverage drift, hidden authority and fail-open paths. It must report realistic
findings and the honest cover rate from the full quality gate.
```

Constitution family mismatch visibility rule:

```text
Any mismatch across core, Custom Instructions, Codex and compliance matrix is a
contract finding, not editorial drift. The governance contract test must surface
the exact document and missing canonical fragment before COMPLETE is allowed.
```

Loose changed source rule:

```text
A changed source file without visible source, test, written-rule and compliance
evidence is loose code. Loose code must be reported as RUNNING_WITH_BLOCKERS and
must not be hidden behind a green unit test or broad coverage number.
```

Capability OOS/operational evidence gap rule:

```text
Capability OOS/operational evidence gaps remain visible until artifact-level OOS,
walk-forward, regime, paper/operational, owner and promotion evidence exists.
Contract-ready code, schemas or agents do not close those gaps by themselves.
```

Repository governance enforcement rule:

```text
Repository layout is governed infrastructure, not a one-off Codex cleanup task.
Folder and file structure must be continuously enforced through RepositoryPolicy,
RepositoryArtifact schema and deterministic repository_validator. Unknown paths,
unsafe names, source/runtime mixing, generated artifacts under src and
unapproved absolute paths remain visible findings until policy, schema, tests
and quality_gate evidence agree.
```

Documentation and knowledge governance rule:

```text
Critical system knowledge is governed infrastructure, not free-form Markdown.
Active governance standards must carry GovernedKnowledgeObject metadata with
identity, version, owner, authority_level, content_role, lifecycle status and
source_of_truth. AI4B-GOV-DKG-001 is enforced through RepositoryPolicy,
RepositoryArtifact schema and deterministic repository_validator inside the full
quality gate. Missing or invalid knowledge metadata is RUNNING_WITH_BLOCKERS and
cannot be hidden behind prose quality, green focused tests or manual cleanup.
Duplicate active source-of-truth concepts are governance blockers until one
authoritative object is explicitly retained, superseded or demoted.
Governed repository/file standards and machine governance contracts are locked
to professional English (`en-US`); language drift in those controlled surfaces
is NON_CODE_CONTENT_LANGUAGE_VIOLATION.
```

Typed contract:

```text
ConstitutionalChangeControl
  -> code_runs_within_constitution=true
  -> quality_gate_role=TECHNICAL_TRUTH
  -> governance_gate_role=POLICY_ELIGIBILITY
  -> human_governance_role=CONSEQUENTIAL_AUTHORITY
  -> risk_tiered_human_governance=true
  -> change_classes=C0,C1,C2,C3,C4
  -> change_classes_without_human_governance=C0,C1
  -> approval_packet_required_change_classes=C2,C3,C4
  -> constitution_sync_change_classes=C3,C4
  -> double_approval_change_classes=C3
  -> high_assurance_change_classes=C4
  -> constitution_sync_required=true
  -> code_constitution_divergence_allowed=false
  -> live_eligibility_status=LIVE_ORDER_BLOCKED
```

#### 3.1.2 Bounded Owner Acceptance for the Canonical Git Rule Package

bounded_owner_acceptance_contract=AI4B-GOV-C3-OWNER-20261007

Only the current canonical Git rule package and its directly necessary acceptance
amendment may use one genuine human owner decision in local research/paper scope.
This prospective normative amendment expressly departs from the project-authored
two-human C3 default for this package. It never reports that two independent
humans reviewed or approved it. Other C3 changes retain section 3.1 unchanged;
C4, live execution, credentials, deployment, promotion and risk overrides remain
outside this recognition. The owner is Huseyin Cicek, represented by the existing
Huseyin / GovernanceOwner / huseyin-governance-owner-principal identity. No new
person, role appointment, identity verification or independent review is created.

The original package is the exact committed change from
51aa502297903c52f98d58e63f6c916b43bce433 to
f3d81cb6bb57f9fe6e69661f1ddbbcf4db4d5901. The non-authoritative
bounded_owner_acceptance fabric projection must bind that original patch, this
Core raw-byte hash, the canonical root, the finite allowed change paths and the
complete individually reviewed output inventory. Each output must match the
immutable evidence sealed by the new WrittenOwnerDocumentLockUpdate/v1 review.
Only the replacement of Core 2.0.11 raw SHA-256
7147a031c7774e03def1a232030c70af32f110af83898b4f04f43b4c9e8d7e08
with reviewed Core 2.0.12 at the exact package commit baseline is recognized.
Later successor updates cannot reuse this recognition.
The derived protected manifest remains subject to its existing exact transition
verifier. Missing, changed, expired, revoked or inconsistent input fails closed.

Recognition requires a separately genuine OWNER_ISSUED normative decision over
the exact reviewed amendment, bound to the same source and subject as its actual
completed DocumentLockAuthorityContext/v4 update. The normative record must
expressly state departure_from_legacy_c3=true, natural_person_count=1 and
independent_human_review=false. An application receipt alone cannot supply it.
Its validity is at most 24 hours and cannot outlive the application decision.
Preparation, a draft, a test fixture or an agent-written assertion cannot activate
this recognition. Preserve the immutable predecessor chain and all protections.

The existing governance gate remains the sole acceptance consumer. Only an
eligible C3 package may require one exact current GovernanceOwner approval.
Subject, scope, quality, governance, authority, lifecycle, expiry, revocation,
identity and all deterministic vetoes remain mandatory. Final acceptance requires
fresh canonical FULL evidence and an actual current-scope owner decision; old
approval records do not approve changed subjects or hashes. Record the profile as
BOUNDED_OWNER_PACKAGE and independent_human_review=false. File installation,
normative recognition, final acceptance and Git baseline are separate facts.

The existing closure request and approval replay must consume this exact profile
without soliciting a fictional second principal. Git publication still requires
its independent explicit authorization; section 3.2 remains unchanged. No future
amendment, general single-owner model, historical approval repair, trading,
promotion, deployment or live-risk permission is established. Keep RESEARCH_ONLY,
execution_allowed=false and LIVE_ORDER_BLOCKED.

### 3.2 Repository Completion Invariant

Rule ID: `AI4B-GOV-GIT-001`.

This normative rule belongs to `L1_CORE_CONSTITUTION`, subordinate to external
mandatory constraints. The steady state is `VERIFIED_BASELINE`: exactly one
registered Git worktree at the verified canonical repository root, HEAD attached
to `main`, exactly one local branch (`refs/heads/main`), exactly one branch on the
verified canonical remote (`refs/heads/main`), and identical full commit SHAs for
HEAD, local main and live remote main. The index and working tree must be clean,
including no untracked non-ignored files. Canonical ignore rules apply; changing
them to conceal work or a violation is prohibited.

Local branches are `refs/heads/*`; remote branches are the current `refs/heads/*`
advertised by the canonical remote. Tags are outside branch cardinality.
Worktrees are all registered worktrees in this repository's common Git directory.
Remote-tracking refs are cached evidence and neither required equality inputs nor
proof of current remote truth. Resolve the canonical remote from the approved
identity projection and actual fetch/push configuration, never from its alias.

`CHANGE_IN_PROGRESS` records an already authorized bounded task through the
existing task/status evidence mechanism. Editing, testing, validation and
authorized recovery may make the worktree dirty. An independently explicitly
authorized commit/publication sequence may temporarily separate local and remote
SHAs. This state grants no new permission and cannot be reported as a clean,
synchronized baseline. No additional branch, registered worktree or alternate
checkout is permitted, including during an authorized task.

Task preflight and quality checks preserve necessary authorized editing and
testing; independent unsafe or unauthorized actions remain blocked. Commit/push
preparation must not require remote SHA equality before authorized publication.
Final completion and baseline declarations require fresh equality afterward.
Do not declare COMPLETE, release readiness or VERIFIED_BASELINE while any
invariant is violated or unverified. Required quality, governance,
protected-document and human acceptance controls remain independently binding.

Lower-authority instructions, providers, scoped instructions, scripts,
configuration and execution workflows cannot waive or redefine this rule.
Future change requires an explicitly owner-authorized canonical amendment
under section 3.1; it never grants an exception through a lower-level adapter.
Missing or inaccessible live remote evidence is NOT_VERIFIED and blocks closure.
Detached or shallow CI checkouts may validate declared remote/ref evidence only;
they cannot prove workstation worktree cardinality, attachment or cleanliness.

Operational enforcement belongs to the existing Manifest Governance policy and
its pinned fabric projection. Reuse the shared
`ai4binance.ops.quality_gate.repository_completion` checker at task preflight,
controlled creation, quality/repository validation, Git publication preparation,
CI and final Stop/completion boundaries. Evaluate independent observations and
preserve every violation; never silently remediate them.

Instructions and client hooks cannot prevent every direct Git command or another
clone from creating remote branches. Inspect provider protections read-only;
unavailable or unverified prevention remains an explicit limitation. Detection
must block false completion/baseline claims. External settings require separate
authorization. Current extra branches/worktrees require a preservation inventory
and separately authorized remediation; this rule grants no deletion, discard,
commit, push, deployment or history-rewrite authority.

Preserve PAPER_TRADING, MANUAL_CONFIRMATION, LIVE_EXECUTION_DISABLED, READ_ONLY_API,
RESEARCH_ONLY and LIVE_ORDER_BLOCKED.

## 4. Canonical Cycle

```text
ONE CYCLE
-> ONE CANONICAL SNAPSHOT
-> ONE SHARED STATE
-> MANY BOUNDED OBSERVATIONS
-> ONE DETERMINISTIC DECISION
-> ONE RISK ASSESSMENT
-> ONE GOVERNANCE RESULT
-> ZERO OR ONE EXECUTION PLAN
-> ONE AUDIT TRAIL
```

All agents use the same `snapshot_id` inside the same `cycle_id`. Agents must
not create their own canonical market-truth source.

## 5. Canonical Domains

AI4BINANCE Core vNext is modeled with 19 canonical domains, including
`00_META`:

```text
00_META
01_REGISTRIES
02_MARKET_DATA
03_SHARED_MARKET_STATE
04_INTELLIGENCE
05_DETERMINISTIC_ANALYTICS
06_AGENT_OBSERVATIONS
07_DECISION
08_RISK
09_PORTFOLIO
10_EXECUTION
11_VALIDATION
12_LEARNING
13_GOVERNANCE
14_EVIDENCE
15_AUDIT_OBSERVABILITY
16_SECURITY
17_EVENT_FABRIC
18_RESEARCH_CAPABILITY
```

Physical layout:

- Control & Assurance Plane
- Data & Evidence Plane
- Intelligence Plane
- Decision & Execution Plane
- Orchestration + Event Fabric

## 6. Governance Registry Family

All governed components are linked to one governance registry family:

```text
GovernanceRegistry
  -> AgentRegistry
  -> CapabilityRegistry
  -> SkillRegistry
  -> ToolRegistry
  -> ModelRegistry
  -> PromptRegistry
  -> StrategyRegistry
  -> IndicatorRegistry
  -> PatternRegistry
  -> ParameterRegistry
  -> WorkflowRegistry
  -> DataSourceRegistry
  -> DatasetRegistry
  -> FeatureRegistry
  -> RiskRuleRegistry
  -> ControlRegistry
  -> PolicyRegistry
  -> RequirementRegistry
  -> ResearchUnitRegistry
  -> OracleRegistry
  -> FormulaRegistry
  -> ValidationProfileRegistry
```

Priority order:

```text
Capability Inventory
-> Capability Coverage Matrix
-> Formula/Oracle Contracts
-> OOS Evidence
-> Governance Registry Mapping
-> Decision Contribution
```

## 7. Capability-First Governance

Agent's OOS validation is not sufficient. Trading-impacting actions
capabilities must have the following chain:

```text
Capability
  MUST_HAVE Formula
  MUST_HAVE Oracle
  MUST_HAVE ValidationProfile
  MUST_HAVE OOS Evidence
  MUST_HAVE Regime Evidence
  MUST_HAVE Owner
  MUST_HAVE Lifecycle Status
```

Capability contract:

```yaml
Capability:
  capability_id: required
  version: required
  family: required
  role: required
  implementation:
    formula_id: required
    oracle_id: required
  allowed_timeframes: []
  supported_markets: []
  inputs: []
  outputs: []
  score_contribution:
    level: low | medium | high
    weight_ref: required
  hard_gate:
    eligible: true | false | conditional
    promoted: false
  known_failure_modes: []
  repainting:
    allowed: false
  lookahead:
    allowed: false
  validation:
    validation_profile_id: required
    IS_status: UNKNOWN
    WF_status: UNKNOWN
    OOS_status: UNKNOWN
    regime_status: {}
  lifecycle_status: required
```

Capability Coverage Matrix is maintained in machine-readable form:

```yaml
coverage:
  formula: PASS
  oracle: PASS
  unit_tests: PASS
  regression: PASS
  walk_forward: PASS
  oos: MISSING
  regime_validation: PARTIAL
  evidence_complete: false
  promotion_eligible: false
```

`MISSING` hicbir zaman `PASS` varsayilmaz.

Initial canonical capability set:

```text
SWING_HIGH_LOW
BOS
CHoCH
BREAKOUT
FAILED_BREAKOUT
STRUCTURE_SHIFT
```

## 8. Market Data Authority

Canonical raw market universe:

```text
OHLCV
Ticker
Trades
AggTrades
OrderBookSnapshot
OrderBookDelta
Spread
Liquidity
ExchangeInfo
SymbolFilters
MarketStatus
Funding
OpenInterest
LongShortRatio
TopTraderRatio
TakerFlow
ServerTime
```

In Spot decisions, `Funding`, `OpenInterest`, `LongShortRatio`,
`TopTraderRatio` and `TakerFlow` remain supplementary/advisory. Spot price,
liquidity, filters, wallet/inventory, and risk are decision-authority inputs.

Raw market data is immutable and append-only; normalization does not overwrite
the raw record.

## 9. Agent Observation Contract

The agent does not produce the final signal or trade decision. It only produces bounded
observation/assessment is generated.

```python
class AgentObservation:
    observation_id: str
    agent_id: str
    agent_version: str
    cycle_id: str
    snapshot_id: str
    symbol: str
    timeframe: str
    capability_ids: list[str]
    assessment: str
    confidence: float
    uncertainty: float
    evidence_ids: list[str]
    conflicting_evidence_ids: list[str]
    blockers: list[str]
    data_quality_score: float
    execution_authority: Literal["NONE"]
```

Agent permission rule:

```text
Agent -> Capability -> Permission -> Tool
```

For the LLM-based agent, `OrderGateway = NOT_EXPOSED`.

## 10. Decision Pipeline

The Decision Core follows this fixed sequence:

```text
1 DATA READINESS
2 HARD BLOCKER CHECK
3 EVIDENCE COMPLETENESS
4 CAPABILITY ELIGIBILITY
5 SETUP QUALIFICATION
6 DETERMINISTIC 100-POINT SCORE
7 ACTION CEILING
8 RISK ASSESSMENT
9 GOVERNANCE ELIGIBILITY
10 TRADE PLAN
11 EXECUTION GATE
```

A high score cannot bypass a hard blocker or governance maturity. The first
question must always be `WHY NOT TO TRADE?`.

Hard blockers and soft penalties are separate canonical control concerns.
`HardBlocker` belongs to the eligibility/veto channel and forces a non-eligible
decision while active. `SoftPenalty` belongs to the bounded score/ranking
channel and cannot create, clear, downgrade, resolve or offset a hard blocker.
Any unknown trading-sensitive control classification fails closed until the
declared control authority resolves it with evidence.

Action semantics:

- `BUY`: validated Spot buy candidate, gates and risk permitting.
- `SELL`: existing Spot inventory reduction only; no naked short in Spot.
- `HOLD`: existing inventory is maintained.
- `WAIT`: setup potential exists but trigger/gate is incomplete.
- `NO_TRADE`: hard blocker, eligibility failure or insufficient edge.

## 11. Risk, Portfolio and Execution

`DeterministicCore` produces a `DecisionCandidate`, not a final
`TradeDecision`. Risk, validation, blockers, action ceilings, and Decision
Governance constrain the candidate before a final `TradeDecision` exists.

Risk remains a separate domain; it is not embedded into `TradeDecision`.

Prohibitions:

- martingale
- uncontrolled averaging down
- automatic risk increase
- risk-limit self-modification

Historical backtests must not consume the current `PortfolioState`.

Defaults:

```yaml
trading.mode: paper
execution.order_mode: manual
execution.allow_auto_live_orders: false
```

Live mode requires an explicit user request and all technical, validation, risk,
governance, and execution gates. A single failure returns:

```text
LIVE_ORDER_BLOCKED
```

Current route:

```text
AgentObservation
-> DeterministicCore
-> RiskAssessment
-> Validation
-> DecisionGovernance
-> ExecutionGate
-> Execution
```

Forbidden route:

```text
Agent -> executes -> LiveOrder
```

### 11.1 MCP Gateway Rule

Agents are not granted unrestricted access through MCP or tool names.
Current MCP route:

```text
Agent
-> Tool Policy
-> Authorization
-> MCP Gateway
-> Tool
```

AI4BINANCE MCP Gateway canonical surfaces:

```text
Filesystem MCP
GitHub MCP
PostgreSQL MCP
Research MCP
Wolfram MCP
Quant Research MCP
Canonical Market Data MCP
Evidence MCP
Governance MCP
future Binance READ-ONLY adapter
```

Example policy:

```yaml
tool_policy:
  agent: research_agent
  allowed:
    - github.search
    - filesystem.read
  denied:
    - filesystem.delete
    - shell.admin
    - exchange.place_order
```

`McpGatewayContract` rejects agent shortcuts. `github.search` or
Permissions such as `filesystem.read` are only read/research invocation permissions; final
decision, risk, promotion, parameter, or order authority is not generated.

Quantitative MCP surfaces, including Wolfram-backed or internal Quant Research
MCP tools, are cold-path research verification surfaces. They may support
formula checks, statistical diagnostics, uncertainty review, and experiment
evidence packaging. They must not participate in live market hot-path decision
logic, cannot authorize paper execution, cannot authorize live execution, cannot
modify parameters or risk limits, and cannot promote an algorithm or strategy.
External Wolfram MCP provider invocation requires explicit registration,
endpoint configuration, credential configuration, and operator approval. Missing
registration remains a blocker and must not be silently replaced by an LLM
opinion.

MCP fabric authority classes:

```text
MCP_R0_READ_ONLY
MCP_R1_ANALYZE_COMPUTE
MCP_R2_CREATE_RESEARCH_ARTIFACTS
MCP_R3_CONTROLLED_STATE_MUTATION
MCP_X_EXECUTION_SENSITIVE
```

`MCP_X_EXECUTION_SENSITIVE` tools are blocked. The following tool classes must
not be allowlisted: `risk.override`, `governance.override`,
`strategy.promote`, `parameter.promote`, `kill_switch.disable`, `live.enable`,
`order.live.submit`, `credential.read`, and `secret.export`.

## 12. Validation and Research Capability

Validation works capability-first:

```text
formula
-> oracle
-> tests
-> backtest
-> walk-forward
-> OOS
-> regime evidence
-> promotion
```

Research lifecycle:

```text
RadarFinding
-> ResearchUnit
-> CapabilityCandidate
-> POC
-> Validation
-> PromotionGovernance
-> Governance Registry Entry
```

Unknown license returns `NO_CODE_REUSE`. If lookahead or repainting is detected,
`trading_eligible=false`. POC success does not generate automatic production promotion.

Controlled Auto-Learn can only observe, classify, propose, rank and stage
candidates. It has no authority to deploy, promote, change risk limits, enable live
mode, or disable gates.

Algorithm discovery outputs start as `RESEARCH_CANDIDATE` artifacts. Novelty,
mathematical consistency, statistical plausibility, backtest performance,
out-of-sample evidence, robustness, tradability, paper eligibility, and live
eligibility are separate gates. No single gate can imply the next gate.

### 12.1 LOOPS Self-Improvement Cycle

Technology self-improvement is governed by the LOOPS cycle. LOOPS is not
autonomous deployment; it is a controlled research and validation intake
mechanism.

```text
L - LISTEN
    Outcome, ClosureReview, and AuditEvent are observed.

O - OBSERVE
    Web Intelligence Radar collects public technology, risk, and governance
    evidence.

O - ORIENT
    RadarFinding and EvidencePack are converted into Hypothesis,
    LearningCandidate, and GovernanceIntake objects.

P - PROVE
    ResearchUnit and CapabilityCandidate are proven with Formula, Oracle, Test,
    WF, OOS, robustness, and regime evidence.

S - STAGE
    PromotionReview result for RegistryComponent must be human-approved and rollback-ready
    staged release is created or the candidate is rejected.
```

Typed contract:

```text
AI4BINANCE_LOOPS_SELF_IMPROVEMENT_CONTRACT
  -> L_LISTEN_OUTCOMES
  -> O_OBSERVE_WEB_INTELLIGENCE
  -> O_ORIENT_HYPOTHESES
  -> P_PROVE_WITH_VALIDATION
  -> S_STAGE_GOVERNED_CANDIDATES
```

LOOPS cannot:

```text
DEPLOY
SELF_PROMOTE
MODIFY_LIVE_PARAMETER
MODIFY_RISK_LIMIT
DISABLE_GATE
ENABLE_LIVE
EXECUTE_ORDER
```

### 12.2 Web Intelligence Radar

Web Intelligence Radar scans public technology evidence and risk signals that can improve the system
findings. The credentialless default remains active; if the provider/API is unavailable
`DATA_UNAVAILABLE` or `LOW_CONFIDENCE` is generated. Radar results are never trade
authorization.

Canonical source families:

```text
News
GitHub
arxiv.org
cve.org
Security
Regulatory
ExchangeAnnouncements
ProjectOfficialSources
Research
```

Pipeline:

```text
PublicSource
-> SourceValidation
-> Claim/Event Extraction
-> EvidenceScoring
-> EvidencePack
-> CapabilityGap
-> ResearchUnit
-> ValidationPlan
-> GovernanceIntake
-> AuditEvent
```

Typed contract:

```text
AI4BINANCE_WEB_INTELLIGENCE_RADAR_CONTRACT
  -> decision_authority=ADVISORY_ONLY
  -> credentialless_default=true
  -> execution_allowed=false
  -> live_eligibility_status=LIVE_ORDER_BLOCKED
```

## 13. Evidence Fabric

Evidence is append-only. New validation does not modify old evidence; new
event/evidence is generated.

Canonical evidence objects:

```text
Source
Observation
Claim
Evidence
Contradiction
EvidencePack
Provenance
```

Evidence status:

```text
VERIFIED
PARTIALLY_VERIFIED
UNVERIFIED
CONFLICTED
```

Evidence Completeness is a separate gate. Missing evidence remains `UNKNOWN` and
is not predicted.

## 14. Entity Rules

- `ER-001 Identity`: every persistent entity carries a globally unique `entity_id`.
- `ER-002 Versioning`: every component that affects trading behavior is versioned.
- `ER-003 Ownership`: ownerless production component is forbidden.
- `ER-004 Lifecycle`: DRAFT, RESEARCH, POC_CANDIDATE, BACKTESTED, WF_VALIDATED, OOS_VALIDATED, PAPER_CANDIDATE, PAPER_APPROVED, LIVE_CANDIDATE, LIVE_APPROVED, RESTRICTED, QUARANTINED, SUSPENDED, REJECTED, DEPRECATED, RETIRED, WITHDRAWN.
- `ER-005 Provenance`: evidence and derived data provenance without authoritative is not accepted.
- `ER-006 Snapshot consistency`: cycle observations carry `snapshot_id`.
- `ER-007 Cycle identity`: `cycle_id` is the canonical correlation key.
- `ER-008 Immutability`: raw market data, evidence, decision records, execution records, audit events and validation artifacts are append-only and immutable.
- `ER-009 Evidence status`: explicit evidence status is mandatory.
- `ER-010 Unknown`: fabricated default is forbidden.
- `ER-011 Capability-first validation`: agent promotion does not replace capability validation.
- `ER-012 License governance`: unknown license `reuse_mode=NO_CODE_REUSE`.
- `ER-013 Repainting/lookahead`: if detected, `trading_eligible=false`.
- `ER-014 State separation`: RuntimeState, HistoricalMemory, Knowledge, Evidence, and Learning are separate.
- `ER-015 Risk separation`: RiskAssessment is a separate entity.

## 15. Relationship Rules

Canonical relationships:

```text
OWNS
CONSUMES
PRODUCES
DERIVED_FROM
OBSERVES
CONTAINS
USES
DEPENDS_ON
SUPPORTS
CONTRADICTS
VERIFIES
CONTRIBUTES_TO
QUALIFIES
EVALUATED_BY
CONSTRAINED_BY
MITIGATED_BY
GOVERNED_BY
CONTROLLED_BY
ALLOWED_BY
BLOCKED_BY
SUBJECT_TO
VALIDATED_BY
APPROVED_BY
PROMOTED_TO
RESTRICTS
SUPERSEDES
CREATES
EXECUTES
RESULTS_IN
RECORDED_AS
PRODUCES_LESSON
PROPOSES
ESCALATES_TO
```

Mandatory lineage:

```text
RawData
-> MarketSnapshot
-> FeatureSnapshot
-> Observation
-> Evidence
-> SetupCandidate
-> DecisionCandidate
-> RiskAssessment
-> Validation
-> DecisionGovernance
-> TradeDecision
-> TradePlan
-> Execution
-> PositionLifecycle
-> ClosureReview
-> Lesson
```

Forbidden:

```text
Agent -> PRODUCES -> TradeDecision
Agent -> EXECUTES -> Order
LearningCandidate -> PROMOTES -> ProductionComponent
```

Decision chain:

```text
Setup -> EVALUATED_BY -> DeterministicCore
DeterministicCore -> PRODUCES -> DecisionCandidate
DecisionCandidate -> CONSTRAINED_BY -> RiskAssessment
DecisionCandidate -> VALIDATED_BY -> Validation
DecisionGovernance -> PRODUCES -> TradeDecision
```

Mandatory relationship rules for this chain are independent and ordered by
responsibility:

```text
RR-007: DeterministicCore -> PRODUCES -> DecisionCandidate
RR-008: DecisionCandidate -> CONSTRAINED_BY -> RiskAssessment
RR-021: DecisionCandidate -> VALIDATED_BY -> Validation
RR-022: DecisionGovernance -> PRODUCES -> TradeDecision
```

`DecisionCandidate` is advisory and has no execution authority. Risk and
Validation have veto authority; Decision Governance can produce a
`TradeDecision` only after their deterministic outcomes are applied. This does
not authorize a TradePlan, Execution, or live order; `RESEARCH_ONLY` and
`LIVE_ORDER_BLOCKED` remain mandatory.

Correct research promotion route:

```text
RadarFinding
-> ResearchUnit
-> CapabilityCandidate
-> VALIDATED_BY Validation
-> SUBJECT_TO PromotionGovernance
-> PROMOTED_TO RegistryComponent
```

## 16. Standards and Compliance Mapping

ISO 42001, ISO 23894, ISO 27001, ISO 31000, NIST AI RMF, COSO and COBIT gibi
No separate compliance subsystem is created for external frameworks. The shared ontology
is used:

```text
ExternalFramework
-> Requirement
-> Risk
-> Control
-> Implementation
-> Evidence
-> Test
-> Finding
-> Remediation
```

Mandatory metadata in legal sources:

```text
jurisdiction
status
effective_from
effective_to
last_verified_at
source_reference
```

## 17. Human Output Format

Standard scan table:

```text
Coin | Direction | Quality | Order | Entry | Stop Loss | TP1 | TP2 | TP3 | Leverage | Budget/Margin | R:R | News Risk | Decision
```

For Spot, `Leverage=N/A`. If data is missing, return `DATA_UNAVAILABLE`; if confidence is low,
`LOW_CONFIDENCE`. Price, indicator, wallet, order book, or news data is not fabricated.

Each decision cycle produces the following subsections:

1. Basic Decision
2. Market Outlook
3. Setup & Technical Evidence
4. Liquidity / Derivatives / Intelligence
5. Risk & Governance
6. Trade Plan
7. Execution Tagging
8. Closure Review
9. Learning Record

Machine-readable decision output `schema_version=2.0.0`, `cycle_id`,
`snapshot_id`, `decision_id`, data state, market outlook, observations,
evidence completeness, setup, scores, decision, risk, trade plan, governance,
execution, audit, and learning fields. The canonical trade plan includes entry
and exit rationale, target and invalidation levels, timeframes, markets, market
condition filters, risk controls, discovery method, and review/improvement
notes. Long-position exits may be governed by validated EMA crossover, price
action rejection, close-below-trendline, or Fibonacci retracement rules when
those exit methods are evidence-backed for the setup. Moving-average crossover
signals such as golden cross and death cross, and moving-average structures such
as 5-8-13, 25, 50, 100, and 50-200, are treated as confirmation cues, not as
standalone live gates. Unknown fields are `UNKNOWN`, `null`, or
`DATA_UNAVAILABLE`; fabricated defaults are not used.

The canonical setup includes `setup_id`, `name`, `timeframe`, `pattern_type`,
`quality`, and `trigger_status`. Reversal pattern families should set
`pattern_type` explicitly when the setup is pattern-driven.

## 18. Continuous Assurance and Safe State

Continuous Assurance Engine:

```text
DataAssurance
CapabilityAssurance
StrategyAssurance
PerformanceAssurance
RiskAssurance
OperationalAssurance
EvidenceAssurance
SecurityAssurance
GovernanceRevalidation
```

Durumlar:

```text
CONTINUE
RESTRICT
QUARANTINE
SUSPEND
WITHDRAW
```

Safe State:

```text
NO_NEW_TRADE
NO_LIVE_EXECUTION
PRESERVE_STATE
CONTINUE_MONITORING
WRITE_INCIDENT
REQUIRE_REVALIDATION
```

An unknown critical state returns `DENY`.

## 19. Current Visible Gaps

The core schema keeps the following gaps visible:

These gaps are not considered closed by schema presence, agent presence, proxy
logic, green unit tests, or broad coverage alone. Every gap remains visibly
`PARTIAL`, `MISSING`, or `RESEARCH_ONLY` until artifact-level OOS, walk-forward,
regime, paper/operational evidence, owner review, and promotion evidence exist.

- Trend: EMA, Supertrend, and trend channel exist; capability coverage is missing.
- Volatility: ATR exists; Bollinger, Keltner, squeeze, and realized-volatility catalog are missing.
- Momentum: RSI and momentum exist; MACD, Stochastic, ROC, and CCI atoms are incomplete.
- Structure: confirmed swing exists; BOS and CHoCH have separate evidence gaps.
- S/R: lookback min/max is weighted; pivot, cluster, zone decay, and reaction statistics are missing.
- Derivatives: funding, OI, and long-short surfaces exist; parity/OOS evidence is not separate.
- Validation: WF/OOS infrastructure exists; real capability-based OOS artifact is missing.
- Observability: trace/metrics/audit is strong; capability health and decision health are missing.
- Data Quality: temporal lineage and gap controls exist; expectation/capability catalog is missing.
- Research: license/hash/quarantine exists; the Radar -> ResearchUnit -> Capability -> Validation -> Promotion chain is not fully connected.
- DGE: blocker-first and rule catalog exist; Radar capability-gap mapping is missing.

## 20. Implementation Alignment

This document's typed Python contracts are represented in
`src/ai4binance/governance/framework.py`, and the related behavior is verified
by `tests/test_governance_framework.py`.

Core contract constants:

```text
AI4BINANCE_CORE_CONSTITUTION
AI4BINANCE_CORE_ARCHITECTURE
AI4BINANCE_DIGITAL_COMPANY_OPERATING_MODEL
AI4BINANCE_WEB_INTELLIGENCE_RADAR_CONTRACT
AI4BINANCE_LOOPS_SELF_IMPROVEMENT_CONTRACT
AI4BINANCE_CAPABILITY_GAP_REGISTRY
AI4BINANCE_APPEND_ONLY_EVIDENCE_FABRIC
AI4BINANCE_CONTINUOUS_ASSURANCE_ENGINE
AI4BINANCE_REPOSITORY_FILE_GOVERNANCE_STANDARD
AI4BINANCE_SAFE_STATE
```

Document defines the target governance standard, not the completion of the code.


