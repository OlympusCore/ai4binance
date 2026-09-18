---
document_id: AI4B-CLI-IFC-001
title: AI4BINANCE CLI Command Contract
document_type: INTERFACE_CONTRACT
version: 1.0.3
status: ACTIVE
owner: Enterprise Knowledge Governance
authority_level: NORMATIVE
authority_layer: L3_CANONICAL_CONTRACTS_SCHEMAS
authority_scope: cli_command
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
canonical_path: docs/contracts/interface_contract_cli_command.md
machine_enforceable: true
audit_required: true
classification: INTERNAL
---

# AI4Binance CLI

## ELI10

This document is a glossary of AI4BINANCE commands that can be written in the terminal.
Each command's name, purpose, and safe operating area are described here; when a
new command is added, this list must be updated.


## Purpose

`AI4Binance CLI` is the report-oriented and
fail-closed command interface for AI4BINANCE EnterpriseAI vNext. Commands are used
for market research, validation, governance, portfolio visibility, runtime
control, accounting collection, and Spot live-trading preview flows.

Default security state remains unchanged:

- Weak, incomplete, or unverified evidence returns `NO_TRADE`.
- Work without completed OOS and risk approval remains `RESEARCH_ONLY`.
- When the live order blocking is not completed, `LIVE_ORDER_BLOCKED`.
- CLI, LLM or a consultant agent is not the ultimate command authority.

## Maintenance Rule

When a CLI command is created, updated, deleted, or given an alias, this file must
be updated in the same change set. The primary source for the command catalog is
the `COMMAND_SPECS` list in `src/ai4binance/cli/commands.py`. The command table in
this document and `COMMAND_SPECS` must stay synchronized; `tests/test_cli.py`
checks this rule at least at command-name and catalog-summary level.

## Running

```powershell
.\.venv\Scripts\python.exe -m ai4binance.cli commands --format text
.\.venv\Scripts\python.exe -m ai4binance.cli status --format json
```

### Continuous Futures Multi-Timeframe Research

`src/ai4binance/cli/futures_multitf.py` owns the bounded continuous Futures
research cycle and its `once` and `daemon` entry points. Replay datasets are
written below `runtime/data/datasets/futures/multitf/`; validation and tuning
evidence remain under `runtime/artifacts/validation/`. This command is
research-only and cannot grant execution, promotion, or live-order authority.

### Standalone Futures OOS Publication

`src/ai4binance/cli/futures_oos.py` provides the standalone research-only
`python -m ai4binance.cli.futures_oos` entry point. It is intentionally outside
the primary `COMMAND_SPECS` dispatcher because publication requires an explicit
repository root, checksum-bound replay artifact, directional setup, and
walk-forward window sizes.

The entry point accepts replay files only from the repository-local
`runtime/data/datasets/futures/` boundary. It verifies an exact clean Git revision
before and after validation, rejects repository or dataset drift, and writes
immutable evidence only below `runtime/artifacts/validation/futures_oos/`.
Tests in `tests/test_futures_replay.py`, `tests/test_futures_oos.py`, and
`tests/test_futures_walk_forward.py` cover the CLI, evidence, and validation
boundaries.

Publication is not promotion or execution authority. All successful and
blocked outputs retain `execution_allowed=false`, `RESEARCH_ONLY`, and
`LIVE_ORDER_BLOCKED`.

General options:

| Option | Scope |
| --- | --- |
| `--format json\|text` | Produces JSON or short text output for supported commands. |
| `--confirm-live` | Marks only the CLI confirmation prompt; does not send the command alone. |
| `--symbol` | Changes the research or validation symbol in a command-bounded way. |
| `subject` | Optional subject field for slash commands, for example: `/scan spot`. |

## Command Scopes

| Group | Scope |
| --- | --- |
| `core` | Safe state summary and command help. |
| `governance` | OEK, QAQC, agent, skill and repo hygiene checks. |
| `market-research` | Spot research using public data and local evidence search. |
| `validation` | Validation data, backtest summary, backtest runtime economics, and governed crew plans. |
| `portfolio` | Portfolio, opportunity, manual action, and symbol-scan visibility. |
| `runtime` | Read-only runtime and voice loops. |
| `accounting` | Read-only accounting snapshot, reconcile, status, and UI report. |
| `live-spot` | Spot order preview and fail-closed placement with a fully approved preview hash. |

