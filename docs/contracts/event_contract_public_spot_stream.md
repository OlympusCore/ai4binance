---
document_id: AI4B-SPOT-EVT-001
title: AI4BINANCE Public Spot Stream Contract
document_type: EVENT_CONTRACT
version: 1.0.0
status: ACTIVE
owner: Enterprise Knowledge Governance
authority_level: NORMATIVE
authority_layer: L3_CANONICAL_CONTRACTS_SCHEMAS
authority_scope: public_spot_stream
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
canonical_path: docs/contracts/event_contract_public_spot_stream.md
machine_enforceable: true
audit_required: true
classification: INTERNAL
---

# Public Binance Spot Stream Contract

## ELI10

This document explains how to validate Binance Spot public data messages.
The system only verifies trusted, closed, and correctly timed candles.
This layer does not use the API key or command.


## Scope

This vertical slice only validates Binance Spot public market-data payloads.
It does not establish a network connection, use an API key, or include an order method.

Desteklenen karar zaman dilimleri:

- `15m`
- `1h`
- `4h`
- `1d`

## Applied contracts

1. Raw and combined `kline` payload shapes are converted into typed models.
2. Symbol, timeframe, time boundaries, OHLCV, and trade-ID lineage are validated.
3. Only `x=true` closed candles are considered `OHLCVCandle`.
4. Candles without valid open, old, duplicate, or sequence proof are rejected.
5. Trade-ID gaps and bounded queues are connected to the existing `PublicStreamRecovery` engine.
6. `serverShutdown` planned reconnect scenario is generated.
7. Connection age requires a planned rollover at 23 hours 55 minutes.
8. Subscription count, lowercase identity, control message rate, pong deadline, and
   message byte limits are preserved in the open policy.
9. Accepted closed candle can be converted into the deterministic `SPOT_KLINE_CLOSED` domain event
   and written to the hash-linked journal.

## Fail-closed outcomes

```text
OPEN_KLINE_NOT_DECISION_ELIGIBLE
DUPLICATE_OR_OLD_CLOSED_KLINE
KLINE_TRADE_SEQUENCE_UNAVAILABLE
STREAM_SEQUENCE_GAP
STREAM_BACKPRESSURE_LIMIT_EXCEEDED
STREAM_SERVER_SHUTDOWN
STREAM_CONNECTION_ROLLOVER_REQUIRED
```

None of these proofs grant execution permission:

```text
execution_allowed=false
LIVE_ORDER_BLOCKED
```

## Intentional out-of-scope

- Real WebSocket network transport.
- Ping/pong frame transmission.
- REST snapshot adapter runtime automation.
- Private user-data stream.
- `executionReport` and balance reconciliation.
- API key, Ed25519 session, or order endpoint.
- `python-binance`, OctoBot or another external runtime dependency.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_public_spot_stream.py tests\test_connector_stream_readiness.py --no-cov -q
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .agents\skills\quality-gate-loop\scripts\invoke_gate.ps1 -RepositoryRoot .
```
