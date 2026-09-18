---
document_id: AI4B-BINANCE-IFC-103
title: Binance WebSocket API General Requests Reference
document_type: INTERFACE_CONTRACT
version: 1.0.0
status: ACTIVE
owner: Enterprise Governance
authority_level: EXTERNAL_AUTHORITY
authority_layer: L3_CANONICAL_CONTRACTS_SCHEMAS
authority_scope: binance_websocket_api_general_requests
content_role: DERIVED
source_of_truth: false
canonical_path: docs/contracts/interface_contract_binance_websocket_api_general_requests.md
machine_enforceable: false
audit_required: true
classification: INTERNAL
---
# Binance WebSocket API General Requests Reference

## ELI10

This document keeps connectivity, server time, and exchange information requests together.

## Source Lineage

- Source file: `docs/contracts/interface_contract_binance_websocket_api_reference.md`
- Source section start: `# Public API requests`
- This file preserves a bounded section of the governed source document.

# Public API requests

## General requests

### Test connectivity

```javascript
{
    "id": "922bcc6e-9de8-440d-9e84-7c80933a8d0d",
    "method": "ping"
}
```

Test connectivity to the WebSocket API.

**Note:**
You can use regular WebSocket ping frames to test connectivity as well,
WebSocket API will respond with pong frames as soon as possible.
`ping` request along with `time` is a safe way to test request-response handling in your application.

**Weight:**
1

**Parameters:**
NONE

**Data Source:**
Memory

**Response:**
```javascript
{
    "id": "922bcc6e-9de8-440d-9e84-7c80933a8d0d",
    "status": 200,
    "result": {},
    "rateLimits": [
        {
            "rateLimitType": "REQUEST_WEIGHT",
            "interval": "MINUTE",
            "intervalNum": 1,
            "limit": 6000,
            "count": 1
        }
    ]
}
```

### Check server time

```javascript
{
    "id": "187d3cb2-942d-484c-8271-4e2141bbadb1",
    "method": "time"
}
```

Test connectivity to the WebSocket API and get the current server time.

**Weight:**
1

**Parameters:**
NONE

**Data Source:**
Memory

**Response:**
```javascript
{
    "id": "187d3cb2-942d-484c-8271-4e2141bbadb1",
    "status": 200,
    "result": {
        "serverTime": 1656400526260
    },
    "rateLimits": [
        {
            "rateLimitType": "REQUEST_WEIGHT",
            "interval": "MINUTE",
            "intervalNum": 1,
            "limit": 6000,
            "count": 1
        }
    ]
}
```

<a id="exchangeInfo"></a>

### Exchange information

```javascript
{
    "id": "5494febb-d167-46a2-996d-70533eb4d976",
    "method": "exchangeInfo",
    "params": {
        "symbols": ["BNBBTC"]
    }
}
```

Query current exchange trading rules, rate limits, and symbol information.

**Weight:**
20

**Parameters:**

<table>
<thead>
    <tr>
        <th>Name</th>
        <th>Type</th>
        <th>Mandatory</th>
        <th>Description</th>
    </tr>
</thead>
<tbody>
    <tr>
        <td><code>symbol</code></td>
        <td>STRING</td>
        <td rowspan="5" align="center">NO</td>
        <td>Describe a single symbol</td>
    </tr>
    <tr>
        <td><code>symbols</code></td>
        <td>ARRAY of STRING</td>
        <td>Describe multiple symbols</td>
    </tr>
    <tr>
        <td><code>permissions</code></td>
        <td>ARRAY of STRING</td>
        <td>Filter symbols by permissions</td>
    </tr>
    <tr>
        <td><code>showPermissionSets</code></td>
        <td>BOOLEAN</td>
        <td>Controls whether the content of the <code>permissionSets</code> field is populated or not. Defaults to <code>true</code>.</td>
    </tr>
    <tr>
        <td><code>symbolStatus</code></td>
        <td>ENUM</td>
        <td>Filters for symbols that have this <code>tradingStatus</code>.<br></br> Valid values: <code>TRADING</code>, <code>HALT</code>, <code>BREAK</code> <br> Cannot be used in combination with <code>symbol</code> or <code>symbols</code></td>
    </tr>
</tbody>
</table>

Notes:

* Only one of `symbol`, `symbols`, `permissions` parameters can be specified.

* Without parameters, `exchangeInfo` displays all symbols with `["SPOT, "MARGIN", "LEVERAGED"]` permissions.

  * In order to list *all* active symbols on the exchange, you need to explicitly request all permissions.

* `permissions` accepts either a list of permissions, or a single permission name. E.g. `"SPOT"`.

