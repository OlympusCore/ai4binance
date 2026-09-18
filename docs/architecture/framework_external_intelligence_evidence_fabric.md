---
document_id: AI4B-EIEF-FRM-001
title: External Intelligence and Evidence Fabric Architecture
document_type: FRAMEWORK
version: 1.0.0
status: ACTIVE
owner: Enterprise Knowledge Governance
authority_level: NORMATIVE
authority_layer: L6_ARCHITECTURE_ONTOLOGY_ADR
authority_scope: external_intelligence_evidence_fabric
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
canonical_path: docs/architecture/framework_external_intelligence_evidence_fabric.md
machine_enforceable: true
audit_required: true
classification: INTERNAL
---

# AI4BINANCE External Intelligence & Evidence Fabric v2

## ELI10

EIEF turns external news, social signals, GitHub research, security findings,
and regulatory information into a single evidence factory. The factory first
asks who the source is, where the evidence is, whether another source verifies
it, and whether there is a risk. The result is not an order; it is advisory
risk impact for AI4BINANCE decision governance.

## Purpose

External Intelligence & Evidence Fabric, abbreviated as EIEF, combines two duties:

1. Technology Development Radar: tracks external technology evidence that can
   improve AI4BINANCE architecture, backtest/validation, Graph RAG, XAI, audit,
   security, AutoML, and local LLM operations.
2. Binance Spot/Futures Opportunity News Radar: stablecoin base, wrapped asset
   and eligible Binance assets outside leveraged tokens
   classifies the news based on evidence, source quality, and risk impact.

EIEF is not an autonomous trading system. External information does not create
final signals, position expansion, risk-limit changes, or live-order authority.

```text
DATA
-> CLAIM
-> EVIDENCE
-> VERIFICATION
-> RISK
-> OPPORTUNITY_OR_TECHNOLOGY_IMPACT
-> AUDIT
```

Asla:

```text
DATA
-> HYPE
-> TRADE
```

## Radarlar

Radars using the shared `RadarConnector` contract:

- Web Intelligence Radar
- X Radar
- News Radar
- Reddit Radar
- Telegram Radar
- GitHub Radar
- Security Radar
- Regulatory Radar

In the first MVP slice, X, News, Reddit, Telegram, Security, and Regulatory radars
produce the standard `DATA_UNAVAILABLE` finding when the provider/API is
unavailable. This is intentional fail-closed behavior. GitHub Radar connects the
existing capability-first engine to the EIEF `RadarFinding` contract through an adapter.

## Web Intelligence Radar and LOOPS

Web Intelligence Radar is a research-only radar directory that feeds the system's
own technology development loop. Its purpose is to collect technology, security,
validation, model-governance, agent-orchestration, and market-intelligence
findings, make them evidence-backed, and pass them into the LOOPS cycle.

LOOPS flow:

```text
LISTEN outcome/audit/closure
-> OBSERVE Web Intelligence Radar
-> ORIENT hypothesis and capability gap
-> PROVE validation, WF, OOS and regime evidence
-> STAGE governed promotion or rejection
```

Web Intelligence Radar outputs:

```text
RadarFinding
EvidencePack
CapabilityGap
ResearchUnit
ValidationPlan
GovernanceIntake
AuditEvent
```

Permission boundary:

```text
decision_authority=ADVISORY_ONLY
promotion_status=RESEARCH_ONLY
execution_allowed=false
live_eligibility_status=LIVE_ORDER_BLOCKED
```

Unknown license `NO_CODE_REUSE`; lookahead/repainting `NOT_TRADING_ELIGIBLE`;
returns `DATA_UNAVAILABLE` when the provider is unavailable.

## Shared Contracts

Canonical data types:

- `ExternalClaim`
- `ExternalEvidence`
- `ExternalFinding`
- `EvidenceGraphNode`
- `EvidenceGraphEdge`
- `RadarRunManifest`
- `EligibleAsset`
- `UniverseSnapshot`
- `OpportunityCandidate`
- `TechnologyCandidate`
- `ExternalDecisionImpact`

All contracts preserve the following authority boundary:

```text
promotion_status=RESEARCH_ONLY
execution_allowed=false
live_eligibility_status=LIVE_ORDER_BLOCKED
```

## Binance Universe

Opportunity scans must run fail-closed through the dynamic Binance Spot/Futures
universe. The full coin list is not hard-coded. The first MVP converts existing
`ai4binance.universe` models into an EIEF `EligibleAsset` snapshot.

If the base asset is a stablecoin, it is outside the opportunity universe. Using
USDT, USDC, or FDUSD only as quote asset is not a standalone exclusion reason.
Wrapped and leveraged asset
detection cannot rely only on suffix/prefix; when uncertainty exists:

```text
ASSET_CLASSIFICATION_UNCERTAIN
LOW_CONFIDENCE
MANUAL_REVIEW_REQUIRED
```

## Evidence and Validation

EIEF does not count reshare volume as independent validation. If 500 social shares
copy a single original claim, the number of independent sources can remain 1.

Shared layers:

- original-source discovery
- duplicate/copy clustering
- source credibility scoring
- claim verification
- manipulation/copy risk scoring
- cross-radar fusion
- advisory decision impact

## AI4BINANCE Baglantisi

EIEF gives the Decision Governance Engine only compact advisory risk impact:

```text
external_bias
news_risk
social_risk
security_risk
regulatory_risk
manipulation_risk
decision_impact
blockers
confidence
```

This adapter does not own the signal engine, risk gate, execution gate, or order
preview. It is not authority. The deterministic AI4BINANCE core always holds the final decision.

## Security, Privacy and GDPR

- Private messages, private groups, cookies, session strings, or credentials are not stored.
- X/Reddit/Telegram restrictions are not bypassed.
- The news radar does not store full copyrighted article text when a license is unavailable.
- Security radar does not generate exploit instructions.
- Regulatory radar does not provide legal advice.
- All reports must be secret-redacted and audit-traced.

## MVP Acceptance Criteria

1. EIEF core models reject authority drift.
2. Every radar returns the standard `RadarFinding`.
3. `DATA_UNAVAILABLE` remains visible when a provider is unavailable.
4. GitHub Radar adapter connects the existing engine without replacing it.
5. Evidence graph and original-source/copy scoring exist in the shared layer.
6. Fusion produces an advisory-only `ExternalDecisionImpact`.
7. CLI and documentation links are available.
8. Testler dis API kullanmadan synthetic fixture with gecer.

## Live Compatibility

```text
RESEARCH_ONLY
execution_allowed=false
LIVE_ORDER_BLOCKED
```
