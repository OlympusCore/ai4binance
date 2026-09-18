---
document_id: AI4B-GOV-REG-STR-001
title: AI4BINANCE Strategy Registry
document_type: REGISTRY
version: 1.0.0
status: ACTIVE
owner: Strategy Governance
authority_level: NORMATIVE
authority_layer: L5_REGISTRIES_ROADMAP
authority_scope: strategy_registry
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
machine_enforceable: true
audit_required: true
classification: INTERNAL
canonical_path: docs/registries/registry_strategy_registry.md
schema_refs:
  - schemas/governance/repository_artifact.schema.json
validated_by:
  - src/ai4binance/governance/repository_validator.py
  - tests/test_repository_validator.py
---

# AI4BINANCE Strategy Registry

## ELI10

This registry lists strategy definitions and keeps research, paper, and live eligibility separated.

## Registry Contract

No strategy entry may imply live approval without explicit OOS, walk-forward, paper evidence, risk approval, and human-governed promotion.

| strategy_id | name | owner | lifecycle_status | market_scope | promotion_status | evidence_ref |
| --- | --- | --- | --- | --- | --- | --- |
| TREND_PULLBACK | Trend pullback family | Strategy Governance | RESEARCH_ONLY | SPOT, USD_M_FUTURES | RESEARCH_ONLY | `runtime/artifacts/research/backtest/validation/HOTUSDT/1h/support_reclaim.run-card.json` and `runtime/artifacts/research/backtest/validation` |
| BREAKOUT_RETEST | Breakout retest family | Strategy Governance | RESEARCH_ONLY | SPOT, USD_M_FUTURES | RESEARCH_ONLY | `runtime/artifacts/research/backtest/validation/HOTUSDT/1h/breakout_retest.run-card.json` and `runtime/artifacts/research/backtest/validation` |
| MOMENTUM_CONTINUATION | Momentum continuation family | Strategy Governance | RESEARCH_ONLY | SPOT, USD_M_FUTURES | RESEARCH_ONLY | `runtime/artifacts/research/backtest/validation/HOTUSDT/1h/trend_continuation.run-card.json` and `runtime/artifacts/research/backtest/validation` |
| MEAN_REVERSION | Mean reversion family | Strategy Governance | RESEARCH_ONLY | SPOT, USD_M_FUTURES | RESEARCH_ONLY | `runtime/artifacts/research/backtest/validation/HOTUSDT/1h/failed_breakout_reversal.run-card.json` and `runtime/artifacts/research/backtest/validation` |

The registry is intentionally bound to repo-local validation evidence roots. A family remains `RESEARCH_ONLY` until its validation summary can demonstrate paper-approved evidence for the family playbooks; the presence of a real run card or validation root is not sufficient by itself.

## Strategy Classification Reference

This registry uses the following reference classification for strategy ideas, execution methods, and research methods.
The table is descriptive only. It does not grant execution authority, live eligibility, or promotion status.

