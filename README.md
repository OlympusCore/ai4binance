---
document_id: AI4B-DOC-README-001
title: AI4BINANCE EnterpriseAI vNext Repository README
document_type: REGISTRY
version: 1.0.1
status: ACTIVE
owner: Enterprise Knowledge Governance
authority_level: NORMATIVE
authority_layer: L5_REGISTRIES_ROADMAP
authority_scope: repository_readme
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
machine_enforceable: true
audit_required: true
classification: INTERNAL
canonical_path: README.md
---

# AI4BINANCE EnterpriseAI vNext

## ELI10

This repository is the governed AI4BINANCE workspace. It explains what the system can do, which evidence is real, and why live trading remains blocked unless every validation and risk gate passes.


AI4BINANCE reviews Binance Spot data, tests strategy ideas, and remains a research platform that does not open operations when evidence is insufficient. It does not guarantee profit.
The canonical source for Core vNext governance, schema, entity/relationship rules, output format, and the policy-as-code backbone is:
[AI4BINANCE Core vNext Governance Framework](docs/governance/framework_core_vnext_governance.md).
This backbone defines AI4BINANCE with a pyramid authority model, evidence-based fail-closed operation, LOOPS, Web Intelligence Radar, research-only development candidates, and the transparent digital-company operating model.

## ELI10: What does the system do?

Think of it as a control tower:

1. It only retrieves market data from Binance.
2. Checks whether the data is broken or outdated.
3. Expert agents examine the same data snapshot.
4. The strategy engine only creates research candidates.
5. The risk engine writes all missing proofs as blockers.
6. Backtest, walk-forward, and tuning candidates are tested against historical data.
7. If the proof is insufficient, the result is `NO_TRADE`.

```text
Public data -> immutable snapshot -> agents -> candidate -> risk
            -> backtest/walk-forward/tuning -> human review
```

## Current Real Situation

| Area | Status |
|---|---|
| Python | 3.14.7 |
| Agent Catalog | 49 platform definitions; 34 logical analytical capabilities |
| Technical Analysis | 10 core, 23 advanced, and 1 trend-events agents |
| Strategy | 20 playbooks; 10 calculation-generating playbooks |
| Supertrend | ATR14 + OHLC4 + multiplier 2, research-only |
| Backtest | Event-based Spot long engine is available |
| Walk-forward/OOS | Code is present; real long-term evidence is missing |
| Tuning | Limited and human-validated governance is present |
| Research integrity | Kline/aggTrade revision, scalable integrity, queue-fill replay, SPA/MCS, Monte Carlo and CPCV are present |
| Paper lifecycle | Present; automatic CLI command is not |
| Wallet | Salt-read HMAC REST adapter is present, not CLI-dependent |
| WebSocket/Ed25519 | Signing, `session.logon`, read-only account/orders and gate-enforced order methods are ready; real testnet/production session authority is pending |
| Live order | Adapter shell is present; real testnet authentication and end-to-end live write proof are missing; blocked |

Verified quality baseline:

```text
Pytest pass count: evidence-bound
Coverage: evidence-bound
Ruff format/lint: evidence-bound
MyPy: evidence-bound
Bandit: evidence-bound
Financial/privacy leak guards: evidence-bound
```

Machine-readable current quality evidence:
`runtime/artifacts/quality/gate/latest.json`. This file contains `pytest_pass_count`,
`coverage_percent`, `coverage_source`, `execution_allowed=false`,
`promotion_status=RESEARCH_ONLY`, and `live_eligibility_status=LIVE_ORDER_BLOCKED`.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Step-by-step usage

### 1. First, check the quality

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  .agents\skills\quality-gate-loop\scripts\invoke_gate.ps1 `
  -RepositoryRoot (Resolve-Path .).Path
```

### 2. View secure default state

```powershell
.\.venv\Scripts\python.exe -m ai4binance.cli status
```

Expected secure result:

```text
NO_TRADE
LIVE_ORDER_BLOCKED
```

### 3. View Agent Catalog

```powershell
.\.venv\Scripts\python.exe -m ai4binance.cli agents
```

### 3a. QAQC-Agent continuous improvement report view

```powershell
.\.venv\Scripts\python.exe -m ai4binance.cli qaqc-agent
```

`QAQC-Agent`, 5S, Hoshin Kanri, Kaizen, Six Sigma, and Poka-Yoke via
Generates a report-only edit/suggestion; does not issue an order or live permission.

### 4. Run Public Spot analysis

