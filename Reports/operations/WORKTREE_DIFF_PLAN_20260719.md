# Worktree Diff Plan - 2026-07-19

## ELI10

Bu rapor, buyuk ve daginik worktree degisikliklerinin nasil kucuk parcalara
ayrilacagini anlatir. Amac once gurultuyu azaltmak, sonra kaynak, test ve dokuman
degisikliklerini karistirmadan incelemektir.


## Current Topology

Measured before ignore cleanup:

```text
git status --short --untracked-files=all: 5006 entries
cli.py size: 1453 lines
tracked modified/added core bootstrap files: present
large untracked source/test expansion: present
generated test/runtime artifacts: dominant noise source
```

Measured after ignore cleanup:

```text
git status --short --untracked-files=all: 356 entries
staged added: 16
staged added + unstaged modified: 14
unstaged diff files: 14
untracked paths: 326
generated pytest/runtime/log/state noise: mostly hidden
source, tests, docs and operator scripts: still visible
```

The worktree is not clean, but it is now more readable. The remaining untracked
surface mostly looks like real project evolution rather than disposable output.

Current untracked top-level distribution:

```text
src: 203
tests: 92
Docs: 16
.agents: 5
Scripts: 5
.github/.vscode/Backtest/Opportunities/Secrets: 1 each
```

Current unstaged diff hotspots:

```text
tests/test_cli.py: +398/-1
src/ai4binance/config.py: +289/-3
Docs/ARCHITECTURE.md: +248/-36
Docs/ROADMAP.md: +142/-49
README.md: +167/-14
src/ai4binance/cli.py: +125/-15
src/ai4binance/domain.py: +89/-0
```

Current staged baseline size:

```text
cached files: 30
cached added lines: about 5038
largest staged files:
  Custom_Instructions_Core.md: +2701
  CleanCodes.md: +431
  src/ai4binance/domain.py: +342
  src/ai4binance/schemas.py: +273
  tests/test_schemas.py: +266
```

Large local artifacts verified as ignored:

```text
Logs/runtime_research_events.jsonl: 541,339,905 bytes
Backtest/validation: 45 files / 5,168,467,649 bytes
Artifacts/TestTemp: 4,157 files / 32,210,427 bytes
State/private: 20 files / 66,059,753 bytes
src/ai4binance.egg-info: 6 files / 18,769 bytes
Secrets: 5 files / 2,380 bytes; only Secrets/.gitkeep should remain visible
```

## Noise Classes Hidden By .gitignore

- `.pytest-audit-temp*/`
- `.pytest-money-audit-*/`
- `Artifacts/TestTemp/`
- `Artifacts/accounting-ui/`
- `Artifacts/market-outlook/`
- `Artifacts/validation/`
- `Logs/`
- `Logs/**/*.log`
- `Logs/**/*.jsonl`
- `State/private/`
- `State/*.html`
- `*.egg-info/`, `src/*.egg-info/`, `build/`, `dist/`

Do not commit private state, generated logs, pytest temp output, local package
metadata, or runtime HTML/JSON snapshots unless a specific artifact is promoted
as documentation.

## CLI Split Applied

`src/ai4binance/cli.py` is now a thin dispatcher. The implementation moved into:

- `src/ai4binance/cli/parser.py`
- `src/ai4binance/cli/status.py`
- `src/ai4binance/cli/research.py`
- `src/ai4binance/cli/runtime.py`
- `src/ai4binance/cli/accounting.py`
- `src/ai4binance/cli/voice.py`

`src/ai4binance/cli.py` remains the public dispatcher and sets a narrow
`__path__` so `ai4binance.cli.parser` style submodules are importable without
changing the `ai4binance.cli:main` entry point. Do not add
`src/ai4binance/cli/__init__.py` in this shape; that would shadow the dispatcher
module.

## Commit Slicing Plan

### Diff 1 - Ignore And Worktree Hygiene

Files:

- `.gitignore`
- `Reports/operations/WORKTREE_DIFF_PLAN_20260719.md`

Validation:

```powershell
git status --short --untracked-files=all
git diff --check
git diff --cached --check
```

Expected result: generated temp/runtime state stays hidden, source remains visible.

Current result:

```text
git diff --check: passed
git diff --cached --check: passed
EOF final newline scan on staged/unstaged touched files: passed
```

Do not stage:

- `Logs/**`
- `Backtest/validation/**`
- `Artifacts/TestTemp/**`
- `Artifacts/accounting-ui/**`
- `Artifacts/market-outlook/**`
- `Artifacts/validation/**`
- `State/private/**`
- `src/*.egg-info/**`
- secret files under `Secrets/**` except `Secrets/.gitkeep`

### Diff 2 - CLI Dispatcher Split

Files:

- `src/ai4binance/cli.py`
- `src/ai4binance/cli/parser.py`
- `src/ai4binance/cli/status.py`
- `src/ai4binance/cli/research.py`
- `src/ai4binance/cli/runtime.py`
- `src/ai4binance/cli/accounting.py`
- `src/ai4binance/cli/voice.py`

Validation:

```powershell
.\.venv\Scripts\python.exe -m ruff check src\ai4binance\cli.py src\ai4binance\cli tests\test_cli.py tests\test_objective_portfolio_phase.py
.\.venv\Scripts\python.exe -m mypy src\ai4binance\cli.py src\ai4binance\cli
.\.venv\Scripts\python.exe -m pytest tests\test_cli.py tests\test_objective_portfolio_phase.py --no-cov -q
```

Current targeted result:

```text
Ruff: passed
MyPy: passed
Pytest: 30 passed
```

### Diff 3 - Source/Test Evolution Commit

Files:

- remaining `src/ai4binance/**`
- remaining `tests/**`
- governance and docs files that are not generated output

Validation:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File Scripts\quality.ps1
```

Expected result before coverage repair:

```text
Ruff: pass
MyPy: pass
Pytest assertions: pass
Coverage: below 90 until coverage diff plan is completed
```

Suggested commit message:

```text
feat: establish spot-safe deterministic baseline
```

Keep the commit explicitly framed as `NO_TRADE`/`RESEARCH_ONLY`/
`LIVE_ORDER_BLOCKED` baseline. Do not include real runtime data.

### Diff 4 - Coverage Recovery

Follow `Reports/operations/COVERAGE_DIFF_PLAN_20260719.md`. Keep this separate from the CLI
split so test coverage work is reviewable and does not hide behavior-preserving
module movement.

Suggested final commit order:

```text
chore: clean git hygiene and ignore runtime artifacts
feat: establish spot-safe deterministic baseline
refactor: split CLI command surfaces
feat: add read-only runtime and private-state boundary
feat: add validation and OOS research pipeline
feat: add advisory-only portfolio and derivatives context
docs: sync compliance and runtime evidence docs
test: raise repository coverage above 90 percent
```

## Safety State

The cleanup and split are development-only. They do not add live order authority.

```text
NO_TRADE
RESEARCH_ONLY
LIVE_ORDER_BLOCKED
```

