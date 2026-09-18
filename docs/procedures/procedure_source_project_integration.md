---
document_id: AI4B-SOURCE-PROC-001
title: AI4BINANCE Source Project Integration
document_type: PROCEDURE
version: 1.0.1
status: ACTIVE
owner: Enterprise Knowledge Governance
authority_level: NORMATIVE
authority_layer: L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS
authority_scope: source_project_integration
authority_effect: OPERATIONAL_SPECIALIZATION
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: source_project_integration_procedure
machine_enforceable: true
audit_required: true
classification: INTERNAL
canonical_path: docs/procedures/procedure_source_project_integration.md
---

# Source Project Integration

## ELI10

This document explains how ideas learned from other projects can be securely implemented in AI4BINANCE.
Source code is not copied in bulk; useful ideas are reimplemented with tests and fail-closed rules.


This work is derived from the analysis of `ai4bspot`, `ai4bfutures` and `ai4cryptotrade`.
The ideas are reapplied within the AI4BINANCE security agreement.
Source repository files have not been copied in bulk.

## Applied contributions

### ai4bspot

- `exchange/ws_api.py`: Ed25519 canonical signature payload, PEM validation
  official-host allowlist, bounded unsolicited queue, `session.logon`, read-only
account/open-orders and authenticated request kernel.
- `execution/live_spot.py`: `order.test`, `order.place`, and `order.cancel` for
Deterministic internal live gate. Missing a single gate or different preview hash exchange
Completely blocks the call.
- `portfolio/cost_basis.py`: signed GET-only `myTrades` via fee-aware
  weighted-average cost and realized PnL.
- `portfolio/rebalancing.py`: immutable core/strategic/tactical/cash bucket modeli,
  stage/cooldown/hysteresis and fee-aware proposal-only rebalancing.

### ai4bfutures

- `whale_fusion/derivatives/cross_venue.py`: freshness, sequence, field validity,
  coverage and venue-concentration gate-based supplementary multi-venue research
  skoru.
- Median/MAD robust normalization in the same module. Insufficient history `None`, zero
  dispersion deterministically produces zero-score.
- Outputs remain fixed `RESEARCH_ONLY`, `execution_allowed=false` and
  `LIVE_ORDER_BLOCKED`.

### ai4cryptotrade

- Gap/staleness, kill-switch, and rebalancing concepts are existing stronger
  input for comparison against archive/risk-flow/rebalancing test contracts.
- Live execution, unsigned approval, futures-notional-as-equity, otomatik short,
  Untrusted model loading and naive walk-forward code were not taken.

## Live Order Limit

The existence of order methods does not imply live authority. `GatedSpotOrderExecutor`
re-evaluates the 35 live prerequisites on each call. The place command also
requires the canonical payload SHA-256 preview hash to match exactly with the user-approved hash,
and will not call `order.place` unless `order.test` is successful.

Default:

```text
trading_mode=paper
order_mode=manual
allow_auto_live_orders=false
LIVE_ORDER_BLOCKED
```

No real testnet or production order has been sent during this integration.

## Remaining External Evidence

- Real Binance Ed25519 testnet authentication and reconnect soak.
- Full trade-history pagination for more than 1000 fills.
- Point-in-time price source for fee conversion of BNB/third asset.
- Permanent inventory bucket state and allocation policy OOS validation.
- Real multi-venue provider adapters and long-term OOS proof.


