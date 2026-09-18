---
document_id: AI4B-GOV-OEK-103
title: AI4BINANCE Organization Market Strategy and Validation Policy
document_type: POLICY
version: 1.0.0
status: ACTIVE
owner: Enterprise Governance
authority_level: NORMATIVE
authority_layer: L2_GOVERNANCE_COMPLIANCE
authority_scope: organization_market_strategy_validation
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
canonical_path: docs/governance/policy_organization_market_strategy_validation.md
machine_enforceable: false
audit_required: true
classification: INTERNAL
---
# AI4BINANCE Organization Market Strategy and Validation Policy

## ELI10

This policy section defines market intelligence, strategy manufacturing, validation, and portfolio principles.

## Source Lineage

- Source file: `docs/governance/policy_organization_constitution_handbook.md`
- Source section start: `# 13. CONTINUOUS MARKET, NEWS, SOCIAL MEDIA AND CONTENT INTELLIGENCE`
- This file preserves a bounded section of the governed source document.

# 13. CONTINUOUS MARKET, NEWS, SOCIAL MEDIA AND CONTENT INTELLIGENCE



## 13.1 Monitoring Universe

- Binance official market/announcement/data channels, BIST/KAP and licensed broker sources.

- Central banks, macroeconomic data, regulation and financial authority announcements.

- Trusted news agencies, industry reports, research publications, and technology resources.

- On-chain, exchange inflow/outflow, stablecoin flow, whale/smart-money, and derivative data.

- Social media; trust in source, verification, and manipulation risk layers.

## 13.2 Source Trustworthiness and Manipulation Control

| **Boyut**        | **Kontrol**                                                                                     |
|------------------|-------------------------------------------------------------------------------------------------|
| Source Identity   | Official/organizational/expert/anonymity class; past accuracy and conflict of interest.                         |
| Verification        | Number of independent sources, timestamp, original content, verified by chain-level or official data.       |
| Manipulation     | Pump/dump language, coordinated sharing, bot behavior, fake screenshots, cherry-picking.      |
| Prompt Injection | Text that instructs the agent, requests secrets, or bypasses policy is quarantined. |
| Freshness/Expiry | Expiration time of news and opportunities; old content cannot be used as a new catalyst.              |
| Decision Weight  | A single source is not a hard gate; limited weight is given to verified confluence layers.          |

## 13.3 Opportunity Queue

| **Field**              | **Description**                                                  |
|-----------------------|---------------------------------------------------------------|
| opportunity_id        | Unique identifier and creation timestamp.                                |
| market/asset/pair     | Market, asset, trading pair and venue.                      |
| thesis/invalidation   | Thesis, counter thesis and invalidation condition.                         |
| evidence/source score | Technical/fundamental/macro/news/flow evidence and source reliability.        |
| risk/capital fit      | Portfolio, correlation, liquidity, cost and risk budget alignment. |
| expiry                | Opportunity's last usable time; expire means re-verification.    |
| status                | WATCH / RESEARCH / WAIT / PAPER / MANUAL_REVIEW / NO_TRADE.   |

<a id="bolum-14"></a>
# 14. CORRELATION, PAIR AND CROSS-MARKET INTELLIGENCE



BTCUSDT; is one of the main reference factors for crypto market risk appetite and liquidity regime; however, it is not accepted as the sole cause of all altcoin movements. Each altcoin is evaluated together with its BTC beta, idiosyncratic risk, sector/theme, liquidity, and news impact.

## 14.1 Mandatory Analyses

| **Analysis**                     | **Purpose**                                                               | **Control**                                                 |
|--------------------------------|------------------------------------------------------------------------|-------------------------------------------------------------|
| Rolling Pearson/Spearman         | Measuring linear and ordinal relationships across different windows.     | Regime and outlier sensitivity are reported.                |
| Beta and Relative Strength       | Sensitivity of altcoin to BTC/ETH/market movements and relative performance. | Stable beta assumption is not made.                         |
| Partial Correlation              | Relationship with BTC, ETH, USD/TRY or macro factors controlled.          | Causality is not presented.                                 |
| Lead–Lag / Cross-Correlation     | Testing potential leading/lagging movements.                             | Look-ahead and multiple testing control.                   |
| Cointegration / Spread           | Long-term equilibrium and relative-value hypothesis.                     | Structural break and transaction costs.                    |
| Regime-Conditioned Correlation   | Relationship within trend, risk-off, volatility, and liquidity regimes.  | No decision is made based on a single global correlation.  |
| PCA / Clustering / Network       | Common factors, sector, and correlation clusters.                        | Concentration and hidden exposure visibility.               |
| Pair/Venue Analysis              | USDT/USDC/TRY/BTC parity, spread, depth, fee, and transfer friction.       | Price difference arbitrage is not considered; executability is verified. |

## 14.2 Decision Usage

- Correlation affects position direction, concentration, hedging, stop distance, and capital distribution.

- In a crisis regime where correlation increases, total open risk can be automatically reduced.

- Multiple altcoins exposed to the same factor are not considered independent opportunities; the correlation cluster limit is applied.

- Causal or Granger tests are not trade signals without economic justification.

<a id="bolum-15"></a>
# 15. ALGORITHM, INDICATOR, MODEL AND STRATEGY MANUFACTORY



## 15.1 Production Line

```text
PROBLEM
→ HYPOTHESIS
→ DATA / FEATURE DESIGN
→ BASELINE
→ PROTOTYPE
→ BACKTEST / OOS
→ ROBUSTNESS / STRESS
→ SECURITY / PRIVACY
→ QA/QC
→ PAPER / SHADOW
→ LIMITED PILOT
→ COMMITTEE APPROVAL
→ CONTROLLED PRODUCTION
→ MONITOR / RETIRE
```