```powershell
.\.venv\Scripts\python.exe -m ai4binance.cli analyze-public
```

Do not use API key or order permission.

### WHALE-FUSION Phases 1-2-3-4-5-6-7-8

Think of this motor as a shared data dictionary of three separate detectors. First three phases:

1. Whale Fusion identifies the names and source evidence of social media and derivative events.
2. Binance USD-M public data source for OI, long/short ratios, funding, taker flow,
Reads the difference between mark/index, order-book balance, and large orders.
3. OI change, z-score, percentile, and price-OI regime are deterministically calculated.
4. Validate the on-chain transfer from the provider; Binance, DEX, bridge,
staking, token-unlock, market-maker, stablecoin, new wallet and partial
Separates transfer events.
5. Validate canonical posts from social accounts in the allowlist;
category, event, stance, entity, freshness, duplicate, and conflict checks
   applies these checks.
6. On-chain, social, and derivatives channels with time-decay and fixed weights
merges; averages the duplicates of the same channel and applies the conflict penalty.
7. Binds the fusion result to an immutable market snapshot with the same `snapshot_id`,
Assigns research-only `whale` and records it in an idempotent JSONL audit.
8. Application service same cycle's canonical proofs fusion, audit, snapshot,
Orchestrator passes through the reporting chain; produces a secure CLI output.

This data is only auxiliary research evidence for the spot decision. On its own, it is a signal,
Does not generate risk approval or order authority. Phase 4 does not connect to the external provider; provider
Secure kernel that will be used by the adapters. Phase 5 for real social platform
Not applicable; verifies events explicitly labeled by the provider adapter. Phase 6 combined
generates a score but this score is not a final spot signal or execution permission.

Default fusion weights:

```text
on-chain 40% | social 25% | derivatives 35%
```

Returns `INDEPENDENT_FUSION_CHANNELS_INSUFFICIENT` if there are fewer than two independent channels.
Fusion agent only produces supplementary evidence; confluence, validation and
`NO_TRADE` security flow does not alter ownership.

Secure Phase 8 smoke command without a provider:

```powershell
.\.venv\Scripts\python.exe -m ai4binance.cli whale-fusion-research
```

Default empty cycle, neutral score and `INDEPENDENT_FUSION_CHANNELS_INSUFFICIENT`
blocker with `NO_TRADE` is returned.

### External Intelligence & Evidence Fabric

EIEF connects X, News, Reddit, Telegram, GitHub, Security, and Regulatory radars
to a shared evidence, validation, manipulation/copy scoring, fusion, and advisory
risk-impact contract. The first MVP returns explicit `DATA_UNAVAILABLE` when a
provider is absent and connects GitHub Radar to the existing capability-first
engine through an adapter.

```powershell
.\.venv\Scripts\python.exe -m ai4binance.external_intel scan --symbol HOTUSDT
.\.venv\Scripts\python.exe -m ai4binance.cli external-intel --symbol HOTUSDT
.\.venv\Scripts\python.exe -m ai4binance.cli external-intel-open-web --format json
```

EIEF sends this information to the evidence factory; it is not a trade signal or order engine.
Open Web Radar discovers allowlisted RSS/Atom feeds and seed URLs without collecting hosted LLM or API tokens; it does not store full article text and keeps all outputs within `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` boundaries.

### 5. Archive and verify data

```powershell
.\.venv\Scripts\python.exe -m ai4binance.cli archive-public
.\.venv\Scripts\python.exe -m ai4binance.cli validate-research
```

## Security Rules

- The default mode is `paper/manual`.
- Spot SELL can only reduce the available inventory; there is no naked short.
- Agents cannot send orders.
- A method cannot be a hard gate if it does not have an OOS proof.
- Private keys and API secrets must not be logged or added to Git.
- `--confirm-live` by itself does not issue any command.

## Documents

- [ELI10 document map](docs/registries/registry_documentation_index.md)
- [Core vNext Governance Framework](docs/governance/framework_core_vnext_governance.md)
- [Architecture](docs/architecture/framework_architecture_overview.md)
- [Roadmap](docs/roadmap/registry_product_roadmap.md)
- [Compliance matrix](docs/compliance/registry_compliance_matrix.md)
- [External Intelligence & Evidence Fabric](docs/architecture/framework_external_intelligence_evidence_fabric.md)
- [Backtest explanation](runtime/reports/backtest/README.md)
- [Secrets security](secrets/README.md)

## Live compatibility

```text
execution_allowed=false
LIVE_ORDER_BLOCKED
```


