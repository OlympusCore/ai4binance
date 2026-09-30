# Local dashboard installation

This directory contains the tracked dashboard source bundle. Windows operation
templates are owned by `scripts/local_dashboard/`. The `.in` suffix marks
packaging templates; their content remains subject to language ownership and
repository validation. Run `scripts/deploy_local_dashboard.ps1`
for a dry-run or add `-Apply`
to build and copy the deterministic deployment into `runtime/dashboard`.
Deployment preserves machine-specific configuration, health, logs, and the
private browser profile, and writes `runtime/dashboard/source-manifest.json`
with source and deployment SHA-256 records.

## Command center presentation

`frontend/src/command_center.ts` owns the incremental human-interface adapter;
`frontend/src/dashboard_shell.ts` owns the navigation and labelled design preview.
The HTML source contains presentation markup and CSS only.
`frontend/src/command_center.css` extends the existing semantic tokens. Packaging
requires an existing Node.js runtime with `node:module.stripTypeScriptTypes`
(validated with Node 24). No frontend framework or runtime dependency is added.
The packaging receipt includes all interface source hashes. The Python builder
only composes assets at an explicit marker; navigation, refresh scheduling and
presentation behavior are authored in TypeScript. Strict no-emit type checking
runs through `scripts/check_dashboard_types.py` and the canonical quality profile's
dashboard test mapping. It uses an existing TypeScript compiler (the installed
editor compiler, or `AI4BINANCE_TYPESCRIPT_PATH` pointing to `typescript.js`).
No package installation or compiler download is performed. Compiler absence fails
validation. `frontend/tsconfig.json` is the reproducible checking configuration.

Overview shows source-reported health, OHLCV freshness and readiness separately,
high-priority findings, and the background paper observation. An expired decision
source remains prominently `STALE`, even while market data is current. Missing
counts, percentages and observations remain unavailable; a reported zero is zero.
Decision workbench selects bounded historical research receipts independently of
the market workspace and shows reported stages, vetoes and canonical governance.
It links each reference into Evidence & audit with cycle, snapshot and SHA-256.
Validation and classified supporting/counter/conflicting evidence remain explicitly
`DATA_UNAVAILABLE` when the producer does not supply them. Audit health is
never substituted for decision governance. Evidence & audit reuses source
metadata and AutoAuditLoop; System & data retains the original operational view.
All existing domain pages remain available in their original relative order.
Overview separates the background observation from the selected historical
receipt. Finding-specific evidence navigation retains the finding identity;
disappearing findings are explicitly unavailable instead of silently replaced.

Market selection is shared between Opportunities and VirtualMarket. Symbol
choices and timeframe filters are retained independently per market; available timeframes come from
the existing market payload. These filters do not change the background decision
or join independent snapshots. No additional polling loop or market retrieval is added.
English/Turkish labels use an explicit message dictionary and a language selector.
UI context remains in memory, with no private payload persisted to browser storage.

The hierarchy is summary, reported blocker, source evidence, then technical
provenance. Status is always textual; unknown values are never formatted as zero.
Keyboard users can skip navigation, focus table scroll regions, and use native
selects/details. Expanded details are associated with the page and their labels.
Tables share search, exact signed-decimal sorting, 25-row pagination and retained in-memory
context. Shared tokens, visible focus, reduced-motion support, bounded table scrolling and
responsive status cards support accessibility; they do not establish WCAG certification.
The safety strip remains visible in the document at every supported width.
Resident deployment and restart are separate from source validation.

## Read-only decision projection

`/api/state.decision_history` projects the existing configured audit directory's
`research_events.jsonl` and `runtime_research_events.chained.jsonl`. Reads are
limited to 100 recent lines and 4 MB per journal. The dashboard projects the
newest 32 decisions that fit a 512 KB response budget; the complete journals
remain available as audit evidence. An individual newest receipt above this
budget is reported as `DASHBOARD_RECEIPT_TOO_LARGE` rather than silently omitted.
The loopback server sends response bodies in bounded 32 KB writes so large
read-only snapshots complete within the client's finite read timeout.
Paths must resolve inside repository `runtime/`. The adapter never repairs,
creates or appends journals. A changing journal is reported as `SOURCE_CHANGED`.
CanonicalCycleEnvelope validates reference kinds, unique identities, cycle and
snapshot binding, immutable step order and safety. The semantic receipt hash
and outer event/snapshot identity and timestamps must match. Conflicting duplicate
decision identities invalidate both observations. Malformed entries are visible
findings rather than silently accepted decisions.