## Command Catalog

<!-- CLI_COMMAND_TABLE_START -->
| Command | Group | Alias | Catalog summary | Scope |
| --- | --- | --- | --- | --- |
| `status` | `core` | `summary` | Print the fail-closed default trading status. | Reports the default trading status, time zones, and the canonical virtual-market gate envelope used by `virtual-market-once`; reasons live gates are closed remain visible. |
| `commands` | `core` | `help` | List command groups, aliases, and examples. | Lists available commands with groups, aliases, and examples. |
| `system-report` | `core` | - | Build a secret-safe whole-system operator report. | Collects QAQC, OEK, Lean, runtime, validation, opportunity, accounting, and skill-discovery status in one report. |
| `auto-audit-once` | `core` | `auto-audit` | Run one report-only auto-audit cycle with optional local Qwen review. | Runs one auto-audit cycle; reports the system report, blocker trend and optional local Qwen advisory evidence. |
| `auto-audit-daemon` | `core` | - | Run bounded report-only auto-audit cycles while the session is active. | Executes bounded report-only auto-audit cycles during an active session. |
| `security-weekly-deep-audit` | `core` | `security-deep-audit` | Run the report-only EAACIE weekly deep security audit with SBOM, CVE evidence, MFA, restore, WORM and scheduler checks. | SBOM-lite, CVE/advisory evidence, MFA provider attestation, backup/restore proof, external immutable/WORM proof and weekly scheduler CLI surface are checked in report-only mode; generates a blocker if evidence is missing. |
| `ykb-report` | `core` | `ykb-brief` | Build a YKB-friendly executive brief from auto-audit, DGE, opportunities and financial context. | Converts the auto-audit, DGE, opportunity radar and current financial context summary into a YKB-friendly decision package. `--approve-blocker-order` only records approval for blocker-resolution order; it grants no risk, OOS or live authority. |
| `vnext-gap-audit` | `core` | `v3next-audit`, `gap-audit` | Map the EnterpriseAI vNext v1.1 target architecture to local evidence. | Matches vNext v1.1 targets with local file/test evidence; reports missing controls as diff plan input, does not perform file or command operations. |
| `opportunity-recovery-radar` | `portfolio` | `recovery-radar`, `candidate-ladder` | Build a recovery-mode candidate ladder from inventory, range and opportunity evidence. | Full-coin inventory, technical support/resistance range, trend/regime, setup radars and validation evidence are combined to generate a sell/rebuy review candidate ladder; `--range-low/--range-high` is only manual override, does not grant order/live authority. |
| `dge-rules` | `governance` | - | List centralized DGE rule metadata without changing policy. | List centralized DGE rule metadata without changing policy. |
| `dge-replay` | `governance` | - | Replay a persisted DGE decision record by decision id. | Recomputes a persisted DGE replay record by decision id and returns MATCH/MISMATCH/NON_REPRODUCIBLE; it does not create execution authority. |
| `dge-shadow-rules` | `governance` | - | Show DGE shadow-rule mode and live-safe promotion blockers. | Reports shadow-rule mode and rule promotion blockers; no active policy mutation or live permissions. |
| `agents` | `governance` | - | List governed advisory agents and live-authority counts. | Makes the advisory agent catalog and live-authority counts visible. |
| `agentic-skills` | `governance` | - | Recommend a governed workflow pattern for a bounded task. | Recommends an appropriate governed agentic workflow pattern for bounded tasks. |
| `skills-audit` | `governance` | - | Audit repo-local Agent Skills without installing or executing them. | Audits repo-local skills without installing or running them. |
| `skill-discovery-once` | `governance` | - | Run one quarantine-first external Agent Skill discovery cycle. | Researches external skill candidates in one quarantine-first cycle. |
| `skill-discovery-daemon` | `governance` | - | Run continuous skill discovery while the computer session is active. | Runs the continuous skill discovery loop while the session is active. |
| `skill-discovery-status` | `governance` | - | Read the last continuous skill discovery state. | Reads the last continuous skill discovery status. |
| `privacy-boundary` | `governance` | - | Scan for local profile details copied outside docs/archive/reference_local_computer_profile.md. | Reports local/personal detail risks that spill outside `docs/archive/reference_local_computer_profile.md`. |
| `enterprise-intake` | `governance` | - | Convert a raw prompt file into a General Manager summary-only directive. | Converts a raw prompt file into a summary-only directive for the General Manager. |
| `quality-system-audit` | `governance` | `qaqc-audit` | Run the QAQC enterprise system audit. | Runs the QAQC system audit in report-only mode. |
| `agent-stack-audit` | `governance` | - | Audit the governed modern AI agent stack. | Audits RAG, context, memory, tools, MCP, skills, hooks, subagents, orchestration, eval, and missing governance/security/audit/provenance layers fail-closed. |
| `oek-gap-analysis` | `governance` | `oek-audit` | Check an agent, skill, workflow, or config change against the OEK. | Audits an agent, skill, workflow or config change against the OEK. |
| `repository-cleanup-audit` | `governance` | `cleanup-audit` | Run the report-only repository cleanup and stability audit. | Reports repository cleanup, simplicity, and stability risks without deleting sources. |
| `virtual-market-paper-soak` | `validation` | `paper-soak-readiness` | Build a fail-closed virtual-market paper-soak readiness artifact. | Builds a local paper-soak readiness artifact for the virtual-market research surface with explicit user-approval and live-order blockers; no execution authority is granted. |
| `virtual-market-retrieval-eval` | `validation` | - | Evaluate virtual-market retrieval evidence quality. | Evaluates a local second-brain retrieval query for virtual-market governance evidence and writes a fail-closed retrieval-eval artifact. |
| `lean-governance` | `governance` | - | Review operational excellence guardrails. | Reviews operational excellence guardrails. |
| `qaqc-agent` | `governance` | - | Show the QAQC-Agent governance review. | Displays the QAQC-Agent governance review. |
| `analyze-public` | `market-research` | - | Acquire public Spot data and produce a deterministic NO_TRADE analysis. | Produces deterministic analysis from public Spot data without order authority. |
| `research-public` | `market-research` | `research` | Run the safe public research workflow. | Runs the safe public research flow. |
| `archive-public` | `market-research` | - | Archive public market candles without wallet contamination. | Archives public candle data without wallet contamination. |
| `whale-fusion-research` | `market-research` | - | Run whale-fusion research with provider blockers surfaced. | Runs whale-fusion research while clearly reporting provider gaps and blockers. |
| `external-intel` | `market-research` | `eief` | Run the report-only External Intelligence & Evidence Fabric MVP with fail-closed radar outputs. | Runs the EIEF MVP report that returns DATA_UNAVAILABLE when X, News, Reddit, Telegram, Security, or Regulatory providers are unavailable and connects GitHub Radar through an adapter. |
| `external-intel-universe` | `market-research` | `eief-universe` | Show the EIEF opportunity universe classification smoke snapshot. | Shows the stablecoin-base, wrapped-asset, and leveraged-asset exclusion contract as a smoke snapshot. |
| `external-intel-open-web` | `market-research` | `open-web-radar` | Retrieve allowlisted public web evidence without credentialed search or cloud LLM tokens. | Converts allowlisted RSS/Atom and seed URL sources into bounded, robots-aware, fail-closed EIEF evidence. |
| `second-brain` | `market-research` | - | Search the local second-brain evidence index. | Searches the local second-brain evidence index. |
| `sync-validation-data` | `validation` | - | Sync Binance Vision validation data for the validation symbol. | Synchronizes Binance Vision data for the validation symbol. |
| `validate-research` | `validation` | `validate` | Run validation research gates. | Passes research candidates through validation gates. |
| `validation-summary` | `validation` | `backtests` | Summarize persisted validation run cards. | Summarizes persisted validation/backtest run cards. |
| `backtest-runtime-economics` | `validation` | - | Review local backtest runtime economics and CUDA readiness. | Reviews a local synthetic backtest benchmark and current CUDA request state without granting execution authority. |
| `backtest-results` | `validation` | - | Compatibility alias for validation-summary output. | Provides validation-summary output compatible with legacy usage. |
| `crew-plan` | `validation` | - | Show the governed validation crew plan. | Shows the governed validation crew plan. |
| `portfolio` | `portfolio` | `/portfolio` | Show read-only portfolio/account snapshot status. | Reports read-only portfolio and account snapshot status. |
| `opportunities` | `portfolio` | `/opportunities`, `ops` | Show visible research opportunities and execution blockers. | Reports the opportunity radar as active/inactive; if a research item exists, exit code 0 is returned while execution blockers remain visible. |
| `manual-actions` | `portfolio` | `/manual-actions` | Show pending manual actions. | Lists pending manual actions. |
| `approvals` | `portfolio` | `/approvals` | Show recorded manual approvals. | Shows recorded manual approvals. |
| `scan-spot` | `portfolio` | `scan` subject `spot`, `/scan spot` | Scan configured Spot watch symbols with explicit blockers. | Scans configured Spot watch symbols with blockers. |
| `scan-futures` | `portfolio` | `scan` subject `futures`, `/scan futures` | Scan configured USD-M Futures watch symbols as research-only evidence. | Scans configured USD-M Futures watch symbols as research-only evidence. |
| `scan-all` | `portfolio` | `scan` subject `all`, `/scan all` | Scan configured Spot and USD-M Futures watch symbols. | Scans Spot and USD-M Futures watchlists together. |
| `runtime-once` | `runtime` | - | Run one read-only runtime cycle. | Runs one read-only runtime cycle. |
| `runtime-research-refresh-once` | `runtime` | `runtime-refresh` | Refresh internet research feeds, run runtime-once, and publish a trace-validation report. | Refreshes internet feeds, runs `runtime-once` and writes a trace-validation report for URL traceability. |
| `runtime-daemon` | `runtime` | - | Run the read-only runtime daemon. | Read-only runtime daemon. |
| `virtual-market-once` | `runtime` | `virtual-runtime-once`, `virtual-runtime` | Run one bounded virtual-market simulation probe. | Reports the canonical virtual-market boundary, automation mode, and live block without routing to exchange or live order paths; it shares the same canonical virtual-market gate payload as `status`. |
| `virtual-market-soak` | `runtime` | `virtual-runtime-soak` | Write a bounded virtual-market boundary-soak artifact. | Writes a small local soak artifact that samples the canonical virtual-market gate payload multiple times and preserves `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED`. |
| `voice-once` | `runtime` | - | Run one voice assistant cycle. | Runs one voice assistant cycle. |
| `voice-daemon` | `runtime` | - | Run the voice assistant daemon. | Voice assistant daemon. |
| `accounting-collect-once` | `accounting` | - | Collect one read-only accounting REST snapshot. | Collects one read-only accounting REST snapshot. |
| `accounting-collect-daemon` | `accounting` | - | Run the read-only accounting REST daemon. | Runs the read-only accounting REST daemon. |
| `accounting-ws-once` | `accounting` | - | Collect one read-only accounting WebSocket snapshot. | Collects one read-only accounting WebSocket snapshot. |
| `accounting-ws-daemon` | `accounting` | - | Run the read-only accounting WebSocket daemon. | Runs the read-only accounting WebSocket daemon. |
| `accounting-reconcile-once` | `accounting` | - | Run one accounting reconciliation pass. | Runs one accounting reconciliation pass. |
| `accounting-ui-report` | `accounting` | - | Build the local accounting UI report. | Builds the local accounting UI report. |
| `accounting-status` | `accounting` | - | Show accounting file freshness and reconciliation status. | Displays accounting file freshness and reconciliation status. |
| `live-preview-spot` | `live-spot` | `live-preview` | Create a Spot order preview hash without authority. | Creates a Spot order preview hash without granting order authority. |
| `live-place-spot` | `live-spot` | `live-place` | Place an exact approved Spot preview only after all live gates pass. | Advances to the Spot order layer only with an approved preview hash after every live gate passes. |
<!-- CLI_COMMAND_TABLE_END -->

