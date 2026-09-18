---
document_id: AI4B-BINANCE-IFC-107
title: Binance WebSocket API Order List Requests Reference
document_type: INTERFACE_CONTRACT
version: 1.0.0
status: ACTIVE
owner: Enterprise Governance
authority_level: EXTERNAL_AUTHORITY
authority_layer: L3_CANONICAL_CONTRACTS_SCHEMAS
authority_scope: binance_websocket_api_order_list_requests
content_role: DERIVED
source_of_truth: false
canonical_path: docs/contracts/interface_contract_binance_websocket_api_order_list_requests.md
machine_enforceable: false
audit_required: true
classification: INTERNAL
---
# Binance WebSocket API Order List Requests Reference

## ELI10

This document keeps order-list and SOR request formats in a focused file.

## Source Lineage

- Source file: `docs/contracts/interface_contract_binance_websocket_api_reference.md`
- Source section start: `### Order lists`
- This file preserves a bounded section of the governed source document.

### Order lists

#### Place new OCO - Deprecated (TRADE)

```javascript
{
    "id": "56374a46-3061-486b-a311-99ee972eb648",
    "method": "orderList.place",
    "params": {
        "symbol": "BTCUSDT",
        "side": "SELL",
        "price": "23420.00000000",
        "quantity": "0.00650000",
        "stopPrice": "23410.00000000",
        "stopLimitPrice": "23405.00000000",
        "stopLimitTimeInForce": "GTC",
        "newOrderRespType": "RESULT",
        "apiKey": "key",
        "signature": "6689c2a36a639ff3915c2904871709990ab65f3c7a9ff13857558fd350315c35",
        "timestamp": 1660801713767
    }
}
```

Send in a new one-cancels-the-other (OCO) pair:
`LIMIT_MAKER` + `STOP_LOSS`/`STOP_LOSS_LIMIT` orders (called *legs*),
where activation of one order immediately cancels the other.

This adds 1 order to `EXCHANGE_MAX_ORDERS` filter and the `MAX_NUM_ORDERS` filter

**Weight:**
1

**Unfilled Order Count:**
1

**Parameters:**

