"""Governed research radar lifecycle, assessment, and persistence tests."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ai4binance.research_catalog import (
    AgentEngineeringLayer,
    AgentEngineeringLayerEvidence,
    AgentEngineeringLayerReview,
    AgentEngineeringLayerReviewStatus,
    AgentRuntimeEconomicsEvidence,
    AgentRuntimeEconomicsReview,
    AgentRuntimeEconomicsReviewStatus,
    CatalogStatus,
    ExternalQuantLectureEvidence,
    ExternalQuantLectureReview,
    ExternalQuantLectureReviewStatus,
    ExternalQuestionBankEvidence,
    ExternalQuestionBankReview,
    ExternalQuestionBankReviewStatus,
    ExternalRepoWatchlistAdmission,
    ExternalRepoWatchlistCandidate,
    ExternalRepoWatchlistCategory,
    QuantResearchHypothesisEvidence,
    QuantResearchHypothesisReview,
    QuantResearchHypothesisStatus,
    QuantResearchReviewerResult,
    ReproductionQueueWriter,
    ResearchCatalog,
    ResearchCatalogEntry,
    SecondBrainMemoryEvidence,
    SecondBrainMemoryReview,
    SecondBrainMemoryReviewStatus,
    VolatilityAssumptionEvidence,
    VolatilityAssumptionReview,
    VolatilityAssumptionReviewStatus,
    assess_technology_candidate,
    external_repo_watchlist_admission,
    review_agent_engineering_layer,
    review_agent_runtime_economics,
    review_external_quant_lecture,
    review_external_question_bank,
    review_quant_research_hypothesis,
    review_second_brain_memory,
    review_volatility_assumption,
)
from ai4binance.storage import JsonlAuditStore

NOW = datetime(2026, 7, 13, tzinfo=UTC)


def entry(entry_id: str = "vnpy-patterns") -> ResearchCatalogEntry:
    return ResearchCatalogEntry(
        entry_id=entry_id,
        title="Event lifecycle patterns",
        source_url="https://github.com/vnpy/vnpy",
        source_revision="UNPINNED_REVIEW_2026-07-13",
        license_id="MIT",
        hypothesis="Persistent event recovery reduces restart ambiguity.",
        asset_classes=("CRYPTO_SPOT",),
        timeframes=("5m", "15m", "1h", "4h", "1d"),
        leakage_risks=("EVENT_TIME_CONTAMINATION",),
        data_requirements=("ORDER_EVENTS",),
        cost_assumptions=("NO_LIVE_EXECUTION",),
        discovered_at=NOW,
        updated_at=NOW,
    )


def quant_hypothesis() -> QuantResearchHypothesisEvidence:
    return QuantResearchHypothesisEvidence(
        hypothesis_id="hotusdt-residual-reclaim-v1",
        symbol="HOTUSDT",
        timeframe="1h",
        market_mechanism=(
            "Temporary sell pressure may overshoot during high-volume support reclaims."
        ),
        measurable_footprint=(
            "Negative residual return followed by support reclaim and volume "
            "confirmation."
        ),
        universe="Binance Spot HOTUSDT with BTC market context as benchmark",
        liquidity_assumption="Spread and slippage must stay below configured caps",
        feature_horizon="Residual return over 24 1h bars with 4h regime context",
        oos_requirement="Walk-forward OOS split across trend and range regimes",
        transaction_cost_requirement="Fees plus slippage must be deducted per fill",
        reviewer_result=QuantResearchReviewerResult.PASSED,
        data_citations=("research:quant/hotusdt-residual-reclaim-v1.json",),
        leakage_checks=(
            "FEATURES_KNOWN_AT_SIGNAL_TIME",
            "NO_FUTURE_CLOSE_IN_ENTRY_DECISION",
        ),
        robustness_checks=(
            "LOOKBACK_SENSITIVITY",
            "TRANSACTION_COST_STRESS",
            "REMOVE_BEST_YEAR",
        ),
        rejection_reason="none",
        maker_checker_separated=True,
    )


def question_bank() -> ExternalQuestionBankEvidence:
    return ExternalQuestionBankEvidence(
        repository="akira82-ai/100-questions-of-ai-agent",
        source_url="https://github.com/akira82-ai/100-questions-of-ai-agent",
        pinned_revision="a" * 40,
        license_id="MIT",
        reviewed_paths=(
            "README.md",
            "100-questions-of-loop-engineering/04-verification-quality-and-cost-control.md",
            "100-questions-of-graph-engineering/02-core-architecture-and-key-mechanisms.md",
            "100-questions-of-codex/04-advanced-skills-mcp-plugins-automation-computer-use.md",
        ),
        content_sha256="b" * 64,
        topic_tags=("loop-engineering", "graph-engineering", "computer use"),
        mapped_ai4binance_domains=(
            "agent-workflow",
            "validation",
            "docs-reporting",
        ),
        evidence_citations=(
            "https://github.com/akira82-ai/100-questions-of-ai-agent",
            "https://raw.githubusercontent.com/akira82-ai/100-questions-of-ai-agent/main/100-questions-of-loop-engineering/04-verification-quality-and-cost-control.md",
        ),
        privacy_controls=("NO_PII_INGESTION", "NO_SECRET_ACCESS"),
    )


def quant_lecture() -> ExternalQuantLectureEvidence:
    return ExternalQuantLectureEvidence(
        lecture_id="tsukiema-quant-lecture-20260801",
        title="Crypto spot volatility regime lecture",
        source_url="https://x.com/tsukiema_/status/2082029483519811761",
        source_sha256="d" * 64,
        topics=("volatility regime", "market microstructure"),
        asset_classes=("CRYPTO_SPOT",),
        claimed_techniques=("walk-forward validation", "transaction-cost stress"),
        oos_requirement="Walk-forward OOS split across trend and range regimes",
        transaction_cost_requirement="Binance Spot fees plus slippage per fill",
        reviewer_result=QuantResearchReviewerResult.PASSED,
        evidence_citations=(
            "https://x.com/tsukiema_/status/2082029483519811761",
            "research:external/tsukiema-quant-lecture-20260801.json",
        ),
        rejection_reason="none",
        maker_checker_separated=True,
    )


def agent_layer_evidence(
    layer: AgentEngineeringLayer = AgentEngineeringLayer.HARNESS,
) -> AgentEngineeringLayerEvidence:
    return AgentEngineeringLayerEvidence(
        artifact_id="loop-graph-harness-0xwhrrari-20260801",
        title="Loop vs graph vs harness engineering",
        source_url="https://x.com/0xwhrrari/article/2082096897964306572",
        source_sha256="e" * 64,
        layer=layer,
        observed_controls=(
            "least_privilege_tools",
            "memory_boundary",
            "permission_model",
            "sandbox",
            "trace_logging",
            "human_approval_gate",
        ),
        reviewer_result=QuantResearchReviewerResult.PASSED,
        evidence_citations=(
            "https://x.com/0xwhrrari/article/2082096897964306572",
            "https://docs.langchain.com/oss/python/langchain/agents",
            "https://openai.github.io/openai-agents-python/tracing/",
        ),
        rejection_reason="none",
    )


def runtime_economics() -> AgentRuntimeEconomicsEvidence:
    return AgentRuntimeEconomicsEvidence(
        artifact_id="marfinxx-local-runtime-economics-20260801",
        title="Local AI agent runtime economics",
        source_url="https://x.com/marfinxx/status/2081687570488954915",
        source_sha256="f" * 64,
        hardware_profile="Local RTX workstation with loopback-only advisory runtime",
        runtime_stack="Hermes/OpenClaw-style local agent loop benchmark",
        reviewer_result=QuantResearchReviewerResult.PASSED,
        claimed_monthly_cost_usd=5.0,
        measured_latency_ms=850.0,
        measured_tokens_per_second=42.0,
        measured_power_watts=310.0,
        benchmark_citations=(
            "https://x.com/marfinxx/status/2081687570488954915",
            "research:runtime/marfinxx-local-runtime-economics-20260801.json",
        ),
        privacy_controls=("LOOPBACK_ONLY", "NO_SECRET_ACCESS", "NO_RAW_WALLET_CONTEXT"),
        operational_controls=(
            "RUNAWAY_LOOP_BUDGET",
            "THERMAL_MONITORING_REQUIRED",
            "PROVIDER_SWITCH_BLOCKED",
        ),
        rejection_reason="none",
    )


def second_brain_memory() -> SecondBrainMemoryEvidence:
    return SecondBrainMemoryEvidence(
        memory_id="undefinedki-second-brain-20260801",
        title="Claude and Obsidian second-brain research memory",
        source_url="https://x.com/undefinedKi/status/2068306794116501544",
        source_sha256="1" * 64,
        vault_path_sha256="2" * 64,
        topic_tags=("second-brain", "research-memory", "privacy-boundary"),
        staleness_policy="Re-review social-source claims every 30 days.",
        reviewer_result=QuantResearchReviewerResult.PASSED,
        evidence_citations=(
            "https://x.com/undefinedKi/status/2068306794116501544",
            "https://obsidian.md/help/data-storage",
        ),
        privacy_controls=("LOCAL_VAULT_ONLY", "NO_SECRET_ACCESS", "NO_WALLET_CONTEXT"),
        redaction_controls=(
            "HASH_PATH_ONLY",
            "REDACT_PRIVATE_STATE",
            "BOUNDED_CONTEXT",
        ),
        rejection_reason="none",
    )


def test_catalog_lifecycle_is_append_only_and_human_governed(tmp_path: Path) -> None:
    ledger_path = tmp_path / "catalog.jsonl"
    catalog = ResearchCatalog(ledger=JsonlAuditStore(ledger_path)).add(entry())
    registered = catalog.entries[0].transition(
        CatalogStatus.HYPOTHESIS_REGISTERED,
        updated_at=NOW + timedelta(seconds=1),
        blockers=("REPRODUCTION_NOT_RUN",),
    )
    catalog = catalog.update(registered)
    pending = registered.transition(
        CatalogStatus.REPRODUCTION_PENDING,
        updated_at=NOW + timedelta(seconds=2),
        blockers=("REPRODUCTION_NOT_RUN",),
    )
    catalog = catalog.update(pending)
    ReproductionQueueWriter(tmp_path / "queue.json").write(catalog)

    assert len(ledger_path.read_text(encoding="utf-8").splitlines()) == 3
    queue = json.loads((tmp_path / "queue.json").read_text(encoding="utf-8"))
    assert queue["entries"][0]["entry_id"] == "vnpy-patterns"
    assert queue["execution_allowed"] is False


def test_catalog_blocks_skipped_and_automatic_paper_transitions() -> None:
    item = entry()
    with pytest.raises(ValueError, match="invalid catalog transition"):
        item.transition(CatalogStatus.STAGED_CANDIDATE, updated_at=NOW)
    staged = replace(
        item,
        status=CatalogStatus.STAGED_CANDIDATE,
        blockers=(),
        artifact_ids=("oos-report",),
    )
    with pytest.raises(ValueError, match="human approval"):
        staged.transition(
            CatalogStatus.PAPER_APPROVED,
            updated_at=NOW + timedelta(seconds=1),
        )
    approved = staged.transition(
        CatalogStatus.PAPER_APPROVED,
        updated_at=NOW + timedelta(seconds=1),
        human_approved=True,
    )
    assert approved.execution_allowed is False


def test_technology_assessment_requires_all_evidence_and_never_installs() -> None:
    blocked = assess_technology_candidate(
        entry_id="polars-benchmark",
        license_compatible=True,
        actively_maintained=True,
        canonical_python_supported=True,
        deterministic_or_seeded=True,
        lookahead_reviewed=False,
        security_reviewed=False,
        benchmark_gain_percent=None,
        removal_cost_documented=True,
    )
    assert blocked.approved_for_experiment is False
    assert blocked.installation_allowed is False
    assert blocked.blockers == (
        "LOOKAHEAD_RISK_NOT_REVIEWED",
        "SECURITY_REVIEW_MISSING",
        "BENCHMARK_EVIDENCE_MISSING",
    )

    approved = assess_technology_candidate(
        entry_id="polars-benchmark",
        license_compatible=True,
        actively_maintained=True,
        canonical_python_supported=True,
        deterministic_or_seeded=True,
        lookahead_reviewed=True,
        security_reviewed=True,
        benchmark_gain_percent=20.0,
        removal_cost_documented=True,
    )
    assert approved.approved_for_experiment is True
    assert approved.installation_allowed is False

    unsupported = assess_technology_candidate(
        entry_id="runtime-incompatible-candidate",
        license_compatible=True,
        actively_maintained=True,
        canonical_python_supported=False,
        deterministic_or_seeded=True,
        lookahead_reviewed=True,
        security_reviewed=True,
        benchmark_gain_percent=20.0,
        removal_cost_documented=True,
    )
    assert unsupported.blockers == ("CANONICAL_PYTHON_UNSUPPORTED",)


def test_technology_assessment_rejects_invalid_manual_shapes() -> None:
    with pytest.raises(ValueError, match="identity"):
        replace(
            assess_technology_candidate(
                entry_id="polars-benchmark",
                license_compatible=True,
                actively_maintained=True,
                canonical_python_supported=True,
                deterministic_or_seeded=True,
                lookahead_reviewed=True,
                security_reviewed=True,
                benchmark_gain_percent=20.0,
                removal_cost_documented=True,
            ),
            entry_id="",
        )
    with pytest.raises(ValueError, match="benchmark"):
        assess_technology_candidate(
            entry_id="polars-benchmark",
            license_compatible=True,
            actively_maintained=True,
            canonical_python_supported=True,
            deterministic_or_seeded=True,
            lookahead_reviewed=True,
            security_reviewed=True,
            benchmark_gain_percent=100_001.0,
            removal_cost_documented=True,
        )
    with pytest.raises(ValueError, match="blockers disagree"):
        replace(
            assess_technology_candidate(
                entry_id="polars-benchmark",
                license_compatible=True,
                actively_maintained=True,
                canonical_python_supported=True,
                deterministic_or_seeded=True,
                lookahead_reviewed=True,
                security_reviewed=True,
                benchmark_gain_percent=20.0,
                removal_cost_documented=True,
            ),
            blockers=("MANUAL_BLOCKER",),
        )
    with pytest.raises(ValueError, match="cannot install"):
        replace(
            assess_technology_candidate(
                entry_id="polars-benchmark",
                license_compatible=True,
                actively_maintained=True,
                canonical_python_supported=True,
                deterministic_or_seeded=True,
                lookahead_reviewed=True,
                security_reviewed=True,
                benchmark_gain_percent=20.0,
                removal_cost_documented=True,
            ),
            installation_allowed=True,
        )


def test_external_repo_watchlist_admits_pinned_cited_github_repo_as_watchlist() -> None:
    admission = external_repo_watchlist_admission(
        ExternalRepoWatchlistCandidate(
            repo_url="https://github.com/example/research-tools",
            title="Research tools",
            category=ExternalRepoWatchlistCategory.VALIDATION,
            pinned_revision="a" * 40,
            license_id="MIT",
            reviewed_paths=("README.md", "docs/usage.md", "tests/test_contract.py"),
            evidence_citations=("https://github.com/example/research-tools",),
            declared_features=("validation reporting",),
        )
    )

    assert admission.status == "WATCHLIST"
    assert admission.promotion_status == "RESEARCH_ONLY_REPO_CANDIDATE"
    assert admission.blockers == (
        "EXTERNAL_REPO_CLONE_BLOCKED",
        "EXTERNAL_REPO_INSTALL_BLOCKED",
        "EXTERNAL_REPO_EXECUTION_BLOCKED",
        "LIVE_ORDER_BLOCKED",
    )
    assert admission.execution_allowed is False
    assert admission.installation_allowed is False
    assert admission.clone_allowed is False
    assert admission.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_external_repo_watchlist_blocks_missing_pin_license_and_scope() -> None:
    admission = external_repo_watchlist_admission(
        ExternalRepoWatchlistCandidate(
            repo_url="https://github.com/example/trading-bot",
            title="Trading bot",
            category=ExternalRepoWatchlistCategory.PORTFOLIO_RISK,
            reviewed_paths=("src/live_order.py",),
            declared_features=(
                "MCP plugin with script hook and live order trading support",
            ),
        )
    )

    assert admission.status == "BLOCKED"
    assert "PINNED_REVISION_REQUIRED" in admission.blockers
    assert "LICENSE_REVIEW_REQUIRED" in admission.blockers
    assert "SOURCE_CITATION_REQUIRED" in admission.blockers
    assert "EXTERNAL_REPO_REVIEW_SCOPE_BLOCKED" in admission.blockers
    assert "HUMAN_REVIEW_REQUIRED" in admission.blockers
    assert "FINANCIAL_SENSITIVE_REVIEW" in admission.blockers
    assert "LIVE_ORDER_BLOCKED" in admission.blockers


def test_external_repo_watchlist_rejects_non_github_and_authority_shapes() -> None:
    with pytest.raises(ValueError, match="public GitHub URL"):
        ExternalRepoWatchlistCandidate(
            repo_url="https://gitlab.com/example/repo",
            title="Wrong host",
            category=ExternalRepoWatchlistCategory.AGENT_WORKFLOW,
        )
    with pytest.raises(ValueError, match="cannot grant authority"):
        ExternalRepoWatchlistCandidate(
            repo_url="https://github.com/example/repo",
            title="Unsafe",
            category=ExternalRepoWatchlistCategory.AGENT_WORKFLOW,
            execution_allowed=True,
        )
    with pytest.raises(ValueError, match="research-only"):
        ExternalRepoWatchlistAdmission(
            repo_url="https://github.com/example/repo",
            category=ExternalRepoWatchlistCategory.AGENT_WORKFLOW,
            status="WATCHLIST",
            blockers=("LIVE_ORDER_BLOCKED",),
            reviewed_paths=("README.md",),
            evidence_citations=("https://github.com/example/repo",),
            promotion_status="PAPER_APPROVED",
        )
    with pytest.raises(ValueError, match="reviewed paths"):
        ExternalRepoWatchlistCandidate(
            repo_url="https://github.com/example/repo",
            title="Duplicate paths",
            category=ExternalRepoWatchlistCategory.AGENT_WORKFLOW,
            reviewed_paths=("README.md", "README.md"),
        )
    with pytest.raises(ValueError, match="citations"):
        ExternalRepoWatchlistCandidate(
            repo_url="https://github.com/example/repo",
            title="Duplicate citations",
            category=ExternalRepoWatchlistCategory.AGENT_WORKFLOW,
            evidence_citations=("https://github.com/example/repo", ""),
        )
    with pytest.raises(ValueError, match="features"):
        ExternalRepoWatchlistCandidate(
            repo_url="https://github.com/example/repo",
            title="Duplicate features",
            category=ExternalRepoWatchlistCategory.AGENT_WORKFLOW,
            declared_features=("docs", "docs"),
        )
    with pytest.raises(ValueError, match="status"):
        ExternalRepoWatchlistAdmission(
            repo_url="https://github.com/example/repo",
            category=ExternalRepoWatchlistCategory.AGENT_WORKFLOW,
            status="RESEARCH_ONLY",
            blockers=("LIVE_ORDER_BLOCKED",),
            reviewed_paths=("README.md",),
            evidence_citations=("https://github.com/example/repo",),
        )
    with pytest.raises(ValueError, match="retain review blockers"):
        ExternalRepoWatchlistAdmission(
            repo_url="https://github.com/example/repo",
            category=ExternalRepoWatchlistCategory.AGENT_WORKFLOW,
            status="WATCHLIST",
            blockers=(),
            reviewed_paths=("README.md",),
            evidence_citations=("https://github.com/example/repo",),
        )
    with pytest.raises(ValueError, match="hard blockers"):
        ExternalRepoWatchlistAdmission(
            repo_url="https://github.com/example/repo",
            category=ExternalRepoWatchlistCategory.AGENT_WORKFLOW,
            status="BLOCKED",
            blockers=("FINANCIAL_SENSITIVE_REVIEW",),
            reviewed_paths=("README.md",),
            evidence_citations=("https://github.com/example/repo",),
        )
    with pytest.raises(ValueError, match="keep live trading blocked"):
        ExternalRepoWatchlistAdmission(
            repo_url="https://github.com/example/repo",
            category=ExternalRepoWatchlistCategory.AGENT_WORKFLOW,
            status="WATCHLIST",
            blockers=("LIVE_ORDER_BLOCKED",),
            reviewed_paths=("README.md",),
            evidence_citations=("https://github.com/example/repo",),
            live_eligibility_status="PAPER_APPROVED",
        )


def test_external_question_bank_keeps_complete_repo_research_only() -> None:
    review = review_external_question_bank(question_bank())

    assert review.status is ExternalQuestionBankReviewStatus.RESEARCH_ONLY_QUESTION_BANK
    assert review.promotion_status == "RESEARCH_ONLY_QUESTION_BANK"
    assert review.repository == "akira82-ai/100-questions-of-ai-agent"
    assert review.content_sha256 == "b" * 64
    assert review.privacy_controls == ("NO_PII_INGESTION", "NO_SECRET_ACCESS")
    assert review.blockers == (
        "NO_TRADE_SIGNAL_AUTHORITY",
        "QUESTION_BANK_REVIEW_READ_ONLY",
        "HUMAN_REVIEW_REQUIRED",
        "LIVE_ORDER_BLOCKED",
    )
    assert review.execution_allowed is False
    assert review.installation_allowed is False
    assert review.clone_allowed is False
    assert review.signal_authority is False
    assert review.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_external_question_bank_watchlists_missing_controls_and_trading_scope() -> None:
    review = review_external_question_bank(
        ExternalQuestionBankEvidence(
            repository="example/trading-questions",
            source_url="https://github.com/example/trading-questions",
            pinned_revision="",
            license_id="unknown",
            reviewed_paths=("src/live_order.md",),
            content_sha256="c" * 64,
            topic_tags=("computer use", "live order trading"),
            mapped_ai4binance_domains=("portfolio-risk",),
        )
    )

    assert review.status is ExternalQuestionBankReviewStatus.WATCHLIST
    assert "QUESTION_BANK_PIN_REQUIRED" in review.blockers
    assert "QUESTION_BANK_LICENSE_REVIEW_REQUIRED" in review.blockers
    assert "QUESTION_BANK_REVIEW_SCOPE_BLOCKED" in review.blockers
    assert "QUESTION_BANK_CITATION_REQUIRED" in review.blockers
    assert "QUESTION_BANK_TRADING_SCOPE_REVIEW_REQUIRED" in review.blockers
    assert "QUESTION_BANK_PRIVACY_REVIEW_REQUIRED" in review.blockers
    assert "LIVE_ORDER_BLOCKED" in review.blockers


def test_external_question_bank_rejects_authority_and_invalid_shapes() -> None:
    with pytest.raises(ValueError, match="public GitHub URL"):
        replace(question_bank(), source_url="https://gitlab.com/example/repo")
    with pytest.raises(ValueError, match="content hash"):
        replace(question_bank(), content_sha256="bad")
    with pytest.raises(ValueError, match="topic tags"):
        replace(question_bank(), topic_tags=("same", "same"))
    with pytest.raises(ValueError, match="cannot grant authority"):
        replace(question_bank(), execution_allowed=True)
    with pytest.raises(ValueError, match="research-only"):
        replace(
            review_external_question_bank(question_bank()),
            promotion_status="STAGED_CANDIDATE",
        )
    with pytest.raises(ValueError, match="require human review"):
        ExternalQuestionBankReview(
            repository="example/questions",
            source_url="https://github.com/example/questions",
            pinned_revision="a" * 40,
            license_id="MIT",
            reviewed_paths=("README.md",),
            content_sha256="b" * 64,
            topic_tags=("loop-engineering",),
            mapped_ai4binance_domains=("validation",),
            status=ExternalQuestionBankReviewStatus.RESEARCH_ONLY_QUESTION_BANK,
            blockers=(
                "NO_TRADE_SIGNAL_AUTHORITY",
                "QUESTION_BANK_REVIEW_READ_ONLY",
                "LIVE_ORDER_BLOCKED",
            ),
            evidence_citations=("https://github.com/example/questions",),
            privacy_controls=(),
        )
    with pytest.raises(ValueError, match="block live trading"):
        replace(
            review_external_question_bank(question_bank()),
            live_eligibility_status="PAPER_APPROVED",
        )


def test_external_quant_lecture_keeps_complete_spot_source_research_only() -> None:
    review = review_external_quant_lecture(quant_lecture())

    assert review.status is ExternalQuantLectureReviewStatus.RESEARCH_ONLY_LECTURE
    assert review.reviewer_result is QuantResearchReviewerResult.PASSED
    assert review.promotion_status == "RESEARCH_ONLY_QUANT_LECTURE"
    assert review.source_sha256 == "d" * 64
    assert review.blockers == (
        "NO_TRADE_SIGNAL_AUTHORITY",
        "QUANT_LECTURE_REVIEW_READ_ONLY",
        "HUMAN_REVIEW_REQUIRED",
        "LIVE_ORDER_BLOCKED",
    )
    assert review.execution_allowed is False
    assert review.signal_authority is False
    assert review.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_external_quant_lecture_watchlists_unavailable_source_and_missing_oos() -> None:
    review = review_external_quant_lecture(
        replace(
            quant_lecture(),
            source_available=False,
            oos_requirement="",
            transaction_cost_requirement="",
            maker_checker_separated=False,
            reviewer_result=QuantResearchReviewerResult.WATCHLIST,
            rejection_reason="Original thread was unavailable during review.",
        )
    )

    assert review.status is ExternalQuantLectureReviewStatus.WATCHLIST
    assert "QUANT_LECTURE_SOURCE_UNAVAILABLE" in review.blockers
    assert "OOS_REQUIREMENT_REQUIRED" in review.blockers
    assert "TRANSACTION_COST_REQUIREMENT_REQUIRED" in review.blockers
    assert "MAKER_CHECKER_SEPARATION_REQUIRED" in review.blockers
    assert "QUANT_LECTURE_REVIEWER_WATCHLIST" in review.blockers
    assert "LIVE_ORDER_BLOCKED" in review.blockers


def test_external_quant_lecture_rejects_institutional_only_non_spot_context() -> None:
    review = review_external_quant_lecture(
        replace(
            quant_lecture(),
            title="Dark pool order splitting lecture",
            topics=("dark pool", "hidden liquidity"),
            asset_classes=("EQUITY_MARKET_STRUCTURE",),
            claimed_techniques=("order splitting",),
            reviewer_result=QuantResearchReviewerResult.REJECTED,
            rejection_reason="Institutional dark-pool mechanics are not Binance Spot.",
        )
    )

    assert review.status is ExternalQuantLectureReviewStatus.REJECTED_AS_SPOT_IRRELEVANT
    assert "SPOT_RELEVANCE_REVIEW_REQUIRED" in review.blockers
    assert "INSTITUTIONAL_MARKET_STRUCTURE_NOT_BINANCE_SPOT" in review.blockers
    assert "QUANT_LECTURE_REVIEWER_REJECTED" in review.blockers
    assert "NO_TRADE_SIGNAL_AUTHORITY" in review.blockers


def test_external_quant_lecture_rejects_authority_and_invalid_shapes() -> None:
    with pytest.raises(ValueError, match="credential-free HTTPS"):
        replace(quant_lecture(), source_url="http://user:pass@example.com")
    with pytest.raises(ValueError, match="source hash"):
        replace(quant_lecture(), source_sha256="bad")
    with pytest.raises(ValueError, match="topics"):
        replace(quant_lecture(), topics=("same", "same"))
    with pytest.raises(ValueError, match="claimed techniques"):
        replace(quant_lecture(), claimed_techniques=("",))
    with pytest.raises(ValueError, match="cannot grant authority"):
        replace(quant_lecture(), live_order_authority=True)
    with pytest.raises(ValueError, match="research-only"):
        replace(
            review_external_quant_lecture(quant_lecture()),
            promotion_status="STAGED_CANDIDATE",
        )
    with pytest.raises(ValueError, match="require human review"):
        ExternalQuantLectureReview(
            lecture_id="lecture",
            title="lecture",
            source_url="https://example.com/lecture",
            source_sha256="d" * 64,
            status=ExternalQuantLectureReviewStatus.RESEARCH_ONLY_LECTURE,
            reviewer_result=QuantResearchReviewerResult.PASSED,
            topics=("spot",),
            asset_classes=("CRYPTO_SPOT",),
            claimed_techniques=("walk-forward",),
            oos_requirement="oos",
            transaction_cost_requirement="cost",
            rejection_reason="none",
            blockers=(
                "NO_TRADE_SIGNAL_AUTHORITY",
                "QUANT_LECTURE_REVIEW_READ_ONLY",
                "LIVE_ORDER_BLOCKED",
            ),
            evidence_citations=("https://example.com/lecture",),
        )
    with pytest.raises(ValueError, match="block live trading"):
        replace(
            review_external_quant_lecture(quant_lecture()),
            live_eligibility_status="PAPER_APPROVED",
        )


def test_agent_engineering_layer_accepts_complete_harness_as_research_only() -> None:
    review = review_agent_engineering_layer(agent_layer_evidence())

    assert review.layer is AgentEngineeringLayer.HARNESS
    assert (
        review.status is AgentEngineeringLayerReviewStatus.RESEARCH_ONLY_AGENT_PATTERN
    )
    assert review.promotion_status == "RESEARCH_ONLY_AGENT_PATTERN"
    assert review.required_controls == (
        "least_privilege_tools",
        "memory_boundary",
        "permission_model",
        "sandbox",
        "trace_logging",
        "human_approval_gate",
    )
    assert review.missing_controls == ()
    assert review.blockers == (
        "NO_TRADE_SIGNAL_AUTHORITY",
        "AGENT_ENGINEERING_REVIEW_READ_ONLY",
        "HUMAN_REVIEW_REQUIRED",
        "LIVE_ORDER_BLOCKED",
    )
    assert review.execution_allowed is False
    assert review.signal_authority is False
    assert review.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_agent_engineering_layer_watchlists_missing_graph_controls() -> None:
    review = review_agent_engineering_layer(
        replace(
            agent_layer_evidence(AgentEngineeringLayer.GRAPH),
            observed_controls=("nodes", "edges", "guards", "terminal-states"),
            reviewer_result=QuantResearchReviewerResult.WATCHLIST,
            rejection_reason="Reducer and reviewer node are not evidenced.",
        )
    )

    assert review.layer is AgentEngineeringLayer.GRAPH
    assert review.status is AgentEngineeringLayerReviewStatus.WATCHLIST
    assert review.missing_controls == (
        "reviewer_node",
        "deterministic_reducer",
    )
    assert "MISSING_CONTROL_REVIEWER_NODE" in review.blockers
    assert "MISSING_CONTROL_DETERMINISTIC_REDUCER" in review.blockers
    assert "AGENT_PATTERN_REVIEWER_WATCHLIST" in review.blockers
    assert "LIVE_ORDER_BLOCKED" in review.blockers


def test_agent_engineering_layer_blocks_unavailable_uncited_source() -> None:
    review = review_agent_engineering_layer(
        replace(
            agent_layer_evidence(AgentEngineeringLayer.LOOP),
            observed_controls=("trigger", "bounded_context", "stop_condition"),
            source_available=False,
            evidence_citations=(),
            reviewer_result=QuantResearchReviewerResult.REJECTED,
            rejection_reason="Source unavailable and loop controls incomplete.",
        )
    )

    assert review.status is AgentEngineeringLayerReviewStatus.BLOCKED
    assert "AGENT_PATTERN_SOURCE_UNAVAILABLE" in review.blockers
    assert "SOURCE_CITATION_REQUIRED" in review.blockers
    assert "AGENT_PATTERN_REVIEWER_REJECTED" in review.blockers
    assert "MISSING_CONTROL_TOOL_CONTRACT" in review.blockers
    assert "MISSING_CONTROL_VERIFICATION_CHECK" in review.blockers
    assert "MISSING_CONTROL_RETRY_BUDGET" in review.blockers
    assert "NO_TRADE_SIGNAL_AUTHORITY" in review.blockers


def test_agent_engineering_layer_rejects_authority_and_invalid_shapes() -> None:
    with pytest.raises(ValueError, match="credential-free HTTPS"):
        replace(agent_layer_evidence(), source_url="http://user:pass@example.com")
    with pytest.raises(ValueError, match="source hash"):
        replace(agent_layer_evidence(), source_sha256="bad")
    with pytest.raises(ValueError, match="observed controls"):
        replace(agent_layer_evidence(), observed_controls=("same", "same"))
    with pytest.raises(ValueError, match="cannot grant authority"):
        replace(agent_layer_evidence(), signal_authority=True)
    with pytest.raises(ValueError, match="research-only"):
        replace(
            review_agent_engineering_layer(agent_layer_evidence()),
            promotion_status="STAGED_CANDIDATE",
        )
    with pytest.raises(ValueError, match="require human review"):
        AgentEngineeringLayerReview(
            artifact_id="artifact",
            title="title",
            source_url="https://example.com/article",
            source_sha256="e" * 64,
            layer=AgentEngineeringLayer.LOOP,
            status=AgentEngineeringLayerReviewStatus.RESEARCH_ONLY_AGENT_PATTERN,
            reviewer_result=QuantResearchReviewerResult.PASSED,
            required_controls=("trigger",),
            observed_controls=("trigger",),
            missing_controls=(),
            blockers=(
                "NO_TRADE_SIGNAL_AUTHORITY",
                "AGENT_ENGINEERING_REVIEW_READ_ONLY",
                "LIVE_ORDER_BLOCKED",
            ),
            evidence_citations=("https://example.com/article",),
            rejection_reason="none",
        )
    with pytest.raises(ValueError, match="cannot miss controls"):
        replace(
            review_agent_engineering_layer(agent_layer_evidence()),
            missing_controls=("trace_logging",),
        )
    with pytest.raises(ValueError, match="block live trading"):
        replace(
            review_agent_engineering_layer(agent_layer_evidence()),
            live_eligibility_status="PAPER_APPROVED",
        )


def test_agent_runtime_economics_accepts_measured_local_runtime_research_only() -> None:
    review = review_agent_runtime_economics(runtime_economics())

    assert (
        review.status is AgentRuntimeEconomicsReviewStatus.RESEARCH_ONLY_RUNTIME_PATTERN
    )
    assert review.promotion_status == "RESEARCH_ONLY_RUNTIME_PATTERN"
    assert review.hardware_profile.startswith("Local RTX workstation")
    assert review.claimed_monthly_cost_usd == 5.0
    assert review.measured_latency_ms == 850.0
    assert review.measured_tokens_per_second == 42.0
    assert review.measured_power_watts == 310.0
    assert review.blockers == (
        "NO_TRADE_SIGNAL_AUTHORITY",
        "AGENT_RUNTIME_REVIEW_READ_ONLY",
        "HUMAN_REVIEW_REQUIRED",
        "LIVE_ORDER_BLOCKED",
    )
    assert review.execution_allowed is False
    assert review.installation_allowed is False
    assert review.provider_switch_allowed is False
    assert review.signal_authority is False
    assert review.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_agent_runtime_economics_watchlists_missing_measurements_and_controls() -> None:
    review = review_agent_runtime_economics(
        replace(
            runtime_economics(),
            measured_power_watts=None,
            privacy_controls=(),
            operational_controls=(),
            reviewer_result=QuantResearchReviewerResult.WATCHLIST,
            rejection_reason="Power, privacy, and operational controls are incomplete.",
        )
    )

    assert review.status is AgentRuntimeEconomicsReviewStatus.WATCHLIST
    assert "POWER_THERMAL_REVIEW_REQUIRED" in review.blockers
    assert "RUNTIME_PRIVACY_CONTROL_REQUIRED" in review.blockers
    assert "RUNTIME_OPERATIONAL_CONTROL_REQUIRED" in review.blockers
    assert "AGENT_RUNTIME_REVIEWER_WATCHLIST" in review.blockers
    assert "LIVE_ORDER_BLOCKED" in review.blockers


def test_agent_runtime_economics_blocks_unavailable_uncited_hype_claim() -> None:
    review = review_agent_runtime_economics(
        replace(
            runtime_economics(),
            source_available=False,
            benchmark_citations=(),
            claimed_monthly_cost_usd=None,
            measured_latency_ms=None,
            measured_tokens_per_second=None,
            reviewer_result=QuantResearchReviewerResult.REJECTED,
            rejection_reason="Source and benchmark evidence unavailable.",
        )
    )

    assert review.status is AgentRuntimeEconomicsReviewStatus.BLOCKED
    assert "AGENT_RUNTIME_SOURCE_UNAVAILABLE" in review.blockers
    assert "RUNTIME_BENCHMARK_CITATION_REQUIRED" in review.blockers
    assert "RUNTIME_COST_MEASUREMENT_REQUIRED" in review.blockers
    assert "RUNTIME_LATENCY_MEASUREMENT_REQUIRED" in review.blockers
    assert "RUNTIME_THROUGHPUT_MEASUREMENT_REQUIRED" in review.blockers
    assert "AGENT_RUNTIME_REVIEWER_REJECTED" in review.blockers
    assert "NO_TRADE_SIGNAL_AUTHORITY" in review.blockers


def test_agent_runtime_economics_rejects_authority_and_invalid_shapes() -> None:
    with pytest.raises(ValueError, match="credential-free HTTPS"):
        replace(runtime_economics(), source_url="http://user:pass@example.com")
    with pytest.raises(ValueError, match="source hash"):
        replace(runtime_economics(), source_sha256="bad")
    with pytest.raises(ValueError, match="finite and non-negative"):
        replace(runtime_economics(), measured_latency_ms=-1.0)
    with pytest.raises(ValueError, match="benchmark citations"):
        replace(runtime_economics(), benchmark_citations=("same", "same"))
    with pytest.raises(ValueError, match="cannot grant authority"):
        replace(runtime_economics(), provider_switch_allowed=True)
    with pytest.raises(ValueError, match="research-only"):
        replace(
            review_agent_runtime_economics(runtime_economics()),
            promotion_status="STAGED_CANDIDATE",
        )
    with pytest.raises(ValueError, match="require human review"):
        AgentRuntimeEconomicsReview(
            artifact_id="artifact",
            title="runtime",
            source_url="https://example.com/runtime",
            source_sha256="f" * 64,
            hardware_profile="local workstation",
            runtime_stack="local loop",
            status=AgentRuntimeEconomicsReviewStatus.RESEARCH_ONLY_RUNTIME_PATTERN,
            reviewer_result=QuantResearchReviewerResult.PASSED,
            blockers=(
                "NO_TRADE_SIGNAL_AUTHORITY",
                "AGENT_RUNTIME_REVIEW_READ_ONLY",
                "LIVE_ORDER_BLOCKED",
            ),
            benchmark_citations=("https://example.com/runtime",),
            privacy_controls=("LOOPBACK_ONLY",),
            operational_controls=("RUNAWAY_LOOP_BUDGET",),
            claimed_monthly_cost_usd=5.0,
            measured_latency_ms=850.0,
            measured_tokens_per_second=42.0,
            measured_power_watts=310.0,
            rejection_reason="none",
        )
    with pytest.raises(ValueError, match="cannot grant authority"):
        replace(
            review_agent_runtime_economics(runtime_economics()),
            installation_allowed=True,
        )
    with pytest.raises(ValueError, match="block live trading"):
        replace(
            review_agent_runtime_economics(runtime_economics()),
            live_eligibility_status="PAPER_APPROVED",
        )


def test_second_brain_memory_accepts_reviewed_local_note_research_only() -> None:
    review = review_second_brain_memory(second_brain_memory())

    assert review.status is SecondBrainMemoryReviewStatus.RESEARCH_ONLY_MEMORY
    assert review.promotion_status == "RESEARCH_ONLY_MEMORY"
    assert review.vault_path_sha256 == "2" * 64
    assert review.topic_tags == (
        "second-brain",
        "research-memory",
        "privacy-boundary",
    )
    assert review.blockers == (
        "NO_TRADE_SIGNAL_AUTHORITY",
        "SECOND_BRAIN_MEMORY_READ_ONLY",
        "HUMAN_REVIEW_REQUIRED",
        "LIVE_ORDER_BLOCKED",
    )
    assert review.execution_allowed is False
    assert review.sync_allowed is False
    assert review.context_export_allowed is False
    assert review.signal_authority is False
    assert review.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_second_brain_memory_keeps_unreviewed_capture_pending() -> None:
    review = review_second_brain_memory(
        replace(
            second_brain_memory(),
            reviewed=False,
            reviewer_result=QuantResearchReviewerResult.WATCHLIST,
            rejection_reason="Captured from social source pending human review.",
        )
    )

    assert review.status is SecondBrainMemoryReviewStatus.CAPTURED
    assert "SECOND_BRAIN_REVIEW_PENDING" in review.blockers
    assert "SECOND_BRAIN_REVIEWER_WATCHLIST" in review.blockers
    assert "LIVE_ORDER_BLOCKED" in review.blockers


def test_second_brain_memory_watchlists_missing_privacy_redaction_staleness() -> None:
    review = review_second_brain_memory(
        replace(
            second_brain_memory(),
            privacy_controls=(),
            redaction_controls=(),
            staleness_policy="",
        )
    )

    assert review.status is SecondBrainMemoryReviewStatus.WATCHLIST
    assert "SECOND_BRAIN_PRIVACY_CONTROL_REQUIRED" in review.blockers
    assert "SECOND_BRAIN_REDACTION_CONTROL_REQUIRED" in review.blockers
    assert "SECOND_BRAIN_STALENESS_POLICY_REQUIRED" in review.blockers
    assert "NO_TRADE_SIGNAL_AUTHORITY" in review.blockers


def test_second_brain_memory_blocks_unavailable_uncited_source() -> None:
    review = review_second_brain_memory(
        replace(
            second_brain_memory(),
            source_available=False,
            evidence_citations=(),
            reviewer_result=QuantResearchReviewerResult.REJECTED,
            rejection_reason="Original source and citations unavailable.",
        )
    )

    assert review.status is SecondBrainMemoryReviewStatus.BLOCKED
    assert "SECOND_BRAIN_SOURCE_UNAVAILABLE" in review.blockers
    assert "SOURCE_CITATION_REQUIRED" in review.blockers
    assert "SECOND_BRAIN_REVIEWER_REJECTED" in review.blockers
    assert "NO_TRADE_SIGNAL_AUTHORITY" in review.blockers


def test_second_brain_memory_rejects_authority_and_invalid_shapes() -> None:
    with pytest.raises(ValueError, match="credential-free HTTPS"):
        replace(second_brain_memory(), source_url="http://user:pass@example.com")
    with pytest.raises(ValueError, match="source hash"):
        replace(second_brain_memory(), source_sha256="bad")
    with pytest.raises(ValueError, match="vault path hash"):
        replace(second_brain_memory(), vault_path_sha256="bad")
    with pytest.raises(ValueError, match="topic tags"):
        replace(second_brain_memory(), topic_tags=("same", "same"))
    with pytest.raises(ValueError, match="cannot grant authority"):
        replace(second_brain_memory(), context_export_allowed=True)
    with pytest.raises(ValueError, match="citations"):
        replace(second_brain_memory(), evidence_citations=("same", "same"))
    with pytest.raises(ValueError, match="privacy controls"):
        replace(second_brain_memory(), privacy_controls=("",))
    with pytest.raises(ValueError, match="redaction controls"):
        replace(second_brain_memory(), redaction_controls=("same", "same"))
    with pytest.raises(ValueError, match="research-only"):
        replace(
            review_second_brain_memory(second_brain_memory()),
            promotion_status="STAGED_CANDIDATE",
        )
    with pytest.raises(ValueError, match="status"):
        replace(
            review_second_brain_memory(second_brain_memory()),
            status="BAD",  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="reviewer result"):
        replace(
            review_second_brain_memory(second_brain_memory()),
            reviewer_result="BAD",  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="cannot be pending"):
        replace(
            review_second_brain_memory(second_brain_memory()),
            blockers=(
                "SECOND_BRAIN_REVIEW_PENDING",
                "NO_TRADE_SIGNAL_AUTHORITY",
                "SECOND_BRAIN_MEMORY_READ_ONLY",
                "HUMAN_REVIEW_REQUIRED",
                "LIVE_ORDER_BLOCKED",
            ),
        )
    with pytest.raises(ValueError, match="require human review"):
        SecondBrainMemoryReview(
            memory_id="memory",
            title="memory",
            source_url="https://example.com/memory",
            source_sha256="1" * 64,
            vault_path_sha256="2" * 64,
            status=SecondBrainMemoryReviewStatus.RESEARCH_ONLY_MEMORY,
            reviewer_result=QuantResearchReviewerResult.PASSED,
            topic_tags=("second-brain",),
            staleness_policy="review monthly",
            blockers=(
                "NO_TRADE_SIGNAL_AUTHORITY",
                "SECOND_BRAIN_MEMORY_READ_ONLY",
                "LIVE_ORDER_BLOCKED",
            ),
            evidence_citations=("https://example.com/memory",),
            privacy_controls=("LOCAL_VAULT_ONLY",),
            redaction_controls=("HASH_PATH_ONLY",),
            rejection_reason="none",
        )
    with pytest.raises(ValueError, match="cannot become a signal"):
        replace(
            review_second_brain_memory(second_brain_memory()),
            blockers=(
                "SECOND_BRAIN_MEMORY_READ_ONLY",
                "HUMAN_REVIEW_REQUIRED",
                "LIVE_ORDER_BLOCKED",
            ),
        )
    with pytest.raises(ValueError, match="cannot grant authority"):
        replace(
            review_second_brain_memory(second_brain_memory()),
            sync_allowed=True,
        )
    with pytest.raises(ValueError, match="cannot grant authority"):
        replace(
            review_second_brain_memory(second_brain_memory()),
            signal_authority=True,
        )
    with pytest.raises(ValueError, match="block live trading"):
        replace(
            review_second_brain_memory(second_brain_memory()),
            live_eligibility_status="PAPER_APPROVED",
        )


def test_second_brain_memory_conflicting_review_requires_reason() -> None:
    review = review_second_brain_memory(
        replace(
            second_brain_memory(),
            reviewer_result=QuantResearchReviewerResult.CONFLICTING,
            rejection_reason="",
        )
    )

    assert review.status is SecondBrainMemoryReviewStatus.WATCHLIST
    assert "SECOND_BRAIN_REVIEWER_CONFLICTING" in review.blockers
    assert "REJECTION_REASON_REQUIRED" in review.blockers


def test_quant_hypothesis_review_accepts_complete_mechanism_as_research_only() -> None:
    review = review_quant_research_hypothesis(quant_hypothesis())

    assert review.status is QuantResearchHypothesisStatus.RESEARCH_ONLY_OPPORTUNITY
    assert review.reviewer_result is QuantResearchReviewerResult.PASSED
    assert review.promotion_status == "RESEARCH_ONLY_QUANT_HYPOTHESIS"
    assert review.blockers == (
        "NO_TRADE_SIGNAL_AUTHORITY",
        "QUANT_HYPOTHESIS_REVIEW_READ_ONLY",
        "LIVE_ORDER_BLOCKED",
    )
    assert review.execution_allowed is False
    assert review.signal_authority is False
    assert review.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_quant_hypothesis_review_watchlists_missing_pipeline_controls() -> None:
    review = review_quant_research_hypothesis(
        QuantResearchHypothesisEvidence(
            hypothesis_id="hotusdt-model-first-v0",
            symbol="HOTUSDT",
            timeframe="1h",
            market_mechanism="",
            measurable_footprint="",
            universe="",
            liquidity_assumption="",
            feature_horizon="",
            oos_requirement="",
            transaction_cost_requirement="",
            reviewer_result=QuantResearchReviewerResult.REJECTED,
        )
    )

    assert review.status is QuantResearchHypothesisStatus.WATCHLIST
    assert "MARKET_MECHANISM_REQUIRED" in review.blockers
    assert "MEASURABLE_FOOTPRINT_REQUIRED" in review.blockers
    assert "RESEARCH_UNIVERSE_REQUIRED" in review.blockers
    assert "LIQUIDITY_ASSUMPTION_REQUIRED" in review.blockers
    assert "FEATURE_HORIZON_REQUIRED" in review.blockers
    assert "SOURCE_CITATION_REQUIRED" in review.blockers
    assert "LEAKAGE_CHECK_REQUIRED" in review.blockers
    assert "OOS_REQUIREMENT_REQUIRED" in review.blockers
    assert "TRANSACTION_COST_REQUIREMENT_REQUIRED" in review.blockers
    assert "ROBUSTNESS_CHECK_REQUIRED" in review.blockers
    assert "MAKER_CHECKER_SEPARATION_REQUIRED" in review.blockers
    assert "QUANT_REVIEWER_REJECTED" in review.blockers
    assert "REJECTION_REASON_REQUIRED" in review.blockers
    assert "LIVE_ORDER_BLOCKED" in review.blockers


def test_quant_hypothesis_review_rejects_authority_and_invalid_shapes() -> None:
    with pytest.raises(ValueError, match="cannot grant authority"):
        replace(quant_hypothesis(), signal_authority=True)
    with pytest.raises(ValueError, match="cannot grant authority"):
        replace(quant_hypothesis(), live_order_authority=True)
    with pytest.raises(ValueError, match="citations"):
        replace(quant_hypothesis(), data_citations=("same", "same"))
    with pytest.raises(ValueError, match="leakage checks"):
        replace(quant_hypothesis(), leakage_checks=("",))
    with pytest.raises(ValueError, match="robustness checks"):
        replace(quant_hypothesis(), robustness_checks=("same", "same"))
    with pytest.raises(ValueError, match="research-only"):
        replace(
            review_quant_research_hypothesis(quant_hypothesis()),
            promotion_status="STAGED_CANDIDATE",
        )
    with pytest.raises(ValueError, match="keep live blocked"):
        QuantResearchHypothesisReview(
            hypothesis_id="hypothesis",
            symbol="HOTUSDT",
            timeframe="1h",
            status=QuantResearchHypothesisStatus.RESEARCH_ONLY_OPPORTUNITY,
            reviewer_result=QuantResearchReviewerResult.PASSED,
            market_mechanism="mechanism",
            measurable_footprint="footprint",
            universe="universe",
            liquidity_assumption="liquidity",
            feature_horizon="horizon",
            oos_requirement="oos",
            transaction_cost_requirement="cost",
            rejection_reason="none",
            blockers=("NO_TRADE_SIGNAL_AUTHORITY",),
            data_citations=("research:quant/hypothesis.json",),
            leakage_checks=("NO_LOOKAHEAD",),
            robustness_checks=("PARAMETER_SENSITIVITY",),
        )
    with pytest.raises(ValueError, match="cannot become a signal"):
        QuantResearchHypothesisReview(
            hypothesis_id="hypothesis",
            symbol="HOTUSDT",
            timeframe="1h",
            status=QuantResearchHypothesisStatus.RESEARCH_ONLY_OPPORTUNITY,
            reviewer_result=QuantResearchReviewerResult.PASSED,
            market_mechanism="mechanism",
            measurable_footprint="footprint",
            universe="universe",
            liquidity_assumption="liquidity",
            feature_horizon="horizon",
            oos_requirement="oos",
            transaction_cost_requirement="cost",
            rejection_reason="none",
            blockers=("LIVE_ORDER_BLOCKED",),
            data_citations=("research:quant/hypothesis.json",),
            leakage_checks=("NO_LOOKAHEAD",),
            robustness_checks=("PARAMETER_SENSITIVITY",),
        )
    with pytest.raises(ValueError, match="cannot grant authority"):
        replace(
            review_quant_research_hypothesis(quant_hypothesis()),
            execution_allowed=True,
        )
    with pytest.raises(ValueError, match="block live trading"):
        replace(
            review_quant_research_hypothesis(quant_hypothesis()),
            live_eligibility_status="PAPER_APPROVED",
        )


def test_volatility_assumption_review_accepts_cited_read_only_evidence() -> None:
    review = review_volatility_assumption(
        VolatilityAssumptionEvidence(
            symbol="HOTUSDT",
            timeframe="4h",
            observed_at=NOW,
            model_family="realized-volatility",
            assumption_name="atr-stop-volatility-budget",
            horizon_days=14,
            sample_size=96,
            realized_volatility=0.42,
            assumed_volatility=0.40,
            evidence_citations=("research:volatility/hotusdt-4h-20260801.json",),
        )
    )

    assert review.status is VolatilityAssumptionReviewStatus.RESEARCH_ONLY
    assert review.promotion_status == "RESEARCH_ONLY_VOLATILITY_ASSUMPTION"
    assert review.execution_allowed is False
    assert review.signal_authority is False
    assert review.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert review.blockers == (
        "NO_TRADE_SIGNAL_AUTHORITY",
        "VOLATILITY_REVIEW_READ_ONLY",
        "LIVE_ORDER_BLOCKED",
    )


def test_volatility_assumption_review_watchlists_black_scholes_spot_limits() -> None:
    review = review_volatility_assumption(
        VolatilityAssumptionEvidence(
            symbol="HOTUSDT",
            timeframe="1d",
            observed_at=NOW,
            model_family="Black-Scholes option-volatility proxy",
            assumption_name="strategic-rebuy-volatility-band",
            horizon_days=30,
            sample_size=45,
            realized_volatility=0.75,
            assumed_volatility=0.50,
            implied_volatility=0.80,
            evidence_citations=(
                "https://www.journals.uchicago.edu/doi/10.1086/260062",
            ),
        )
    )

    assert review.status is VolatilityAssumptionReviewStatus.WATCHLIST
    assert "DERIVATIVES_DATA_SUPPLEMENTARY_ONLY" in review.blockers
    assert "BLACK_SCHOLES_SPOT_LIMITATION_REVIEW_REQUIRED" in review.blockers
    assert "VOLATILITY_ASSUMPTION_DIVERGENCE" in review.blockers
    assert "LIVE_ORDER_BLOCKED" in review.blockers


def test_volatility_assumption_review_blocks_missing_source_and_weak_sample() -> None:
    review = review_volatility_assumption(
        VolatilityAssumptionEvidence(
            symbol="HOTUSDT",
            timeframe="15m",
            observed_at=NOW,
            model_family="realized-volatility",
            assumption_name="intraday-stop-budget",
            horizon_days=2,
            sample_size=12,
            realized_volatility=0.30,
            assumed_volatility=0.31,
        )
    )

    assert review.status is VolatilityAssumptionReviewStatus.BLOCKED
    assert "SOURCE_CITATION_REQUIRED" in review.blockers
    assert "VOLATILITY_SAMPLE_TOO_SMALL" in review.blockers
    assert "NO_TRADE_SIGNAL_AUTHORITY" in review.blockers


def test_volatility_assumption_review_rejects_authority_and_invalid_shapes() -> None:
    with pytest.raises(ValueError, match="cannot grant authority"):
        VolatilityAssumptionEvidence(
            symbol="HOTUSDT",
            timeframe="4h",
            observed_at=NOW,
            model_family="realized-volatility",
            assumption_name="unsafe",
            horizon_days=14,
            sample_size=40,
            realized_volatility=0.42,
            assumed_volatility=0.40,
            evidence_citations=("research:volatility/hotusdt-4h.json",),
            signal_authority=True,
        )
    with pytest.raises(ValueError, match="research-only"):
        VolatilityAssumptionReview(
            symbol="HOTUSDT",
            timeframe="4h",
            model_family="realized-volatility",
            assumption_name="unsafe",
            status=VolatilityAssumptionReviewStatus.RESEARCH_ONLY,
            observed_relative_gap=0.01,
            max_relative_gap=0.25,
            blockers=("NO_TRADE_SIGNAL_AUTHORITY", "LIVE_ORDER_BLOCKED"),
            evidence_citations=("research:volatility/hotusdt-4h.json",),
            promotion_status="STAGED_CANDIDATE",
        )
    with pytest.raises(ValueError, match="horizon"):
        VolatilityAssumptionEvidence(
            symbol="HOTUSDT",
            timeframe="4h",
            observed_at=NOW,
            model_family="realized-volatility",
            assumption_name="invalid",
            horizon_days=0,
            sample_size=40,
            realized_volatility=0.42,
            assumed_volatility=0.40,
        )
    with pytest.raises(ValueError, match="finite and positive"):
        VolatilityAssumptionEvidence(
            symbol="HOTUSDT",
            timeframe="4h",
            observed_at=NOW,
            model_family="realized-volatility",
            assumption_name="invalid",
            horizon_days=14,
            sample_size=40,
            realized_volatility=0.42,
            assumed_volatility=0.0,
        )
    with pytest.raises(ValueError, match="citations"):
        VolatilityAssumptionEvidence(
            symbol="HOTUSDT",
            timeframe="4h",
            observed_at=NOW,
            model_family="realized-volatility",
            assumption_name="invalid",
            horizon_days=14,
            sample_size=40,
            realized_volatility=0.42,
            assumed_volatility=0.40,
            evidence_citations=("same", "same"),
        )
    with pytest.raises(ValueError, match="notes"):
        VolatilityAssumptionEvidence(
            symbol="HOTUSDT",
            timeframe="4h",
            observed_at=NOW,
            model_family="realized-volatility",
            assumption_name="invalid",
            horizon_days=14,
            sample_size=40,
            realized_volatility=0.42,
            assumed_volatility=0.40,
            notes=("",),
        )
    with pytest.raises(ValueError, match="status"):
        VolatilityAssumptionReview(
            symbol="HOTUSDT",
            timeframe="4h",
            model_family="realized-volatility",
            assumption_name="invalid",
            status="BAD",  # type: ignore[arg-type]
            observed_relative_gap=0.01,
            max_relative_gap=0.25,
            blockers=("NO_TRADE_SIGNAL_AUTHORITY", "LIVE_ORDER_BLOCKED"),
            evidence_citations=("research:volatility/hotusdt-4h.json",),
        )
    with pytest.raises(ValueError, match="non-negative"):
        VolatilityAssumptionReview(
            symbol="HOTUSDT",
            timeframe="4h",
            model_family="realized-volatility",
            assumption_name="invalid",
            status=VolatilityAssumptionReviewStatus.RESEARCH_ONLY,
            observed_relative_gap=-0.01,
            max_relative_gap=0.25,
            blockers=("NO_TRADE_SIGNAL_AUTHORITY", "LIVE_ORDER_BLOCKED"),
            evidence_citations=("research:volatility/hotusdt-4h.json",),
        )
    with pytest.raises(ValueError, match="threshold"):
        review_volatility_assumption(
            VolatilityAssumptionEvidence(
                symbol="HOTUSDT",
                timeframe="4h",
                observed_at=NOW,
                model_family="realized-volatility",
                assumption_name="invalid",
                horizon_days=14,
                sample_size=40,
                realized_volatility=0.42,
                assumed_volatility=0.40,
                evidence_citations=("research:volatility/hotusdt-4h.json",),
            ),
            max_relative_gap=0.0,
        )
    with pytest.raises(ValueError, match="sample size"):
        review_volatility_assumption(
            VolatilityAssumptionEvidence(
                symbol="HOTUSDT",
                timeframe="4h",
                observed_at=NOW,
                model_family="realized-volatility",
                assumption_name="invalid",
                horizon_days=14,
                sample_size=40,
                realized_volatility=0.42,
                assumed_volatility=0.40,
                evidence_citations=("research:volatility/hotusdt-4h.json",),
            ),
            min_sample_size=1,
        )
    with pytest.raises(ValueError, match="keep live blocked"):
        VolatilityAssumptionReview(
            symbol="HOTUSDT",
            timeframe="4h",
            model_family="realized-volatility",
            assumption_name="invalid",
            status=VolatilityAssumptionReviewStatus.RESEARCH_ONLY,
            observed_relative_gap=0.01,
            max_relative_gap=0.25,
            blockers=("NO_TRADE_SIGNAL_AUTHORITY",),
            evidence_citations=("research:volatility/hotusdt-4h.json",),
        )
    with pytest.raises(ValueError, match="cannot become a signal"):
        VolatilityAssumptionReview(
            symbol="HOTUSDT",
            timeframe="4h",
            model_family="realized-volatility",
            assumption_name="invalid",
            status=VolatilityAssumptionReviewStatus.RESEARCH_ONLY,
            observed_relative_gap=0.01,
            max_relative_gap=0.25,
            blockers=("LIVE_ORDER_BLOCKED",),
            evidence_citations=("research:volatility/hotusdt-4h.json",),
        )
    with pytest.raises(ValueError, match="cannot grant authority"):
        VolatilityAssumptionReview(
            symbol="HOTUSDT",
            timeframe="4h",
            model_family="realized-volatility",
            assumption_name="invalid",
            status=VolatilityAssumptionReviewStatus.RESEARCH_ONLY,
            observed_relative_gap=0.01,
            max_relative_gap=0.25,
            blockers=("NO_TRADE_SIGNAL_AUTHORITY", "LIVE_ORDER_BLOCKED"),
            evidence_citations=("research:volatility/hotusdt-4h.json",),
            execution_allowed=True,
        )
    with pytest.raises(ValueError, match="block live trading"):
        VolatilityAssumptionReview(
            symbol="HOTUSDT",
            timeframe="4h",
            model_family="realized-volatility",
            assumption_name="invalid",
            status=VolatilityAssumptionReviewStatus.RESEARCH_ONLY,
            observed_relative_gap=0.01,
            max_relative_gap=0.25,
            blockers=("NO_TRADE_SIGNAL_AUTHORITY", "LIVE_ORDER_BLOCKED"),
            evidence_citations=("research:volatility/hotusdt-4h.json",),
            live_eligibility_status="PAPER_APPROVED",
        )


def test_catalog_rejects_unsafe_sources_duplicates_and_invalid_shapes() -> None:
    item = entry()
    with pytest.raises(ValueError, match="HTTPS"):
        replace(item, source_url="http://user:pass@example.com")
    catalog = ResearchCatalog().add(item)
    with pytest.raises(ValueError, match="already exists"):
        catalog.add(item)
    with pytest.raises(KeyError):
        catalog.update(entry("missing"))


def test_catalog_entry_preserves_evidence_integrity_and_no_authority() -> None:
    item = entry()
    with pytest.raises(ValueError, match="text fields"):
        replace(item, title="")
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(item, discovered_at=datetime(2026, 7, 13))
    with pytest.raises(ValueError, match="artifact identities"):
        replace(item, artifact_ids=("same", "same"))
    with pytest.raises(ValueError, match="evidence groups"):
        replace(item, data_requirements=())
    with pytest.raises(ValueError, match="staged catalog candidate"):
        replace(item, status=CatalogStatus.STAGED_CANDIDATE)
    with pytest.raises(ValueError, match="paper approval requires"):
        replace(item, status=CatalogStatus.PAPER_APPROVED)
    with pytest.raises(ValueError, match="cannot authorize"):
        replace(item, execution_allowed=True)