| Strategy | Category | AI4Binance Utility | Recommended Use | Notes |
| --- | --- | --- | --- | --- |
| Pairs Trading | Alpha strategy | High | Research candidate with strict hedge-ratio, stationarity, and cost validation | Useful when the spread is demonstrably mean-reverting and liquid enough after fees and slippage. |
| Scalping | Alpha strategy | Low | Research-only | Usually too sensitive to latency, fees, slippage, and exchange microstructure for a conservative default profile. |
| Smart Order Routing | Execution algorithm | High | Execution infrastructure | Improves fill quality and venue selection; it is not an alpha source by itself. |
| Market-Making Trading | Execution strategy | Medium | Restricted research-only | Can be useful only with strong inventory, adverse-selection, and quote-management controls. |
| Momentum Strategy | Alpha strategy | High | Core candidate family | One of the most practical families for trend-following and continuation behavior. |
| Time-Weighted Average Price (TWAP) | Execution algorithm | High | Execution infrastructure | Reduces market impact by spreading execution through time. |
| Volume-Weighted Average Price (VWAP) | Execution algorithm | High | Execution infrastructure | Useful for execution benchmarking and liquidity-aware order slicing. |
| Seasonality Trading | Context signal | Medium | Secondary feature or regime filter | Better treated as a supporting hypothesis than a standalone trigger in crypto markets. |
| Volatility Trading | Alpha strategy | High | Core candidate family | Strong when paired with regime detection, breakout logic, or volatility compression/expansion analysis. |
| Golden Cross / Death Cross | Trend confirmation signal | Medium | Research-only confirmation layer | Useful as a moving-average crossover regime cue when the faster average crosses above or below the slower average and the signal is validated by volume, structure, and broader market context. |
| Machine Learning-Based Strategy | Meta/model strategy | High | Research and scoring layer | Best used for ranking, feature synthesis, or regime scoring rather than as an opaque sole decision authority. |
| Pattern Recognition Strategy | Alpha strategy | Medium | Supporting signal family | Useful when chart patterns are defined precisely and validated against OOS data. |
| Price Action + MACD Confirmation | Trigger / confirmation setup | Medium | Research-only confirmation layer | Useful for breakout and trend continuation confirmation when price action and MACD crossover align with volume and regime context. MACD atoms remain incomplete, so this must not be treated as a live-ready standalone gate. |
| Sentiment Analysis Trading | Context signal | High | Supporting signal family | Valuable as a risk or confirmation layer; it should not be the only gate for a trade. |
| Deep Reinforcement Learning Strategy | Meta/research strategy | Low | Research-only | High overfitting and non-stationarity risk make it unsuitable as a direct live decision source. |
| Adaptive Strategies | Meta strategy | High | Meta-controller or allocator | Useful for regime-aware parameter selection, strategy weighting, or family selection. |
| Genetic Algorithms | Research method | Medium | Parameter search and hypothesis generation | Better used for optimization and candidate discovery than as a direct live strategy. |

## Moving Average Structure Reference

These moving-average structures are useful as trend, pullback, and regime-shift cues.
They remain confirmation signals and do not grant execution authority by themselves.

| Structure | Typical Interpretation | AI4Binance Use | Notes |
| --- | --- | --- | --- |
| 5-8-13 Bullish Trend Shift | Fast trend acceleration and alignment | Research-only confirmation layer | Useful when short-term averages stack upward and price holds above them. |
| 5-8-13 Bearish Trend Shift | Fast trend deterioration and alignment | Research-only confirmation layer | Useful when short-term averages stack downward and price fails below them. |
| 25 Short-Term Crossover | Short-to-intermediate momentum turn | Research-only confirmation layer | Useful for detecting early trend continuation or weakening after a local pullback. |
| 50 Mid-Term Crossover | Mid-term regime transition | Research-only confirmation layer | Useful for intermediate trend confirmation and as a contextual filter. |
| 100 Long-Term Pullback | Longer-term retracement against trend | Research-only support or caution zone | Useful for spotting deeper pullbacks within a still-structured move. |
| 50-200 Golden Cross | Structural bullish regime shift | Research-only trend confirmation layer | Useful when 50-day average rises above 200-day average with broader confirmation. |
| 50-200 Death Cross | Structural bearish regime shift | Research-only trend confirmation layer | Useful when 50-day average falls below 200-day average with broader confirmation. |

## Reversal Pattern Reference

These after-downtrend reversal patterns are useful as confirmation cues when they are validated by structure, volume, market context, and risk controls.
They remain research-only and do not grant execution authority by themselves.

| Pattern | Typical Interpretation | AI4Binance Use | Notes |
| --- | --- | --- | --- |
| Descending Wedge Pattern | Bearish compression that may reverse upward | Research-only reversal confirmation layer | Useful when contraction resolves with breakout and follow-through. |
| Rounding Bottom Pattern | Gradual downtrend exhaustion and recovery | Research-only reversal confirmation layer | Useful when a rounded base is confirmed by improving momentum and structure. |
| Cup and Handle Pattern | Base formation followed by continuation break | Research-only reversal or continuation confirmation layer | Useful when the handle resolves above resistance with supporting volume. |
| W Pattern | Double-bottom style reversal structure | Research-only reversal confirmation layer | Useful when the second low holds and neckline resistance breaks decisively. |
| Rectangle Pattern | Range compression before directional break | Research-only breakout or reversal confirmation layer | Useful when the upper boundary breaks after repeated rejections. |
| Inverted Head and Shoulders Pattern | Bullish reversal after downtrend | Research-only reversal confirmation layer | Useful when the neckline break is supported by volume and higher-low structure. |

## Fibonacci Retracement Reference

