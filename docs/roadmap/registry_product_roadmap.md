---
document_id: AI4B-ROADMAP-REG-001
title: AI4BINANCE Roadmap
document_type: REGISTRY
version: 1.9.1
status: ACTIVE
owner: Enterprise Knowledge Governance
authority_level: NORMATIVE
authority_layer: L5_REGISTRIES_ROADMAP
authority_scope: product_roadmap
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
canonical_path: docs/roadmap/registry_product_roadmap.md
machine_enforceable: true
audit_required: true
classification: INTERNAL
---

# Route Map — ELI5

## ELI10

This document is like a travel map. Which part is ready, which part is under research /no\_think
which part is in research, and which part is visibly closed for security reasons; this keeps the system
easy to understand at a glance.


Indicators:

- Code and tests exist.
- 🟡 Code exists but real data/integration/promotion proof is missing.
- ⛔ Not yet implemented or closed for security reasons.

## Step 0 — Safe foundation ✅

- Python 3.14.7, typed modeller, immutable snapshot
- `NO_TRADE` and `LIVE_ORDER_BLOCKED` are default
- Secret redaction and append-only audit
- Pytest, Ruff and MyPy quality gate

## Phase 1 — Spot Data: Available / Partial

- ✅ Public Spot REST, exchangeInfo, klines, ticker and book ticker
- ✅ Closed lamp, freshness and data quality controls
- ✅ Checksummed Parquet archive
- ✅ Dataset revision manifest that seals four timeframes in a single checksum chain
- 🟡 Long-term BTCUSDT validation archive depth depends on external data collection
- 🟡 Ed25519 imza + `session.logon` + read-only account/orders + gate-enforced
  order request core is complete; real testnet auth/reconnect soak is pending

## Phase 2 — Analysis Capability Fabric ✅ / 🟡

- ✅ 49 platform definitions: 34 logical analytical capabilities, one
  `memory_advisory` analysis definition, and deterministic lifecycle/control
  components
- ✅ 10 core + 23 advanced capability implementations plus the trend-events
  implementation
- ✅ Supertrend ATR14/OHLC4/multiplier2 and cross primitives
- ✅ Typed Market Outlook synthesis: multi-TF bias, regime, setup radar,
  high-impact event contract, ATR-buffered levels and TPO/composite proxy boundary
- 🟡 Advanced agents lack real OOS/false-positive proof
- 🟡 News/sentiment/derivatives providers are not connected
- 🟡 Real TPO auction profile, single prints and composite balance-area calculation are missing;
  current volume-weighted POC is only research proxy

## Phase 3 — Strategy, Risk, and Paper Trading: Available / Partial

- ✅ 20 playbook registry and 10 calculation-producing playbooks
- ✅ Convergence, reaction statistics, volume-heavy breakouts and retracement validations
  for the `compression_breakout` research playbook
- ✅ Risk, lot/tick/notional, spread/slippage and Spot inventory controls
- ✅ Paper lifecycle, staged exit, trailing and closure review
- ✅ Hash-linked event replay and partial-fill order state reducer
- ✅ Read-only open-order reconciliation and proposal-only portfolio risk budget
- 🟡 Read-only wallet adapter is present but CLI/application wiring is missing
- ⛔ Rebalancing proposal agent
- ⛔ Real or automated order adapter

## Phase 4 — Backtest and Validation ✅ / 🟡

- ✅ Next-bar-open, fee/slippage, stop-first and same-bar trailing protection
- ✅ Optional candle-volume participation, price impact, and partial-entry-fill stress
- ✅ Rolling/anchored walk-forward and OOS regime report
- ✅ Bounded tuning, sensitivity and human promotion board
- ✅ Cost stress and seeded bootstrap
- ✅ Out-of-sample confidence interval, effective sample size, confirmatory label and
  multiple-testing correction management
- ✅ Hash-linked research run card, hypothesis lifecycle and demotion-only decay
- ✅ Look-ahead, recursive stability and temporal feature-lineage gate'leri
- ✅ Purge/embargo walk-forward pencereleri
- ✅ CPCV purge/embargo split diagnostic and candle-path Monte Carlo
- ✅ Bounded, artifact-based indicator/strategy integrity catalog
- ✅ Isolated Optuna benchmark adapter; fails closed if optional package is missing
- ✅ `aggTrades` revision, candle reconciliation, and trade-flow lineage contract
- ✅ Logarithmic checkpoint + bounded refinement integrity scan
- ✅ Seeded block-bootstrap SPA and model-confidence-set diagnostic
- ✅ Sequence-aware read-only L2 book core and conservative queue-fill replay
- ✅ `range_rotation`, `volatility_expansion`, and measurable liquidity-sweep playbooks
- ✅ Cost-basis profit basis and rebuy band derived from realized sales
- ✅ Multi-symbol correlation, HHI, and correlated-exposure diagnostic
- ✅ Deflated Sharpe and selection-overfit diagnostic contracts
- 🟡 Real long-term dataset and multi-regime promotion proof are missing
- 🟡 Multi-symbol correlation diagnostic is present; real portfolio backtest proof is missing

