---
document_id: AI4B-BINANCE-IFC-106
title: Binance WebSocket API Order Requests Reference
document_type: INTERFACE_CONTRACT
version: 1.0.0
status: ACTIVE
owner: Enterprise Governance
authority_level: EXTERNAL_AUTHORITY
authority_layer: L3_CANONICAL_CONTRACTS_SCHEMAS
authority_scope: binance_websocket_api_order_requests
content_role: DERIVED
source_of_truth: false
canonical_path: docs/contracts/interface_contract_binance_websocket_api_order_requests.md
machine_enforceable: false
audit_required: true
classification: INTERNAL
---
# Binance WebSocket API Order Requests Reference

## ELI10

This document keeps single-order request formats separate from order-list and account requests.

## Source Lineage

- Source file: `docs/contracts/interface_contract_binance_websocket_api_reference.md`
- Source section start: `## Trading requests`
- This file preserves a bounded section of the governed source document.

## Trading requests

### Place new order (TRADE)

```javascript
{
    "id": "56374a46-3061-486b-a311-99ee972eb648",
    "method": "order.place",
    "params": {
        "symbol": "BTCUSDT",
        "side": "SELL",
        "type": "LIMIT",
        "timeInForce": "GTC",
        "price": "23416.10000000",
        "quantity": "0.00847000",
        "apiKey": "key",
        "signature": "15af09e41c36f3cc61378c2fbe2c33719a03dd5eba8d0f9206fbda44de717c88",
        "timestamp": 1660801715431
    }
}
```

Send in a new order.

