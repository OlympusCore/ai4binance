---
document_id: AI4B-BINANCE-IFC-001
title: Binance WebSocket API Reference
document_type: INTERFACE_CONTRACT
version: 1.0.0
status: ACTIVE
owner: Enterprise Knowledge Governance
authority_level: EXTERNAL_AUTHORITY
authority_layer: L3_CANONICAL_CONTRACTS_SCHEMAS
authority_scope: binance_websocket_api_reference
content_role: DERIVED
source_of_truth: false
canonical_path: docs/contracts/interface_contract_binance_websocket_api_reference.md
machine_enforceable: true
audit_required: true
classification: INTERNAL
---
# Binance WebSocket API Reference

## ELI10

This index points to smaller Binance WebSocket API reference files. It is an external reference snapshot and does not authorize live trading.

## Split Reference Files

| File | Scope |
| --- | --- |
| `docs/contracts/interface_contract_binance_websocket_api_foundation.md` | Binance WebSocket API Foundation Reference |
| `docs/contracts/interface_contract_binance_websocket_api_session_authentication.md` | Binance WebSocket API Session Authentication Reference |
| `docs/contracts/interface_contract_binance_websocket_api_general_requests.md` | Binance WebSocket API General Requests Reference |
| `docs/contracts/interface_contract_binance_websocket_api_market_data.md` | Binance WebSocket API Market Data Reference |
| `docs/contracts/interface_contract_binance_websocket_api_authentication_requests.md` | Binance WebSocket API Authentication Requests Reference |
| `docs/contracts/interface_contract_binance_websocket_api_order_requests.md` | Binance WebSocket API Order Requests Reference |
| `docs/contracts/interface_contract_binance_websocket_api_order_list_requests.md` | Binance WebSocket API Order List Requests Reference |
| `docs/contracts/interface_contract_binance_websocket_api_account_requests.md` | Binance WebSocket API Account Requests Reference |
| `docs/contracts/interface_contract_binance_websocket_api_user_data_stream_requests.md` | Binance WebSocket API User Data Stream Requests Reference |

## Governance Boundary

- This reference remains `source_of_truth=false`.
- Binance documentation remains the external authority.
- AI4BINANCE must keep exchange validation, risk gates, and execution permission deterministic and fail-closed.
- Live eligibility remains `LIVE_ORDER_BLOCKED` unless separately authorized by the governed promotion lifecycle.

