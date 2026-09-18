---
document_id: AI4B-ARCH-FRM-001
title: AI4BINANCE Architecture Overview
document_type: FRAMEWORK
version: 1.11.2
status: ACTIVE
owner: Enterprise Knowledge Governance
authority_level: NORMATIVE
authority_layer: L6_ARCHITECTURE_ONTOLOGY_ADR
authority_scope: architecture_overview
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
canonical_path: docs/architecture/framework_architecture_overview.md
machine_enforceable: true
audit_required: true
classification: INTERNAL
---

# Architecture - ELI5

## ELI10

This document is like the LEGO map of the system. Which piece collects data, which
component owns control and which component only writes reports;
No one can secretly place orders on their own.

Core vNext's canonical governance, schema, entity rule, relationship rule,
policy and output-format source:
[`docs/governance/framework_core_vnext_governance.md`](/docs/governance/framework_core_vnext_governance.md).


## Big image

Platform is similar to a factory. Each section performs a single task and passes the result to the next section
as a typed packet.

```text
Binance public data
  -> DataAcquisitionAgent
  -> immutable MarketSnapshot
  -> DataQuality + Liquidity
  -> 34 logical analytical capabilities
  -> Confluence
  -> StrategyCandidate
  -> Risk
  -> Validation
  -> NO_TRADE / research artifact / paper-only lifecycle
```

Core vNext extends this flow with capability-first governance:

```text
Governance Registry
  -> Event Fabric
  -> Canonical Snapshot
  -> Feature Snapshot
  -> Evidence Fabric + Agent Observations
  -> Evidence Completeness
  -> Setup Engine
  -> Deterministic Core
  -> Action Ceiling
  -> Risk Engine
  -> Decision Governance
  -> Execution Gates
  -> Audit, Closure Review, Lesson, Research and Validation
```

The self-improvement loop is also bound to the same fail-closed backbone:

```text
ClosureReview / AuditEvent / CapabilityGap
  -> LOOPS LISTEN
  -> Web Intelligence Radar OBSERVE
  -> Hypothesis ORIENT
  -> Validation PROVE
  -> Governance STAGE
  -> Registry update candidate / rejection
```

This loop does not autonomously change code, parameters, risk limits, or live mode
Cannot be modified; only can be monitored, research candidate and validation plan are generated.

## Why a Single Snapshot?

All agents must view the same picture. If one agent uses 10:00 data and another
uses 10:05 data, the result cannot be compared. Therefore the `MarketSnapshot`
value remains immutable and all outputs carry the same `snapshot_id`.

## Layers

### 1. Exchange and Data

- `exchange/transport.py`: limited public HTTPS GET.
- `exchange/client.py`: time, exchangeInfo, ticker, book ticker and klines.
- `exchange/private.py`: only read-only account/open-orders HMAC REST
- `data/acquisition.py`: extracts the open candle and generates a common snapshot.
- `data/archive.py`: checksum-based Parquet research archive.

`src/ai4binance/data/market_history_continuous.py` owns resumable public
Spot, USD-M perpetual, and COIN-M perpetual/delivery history collection.
It reuses `src/ai4binance/data/market_history_sync.py` for checksum-verified
compressed sources, the canonical eligible universe, single-instance ownership,
and UTC aggregation, and `src/ai4binance/data/archive.py` for persisted OHLCV.
The default bootstrap is 30 days; original per-stream progress boundaries
survive shutdowns. COIN-M contract quantities remain distinct from Spot units.
Shared pair-index series have one collector owner. Delivery contracts have no
perpetual funding. Missing or invalid provider history remains explicit.

