---
document_id: AI4B-REF-RUNTIME-001
title: Runtime Dependency Ownership Reference
document_type: REFERENCE
version: 1.0.0
status: ACTIVE
owner: Enterprise Architecture
authority_level: REFERENCE
authority_layer: L9_REFERENCES_TEMPLATES
authority_effect: REFERENCE_ONLY
authority_scope: runtime_dependency_ownership_projection
content_role: DERIVED
source_of_truth: false
source_of_truth_scope: reference
machine_enforceable: false
audit_required: true
classification: INTERNAL
canonical_path: docs/references/reference_runtime_dependency_ownership.md
language: en-US
policy_refs:
  - docs/governance/framework_core_vnext_governance.md
  - docs/architecture/framework_architecture_overview.md
  - docs/standards/standard_technology_language_ownership.md
implemented_by:
  - src/ai4binance/application/virtual_runtime_engine.py
  - src/ai4binance/application/services/live_readiness.py
  - src/ai4binance/ops/architecture_migration.py
validated_by:
  - tests/test_virtual_runtime_bridge.py
  - tests/test_live_readiness_bridge.py
  - tests/test_repository_cleanup_audit.py
  - tests/test_kaizen_quality.py
  - tests/test_governance_constitution_sync.py
---

# Runtime Dependency Ownership Reference

## ELI10

The runtime uses one implementation of each shared contract or calculation.
Application services compose those implementations. Old import paths expose the
same objects so existing callers keep working without creating a second engine.

## Governing rules and scope

This reference projects the existing dependency direction, single-owner rule,
source/test/written-rule traceability obligation, and fail-closed safety boundary.
Their authority remains in the policy references above. The overview in
`docs/architecture/diagrams/02_repository/d204_dependency_direction_diagram.md`
shows Application -> Domain -> Core. The machine-readable component projection
remains `docs/registries/registry_logical_architecture.yaml`; migration ownership
is recorded by `src/ai4binance/ops/architecture_migration.py`.

The tables describe the resulting implementation and compatibility boundaries.
They do not define new trading rules, numerical formulas, risk thresholds,
language admission, approval roles, or execution permissions. Python 3.14 owns
the existing intelligence/orchestration implementation under the technology
standard; this relocation introduces no new numerical method or toolchain.

## Application orchestration and compatibility

| Implementation or compatibility surface | Existing responsibility and dependency boundary |
| --- | --- |
| `src/ai4binance/application/virtual_runtime_engine.py` | Owns the virtual runtime formerly implemented in `research/virtual_runtime.py`; composes canonical domain models, policy results, and typed evidence/portfolio ports. |
| `src/ai4binance/application/services/virtual_runtime.py` | Provides bounded cycle orchestration and exposes the canonical runtime exports. It imports the exact engine module, not the legacy research facade. |
| `src/ai4binance/application/services/__init__.py` | Resolves public service exports lazily through exact leaf imports. Importing readiness does not initialize the virtual runtime. |
| `src/ai4binance/application/services/live_readiness.py` | Owns read-only live-readiness assessment; consumes explicit policy/evidence ports without authorizing orders. Application and execution compatibility paths retain object identity. |
| `src/ai4binance/application/blocker_registry.py` | Loads the governed blocker registry. File/configuration access remains outside pure blocker contracts. |
| `src/ai4binance/application/blocker_reduction.py` | Supplies the configured blocker classifier to the pure reduction model; caching and registry access remain application responsibilities. |
| `src/ai4binance/application/virtual_market.py` | Resolves optional policy configuration and report projection around the existing mandatory-policy domain evaluator. |
| `src/ai4binance/application/user_reports.py` | Composes bounded report publication using existing storage operations and the shared renderer. |
| `src/ai4binance/execution/order_command.py` | Preserves the legacy order-command contract imports from the canonical domain owner. It adds no order authority. |
| `src/ai4binance/validation/live_gate_evidence.py` | Retains registry and persistence operations while re-exporting the domain evidence contracts. |

The application evidence and portfolio helpers receive explicit ports from the
real engine. They do not import research or operations implementations. The
legacy `research/virtual_runtime.py` and application runtime compatibility
module expose the canonical objects; their public APIs and typing stubs remain
aligned. Default behavior and deterministic vetoes are preserved.

## Shared contracts and calculations

| Canonical source | Preserved responsibility and legacy consumer |
| --- | --- |
| `src/ai4binance/domain/blockers.py` | Blocker contracts and payload parsing; `governance/blockers.py` remains the compatibility surface. |
| `src/ai4binance/domain/blocker_reduction.py` | Pure reduction with an explicit classifier callback; application owns configuration. |
| `src/ai4binance/domain/execution_authority.py` | Existing deterministic authority contracts; the governance facade preserves identity and vetoes. |
| `src/ai4binance/domain/execution_envelope.py` | Immutable execution-envelope contracts; no new approval or envelope authority. |
| `src/ai4binance/domain/order_command.py` | Order-command values formerly declared in execution; no transport or submission operation. |
| `src/ai4binance/domain/live_gate.py` | Existing live-gate decision contract exported through `safety.py`. |
| `src/ai4binance/domain/live_gate_evidence.py` | Read-only live-gate evidence values; registry writes remain in validation. |
| `src/ai4binance/domain/promotion_evidence.py` | Existing promotion evidence values; approval and registry operations remain in validation. |
| `src/ai4binance/domain/market_data.py` | The shared OHLCV candle contract; `schemas.py` preserves its public identity. |
| `src/ai4binance/domain/portfolio_risk.py` | Existing risk-budget contracts and calculations; `portfolio/risk_budget.py` is the identity-preserving facade. |
| `src/ai4binance/domain/risk_geometry.py` | Shared conservative structural margin-loss geometry; `risk.py` reuses the same function. |
| `src/ai4binance/core/report_rendering.py` | Pure Markdown report formatting with the existing research-only safety wording. Publication and storage remain outside core. |

