# Local dashboard installation

This directory is the tracked canonical source bundle. Python and PowerShell
deployment templates use an `.in` suffix so they are not imported or treated
as repository-owned executable modules. Run `scripts/deploy_local_dashboard.ps1`
for a dry-run or add `-Apply`
to build and copy the deterministic deployment into `runtime/dashboard`.
Deployment preserves machine-specific configuration, health, logs, and the
private browser profile, and writes `runtime/dashboard/source-manifest.json`
with source and deployment SHA-256 records.

`lucide.js.gz` vendors Lucide 1.17.0 under the ISC license; deployment expands
it to `lucide.js`, whose preserved header contains the license notice.

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