`src/ai4binance/data/market_depth.py` owns public L2 diff-depth transport,
durable compressed event recording, periodic checkpoints, and local-only replay.
It reuses `src/ai4binance/exchange/order_book.py` for deterministic reconstruction.
Spot update ranges and Futures previous-final-update IDs must bridge the initial
snapshot and remain continuous. Reconnection, overflow, invalid identity,
crossed/empty books, storage failure, and stale state must fail closed.
Snapshot coverage is provider-limited; unseen outer levels and offline event
history must never be fabricated. All eligible streams are grouped and paced;
USD-M and COIN-M share their public REST weight budget. The existing
`market-history` service owns both producers, and consumers reuse the central
archive or journal without independent retrieval. Proof contracts include
`tests/test_market_history_continuous.py`, `tests/test_coin_m_collection.py`,
`tests/test_order_book_recorder.py`, and `tests/test_market_depth.py`.
These data-only capabilities remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED`.

Private REST adapter is not bound to the CLI and account/open-orders/`myTrades`
uses a signed GET-only allowlist for `exchange/ws_api.py`; Ed25519 signature
Allowlist Binance host, bounded response matching, `session.logon`, read-only
`account.status`/`openOrders.status` and authenticated order request core
sends. The `order` methods in `execution/live_spot.py` handle all `LiveGateInput`
It re-validates the conditions and the one-to-one preview hash inside. CLI live order
submission and lifecycle journaling are governed by
`docs/contracts/interface_contract_live_order_lifecycle.md`.
If not sent; the default status remains `LIVE_ORDER_BLOCKED`.

### 2. Capability Fabric and Runtime Components

- 49 platform definitions exist in the legacy-compatible `AgentDefinition` catalog.
- 35 definitions are in the analysis stage: 34 logical analytical capabilities
  plus one `memory_advisory` definition.
- The five AI orchestration role packages are governed separately in
  `docs/registries/registry_agent_registry.md`; they are not the 49 platform
  definitions and do not supply runtime or trading authority.
- `CapabilityDefinition` and `CapabilityRegistry` project the 34 analytical
  catalog entries into immutable runtime metadata. Their `runtime_eligible`,
  `execution_class`, and `activation_policy` fields describe current bounded
  scheduler admission only; they do not issue a scheduling command or widen
  authority.
- 10 core and 23 advanced capability implementations, along with the
  `trend_events` implementation, are present.
- Trend events; OHLC4, Supertrend ATR14/multiplier2, EMA cross and confirmed swing
Generates knowledge.
- The user does not have final signal or order authority.

Independent capability implementations run in parallel within a bounded thread
pool. A dependent capability waits for its declared inputs; if an input result
is unavailable, it becomes `BLOCKED`. A runtime actor only instantiates and
schedules these bounded implementations; it is not a separate authority class.
All capability contracts remain `RESEARCH_ONLY`, `execution_allowed=false`, and
`LIVE_ORDER_BLOCKED`.

Before worker creation, `CapabilityPreflightPlan` evaluates each analytical
capability against runtime eligibility, required snapshot data, compatible
timeframes, compatible regime, and internal capability dependencies. Rejected
capabilities emit visible `NOT_APPLICABLE` results with deterministic reason
codes and consume no worker execution. `ECONOMY` mode additionally defers
catalog entries marked `expensive`; it is a bounded cost policy, not an
authority, promotion, or execution mode.

`CapabilityBundleRegistry` groups all 34 logical analytical capabilities into
six exhaustive, non-overlapping runtime-planning bundles: `market_state`,
`structure_location`, `momentum_participation`, `liquidity_flow`,
`cross_market_derivatives`, and `setup_event`. The bundle projection exposes
scheduled and skipped groups in cycle telemetry. Within each ready dependency
layer, `CapabilityBundleExecutor` submits at most one task for each bundle,
provides every member the same immutable prior-results view, and merges member
results in canonical capability order. This changes task grouping only; it does
not change capability admission, dependency readiness, authority class,
promotion, or live-execution paths.

`EvidenceFusionEngine` consumes the completed analytical results and selects one
strongest usable result per independent evidence cluster before calculating the
existing `confluence` result. The `confluence` result identity remains a
compatibility contract for strategies, risk, validation, telemetry, and audit.
The engine is deterministic and advisory-only: it cannot change risk limits,
resolve a veto, promote a strategy, authorize a decision, or execute an order.
`ConfluenceAgent` remains only as a compatibility facade over this canonical
engine.

`DataQualityGate` runs first against the immutable canonical snapshot. It
produces the existing `data_quality` compatibility result before liquidity,
preflight, or analytical execution. A blocked result preserves the deterministic
`EARLY_EXIT_NO_TRADE` path; no capability bundle is created. The gate is a
control-only component and cannot authorize a decision, risk change, strategy
promotion, or order. `DataQualityAgent` remains only as its compatibility
facade.

`RiskGate` runs after evidence fusion and candidate arbitration. It produces the
existing `risk` compatibility result only when its `confluence` dependency is
usable, then applies the existing deterministic `RiskEngine`, exchange-filter,
and virtual-market checks. Missing or unusable dependencies preserve
`AGENT_DEPENDENCY_BLOCKED`; the gate cannot approve a decision, modify risk
limits, promote a strategy, or execute an order. `RiskAgent` remains only as a
compatibility facade.

`ValidationGate` runs after all orchestration results, candidate arbitration,
and risk evaluation. It aggregates evidence and deterministic score components
for research while unconditionally retaining the mandatory approval blockers.
Its output is always `VALIDATION_REJECTED`, `NO_TRADE_CAPITAL_PROTECTION`, and
`execution_allowed=false`; it cannot promote a strategy or execute an order.
`ValidationAgent` remains only as a compatibility facade.

`UniverseLiquidityGate` runs immediately after `DataQualityGate` and before
preflight or analytical scheduling. It requires usable data-quality evidence,
then performs deterministic Spot trading-status, exchange-filter, pricing,
bid/ask, and spread checks. A blocked result preserves `EARLY_EXIT_NO_TRADE`;
the gate cannot authorize a decision, promotion, or order.
`UniverseLiquidityAgent` remains only as a compatibility facade.

### 2.1 Market Outlook Intelligent Engine

`outlook/` layer does not compute new technical indicators. It refers to the same immutable snapshot.
current trend, regime, volatility, support/resistance, setup, news and volume-profile agent
Synthesizes the outputs into a typed `MarketOutlook` contract. The output includes:

- 1d, 4h, 1h, 15m and 5m bias,
- **pro-trend direction** and **timeframe conflict**,
- market regime, volatility state and macro-cycle proxy,
- up to five research setups
- high-impact events caused by source-linked drivers,
- ATR-buffered support/resistance zones
- TPO/composite limits and volume-weighted POC proxy

Outlook engine does not generate signals, provide risk approval, or carry order authority. Real
TPO auction profile, single-print and composite balance-area calculation is still missing;
volume-profile result is only applicable in `PROXY_ONLY` and `RESEARCH_ONLY` context.

### 3. Strategy and Risk

`strategies/` generates research candidates. `risk.py`; equity, spread, slippage,
cooldown, daily loss, inventory and Binance filters are checked. Approval of risk calculation
does not mean the order is approved.

### 4. Paper lifecycle

`execution/` does not send orders to the real exchange. Fee/slippage, staged exit, stop-first
ordering, monotonic trailing and closure review are simulated. Ledger append-only
uses append-only JSONL.

### 5. Backtest, Walk-Forward, and Tuning

- Signal only sees closed candles.
- Entry is as early as the next candle's open.
- If stop and target are on the same candle, stop is accepted first.
- Walk-forward selects the parameter in train and measures it once in the following OOS.
- OOS report also records effective sample size, confidence interval, confirmatory/exploratory label
  and Bonferroni multiple-testing correction.
- Tuning only scans whitelist and bounded parameters.
- Successful result is at most `STAGED_CANDIDATE`; automatic live permission is not granted.

### 5.1 Research governance

- `research_governance.py`: falsifiable hypothesis lifecycle, hash-linked run card
  and only includes a strategy decay evaluator that can suggest demotion.
- Run card dataset/config/strategy/artifact SHA-256, code revision, seed, cost
  It carries assumptions, metrics, and blockers.
- Incomplete health proof cannot be considered healthy; decay automation for recovery or promotion
  cannot do this and requires human re-approval.

### 5.2 Backtest integrity and overfit proof

- `validation/integrity.py`: batch/prefix comparative look-ahead analysis,
  warmup-offset recursive stability analysis and point-in-time feature lineage gate.
- `WalkForwardConfig.purge_size` manages the label overlap risk at the train/test boundary;
  `embargo_size` manages the explicit gap between consecutive fold starts.
- `validation/overfit.py`: return skew/kurtosis and hypothesis-count based
  Deflated Sharpe proof with train-winner/OOS-rank based selection-overfit
  diagnostic is generated.
- All these reports remain `execution_allowed=false` and are only for promotion
  blocking decisions.

### 5.3 Deterministic Event and Order State

- `events/`: injectable UTC/simulated clock, SHA-256 linked immutable
  event and contiguous sequence validating bounded event bus.
- `execution/order_state.py`: submitted, accepted, partially-filled, filled,
Replays cancelled and rejected transitions using the same reducer.
- Partial fill quantity, remaining quantity and weighted average fill price
is rebuilt deterministically; illegal transition or hash/sequence discrepancy
Produces an open error.

### 5.4 Exchange, Portfolio and Advisory Resilience

- `exchange/resilience.py`: request-weight budget and server-time drift gate.
- `portfolio/reconciliation.py`: local/exchange open orders by client-order-id
read-only compares.
- `portfolio/risk_budget.py`: gross, symbol, correlation-group and strategy exposure
It evaluates the limits only at the proposal level.
- `agents/advisory.py`: hash-based evidence packet, source citation verification,
  bull/bear/risk/data-quality roles, conflict report, and retry-bounded checkpoint.
Advisory output shall never carry signal, promotion, or execution authority under any circumstances.

### 6. Learning and LLM Limits

The learning engine may propose lessons and experiment candidates. It cannot activate production parameters.
The risk cannot be increased and orders cannot be given. Advisory LLM only provides explanations and monitors.

`learning/lifecycle.py` attaches a persistent local lifecycle worker to the
`ControlledLearningLoop`. It stages advisory lessons, accepts only explicit
local transition requests, and records durable tamper-evident audit evidence.
It cannot originate a human approval: the canonical governed lesson transition
requires an explicit human-approved request and clean validation evidence.
Nonterminal lessons expire deterministically; the persisted lifecycle remains
`execution_allowed=false`, `RESEARCH_ONLY`, and `LIVE_ORDER_BLOCKED`.

### 7. WHALE-FUSION Research Boundary

- `whale_fusion/models.py`: immutable events for whale, social and derivatives evidence.
Provenance is mandatory contracts.
- `whale_fusion/derivatives/binance_client.py`: uses only public HTTPS GET
  Binance USD-M collection; it does not accept private, account, or order
  endpoints.
- `whale_fusion/features.py`: OI change, z-score/percentile, price-OI regime,
funding/basis context, taker imbalance, and top/global divergence accounts.
- `whale_fusion/onchain/providers.py`: no network call for external provider, immutable
  envelope/replay boundary; it validates HTTPS host/provider allowlists, payload SHA-256,
  size, freshness, finality and chain-event deduplication fail-closed.
- `whale_fusion/onchain/normalizer.py`: strictly validates the accepted provider
  envelope's canonical transfer payload; it performs no network call.
- `whale_fusion/onchain/registry.py`: chain + address keyed registry with mandatory provenance
  and immutable wallet-label registry.
- `whale_fusion/onchain/classifier.py`: deterministically classifies large transfers into Binance, DEX, bridge,
  staking, unlock, market-maker, stablecoin, accumulation/distribution, new wallet
  and split-transfer events.
- `whale_fusion/social/registry.py`: founder, project team, fund manager,
  market-maker manager, whale, analyst, exchange, regulator, security and unlock/
The governance accounts are allowedlisted per platform basis.
- `whale_fusion/social/normalizer.py`: provider's explicit event-type, stance and asset
Converts the metadata into a strict canonical post model; does not emit signals from the metadata.
- `whale_fusion/social/engine.py`: verified account, confidence, freshness, asset,
Performs duplicate and opposite stance checks.
- `whale_fusion/fusion.py`: on-chain `%40`, social `%25`, derivatives `%35`
with their weights: channel-average, linear time-decay, and contradiction penalty
Apps. At least two independent channels are required; derivatives Spot context
remains supplementary.
- `whale_fusion/integration.py`: `FusionResult` and `MarketSnapshot` between
snapshot ID, symbol, and timestamp consistency; the original snapshot is not modified.
- `whale_fusion/agent.py`: only `whale` governance definition to the private fusion agent
  bonds; hard-gate compatibility is not present and rejects authority/promotion deviation.
- `whale_fusion/audit.py`: deterministic record ID with restart-idempotent,
  produces secret-redacted and append-only JSONL fusion audit.
- `application/orchestration/whale_fusion.py`: canonical cycle runs engine → audit → immutable
  snapshot → orchestrator sequentially. Reports audit error
  as `FUSION_AUDIT_WRITE_FAILED` and execution is closed.
  `application/whale_fusion.py` remains an identity-preserving compatibility facade.
- `ops/architecture_migration.py`: evidence-only migration classifications keep every source
  module in one explicit `KEEP`, `MOVE`, `SPLIT`, `MERGE`, `FACADE`, `DEPRECATE`, or
  `REMOVE_CANDIDATE` state and cannot grant execution or promotion authority.
- `cli.py whale-fusion-research`: safe research pipeline without provider call
  generates report; in tests, canonical cycle can be injected.

ELI5: It's like an additional camera showing the leveraged behavior of the futures market crowd
which does not steer the spot decision engine. Output is always
`RESEARCH_ONLY`, `execution_allowed=false` remains.

### 8. External Intelligence & Evidence Fabric

`external_intel/` layer includes external intelligence, social sources, GitHub research, and security
and regulatory evidence into the shared `ExternalFinding` contract. The first MVP
scope, X, News, Reddit, Telegram, Security, and Regulatory radars provider
returns `DATA_UNAVAILABLE` when unavailable; GitHub Radar is connected to the existing capability-first engine
adapter.

EIEF has two responsibilities:

- Technology Development Radar: converts external technology evidence that can
  improve the AI4BINANCE architecture into research-only candidates.
- Binance Spot/Futures Opportunity News Radar: classifies opportunity/risk news
  from the eligible asset universe as advisory impact.

This layer does not generate signals, entry, stop, take-profit, risk limit, or order authority.
It gives the Decision Governance Engine only compact advisory risk impact.

## Stability rules

1. Network, file system, and core accounts are kept separate.
2. Decimal accounts are protected within financial/filter limits.
3. Error messages do not contain secrets.
4. If data is missing, stale, inconsistent, or unavailable, the affected
   capability must emit an explicit blocker such as `DATA_UNAVAILABLE`,
   `DATA.MISSING`, or `EVID.MISSING_CRITICAL_EVIDENCE`; silent fallback is not
   allowed when it changes analytical, replay, validation, risk, or execution
   behavior.
5. Every behavior change is validated with pytest, Ruff, and MyPy.
6. Orchestrator uses a single bounded thread pool in an analysis cycle; dependency
   layers reuse this pool, while results are collected in order of name.
7. `agents/telemetry.py` per-agent duration, status and blocker without interfering with the decision outcome
Writes the count to a bounded sink; high-cardinality free text is not supported.
8. `market_context.py` only explicit provider ID, HTTPS host allowlist, health
Binds an event to Market Outlook with probe and provenance validation.
9. `sandbox.py` AST allowlist and backend capability gate apply; real isolation
If the backend is not present, it rejects the execution. If there is no scanner in `security_scan.py`, it gets blocked.

### Read-only Evidence MCP Limit

- Agentlar MCP yuzeylerine dogrudan baglanmaz. Canonical rota:

```text
Agent
  -> Tool Policy
  -> Authorization
  -> MCP Gateway
  -> Tool