## Phase 5 — Controlled Learning: Partial

- ✅ Lesson and experiment recommendation models
- ✅ Atomic summary and append-only audit
- 🟡 Learning loop that automatically collects validation/paper artifacts is not connected
- ⛔ Automatic production activation; explicitly disabled

## Phase 6 — Knowledge and Sandbox: Partial

- ✅ WHALE-FUSION Phase 1: event taxonomy, immutable models, and provenance
- ✅ WHALE-FUSION Phase 2: public Binance USD-M OI/ratio/funding/taker/
  mark-index/depth/aggregate-trade collector and liquidation parser
- ✅ WHALE-FUSION Phase 3: OI feature engine and four price-OI regimes
- ✅ WHALE-FUSION Phase 4: canonical on-chain normalizer, wallet-label registry,
  whale-event classifier and split-transfer detector
- ✅ WHALE-FUSION Phase 5: social account registry, canonical post normalizer,
  freshness/confidence/dedup controls and contradiction detector
- ✅ WHALE-FUSION Phase 6: three-channel fusion score, time-decay, channel-average,
minimum independent channel and contradiction penalty
- ✅ WHALE-FUSION Phase 7: snapshot envelope, advisory whale agent, orchestrator
  wiring and restart-idempotent JSONL audit
- ✅ WHALE-FUSION Phase 8: application assembly service, audit-failure blocker and
`whale-fusion-research` secure CLI command
- 🟡 Futures data is only supplementary `RESEARCH_ONLY` evidence
- 🟡 On-chain core is ready; real indexer/provider adapter is not yet connected
- 🟡 Social core is ready; real X/Telegram/provider adapter is not yet connected
- 🟡 Fusion score is bound to the orchestrator but only `RESEARCH_ONLY`; OOS validation
A promotion certificate is pending
- 🟡 CLI runs the canonical/empty cycle; real provider ingestion is not connected yet.
- ⛔ ADL private account metrics and the continuous WebSocket connection manager are missing.
- ✅ Explicit market-context provider registry, health isolation, HTTPS host
  allowlist, content hash and ResearchApplication wiring
- 🟡 Real macro/news provider selection and its adapter are waiting for external integration.
- ✅ Crew/Local LLM/RAG process plan is typed, loopback-only and fail-closed.
- ✅ Stdlib second-brain RAG index, loopback llama.cpp advisory runner and HTML UI
- ✅ A local-only, sequential advisory evaluation harness runs at most 32 injected-provider fixtures and fails the full batch closed on any fixture failure.
- ✅ Advisory-fixture runner admission is singleton, network- and secret-denied, fixed-command-bound, and capped at `RESEARCH_ONLY`.
- ✅ The on-demand runner invokes only an admitted batch through an injected loopback provider; denied admission never calls the provider.
- ✅ An explicitly configured local evidence writer atomically persists both admitted and admission-blocked redacted fixture outcomes with tamper-evident audit evidence; writer failures are surfaced.
- 🟡 Provider-backed continuous runner, provider deployment, and rich UI remain pending.
- Optional FAISS adapter
- ✅ AST allowlist, resource limits and fail-closed sandbox backend capability gate.
- 🟡 Real network-closed Docker/OS sandbox backend is not connected yet.
- ✅ Optional security-scanner/SARIF adapter contract; blocked when the scanner is unavailable.
- ✅ Advisory Agent v2 evidence packet, citation, role-conflict and checkpoint boundary.
- ✅ Exchange request-weight and server-time drift gate
- 🟡 WebSocket reconnect/gap-backfill runtime and CCXT read-only conformance adapter are missing.

## Step 7 — Live compatibility ⛔

Live processing is only possible when all technical proofs and explicit user permissions are completed.
may be evaluated in a separate project phase. Today:

```text
execution_allowed=false
LIVE_ORDER_BLOCKED
```

## Recommended next step

1. Development run card persistence is now in place and enforced through the verified writer.
2. Governed lesson approval and expiry persistence is attached to the `ControlledLearningLoop`; retain explicit human transition requests and local-only audit evidence.
3. Require 'Capability admission' in the Nightly Quality Triage runner entry.
4. Redacted advisory fixture execution includes an injected loopback-provider adapter with prompt-hash and response-acceptance checks; keep provider deployment and promotion proof counting separate.
5. Connect the permanent event journal and stream recovery core to the application startup.
6. Add the real public WebSocket adapter with the sequence-gap/backfill agreement.
7. External research candidates should be reproduced using pinned revision and passed through the performance gate.
8. Generate purge/embargo OOS proof with the sealed BTCUSDT dataset revision.
9. Finally, isolate and approve the Langflow pilot separately and the real Ed25519 testnet session
Verify; separate production permissions.