This adds 1 order to the `EXCHANGE_MAX_ORDERS` filter and the `MAX_NUM_ORDERS` filter.

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
`timeInForce`       | ENUM    | NO *      |
`price`             | DECIMAL | NO *      |
`quantity`          | DECIMAL | NO *      |
`quoteOrderQty`     | DECIMAL | NO *      |
`newClientOrderId`  | STRING  | NO        | Arbitrary unique ID among open orders. Automatically generated if not sent
`newOrderRespType`  | ENUM    | NO        | <p>Select response format: `ACK`, `RESULT`, `FULL`.</p><p>`MARKET` and `LIMIT` orders use `FULL` by default, other order types default to `ACK`.</p>
`stopPrice`         | DECIMAL | NO *      |
`trailingDelta`     | INT     | NO *      | See [Trailing Stop order FAQ](https://developers.binance.com/docs/binance-spot-api-docs/faqs/trailing-stop-faq.md)
`icebergQty`        | DECIMAL | NO        |
`strategyId`        | LONG    | NO        | Arbitrary numeric value identifying the order within an order strategy.
`strategyType`      | INT     | NO        | <p>Arbitrary numeric value identifying the order strategy.</p><p>Values smaller than `1000000` are reserved and cannot be used.</p>
`selfTradePreventionMode` |ENUM | NO      | The allowed enums is dependent on what is configured on the symbol. Supported values: [STP Modes](https://developers.binance.com/docs/binance-spot-api-docs/enums.md#stpmodes)
`pegPriceType`      | ENUM    | NO        | `PRIMARY_PEG` or `MARKET_PEG` <br> See [Pegged Orders](#pegged-orders-info)
`pegOffsetValue`    | INT     | NO        | Price level to peg the price to (max: 100) <br> See [Pegged Orders](#pegged-orders-info)
`pegOffsetType`     | ENUM    | NO        | Only `PRICE_LEVEL` is supported <br> See [Pegged Orders](#pegged-orders-info)
`apiKey`            | STRING  | YES       |
`recvWindow`        | DECIMAL | NO        | The value cannot be greater than `60000`. <br> Supports up to three decimal places of precision (e.g., 6000.346) so that microseconds may be specified.
`signature`         | STRING  | YES       |
`timestamp`         | LONG    | YES       |

<a id="order-type">Certain parameters (*)</a> become mandatory based on the order `type`:

<table>
<thead>
    <tr>
        <th>Order <code>type</code></th>
        <th>Mandatory parameters</th>
    </tr>
</thead>
<tbody>
    <tr>
        <td><code>LIMIT</code></td>
        <td>
        <ul>
            <li><code>timeInForce</code></li>
            <li><code>price</code></li>
            <li><code>quantity</code></li>
        </ul>
        </td>
    </tr>
    <tr>
        <td><code>LIMIT_MAKER</code></td>
        <td>
        <ul>
            <li><code>price</code></li>
            <li><code>quantity</code></li>
        </ul>
        </td>
    </tr>
    <tr>
        <td><code>MARKET</code></td>
        <td>
        <ul>
            <li><code>quantity</code> or <code>quoteOrderQty</code></li>
        </ul>
        </td>
    </tr>
    <tr>
        <td><code>STOP_LOSS</code></td>
        <td>
        <ul>
            <li><code>quantity</code></li>
            <li><code>stopPrice</code> or <code>trailingDelta</code></li>
        </ul>
        </td>
    </tr>
    <tr>
        <td><code>STOP_LOSS_LIMIT</code></td>
        <td>
        <ul>
            <li><code>timeInForce</code></li>
            <li><code>price</code></li>
            <li><code>quantity</code></li>
            <li><code>stopPrice</code> or <code>trailingDelta</code></li>
        </ul>
        </td>
    </tr>
    <tr>
        <td><code>TAKE_PROFIT</code></td>
        <td>
        <ul>
            <li><code>quantity</code></li>
            <li><code>stopPrice</code> or <code>trailingDelta</code></li>
        </ul>
        </td>
    </tr>
    <tr>
        <td><code>TAKE_PROFIT_LIMIT</code></td>
        <td>
        <ul>
            <li><code>timeInForce</code></li>
            <li><code>price</code></li>
            <li><code>quantity</code></li>
            <li><code>stopPrice</code> or <code>trailingDelta</code></li>
        </ul>
        </td>
    </tr>
</tbody>
</table>

Supported order types:

<table>
<thead>
    <tr>
        <th>Order <code>type</code></th>
        <th>Description</th>
    </tr>
</thead>
<tbody>
    <tr>
        <td><code>LIMIT</code></td>
        <td>
        <p>
            Buy or sell <code>quantity</code> at the specified <code>price</code> or better.
        </p>
        </td>
    </tr>
    <tr>
        <td><code>LIMIT_MAKER</code></td>
        <td>
        <p>
            <code>LIMIT</code> order that will be rejected if it immediately matches and trades as a taker.
        </p>
        <p>
            This order type is also known as a POST-ONLY order.
        </p>
        </td>
    </tr>
    <tr>
        <td><code>MARKET</code></td>
        <td>
        <p>
            Buy or sell at the best available market price.
        </p>
        <ul>
            <li>
                <p>
                    <code>MARKET</code> order with <code>quantity</code> parameter
                    specifies the amount of the <em>base asset</em> you want to buy or sell.
                    Actually executed quantity of the quote asset will be determined by available market liquidity.
                </p>
                <p>
                    E.g., a MARKET BUY order on BTCUSDT for <code>"quantity": "0.1000"</code>
                    specifies that you want to buy 0.1 BTC at the best available price.
                    If there is not enough BTC at the best price, keep buying at the next best price,
                    until either your order is filled, or you run out of USDT, or market runs out of BTC.
                </p>
            </li>
            <li>
                <p>
                    <code>MARKET</code> order with <code>quoteOrderQty</code> parameter
                    specifies the amount of the <em>quote asset</em> you want to spend (when buying) or receive (when selling).
                    Actually executed quantity of the base asset will be determined by available market liquidity.
                </p>
                <p>
                    E.g., a MARKET BUY on BTCUSDT for <code>"quoteOrderQty": "100.00"</code>
                    specifies that you want to buy as much BTC as you can for 100 USDT at the best available price.
                    Similarly, a SELL order will sell as much available BTC as needed for you to receive 100 USDT
                    (before commission).
                </p>
            </li>
        </ul>
        </td>
    </tr>
    <tr>
        <td><code>STOP_LOSS</code></td>
        <td>
        <p>
            Execute a <code>MARKET</code> order for given <code>quantity</code> when specified conditions are met.
        </p>
        <p>
            I.e., when <code>stopPrice</code> is reached, or when <code>trailingDelta</code> is activated.
        </p>
        </td>
    </tr>
    <tr>
        <td><code>STOP_LOSS_LIMIT</code></td>
        <td>
        <p>
            Place a <code>LIMIT</code> order with given parameters when specified conditions are met.
        </p>
        </td>
    </tr>
    <tr>
        <td><code>TAKE_PROFIT</code></td>
        <td>
        <p>
            Like <code>STOP_LOSS</code> but activates when market price moves in the favorable direction.
        </p>
        </td>
    </tr>
    <tr>
        <td><code>TAKE_PROFIT_LIMIT</code></td>
        <td>
        <p>
            Like <code>STOP_LOSS_LIMIT</code> but activates when market price moves in the favorable direction.
        </p>
        </td>
    </tr>
</tbody>
</table>

<a id="pegged-orders-info"></a>
Notes on using parameters for Pegged Orders:

* These parameters are allowed for `LIMIT`, `LIMIT_MAKER`, `STOP_LOSS_LIMIT`, `TAKE_PROFIT_LIMIT` orders.
* If `pegPriceType` is specified, `price` becomes optional. Otherwise, it is still mandatory.
* `pegPriceType=PRIMARY_PEG` means the primary peg, that is the best price on the same side of the order book as your order.
* `pegPriceType=MARKET_PEG` means the market peg, that is the best price on the opposite side of the order book from your order.
* Use `pegOffsetType` and `pegOffsetValue` to request a price level other than the best one. These parameters must be specified together.

<a id="timeInForce"></a>

Available `timeInForce` options,
setting how long the order should be active before expiration:

 TIF  | Description
----- | --------------
`GTC` | **Good 'til Canceled** – the order will remain on the book until you cancel it, or the order is completely filled.
`IOC` | **Immediate or Cancel** – the order will be filled for as much as possible, the unfilled quantity immediately expires.
`FOK` | **Fill or Kill** – the order will expire unless it cannot be immediately filled for the entire quantity.

Notes:

* `newClientOrderId` specifies `clientOrderId` value for the order.

  A new order with the same `clientOrderId` is accepted only when the previous one is filled or expired.

* Any `LIMIT` or `LIMIT_MAKER` order can be made into an iceberg order by specifying the `icebergQty`.

  An order with an `icebergQty` must have `timeInForce` set to `GTC`.

* Trigger order price rules for `STOP_LOSS`/`TAKE_PROFIT` orders:

  * `stopPrice` must be above market price: `STOP_LOSS BUY`, `TAKE_PROFIT SELL`
  * `stopPrice` must be below market price: `STOP_LOSS SELL`, `TAKE_PROFIT BUY`

* `MARKET` orders using `quoteOrderQty` follow [`LOT_SIZE`](https://developers.binance.com/docs/binance-spot-api-docs/filters.md#lot_size) filter rules.

  The order will execute a quantity that has notional value as close as possible to requested `quoteOrderQty`.

**Data Source:**
Matching Engine

**Response:**

Response format is selected by using the `newOrderRespType` parameter.

`ACK` response type:

```javascript
{
    "id": "56374a46-3061-486b-a311-99ee972eb648",
    "status": 200,
    "result": {
        "symbol": "BTCUSDT",
        "orderId": 12569099453,
        "orderListId": -1, // always -1 for singular orders
        "clientOrderId": "4d96324ff9d44481926157ec08158a40",
        "transactTime": 1660801715639
    },
    "rateLimits": [
        {
            "rateLimitType": "ORDERS",
            "interval": "SECOND",
            "intervalNum": 10,
            "limit": 50,
            "count": 1
        },
        {
            "rateLimitType": "ORDERS",
            "interval": "DAY",
            "intervalNum": 1,
            "limit": 160000,
            "count": 1
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

`RESULT` response type:

```javascript
{
    "id": "56374a46-3061-486b-a311-99ee972eb648",
    "status": 200,
    "result": {
        "symbol": "BTCUSDT",
        "orderId": 12569099453,
        "orderListId": -1, // always -1 for singular orders
        "clientOrderId": "4d96324ff9d44481926157ec08158a40",
        "transactTime": 1660801715639,
        "price": "23416.10000000",
        "origQty": "0.00847000",
        "executedQty": "0.00000000",
        "origQuoteOrderQty": "0.000000",
        "cummulativeQuoteQty": "0.00000000",
        "status": "NEW",
        "timeInForce": "GTC",
        "type": "LIMIT",
        "side": "SELL",
        "workingTime": 1660801715639,
        "selfTradePreventionMode": "NONE"
    },
    "rateLimits": [
        {
            "rateLimitType": "ORDERS",
            "interval": "SECOND",
            "intervalNum": 10,
            "limit": 50,
            "count": 1
        },
        {
            "rateLimitType": "ORDERS",
            "interval": "DAY",
            "intervalNum": 1,
            "limit": 160000,
            "count": 1
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

`FULL` response type:

```javascript
{
    "id": "56374a46-3061-486b-a311-99ee972eb648",
    "status": 200,
    "result": {
        "symbol": "BTCUSDT",
        "orderId": 12569099453,
        "orderListId": -1,
        "clientOrderId": "4d96324ff9d44481926157ec08158a40",
        "transactTime": 1660801715793,
        "price": "23416.10000000",
        "origQty": "0.00847000",
        "executedQty": "0.00847000",
        "origQuoteOrderQty": "0.000000",
        "cummulativeQuoteQty": "198.33521500",
        "status": "FILLED",
        "timeInForce": "GTC",
        "type": "LIMIT",
        "side": "SELL",
        "workingTime": 1660801715793,
        // FULL response is identical to RESULT response, with the same optional fields
        // based on the order type and parameters. FULL response additionally includes
        // the list of trades which immediately filled the order.
        "fills": [
            {
                "price": "23416.10000000",
                "qty": "0.00635000",
                "commission": "0.000000",
                "commissionAsset": "BNB",
                "tradeId": 1650422481
            },
            {
                "price": "23416.50000000",
                "qty": "0.00212000",
                "commission": "0.000000",
                "commissionAsset": "BNB",
                "tradeId": 1650422482
            }
        ]
    },
    "rateLimits": [
        {
            "rateLimitType": "ORDERS",
            "interval": "SECOND",
            "intervalNum": 10,
            "limit": 50,
            "count": 1
        },
        {
            "rateLimitType": "ORDERS",
            "interval": "DAY",
            "intervalNum": 1,
            "limit": 160000,
            "count": 1
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

<a id="conditional-fields-in-order-responses"></a>

**Conditional fields in Order Responses**

There are fields in the order responses (e.g. order placement, order query, order cancellation) that appear only if certain conditions are met.

These fields can apply to Order lists.

The fields are listed below:

Field          |Description                                                      |Visibility conditions                                           | Examples |
----           | -----                                                           | ---                                                            |---       |
`icebergQty`   | Quantity for the iceberg order | Appears only if the parameter `icebergQty` was sent in the request.| `"icebergQty": "0.00000000"`
`preventedMatchId` |  When used in combination with `symbol`, can be used to query a prevented match. | Appears only if the order expired due to STP.| `"preventedMatchId": 0`
`preventedQuantity` | Order quantity that expired due to STP | Appears only if the order expired due to STP. | `"preventedQuantity": "1.200000"`
`stopPrice`    | Price when the algorithmic order will be triggered | Appears for `STOP_LOSS`. `TAKE_PROFIT`, `STOP_LOSS_LIMIT` and `TAKE_PROFIT_LIMIT` orders.|`"stopPrice": "23500.00000000"`
`strategyId`   | Can be used to label an order that's part of an order strategy. |Appears if the parameter was populated in the request.| `"strategyId": 37463720`
`strategyType` | Can be used to label an order that is using an order strategy.|Appears if the parameter was populated in the request.| `"strategyType": 1000000`
`trailingDelta`| Delta price change required before order activation| Appears for Trailing Stop Orders.|`"trailingDelta": 10`
`trailingTime` | Time when the trailing order is now active and tracking price changes| Appears only for Trailing Stop Orders.| `"trailingTime": -1`
`usedSor`      | Field that determines whether order used SOR | Appears when placing orders using SOR|`"usedSor": true`
`workingFloor` | Field that determines whether the order is being filled by the SOR or by the order book the order was submitted to.|Appears when placing orders using SOR|`"workingFloor": "SOR"`
`pegPriceType` |  Price peg type  | Only for pegged orders  | `"pegPriceType": "PRIMARY_PEG"`
`pegOffsetType`| Price peg offset type | Only for pegged orders, if requested  | `"pegOffsetType": "PRICE_LEVEL"`
`pegOffsetValue` | Price peg offset value  | Only for pegged orders, if requested  | `"pegOffsetValue": 5`
`peggedPrice`  | Current price order is pegged at | Only for pegged orders, once determined | `"peggedPrice": "87523.83710000"`
`expiryReason` | Cause of the order’s expiration | When an order has expired | `"expiryReason": "INSUFFICIENT_LIQUIDITY"` |

### Test new order (TRADE)

```javascript
{
    "id": "6ffebe91-01d9-43ac-be99-57cf062e0e30",
    "method": "order.test",
    "params": {
        "symbol": "BTCUSDT",
        "side": "SELL",
        "type": "LIMIT",
        "timeInForce": "GTC",
        "price": "23416.10000000",
        "quantity": "0.00847000",
        "apiKey": "key",
        "signature": "15af09e41c36f3cc61378c2fbe2c33719a03dd5eba8d0f9206fbda44de717c88",
        "timestamp": 1660801715431
    }
}
```

Test order placement.

Validates new order parameters and verifies your signature
but does not send the order into the matching engine.

**Weight:**

|Condition| Request Weight|
|------------           | ------------ |
|Without `computeCommissionRates`| 1|
|With `computeCommissionRates`|20|

**Parameters:**

In addition to all parameters accepted by [`order.place`](#place-new-order-trade),
the following optional parameters are also accepted:

Name                   |Type          | Mandatory    | Description
------------           | ------------ | ------------ | ------------
`computeCommissionRates` | BOOLEAN      | NO         | Default: `false` <br> See [Commissions FAQ](https://developers.binance.com/docs/binance-spot-api-docs/faqs/commission_faq.md#test-order-diferences) to learn more.


**Data Source:**
Memory

**Response:**

Without `computeCommissionRates`:

```javascript
{
    "id": "6ffebe91-01d9-43ac-be99-57cf062e0e30",
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
    "id": "6ffebe91-01d9-43ac-be99-57cf062e0e30",
    "status": 200,
    "result": {
        "standardCommissionForOrder": {  // Standard commission rates on trades from the order.
            "maker": "0.00000112",
            "taker": "0.00000114"
        },
        "specialCommissionForOrder": {   // Special commission rates on trades from the order.
            "maker": "0.05000000",
            "taker": "0.06000000"
        },
        "taxCommissionForOrder": {       // Tax commission rates for trades from the order
            "maker": "0.00000112",
            "taker": "0.00000114"
        },
        "discount": {                    // Discount on standard commissions when paying in BNB.
            "enabledForAccount": true,
            "enabledForSymbol": true,
            "discountAsset": "BNB",
            "discount": "0.25000000"     // Standard commission is reduced by this rate when paying in BNB.
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

### Cancel order (TRADE)

```javascript
{
    "id": "5633b6a2-90a9-4192-83e7-925c90b6a2fd",
    "method": "order.cancel",
    "params": {
        "symbol": "BTCUSDT",
        "origClientOrderId": "4d96324ff9d44481926157",
        "apiKey": "key",
        "signature": "33d5b721f278ae17a52f004a82a6f68a70c68e7dd6776ed0be77a455ab855282",
        "timestamp": 1660801715830
    }
}
```

Cancel an active order.

**Weight:**
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
        <td><code>orderId</code></td>
        <td>LONG</td>
        <td rowspan="2">YES</td>
        <td>Cancel order by <code>orderId</code></td>
    </tr>
    <tr>
        <td><code>origClientOrderId</code></td>
        <td>STRING</td>
        <td>Cancel order by <code>clientOrderId</code></td>
    </tr>
    <tr>
        <td><code>newClientOrderId</code></td>
        <td>STRING</td>
        <td>NO</td>
        <td>New ID for the canceled order. Automatically generated if not sent</td>
    </tr>
    <tr>
      <td><code>cancelRestrictions</code></td>
      <td>ENUM</td>
      <td>NO</td>
      <td>Supported values: <br><code>ONLY_NEW</code> - Cancel will succeed if the order status is <code>NEW</code>.<br> <code>ONLY_PARTIALLY_FILLED</code> - Cancel will succeed if order status is <code>PARTIALLY_FILLED</code>.</td>
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

* If both `orderId` and `origClientOrderId` parameters are provided, the `orderId` is searched first, then the `origClientOrderId` from that result is checked against that order. If both conditions are not met the request will be rejected.

* `newClientOrderId` will replace `clientOrderId` of the canceled order, freeing it up for new orders.

* If you cancel an order that is a part of an order list, the entire order list is canceled.

* The performance for canceling an order (single cancel or as part of a cancel-replace) is always better when only `orderId` is sent. Sending `origClientOrderId` or both `orderId` + `origClientOrderId` will be slower.

**Data Source:**
Matching Engine

**Response:**

When an individual order is canceled:

```javascript
{
    "id": "5633b6a2-90a9-4192-83e7-925c90b6a2fd",
    "status": 200,
    "result": {
        "symbol": "BTCUSDT",
        "origClientOrderId": "4d96324ff9d44481926157",     // clientOrderId that was canceled
        "orderId": 12569099453,
        "orderListId": -1,                                 // set only for legs of an order list
        "clientOrderId": "91fe37ce9e69c90d6358c0",         // newClientOrderId from request
        "transactTime": 1684804350068,
        "price": "23416.10000000",
        "origQty": "0.00847000",
        "executedQty": "0.00001000",
        "origQuoteOrderQty": "0.000000",
        "cummulativeQuoteQty": "0.23416100",
        "status": "CANCELED",
        "timeInForce": "GTC",
        "type": "LIMIT",
        "side": "SELL",
        "stopPrice": "0.00000000",                         // present only if stopPrice set for the order
        "trailingDelta": 0,                                // present only if trailingDelta set for the order
        "icebergQty": "0.00000000",                        // present only if icebergQty set for the order
        "strategyId": 37463720,                            // present only if strategyId set for the order
        "strategyType": 1000000,                           // present only if strategyType set for the order
        "selfTradePreventionMode": "NONE"
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

When an order list is canceled:

```javascript
{
    "id": "16eaf097-bbec-44b9-96ff-e97e6e875870",
    "status": 200,
    "result": {
        "orderListId": 19431,
        "contingencyType": "OCO",
        "listStatusType": "ALL_DONE",
        "listOrderStatus": "ALL_DONE",
        "listClientOrderId": "iuVNVJYYrByz6C4yGOPPK0",
        "transactionTime": 1660803702431,
        "symbol": "BTCUSDT",
        "orders": [
            {
                "symbol": "BTCUSDT",
                "orderId": 12569099453,
                "clientOrderId": "bX5wROblo6YeDwa9iTLeyY"
            },
            {
                "symbol": "BTCUSDT",
                "orderId": 12569099454,
                "clientOrderId": "Tnu2IP0J5Y4mxw3IATBfmW"
            }
        ],
        // order list order's status format is the same as for individual orders.
        "orderReports": [
            {
                "symbol": "BTCUSDT",
                "origClientOrderId": "bX5wROblo6YeDwa9iTLeyY",
                "orderId": 12569099453,
                "orderListId": 19431,
                "clientOrderId": "OFFXQtxVFZ6Nbcg4PgE2DA",
                "transactTime": 1684804350068,
                "price": "23450.50000000",
                "origQty": "0.00850000",
                "executedQty": "0.00000000",
                "origQuoteOrderQty": "0.000000",
                "cummulativeQuoteQty": "0.00000000",
                "status": "CANCELED",
                "timeInForce": "GTC",
                "type": "STOP_LOSS_LIMIT",
                "side": "BUY",
                "stopPrice": "23430.00000000",
                "selfTradePreventionMode": "NONE"
            },
            {
                "symbol": "BTCUSDT",
                "origClientOrderId": "Tnu2IP0J5Y4mxw3IATBfmW",
                "orderId": 12569099454,
                "orderListId": 19431,
                "clientOrderId": "OFFXQtxVFZ6Nbcg4PgE2DA",
                "transactTime": 1684804350068,
                "price": "23400.00000000",
                "origQty": "0.00850000",
                "executedQty": "0.00000000",
                "origQuoteOrderQty": "0.000000",
                "cummulativeQuoteQty": "0.00000000",
                "status": "CANCELED",
                "timeInForce": "GTC",
                "type": "LIMIT_MAKER",
                "side": "BUY",
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

**Note:** The payload above does not show all fields that can appear. Please refer to [Conditional fields in Order Responses](#conditional-fields-in-order-responses).

<a id="regarding-cancelrestrictions"></a>

**Regarding `cancelRestrictions`**

* If the `cancelRestrictions` value is not any of the supported values, the error will be:
```json
{
    "code": -1145,
    "msg": "Invalid cancelRestrictions"
}
```
* If the order did not pass the conditions for `cancelRestrictions`, the error will be:
```json
{
    "code": -2011,
    "msg": "Order was not canceled due to cancel restrictions."
}
```

### Cancel and replace order (TRADE)

```javascript
{
    "id": "99de1036-b5e2-4e0f-9b5c-13d751c93a1a",
    "method": "order.cancelReplace",
    "params": {
        "symbol": "BTCUSDT",
        "cancelReplaceMode": "ALLOW_FAILURE",
        "cancelOrigClientOrderId": "4d96324ff9d44481926157",
        "side": "SELL",
        "type": "LIMIT",
        "timeInForce": "GTC",
        "price": "23416.10000000",
        "quantity": "0.00847000",
        "apiKey": "key",
        "signature": "7028fdc187868754d25e42c37ccfa5ba2bab1d180ad55d4c3a7e2de643943dc5",
        "timestamp": 1660813156900
    }
}
```

* Cancel an existing order and immediately place a new order instead of the canceled one.
* A new order that was not attempted (i.e. when `newOrderResult: NOT_ATTEMPTED`), will still increase the unfilled order count by 1.
* You can only cancel an individual order from an orderList using this method, but the result is the same as canceling the entire orderList.

**Weight:**
1

**Unfilled Order Count:**
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
        <td><code>cancelReplaceMode</code></td>
        <td>ENUM</td>
        <td>YES</td>
        <td></td>
    </tr>
    <tr>
        <td><code>cancelOrderId</code></td>
        <td>LONG</td>
        <td rowspan="2">YES</td>
        <td>Cancel order by <code>orderId</code></td>
    </tr>
    <tr>
        <td><code>cancelOrigClientOrderId</code></td>
        <td>STRING</td>
        <td>Cancel order by <code>clientOrderId</code></td>
    </tr>
    <tr>
        <td><code>cancelNewClientOrderId</code></td>
        <td>STRING</td>
        <td>NO</td>
        <td>New ID for the canceled order. Automatically generated if not sent</td>
    </tr>
    <tr>
        <td><code>side</code></td>
        <td>ENUM</td>
        <td>YES</td>
        <td><code>BUY</code> or <code>SELL</code></td>
    </tr>
    <tr>
        <td><code>type</code></td>
        <td>ENUM</td>
        <td>YES</td>
        <td></td>
    </tr>
    <tr>
        <td><code>timeInForce</code></td>
        <td>ENUM</td>
        <td>NO *</td>
        <td></td>
    </tr>
    <tr>
        <td><code>price</code></td>
        <td>DECIMAL</td>
        <td>NO *</td>
        <td></td>
    </tr>
    <tr>
        <td><code>quantity</code></td>
        <td>DECIMAL</td>
        <td>NO *</td>
        <td></td>
    </tr>
    <tr>
        <td><code>quoteOrderQty</code></td>
        <td>DECIMAL</td>
        <td>NO *</td>
        <td></td>
    </tr>
    <tr>
        <td><code>newClientOrderId</code></td>
        <td>STRING</td>
        <td>NO</td>
        <td>Arbitrary unique ID among open orders. Automatically generated if not sent</td>
    </tr>
    <tr>
        <td><code>newOrderRespType</code></td>
        <td>ENUM</td>
        <td>NO</td>
        <td>
            <p>Select response format: <code>ACK</code>, <code>RESULT</code>, <code>FULL</code>.</p>
            <p>
                <code>MARKET</code> and <code>LIMIT</code> orders produce <code>FULL</code> response by default,
                other order types default to <code>ACK</code>.
            </p>
        </td>
    </tr>
    <tr>
        <td><code>stopPrice</code></td>
        <td>DECIMAL</td>
        <td>NO *</td>
        <td></td>
    </tr>
    <tr>
        <td><code>trailingDelta</code></td>
        <td>DECIMAL</td>
        <td>NO *</td>
        <td>See <a href="faqs/trailing-stop-faq.md">Trailing Stop order FAQ</a></td>
    </tr>
    <tr>
        <td><code>icebergQty</code></td>
        <td>DECIMAL</td>
        <td>NO</td>
        <td></td>
    </tr>
    <tr>
        <td><code>strategyId</code></td>
        <td>LONG</td>
        <td>NO</td>
        <td>Arbitrary numeric value identifying the order within an order strategy.</td>
    </tr>
    <tr>
        <td><code>strategyType</code></td>
        <td>INT</td>
        <td>NO</td>
        <td>
            <p>Arbitrary numeric value identifying the order strategy.</p>
            <p>Values smaller than <tt>1000000</tt> are reserved and cannot be used.</p>
        </td>
    </tr>
    <tr>
        <td><code>selfTradePreventionMode</code></td>
        <td>ENUM</td>
        <td>NO</td>
        <td>
            <p>The allowed enums is dependent on what is configured on the symbol.</p>
            <p>Supported values: <a href="enums.md#stpmodes">STP Modes</a>.</p>
        </td>
    </tr>
    <tr>
      <td><code>cancelRestrictions</code></td>
      <td>ENUM</td>
      <td>NO</td>
      <td>Supported values: <br><code>ONLY_NEW</code> - Cancel will succeed if the order status is <code>NEW</code>.<br> <code>ONLY_PARTIALLY_FILLED</code> - Cancel will succeed if order status is <code>PARTIALLY_FILLED</code>. For more information please refer to <a href="#regarding-cancelrestrictions">Regarding <code>cancelRestrictions</code></a>.</td>
    </tr>
    <tr>
        <td><code>apiKey</code></td>
        <td>STRING</td>
        <td>YES</td>
        <td></td>
    </tr>
    <tr>
        <td><code>orderRateLimitExceededMode</code></td>
        <td>ENUM</td>
        <td>NO</td>
        <td>Supported values: <br> <code>DO_NOTHING</code> (default)- will only attempt to cancel the order if account has not exceeded the unfilled order rate limit<br> <code>CANCEL_ONLY</code> - will always cancel the order.</td>
    </tr>
    <tr>
        <td><code>pegPriceType</code></td>
        <td>ENUM</td>
        <td>NO</td>
        <td><code>PRIMARY_PEG</code> or <code>MARKET_PEG</code>. <br>See <a href="#pegged-orders-info">Pegged Orders</a>"</td>
    </tr>
    <tr>
        <td><code>pegOffsetValue</code></td>
        <td>INT</td>
        <td>NO</td>
        <td>Price level to peg the price to (max: 100) <br> See <a href="#pegged-orders-info">Pegged Orders</a></td>
    </tr>
    <tr>
        <td><code>pegOffsetType</code></td>
        <td>ENUM</td>
        <td>NO</td>
        <td>Only <code>PRICE_LEVEL</code> is supported<br>See <a href="#pegged-orders-info">Pegged Orders</a></td>
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

Similar to the [`order.place`](#place-new-order-trade) request,
additional mandatory parameters (*) are determined by the new order [`type`](#order-type).

Available `cancelReplaceMode` options:

* `STOP_ON_FAILURE` – if cancellation request fails, new order placement will not be attempted.
* `ALLOW_FAILURE` – new order placement will be attempted even if the cancel request fails.

<table>
<thead>
    <tr>
        <th colspan=3 align=left>Request</th>
        <th colspan=3 align=left>Response</th>
    </tr>
    <tr>
        <th><code>cancelReplaceMode</code></th>
        <th><code>orderRateLimitExceededMode</code></th>
        <th>Unfilled Order Count</th>
        <th><code>cancelResult</code></th>
        <th><code>newOrderResult</code></th>
        <th><code>status</code></th>
    </tr>
</thead>
<tbody>
    <tr>
        <td rowspan="11"><code>STOP_ON_FAILURE</code></td>
        <td rowspan="6"><code>DO_NOTHING</code></td>
        <td rowspan="3">Within Limits</td>
        <td>✅ <code>SUCCESS</code></td>
        <td>✅ <code>SUCCESS</code></td>
        <td align=right><code>200</code></td>
    </tr>
    <tr>
        <td>❌ <code>FAILURE</code></td>
        <td>➖ <code>NOT_ATTEMPTED</code></td>
        <td align=right><code>400</code></td>
    </tr>
    <tr>
        <td>✅ <code>SUCCESS</code></td>
        <td>❌ <code>FAILURE</code></td>
        <td align=right><code>409</code></td>
    </tr>
    <tr>
        <td rowspan="3">Exceeds Limits</td>
        <td>✅ <code>SUCCESS</code></td>
        <td>✅ <code>SUCCESS</code></td>
        <td align=right>N/A</td>
    </tr>
    <tr>
        <td>❌ <code>FAILURE</code></td>
        <td>➖ <code>NOT_ATTEMPTED</code></td>
        <td align=right>N/A</td>
    </tr>
    <tr>
        <td>✅ <code>SUCCESS</code></td>
        <td>❌ <code>FAILURE</code></td>
        <td align=right>N/A</td>
    </tr>
     <tr>
        <td rowspan="5"><code>CANCEL_ONLY</code></td>
        <td rowspan="3">Within Limits</td>
        <td>✅ <code>SUCCESS</code></td>
        <td>✅ <code>SUCCESS</code></td>
        <td align=right><code>200</code></td>
    </tr>
    <tr>
        <td>❌ <code>FAILURE</code></td>
        <td>➖ <code>NOT_ATTEMPTED</code></td>
        <td align=right><code>400</code></td>
    </tr>
    <tr>
        <td>✅ <code>SUCCESS</code></td>
        <td>❌ <code>FAILURE</code></td>
        <td align=right><code>409</code></td>
    </tr>
    <tr>
        <td rowspan="2">Exceeds Limits</td>
        <td>❌ <code>FAILURE</code></td>
        <td>➖ <code>NOT_ATTEMPTED</code></td>
        <td align=right><code>429</code></td>
    </tr>
    <tr>
        <td>✅ <code>SUCCESS</code></td>
        <td>❌ <code>FAILURE</code></td>
        <td align=right><code>429</code></td>
    </tr>
    <tr>
        <td rowspan="16"><code>ALLOW_FAILURE</code></td>
        <td rowspan="8"><code>DO_NOTHING</code></td>
        <td rowspan="4">Within Limits</td>
        <td>✅ <code>SUCCESS</code></td>
        <td>✅ <code>SUCCESS</code></td>
        <td align=right><code>200</code></td>
    </tr>
    <tr>
        <td>❌ <code>FAILURE</code></td>
        <td>❌ <code>FAILURE</code></td>
        <td align=right><code>400</code></td>
    </tr>
    <tr>
        <td>❌ <code>FAILURE</code></td>
        <td>✅ <code>SUCCESS</code></td>
        <td align=right><code>409</code></td>
    </tr>
    <tr>
        <td>✅ <code>SUCCESS</code></td>
        <td>❌ <code>FAILURE</code></td>
        <td align=right><code>409</code></td>
    </tr>
    <tr>
     <td rowspan="4">Exceeds Limits</td>
        <td>✅ <code>SUCCESS</code></td>
        <td>✅ <code>SUCCESS</code></td>
        <td align=right>N/A</td>
    </tr>
    <tr>
        <td>❌ <code>FAILURE</code></td>
        <td>❌ <code>FAILURE</code></td>
        <td align=right>N/A</td>
    </tr>
    <tr>
        <td>❌ <code>FAILURE</code></td>
        <td>✅ <code>SUCCESS</code></td>
        <td align=right>N/A</td>
    </tr>
    <tr>
        <td>✅ <code>SUCCESS</code></td>
        <td>❌ <code>FAILURE</code></td>
        <td align=right>N/A</td>
    </tr>
    <tr>
        <td rowspan="8"><CODE>CANCEL_ONLY</CODE></td>
        <td rowspan="4">Within Limits</td>
        <td>✅ <code>SUCCESS</code></td>
        <td>✅ <code>SUCCESS</code></td>
        <td align=right><code>200</code></td>
    </tr>
    <tr>
        <td>❌ <code>FAILURE</code></td>
        <td>❌ <code>FAILURE</code></td>
        <td align=right><code>400</code></td>
    </tr>
    <tr>
        <td>❌ <code>FAILURE</code></td>
        <td>✅ <code>SUCCESS</code></td>
        <td align=right><code>409</code></td>
    </tr>
    <tr>
        <td>✅ <code>SUCCESS</code></td>
        <td>❌ <code>FAILURE</code></td>
        <td align=right><code>409</code></td>
    </tr>
    <tr>
        <td rowspan="4">Exceeds Limits</td>
        <td>✅ <code>SUCCESS</code></td>
        <td>✅ <code>SUCCESS</code></td>
        <td align=right><code>200</code></td>
    </tr>
    <tr>
        <td>❌ <code>FAILURE</code></td>
        <td>❌ <code>FAILURE</code></td>
        <td align=right><code>400</code></td>
    </tr>
    <tr>
        <td>❌ <code>FAILURE</code></td>
        <td>✅ <code>SUCCESS</code></td>
        <td align=right>N/A</td>
    </tr>
    <tr>
        <td>✅ <code>SUCCESS</code></td>
        <td>❌ <code>FAILURE</code></td>
        <td align=right><code>409</code></td>
    </tr>
</tbody>
</table>

Notes:

* If both `cancelOrderId` and `cancelOrigClientOrderId` parameters are provided, the `cancelOrderId` is searched first, then the `cancelOrigClientOrderId` from that result is checked against that order. If both conditions are not met the request will be rejected.

* `cancelNewClientOrderId` will replace `clientOrderId` of the canceled order, freeing it up for new orders.

* `newClientOrderId` specifies `clientOrderId` value for the placed order.

  A new order with the same `clientOrderId` is accepted only when the previous one is filled or expired.

  The new order can reuse old `clientOrderId` of the canceled order.

* This cancel-replace operation is **not transactional**.

  If one operation succeeds but the other one fails, the successful operation is still executed.

  For example, in `STOP_ON_FAILURE` mode, if the new order placement fails, the old order is still canceled.

* Filters and order count limits are evaluated before cancellation and order placement occurs.

* If new order placement is not attempted, your order count is still incremented.

* Like [`order.cancel`](#cancel-order-trade), if you cancel an individual order from an order list, the entire order list is canceled.

* The performance for canceling an order (single cancel or as part of a cancel-replace) is always better when only `orderId` is sent. Sending `origClientOrderId` or both `orderId` + `origClientOrderId` will be slower.

**Data Source:**
Matching Engine

**Response:**

If both cancel and placement succeed, you get the following response with `"status": 200`:

```javascript
{
    "id": "99de1036-b5e2-4e0f-9b5c-13d751c93a1a",
    "status": 200,
    "result": {
        "cancelResult": "SUCCESS",
        "newOrderResult": "SUCCESS",
        // Format is identical to "order.cancel" format.
        // Some fields are optional and are included only for orders that set them.
        "cancelResponse": {
            "symbol": "BTCUSDT",
            "origClientOrderId": "4d96324ff9d44481926157",     // cancelOrigClientOrderId from request
            "orderId": 125690984230,
            "orderListId": -1,
            "clientOrderId": "91fe37ce9e69c90d6358c0",         // cancelNewClientOrderId from request
            "transactTime": 1684804350068,
            "price": "23450.00000000",
            "origQty": "0.00847000",
            "executedQty": "0.00001000",
            "origQuoteOrderQty": "0.000000",
            "cummulativeQuoteQty": "0.23450000",
            "status": "CANCELED",
            "timeInForce": "GTC",
            "type": "LIMIT",
            "side": "SELL",
            "selfTradePreventionMode": "NONE"
        },
        // Format is identical to "order.place" format, affected by "newOrderRespType".
        // Some fields are optional and are included only for orders that set them.
        "newOrderResponse": {
            "symbol": "BTCUSDT",
            "orderId": 12569099453,
            "orderListId": -1,
            "clientOrderId": "bX5wROblo6YeDwa9iTLeyY",         // newClientOrderId from request
            "transactTime": 1660813156959,
            "price": "23416.10000000",
            "origQty": "0.00847000",
            "executedQty": "0.00000000",
            "origQuoteOrderQty": "0.000000",
            "cummulativeQuoteQty": "0.00000000",
            "status": "NEW",
            "timeInForce": "GTC",
            "type": "LIMIT",
            "side": "SELL",
            "selfTradePreventionMode": "NONE"
        }
    },
    "rateLimits": [
        {
            "rateLimitType": "ORDERS",
            "interval": "SECOND",
            "intervalNum": 10,
            "limit": 50,
            "count": 1
        },
        {
            "rateLimitType": "ORDERS",
            "interval": "DAY",
            "intervalNum": 1,
            "limit": 160000,
            "count": 1
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

In `STOP_ON_FAILURE` mode, failed order cancellation prevents new order from being placed
and returns the following response with `"status": 400`:

```javascript
{
    "id": "27e1bf9f-0539-4fb0-85c6-06183d36f66c",
    "status": 400,
    "error": {
        "code": -2022,
        "msg": "Order cancel-replace failed.",
        "data": {
            "cancelResult": "FAILURE",
            "newOrderResult": "NOT_ATTEMPTED",
            "cancelResponse": {
                "code": -2011,
                "msg": "Unknown order sent."
            },
            "newOrderResponse": null
        }
    },
    "rateLimits": [
        {
            "rateLimitType": "ORDERS",
            "interval": "SECOND",
            "intervalNum": 10,
            "limit": 50,
            "count": 1
        },
        {
            "rateLimitType": "ORDERS",
            "interval": "DAY",
            "intervalNum": 1,
            "limit": 160000,
            "count": 1
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

If cancel-replace mode allows failure and one of the operations fails,
you get a response with `"status": 409`,
and the `"data"` field detailing which operation succeeded, which failed, and why:

```javascript
{
    "id": "b220edfe-f3c4-4a3a-9d13-b35473783a25",
    "status": 409,
    "error": {
        "code": -2021,
        "msg": "Order cancel-replace partially failed.",
        "data": {
            "cancelResult": "SUCCESS",
            "newOrderResult": "FAILURE",
            "cancelResponse": {
                "symbol": "BTCUSDT",
                "origClientOrderId": "4d96324ff9d44481926157",
                "orderId": 125690984230,
                "orderListId": -1,
                "clientOrderId": "91fe37ce9e69c90d6358c0",
                "transactTime": 1684804350068,
                "price": "23450.00000000",
                "origQty": "0.00847000",
                "executedQty": "0.00001000",
                "origQuoteOrderQty": "0.000000",
                "cummulativeQuoteQty": "0.23450000",
                "status": "CANCELED",
                "timeInForce": "GTC",
                "type": "LIMIT",
                "side": "SELL",
                "selfTradePreventionMode": "NONE"
            },
            "newOrderResponse": {
                "code": -2010,
                "msg": "Order would immediately match and take."
            }
        }
    },
    "rateLimits": [
        {
            "rateLimitType": "ORDERS",
            "interval": "SECOND",
            "intervalNum": 10,
            "limit": 50,
            "count": 1
        },
        {
            "rateLimitType": "ORDERS",
            "interval": "DAY",
            "intervalNum": 1,
            "limit": 160000,
            "count": 1
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

```javascript
{
    "id": "ce641763-ff74-41ac-b9f7-db7cbe5e93b1",
    "status": 409,
    "error": {
        "code": -2021,
        "msg": "Order cancel-replace partially failed.",
        "data": {
            "cancelResult": "FAILURE",
            "newOrderResult": "SUCCESS",
            "cancelResponse": {
                "code": -2011,
                "msg": "Unknown order sent."
            },
            "newOrderResponse": {
                "symbol": "BTCUSDT",
                "orderId": 12569099453,
                "orderListId": -1,
                "clientOrderId": "bX5wROblo6YeDwa9iTLeyY",
                "transactTime": 1660813156959,
                "price": "23416.10000000",
                "origQty": "0.00847000",
                "executedQty": "0.00000000",
                "origQuoteOrderQty": "0.000000",
                "cummulativeQuoteQty": "0.00000000",
                "status": "NEW",
                "timeInForce": "GTC",
                "type": "LIMIT",
                "side": "SELL",
                "workingTime": 1669693344508,
                "fills": [],
                "selfTradePreventionMode": "NONE"
            }
        }
    },
    "rateLimits": [
        {
            "rateLimitType": "ORDERS",
            "interval": "SECOND",
            "intervalNum": 10,
            "limit": 50,
            "count": 1
        },
        {
            "rateLimitType": "ORDERS",
            "interval": "DAY",
            "intervalNum": 1,
            "limit": 160000,
            "count": 1
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

If both operations fail, response will have `"status": 400`:

```javascript
{
    "id": "3b3ac45c-1002-4c7d-88e8-630c408ecd87",
    "status": 400,
    "error": {
        "code": -2022,
        "msg": "Order cancel-replace failed.",
        "data": {
            "cancelResult": "FAILURE",
            "newOrderResult": "FAILURE",
            "cancelResponse": {
                "code": -2011,
                "msg": "Unknown order sent."
            },
            "newOrderResponse": {
                "code": -2010,
                "msg": "Order would immediately match and take."
            }
        }
    },
    "rateLimits": [
        {
            "rateLimitType": "ORDERS",
            "interval": "SECOND",
            "intervalNum": 10,
            "limit": 50,
            "count": 1
        },
        {
            "rateLimitType": "ORDERS",
            "interval": "DAY",
            "intervalNum": 1,
            "limit": 160000,
            "count": 1
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

If `orderRateLimitExceededMode` is `DO_NOTHING` regardless of `cancelReplaceMode`, and you have exceeded your unfilled order count, you will get status `429` with the following error:

```javascript
{
    "id": "3b3ac45c-1002-4c7d-88e8-630c408ecd87",
    "status": 429,
    "error": {
        "code": -1015,
        "msg": "Too many new orders; current limit is 50 orders per 10 SECOND."
    },
    "rateLimits": [
        {
            "rateLimitType": "ORDERS",
            "interval": "SECOND",
            "intervalNum": 10,
            "limit": 50,
            "count": 50
        },
        {
            "rateLimitType": "ORDERS",
            "interval": "DAY",
            "intervalNum": 1,
            "limit": 160000,
            "count": 50
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

If `orderRateLimitExceededMode` is `CANCEL_ONLY` regardless of `cancelReplaceMode`, and you have exceeded your unfilled order count, you will get status `409` with the following error:

```javascript
{
    "id": "3b3ac45c-1002-4c7d-88e8-630c408ecd87",
    "status": 409,
    "error": {
        "code": -2021,
        "msg": "Order cancel-replace partially failed.",
        "data": {
            "cancelResult": "SUCCESS",
            "newOrderResult": "FAILURE",
            "cancelResponse": {
                "symbol": "LTCBNB",
                "origClientOrderId": "GKt5zzfOxRDSQLveDYCTkc",
                "orderId": 64,
                "orderListId": -1,
                "clientOrderId": "loehOJF3FjoreUBDmv739R",
                "transactTime": 1715779007228,
                "price": "1.00",
                "origQty": "10.00000000",
                "executedQty": "0.00000000",
                "origQuoteOrderQty": "0.000000",
                "cummulativeQuoteQty": "0.00",
                "status": "CANCELED",
                "timeInForce": "GTC",
                "type": "LIMIT",
                "side": "SELL",
                "selfTradePreventionMode": "NONE"
            },
            "newOrderResponse": {
                "code": -1015,
                "msg": "Too many new orders; current limit is 50 orders per 10 SECOND."
            }
        }
    },
    "rateLimits": [
        {
            "rateLimitType": "ORDERS",
            "interval": "SECOND",
            "intervalNum": 10,
            "limit": 50,
            "count": 50
        },
        {
            "rateLimitType": "ORDERS",
            "interval": "DAY",
            "intervalNum": 1,
            "limit": 160000,
            "count": 50
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

**Note:** The payload above does not show all fields that can appear. Please refer to [Conditional fields in Order Responses](#conditional-fields-in-order-responses).

### Order Amend Keep Priority (TRADE)

```javascript
{
    "id": "56374a46-3061-486b-a311-89ee972eb648",
    "method": "order.amend.keepPriority",
    "params": {
        "newQty": "5",
        "origClientOrderId": "my_test_order1",
        "recvWindow": 5000,
        "symbol": "BTCUSDT",
        "timestamp": 1741922620419,
        "apiKey": "key",
        "signature": "fa49c0c4ebc331c6ebd3fcb20deb387f60081ea858eebe6e35aa6fcdf2a82e08"
    }
}
```

Reduce the quantity of an existing open order.

This adds 0 orders to the `EXCHANGE_MAX_ORDERS` filter and the `MAX_NUM_ORDERS` filter.

Read [Order Amend Keep Priority FAQ](https://developers.binance.com/docs/binance-spot-api-docs/faqs/order_amend_keep_priority.md) to learn more.

**Weight**: 4

**Unfilled Order Count:**
0

**Parameters:**

Name | Type | Mandatory | Description |
:---- | :---- | :---- | :---- |
symbol | STRING | YES |  |
orderId | LONG | NO\* | `orderId` or `origClientOrderId` must be sent  |
origClientOrderId | STRING | NO\* | `orderId` or `origClientOrderId` must be sent  |
newClientOrderId | STRING | NO\* | The new client order ID for the order after being amended. <br> If not sent, one will be randomly generated. <br> It is possible to reuse the current clientOrderId by sending it as the `newClientOrderId`. |
newQty | DECIMAL | YES | `newQty` must be greater than 0 and less than the order's quantity. |
recvWindow | DECIMAL | NO | The value cannot be greater than `60000`. <br> Supports up to three decimal places of precision (e.g., 6000.346) so that microseconds may be specified.
timestamp | LONG | YES |

**Data Source**:
Matching Engine

**Response:**

Response for a single order:

```javascript
{
    "id": "56374a46-3061-486b-a311-89ee972eb648",
    "status": 200,
    "result": {
        "transactTime": 1741923284382,
        "executionId": 16,
        "amendedOrder": {
            "symbol": "BTCUSDT",
            "orderId": 12,
            "orderListId": -1,
            "origClientOrderId": "my_test_order1",
            "clientOrderId": "4zR9HFcEq8gM1tWUqPEUHc",
            "price": "5.00000000",
            "qty": "5.00000000",
            "executedQty": "0.00000000",
            "preventedQty": "0.00000000",
            "quoteOrderQty": "0.00000000",
            "cumulativeQuoteQty": "0.00000000",
            "status": "NEW",
            "timeInForce": "GTC",
            "type": "LIMIT",
            "side": "BUY",
            "workingTime": 1741923284364,
            "selfTradePreventionMode": "NONE"
        }
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

Response for an order which is part of an Order list:

```javascript
{
    "id": "56374b46-3061-486b-a311-89ee972eb648",
    "status": 200,
    "result": {
        "transactTime": 1741924229819,
        "executionId": 60,
        "amendedOrder": {
            "symbol": "BTUCSDT",
            "orderId": 23,
            "orderListId": 4,
            "origClientOrderId": "my_pending_order",
            "clientOrderId": "xbxXh5SSwaHS7oUEOCI88B",
            "price": "1.00000000",
            "qty": "5.00000000",
            "executedQty": "0.00000000",
            "preventedQty": "0.00000000",
            "quoteOrderQty": "0.00000000",
            "cumulativeQuoteQty": "0.00000000",
            "status": "NEW",
            "timeInForce": "GTC",
            "type": "LIMIT",
            "side": "BUY",
            "workingTime": 1741924204920,
            "selfTradePreventionMode": "NONE"
        },
        "listStatus": {
            "orderListId": 4,
            "contingencyType": "OTO",
            "listOrderStatus": "EXECUTING",
            "listClientOrderId": "8nOGLLawudj1QoOiwbroRH",
            "symbol": "BTCUSDT",
            "orders": [
                {
                    "symbol": "BTCUSDT",
                    "orderId": 22,
                    "clientOrderId": "g04EWsjaackzedjC9wRkWD"
                },
                {
                    "symbol": "BTCUSDT",
                    "orderId": 23,
                    "clientOrderId": "xbxXh5SSwaHS7oUEOCI88B"
                }
            ]
        }
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

**Note:** The payloads above do not show all fields that can appear. Please refer to [Conditional fields in Order Responses](#conditional-fields-in-order-responses).


### Cancel open orders (TRADE)

```javascript
{
    "id": "778f938f-9041-4b88-9914-efbf64eeacc8",
    "method": "openOrders.cancelAll",
    "params": {
        "symbol": "BTCUSDT",
        "apiKey": "key",
        "signature": "773f01b6e3c2c9e0c1d217bc043ce383c1ddd6f0e25f8d6070f2b66a6ceaf3a5",
        "timestamp": 1660805557200
    }
}
```

Cancel all open orders on a symbol.
This includes orders that are part of an order list.

**Weight:**
1

**Parameters:**

Name                | Type    | Mandatory | Description
------------------- | ------- | --------- | ------------
`symbol`            | STRING  | YES       |
`apiKey`            | STRING  | YES       |
`recvWindow`        | DECIMAL | NO        | The value cannot be greater than `60000`. <br> Supports up to three decimal places of precision (e.g., 6000.346) so that microseconds may be specified.
`signature`         | STRING  | YES       |
`timestamp`         | LONG    | YES       |

**Data Source:**
Matching Engine

**Response:**

Cancellation reports for orders and order lists have the same format as in [`order.cancel`](#cancel-order-trade).

```javascript
{
    "id": "778f938f-9041-4b88-9914-efbf64eeacc8",
    "status": 200,
    "result": [
        {
            "symbol": "BTCUSDT",
            "origClientOrderId": "4d96324ff9d44481926157",
            "orderId": 12569099453,
            "orderListId": -1,
            "clientOrderId": "91fe37ce9e69c90d6358c0",
            "transactTime": 1684804350068,
            "price": "23416.10000000",
            "origQty": "0.00847000",
            "executedQty": "0.00001000",
            "origQuoteOrderQty": "0.000000",
            "cummulativeQuoteQty": "0.23416100",
            "status": "CANCELED",
            "timeInForce": "GTC",
            "type": "LIMIT",
            "side": "SELL",
            "stopPrice": "0.00000000",
            "trailingDelta": 0,
            "trailingTime": -1,
            "icebergQty": "0.00000000",
            "strategyId": 37463720,
            "strategyType": 1000000,
            "selfTradePreventionMode": "NONE"
        },
        {
            "orderListId": 19431,
            "contingencyType": "OCO",
            "listStatusType": "ALL_DONE",
            "listOrderStatus": "ALL_DONE",
            "listClientOrderId": "iuVNVJYYrByz6C4yGOPPK0",
            "transactionTime": 1660803702431,
            "symbol": "BTCUSDT",
            "orders": [
                {
                    "symbol": "BTCUSDT",
                    "orderId": 12569099453,
                    "clientOrderId": "bX5wROblo6YeDwa9iTLeyY"
                },
                {
                    "symbol": "BTCUSDT",
                    "orderId": 12569099454,
                    "clientOrderId": "Tnu2IP0J5Y4mxw3IATBfmW"
                }
            ],
            "orderReports": [
                {
                    "symbol": "BTCUSDT",
                    "origClientOrderId": "bX5wROblo6YeDwa9iTLeyY",
                    "orderId": 12569099453,
                    "orderListId": 19431,
                    "clientOrderId": "OFFXQtxVFZ6Nbcg4PgE2DA",
                    "transactTime": 1684804350068,
                    "price": "23450.50000000",
                    "origQty": "0.00850000",
                    "executedQty": "0.00000000",
                    "origQuoteOrderQty": "0.000000",
                    "cummulativeQuoteQty": "0.00000000",
                    "status": "CANCELED",
                    "timeInForce": "GTC",
                    "type": "STOP_LOSS_LIMIT",
                    "side": "BUY",
                    "stopPrice": "23430.00000000",
                    "selfTradePreventionMode": "NONE"
                },
                {
                    "symbol": "BTCUSDT",
                    "origClientOrderId": "Tnu2IP0J5Y4mxw3IATBfmW",
                    "orderId": 12569099454,
                    "orderListId": 19431,
                    "clientOrderId": "OFFXQtxVFZ6Nbcg4PgE2DA",
                    "transactTime": 1684804350068,
                    "price": "23400.00000000",
                    "origQty": "0.00850000",
                    "executedQty": "0.00000000",
                    "origQuoteOrderQty": "0.000000",
                    "cummulativeQuoteQty": "0.00000000",
                    "status": "CANCELED",
                    "timeInForce": "GTC",
                    "type": "LIMIT_MAKER",
                    "side": "BUY",
                    "selfTradePreventionMode": "NONE"
                }
            ]
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

**Note:** The payload above does not show all fields that can appear. Please refer to [Conditional fields in Order Responses](#conditional-fields-in-order-responses).