```

- AI4BINANCE MCP Gateway; Filesystem MCP, GitHub MCP, PostgreSQL MCP,
  Research MCP and future Binance READ-ONLY adapter surfaces in one
  default-deny policy boundary.
- `filesystem.delete`, `shell.admin`, and `exchange.place_order` every MCP policy
  remains forbidden for this path.
- `outlook/storage.py` writes the latest deterministic Market Outlook
  to the state artifact atomically.
- `mcp/evidence.py`, only fixed allowlist artifacts with size, schema, SHA-256,
  and freshness validation under the respective permissions.
- `mcp/server.py`, optionally enables local STDIO transport via the FastMCP SDK
  and provides four read-only tools.
- Tools do not accept file path, shell command, credential, wallet, risk,
  promotion, or order parameters.
- If MCP is not found, the core process is unaffected; if an artifact is not
  found, an open blocker is produced. All responses remain `RESEARCH_ONLY` and
  `LIVE_ORDER_BLOCKED`.

## Known open limitations

- Ed25519 request/session core is present; real testnet/production authentication proof,
  reconnect soak and user-data subscription lifecycle external validation is pending.
- Read-only `myTrades` based weighted cost basis is available; full pagination for records exceeding 1000
  and third-party asset fee conversion such as BNB are pending external price proof.
- Rate-limit/time-drift policy is present; real WebSocket reconnect, gap backfill and
  exchange stream state machine is not yet implemented.
- Wallet reader is not connected to the real application flow.
- No rebalancing proposal agent.
- Market-context registry, health and provenance wiring is present; real macro/news
  provider adapter is waiting for user selection.
- WHALE-FUSION real on-chain/social provider adapter and OOS promotion proof is missing.
  Provider envelope/replay admission limits are complete, but real adapter selection,
  credential, raw-event persistence and retention management is pending.
- ADL account is not present in public collector because it requires a private account context.
- Crew/Local LLM/RAG process plan, stdlib second-brain index, loopback
  llama.cpp advisory runner and HTML UI artifacts are present; no provider means it's open
  It produces a blocker.
- Real long-term BTCUSDT OOS/paper proof is not yet providing promotion.
- Deflated Sharpe and selection-overfit models are present; in the real run-card flow
  Mandatory promotion gate connection is the next validation-pipeline segment.

## Live Status

```text
NO_TRADE
RESEARCH_ONLY
LIVE_ORDER_BLOCKED
```