A matching receipt hash proves internal receipt consistency only. Full journal
chain authenticity is **not verified** by this bounded view. Embedded explanation
bodies are checked against their exact reference identity, cycle, snapshot and
SHA-256 before safe fields are exposed. They report `PAYLOAD_HASH_MATCH` or
`PAYLOAD_INVALID`. References with no resolvable body show `PAYLOAD_UNAVAILABLE`;
reported stage completion does not grant risk approval. The compact producer
does not provide a market identifier or a standalone validation result: neither
is inferred from the selected workspace. Historical records older than 180 seconds
are visibly stale and remain inspection-only. No new decision, risk or audit engine
is introduced.

The existing research producer may embed bounded decision, governance, audit and
virtual-plan explanation bodies in its existing audit event. It excludes full
snapshots, wallet state and agent calculation metadata, preserves the compact
audit budget, and never truncates a hash-bound body. Bodies that do not fit remain
unavailable. Old records are not rewritten or reconstructed. Risk payloads,
standalone validation and classified supporting/counter evidence remain missing
unless their canonical producer supplies them. The dashboard follows no arbitrary
file paths. Historical authenticity and risk approval are not inferred from an
internally matching hash.

Opportunity eligibility is projected through the existing canonical predicate;
the browser only consumes its `measurable_plan` result. Net virtual P&L is supplied
by the canonical wallet projection. Missing numeric values remain unavailable,
and table cells retain raw decimal sorting keys where supplied. The client has
no independent leverage, price-plan or portfolio-accounting rules.

Local-state reads distinguish unauthorized, timeout, HTTP, invalid-payload and
connection failures. Failed reads withhold previous state and offer a bounded,
single-flight retry while preserving the existing 30-second polling cadence.

## Acceptance and deployment

Focused tests cover missing/zero, stale/future, invalid hashes, missing/cross-cycle
references, duplicate/conflicting IDs, oversized journals, DOM value types,
poll scheduling and strict TypeScript. `tests/dashboard_browser_fixture.py` serves
an explicitly labelled, loopback-only test fixture on port 8766. All action
endpoints are disabled in that fixture; it never reads live account or market data.
Use it for decision-to-evidence, keyboard, responsive and table-flow acceptance.
Its disposable test build records render count and duration in DOM data attributes.

Run `scripts/quality.ps1 -Profile standard` for the mapped acceptance scope.
Then run `scripts/deploy_local_dashboard.ps1` to prepare a dry-run receipt.
The deployer rejects source drift during packaging and records source/output
hashes, changed files, and whether applying requires restart. `BUILT_NOT_DEPLOYED`
is not a running-package claim. Only an authorized `-Apply` copies the package;
the existing scheduled task's process must then be restarted under its own
authorization. `/health.loaded_server_sha256` identifies the server bytes loaded
at listener creation; compare with the accepted receipt before claiming runtime
convergence. Existing configuration, logs and browser profile are preserved.

`frontend/src/dashboard_icons.ts` owns the typed icon renderer and the ten
Lucide 1.17.0 icon geometries used by the dashboard. Its ISC notice is retained
in the emitted `app.js`. Packaging needs no compressed JavaScript vendor bundle
or separate icon-library request. Source migration evidence is retained under
`runtime/artifacts/repository_validation/dashboard_icons/`; archived input is
never read by the build or the dashboard server.

Open http://127.0.0.1:8765/ or use the AI4Binance Dashboard desktop shortcut.

The AI4BINANCE-Dashboard scheduled task starts at this user's Windows sign-in.
It runs with limited privileges, without a time limit, including on battery.
The guardian checks the local server and dedicated Edge application every ten
seconds. A failed guardian is retried by Task Scheduler after one minute.
Closing the application window causes it to reopen. Sleep, shutdown, and
sign-out suspend or stop interactive operation; the application resumes at
the next sign-in. No power-management settings were changed.

