---
document_id: AI4B-GOV-EVID-AIMS-003
title: AI4BINANCE AIMS Provider Control Review
document_type: EVIDENCE_REQUIREMENT
version: 1.0.0
status: ACTIVE
owner: Security and Privacy Governance
authority_level: ADVISORY
authority_layer: L8_REPORTS_EVIDENCE_INVENTORIES
authority_scope: evidence_aims_provider_control_review
content_role: GENERATED
source_of_truth: false
machine_enforceable: false
audit_required: true
classification: INTERNAL
canonical_path: docs/reports/governance/evidence_aims_provider_control_review.md
---

# AI4BINANCE AIMS Provider Control Review

## ELI10

This review checks provider and tool boundaries used by AI4BINANCE evidence
work. Providers may help produce advisory evidence, but they cannot create
authority, approve live trading, bypass controls, or write secrets.

## Review Scope

| provider_surface | role | trust_boundary | required_control | review_result |
|---|---|---|---|---|
| Codex provider adapter | repository assistance | local repository and governed instructions | provider adapter must not redefine canonical governance | CONTROLLED |
| Claude provider adapter | repository assistance | provider-specific syntax and tooling | semantic parity with core and repository rules | CONTROLLED |
| Gemini provider adapter | repository assistance | provider-specific syntax and tooling | semantic parity with core and repository rules | CONTROLLED |
| Local or loopback LLM | advisory analysis | local-only model runtime boundary | no live authority, no secret exposure, evidence provenance | CONTROLLED |
| Read-only evidence MCP | evidence retrieval | read-only tool boundary | `Agent -> Tool Policy -> Authorization -> MCP Gateway -> Tool` | CONTROLLED |
| External web, news, social, and research sources | hostile external content | untrusted input boundary | provenance, freshness, quote limits, source trust, degraded states | CONTROLLED_FOR_RESEARCH |
| AIMS blocker closure map | governance evidence traceability | report-only closure mapping boundary | blocker visibility must remain traceable and not imply live authority | CONTROLLED |
| AIMS repository governance findings | governance evidence traceability | report-only findings boundary | repository findings must remain traceable and not imply live authority | CONTROLLED |
| Exchange or market-data providers | market data and private read-only data | least-privilege exchange boundary | read-only by default, no live order authority from provider access | CONTROLLED |

## Provider Risk Controls

| risk_id | risk | control | residual_status |
|---|---|---|---|
| PROV-RISK-001 | Tool availability is mistaken for authorization | tool governance route and default deny | CONTROLLED |
| PROV-RISK-002 | Provider-specific instructions redefine safety boundaries | provider adapters reference canonical governance | CONTROLLED |
| PROV-RISK-003 | External content is treated as verified truth | hostile-input assumption and provenance requirement | CONTROLLED_FOR_RESEARCH |
| PROV-RISK-004 | Provider output authorizes live trading or risk expansion | LLM boundary and fail-closed trading policy | BLOCKED_BY_DEFAULT |
| PROV-RISK-005 | Secrets or private data are exposed to provider surfaces | privacy and leak guard controls | CONTROLLED |

## Required Operating Rules

- Provider output is advisory evidence only.
- External content requires provenance and freshness checks before use.
- No provider can approve live execution, deployment, strategy promotion, or
  risk-limit expansion.
- Missing provider evidence creates `REQUIRE_EVIDENCE` or a degraded state.
- Secret, wallet, account, and private-key data must not be exposed.

## Decision

```text
provider_control_review=COMPLETE_FOR_INTERNAL_BASELINE
execution_allowed=false
promotion_status=RESEARCH_ONLY
live_eligibility_status=LIVE_ORDER_BLOCKED
```
