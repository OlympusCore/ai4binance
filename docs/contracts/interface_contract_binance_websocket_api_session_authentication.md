---
document_id: AI4B-BINANCE-IFC-102
title: Binance WebSocket API Session Authentication Reference
document_type: INTERFACE_CONTRACT
version: 1.0.0
status: ACTIVE
owner: Enterprise Governance
authority_level: EXTERNAL_AUTHORITY
authority_layer: L3_CANONICAL_CONTRACTS_SCHEMAS
authority_scope: binance_websocket_api_session_authentication
content_role: DERIVED
source_of_truth: false
canonical_path: docs/contracts/interface_contract_binance_websocket_api_session_authentication.md
machine_enforceable: false
audit_required: true
classification: INTERNAL
---
# Binance WebSocket API Session Authentication Reference

## ELI10

This document keeps the Binance session authentication material separate from market and trading methods.

## Source Lineage

- Source file: `docs/contracts/interface_contract_binance_websocket_api_reference.md`
- Source section start: `## Session Authentication`
- This file preserves a bounded section of the governed source document.

## Session Authentication

**Note:** Only _Ed25519_ keys are supported for this feature.

If you do not want to specify `apiKey` and `signature` in each individual request,
you can authenticate your API key for the active WebSocket session.

Once authenticated, you no longer have to specify `apiKey` and `signature` for those requests that need them.
Requests will be performed on behalf of the account owning the authenticated API key.

**Note:** You still have to specify the `timestamp` parameter for `SIGNED` requests.

### Authenticate after connection

You can authenticate an already established connection using session authentication requests:

* [`session.logon`](#log-in-with-api-key-signed) – authenticate, or change the API key associated with the connection
* [`session.status`](#query-session-status) – check connection status and the current API key
* [`session.logout`](#log-out-of-the-session) – forget the API key associated with the connection

**Regarding API key revocation:**

If during an active session the API key becomes invalid for _any reason_ (e.g. IP address is not whitelisted, API key was deleted, API key doesn't have correct permissions, etc), after the next request the session will be revoked with the following error message:

```javascript
{
    "id": null,
    "status": 401,
    "error": {
        "code": -2015,
        "msg": "Invalid API-key, IP, or permissions for action."
    }
}
```

### Authorize _ad hoc_ requests

Only one API key can be authenticated with the WebSocket connection.
The authenticated API key is used by default for requests that require an `apiKey` parameter.
However, you can always specify the `apiKey` and `signature` explicitly for individual requests,
overriding the authenticated API key and using a different one to authorize a specific request.

For example, you might want to authenticate your `USER_DATA` key to be used by default,
but specify the `TRADE` key with an explicit signature when placing orders.

## Data sources

* The API system is asynchronous. Some delay in the response is normal and expected.

* Each method has a data source indicating where the data is coming from, and thus how up-to-date it is.

Data Source     | Latency  | Description
--------------- | -------- | -----------
Matching Engine | lowest   | The Matching Engine produces the response directly
Memory          | low      | Data is fetched from API server's local or external memory cache
Database        | moderate | Data is retrieved from the database

* Some methods have more than one data source (e.g., Memory => Database).

  This means that the API will look for the latest data in that order:
  first in the cache, then in the database.