## Runtime Feed Security Note

The `runtime-research-refresh-once` command refreshes internet feeds while staying fail-closed
and applies traceable security boundaries:

- Feed sources are restricted by a fixed allowlist:
  `https://www.coindesk.com/arc/outboundfeeds/rss/`,
  `https://www.reddit.com/r/CryptoCurrency/new/.rss`,
  `https://github.blog/changelog/feed/`.
- URL validation accepts only credential-free HTTPS sources; URLs containing a
  username or password are rejected.
- Downloaded XML size is bounded by `runtime_context_max_file_bytes`; feed
  refresh is blocked fail-closed when the limit is exceeded.
- XML parsing uses `defusedxml.ElementTree`; RSS (`./channel/item`) and Atom
  (`entry`) formats are supported.
- `source_url` is mandatory for every record; when feed refresh produces a
  blocker, the command result is `BLOCKED` and no runtime/trade authority opens.

## Open Web Radar Security Note

`external-intel-open-web` performs direct source scanning without credentials or
cloud LLM tokens. The default policy
`config/research/open_web_sources.json` dosyasindadir. Yalniz allowlist HTTPS
hostlari kabul is revised; DNS ozel/loopback adresleri, credential iceren URL'ler,
uncontrolled redirects, robots blockers, unexpected content type/encoding, and
size overages are blocked. Full article text is not persisted; bounded
excerpt, metadata, SHA-256 and source URL are appended-only to local evidence record
yazilir.

