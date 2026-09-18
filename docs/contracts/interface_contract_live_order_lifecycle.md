---
document_id: AI4B-LIVE-ORDER-001
title: AI4BINANCE Live Order Lifecycle Contract
document_type: INTERFACE_CONTRACT
version: 1.0.0
status: ACTIVE
owner: Enterprise Knowledge Governance
authority_level: NORMATIVE
authority_layer: L3_CANONICAL_CONTRACTS_SCHEMAS
authority_scope: live_order_lifecycle
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
canonical_path: docs/contracts/interface_contract_live_order_lifecycle.md
machine_enforceable: true
audit_required: true
classification: INTERNAL
---

# AI4Binance Live Order Lifecycle Contract

## ELI10

This document defines the only approved lifecycle shape for Spot live orders.
It records how a preview becomes a promotion request, a human approval request,
an approved submission, and a post-submit lifecycle record.
It does not grant execution authority by itself.

## Purpose

The live order lifecycle is a separate canonical contract from research
promotion, paper execution, and validation summaries.

It exists to keep three boundaries explicit:

- `BINANCE_MARKET` remains human-hand manual only.
- `VIRTUAL_MARKET` remains bounded and simulation only.
- `LIVE_ORDER` remains separately promoted, human approved, and fail closed.

## Canonical Source

The runtime source of truth is `src/ai4binance/execution/live_order_lifecycle.py`.
The live place consumer is `src/ai4binance/cli/live.py`.
The durable event journal is `live-order-lifecycle.jsonl` under the configured
audit directory.

## Lifecycle Stages

The approved live order lifecycle stages are:

| Stage | Meaning |
| --- | --- |
| `DRAFT` | An order idea exists but has no preview evidence. |
| `PREVIEWED` | A deterministic preview hash exists. |
| `PROMOTION_REQUIRED` | Promotion evidence is required before human approval. |
| `HUMAN_APPROVAL_REQUIRED` | A governed human approval request has been issued. |
| `READY_FOR_SUBMISSION` | Promotion and human approval evidence are aligned. |
| `SUBMITTED` | The order has been sent to the live executor. |
| `ACCEPTED` | The venue has acknowledged the submission. |
| `PARTIALLY_FILLED` | The order has partial fill evidence. |
| `FILLED` | The order is fully filled. |
| `CANCEL_REQUESTED` | A cancel request has been recorded. |
| `CANCELLED` | The order is cancelled. |
| `REJECTED` | The venue rejected the order. |
| `EXPIRED` | The order expired before completion. |

## Event Contract

The lifecycle journal is append only and replays these event types:

- `LIVE_ORDER_PREVIEWED`
- `LIVE_ORDER_PROMOTION_REQUESTED`
- `LIVE_ORDER_HUMAN_APPROVAL_REQUESTED`
- `LIVE_ORDER_HUMAN_APPROVED`
- `LIVE_ORDER_SUBMITTED`
- `LIVE_ORDER_ACCEPTED`
- `LIVE_ORDER_PARTIALLY_FILLED`
- `LIVE_ORDER_FILLED`
- `LIVE_ORDER_CANCEL_REQUESTED`
- `LIVE_ORDER_CANCELLED`
- `LIVE_ORDER_REJECTED`
- `LIVE_ORDER_EXPIRED`

The first event must be `LIVE_ORDER_PREVIEWED`.
The event chain must preserve symbol identity, preview hash identity, and
contiguous sequence numbers.

The submit path may extend the chain with post-submit venue evidence from
read-only order history snapshots when the runtime can verify them.

## Fail-Closed Rules

The lifecycle contract never grants execution authority.
It always remains bound to these outputs:

```text
execution_allowed=false
LIVE_ORDER_BLOCKED
```

The record must reject:

- negative fill evidence,
- missing preview identity,
- non-contiguous lifecycle sequence numbers,
- invalid promotion status,
- mismatched preview hashes,
- illegal state transitions.

## Promotion Evidence Binding

Live order readiness may be informed by a promotion evidence registry.
Promotion evidence can be resolved from the validation summary or from the
dedicated evidence ledger when the registry is configured that way.

This contract does not treat evidence provenance as optional.
Every promoted live order must be traceable back to governed evidence.

## Consumer Binding

The `live-place-spot` command must record the lifecycle journal after a
successful live submission path.
The journal output is advisory and auditable only.
It is not an authorization source.

## Out of Scope

- Automated live execution promotion.
- Strategy-level live eligibility.
- Portfolio-level risk override.
- Venue reconciliation beyond the recorded lifecycle state.
- Paper lifecycle semantics.

## Maintenance Rule

If a live order stage, event type, blocker, or journal field changes, update
this contract, the runtime lifecycle implementation, and the matching tests in
the same change set.