The local view refreshes every thirty seconds. Current account, runtime,
virtual runtime, research progress, and discovery summaries use existing
canonical local files. Stale or invalid data is withheld. Balances are masked
by default. Missing opportunity price packages, radar/news feeds, virtual
wallet ledgers, and development-idea feeds remain explicitly unavailable.
The separate design-example mode contains synthetic demonstration data.

The Recommendations and Kaizen pages include Refresh summary and automatically
request a refresh for missing or stale learning summaries. Refresh uses the existing
read-only runtime analysis pipeline, including its canonical evidence providers.
Unchanged summaries are persisted again after a day only following successful
analysis. Refresh does not establish new evidence or measured improvement.
Learning refresh is single-flight, throttled to once per minute, and limited to
three minutes. Failures remain visible; private runtime output is discarded.

The Opportunities and VirtualMarket pages share a coin selector, quality table,
manual refresh, separate Spot (5m/15m/1h/4h/1d) and USD-M Futures (5m/15m/1h)
observations, and historical/potential performance. The canonical market-history
service refreshes the full eligible Spot and USD-M Futures market snapshots on
its configured five-minute cadence. VirtualMarket projects that collector's
freshness, universe coverage, progress, and blockers. Missing or old selected
coin scans refresh automatically while these pages are open. A selected-coin
refresh reuses verified collector windows, then fills missing windows through
bounded public Binance kline reads.
The monitor stores checksum-bound source windows and tamper-evident observations
under runtime/artifacts/opportunity-radar/monitor, separated by market and symbol.
It reuses the canonical radar, derivatives advisor, quality gate, lifecycle ledger,
and post-hoc outcome evaluator. It does not grant execution authority.

The first observation is immutable; repeat polling cannot reset its date or
reference price. Performance uses three subsequent closed bars and reports MFE,
MAE, target/stop ordering and R only where original evidence supports them.
Missing legacy price/timestamp records cannot be reconstructed as proven results.
Fees, funding, slippage and actual trading P&L are excluded. Futures entry, stop,
targets and leverage remain unavailable when the canonical advisor supplies none.
The view shows the latest 500 records; ledgers are retained and refresh fails
explicitly at the 16 MB ledger boundary until archival is provided. Market refresh
is single-flight, throttled for 60 seconds, and bounded by a 180-second worker deadline.

On VirtualMarket, a Spot refresh also places the selected eligible coin at the
front of the resident canonical simulation cycle. That cycle may autonomously
create and manage a virtual position only when deterministic data, risk,
validation, OOS, governance, and DGE gates produce a complete virtual order.
Blocked candidates remain observations with their reasons; refresh never turns a
blocked candidate into a trade. Futures observations are refreshed and analyzed,
but autonomous Futures position lifecycle remains visibly blocked until canonical
mark-price and funding context is connected.

The wallet section reads the verified append-only VirtualWalletJournal. It shows
independent Spot/Futures equity and available USDT, net virtual P&L, daily,
weekly, and monthly equity changes, current position/risk/cost fields, and a
bounded expandable movement table. A period shorter than the wallet's lifetime
is marked as since inception. These values are simulated account results only.

The server accepts only local loopback traffic. Its state-changing endpoints
starts fixed, bounded runs: Web Radar, GitHub Radar, News Radar, or learning
summary refresh, or a selected market/coin scan. These runs use canonical read-only retrieval with no inherited
GitHub token. They cannot submit orders or alter trading permissions. No
credentials are stored in this installation. Browser assets are served locally.

To intentionally suspend automatic operation, open Windows Task Scheduler,
disable AI4BINANCE-Dashboard, and end that task. To resume, enable and run
the same task. The desktop shortcut also launches the guardian; do not use
it while automatic recovery is intentionally suspended.

Configuration is in config.json; startup configuration is in installation.json.
Operational events and process identifiers are in guardian.log and health.json.
Validation evidence is in validation.json and the two recovery-test files.
No reboot was performed during installation validation.