```powershell
.\.venv\Scripts\python.exe -m ai4binance.cli external-intel-open-web --format json
.\.venv\Scripts\python.exe -m ai4binance.external_intel open-web --seed-url https://github.blog/example/
```

This is not a general search engine: Google/Bing query, X scraping,
credentialed provider, cloud LLM, automatic installation, strategy promotion, or
order authority. Results remain locked at `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED`.

## Virtual Market Gate Note

The `status` and `virtual-market-once` commands share the same canonical
`virtual_market_gate_payload` helper from `src/ai4binance/cli/shared.py`.
Both command surfaces remain fail-closed, `RESEARCH_ONLY`, and
`LIVE_ORDER_BLOCKED`. The shared helper exists only to keep the CLI envelope
consistent across JSON and text output surfaces; it does not grant execution
authority or change promotion policy.

## Backtest Runtime Economics Note

The `backtest-runtime-economics` command reports a local synthetic benchmark of
the backtest engine and the current CUDA request state. It remains
research-only, keeps live eligibility blocked, and surfaces missing
measurements or an unavailable CUDA path as blockers rather than auto-switching
authority or execution mode.

## Opportunity Radar V2 Note

The `opportunities` and `scan-*` commands separate opportunity visibility from
execution eligibility. A candidate may appear as `SETUP_FORMING`,
`CONFIRMATION_PENDING`, `RESEARCH_CANDIDATE`, or `VALIDATION_PENDING` while the
execution boundary remains `NO_TRADE`, `RESEARCH_ONLY`, and
`LIVE_ORDER_BLOCKED`.

Opportunity Radar V2 reports use separate sections for top opportunities,
confirmation-pending setups, developing setups, validation ladder items, and
rejected or lost candidates. Confirmation and validation gaps explain what
evidence is missing; execution blockers explain why no paper or live order
authority exists. Discovery exclusions still remove a candidate from active
opportunity visibility.

## Sinirlar

- `live-preview-spot` sends no order; it only produces a preview and hash evidence.
- `live-place-spot` is governed by the live order lifecycle contract, writes a
  lifecycle journal on submission, and remains `LIVE_ORDER_BLOCKED` until the
  preview hash, promotion evidence, and human approval are aligned.
- Research and Futures sources can be only auxiliary evidence for Spot decisions
  they do not grant execution authority for unverified evidence.
- The `opportunities` command refers to active radar, not trade confirmation. It
  reports that opportunity research is running; `NO_READY_CANDIDATE`,
  `VALIDATION_GATE_REQUIRED`, or similar blockers keep the execution path closed.
- Wallet and inventory information is for reporting and real execution control;
  it must not affect historical backtest integrity.
