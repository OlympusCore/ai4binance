# Coverage Diff Plan — 90% Gate Recovery

Current full quality run:

```text
Ruff: passed
MyPy: passed
Pytest: 886 passed
Coverage: 87.69%
Required: 90%
Total statements: 19176
Missed statements: 1717
Branches: 5830
Partial branches: 1264
```

This is a test-coverage shortfall, not a trading-readiness failure. Do not lower
the gate and do not soften fail-closed trading checks.

Approximate recovery target: cover about 450 currently missed statements or
equivalent branch outcomes, then rerun the full gate. Prefer deterministic
validation, parsing, and fail-closed branches over broad snapshot-style tests.

Work in small reviewable diffs. Do not lower `fail_under = 90`, do not exclude
low-coverage modules, and do not mark generated artifacts as covered by tests.

Coverage math: reaching 90% requires reducing missed executable statements by
roughly 440 to 460 effective statement equivalents at the current code size.
New test files are fine, but avoid adding production code in the same diff unless
the test exposes a real bug.

## Gate Baseline

Run the same command for every final measurement:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File Scripts\quality.ps1
```

Use `--no-cov` only for targeted development checks. The final answer for a
coverage diff must quote the full gate's printed coverage percentage, not just
the process exit code.

## Diff 1 — CLI Branch Coverage

Targets:

- `tests/test_cli.py`
- `tests/test_objective_portfolio_phase.py`
- `src/ai4binance/cli/*`

Add tests for:

- `crew-plan --symbol ETHUSDT` override.
- `second-brain --llm` with unavailable loopback provider.
- invalid `--symbol` fallback on `validate-research`.
- `sync-validation-data` serialization using a monkeypatched ingestor/revision
  builder seam.

Expected impact: covers high-miss CLI branches around lines 297-352 and 325-470.
This should include the new RAG and BTCUSDT revision command branches without
touching live execution.

Detailed checks:

- Parser: slash command normalization and invalid symbol/date rejection.
- Status: scanner unknown subject, empty approvals queue, portfolio fallback.
- Research: `validate-research` success with fake archive, failed archive,
  `crew-plan` symbol override, `second-brain --llm` unavailable provider,
  `sync-validation-data` with monkeypatched ingestor/revision builder.
- Runtime: `runtime-daemon --max-cycles 0` rejection and supervisor failure path
  with injected runtime cycle.
- Voice: private-state wait failure and local session rejection.

Target lift: about 0.25 to 0.45 percentage points.

Current split-module hotspots from the full gate:

```text
cli/accounting.py: 47%
cli/parser.py: 58%
cli/status.py: 63%
cli/voice.py: 24%
```

These are good early coverage targets because they are mostly deterministic
branch/fallback tests and do not require network calls.

Acceptance checks:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_cli.py tests\test_objective_portfolio_phase.py --no-cov -q
.\.venv\Scripts\python.exe -m ruff check src\ai4binance\cli.py src\ai4binance\cli tests\test_cli.py tests\test_objective_portfolio_phase.py
.\.venv\Scripts\python.exe -m mypy src\ai4binance\cli.py src\ai4binance\cli
```

## Diff 2 — RAG / Second Brain Branches

Target: `tests/test_rag_second_brain.py`

Add tests for:

- empty query rejection.
- invalid limit rejection.
- escaped RAG root rejection.
- missing allowed roots producing `RAG index has no approved fragments`.
- non-loopback llama.cpp URL rejection and empty provider response.

Expected impact: raises `src/ai4binance/rag.py` toward 95%+.

Target lift: about 0.10 to 0.20 percentage points.

Acceptance checks:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_rag_second_brain.py --no-cov -q
.\.venv\Scripts\python.exe -m ruff check src\ai4binance\rag.py tests\test_rag_second_brain.py
.\.venv\Scripts\python.exe -m mypy src\ai4binance\rag.py
```

## Diff 3 — Binance Vision Edge Cases

Target: `tests/test_binance_vision.py`

Add tests for:

- non-allowlisted symbol rejection.
- archive symbol/timeframe mismatch rejection.
- invalid ZIP.
- archive with multiple CSV files.
- oversized network response guard with injected fetch.

Expected impact: covers guarded ingestion branches without network calls.
The `sync-validation-data` command must remain monkeypatched in coverage tests;
real Binance Vision sync belongs to explicit operator runs only.

Target lift: about 0.15 to 0.30 percentage points.

## Diff 3.5 — Dataset Revision Branches

Target: `tests/test_dataset_revision.py`

Add tests for:

- missing timeframe manifest;
- mismatched manifest symbol;
- empty timeframe sequence;
- revision warning aggregation for gaps;
- deterministic revision ID under stable manifest hashes.

Target lift: about 0.10 to 0.20 percentage points.

Acceptance checks for Diff 3 and 3.5:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_binance_vision.py tests\test_dataset_revision.py --no-cov -q
.\.venv\Scripts\python.exe -m ruff check src\ai4binance\data tests\test_binance_vision.py tests\test_dataset_revision.py
.\.venv\Scripts\python.exe -m mypy src\ai4binance\data
```

## Diff 4 — Accounting / Portfolio Hotspots

Targets:

- `tests/test_accounting_collectors.py`
- `tests/test_accounting_records.py`
- `tests/test_portfolio_*.py`

Add focused tests for validation-only branches in low-coverage files from the
latest report:

- `accounting/collectors.py`
- `account/account_snapshot.py`
- `portfolio/cost_basis.py`
- `portfolio/current_holding_review.py`
- `portfolio/futures.py`
- `portfolio/holding_opportunity.py`

Expected impact: largest route to recover the missing ~2.23 percentage points.

Prioritize in this order:

1. `portfolio/current_holding_review.py`
2. `portfolio/holding_opportunity.py`
3. `portfolio/cost_basis.py`
4. `accounting/collectors.py`
5. `account/account_snapshot.py`
6. `portfolio/futures.py`

Add tests for constructor validation, stale/missing evidence branches,
malformed-file branches, blocker aggregation, and secret-safe degraded payloads.

Target lift: about 1.10 to 1.60 percentage points.

Acceptance checks:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_accounting_collectors.py tests\test_accounting_records.py tests\test_cost_basis.py tests\test_holding_opportunity.py tests\test_inventory_rotation.py --no-cov -q
.\.venv\Scripts\python.exe -m ruff check src\ai4binance\account src\ai4binance\accounting src\ai4binance\portfolio tests\test_accounting_collectors.py tests\test_accounting_records.py tests\test_cost_basis.py tests\test_holding_opportunity.py tests\test_inventory_rotation.py
.\.venv\Scripts\python.exe -m mypy src\ai4binance\account src\ai4binance\accounting src\ai4binance\portfolio
```

## Diff 4.5 — Governance / Funding / Universe Low-Coverage Branches

Targets:

- `tests/test_crew_governance.py`
- `tests/test_governance_hardening.py`
- `tests/test_universe_*.py`
- `tests/test_investment_management.py`

Add tests for:

- Crew contract rejects `emits_signal_opportunity` without role permission;
- funding plan invalid limits and insufficient liquidity branches;
- spot/futures universe reject malformed symbols and missing quote data;
- investment-management degraded read-only branches.

Target lift: about 0.35 to 0.55 percentage points.

## Diff 4.75 — Exchange / Execution Error Branches

Targets:

- `tests/test_exchange_transport.py`
- `tests/test_exchange_private.py` if added
- `tests/test_paper_execution.py`
- `tests/test_paper_recovery_risk_flow.py`

Add tests for:

- timeout/retry exhaustion redaction;
- private reader bad response shape;
- paper order invalid transition branches;
- recovery quarantine malformed ledger rows.

Target lift: about 0.30 to 0.50 percentage points.

Final expected cumulative lift:

```text
Diff 1:    +0.25 to +0.45
Diff 2:    +0.10 to +0.20
Diff 3:    +0.15 to +0.30
Diff 3.5:  +0.10 to +0.20
Diff 4:    +1.10 to +1.60
Diff 4.5:  +0.35 to +0.55
Diff 4.75: +0.30 to +0.50
Total:     +2.35 to +3.80 percentage points
```

That gives buffer above 90% without weakening gates.

## Diff 5 — Coverage Guard Workflow

Run sequence after each diff:

```powershell
.\.venv\Scripts\python.exe -m pytest <changed-test-files> --no-cov -q
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m mypy src tests
powershell.exe -NoProfile -ExecutionPolicy Bypass -File Scripts\quality.ps1
```

Stop after any failing targeted test and fix only that failure class before
continuing. The full quality gate can remain red only for the known coverage
shortfall until the final coverage diff lands.

Completion condition:

```text
Coverage >= 90.00%
Ruff passed
MyPy passed
Pytest passed
Bandit passed if quality script reaches security gate
LIVE_ORDER_BLOCKED unchanged
```
