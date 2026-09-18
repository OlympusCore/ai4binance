---
document_id: AI4B-BINANCE-IFC-105
title: Binance WebSocket API Authentication Requests Reference
document_type: INTERFACE_CONTRACT
version: 1.0.0
status: ACTIVE
owner: Enterprise Governance
authority_level: EXTERNAL_AUTHORITY
authority_layer: L3_CANONICAL_CONTRACTS_SCHEMAS
authority_scope: binance_websocket_api_authentication_requests
content_role: DERIVED
source_of_truth: false
canonical_path: docs/contracts/interface_contract_binance_websocket_api_authentication_requests.md
machine_enforceable: false
audit_required: true
classification: INTERNAL
---
# Binance WebSocket API Authentication Requests Reference

## ELI10

This document keeps login, session status, and logout request formats separate.

## Source Lineage

- Source file: `docs/contracts/interface_contract_binance_websocket_api_reference.md`
- Source section start: `## Authentication requests`
- This file preserves a bounded section of the governed source document.

## Authentication requests

**Note:** Only _Ed25519_ keys are supported for this feature.

<a id="session-logon"></a>

### Log in with API key (SIGNED)

```javascript
{
    "id": "c174a2b1-3f51-4580-b200-8528bd237cb7",
    "method": "session.logon",
    "params": {
        "apiKey": "key",
        "signature": "1cf54395b336b0a9727ef27d5d98987962bc47aca6e13fe978612d0adee066ed",
        "timestamp": 1649729878532
    }
}
```

Authenticate WebSocket connection using the provided API key.

After calling `session.logon`, you can omit `apiKey` and `signature` parameters for future requests that require them.

Note that only one API key can be authenticated.
Calling `session.logon` multiple times changes the current authenticated API key.

**Weight:**
2

**Parameters:**

Name          | Type    | Mandatory | Description
------------- | ------- | --------- | ------------
`apiKey`      | STRING  | YES       |
`recvWindow`  | DECIMAL | NO        | The value cannot be greater than `60000`. <br> Supports up to three decimal places of precision (e.g., 6000.346) so that microseconds may be specified.
`signature`   | STRING  | YES       |
`timestamp`   | LONG    | YES       |

**Data Source:**
Memory

**Response:**

```javascript
{
    "id": "c174a2b1-3f51-4580-b200-8528bd237cb7",
    "status": 200,
    "result": {
        "apiKey": "key",
        "authorizedSince": 1649729878532,
        "connectedSince": 1649729873021,
        "returnRateLimits": false,
        "serverTime": 1649729878630,
        "userDataStream": false // is User Data Stream subscription active?
    }
}
```

<a id="session-status"></a>

### Query session status

```javascript
{
    "id": "b50c16cd-62c9-4e29-89e4-37f10111f5bf",
    "method": "session.status"
}
```

Query the status of the WebSocket connection,
inspecting which API key (if any) is used to authorize requests.

**Weight:**
2

**Parameters:**
NONE

**Data Source:**
Memory

**Response:**

```javascript
{
    "id": "b50c16cd-62c9-4e29-89e4-37f10111f5bf",
    "status": 200,
    "result": {
        // if the connection is not authenticated, "apiKey" and "authorizedSince" will be shown as null
        "apiKey": "key",
        "authorizedSince": 1649729878532,
        "connectedSince": 1649729873021,
        "returnRateLimits": false,
        "serverTime": 1649730611671,
        "userDataStream": true     // is User Data Stream subscription active?
    }
}
```

### Log out of the session

```javascript
{
    "id": "c174a2b1-3f51-4580-b200-8528bd237cb7",
    "method": "session.logout"
}
```

Forget the API key previously authenticated.
If the connection is not authenticated, this request does nothing.

Note that the WebSocket connection stays open after `session.logout` request.
You can continue using the connection,
but now you will have to explicitly provide the `apiKey` and `signature` parameters where needed.

**Weight:**
2

**Parameters:**
NONE

**Data Source:**
Memory

**Response:**

```javascript
{
    "id": "c174a2b1-3f51-4580-b200-8528bd237cb7",
    "status": 200,
    "result": {
        "apiKey": null,
        "authorizedSince": null,
        "connectedSince": 1649729873021,
        "returnRateLimits": false,
        "serverTime": 1649730611671,
        "userDataStream": false // is User Data Stream subscription active?
    }
}
```