## Research and paper runtime contracts

| Canonical source | Preserved responsibility |
| --- | --- |
| `src/ai4binance/domain/research/backtest_models.py` | Existing immutable backtest configuration, fills, trades, and result models. |
| `src/ai4binance/domain/research/equity_metrics.py` | Existing deterministic equity statistics, shared without a reverse research import. |
| `src/ai4binance/domain/research/governance.py` | Pure hypothesis, run-card, improvement, and review contracts; persistence/writers remain in `research_governance.py`. |
| `src/ai4binance/domain/research/liquidity.py` | Existing liquidity contracts and deterministic execution-cost support. |
| `src/ai4binance/domain/research/paper_lifecycle.py` | Existing simulated lifecycle transitions and closure contracts, also exposed through `execution/lifecycle.py`. |
| `src/ai4binance/domain/research/paper_models.py` | Immutable simulated order/status/exit contracts with timestamp, amount, and blocker validation. |
| `src/ai4binance/domain/research/robustness_models.py` | Immutable stress/bootstrap evidence; live execution and unapproved promotion remain rejected. |
| `src/ai4binance/domain/research/statistics.py` | Existing pure validation statistics, retaining the validation compatibility surface. |
| `src/ai4binance/domain/research/trailing.py` | Existing trailing-stop calculation contracts, retaining the execution compatibility surface. |
| `src/ai4binance/domain/research/validation_models.py` | Shared validation model values; no data loading or promotion operation. |
| `src/ai4binance/domain/research/virtual_market.py` | Existing paper-market contracts, calculations, and acceptance evaluation with explicit policy input. |
| `src/ai4binance/domain/research/virtual_runtime_portfolio_state.py` | Existing portfolio values and deterministic state transitions. |
| `src/ai4binance/domain/research/virtual_runtime_portfolios.py` | Independent Spot/Futures paper portfolio contracts. |
| `src/ai4binance/domain/research/virtual_runtime_request.py` | Existing runtime request contract and input validation. |
| `src/ai4binance/domain/research/virtual_runtime_risk.py` | Existing deterministic paper risk/leverage checks; no confidence-driven sizing or live permission. |
| `src/ai4binance/domain/research/virtual_runtime_trade_intent.py` | Existing virtual trade-intent contract, without order submission. |

Pure extractions preserve the original calculation bodies. The corresponding
legacy modules expose the same objects. Partial extractions retain their
remaining I/O responsibilities and are not represented as complete facades.

## Evidence contracts and operational ownership

| Canonical source | Preserved operational boundary |
| --- | --- |
| `src/ai4binance/domain/evidence/continuous_assurance.py` | Shared immutable assurance values and pure helpers; triggers, journals, and operational routes remain in `ops/continuous_assurance.py`. |
| `src/ai4binance/domain/evidence/decision_telemetry.py` | Shared telemetry models and pure builders; ledger writes and Markdown export remain in `ops/decision_telemetry.py`. GPU evidence is a read-only protocol. |
| `src/ai4binance/domain/evidence/trust_plane.py` | Existing pure trust catalog and contracts; `trust/plane.py` preserves public identity. |

Evidence is never execution authority. A source relocation does not refresh
historical OOS, approval, quality, or traceability evidence. Each evidence
consumer retains its original identity, hash, freshness, and veto checks.

## Verification links

Cold-import, lazy loading, full public identity, and stub export parity are
verified in `tests/test_virtual_runtime_bridge.py` and
`tests/test_live_readiness_bridge.py`. The unchanged architecture scanner and
migration ledger are exercised by `tests/test_repository_cleanup_audit.py` and
`tests/test_kaizen_quality.py`.

Contract behavior and authority rejection are covered by
`tests/test_user_reports.py`, `tests/test_paper_execution.py`,
`tests/test_parameter_tournament.py`, `tests/test_strategy_risk.py`,
`tests/test_virtual_runtime.py`, `tests/test_virtual_runtime_performance.py`,
`tests/test_virtual_blocker_reduction.py`, `tests/test_execution_authority.py`,
`tests/test_execution_envelope.py`, `tests/test_continuous_assurance.py`,
`tests/test_decision_telemetry.py`, and `tests/test_trust_plane.py`.

The canonical quality profile and repository validator must validate the
resulting workspace. This reference is not test-run evidence, policy eligibility,
consequential human approval, or permission to trade. `RESEARCH_ONLY`,
`execution_allowed=false`, and `LIVE_ORDER_BLOCKED` remain applicable.