* [Available Permissions](https://developers.binance.com/docs/binance-spot-api-docs/enums.md#account-and-symbol-permissions)

<a id="examples-of-symbol-permissions-interpretation-from-the-response"></a>

**Examples of Symbol Permissions Interpretation from the Response:**

* `[["A","B"]]` means you may place an order if your account has either permission "A" **or** permission "B".
* `[["A"],["B"]]` means you can place an order if your account has permission "A" **and** permission "B".
* `[["A"],["B","C"]]` means you can place an order if your account has permission "A" **and** permission "B" or permission "C". (Inclusive or is applied here, not exclusive or, so your account may have both permission "B" and permission "C".)

**Data Source:**
Memory

**Response:**
```javascript
{
    "id": "5494febb-d167-46a2-996d-70533eb4d976",
    "status": 200,
    "result": {
        "timezone": "UTC",
        "serverTime": 1655969291181,
        // Global rate limits. See "Rate limits" section.
        "rateLimits": [
            {
                "rateLimitType": "REQUEST_WEIGHT",     // Rate limit type: REQUEST_WEIGHT, ORDERS, CONNECTIONS
                "interval": "MINUTE",                  // Rate limit interval: SECOND, MINUTE, DAY
                "intervalNum": 1,                      // Rate limit interval multiplier (i.e., "1 minute")
                "limit": 6000                          // Rate limit per interval
            },
            {
                "rateLimitType": "ORDERS",
                "interval": "SECOND",
                "intervalNum": 10,
                "limit": 50
            },
            {
                "rateLimitType": "ORDERS",
                "interval": "DAY",
                "intervalNum": 1,
                "limit": 160000
            },
            {
                "rateLimitType": "CONNECTIONS",
                "interval": "MINUTE",
                "intervalNum": 5,
                "limit": 300
            }
        ],
        // Exchange filters are explained on the "Filters" page:
        // https://github.com/binance/binance-spot-api-docs/blob/master/filters.md
        // All exchange filters are optional.
        "exchangeFilters": [],
        "symbols": [
            {
                "symbol": "BNBBTC",
                "status": "TRADING",
                "baseAsset": "BNB",
                "baseAssetPrecision": 8,
                "quoteAsset": "BTC",
                "quotePrecision": 8,
                "quoteAssetPrecision": 8,
                "baseCommissionPrecision": 8,
                "quoteCommissionPrecision": 8,
                "orderTypes": [
                    "LIMIT",
                    "LIMIT_MAKER",
                    "MARKET",
                    "STOP_LOSS_LIMIT",
                    "TAKE_PROFIT_LIMIT"
                ],
                "icebergAllowed": true,
                "ocoAllowed": true,
                "otoAllowed": true,
                "opoAllowed": true,
                "quoteOrderQtyMarketAllowed": true,
                "allowTrailingStop": true,
                "cancelReplaceAllowed": true,
                "amendAllowed": false,
                "pegInstructionsAllowed": true,
                "isSpotTradingAllowed": true,
                "isMarginTradingAllowed": true,
                // Symbol filters are explained on the "Filters" page:
                // https://github.com/binance/binance-spot-api-docs/blob/master/filters.md
                // All symbol filters are optional.
                "filters": [
                    {
                        "filterType": "PRICE_FILTER",
                        "minPrice": "0.00000100",
                        "maxPrice": "100000.00000000",
                        "tickSize": "0.00000100"
                    },
                    {
                        "filterType": "LOT_SIZE",
                        "minQty": "0.00100000",
                        "maxQty": "100000.00000000",
                        "stepSize": "0.00100000"
                    }
                ],
                "permissions": [],
                "permissionSets": [["SPOT", "MARGIN", "TRD_GRP_004"]],
                "defaultSelfTradePreventionMode": "NONE",
                "allowedSelfTradePreventionModes": ["NONE"]
            }
        ],
        // Optional field. Present only when SOR is available.
        // https://github.com/binance/binance-spot-api-docs/blob/master/faqs/sor_faq.md
        "sors": [
            {
                "baseAsset": "BTC",
                "symbols": ["BTCUSDT", "BTCUSDC"]
            }
        ]
    },
    "rateLimits": [
        {
            "rateLimitType": "REQUEST_WEIGHT",
            "interval": "MINUTE",
            "intervalNum": 1,
            "limit": 6000,
            "count": 20
        }
    ]
}
```

### Query Execution Rules

```javascript
{
    "id": "5162affb-0aba-4821-b475-f2625006eb43",
    "method": "executionRules",
    "params": {
        "symbol": "BAZUSD"
    }
}
```

**Weight**

Parameter | Weight|
---        | ---
`symbol`  | 2
`symbols` | 2 for each `symbol`, capped at a max of 40|
`symbolStatus` |40|
None            |40|

**Parameters:**

Name | Type | Mandatory | Description
------------ | ------------ | ------------ | ------------
`symbol`   | STRING| No      | Query for specified symbol
`symbols`  | STRING | No     | Query for multiple symbols
`symbolStatus` |ENUM| No |Query for all symbols with the specified status. Supported values: `TRADING`, `HALT`, `BREAK`

**Note:** No combination of multiple parameters is allowed.

**Data Source:** Memory

**Response:**

```javascript
{
  "id": "5162affb-0aba-4821-b475-f2625006eb43",
  "status": 200,
  "result": {
    "symbolRules": [
      {
        "symbol": "BAZUSD",
        "rules": [
          {
            "ruleType": "PRICE_RANGE",
            "bidLimitMultUp": "1.0001",
            "bidLimitMultDown": "0.9999",
            "askLimitMultUp": "1.0001",
            "askLimitMultDown": "0.9999"
          }
        ]
      }
    ]
  }
}
```