The following Fibonacci retracement levels are used as heuristic confluence zones, not as probability guarantees.
They can support entries, exits, and reversal warnings when they are validated by price structure, volume, regime context, and risk controls.

| Level | Typical Interpretation | AI4Binance Use | Notes |
| --- | --- | --- | --- |
| 38.2% | Shallow retracement / weak pullback | Research-only support or early warning level | Useful as a mild pullback zone, but not a standalone trigger. |
| 50.0% | Midpoint retracement / balanced pullback | Research-only support or neutral zone | Often useful as a midpoint reference, but it has no inherent edge by itself. |
| 61.8% | Strong retracement / higher-probability reaction zone | Research-only confirmation or exit-protection level | Useful when structure, momentum, and volume confirm the reaction. |
| 78.6% to 88.6% | Deep retracement / high-risk continuation or reversal zone | Research-only reversal or invalidation watch zone | Useful for identifying exhaustion, failed continuation, or late-entry risk. |
| 100.0% | Full retracement / prior swing invalidation | Invalidates the prior impulse unless evidence proves otherwise | Should be treated as a structural reset unless the setup explicitly tolerates full retracement. |

## Fibonacci Interpretation

- Fibonacci levels are not probability guarantees.
- A labeled zone on its own does not justify live entry or exit.
- Fibonacci confluence becomes more useful when it aligns with trend structure, MACD confirmation, price action rejection, or validated support and resistance.
- Deep retracements such as 78.6% to 88.6% are especially useful as caution zones for long positions.

## AI4Binance Interpretation

The most useful ideas from the attached reference are:

- Momentum, volatility, and pairs trading as alpha candidates.
- Golden cross and death cross as research-only trend confirmation cues.
- Moving-average structures such as 5-8-13, 25, 50, 100, and 50-200 as research-only trend or pullback cues.
- Reversal patterns such as descending wedge, rounding bottom, cup and handle, W, rectangle, and inverted head and shoulders as research-only confirmation cues.
- Price action + MACD as a research-only confirmation layer for breakout and trend continuation setups.
- TWAP, VWAP, and smart order routing as execution-quality improvements.
- Sentiment, pattern recognition, seasonality, and adaptive strategies as supporting or meta layers.
- Machine learning and genetic algorithms as research and optimization tools.

The least suitable ideas for a conservative default architecture are:

- Scalping, because of latency and cost sensitivity.
- Market making, because of inventory and adverse-selection risk.
- Deep reinforcement learning, because of overfitting and regime instability risk.
- Golden cross or death cross as standalone live gates, because moving-average crossovers require validation from volume, structure, and regime context.
- Moving-average structures as standalone live gates, because trend alignment still requires validation from structure, volatility, and volume.
- Reversal patterns as standalone live gates, because pattern shape alone is not sufficient without confirmation and context.
- Price action + MACD as a standalone live gate, because MACD capability coverage is still incomplete.
- Fibonacci retracement levels as probability guarantees, because they are heuristic confluence zones rather than certainty signals.

## Exit Strategy Reference

These long-position exit methods are useful as governed confirmation or exit-rule candidates.
They are descriptive only and do not grant live execution authority.

| Exit Method | Category | AI4Binance Utility | Recommended Use | Notes |
| --- | --- | --- | --- | --- |
| EMA Crossover Exit | Exit rule | High | Research and paper trading | Useful when the shorter EMA crossing below the longer EMA is a validated trend-weakness signal. |
| Price Action Exit | Exit rule | High | Research and paper trading | Useful when price rejects major resistance and loses the trend structure that justified entry. |
| Close Below Trendline Exit | Exit rule | High | Research and paper trading | Useful for long positions that depend on an intact trendline and higher-low structure. |
| Fibonacci Retracement Exit | Exit rule | Medium | Research and paper trading | Useful when a validated retracement threshold, such as 61.8%, is used as a reversal or profit-protection trigger. |

Any candidate in this registry remains subject to the normal AI4Binance gates:

- research-only until validated,
- no live eligibility without OOS and walk-forward evidence,
- no execution authority without risk approval,
- no promotion without human-governed approval.

Strategy family expansion is therefore governed by the same staged evidence
chain: research, backtest, walk-forward, out-of-sample, robustness, paper, and
human promotion. Registry entries may describe visibility and readiness, but
they do not grant trade authority by themselves.
