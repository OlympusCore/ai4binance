# AI4BINANCE Dynamic Portfolio and Opportunity Plan

## ELI10

Bu rapor, portfoy ve firsat fikirlerinin nasil ayrilacagini anlatan operasyon
planidir. Bir coinde firsat gorunmesi, otomatik olarak para ayirma veya islem
yapma izni anlamina gelmez.


## Evaluation

The attached plan is directionally correct in separating opportunity, capital,
funding, and execution. The updated product decision is that HOT is not a
protected or priority asset by default. HOT and every other Binance holding can
be reviewed for opportunities, funding alternatives, and rebalance actions.
The most important safety split is:

- opportunity quality is not capital eligibility
- Spot capital is not Futures margin
- total wallet value is not available trading capital
- funding advice is not execution authority
- reviewable asset is not automatically sellable asset

The current repository already contains a proposal-only
`InvestmentManagementAssistant`, normalized Spot/Futures open orders, and a
read-only resident runtime. This makes the safest first implementation step a
policy and proposal layer above the existing wallet/account snapshots.

The strategic portfolio target is:

- Spot capital: 90%
- USD-M Futures capital: 10%
- Spot internal reserve: at least 10% liquid quote
- Futures internal reserve: at least 70% liquid available margin

Futures 10% is a capital allocation target, not leveraged notional permission.
Futures position notional must remain separately risk-capped.

## Implementation Plan

1. Audit HOTUSDT usages.
   Keep HOTUSDT where it is a fixture, default watch symbol, sealed HOTUSDT
   research dataset, or explicit single-symbol analysis. Remove it from scanner
   universe defaults as dynamic universe modules are introduced.

2. Add dynamic asset policy.
   Store `protected_assets`, `fee_reserve_assets`, `preferred_quote_assets`, and
   automatic asset-action flags in configuration. Defaults should keep
   `protected_assets=[]` and all automatic conversion, transfer, and position
   close actions disabled.

3. Classify Spot assets before funding.
   Classify balances as cash equivalent, protected position, fee reserve, locked,
   dust, convertible, or unsupported. Only free preferred quote balance can be
   treated as immediately available Spot notional.

4. Separate opportunity from allocation.
   Add allocation proposals that can say an opportunity exists but capital,
   minimum-notional, protected-asset, or risk limits block trading.

5. Add proposal-only funding plans.
   Funding plans may propose stablecoin use, locked-order review, manual
   conversion, or wallet transfer. HOT can be proposed as a manual review
   candidate when it is actually held and priced. Explicitly configured
   protected assets must still be rejected with
   `PROTECTED_ASSET_REQUIRES_EXPLICIT_OVERRIDE`.

6. Build dynamic Spot universe.
   Introduce `src/ai4binance/universe/spot_universe.py` with active symbol,
   quote, filter, volume, spread, depth, data-quality, news/delist, and denylist
   filters.

7. Build dynamic Futures universe.
   Keep Futures filters separate from Spot: active perpetual contracts, margin
   asset, notional, spread, open interest, funding anomalies, and risk limits.

8. Add two-stage scanning.
   Run cheap prefilters across the universe, then deep technical and external
   analysis only for a bounded candidate set.

9. Add portfolio-aware validation.
   Compute portfolio fit, capital fit, concentration, correlation, and combined
   Spot/Futures exposure separately from technical score.

10. Integrate CLI and runtime reporting.
    `/scan spot` should scan dynamic Spot candidates; `/analyze HOTUSDT` should
    remain a single-symbol analysis path. Reports should expose decision,
    capital status, funding source, blockers, and `LIVE_ORDER_BLOCKED`.

11. Add Spot/Futures rebalancing agent.
    The agent should compare current capital to 90% Spot / 10% Futures, then
    report Spot position/liquid ratio and Futures position/liquid margin ratio.
    It must recommend only manual-review actions such as transfer review,
    liquidity reserve review, or Futures risk reduction review.

12. Add holdings opportunity review.
    Compare every existing Binance holding against new Spot and Futures
    opportunities with no emotional attachment to any coin. If liquid capital is
    insufficient and a stronger opportunity has materially better quality and
    risk/reward, propose a capped partial conversion from the weakest
    liquidatable holding. Use free liquid capital before proposing any coin sale.
    Block additional Futures risk when the 10% Futures capital target is full.

## Scanner, Futures, WebSocket, Execution Change Proposals

- Scanner: split `/scan spot` from `/analyze SYMBOL`. `/scan spot` should build
  a dynamic Binance Spot universe, prioritize current wallet holdings plus high
  liquidity candidates, then run two-stage filtering before deep analysis.
- Futures: build a separate USD-M universe with perpetual status, margin asset,
  notional, funding, open interest, spread, liquidation-risk, and max leverage
  filters. Futures signals must never dominate Spot inventory decisions.
- WebSocket: keep REST snapshot as the checkpoint and use account/order streams
  only as reconciliation deltas. Missing sequence, stale stream, or duplicate
  event must produce degraded state and block execution.
- Execution: keep `manual` as the default order mode. Add execution intents only
  after allocation, funding, risk, exchange filters, and validation pass. Real
  order, transfer, close, or conversion requires explicit user approval and live
  gates; otherwise return `LIVE_ORDER_BLOCKED`.

## Diff Slice Implemented Here

- Added asset policy and Spot balance classification.
- Added allocation proposals that separate opportunity from capital fit.
- Added proposal-only funding plans where HOT is reviewable by default and
  explicitly protected assets are still rejected.
- Added Spot/Futures `RebalancingAgent` with 90/10 capital target and
  position/liquid ratio advice.
- Added `HoldingsOpportunityReviewEngine` that compares current holdings
  against better Spot/Futures candidates, proposes capped partial rotation, and
  blocks new Futures risk when the 10% capital target is full.
- Integrated holding-opportunity rotation advice into
  `InvestmentManagementAssistant` as proposal-only management output.
- Added configuration defaults for watchlist, protected assets, quote assets,
  and disabled automatic asset actions.
- Added deterministic tests for reviewable HOT, free USDT, insufficient capital,
  protected funding override, 90/10 rebalancing, holding-vs-opportunity
  rotation, liquidity recommendations, and fail-closed live eligibility.

## Safety Status

This slice is `RESEARCH_ONLY` / proposal-only. It adds no Binance order calls,
does not cancel open orders, does not transfer wallets, does not sell assets,
and keeps all live eligibility at `LIVE_ORDER_BLOCKED`.