Name                | Type    | Mandatory | Description
------------------- | ------- | --------- | ------------
`symbol`            | STRING  | YES       |
`side`              | ENUM    | YES       | `BUY` or `SELL`
`price`             | DECIMAL | YES       | Price for the limit order
`quantity`          | DECIMAL | YES       |
`listClientOrderId` | STRING  | NO        | Arbitrary unique ID among open order lists. Automatically generated if not sent
`limitClientOrderId`| STRING  | NO        | Arbitrary unique ID among open orders for the limit order. Automatically generated if not sent
`limitIcebergQty`   | DECIMAL | NO        |
`limitStrategyId`   | LONG     | NO        | Arbitrary numeric value identifying the limit order within an order strategy.
`limitStrategyType` | INT     | NO        | <p>Arbitrary numeric value identifying the limit order strategy.</p><p>Values smaller than `1000000` are reserved and cannot be used.</p>
`stopPrice`         | DECIMAL | YES *     | Either `stopPrice` or `trailingDelta`, or both must be specified
`trailingDelta`     | INT     | YES *     | See [Trailing Stop order FAQ](https://developers.binance.com/docs/binance-spot-api-docs/faqs/trailing-stop-faq.md)
`stopClientOrderId` | STRING  | NO        | Arbitrary unique ID among open orders for the stop order. Automatically generated if not sent
`stopLimitPrice`    | DECIMAL | NO *      |
`stopLimitTimeInForce` | ENUM | NO *      | See [`order.place`](#timeInForce) for available options
`stopIcebergQty`    | DECIMAL | NO *      |
`stopStrategyId`    | LONG     | NO        | Arbitrary numeric value identifying the stop order within an order strategy.
`stopStrategyType`  | INT     | NO        | <p>Arbitrary numeric value identifying the stop order strategy.</p><p>Values smaller than `1000000` are reserved and cannot be used.</p>
`newOrderRespType`  | ENUM    | NO        | Select response format: `ACK`, `RESULT`, `FULL` (default)
`selfTradePreventionMode` |ENUM | NO      | The allowed enums is dependent on what is configured on the symbol. The possible supported values are: [STP Modes](https://developers.binance.com/docs/binance-spot-api-docs/enums.md#stpmodes)
`apiKey`            | STRING  | YES       |
`recvWindow`        | DECIMAL | NO        | The value cannot be greater than `60000`. <br> Supports up to three decimal places of precision (e.g., 6000.346) so that microseconds may be specified.
`signature`         | STRING  | YES       |
`timestamp`         | LONG    | YES       |

Notes:

* `listClientOrderId` parameter specifies `listClientOrderId` for the OCO pair.

  A new OCO with the same `listClientOrderId` is accepted only when the previous one is filled or completely expired.

  `listClientOrderId` is distinct from `clientOrderId` of individual orders.

* `limitClientOrderId` and `stopClientOrderId` specify `clientOrderId` values for both legs of the OCO.

  A new order with the same `clientOrderId` is accepted only when the previous one is filled or expired.

* Price restrictions on the legs:

  | `side` | Price relation |
  | ------ | -------------- |
  | `BUY`  | `price` < market price < `stopPrice` |
  | `SELL` | `price` > market price > `stopPrice` |

* Both legs have the same `quantity`.

  However, you can set different iceberg quantity for individual legs.

  If `stopIcebergQty` is used, `stopLimitTimeInForce` must be `GTC`.

* `trailingDelta` applies only to the `STOP_LOSS`/`STOP_LOSS_LIMIT` leg of the OCO.

**Data Source:**
Matching Engine

**Response:**

Response format for `orderReports` is selected using the `newOrderRespType` parameter.
The following example is for `RESULT` response type.
See [`order.place`](#place-new-order-trade) for more examples.

```javascript
{
    "id": "57833dc0-e3f2-43fb-ba20-46480973b0aa",
    "status": 200,
    "result": {
        "orderListId": 1274512,
        "contingencyType": "OCO",
        "listStatusType": "EXEC_STARTED",
        "listOrderStatus": "EXECUTING",
        "listClientOrderId": "08985fedd9ea2cf6b28996",
        "transactionTime": 1660801713793,
        "symbol": "BTCUSDT",
        "orders": [
            {
                "symbol": "BTCUSDT",
                "orderId": 12569138901,
                "clientOrderId": "BqtFCj5odMoWtSqGk2X9tU"
            },
            {
                "symbol": "BTCUSDT",
                "orderId": 12569138902,
                "clientOrderId": "jLnZpj5enfMXTuhKB1d0us"
            }
        ],
        "orderReports": [
            {
                "symbol": "BTCUSDT",
                "orderId": 12569138901,
                "orderListId": 1274512,
                "clientOrderId": "BqtFCj5odMoWtSqGk2X9tU",
                "transactTime": 1660801713793,
                "price": "23410.00000000",
                "origQty": "0.00650000",
                "executedQty": "0.00000000",
                "origQuoteOrderQty": "0.000000",
                "cummulativeQuoteQty": "0.00000000",
                "status": "NEW",
                "timeInForce": "GTC",
                "type": "STOP_LOSS_LIMIT",
                "side": "SELL",
                "stopPrice": "23405.00000000",
                "workingTime": -1,
                "selfTradePreventionMode": "NONE"
            },
            {
                "symbol": "BTCUSDT",
                "orderId": 12569138902,
                "orderListId": 1274512,
                "clientOrderId": "jLnZpj5enfMXTuhKB1d0us",
                "transactTime": 1660801713793,
                "price": "23420.00000000",
                "origQty": "0.00650000",
                "executedQty": "0.00000000",
                "origQuoteOrderQty": "0.000000",
                "cummulativeQuoteQty": "0.00000000",
                "status": "NEW",
                "timeInForce": "GTC",
                "type": "LIMIT_MAKER",
                "side": "SELL",
                "workingTime": 1660801713793,
                "selfTradePreventionMode": "NONE"
            }
        ]
    },
    "rateLimits": [
        {
            "rateLimitType": "ORDERS",
            "interval": "SECOND",
            "intervalNum": 10,
            "limit": 50,
            "count": 2
        },
        {
            "rateLimitType": "ORDERS",
            "interval": "DAY",
            "intervalNum": 1,
            "limit": 160000,
            "count": 2
        },
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

#### Place new Order list - OCO (TRADE)

```javascript
{
    "id": "56374a46-3261-486b-a211-99ed972eb648",
    "method": "orderList.place.oco",
    "params": {
        "symbol": "LTCBNB",
        "side": "BUY",
        "quantity": 1,
        "timestamp": 1711062760647,
        "aboveType": "STOP_LOSS_LIMIT",
        "abovePrice": "1.5",
        "aboveStopPrice": "1.50000001",
        "aboveTimeInForce": "GTC",
        "belowType": "LIMIT_MAKER",
        "belowPrice": "1.49999999",
        "apiKey": "key",
        "signature": "64614cfd8dd38260d4fd86d3c455dbf4b9d1c8a8170ea54f700592a986c30ddb"
    }
}
```

Send in an one-cancels-the-other (OCO) pair, where activation of one order immediately cancels the other.

* An OCO has 2 orders called the **above order** and **below order**.
* One of the orders must be a `LIMIT_MAKER/TAKE_PROFIT/TAKE_PROFIT_LIMIT` order and the other must be `STOP_LOSS` or `STOP_LOSS_LIMIT` order.
* Price restrictions:
  * If the OCO is on the `SELL` side:
    * `LIMIT_MAKER/TAKE_PROFIT_LIMIT` `price` > Last Traded Price > `STOP_LOSS/STOP_LOSS_LIMIT` `stopPrice`
    * `TAKE_PROFIT stopPrice` > Last Traded Price > `STOP_LOSS/STOP_LOSS_LIMIT stopPrice`
  * If the OCO is on the `BUY` side:
    * `LIMIT_MAKER` `price` < Last Traded Price < `STOP_LOSS/STOP_LOSS_LIMIT` `stopPrice`
    * `TAKE_PROFIT stopPrice` > Last Traded Price > `STOP_LOSS/STOP_LOSS_LIMIT stopPrice`
* OCOs add **2 orders** to the `EXCHANGE_MAX_ORDERS` filter and `MAX_NUM_ORDERS` filter.

**Weight:**
1

**Unfilled Order Count:**
2

**Parameters:**

Name                     |Type    | Mandatory | Description
-----                    |------  | -----     |----
`symbol`                 |STRING  |YES        |
`listClientOrderId`      |STRING  |NO         |Arbitrary unique ID among open order lists. Automatically generated if not sent. <br> A new order list with the same `listClientOrderId` is accepted only when the previous one is filled or completely expired. <br> `listClientOrderId` is distinct from the `aboveClientOrderId` and the `belowCLientOrderId`.
`side`                   |ENUM    |YES        |`BUY` or `SELL`
`quantity`               |DECIMAL |YES        |Quantity for both orders of the order list.
`aboveType`              |ENUM    |YES        |Supported values: `STOP_LOSS_LIMIT`, `STOP_LOSS`, `LIMIT_MAKER`, `TAKE_PROFIT`, `TAKE_PROFIT_LIMIT`
`aboveClientOrderId`     |STRING  |NO         |Arbitrary unique ID among open orders for the above order. Automatically generated if not sent
`aboveIcebergQty`        |LONG    |NO         |Note that this can only be used if `aboveTimeInForce` is `GTC`.
`abovePrice`             |DECIMAL |NO         |Can be used if `aboveType` is `STOP_LOSS_LIMIT` , `LIMIT_MAKER`, or `TAKE_PROFIT_LIMIT` to specify the limit price.
`aboveStopPrice`         |DECIMAL |NO         |Can be used if `aboveType` is `STOP_LOSS`, `STOP_LOSS_LIMIT`, `TAKE_PROFIT`, `TAKE_PROFIT_LIMIT`. <br>Either `aboveStopPrice` or `aboveTrailingDelta` or both, must be specified.
`aboveTrailingDelta`     |LONG    |NO         |See [Trailing Stop order FAQ](https://developers.binance.com/docs/binance-spot-api-docs/faqs/trailing-stop-faq.md).
`aboveTimeInForce`       |ENUM    |NO         |Required if `aboveType` is `STOP_LOSS_LIMIT` or `TAKE_PROFIT_LIMIT`.
`aboveStrategyId`        |LONG    |NO         |Arbitrary numeric value identifying the above order within an order strategy.
`aboveStrategyType`      |INT     |NO         |Arbitrary numeric value identifying the above order strategy. <br>Values smaller than 1000000 are reserved and cannot be used.
`abovePegPriceType`      |ENUM    |NO         |See [Pegged Orders](#pegged-orders-info)
`abovePegOffsetType`     |ENUM    |NO         |
`abovePegOffsetValue`    |INT     |NO         |
`belowType`              |ENUM    |YES        |Supported values: `STOP_LOSS`, `STOP_LOSS_LIMIT`, `TAKE_PROFIT`,`TAKE_PROFIT_LIMIT`
`belowClientOrderId`     |STRING  |NO         |
`belowIcebergQty`        |LONG    |NO         |Note that this can only be used if `belowTimeInForce` is `GTC`.
`belowPrice`             |DECIMAL |NO         |Can be used if `belowType` is `STOP_LOSS_LIMIT` , `LIMIT_MAKER`, or `TAKE_PROFIT_LIMIT` to specify the limit price.
`belowStopPrice`         |DECIMAL |NO         |Can be used if `belowType` is `STOP_LOSS`, `STOP_LOSS_LIMIT`, `TAKE_PROFIT` or `TAKE_PROFIT_LIMIT`. <br>Either `belowStopPrice` or `belowTrailingDelta` or both, must be specified.
`belowTrailingDelta`     |LONG    |NO         |See [Trailing Stop order FAQ](https://developers.binance.com/docs/binance-spot-api-docs/faqs/trailing-stop-faq.md).
`belowTimeInForce`       |ENUM    |NO         |Required if `belowType` is `STOP_LOSS_LIMIT` or `TAKE_PROFIT_LIMIT`
`belowStrategyId`        |LONG    |NO         |Arbitrary numeric value identifying the below order within an order strategy.
`belowStrategyType`      |INT     |NO         |Arbitrary numeric value identifying the below order strategy. <br>Values smaller than 1000000 are reserved and cannot be used.
`belowPegPriceType`      |ENUM    |NO         |See [Pegged Orders](#pegged-orders-info)
`belowPegOffsetType`     |ENUM    |NO         |
`belowPegOffsetValue`    |INT     |NO         |
`newOrderRespType`       |ENUM    |NO         |Select response format: `ACK`, `RESULT`, `FULL`
`selfTradePreventionMode`|ENUM    |NO         |The allowed enums is dependent on what is configured on the symbol. The possible supported values are: [STP Modes](https://developers.binance.com/docs/binance-spot-api-docs/enums.md#stpmodes).
`apiKey`                 |STRING  |YES        |
`recvWindow`             |DECIMAL |NO         |The value cannot be greater than `60000`. <br> Supports up to three decimal places of precision (e.g., 6000.346) so that microseconds may be specified.
`timestamp`              |LONG    |YES        |
`signature`              |STRING  |YES        |

**Data Source:**
Matching Engine

**Response:**

Response format for `orderReports` is selected using the `newOrderRespType` parameter.
The following example is for `RESULT` response type.
See [`order.place`](#place-new-order-trade) for more examples.

```javascript
{
    "id": "56374a46-3261-486b-a211-99ed972eb648",
    "status": 200,
    "result": {
        "orderListId": 2,
        "contingencyType": "OCO",
        "listStatusType": "EXEC_STARTED",
        "listOrderStatus": "EXECUTING",
        "listClientOrderId": "cKPMnDCbcLQILtDYM4f4fX",
        "transactionTime": 1711062760648,
        "symbol": "LTCBNB",
        "orders": [
            {
                "symbol": "LTCBNB",
                "orderId": 2,
                "clientOrderId": "0m6I4wfxvTUrOBSMUl0OPU"
            },
            {
                "symbol": "LTCBNB",
                "orderId": 3,
                "clientOrderId": "Z2IMlR79XNY5LU0tOxrWyW"
            }
        ],
        "orderReports": [
            {
                "symbol": "LTCBNB",
                "orderId": 2,
                "orderListId": 2,
                "clientOrderId": "0m6I4wfxvTUrOBSMUl0OPU",
                "transactTime": 1711062760648,
                "price": "1.50000000",
                "origQty": "1.000000",
                "executedQty": "0.000000",
                "origQuoteOrderQty": "0.000000",
                "cummulativeQuoteQty": "0.00000000",
                "status": "NEW",
                "timeInForce": "GTC",
                "type": "STOP_LOSS_LIMIT",
                "side": "BUY",
                "stopPrice": "1.50000001",
                "workingTime": -1,
                "selfTradePreventionMode": "NONE"
            },
            {
                "symbol": "LTCBNB",
                "orderId": 3,
                "orderListId": 2,
                "clientOrderId": "Z2IMlR79XNY5LU0tOxrWyW",
                "transactTime": 1711062760648,
                "price": "1.49999999",
                "origQty": "1.000000",
                "executedQty": "0.000000",
                "origQuoteOrderQty": "0.000000",
                "cummulativeQuoteQty": "0.00000000",
                "status": "NEW",
                "timeInForce": "GTC",
                "type": "LIMIT_MAKER",
                "side": "BUY",
                "workingTime": 1711062760648,
                "selfTradePreventionMode": "NONE"
            }
        ]
    },
    "rateLimits": [
        {
            "rateLimitType": "ORDERS",
            "interval": "SECOND",
            "intervalNum": 10,
            "limit": 50,
            "count": 2
        },
        {
            "rateLimitType": "ORDERS",
            "interval": "DAY",
            "intervalNum": 1,
            "limit": 160000,
            "count": 2
        },
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

#### Place new Order list - OTO (TRADE)

```javascript
{
    "id": "1712544395950",
    "method": "orderList.place.oto",
    "params": {
        "signature": "3e1e5ac8690b0caf9a2afd5c5de881ceba69939cc9d817daead5386bf65d0cbb",
        "apiKey": "key",
        "pendingQuantity": 1,
        "pendingSide": "BUY",
        "pendingType": "MARKET",
        "symbol": "LTCBNB",
        "recvWindow": "5000",
        "timestamp": "1712544395951",
        "workingPrice": 1,
        "workingQuantity": 1,
        "workingSide": "SELL",
        "workingTimeInForce": "GTC",
        "workingType": "LIMIT"
    }
}
```

Places an OTO.

* An OTO (One-Triggers-the-Other) is an order list comprised of 2 orders.
* The first order is called the **working order** and must be `LIMIT` or `LIMIT_MAKER`. Initially, only the working order goes on the order book.
* The second order is called the **pending order**. It can be any order type except for `MARKET` orders using parameter `quoteOrderQty`. The pending order is only placed on the order book when the working order gets **fully filled**.
* If either the working order or the pending order is cancelled individually, the other order in the order list will also be canceled or expired.
* When the order list is placed, if the working order gets **immediately fully filled**, the placement response will show the working order as `FILLED` but the pending order will still appear as `PENDING_NEW`. You need to query the status of the pending order again to see its updated status.
* OTOs add **2 orders** to the `EXCHANGE_MAX_NUM_ORDERS` filter and `MAX_NUM_ORDERS` filter.

**Weight:** 1

**Unfilled Order Count:**
2

**Parameters:**

Name                   |Type   |Mandatory | Description
----                   |----   |------    |------
`symbol`                 |STRING |YES       |
`listClientOrderId`      |STRING |NO        |Arbitrary unique ID among open order lists. Automatically generated if not sent. <br>A new order list with the same listClientOrderId is accepted only when the previous one is filled or completely expired. <br> `listClientOrderId` is distinct from the `workingClientOrderId` and the `pendingClientOrderId`.
`newOrderRespType`       |ENUM   |NO        |Format of the JSON response. Supported values: [Order Response Type](https://developers.binance.com/docs/binance-spot-api-docs/enums.md#orderresponsetype)
`selfTradePreventionMode`|ENUM   |NO        |The allowed values are dependent on what is configured on the symbol. Supported values: [STP Modes](https://developers.binance.com/docs/binance-spot-api-docs/enums.md#stpmodes)
`workingType`            |ENUM   |YES       |Supported values: `LIMIT`,`LIMIT_MAKER`
`workingSide`            |ENUM   |YES       |Supported values: [Order side](https://developers.binance.com/docs/binance-spot-api-docs/enums.md#side)
`workingClientOrderId`   |STRING |NO        |Arbitrary unique ID among open orders for the working order.<br> Automatically generated if not sent.
`workingPrice`           |DECIMAL|YES       |
`workingQuantity`        |DECIMAL|YES       |Sets the quantity for the working order.
`workingIcebergQty`      |DECIMAL|NO       |This can only be used if `workingTimeInForce` is `GTC`, or if `workingType` is `LIMIT_MAKER`.
`workingTimeInForce`     |ENUM   |NO        |Supported values: [Time In Force](https://developers.binance.com/docs/binance-spot-api-docs/enums.md#timeinforce)
`workingStrategyId`      |LONG   |NO        |Arbitrary numeric value identifying the working order within an order strategy.
`workingStrategyType`    |INT    |NO        |Arbitrary numeric value identifying the working order strategy. <br> Values smaller than 1000000 are reserved and cannot be used.
`workingPegPriceType`    |ENUM   |NO        |See [Pegged Orders](#pegged-orders-info)
`workingPegOffsetType`   |ENUM   |NO        |
`workingPegOffsetValue`  |INT    |NO        |
`pendingType`            |ENUM   |YES       |Supported values: [Order types](#order-type). <br> Note that `MARKET` orders using `quoteOrderQty` are not supported.
`pendingSide`            |ENUM   |YES       |Supported values: [Order side](https://developers.binance.com/docs/binance-spot-api-docs/enums.md#side)
`pendingClientOrderId`   |STRING |NO        |Arbitrary unique ID among open orders for the pending order.<br> Automatically generated if not sent.
`pendingPrice`           |DECIMAL|NO        |
`pendingStopPrice`       |DECIMAL|NO        |
`pendingTrailingDelta`   |DECIMAL|NO        |
`pendingQuantity`        |DECIMAL|YES       |Sets the quantity for the pending order.
`pendingIcebergQty`      |DECIMAL|NO        |This can only be used if `pendingTimeInForce` is `GTC`, or if `pendingType` is `LIMIT_MAKER`.
`pendingTimeInForce`     |ENUM   |NO        |Supported values: [Time In Force](https://developers.binance.com/docs/binance-spot-api-docs/enums.md#timeinforce)
`pendingStrategyId`      |LONG   |NO        |Arbitrary numeric value identifying the pending order within an order strategy.
`pendingStrategyType`    |INT    |NO        |Arbitrary numeric value identifying the pending order strategy. <br> Values smaller than 1000000 are reserved and cannot be used.
`pendingPegOffsetType`   |ENUM   |NO        |See [Pegged Orders](#pegged-orders-info)
`pendingPegPriceType`    |ENUM   |NO        |
`pendingPegOffsetValue`  |INT    |NO        |
`recvWindow`             |DECIMAL|NO        |The value cannot be greater than `60000`. <br> Supports up to three decimal places of precision (e.g., 6000.346) so that microseconds may be specified.
`timestamp`              |LONG   |YES       |
`signature`              |STRING |YES       |

<a id="mandatory-parameters-based-on-pendingtype-or-workingtype"></a>

**Mandatory parameters based on `pendingType` or `workingType`**

Depending on the `pendingType` or `workingType`, some optional parameters will become mandatory.

|Type                                                  |Additional mandatory parameters|Additional information|
|----                                                  |----                           |------
|`workingType` = `LIMIT`                               |`workingTimeInForce`           |
|`pendingType` = `LIMIT`                                |`pendingPrice`, `pendingTimeInForce`          |
|`pendingType` = `STOP_LOSS` or `TAKE_PROFIT`           |`pendingStopPrice` and/or `pendingTrailingDelta`|
|`pendingType` =`STOP_LOSS_LIMIT` or `TAKE_PROFIT_LIMIT`|`pendingPrice`, `pendingStopPrice` and/or `pendingTrailingDelta`, `pendingTimeInForce`|

**Data Source:**
Matching Engine

**Response:**

```javascript
{
    "id": "1712544395950",
    "status": 200,
    "result": {
        "orderListId": 626,
        "contingencyType": "OTO",
        "listStatusType": "EXEC_STARTED",
        "listOrderStatus": "EXECUTING",
        "listClientOrderId": "KA4EBjGnzvSwSCQsDdTrlf",
        "transactionTime": 1712544395981,
        "symbol": "1712544378871",
        "orders": [
            {
                "symbol": "LTCBNB",
                "orderId": 13,
                "clientOrderId": "YiAUtM9yJjl1a2jXHSp9Ny"
            },
            {
                "symbol": "LTCBNB",
                "orderId": 14,
                "clientOrderId": "9MxJSE1TYkmyx5lbGLve7R"
            }
        ],
        "orderReports": [
            {
                "symbol": "LTCBNB",
                "orderId": 13,
                "orderListId": 626,
                "clientOrderId": "YiAUtM9yJjl1a2jXHSp9Ny",
                "transactTime": 1712544395981,
                "price": "1.000000",
                "origQty": "1.000000",
                "executedQty": "0.000000",
                "origQuoteOrderQty": "0.000000",
                "cummulativeQuoteQty": "0.000000",
                "status": "NEW",
                "timeInForce": "GTC",
                "type": "LIMIT",
                "side": "SELL",
                "workingTime": 1712544395981,
                "selfTradePreventionMode": "NONE"
            },
            {
                "symbol": "LTCBNB",
                "orderId": 14,
                "orderListId": 626,
                "clientOrderId": "9MxJSE1TYkmyx5lbGLve7R",
                "transactTime": 1712544395981,
                "price": "0.000000",
                "origQty": "1.000000",
                "executedQty": "0.000000",
                "origQuoteOrderQty": "0.000000",
                "cummulativeQuoteQty": "0.000000",
                "status": "PENDING_NEW",
                "timeInForce": "GTC",
                "type": "MARKET",
                "side": "BUY",
                "workingTime": -1,
                "selfTradePreventionMode": "NONE"
            }
        ]
    },
    "rateLimits": [
        {
            "rateLimitType": "ORDERS",
            "interval": "MINUTE",
            "intervalNum": 1,
            "limit": 10000000,
            "count": 10
        },
        {
            "rateLimitType": "REQUEST_WEIGHT",
            "interval": "MINUTE",
            "intervalNum": 1,
            "limit": 1000,
            "count": 38
        }
    ]
}
```

**Note:** The payload above does not show all fields that can appear. Please refer to [Conditional fields in Order Responses](#conditional-fields-in-order-responses).

#### Place new Order list - OTOCO (TRADE)

```javascript
{
    "id": "1712544408508",
    "method": "orderList.place.otoco",
    "params": {
        "signature": "c094473304374e1b9c5f7e2558358066cfa99df69f50f63d09cfee755136cb07",
        "apiKey": "key",
        "pendingQuantity": 5,
        "pendingSide": "SELL",
        "pendingBelowPrice": 5,
        "pendingBelowType": "LIMIT_MAKER",
        "pendingAboveStopPrice": 0.5,
        "pendingAboveType": "STOP_LOSS",
        "symbol": "LTCBNB",
        "recvWindow": "5000",
        "timestamp": "1712544408509",
        "workingPrice": 1.5,
        "workingQuantity": 1,
        "workingSide": "BUY",
        "workingTimeInForce": "GTC",
        "workingType": "LIMIT"
    }
}
```

Place an OTOCO.

* An OTOCO (One-Triggers-One-Cancels-the-Other) is an order list comprised of 3 orders.
* The first order is called the **working order** and must be `LIMIT` or `LIMIT_MAKER`. Initially, only the working order goes on the order book.
  * The behavior of the working order is the same as the [OTO](#place-new-order-list---oto-trade).
* OTOCO has 2 pending orders (pending above and pending below), forming an OCO pair. The pending orders are only placed on the order book when the working order gets **fully filled**.
    * The rules of the pending above and pending below follow the same rules as the [Order list OCO](#place-new-order-list---oco-trade).
* OTOCOs add **3 orders** to the `EXCHANGE_MAX_NUM_ORDERS` filter and `MAX_NUM_ORDERS` filter.

**Weight:** 1

**Unfilled Order Count:**
3

**Parameters:**

Name                     |Type   |Mandatory | Description
----                     |----   |------    |------
`symbol`                   |STRING |YES       |
`listClientOrderId`        |STRING |NO        |Arbitrary unique ID among open order lists. Automatically generated if not sent. <br>A new order list with the same listClientOrderId is accepted only when the previous one is filled or completely expired. <br> `listClientOrderId` is distinct from the `workingClientOrderId`, `pendingAboveClientOrderId`, and the `pendingBelowClientOrderId`.
`newOrderRespType`         |ENUM   |NO        |Format of the JSON response. Supported values: [Order Response Type](https://developers.binance.com/docs/binance-spot-api-docs/enums.md#orderresponsetype)
`selfTradePreventionMode`  |ENUM   |NO        |The allowed values are dependent on what is configured on the symbol. Supported values: [STP Modes](https://developers.binance.com/docs/binance-spot-api-docs/enums.md#stpmodes)
`workingType`              |ENUM   |YES       |Supported values: `LIMIT`, `LIMIT_MAKER`
`workingSide`              |ENUM   |YES       |Supported values: [Order Side](https://developers.binance.com/docs/binance-spot-api-docs/enums.md#side)
`workingClientOrderId`     |STRING |NO        |Arbitrary unique ID among open orders for the working order.<br> Automatically generated if not sent.
`workingPrice`             |DECIMAL|YES       |
`workingQuantity`          |DECIMAL|YES       |
`workingIcebergQty`        |DECIMAL|NO        |This can only be used if `workingTimeInForce` is `GTC`, or if `workingType` is `LIMIT_MAKER`.
`workingTimeInForce`       |ENUM   |NO        |Supported values: [Time In Force](https://developers.binance.com/docs/binance-spot-api-docs/enums.md#timeinforce)
`workingStrategyId`        |LONG    |NO        |Arbitrary numeric value identifying the working order within an order strategy.
`workingStrategyType`      |INT    |NO        |Arbitrary numeric value identifying the working order strategy. <br> Values smaller than 1000000 are reserved and cannot be used.
`workingPegPriceType`      |ENUM   |NO        |See [Pegged Orders](#pegged-orders-info)
`workingPegOffsetType`     |ENUM   |NO        |
`workingPegOffsetValue`    |INT    |NO        |
`pendingSide`              |ENUM   |YES       |Supported values: [Order Side](https://developers.binance.com/docs/binance-spot-api-docs/enums.md#side)
`pendingQuantity`          |DECIMAL|YES       |
`pendingAboveType`         |ENUM   |YES       |Supported values: `STOP_LOSS_LIMIT`, `STOP_LOSS`, `LIMIT_MAKER`, `TAKE_PROFIT`, `TAKE_PROFIT_LIMIT`
`pendingAboveClientOrderId`|STRING |NO        |Arbitrary unique ID among open orders for the pending above order.<br> Automatically generated if not sent.
`pendingAbovePrice`        |DECIMAL|NO        |Can be used if `pendingAboveType` is `STOP_LOSS_LIMIT` , `LIMIT_MAKER`, or `TAKE_PROFIT_LIMIT` to specify the limit price.
`pendingAboveStopPrice`    |DECIMAL|NO        |Can be used if `pendingAboveType` is `STOP_LOSS`, `STOP_LOSS_LIMIT`, `TAKE_PROFIT`, `TAKE_PROFIT_LIMIT`
`pendingAboveTrailingDelta`|DECIMAL|NO        |See [Trailing Stop FAQ](https://developers.binance.com/docs/binance-spot-api-docs/faqs/trailing-stop-faq.md)
`pendingAboveIcebergQty`   |DECIMAL|NO        |This can only be used if `pendingAboveTimeInForce` is `GTC` or if `pendingAboveType` is `LIMIT_MAKER`.
`pendingAboveTimeInForce`  |ENUM   |NO        |
`pendingAboveStrategyId`   |LONG    |NO        |Arbitrary numeric value identifying the pending above order within an order strategy.
`pendingAboveStrategyType` |INT    |NO        |Arbitrary numeric value identifying the pending above order strategy. <br> Values smaller than 1000000 are reserved and cannot be used.
`pendingAbovePegPriceType` |ENUM   |NO        |See [Pegged Orders](#pegged-orders-info)
`pendingAbovePegOffsetType`|ENUM   |NO        |
`pendingAbovePegOffsetValue` |INT  |NO        |
`pendingBelowType`         |ENUM   |NO        |Supported values: `STOP_LOSS`, `STOP_LOSS_LIMIT`, `TAKE_PROFIT`,`TAKE_PROFIT_LIMIT`
`pendingBelowClientOrderId`|STRING |NO        |Arbitrary unique ID among open orders for the pending below order.<br> Automatically generated if not sent.
`pendingBelowPrice`        |DECIMAL|NO        |Can be used if `pendingBelowType` is `STOP_LOSS_LIMIT` or `TAKE_PROFIT_LIMIT` to specify the limit price.
`pendingBelowStopPrice`    |DECIMAL|NO        |Can be used if `pendingBelowType` is `STOP_LOSS`, `STOP_LOSS_LIMIT, TAKE_PROFIT or TAKE_PROFIT_LIMIT`. <br>Either `pendingBelowStopPrice` or `pendingBelowTrailingDelta` or both, must be specified.
`pendingBelowTrailingDelta`|DECIMAL|NO        |
`pendingBelowIcebergQty`   |DECIMAL|NO        |This can only be used if `pendingBelowTimeInForce` is `GTC`, or if `pendingBelowType` is `LIMIT_MAKER`.
`pendingBelowTimeInForce`  |ENUM   |NO        |Supported values: [Time In Force](https://developers.binance.com/docs/binance-spot-api-docs/enums.md#timeinforce)
`pendingBelowStrategyId`   |LONG    |NO        |Arbitrary numeric value identifying the pending below order within an order strategy.
`pendingBelowStrategyType` |INT    |NO        |Arbitrary numeric value identifying the pending below order strategy. <br> Values smaller than 1000000 are reserved and cannot be used.
`pendingBelowPegPriceType` |ENUM   |NO        |See [Pegged Orders](#pegged-orders-info)
`pendingBelowPegOffsetType`|ENUM   |NO        |
`pendingBelowPegOffsetValue` |INT  |NO        |
`recvWindow`               |DECIMAL|NO        |The value cannot be greater than `60000`. <br> Supports up to three decimal places of precision (e.g., 6000.346) so that microseconds may be specified.
`timestamp`                |LONG   |YES       |
`signature`                |STRING|YES|

<a id="mandatory-parameters-based-on-pendingabovetype-pendingbelowtype-or-workingtype"></a>

**Mandatory parameters based on `pendingAboveType`, `pendingBelowType` or `workingType`**

Depending on the `pendingAboveType`/`pendingBelowType` or `workingType`, some optional parameters will become mandatory.

|Type                                                       |Additional mandatory parameters|Additional information|
|----                                                       |----                           |------
|`workingType` = `LIMIT`                                    |`workingTimeInForce`           |
|`pendingAboveType`= `LIMIT_MAKER`                                |`pendingAbovePrice`          |
|`pendingAboveType` = `STOP_LOSS/TAKE_PROFIT`         |`pendingAboveStopPrice` and/or `pendingAboveTrailingDelta`|
|`pendingAboveType=STOP_LOSS_LIMIT/TAKE_PROFIT_LIMIT`|`pendingAbovePrice`, `pendingAboveStopPrice` and/or `pendingAboveTrailingDelta`, `pendingAboveTimeInForce`|
|`pendingBelowType`= `LIMIT_MAKER`                                |`pendingBelowPrice`          |
`pendingBelowType= STOP_LOSS/TAKE_PROFIT`         |`pendingBelowStopPrice` and/or `pendingBelowTrailingDelta`|
|`pendingBelowType=STOP_LOSS_LIMIT/TAKE_PROFIT_LIMIT`|`pendingBelowPrice`, `pendingBelowStopPrice` and/or `pendingBelowTrailingDelta`, `pendingBelowTimeInForce`|

**Data Source:**
Matching Engine

**Response:**

```javascript
{
    "id": "1712544408508",
    "status": 200,
    "result": {
        "orderListId": 629,
        "contingencyType": "OTO",
        "listStatusType": "EXEC_STARTED",
        "listOrderStatus": "EXECUTING",
        "listClientOrderId": "GaeJHjZPasPItFj4x7Mqm6",
        "transactionTime": 1712544408537,
        "symbol": "1712544378871",
        "orders": [
            {
                "symbol": "LTCBNB",
                "orderId": 23,
                "clientOrderId": "OVQOpKwfmPCfaBTD0n7e7H"
            },
            {
                "symbol": "LTCBNB",
                "orderId": 24,
                "clientOrderId": "YcCPKCDMQIjNvLtNswt82X"
            },
            {
                "symbol": "LTCBNB",
                "orderId": 25,
                "clientOrderId": "ilpIoShcFZ1ZGgSASKxMPt"
            }
        ],
        "orderReports": [
            {
                "symbol": "LTCBNB",
                "orderId": 23,
                "orderListId": 629,
                "clientOrderId": "OVQOpKwfmPCfaBTD0n7e7H",
                "transactTime": 1712544408537,
                "price": "1.500000",
                "origQty": "1.000000",
                "executedQty": "0.000000",
                "origQuoteOrderQty": "0.000000",
                "cummulativeQuoteQty": "0.000000",
                "status": "NEW",
                "timeInForce": "GTC",
                "type": "LIMIT",
                "side": "BUY",
                "workingTime": 1712544408537,
                "selfTradePreventionMode": "NONE"
            },
            {
                "symbol": "LTCBNB",
                "orderId": 24,
                "orderListId": 629,
                "clientOrderId": "YcCPKCDMQIjNvLtNswt82X",
                "transactTime": 1712544408537,
                "price": "0.000000",
                "origQty": "5.000000",
                "executedQty": "0.000000",
                "origQuoteOrderQty": "0.000000",
                "cummulativeQuoteQty": "0.000000",
                "status": "PENDING_NEW",
                "timeInForce": "GTC",
                "type": "STOP_LOSS",
                "side": "SELL",
                "stopPrice": "0.500000",
                "workingTime": -1,
                "selfTradePreventionMode": "NONE"
            },
            {
                "symbol": "LTCBNB",
                "orderId": 25,
                "orderListId": 629,
                "clientOrderId": "ilpIoShcFZ1ZGgSASKxMPt",
                "transactTime": 1712544408537,
                "price": "5.000000",
                "origQty": "5.000000",
                "executedQty": "0.000000",
                "origQuoteOrderQty": "0.000000",
                "cummulativeQuoteQty": "0.000000",
                "status": "PENDING_NEW",
                "timeInForce": "GTC",
                "type": "LIMIT_MAKER",
                "side": "SELL",
                "workingTime": -1,
                "selfTradePreventionMode": "NONE"
            }
        ]
    },
    "rateLimits": [
        {
            "rateLimitType": "ORDERS",
            "interval": "MINUTE",
            "intervalNum": 1,
            "limit": 10000000,
            "count": 18
        },
        {
            "rateLimitType": "REQUEST_WEIGHT",
            "interval": "MINUTE",
            "intervalNum": 1,
            "limit": 1000,
            "count": 65
        }
    ]
}
```

**Note:** The payload above does not show all fields that can appear. Please refer to [Conditional fields in Order Responses](#conditional-fields-in-order-responses).
#### OPO (TRADE)

```json
{
    "id": "1762941318128",
    "method": "orderList.place.opo",
    "params": {
        "workingPrice": "101496",
        "workingQuantity": "0.0007",
        "workingType": "LIMIT",
        "workingTimeInForce": "GTC",
        "pendingType": "MARKET",
        "pendingSide": "SELL",
        "recvWindow": 5000,
        "workingSide": "BUY",
        "symbol": "BTCUSDT",
        "timestamp": 1762941318129,
        "apiKey": "key",
        "signature": "b50ce8977333a78a3bbad21df178d7e104a8c985d19007b55df688cdf868639a"
    }
}
```

Place an [OPO](https://developers.binance.com/docs/binance-spot-api-docs/faqs/opo.md).

* OPOs add 2 orders to the EXCHANGE_MAX_NUM_ORDERS filter and MAX_NUM_ORDERS filter.

**Weight:** 1

**Unfilled Order Count:** 2

**Parameters:**

| Name | Type | Mandatory | Description |
| ----- | ----- | ----- | ----- |
| `symbol` | STRING | YES |  |
| `listClientOrderId` | STRING | NO | Arbitrary unique ID among open order lists. Automatically generated if not sent. A new order list with the same listClientOrderId is accepted only when the previous one is filled or completely expired. `listClientOrderId` is distinct from the `workingClientOrderId` and the `pendingClientOrderId`. |
| `newOrderRespType` | ENUM | NO | Format of the JSON response. Supported values: [Order Response Type](https://developers.binance.com/docs/binance-spot-api-docs/enums.md#orderresponsetype) |
| `selfTradePreventionMode` | ENUM | NO | The allowed values are dependent on what is configured on the symbol. Supported values: [STP Modes](https://developers.binance.com/docs/binance-spot-api-docs/enums.md#stpmodes) |
| `workingType` | ENUM | YES | Supported values: `LIMIT`,`LIMIT_MAKER` |
| `workingSide` | ENUM | YES | Supported values: [Order Side](https://developers.binance.com/docs/binance-spot-api-docs/enums.md#side) |
| `workingClientOrderId` | STRING | NO | Arbitrary unique ID among open orders for the working order. Automatically generated if not sent. |
| `workingPrice` | DECIMAL | YES |  |
| `workingQuantity` | DECIMAL | YES | Sets the quantity for the working order. |
| `workingIcebergQty` | DECIMAL | NO | This can only be used if `workingTimeInForce` is `GTC`, or if `workingType` is `LIMIT_MAKER`. |
| `workingTimeInForce` | ENUM | NO | Supported values: [Time In Force](https://developers.binance.com/docs/binance-spot-api-docs/enums.md#timeinforce) |
| `workingStrategyId` | LONG | NO | Arbitrary numeric value identifying the working order within an order strategy. |
| `workingStrategyType` | INT | NO | Arbitrary numeric value identifying the working order strategy. Values smaller than 1000000 are reserved and cannot be used. |
| `workingPegPriceType` | ENUM | NO | See [Pegged Orders](#pegged-orders-info) |
| `workingPegOffsetType` | ENUM | NO |  |
| `workingPegOffsetValue` | INT | NO |  |
| `pendingType` | ENUM | YES | Supported values: [Order Types](#order-type) Note that `MARKET` orders using `quoteOrderQty` are not supported. |
| `pendingSide` | ENUM | YES | Supported values: [Order Side](https://developers.binance.com/docs/binance-spot-api-docs/enums.md#side) |
| `pendingClientOrderId` | STRING | NO | Arbitrary unique ID among open orders for the pending order. Automatically generated if not sent. |
| `pendingPrice` | DECIMAL | NO |  |
| `pendingStopPrice` | DECIMAL | NO |  |
| `pendingTrailingDelta` | DECIMAL | NO |  |
| `pendingIcebergQty` | DECIMAL | NO | This can only be used if `pendingTimeInForce` is `GTC` or if `pendingType` is `LIMIT_MAKER`. |
| `pendingTimeInForce` | ENUM | NO | Supported values: [Time In Force](https://developers.binance.com/docs/binance-spot-api-docs/enums.md#timeinforce) |
| `pendingStrategyId` | LONG | NO | Arbitrary numeric value identifying the pending order within an order strategy. |
| `pendingStrategyType` | INT | NO | Arbitrary numeric value identifying the pending order strategy. Values smaller than 1000000 are reserved and cannot be used. |
| `pendingPegPriceType` | ENUM | NO | See [Pegged Orders](#pegged-orders-info) |
| `pendingPegOffsetType` | ENUM | NO |  |
| `pendingPegOffsetValue` | INT | NO |  |
| `recvWindow` | DECIMAL | NO | The value cannot be greater than `60000`. Supports up to three decimal places of precision (e.g., 6000.346) so that microseconds may be specified. |
| `timestamp` | LONG | YES |  |

**Data Source**: Matching Engine

**Response:**

```json
{
    "id": "1762941318128",
    "status": 200,
    "result": {
        "orderListId": 2,
        "contingencyType": "OTO",
        "listStatusType": "EXEC_STARTED",
        "listOrderStatus": "EXECUTING",
        "listClientOrderId": "OiOgqvRagBefpzdM5gjYX3",
        "transactionTime": 1762941318142,
        "symbol": "BTCUSDT",
        "orders": [
            {
                "symbol": "BTCUSDT",
                "orderId": 2,
                "clientOrderId": "pUzhKBbc0ZVdMScIRAqitH"
            },
            {
                "symbol": "BTCUSDT",
                "orderId": 3,
                "clientOrderId": "x7ISSjywZxFXOdzwsThNnd"
            }
        ],
        "orderReports": [
            {
                "symbol": "BTCUSDT",
                "orderId": 2,
                "orderListId": 2,
                "clientOrderId": "pUzhKBbc0ZVdMScIRAqitH",
                "transactTime": 1762941318142,
                "price": "101496.00000000",
                "origQty": "0.00070000",
                "executedQty": "0.00000000",
                "origQuoteOrderQty": "0.00000000",
                "cummulativeQuoteQty": "0.00000000",
                "status": "NEW",
                "timeInForce": "GTC",
                "type": "LIMIT",
                "side": "BUY",
                "workingTime": 1762941318142,
                "selfTradePreventionMode": "NONE"
            },
            {
                "symbol": "BTCUSDT",
                "orderId": 3,
                "orderListId": 2,
                "clientOrderId": "x7ISSjywZxFXOdzwsThNnd",
                "transactTime": 1762941318142,
                "price": "0.00000000",
                "executedQty": "0.00000000",
                "origQuoteOrderQty": "0.00000000",
                "cummulativeQuoteQty": "0.00000000",
                "status": "PENDING_NEW",
                "timeInForce": "GTC",
                "type": "MARKET",
                "side": "SELL",
                "workingTime": -1,
                "selfTradePreventionMode": "NONE"
            }
        ]
    }
}
```

**Note:** The payload above does not show all fields that can appear. Please refer to [Conditional fields in Order Responses](#conditional-fields-in-order-responses).

#### OPOCO (TRADE)

```json
{
    "id": "1763000139090",
    "method": "orderList.place.opoco",
    "params": {
        "workingPrice": "102496",
        "workingQuantity": "0.0017",
        "workingType": "LIMIT",
        "workingTimeInForce": "GTC",
        "pendingAboveType": "LIMIT_MAKER",
        "pendingAbovePrice": "104261",
        "pendingBelowStopPrice": "10100",
        "pendingBelowPrice": "101613",
        "pendingBelowType": "STOP_LOSS_LIMIT",
        "pendingBelowTimeInForce": "IOC",
        "pendingSide": "SELL",
        "recvWindow": 5000,
        "workingSide": "BUY",
        "symbol": "BTCUSDT",
        "timestamp": 1763000139091,
        "apiKey": "key",
        "signature": "adfa185c50f793392a54ad5a6e2c39fd34ef6d35944adf2ddd6f30e1866e58d3"
    }
}
```

Place an [OPOCO](https://developers.binance.com/docs/binance-spot-api-docs/faqs/opo.md).

**Weight**: 1

**Unfilled Order Count:** 3

**Parameters:**

| Name | Type | Mandatory | Description |
| ----- | ----- | ----- | ----- |
| `symbol` | STRING | YES |  |
| `listClientOrderId` | STRING | NO | Arbitrary unique ID among open order lists. Automatically generated if not sent. A new order list with the same listClientOrderId is accepted only when the previous one is filled or completely expired. `listClientOrderId` is distinct from the `workingClientOrderId`, `pendingAboveClientOrderId`, and the `pendingBelowClientOrderId`. |
| `newOrderRespType` | ENUM | NO | Format of the JSON response. Supported values: [Order Response Type](https://developers.binance.com/docs/binance-spot-api-docs/enums.md#orderresponsetype) |
| `selfTradePreventionMode` | ENUM | NO | The allowed values are dependent on what is configured on the symbol. Supported values: [STP Modes](https://developers.binance.com/docs/binance-spot-api-docs/enums.md#stpmodes) |
| `workingType` | ENUM | YES | Supported values: `LIMIT`, `LIMIT_MAKER` |
| `workingSide` | ENUM | YES | Supported values: [Order side](https://developers.binance.com/docs/binance-spot-api-docs/enums.md#side) |
| `workingClientOrderId` | STRING | NO | Arbitrary unique ID among open orders for the working order. Automatically generated if not sent. |
| `workingPrice` | DECIMAL | YES |  |
| `workingQuantity` | DECIMAL | YES |  |
| `workingIcebergQty` | DECIMAL | NO | This can only be used if `workingTimeInForce` is `GTC`, or if `workingType` is `LIMIT_MAKER`. |
| `workingTimeInForce` | ENUM | NO | Supported values: [Time In Force](https://developers.binance.com/docs/binance-spot-api-docs/enums.md#timeinforce) |
| `workingStrategyId` | LONG | NO | Arbitrary numeric value identifying the working order within an order strategy. |
| `workingStrategyType` | INT | NO | Arbitrary numeric value identifying the working order strategy. Values smaller than 1000000 are reserved and cannot be used. |
| `workingPegPriceType` | ENUM | NO | See [Pegged Orders](#pegged-orders-info) |
| `workingPegOffsetType` | ENUM | NO |  |
| `workingPegOffsetValue` | INT | NO |  |
| `pendingSide` | ENUM | YES | Supported values: [Order side](https://developers.binance.com/docs/binance-spot-api-docs/enums.md#side) |
| `pendingAboveType` | ENUM | YES | Supported values: `STOP_LOSS_LIMIT`, `STOP_LOSS`, `LIMIT_MAKER`, `TAKE_PROFIT`, `TAKE_PROFIT_LIMIT` |
| `pendingAboveClientOrderId` | STRING | NO | Arbitrary unique ID among open orders for the pending above order. Automatically generated if not sent. |
| `pendingAbovePrice` | DECIMAL | NO | Can be used if `pendingAboveType` is `STOP_LOSS_LIMIT` , `LIMIT_MAKER`, or `TAKE_PROFIT_LIMIT` to specify the limit price. |
| `pendingAboveStopPrice` | DECIMAL | NO | Can be used if `pendingAboveType` is `STOP_LOSS`, `STOP_LOSS_LIMIT`, `TAKE_PROFIT`, `TAKE_PROFIT_LIMIT` |
| `pendingAboveTrailingDelta` | DECIMAL | NO | See [Trailing Stop FAQ](https://developers.binance.com/docs/binance-spot-api-docs/faqs/trailing-stop-faq.md) |
| `pendingAboveIcebergQty` | DECIMAL | NO | This can only be used if `pendingAboveTimeInForce` is `GTC` or if `pendingAboveType` is `LIMIT_MAKER`. |
| `pendingAboveTimeInForce` | ENUM | NO |  |
| `pendingAboveStrategyId` | LONG | NO | Arbitrary numeric value identifying the pending above order within an order strategy. |
| `pendingAboveStrategyType` | INT | NO | Arbitrary numeric value identifying the pending above order strategy. Values smaller than 1000000 are reserved and cannot be used. |
| `pendingAbovePegPriceType` | ENUM | NO | See [Pegged Orders](#pegged-orders-info) |
| `pendingAbovePegOffsetType` | ENUM | NO |  |
| `pendingAbovePegOffsetValue` | INT | NO |  |
| `pendingBelowType` | ENUM | NO | Supported values: `STOP_LOSS`, `STOP_LOSS_LIMIT`, `TAKE_PROFIT`,`TAKE_PROFIT_LIMIT` |
| `pendingBelowClientOrderId` | STRING | NO | Arbitrary unique ID among open orders for the pending below order. Automatically generated if not sent. |
| `pendingBelowPrice` | DECIMAL | NO | Can be used if `pendingBelowType` is `STOP_LOSS_LIMIT` or `TAKE_PROFIT_LIMIT` to specify limit price |
| `pendingBelowStopPrice` | DECIMAL | NO | Can be used if `pendingBelowType` is `STOP_LOSS`, `STOP_LOSS_LIMIT, TAKE_PROFIT or TAKE_PROFIT_LIMIT`. Either `pendingBelowStopPrice` or `pendingBelowTrailingDelta` or both, must be specified. |
| `pendingBelowTrailingDelta` | DECIMAL | NO |  |
| `pendingBelowIcebergQty` | DECIMAL | NO | This can only be used if `pendingBelowTimeInForce` is `GTC`, or if `pendingBelowType` is `LIMIT_MAKER`. |
| `pendingBelowTimeInForce` | ENUM | NO | Supported values: [Time In Force](https://developers.binance.com/docs/binance-spot-api-docs/enums.md#timeinforce) |
| `pendingBelowStrategyId` | LONG | NO | Arbitrary numeric value identifying the pending below order within an order strategy. |
| `pendingBelowStrategyType` | INT | NO | Arbitrary numeric value identifying the pending below order strategy. Values smaller than 1000000 are reserved and cannot be used. |
| `pendingBelowPegPriceType` | ENUM | NO | See [Pegged Orders](#pegged-orders-info) |
| `pendingBelowPegOffsetType` | ENUM | NO |  |
| `pendingBelowPegOffsetValue` | INT | NO |  |
| `recvWindow` | DECIMAL | NO | The value cannot be greater than `60000`. Supports up to three decimal places of precision (e.g., 6000.346) so that microseconds may be specified. |
| `timestamp` | LONG | YES |  |

**Data Source**:
Matching Engine

**Response:**

```json
{
    "id": "1763000139090",
    "status": 200,
    "result": {
        "orderListId": 1,
        "contingencyType": "OTO",
        "listStatusType": "EXEC_STARTED",
        "listOrderStatus": "EXECUTING",
        "listClientOrderId": "TVbG6ymkYMXTj7tczbOsBf",
        "transactionTime": 1763000139104,
        "symbol": "BTCUSDT",
        "orders": [
            {
                "symbol": "BTCUSDT",
                "orderId": 6,
                "clientOrderId": "3czuJSeyjPwV9Xo28j1Dv3"
            },
            {
                "symbol": "BTCUSDT",
                "orderId": 7,
                "clientOrderId": "kyIKnMLKQclE5FmyYgaMSo"
            },
            {
                "symbol": "BTCUSDT",
                "orderId": 8,
                "clientOrderId": "i76cGJWN9J1FpADS56TtQZ"
            }
        ],
        "orderReports": [
            {
                "symbol": "BTCUSDT",
                "orderId": 6,
                "orderListId": 1,
                "clientOrderId": "3czuJSeyjPwV9Xo28j1Dv3",
                "transactTime": 1763000139104,
                "price": "102496.00000000",
                "origQty": "0.00170000",
                "executedQty": "0.00000000",
                "origQuoteOrderQty": "0.00000000",
                "cummulativeQuoteQty": "0.00000000",
                "status": "NEW",
                "timeInForce": "GTC",
                "type": "LIMIT",
                "side": "BUY",
                "workingTime": 1763000139104,
                "selfTradePreventionMode": "NONE"
            },
            {
                "symbol": "BTCUSDT",
                "orderId": 7,
                "orderListId": 1,
                "clientOrderId": "kyIKnMLKQclE5FmyYgaMSo",
                "transactTime": 1763000139104,
                "price": "101613.00000000",
                "executedQty": "0.00000000",
                "origQuoteOrderQty": "0.00000000",
                "cummulativeQuoteQty": "0.00000000",
                "status": "PENDING_NEW",
                "timeInForce": "IOC",
                "type": "STOP_LOSS_LIMIT",
                "side": "SELL",
                "stopPrice": "10100.00000000",
                "workingTime": -1,
                "selfTradePreventionMode": "NONE"
            },
            {
                "symbol": "BTCUSDT",
                "orderId": 8,
                "orderListId": 1,
                "clientOrderId": "i76cGJWN9J1FpADS56TtQZ",
                "transactTime": 1763000139104,
                "price": "104261.00000000",
                "executedQty": "0.00000000",
                "origQuoteOrderQty": "0.00000000",
                "cummulativeQuoteQty": "0.00000000",
                "status": "PENDING_NEW",
                "timeInForce": "GTC",
                "type": "LIMIT_MAKER",
                "side": "SELL",
                "workingTime": -1,
                "selfTradePreventionMode": "NONE"
            }
        ]
    }
}
```

**Note:** The payload above does not show all fields that can appear. Please refer to [Conditional fields in Order Responses](#conditional-fields-in-order-responses).

#### Cancel Order list (TRADE)

```javascript
{
    "id": "c5899911-d3f4-47ae-8835-97da553d27d0",
    "method": "orderList.cancel",
    "params": {
        "symbol": "BTCUSDT",
        "orderListId": 1274512,
        "apiKey": "key",
        "signature": "4973f4b2fee30bf6d45e4a973e941cc60fdd53c8dd5a25edeac96f5733c0ccee",
        "timestamp": 1660801720210
    }
}
```

Cancel an active order list.

**Weight**:
1

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
        <td>YES</td>
        <td></td>
    </tr>
    <tr>
        <td><code>orderListId</code></td>
        <td>INT</td>
        <td rowspan="2">YES</td>
        <td>Cancel order list by <code>orderListId</code></td>
    </tr>
    <tr>
        <td><code>listClientOrderId</code></td>
        <td>STRING</td>
        <td>Cancel order list by <code>listClientId</code></td>
    </tr>
    <tr>
        <td><code>newClientOrderId</code></td>
        <td>STRING</td>
        <td>NO</td>
        <td>New ID for the canceled order list. Automatically generated if not sent</td>
    </tr>
    <tr>
        <td><code>apiKey</code></td>
        <td>STRING</td>
        <td>YES</td>
        <td></td>
    </tr>
    <tr>
        <td><code>recvWindow</code></td>
        <td>DECIMAL</td>
        <td>NO</td>
        <td>The value cannot be greater than <tt>60000</tt>.<br> Supports up to three decimal places of precision (e.g., 6000.346) so that microseconds may be specified.</td>
    </tr>
    <tr>
        <td><code>signature</code></td>
        <td>STRING</td>
        <td>YES</td>
        <td></td>
    </tr>
    <tr>
        <td><code>timestamp</code></td>
        <td>LONG</td>
        <td>YES</td>
        <td></td>
    </tr>
</tbody>
</table>

Notes:

* If both `orderListId` and `listClientOrderId` parameters are provided, the `orderListId` is searched first, then the `listClientOrderId` from that result is checked against that order. If both conditions are not met the request will be rejected.

* Canceling an individual order with [`order.cancel`](#cancel-order-trade) will cancel the entire order list as well.

**Data Source:**
Matching Engine

**Response:**

```javascript
{
    "id": "c5899911-d3f4-47ae-8835-97da553d27d0",
    "status": 200,
    "result": {
        "orderListId": 1274512,
        "contingencyType": "OCO",
        "listStatusType": "ALL_DONE",
        "listOrderStatus": "ALL_DONE",
        "listClientOrderId": "6023531d7edaad348f5aff",
        "transactionTime": 1660801720215,
        "symbol": "BTCUSDT",
        "orders": [
            {
                "symbol": "BTCUSDT",
                "orderId": 12569138901,
                "clientOrderId": "BqtFCj5odMoWtSqGk2X9tU"
            },
            {
                "symbol": "BTCUSDT",
                "orderId": 12569138902,
                "clientOrderId": "jLnZpj5enfMXTuhKB1d0us"
            }
        ],
        "orderReports": [
            {
                "symbol": "BTCUSDT",
                "orderId": 12569138901,
                "orderListId": 1274512,
                "clientOrderId": "BqtFCj5odMoWtSqGk2X9tU",
                "transactTime": 1660801720215,
                "price": "23410.00000000",
                "origQty": "0.00650000",
                "executedQty": "0.00000000",
                "origQuoteOrderQty": "0.000000",
                "cummulativeQuoteQty": "0.00000000",
                "status": "CANCELED",
                "timeInForce": "GTC",
                "type": "STOP_LOSS_LIMIT",
                "side": "SELL",
                "stopPrice": "23405.00000000",
                "selfTradePreventionMode": "NONE"
            },
            {
                "symbol": "BTCUSDT",
                "orderId": 12569138902,
                "orderListId": 1274512,
                "clientOrderId": "jLnZpj5enfMXTuhKB1d0us",
                "transactTime": 1660801720215,
                "price": "23420.00000000",
                "origQty": "0.00650000",
                "executedQty": "0.00000000",
                "origQuoteOrderQty": "0.000000",
                "cummulativeQuoteQty": "0.00000000",
                "status": "CANCELED",
                "timeInForce": "GTC",
                "type": "LIMIT_MAKER",
                "side": "SELL",
                "selfTradePreventionMode": "NONE"
            }
        ]
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

### SOR

#### Place new order using SOR (TRADE)

```javascript
{
    "id": "3a4437e2-41a3-4c19-897c-9cadc5dce8b6",
    "method": "sor.order.place",
    "params": {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "type": "LIMIT",
        "quantity": 0.5,
        "timeInForce": "GTC",
        "price": 31000,
        "timestamp": 1687485436575,
        "apiKey": "key",
        "signature": "fd301899567bc9472ce023392160cdc265ad8fcbbb67e0ea1b2af70a4b0cd9c7"
    }
}
```

Places an order using smart order routing (SOR).

This adds 1 order to the `EXCHANGE_MAX_ORDERS` filter and the `MAX_NUM_ORDERS` filter.

Read [SOR FAQ](https://developers.binance.com/docs/binance-spot-api-docs/faqs/sor_faq.md) to learn more.

**Weight:**
1

**Unfilled Order Count:**
1

**Parameters:**

Name                | Type    | Mandatory | Description
------------------- | ------- | --------- | ------------
`symbol`            | STRING  | YES       |
`side`              | ENUM    | YES       | `BUY` or `SELL`
`type`              | ENUM    | YES       |
`timeInForce`       | ENUM    | NO        | Applicable only to `LIMIT` order type
`price`             | DECIMAL | NO        | Applicable only to `LIMIT` order type
`quantity`          | DECIMAL | YES       |
`newClientOrderId`  | STRING  | NO        | Arbitrary unique ID among open orders. Automatically generated if not sent
`newOrderRespType`  | ENUM    | NO        | <p>Select response format: `ACK`, `RESULT`, `FULL`.</p><p>`MARKET` and `LIMIT` orders use `FULL` by default.</p>
`icebergQty`        | DECIMAL | NO        |
`strategyId`        | LONG    | NO        | Arbitrary numeric value identifying the order within an order strategy.
`strategyType`      | INT     | NO        | <p>Arbitrary numeric value identifying the order strategy.</p><p>Values smaller than `1000000` are reserved and cannot be used.</p>
`selfTradePreventionMode` |ENUM | NO      | The allowed enums is dependent on what is configured on the symbol. The possible supported values are: [STP Modes](https://developers.binance.com/docs/binance-spot-api-docs/enums.md#stpmodes).
`apiKey`            | STRING  | YES       |
`timestamp`         | LONG    | YES       |
`recvWindow`        | DECIMAL | NO        | The value cannot be greater than `60000`. <br> Supports up to three decimal places of precision (e.g., 6000.346) so that microseconds may be specified.
`signature`         | STRING  | YES       |

**Note:** `sor.order.place` only supports `LIMIT` and `MARKET` orders. `quoteOrderQty` is not supported.

**Data Source:**
Matching Engine

**Response:**

```javascript
{
    "id": "3a4437e2-41a3-4c19-897c-9cadc5dce8b6",
    "status": 200,
    "result": [
        {
            "symbol": "BTCUSDT",
            "orderId": 2,
            "orderListId": -1,
            "clientOrderId": "sBI1KM6nNtOfj5tccZSKly",
            "transactTime": 1689149087774,
            "price": "31000.00000000",
            "origQty": "0.50000000",
            "executedQty": "0.50000000",
            "origQuoteOrderQty": "0.000000",
            "cummulativeQuoteQty": "14000.00000000",
            "status": "FILLED",
            "timeInForce": "GTC",
            "type": "LIMIT",
            "side": "BUY",
            "workingTime": 1689149087774,
            "fills": [
                {
                    "matchType": "ONE_PARTY_TRADE_REPORT",
                    "price": "28000.00000000",
                    "qty": "0.50000000",
                    "commission": "0.00000000",
                    "commissionAsset": "BTC",
                    "tradeId": -1,
                    "allocId": 0
                }
            ],
            "workingFloor": "SOR",
            "selfTradePreventionMode": "NONE",
            "usedSor": true
        }
    ],
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

#### Test new order using SOR (TRADE)

```javascript
{
    "id": "3a4437e2-41a3-4c19-897c-9cadc5dce8b6",
    "method": "sor.order.test",
    "params": {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "type": "LIMIT",
        "quantity": 0.1,
        "timeInForce": "GTC",
        "price": 0.1,
        "timestamp": 1687485436575,
        "apiKey": "key",
        "signature": "fd301899567bc9472ce023392160cdc265ad8fcbbb67e0ea1b2af70a4b0cd9c7"
    }
}
```

Test new order creation and signature/recvWindow using smart order routing (SOR).
Creates and validates a new order but does not send it into the matching engine.

**Weight:**

|Condition                       | Request Weight|
|------------                    | ------------ |
|Without `computeCommissionRates`| 1            |
|With `computeCommissionRates`   |20            |

**Parameters:**

In addition to all parameters accepted by [`sor.order.place`](#place-new-order-using-sor-trade),
the following optional parameters are also accepted:

Name                   |Type          | Mandatory    | Description
------------           | ------------ | ------------ | ------------
`computeCommissionRates` | BOOLEAN      | NO           | Default: `false`

**Data Source:**
Memory

**Response:**

Without `computeCommissionRates`:

```javascript
{
    "id": "3a4437e2-41a3-4c19-897c-9cadc5dce8b6",
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

With `computeCommissionRates`:

```javascript
{
    "id": "3a4437e2-41a3-4c19-897c-9cadc5dce8b6",
    "status": 200,
    "result": {
        "standardCommissionForOrder": {  // Commission rates for the order depending on its role (e.g. maker or taker)
            "maker": "0.00000112",
            "taker": "0.00000114"
        },
        "taxCommissionForOrder": {       // Tax deduction rates for the order depending on its role (e.g. maker or taker)
            "maker": "0.00000112",
            "taker": "0.00000114"
        },
        "discount": {                    // Discount on standard commissions when paying in BNB.
            "enabledForAccount": true,
            "enabledForSymbol": true,
            "discountAsset": "BNB",
            "discount": "0.25"           // Standard commission is reduced by this rate when paying in BNB.
        }
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
