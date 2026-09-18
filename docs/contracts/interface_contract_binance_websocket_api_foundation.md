---
document_id: AI4B-BINANCE-IFC-101
title: Binance WebSocket API Foundation Reference
document_type: INTERFACE_CONTRACT
version: 1.0.0
status: ACTIVE
owner: Enterprise Governance
authority_level: EXTERNAL_AUTHORITY
authority_layer: L3_CANONICAL_CONTRACTS_SCHEMAS
authority_scope: binance_websocket_api_foundation
content_role: DERIVED
source_of_truth: false
canonical_path: docs/contracts/interface_contract_binance_websocket_api_foundation.md
machine_enforceable: false
audit_required: true
classification: INTERNAL
---
# Binance WebSocket API Foundation Reference

## ELI10

This document keeps the general Binance WebSocket API rules in a small reference file.

## Source Lineage

- Source file: `docs/contracts/interface_contract_binance_websocket_api_reference.md`
- Source section start: `# Public WebSocket API for Binance`
- This file preserves a bounded section of the governed source document.

# Public WebSocket API for Binance

## General API Information

* The base endpoint is: **`wss://ws-api.binance.com:443/ws-api/v3`**.
  * If you experience issues with the standard 443 port, alternative port 9443 is also available.
  * The base endpoint for [testnet](https://testnet.binance.vision/) is: `wss://ws-api.testnet.binance.vision/ws-api/v3`
* A single connection to the API is only valid for 24 hours; expect to be disconnected after the 24-hour mark.
* A [`serverShutdown`](#serverShutdown) event will be sent when the server is about to shutdown, resulting in disconnection. Please establish a new connection as soon as possible to prevent interruption.
* We support HMAC, RSA, and Ed25519 keys. For more information, please see [API Key types](https://developers.binance.com/docs/binance-spot-api-docs/faqs/api_key_types.md).
* Responses are in JSON by default. To receive responses in SBE, refer to the [SBE FAQ](https://developers.binance.com/docs/binance-spot-api-docs/faqs/sbe_faq.md) page.
* If your request contains a symbol name containing non-ASCII characters, then the response may contain non-ASCII characters encoded in UTF-8.
* Some methods may return asset and/or symbol names containing non-ASCII characters encoded in UTF-8 even if the request did not contain non-ASCII characters.
* The WebSocket server will send a `ping frame` every 20 seconds.
  * If the WebSocket server does not receive a `pong frame` back from the connection within a minute the connection will be disconnected.
  * When you receive a ping, you must send a pong with a copy of ping's payload as soon as possible.
  * Unsolicited `pong frames` are allowed, but will not prevent disconnection. **It is recommended that the payload for these pong frames are empty.**
* Data is returned in **chronological order**, unless noted otherwise.
  * Without `startTime` or `endTime`, returns the most recent items up to the limit.
  * With `startTime`, returns oldest items from `startTime` up to the limit.
  * With `endTime`, returns most recent items up to `endTime` and the limit.
  * With both, behaves like `startTime` but does not exceed `endTime`.
* All timestamps in the JSON responses are in **milliseconds in UTC by default**. To receive the information in microseconds, please add the parameter `timeUnit=MICROSECOND` or `timeUnit=microsecond` in the URL.
* Timestamp parameters (e.g. `startTime`, `endTime`, `timestamp`) can be passed in milliseconds or microseconds.
* All field names and values are **case-sensitive**, unless noted otherwise.
* If there are enums or terms you want clarification on, please see [SPOT Glossary](https://developers.binance.com/docs/binance-spot-api-docs/faqs/spot_glossary.md) for more information.
* APIs have a timeout of 10 seconds when processing a request. If a response from the Matching Engine takes longer than this, the API responds with "Timeout waiting for response from backend server. Send status unknown; execution status unknown." [(-1007 TIMEOUT)](https://developers.binance.com/docs/binance-spot-api-docs/errors.md#-1007-timeout)
  * This does not always mean that the request failed in the Matching Engine.
  * If the status of the request has not appeared in [User Data Stream](https://developers.binance.com/docs/binance-spot-api-docs/user-data-stream.md), please perform an API query for its status.
* **Please avoid SQL keywords in requests** as they may trigger a security block by a WAF (Web Application Firewall) rule. See https://www.binance.com/en/support/faq/detail/360004492232 for more details.


## Request format

Requests must be sent as JSON in **text frames**, one request per frame.

Example of request:

```json
{
    "id": "e2a85d9f-07a5-4f94-8d5f-789dc3deb097",
    "method": "order.place",
    "params": {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "type": "LIMIT",
        "price": "0.1",
        "quantity": "10",
        "timeInForce": "GTC",
        "timestamp": 1655716096498,
        "apiKey": "key",
        "signature": "5942ad337e6779f2f4c62cd1c26dba71c91514400a24990a3e7f5edec9323f90"
    }
}
```

Request fields:

Name     | Type    | Mandatory | Description
--------- | ------- | --------- | -----------
`id`      | INT / STRING / `null` | YES | Arbitrary ID used to match responses to requests
`method`  | STRING  | YES       | Request method name
`params`  | OBJECT  | NO        | Request parameters. May be omitted if there are no parameters

* Request `id` is truly arbitrary. You can use UUIDs, sequential IDs, current timestamp, etc.
  The server does not interpret `id` in any way, simply echoing it back in the response.

  You can freely reuse IDs within a session.
  However, be careful to not send more than one request at a time with the same ID,
  since otherwise it might be impossible to tell the responses apart.

* Request method names may be prefixed with explicit version: e.g., `"v3/order.place"`.

* The order of `params` is not significant.

## Response format

Responses are returned as JSON in **text frames**, one response per frame.

Example of successful response:

```json
{
    "id": "e2a85d9f-07a5-4f94-8d5f-789dc3deb097",
    "status": 200,
    "result": {
        "symbol": "BTCUSDT",
        "orderId": 12510053279,
        "orderListId": -1,
        "clientOrderId": "a097fe6304b20a7e4fc436",
        "transactTime": 1655716096505,
        "price": "0.10000000",
        "origQty": "10.00000000",
        "executedQty": "0.00000000",
        "origQuoteOrderQty": "0.000000",
        "cummulativeQuoteQty": "0.00000000",
        "status": "NEW",
        "timeInForce": "GTC",
        "type": "LIMIT",
        "side": "BUY",
        "workingTime": 1655716096505,
        "selfTradePreventionMode": "NONE"
    },
    "rateLimits": [
        {
            "rateLimitType": "ORDERS",
            "interval": "SECOND",
            "intervalNum": 10,
            "limit": 50,
            "count": 12
        },
        {
            "rateLimitType": "ORDERS",
            "interval": "DAY",
            "intervalNum": 1,
            "limit": 160000,
            "count": 4043
        },
        {
            "rateLimitType": "REQUEST_WEIGHT",
            "interval": "MINUTE",
            "intervalNum": 1,
            "limit": 6000,
            "count": 321
        }
    ]
}
```

Example of failed response:

```json
{
    "id": "e2a85d9f-07a5-4f94-8d5f-789dc3deb097",
    "status": 400,
    "error": {
        "code": -2010,
        "msg": "Account has insufficient balance for requested action."
    },
    "rateLimits": [
        {
            "rateLimitType": "ORDERS",
            "interval": "SECOND",
            "intervalNum": 10,
            "limit": 50,
            "count": 13
        },
        {
            "rateLimitType": "ORDERS",
            "interval": "DAY",
            "intervalNum": 1,
            "limit": 160000,
            "count": 4044
        },
        {
            "rateLimitType": "REQUEST_WEIGHT",
            "interval": "MINUTE",
            "intervalNum": 1,
            "limit": 6000,
            "count": 322
        }
    ]
}
```

Response fields:

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
    <td><code>id</code></td>
    <td>INT / STRING / <code>null</code></td>
    <td>YES</td>
    <td>Same as in the original request</td>
  </tr>
  <tr>
    <td><code>status</code></td>
    <td>INT</td>
    <td>YES</td>
    <td>Response status. See <a href="#status-codes">Status codes</a></td>
  </tr>
  <tr>
    <td><code>result</code></td>
    <td>OBJECT / ARRAY</td>
    <td rowspan="2">YES</td>
    <td>Response content. Present if request succeeded</td>
  </tr>
  <tr>
    <td><code>error</code></td>
    <td>OBJECT</td>
    <td>Error description. Present if request failed</td>
  </tr>
  <tr>
    <td><code>rateLimits</code></td>
    <td>ARRAY</td>
    <td>NO</td>
    <td>Rate limiting status. See <a href="#rate-limits">Rate limits</a></td>
  </tr>
</tbody>
</table>

### Status codes

Status codes in the `status` field are the same as in HTTP.

Here are some common status codes that you might encounter:

* `200` indicates a successful response.
* `4XX` status codes indicate invalid requests; the issue is on your side.
  * `400` – your request failed, see `error` for the reason.
  * `403` – you have been blocked by the Web Application Firewall. This can indicate a rate limit violation or a security block. See https://www.binance.com/en/support/faq/detail/360004492232 for more details.
  * `409` – your request partially failed but also partially succeeded, see `error` for details.
  * `418` – you have been auto-banned for repeated violation of rate limits.
  * `429` – you have exceeded API request rate limit, please slow down.
* `5XX` status codes indicate internal errors; the issue is on Binance's side.
  * **Important:** If a response contains 5xx status code, it **does not** necessarily mean that your request has failed.
    Execution status is _unknown_ and the request might have actually succeeded.
    Please use query methods to confirm the status.
    You might also want to establish a new WebSocket connection for that.

See [Error codes for Binance](https://developers.binance.com/docs/binance-spot-api-docs/errors.md) for a list of error codes and messages.

## Event format

[User Data Stream](https://developers.binance.com/docs/binance-spot-api-docs/user-data-stream.md) events for non-SBE sessions are sent as JSON in **text frames**, one event per frame.

Events in [SBE sessions](https://developers.binance.com/docs/binance-spot-api-docs/faqs/sbe_faq.md) will be sent as **binary frames**.

Please refer to [`userDataStream.subscribe`](#user-data-stream-subscribe) for details on how to subscribe to User Data Stream in WebSocket API.

Example of an event:

```javascript
{
    "subscriptionId": 0,
    "event": {
        "e": "outboundAccountPosition",
        "E": 1728972148778,
        "u": 1728972148778,
        "B": [
            {
                "a": "BTC",
                "f": "11818.00000000",
                "l": "182.00000000"
            },
            {
                "a": "USDT",
                "f": "10580.00000000",
                "l": "70.00000000"
            }
        ]
    }
}
```

Event fields:

| Name | Type | Mandatory | Description |
| :---- | :---- | :---- | :---- |
| `event` | OBJECT | YES | Event payload. See [User Data Streams](https://developers.binance.com/docs/binance-spot-api-docs/user-data-stream.md) |
| `subscriptionId`|INT| NO| Identifies which subscription the event is coming from. See [User Data Stream subscriptions](#general_info_user_data_stream_subscriptions) |

## Connection events
<a id="serverShutdown"></a>
### Server Shutdown

`serverShutdown` event is sent when the server is about to shut down.

```javascript
{
  "event": {
    "e": "serverShutdown", // Event Type
    "E": 1770123456789     // Event Time
  }
}
```

Please establish a new connection as soon as possible to prevent interruption.

## Rate limits

### Connection limits

There is a limit of **300 connections per attempt every 5 minutes**.

The connection is per **IP address**.

### General information on rate limits

* Current API rate limits can be queried using the [`exchangeInfo`](#exchange-information) request.
* There are multiple rate limit types across multiple intervals.
* Responses can indicate current rate limit status in the optional `rateLimits` field.
* Requests fail with status `429` when unfilled order count or request rate limits are violated.

#### How to interpret rate limits

A response with rate limit status may look like this:

```json
{
    "id": "7069b743-f477-4ae3-81db-db9b8df085d2",
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
            "count": 70
        }
    ]
}
```

The `rateLimits` array describes all currently active rate limits affected by the request.

| Name            | Type    | Mandatory | Description
| --------------- | ------- | --------- | -----------
| `rateLimitType` | ENUM    | YES       | Rate limit type: `REQUEST_WEIGHT`, `ORDERS`
| `interval`      | ENUM    | YES       | Rate limit interval: `SECOND`, `MINUTE`, `HOUR`, `DAY`
| `intervalNum`   | INT     | YES       | Rate limit interval multiplier
| `limit`         | INT     | YES       | Request limit per interval
| `count`         | INT     | YES       | Current usage per interval

Rate limits are accounted by intervals.

For example, a `1 MINUTE` interval starts every minute.
Request submitted at 00:01:23.456 counts towards the 00:01:00 minute's limit.
Once the 00:02:00 minute starts, the count will reset to zero again.

Other intervals behave in a similar manner.
For example, `1 DAY` rate limit resets at 00:00 UTC every day,
and `10 SECOND` interval resets at 00, 10, 20... seconds of each minute.

APIs have multiple rate-limiting intervals.
If you exhaust a shorter interval but the longer interval still allows requests,
you will have to wait for the shorter interval to expire and reset.
If you exhaust a longer interval, you will have to wait for that interval to reset,
even if shorter rate limit count is zero.

#### How to show/hide rate limit information

`rateLimits` field is included with every response by default.

However, rate limit information can be quite bulky.
If you are not interested in detailed rate limit status of every request,
the `rateLimits` field can be omitted from responses to reduce their size.

* Optional `returnRateLimits` boolean parameter in request.

  Use `returnRateLimits` parameter to control whether to include `rateLimits` fields in response to individual requests.

  Default request and response:

  ```json
  { "id": 1, "method": "time" }
  ```

  ```json
  {
      "id": 1,
      "status": 200,
      "result": { "serverTime": 1656400526260 },
      "rateLimits": [
          {
              "rateLimitType": "REQUEST_WEIGHT",
              "interval": "MINUTE",
              "intervalNum": 1,
              "limit": 6000,
              "count": 70
          }
      ]
  }
  ```

  Request and response without rate limit status:

  ```json
  { "id": 2, "method": "time", "params": { "returnRateLimits": false } }
  ```

  ```json
  { "id": 2, "status": 200, "result": { "serverTime": 1656400527891 } }
  ```

* Optional `returnRateLimits` boolean parameter in connection URL.

  If you wish to omit `rateLimits` from all responses by default,
  use `returnRateLimits` parameter in the query string instead:

  ```
  wss://ws-api.binance.com:443/ws-api/v3?returnRateLimits=false
  ```

  This will make all requests made through this connection behave as if you have passed `"returnRateLimits": false`.

  If you _want_ to see rate limits for a particular request,
  you need to explicitly pass the `"returnRateLimits": true` parameter.

**Note:** Your requests are still rate limited if you hide the `rateLimits` field in responses.

### IP limits

* Every request has a certain **weight**, added to your limit as you perform requests.
  * The heavier the request (e.g. querying data from multiple symbols), the more weight the request will cost.
  * Connecting to WebSocket API costs 2 weight.
* Current weight usage is indicated by the `REQUEST_WEIGHT` rate limit type.
* Use the [`exchangeInfo`](#exchange-information) request
  to keep track of the current weight limits.
* Weight is accumulated **per IP address** and is shared by all connections from that address.
* If you go over the weight limit, requests fail with status `429`.
  * This status code indicates you should back off and stop spamming the API.
  * Rate-limited responses include a `retryAfter` field, indicating when you can retry the request.
* **Repeatedly violating rate limits and/or failing to back off after receiving 429s will result in an automated IP ban and you will be disconnected.**
  * Requests from a banned IP address fail with status `418`.
  * `retryAfter` field indicates the timestamp when the ban will be lifted.
* IP bans are tracked and **scale in duration** for repeat offenders, **from 2 minutes to 3 days**.

Successful response indicating that in 1 minute you have used 70 weight out of your 6000 limit:

```json
{
    "id": "7069b743-f477-4ae3-81db-db9b8df085d2",
    "status": 200,
    "result": [],
    "rateLimits": [
        {
            "rateLimitType": "REQUEST_WEIGHT",
            "interval": "MINUTE",
            "intervalNum": 1,
            "limit": 6000,
            "count": 70
        }
    ]
}
```

Failed response indicating that you are banned and the ban will last until epoch `1659146400000`:

```json
{
    "id": "fc93a61a-a192-4cf4-bb2a-a8f0f0c51e06",
    "status": 418,
    "error": {
        "code": -1003,
        "msg": "Way too much request weight used; IP banned until 1659146400000. Please use WebSocket Streams for live updates to avoid bans.",
        "data": {
            "serverTime": 1659142907531,
            "retryAfter": 1659146400000
        }
    },
    "rateLimits": [
        {
            "rateLimitType": "REQUEST_WEIGHT",
            "interval": "MINUTE",
            "intervalNum": 1,
            "limit": 6000,
            "count": 2411
        }
    ]
}
```

### Unfilled Order Count

* Successfully placed orders update the `ORDERS` rate limit type.
* Rejected or unsuccessful orders might or might not update the `ORDERS` rate limit type.
* **Please note that if your orders are consistently filled by trades, you can continuously place orders on the API**. For more information, please see [Spot Unfilled Order Count Rules](https://developers.binance.com/docs/binance-spot-api-docs/faqs/order_count_decrement.md).
* Use the [`account.rateLimits.orders`](#query-unfilled-order-count) request to keep track of how many orders you have placed within this interval.
* If you exceed this, requests fail with status `429`.
  * This status code indicates you should back off and stop spamming the API.
  * Responses that have a status `429` include a `retryAfter` field, indicating when you can retry the request.
* This is maintained **per account** and is shared by all API keys of the account.

Successful response indicating that you have placed 12 orders in 10 seconds, and 4043 orders in the past 24 hours:
```json
{
    "id": "e2a85d9f-07a5-4f94-8d5f-789dc3deb097",
    "status": 200,
    "result": {
        "symbol": "BTCUSDT",
        "orderId": 12510053279,
        "orderListId": -1,
        "clientOrderId": "a097fe6304b20a7e4fc436",
        "transactTime": 1655716096505,
        "price": "0.10000000",
        "origQty": "10.00000000",
        "executedQty": "0.00000000",
        "origQuoteOrderQty": "0.000000",
        "cummulativeQuoteQty": "0.00000000",
        "status": "NEW",
        "timeInForce": "GTC",
        "type": "LIMIT",
        "side": "BUY",
        "workingTime": 1655716096505,
        "selfTradePreventionMode": "NONE"
    },
    "rateLimits": [
        {
            "rateLimitType": "ORDERS",
            "interval": "SECOND",
            "intervalNum": 10,
            "limit": 50,
            "count": 12
        },
        {
            "rateLimitType": "ORDERS",
            "interval": "DAY",
            "intervalNum": 1,
            "limit": 160000,
            "count": 4043
        },
        {
            "rateLimitType": "REQUEST_WEIGHT",
            "interval": "MINUTE",
            "intervalNum": 1,
            "limit": 6000,
            "count": 321
        }
    ]
}
```

## Request security

* Each method has a security type indicating required API key permissions, shown next to the method name (e.g., [Place new order (TRADE)](#place-new-order-trade)).
* If unspecified, the security type is `NONE`.
* Except for `NONE`, all methods with a security type are considered `SIGNED` requests (i.e. including a `signature`), except for [listenKey management](#user-data-stream-requests).
* Secure methods require a valid API key to be specified and authenticated.
  * API keys can be created on the [API Management](https://www.binance.com/en/support/faq/360002502072) page of your Binance account.
  * **Both API key and secret key are sensitive.** Never share them with anyone.
    If you notice unusual activity in your account, immediately revoke all the keys and contact Binance support.
* API keys can be configured to allow access only to certain types of secure methods.
  * For example, you can have an API key with `TRADE` permission for trading,
    while using a separate API key with `USER_DATA` permission to monitor your order status.
  * By default, an API key cannot `TRADE`. You need to enable trading in API Management first.

Security type |  Description
------------- | ------------
`NONE`        | Public market data
`TRADE`       | Trading on the exchange, placing and canceling orders
`USER_DATA`   | Private account information, such as order status and your trading history
`USER_STREAM` | Managing User Data Stream subscriptions

### SIGNED request security

* `SIGNED` requests require an additional parameter: `signature`, authorizing the request.

#### Signature Case Sensitivity

* **HMAC:** Signatures generated using HMAC are **not case-sensitive**. This means the signature string can be verified regardless of letter casing.
* **RSA:** Signatures generated using RSA are **case-sensitive**.
* **Ed25519:** Signatures generated using ED25519 are also **case-sensitive**

Please consult [SIGNED request example (HMAC)](#signed-request-example-hmac), [SIGNED request example (RSA)](#signed-request-example-rsa), and [SIGNED request example (Ed25519)](#signed-request-example-ed25519) on how to compute signature, depending on which API key type you are using.

<a id="timingsecurity"></a>

### Timing security

* `SIGNED` requests also require a `timestamp` parameter which should be the current timestamp either in milliseconds or microseconds. (See [General API Information](#general-api-information))
* An additional optional parameter, `recvWindow`, specifies for how long the request stays valid and may only be specified in milliseconds.
  * `recvWindow` supports up to three decimal places of precision (e.g., 6000.346) so that microseconds may be specified.
  * If `recvWindow` is not sent, **it defaults to 5000 milliseconds**.
  * Maximum `recvWindow` is 60000 milliseconds.
* Request processing logic is as follows:

```javascript
serverTime = getCurrentTime()
if (timestamp < (serverTime + 1 second) && (serverTime - timestamp) <= recvWindow) {
  // begin processing request
  serverTime = getCurrentTime()
  if (serverTime - timestamp) <= recvWindow {
    // forward request to Matching Engine
  } else {
    // reject request
  }
  // finish processing request
} else {
  // reject request
}
  ```

**Serious trading is about timing.** Networks can be unstable and unreliable,
which can lead to requests taking varying amounts of time to reach the
servers. With `recvWindow`, you can specify that the request must be
processed within a certain number of milliseconds or be rejected by the
server.

**It is recommended to use a small `recvWindow` of 5000 or less!**

### SIGNED request example (HMAC)

Here is a step-by-step guide on how to sign requests using an HMAC secret key.

Example API key and secret key:

Key          | Value
------------ | ------------
`apiKey`       | `key`
`secretKey`    | `secret`

**WARNING: DO NOT SHARE YOUR API KEY AND SECRET KEY WITH ANYONE.**

The example keys are provided here only for illustrative purposes.

Example of request with a symbol name comprised entirely of ASCII characters:

```json
{
    "id": "4885f793-e5ad-4c3b-8f6c-55d891472b71",
    "method": "order.place",
    "params": {
        "symbol": "BTCUSDT",
        "side": "SELL",
        "type": "LIMIT",
        "timeInForce": "GTC",
        "quantity": "0.01000000",
        "price": "52000.00",
        "recvWindow": 100,
        "timestamp": 1645423376532,
        "apiKey": "key",
        "signature": "------ FILL ME ------"
    }
}
```

Example of a request with a symbol name containing non-ASCII characters:

```json
{
    "id": "4885f793-e5ad-4c3b-8f6c-55d891472b71",
    "method": "order.place",
    "params": {
        "symbol": "１２３４５６",
        "side": "BUY",
        "type": "LIMIT",
        "timeInForce": "GTC",
        "quantity": "0.01000000",
        "price": "0.10000000",
        "recvWindow": 5000,
        "timestamp": 1645423376532,
        "apiKey": "key",
        "signature": "------ FILL ME ------"
    }
}
```

As you can see, the `signature` parameter is currently missing.

**Step 1: Construct the signature payload**

Take all request `params` except `signature` and **sort them in alphabetical order by parameter name**:

For the first set of example parameters (ASCII only):

Parameter        | Value
---------------- | ------------
`apiKey`           | key
`price`            | 52000.00
`quantity`         | 0.01000000
`recvWindow`       | 100
`side`             | SELL
`symbol`           | BTCUSDT
`timeInForce`      | GTC
`timestamp`        | 1645423376532
`type`             | LIMIT

For the second set of example parameters (some non-ASCII characters):

Parameter | Value
------------ | ------------
`apiKey` | key
`price` | 0.10000000
`quantity` | 1.00000000
`recvWindow` | 5000
`side` | BUY
`symbol` | １２３４５６
`timeInForce` | GTC
`timestamp` | 1645423376532
`type` | LIMIT

Format parameters as `parameter=value` pairs separated by `&`. Values need to be encoded in UTF-8.

For the first set of example parameters (ASCII only), the signature payload should look like this:

```console
apiKey=key&price=52000.00&quantity=0.01000000&recvWindow=100&side=SELL&symbol=BTCUSDT&timeInForce=GTC&timestamp=1645423376532&type=LIMIT
```

For the second set of example parameters (some non-ASCII characters), the signature payload should look like this:

```console
apiKey=key&price=0.10000000&quantity=1.00000000&recvWindow=5000&side=BUY&symbol=１２３４５６&timeInForce=GTC&timestamp=1645423376532&type=LIMIT
```

**Step 2: Compute the signature**

1. Use the `secretKey` of your API key as the signing key for the HMAC-SHA-256 algorithm.
2. Sign the UTF-8 bytes of the signature payload constructed in Step 1.
3. Encode the HMAC-SHA-256 output as a hex string.

Note that `apiKey`, `secretKey`, and the payload are **case-sensitive**, while the resulting signature value is case-insensitive.

You can cross-check your signature algorithm implementation with OpenSSL:

For the first set of example parameters (ASCII only):

```console
$ echo -n 'apiKey=key&price=52000.00&quantity=0.01000000&recvWindow=100&side=SELL&symbol=BTCUSDT&timeInForce=GTC&timestamp=1645423376532&type=LIMIT' \
  | openssl dgst -hex -sha256 -hmac 'secret'

aa1b5712c094bc4e57c05a1a5c1fd8d88dcd628338ea863fec7b88e59fe2db24
```

For the second set of example parameters (some non-ASCII characters):

```console
$ echo -n 'apiKey=key&price=0.10000000&quantity=1.00000000&recvWindow=5000&side=BUY&symbol=１２３４５６&timeInForce=GTC&timestamp=1645423376532&type=LIMIT' \
  | openssl dgst -hex -sha256 -hmac 'secret'

b33892ae8e687c939f4468c6268ddd4c40ac1af18ad19a064864c47bae0752cd
```

**Step 3: Add `signature` to request `params`**

Complete the request by adding the `signature` parameter with the signature string.

For the first set of example parameters (ASCII only):

```json
{
    "id": "4885f793-e5ad-4c3b-8f6c-55d891472b71",
    "method": "order.place",
    "params": {
        "symbol": "BTCUSDT",
        "side": "SELL",
        "type": "LIMIT",
        "timeInForce": "GTC",
        "quantity": "0.01000000",
        "price": "52000.00",
        "recvWindow": 100,
        "timestamp": 1645423376532,
        "apiKey": "key",
        "signature": "aa1b5712c094bc4e57c05a1a5c1fd8d88dcd628338ea863fec7b88e59fe2db24"
    }
}
```

For the second set of example parameters (some non-ASCII characters):

```json
{
    "id": "4885f793-e5ad-4c3b-8f6c-55d891472b71",
    "method": "order.place",
    "params": {
        "symbol": "１２３４５６",
        "side": "BUY",
        "type": "LIMIT",
        "timeInForce": "GTC",
        "quantity": "1.00000000",
        "price": "0.10000000",
        "recvWindow": 5000,
        "timestamp": 1645423376532,
        "apiKey": "key",
        "signature": "b33892ae8e687c939f4468c6268ddd4c40ac1af18ad19a064864c47bae0752cd"
    }
}
```

### SIGNED request example (RSA)

Here is a step-by-step guide on how to sign requests using an RSA private key.

Key          | Value
------------ | ------------
`apiKey`       | `key`

These examples assume the private key is stored in the file `test-rsa-prv.pem`.

**WARNING: DO NOT SHARE YOUR API KEY AND PRIVATE KEY WITH ANYONE.**

The example keys are provided here only for illustrative purposes.

Example of request with a symbol name comprised entirely of ASCII characters:

```json
{
    "id": "4885f793-e5ad-4c3b-8f6c-55d891472b71",
    "method": "order.place",
    "params": {
        "symbol": "BTCUSDT",
        "side": "SELL",
        "type": "LIMIT",
        "timeInForce": "GTC",
        "quantity": "0.01000000",
        "price": "52000.00",
        "recvWindow": 100,
        "timestamp": 1645423376532,
        "apiKey": "key",
        "signature": "------ FILL ME ------"
    }
}
```

Example of a request with a symbol name containing non-ASCII characters:

```json
{
    "id": "4885f793-e5ad-4c3b-8f6c-55d891472b71",
    "method": "order.place",
    "params": {
        "symbol": "１２３４５６",
        "side": "BUY",
        "type": "LIMIT",
        "timeInForce": "GTC",
        "quantity": "0.01000000",
        "price": "0.10000000",
        "recvWindow": 5000,
        "timestamp": 1645423376532,
        "apiKey": "key",
        "signature": "------ FILL ME ------"
    }
}
```

**Step 1: Construct the signature payload**

Take all request `params` except `signature` and **sort them in alphabetical order by parameter name**:

For the first set of example parameters (ASCII only):

Parameter        | Value
---------------- | ------------
`apiKey`           | key
`price`            | 52000.00
`quantity`         | 0.01000000
`recvWindow`       | 100
`side`             | SELL
`symbol`           | BTCUSDT
`timeInForce`      | GTC
`timestamp`        | 1645423376532
`type`             | LIMIT

For the second set of example parameters (some non-ASCII characters):

Parameter | Value
------------ | ------------
`apiKey` | key
`price` | 0.10000000
`quantity` | 1.00000000
`recvWindow` | 5000
`side` | BUY
`symbol` | １２３４５６
`timeInForce` | GTC
`timestamp` | 1645423376532
`type` | LIMIT

Format parameters as `parameter=value` pairs separated by `&`. Values need to be encoded in UTF-8.

For the first set of example parameters (ASCII only), the signature payload should look like this:

```console
apiKey=key&price=52000.00&quantity=0.01000000&recvWindow=100&side=SELL&symbol=BTCUSDT&timeInForce=GTC&timestamp=1645423376532&type=LIMIT
```

For the second set of example parameters (some non-ASCII characters), the signature payload should look like this:

```console
apiKey=key&price=0.10000000&quantity=1.00000000&recvWindow=5000&side=BUY&symbol=１２３４５６&timeInForce=GTC&timestamp=1645423376532&type=LIMIT
```

**Step 2: Compute the signature**

1. Sign the UTF-8 bytes of the signature payload constructed in Step 1 using the RSASSA-PKCS1-v1_5 algorithm with SHA-256 hash function.
2. Encode the output in base64.

Note that `apiKey`, the payload, and the resulting `signature` are **case-sensitive**.

You can cross-check your signature algorithm implementation with OpenSSL:

For the first set of example parameters (ASCII only):

```console
$ echo -n 'apiKey=key&price=52000.00&quantity=0.01000000&recvWindow=100&side=SELL&symbol=BTCUSDT&timeInForce=GTC&timestamp=1645423376532&type=LIMIT' \
  | openssl dgst -sha256 -sign test-rsa-prv.pem \
  | openssl enc -base64 -A

OJJaf8C/3VGrU4ATTR4GiUDqL2FboSE1Qw7UnnoYNfXTXHubIl1iaePGuGyfct4NPu5oVEZCH4Q6ZStfB1w4ssgu0uiB/Bg+fBrRFfVgVaLKBdYHMvT+ljUJzqVaeoThG9oXlduiw8PbS9U8DYAbDvWN3jqZLo4Z2YJbyovyDAvDTr/oC0+vssLqP7NmlNb3fF3Bj7StmOwJvQJTbRAtzxK5PP7OQe+0mbW+D7RqVkUiSswR8qJFWTeSe4nXXNIdZdueYhF/Xf25L+KitJS5IHdIHcKfEw3MQzHFb2ZsGWkjDQwxkwr7Noi0Zaa+gFtxCuatGFm9dFIyx217pmSHtA==
```

For the second set of example parameters (some non-ASCII characters):

```console
$ echo -n 'apiKey=key&price=0.10000000&quantity=1.00000000&recvWindow=5000&side=BUY&symbol=１２３４５６&timeInForce=GTC&timestamp=1645423376532&type=LIMIT' \
  | openssl dgst -sha256 -sign test-rsa-prv.pem \
  | openssl enc -base64 -A

F3o/79Ttvl2cVYGPfBOF3oEOcm5QcYmTYWpdVIrKve5u+8paMNDAdUE+teqMxFM9HcquetGcfuFpLYtsQames5bDx/tskGM76TWW8HaM+6tuSYBSFLrKqChfA9hQGLYGjAiflf1YBnDhY+7vNbJFusUborNOloOj+ufzP5q42PvI3H0uNy3W5V3pyfXpDGCBtfCYYr9NAqA4d+AQfyllL/zkO9h9JSdozN49t0/hWGoD2dWgSO0Je6MytKEvD4DQXGeqNlBTB6tUXcWnRW+FcaKZ4KYqnxCtb1u8rFXUYgFykr2CbcJLSmw6ydEJ3EZ/NaZopRr+cU0W2m0HZ3qucw==
```

**Step 3: Add `signature` to request `params`**

Complete the request by adding the `signature` parameter with the signature string.

For the first set of example parameters (ASCII only):

```json
{
    "id": "4885f793-e5ad-4c3b-8f6c-55d891472b71",
    "method": "order.place",
    "params": {
        "symbol": "BTCUSDT",
        "side": "SELL",
        "type": "LIMIT",
        "timeInForce": "GTC",
        "quantity": "0.01000000",
        "price": "52000.00",
        "newOrderRespType": "ACK",
        "recvWindow": 100,
        "timestamp": 1645423376532,
        "apiKey": "key",
        "signature": "OJJaf8C/3VGrU4ATTR4GiUDqL2FboSE1Qw7UnnoYNfXTXHubIl1iaePGuGyfct4NPu5oVEZCH4Q6ZStfB1w4ssgu0uiB/Bg+fBrRFfVgVaLKBdYHMvT+ljUJzqVaeoThG9oXlduiw8PbS9U8DYAbDvWN3jqZLo4Z2YJbyovyDAvDTr/oC0+vssLqP7NmlNb3fF3Bj7StmOwJvQJTbRAtzxK5PP7OQe+0mbW+D7RqVkUiSswR8qJFWTeSe4nXXNIdZdueYhF/Xf25L+KitJS5IHdIHcKfEw3MQzHFb2ZsGWkjDQwxkwr7Noi0Zaa+gFtxCuatGFm9dFIyx217pmSHtA=="
    }
}
```

For the second set of example parameters (some non-ASCII characters):

```json
{
    "id": "4885f793-e5ad-4c3b-8f6c-55d891472b71",
    "method": "order.place",
    "params": {
        "symbol": "１２３４５６",
        "side": "SELL",
        "type": "LIMIT",
        "timeInForce": "GTC",
        "quantity": "1.00000000",
        "price": "0.10000000",
        "recvWindow": 5000,
        "timestamp": 1645423376532,
        "apiKey": "key",
        "signature": "F3o/79Ttvl2cVYGPfBOF3oEOcm5QcYmTYWpdVIrKve5u+8paMNDAdUE+teqMxFM9HcquetGcfuFpLYtsQames5bDx/tskGM76TWW8HaM+6tuSYBSFLrKqChfA9hQGLYGjAiflf1YBnDhY+7vNbJFusUborNOloOj+ufzP5q42PvI3H0uNy3W5V3pyfXpDGCBtfCYYr9NAqA4d+AQfyllL/zkO9h9JSdozN49t0/hWGoD2dWgSO0Je6MytKEvD4DQXGeqNlBTB6tUXcWnRW+FcaKZ4KYqnxCtb1u8rFXUYgFykr2CbcJLSmw6ydEJ3EZ/NaZopRr+cU0W2m0HZ3qucw=="
    }
}
```

### SIGNED Request Example (Ed25519)

**Note: It is highly recommended to use Ed25519 API keys as they will provide the best performance and security out of all supported key types.**

Here is a step-by-step guide on how to sign requests using an Ed25519 private key.

Key          | Value
------------ | ------------
`apiKey`       | `key`

These examples assume the private key is stored in the file `test-ed25519-prv.pem`.

**WARNING: DO NOT SHARE YOUR API KEY AND PRIVATE KEY WITH ANYONE.**

The example keys are provided here only for illustrative purposes.

Example of request with a symbol name comprised entirely of ASCII characters:

```json
{
    "id": "4885f793-e5ad-4c3b-8f6c-55d891472b71",
    "method": "order.place",
    "params": {
        "symbol": "BTCUSDT",
        "side": "SELL",
        "type": "LIMIT",
        "timeInForce": "GTC",
        "quantity": "0.01000000",
        "price": "52000.00",
        "recvWindow": 100,
        "timestamp": 1645423376532,
        "apiKey": "key",
        "signature": "------ FILL ME ------"
    }
}
```

Example of a request with a symbol name containing non-ASCII characters:

```json
{
    "id": "4885f793-e5ad-4c3b-8f6c-55d891472b71",
    "method": "order.place",
    "params": {
        "symbol": "１２３４５６",
        "side": "BUY",
        "type": "LIMIT",
        "timeInForce": "GTC",
        "quantity": "0.01000000",
        "price": "0.10000000",
        "recvWindow": 5000,
        "timestamp": 1645423376532,
        "apiKey": "key",
        "signature": "------ FILL ME ------"
    }
}
```

**Step 1: Construct the signature payload**

Take all request `params` except `signature` and **sort them in alphabetical order by parameter name**:

For the first set of example parameters (ASCII only):

Parameter        | Value
---------------- | ------------
`apiKey`           | key
`price`            | 52000.00
`quantity`         | 0.01000000
`recvWindow`       | 100
`side`             | SELL
`symbol`           | BTCUSDT
`timeInForce`      | GTC
`timestamp`        | 1645423376532
`type`             | LIMIT

For the second set of example parameters (some non-ASCII characters):

Parameter     | Value
------------  | ------------
`apiKey`      | key
`price`       | 0.20000000
`quantity`    | 1.00000000
`recvWindow`  | 5000
`side`        | SELL
`symbol`      | １２３４５６
`timeInForce` | GTC
`timestamp`   | 1668481559918
`type`        | LIMIT

Format parameters as `parameter=value` pairs separated by `&`. Values need to be encoded in UTF-8.

For the first set of example parameters (ASCII only), the signature payload should look like this:

```console
apiKey=key&price=52000.00&quantity=0.01000000&recvWindow=100&side=SELL&symbol=BTCUSDT&timeInForce=GTC&timestamp=1645423376532&type=LIMIT
```

For the second set of example parameters (some non-ASCII characters), the signature payload should look like this:

```console
apiKey=key&price=0.10000000&quantity=1.00000000&recvWindow=5000&side=BUY&symbol=１２３４５６&timeInForce=GTC&timestamp=1645423376532&type=LIMIT
```

**Step 2: Compute the signature**

1. Sign the UTF-8 bytes of your signature payload constructed in Step 1 using the Ed25519 private key.
2. Encode the output in base64.

Note that `apiKey`, the payload, and the resulting `signature` are **case-sensitive**.

You can cross-check your signature algorithm implementation with OpenSSL:

For the first set of example parameters (ASCII only):

```console
echo -n "apiKey=key&price=52000.00&quantity=0.01000000&recvWindow=100&side=SELL&symbol=BTCUSDT&timeInForce=GTC&timestamp=1645423376532&type=LIMIT" \
  | openssl dgst -sign ./test-ed25519-prv.pem \
  | openssl enc -base64 -A

EocljwPl29jDxWYaaRaOo4pJ9wEblFbklJvPugNscLLuKd5vHM2grWjn1z+rY0aJ7r/44enxHL6mOAJuJ1kqCg==
```

For the second set of example parameters (some non-ASCII characters):

```console
echo -n "apiKey=key&price=0.10000000&quantity=1.00000000&recvWindow=5000&side=BUY&symbol=１２３４５６&timeInForce=GTC&timestamp=1645423376532&type=LIMIT" \
  | openssl dgst -sign ./test-ed25519-prv.pem \
  | openssl enc -base64 -A

dtNHJeyKry+cNjiGv+sv5kynO9S40tf8k7D5CfAEQAp0s2scunZj+ovJdz2OgW8XhkB9G3/HmASkA9uY9eyFCA==
```

**Step 3: Add the signature to request `params`**

For the first set of example parameters (ASCII only):

```json
{
    "id": "4885f793-e5ad-4c3b-8f6c-55d891472b71",
    "method": "order.place",
    "params": {
        "symbol": "BTCUSDT",
        "side": "SELL",
        "type": "LIMIT",
        "timeInForce": "GTC",
        "quantity": "0.01000000",
        "price": "52000.00",
        "newOrderRespType": "ACK",
        "recvWindow": 100,
        "timestamp": 1645423376532,
        "apiKey": "key",
        "signature": "EocljwPl29jDxWYaaRaOo4pJ9wEblFbklJvPugNscLLuKd5vHM2grWjn1z+rY0aJ7r/44enxHL6mOAJuJ1kqCg=="
    }
}
```

For the second set of example parameters (some non-ASCII characters):

```json
{
    "id": "4885f793-e5ad-4c3b-8f6c-55d891472b71",
    "method": "order.place",
    "params": {
        "symbol": "１２３４５６",
        "side": "SELL",
        "type": "LIMIT",
        "timeInForce": "GTC",
        "quantity": "1.00000000",
        "price": "0.10000000",
        "recvWindow": 5000,
        "timestamp": 1645423376532,
        "apiKey": "key",
        "signature": "dtNHJeyKry+cNjiGv+sv5kynO9S40tf8k7D5CfAEQAp0s2scunZj+ovJdz2OgW8XhkB9G3/HmASkA9uY9eyFCA=="
    }
}
```

Here is a sample Python script performing all the steps above:

```python
#!/usr/bin/env python3

import base64
import time
import json
import os
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from websocket import create_connection

# Set up authentication
API_KEY = os.environ['BINANCE_API_KEY']
PRIVATE_KEY_PATH = os.environ['BINANCE_PRIVATE_KEY_PATH']

# Load the private key.
# In this example the key is expected to be stored without encryption,
# but we recommend using a strong password for improved security.
with open(PRIVATE_KEY_PATH, 'rb') as f:
  private_key = load_pem_private_key(data=f.read(), password=os.environ.get('BINANCE_PRIVATE_KEY_PASSWORD'))

# Set up the request parameters
params = {
    'apiKey':       API_KEY,
    'symbol':       '１２３４５６',
    'side':         'SELL',
    'type':         'LIMIT',
    'timeInForce':  'GTC',
    'quantity':     '1.0000000',
    'price':        '0.10000000',
    'recvWindow':   5000
}

# Timestamp the request
timestamp = int(time.time() * 1000) # UNIX timestamp in milliseconds
params['timestamp'] = timestamp

# Sort parameters alphabetically by name
params = dict(sorted(params.items()))

# Compute the signature payload
payload = '&'.join([f"{k}={v}" for k,v in params.items()]) # no percent encoding here!

# Sign the request
signature = base64.b64encode(private_key.sign(payload.encode('UTF-8')))
params['signature'] = signature.decode('ASCII')

# Send the request
request = {
    'id': 'my_new_order',
    'method': 'order.place',
    'params': params
}

ws = create_connection("wss://ws-api.binance.com:443/ws-api/v3")
ws.send(json.dumps(request))
result =  ws.recv()
ws.close()

print(result)
```