## 15.2 Product Types

| **Type**   | **Example Scope**                                                          | **Acceptance Criteria**                                                 |
|-----------|---------------------------------------------------------------------------|-------------------------------------------------------------------|
| Algorithm | Universe selection, regime detection, execution, risk sizing, allocation. | Deterministic explanation, testing, complexity, and failure mode.         |
| Indicator | Market structure, volume/volatility, trend, momentum, flow, composite.    | Economic justification, incremental value, redundancy test.            |
| Model     | Classification, ranking, forecasting, anomaly, NLP/sentiment.             | Calibration, OOS, drift, explainability and data leakage control. |
| Strategy  | Trend, breakout, mean reversion, relative value, rotation, hedge.         | Net-of-cost return, drawdown, regime robustness and capacity.      |

## 15.3 Minimum Content of Model/Strategy Card

- Name, version, owner, purpose, market/timeframe/universe and economic rationale.

- Data sources, period, lineage, license, leakage, bias and missing-data policy.

- Feature/indicator/model/strategy logic, parameter limits and baseline comparison.

- Train/validation/test, purged/embargo and walk-forward design.

- Net-of-cost results, drawdown, capacity, regime, stress, Monte Carlo and sensitivity.

- Uncertainty, failure modes, explainability, security/privacy/compliance impact.

- Promotion status, risk budget, monitoring, drift, kill criteria, rollback and decommission.

<a id="bolum-16"></a>
# 16. BACKTEST, WALK-FORWARD AND TUNING CONSTITUTION



## 16.1 Mandatory Backtest Controls

| **Risk**             | **Mandatory Mitigation**                                                                       |
|----------------------|------------------------------------------------------------------------------------------|
| Look-Ahead / Leakage | Point-in-time data, fit/transform separation, future label and feature timestamp controls.
| Survivorship         | Delisted/inactive assets and historical universe records.
| Cost Realism         | Fee, spread, slippage, funding, tax/withholding, borrow and latency assumptions.
| Execution Realism    | OHLC ambiguity, partial fill, min notional, tick/step, liquidity and queue.               |
| Overfitting          | Nested/purged CV, OOS, walk-forward, parameter stability and multiple testing correction. |
| Regime Robustness    | Trend/range/volatile/crisis, bull/bear and liquidity stress.                              |
| Capacity             | Order size/depth, turnover, market impact and scalability.                                |
| Reproducibility      | Versioned code/data/config, seed, environment, immutable result artefact.                |

## 16.2 Tuning Principles

- Parameter ranges must be economically and technically bounded; unlimited search is prohibited.

- The objective function is not only gross profit; it includes net return, drawdown, stability, turnover, tail risk and complexity.

- Best best single parametre yerine robust plateau and stability tercih is revised.

- Tuning results do not move to production automatically; OOS, paper, validation and approval evidence are required.

- Failed backtest experiments are not deleted; they are recorded as negative results and lessons.

## 16.3 Promotion Seviyeleri

| **Level**             | **Minimum Evidence**                                | **Authority**              |
|-----------------------|-----------------------------------------------------|----------------------------|
| RESEARCH_ONLY         | Hypothesis and reproducible prototype.              | Report/experiment only; no trading. |
| EXPERIMENTAL          | Backtest and basic robustness.                       | Sandbox only.              |
| STAGED_CANDIDATE      | Out-of-sample/walk-forward, security/privacy review.          | Shadow/paper preparation.    |
| PAPER_APPROVED        | Paper/shadow performance and validation.             | Real money not available.           |
| LIMITED_LIVE_ELIGIBLE | Committee approval, small risk budget, kill criteria.     | Time-bound controlled live.    |
| PRODUCTION_APPROVED   | Long-term proof, monitoring and incident readiness. | Within policy limits. |

Opportunity lifecycle labels such as `WATCH_ONLY`, `CONFIRMATION_PENDING`,
and `PAPER_ELIGIBLE` are reporting states, not trade authorization.
Strategy promotion remains governed by research, backtest, walk-forward,
out-of-sample, robustness, paper, and human approval gates.

<a id="bolum-17"></a>
# 17. CAPITAL ALLOCATION, PORTFOLIO AND PROFIT MANAGEMENT



AI4BINANCE’s financial objective is risk-adjusted, post-cost, and sustainable net profit. No department can equate profit targets with "more trading" or "higher leverage".

## 17.1 Capital Allocation Principles

- Risk budget based on market and strategy; determined by volatility, liquidity, drawdown, correlation, and confidence.

- Concentration limits applied for single asset, single venue, single strategy, and single model.

- Cash and low-risk reserves; absence of opportunity is not failure, but a capital protection tool.

- Futures are managed in a separate risk pool with explicit leverage limits; cross margin is default prohibited.

- Current cost and loss do not grant asset preference; hold vs new opportunity is risk-adjusted compared.

## 17.2 Profit and Performance Measurement

| **Category** | **Indicators**                                                                               |
|--------------|-----------------------------------------------------------------------------------------------|
| Return       | Net P&L, realized/unrealized, CAGR, benchmark excess return, hit rate.                        |
| Risk-Adjusted | Sharpe, Sortino, Calmar, profit factor, expectancy, tail ratio.                               |
| Risk         | Max drawdown, VaR/CVaR, downside deviation, concentration, correlation, liquidation distance. |
| Cost      | Fee, spread, slippage, funding, tax, data/infrastructure cost, turnover.                      |
| Quality      | OOS-live gap, calibration, false positive, missed opportunity, execution quality.             |

> [!WARNING]
> **PROFIT TARGET LIMIT**
> Profit increase target; cannot be justified by guarantee, aggressive risk increase, martingale, uncontrolled averaging, model overfitting, or legal/confidentiality violation.


<a id="bolum-18"></a>
