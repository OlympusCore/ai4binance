# ruff: noqa: E501
from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from ai4binance.cli.opportunity_radar_persistence import (
    write_opportunity_radar_snapshot,
)
from ai4binance.config import Settings
from ai4binance.enterprise import ykb_report as ykb_module
from ai4binance.enterprise.ykb_report import (
    SemiAutoControlManagement,
    YkbContextItem,
    YkbExecutiveBrief,
    YkbFinancialSituation,
    YkbFuturesPositionRow,
    YkbInventoryHeatmapRow,
    YkbOpenOrderRow,
    YkbOpportunityBrief,
    YkbSpotAssetRow,
    YkbValidationDigest,
    YkbWalletPositionManagement,
    _agent_audit_command_names,
    _asset_action_hint,
    _asset_class,
    _asset_liquidity_bucket,
    _asset_opportunity_review_hint,
    _aware_datetime,
    _decimal,
    _financial_fit,
    _find_halt_review_artifact_for_ref,
    _funding_recommendation,
    _halted_scope_artifact_path,
    _halted_scope_improvement_candidate,
    _halted_scope_reset_summary,
    _halted_scope_review_ref,
    _headline,
    _highest_bucket,
    _inventory_heatmap_rows,
    _is_directional_executive_candidate,
    _is_executive_trade_plan_row,
    _is_opportunity_radar_scope_symbol,
    _is_relevant_open_web_article,
    _is_web_article_record,
    _istanbul_time_text,
    _latest_validation_metric_value,
    _latest_validation_wallet_kpi_context,
    _loss_streak_escalated_risk_note,
    _loss_streak_halted_scope_lines,
    _loss_streak_pattern_key,
    _loss_streak_priority_queue_summary,
    _loss_streak_repeat_offender_state,
    _loss_streak_review_priority,
    _loss_streak_review_rationale,
    _loss_streak_scope_escalation_state,
    _loss_streak_scope_first_action,
    _loss_streak_wallet_stress_context,
    _mapping,
    _markdown_table,
    _metric_texts,
    _next_action,
    _open_web_article_impact,
    _open_web_retrieved_document,
    _opportunity_funnel_payload,
    _portfolio_funding_recommendation,
    _position_side_from_quantity,
    _quote_liquidity_bucket,
    _read_open_web_ledger_mappings,
    _reportable_spot_assets,
    _requested_action,
    _require_unique_nonblank,
    _resolve_halt_review_artifact_path,
    _run_card_playbook,
    _runtime_feed_context_items,
    _runtime_open_web_article_context_items,
    _safe_int,
    _score_decimal,
    _sequence,
    _spot_asset_value_report_state,
    _text_tuple,
    _timeframe_value,
    _trade_leverage,
    _trade_plan_value,
    _trade_side,
    _tuning_parameter_texts,
    _unit_float,
    _virtual_runtime_counterfactual_note,
    _virtual_runtime_evidence_context,
    _virtual_runtime_evidence_snapshot,
    _virtual_runtime_market_acceptance_context,
    _virtual_runtime_priority_signal,
    _wallet_position_management,
    _watchlist_gap_summary,
    build_ykb_executive_brief,
)
from ai4binance.external_intel.core.enums import RetrievalStatus, SourceType
from ai4binance.external_intel.core.models import (
    ExternalEvidence,
    ExternalObservation,
    RetrievedDocument,
)
from ai4binance.external_intel.storage.open_web import (
    CachedWebRecord,
    OpenWebEvidenceStore,
)
from ai4binance.governance import (
    DgeDecisionStatus,
    DgeMarketAction,
    GovernedDecision,
)
from ai4binance.opportunity_radar import build_opportunity_radar_snapshot
from ai4binance.ops.auto_audit_loop import AutoAuditCycle, AutoAuditLoopResult
from ai4binance.schemas import DataQuality, MarketSnapshot, OHLCVCandle

NOW = datetime(2026, 8, 8, 15, 0, tzinfo=UTC)


def test_markdown_table_renderer_aligns_raw_header_and_data_columns() -> None:
    lines = _markdown_table(
        ("Koin", "Timeframe", "Sonraki Aksiyon"),
        (("ETHUSDT", "1h", "COMPLETE_BACKTEST_WALK_FORWARD_OOS"),),
    )

    assert lines[0] == "| Koin    | Timeframe | Sonraki Aksiyon                    |"
    assert lines[2] == "| ETHUSDT | 1h        | COMPLETE_BACKTEST_WALK_FORWARD_OOS |"
    assert _pipe_positions(lines[0]) == _pipe_positions(lines[2])


def test_ykb_brief_combines_auto_audit_dge_opportunities_and_financial_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(monkeypatch, tmp_path)

    brief = build_ykb_executive_brief(
        settings,
        repository_root=tmp_path,
        symbol="ETHUSDT",
        observed_at=NOW,
        portfolio_builder=lambda settings: _portfolio_payload(),
        opportunities_builder=lambda settings, symbol: _opportunities_payload(symbol),
        auto_audit_runner=lambda *args, **kwargs: _auto_audit(tmp_path),
    )

    assert brief.status == "RUNNING_WITH_BLOCKERS"
    assert brief.auto_audit_status == "RUNNING_WITH_BLOCKERS"
    assert brief.auto_audit_recommendations == ("resolve:runtime:RUNTIME_DEGRADED",)
    assert brief.agent_audit_status == "REVISION_REQUIRED"
    assert brief.agent_audit_recommendations
    assert brief.vnext_gap_status == "RUNNING_WITH_BLOCKERS"
    assert "VNEXT-00-AUDIT-BASELINE" in brief.vnext_gap_top_gaps
    assert brief.latest_validation.status == "BACKTEST_RUN_CARD_MISSING"
    assert brief.important_context[0].category == "IMPORTANT_CONTEXT"
    assert brief.financial_situation.value_disclosure == "REDACTED_SUMMARY_ONLY"
    assert brief.financial_situation.spot_asset_count == 3
    assert brief.financial_situation.futures_position_count == 1
    assert brief.financial_situation.open_order_count == 2
    assert brief.financial_situation.spot_assets[0].asset == "USDT"
    assert brief.financial_situation.spot_assets[0].asset_class == "QUOTE_CASH"
    assert brief.financial_situation.spot_assets[1].value_bucket == "MEDIUM"
    assert brief.financial_situation.spot_assets[2].asset == "DOGE"
    assert brief.financial_situation.spot_assets[2].value_report_state == (
        "DUST_LT_2_USDT_OMITTED_FROM_PUBLIC_HEATMAP"
    )
    assert all(
        row.inventory_group != "DOGE"
        for row in brief.financial_situation.inventory_heatmap
    )
    assert brief.financial_situation.futures_positions[0].symbol == "BTCUSDT"
    assert brief.financial_situation.open_orders[0].market == "SPOT"
    assert brief.financial_situation.inventory_heatmap[0].liquidity_bucket == "READY"
    assert brief.wallet_position_management.recommendation == (
        "FIX_WALLET_RECONCILIATION_BEFORE_POSITION_ACTION"
    )
    assert brief.wallet_position_management.spot_open_order_count == 1
    assert brief.wallet_position_management.futures_open_order_count == 1
    assert len(brief.opportunities) == 1
    opportunity = brief.opportunities[0]
    assert opportunity.symbol == "ETHUSDT"
    assert opportunity.entry == "PENDING_VALIDATED_LEVEL"
    assert opportunity.dge_status in {"WATCH_ONLY", "NO_TRADE"}
    assert opportunity.governed_action == "NO_TRADE"
    assert opportunity.funding_requirement == "MANUAL_LIQUIDITY_REVIEW_REQUIRED"
    assert opportunity.required_capital_bucket == "UNKNOWN"
    assert opportunity.free_quote_sufficiency == "UNKNOWN_RECONCILIATION_BLOCKED"
    assert opportunity.external_capital_policy == "NO_EXTERNAL_CAPITAL_ALLOWED"
    assert opportunity.conversion_or_transfer_policy == "AUTO_MONEY_MOVEMENT_BLOCKED"
    assert "VAL.OOS_NOT_VALIDATED" in opportunity.blockers
    assert brief.semi_auto_control.mode == "SEMI_AUTO_CONTROL_MANAGEMENT"
    assert brief.semi_auto_control.execution_allowed is False
    assert brief.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert brief.json_path.exists()
    assert brief.latest_json_path.exists()
    assert brief.markdown_path.exists()
    assert brief.private_financial_json_path.exists()
    assert brief.private_financial_markdown_path.exists()
    persisted = json.loads(brief.json_path.read_text(encoding="utf-8"))
    rendered = brief.markdown_path.read_text(encoding="utf-8")
    private_financial = brief.private_financial_markdown_path.read_text(
        encoding="utf-8"
    )
    normalized_rendered = _normalize_table_spacing(rendered)
    assert persisted["command"] == "ykb-report"
    assert persisted["virtual_runtime_evidence"]["available"] is False
    assert persisted["virtual_runtime_evidence"]["status"] == "UNAVAILABLE"
    assert persisted["virtual_runtime_evidence"]["net_return"] is None
    assert persisted["virtual_runtime_evidence"]["max_drawdown"] is None
    assert persisted["virtual_runtime_evidence"]["oos_expectancy_usdt"] is None
    assert persisted["virtual_runtime_priority_signal"] == "UNAVAILABLE"
    assert persisted["opportunity_funnel"]["visible_research_opportunities"] == 1
    assert persisted["opportunity_funnel"]["virtual_market_ready_trade_plans"] == 0
    assert persisted["opportunity_funnel"]["loss_streak_halted_visible_research"] == 0
    assert persisted["opportunity_funnel"]["loss_streak_halted_scopes"] == []
    assert persisted["opportunity_funnel"]["loss_streak_halt_review_refs"] == []
    assert (
        persisted["opportunity_funnel"]["loss_streak_halt_review_artifact_paths"] == []
    )
    assert persisted["opportunity_funnel"]["loss_streak_halt_review_artifacts"] == []
    assert persisted["opportunity_funnel"]["loss_streak_halted_primary_setup"] == "NONE"
    assert persisted["opportunity_funnel"]["loss_streak_halted_setup_clusters"] == []
    assert (
        persisted["opportunity_funnel"]["loss_streak_halted_primary_pattern"] == "NONE"
    )
    assert persisted["opportunity_funnel"]["loss_streak_halted_pattern_clusters"] == []
    assert (
        persisted["opportunity_funnel"]["loss_streak_repeat_offender_visible_research"]
        == 0
    )
    assert persisted["opportunity_funnel"]["loss_streak_repeat_offender_scopes"] == []
    assert persisted["opportunity_funnel"]["loss_streak_priority_queue_summary"] == (
        "aktif review adayi yok."
    )
    assert (
        persisted["opportunity_funnel"]["loss_streak_high_escalation_visible_research"]
        == 0
    )
    assert persisted["opportunity_funnel"]["loss_streak_high_escalation_scopes"] == []
    assert (
        persisted["opportunity_funnel"]["loss_streak_fragile_edge_visible_research"]
        == 0
    )
    assert persisted["opportunity_funnel"]["loss_streak_fragile_edge_scopes"] == []
    assert persisted["opportunities"][0]["loss_streak_review_priority"] == (
        "P2_ARTIFACT_RESOLUTION_REQUIRED"
    )
    assert persisted["opportunities"][0]["loss_streak_review_rationale"] == (
        "Halt review artifact is unresolved and must be recovered before analysis."
    )
    assert (
        persisted["opportunities"][0]["loss_streak_escalation_state"] == "NO_ESCALATION"
    )
    assert persisted["opportunities"][0]["loss_streak_first_action"] == (
        "STANDARD_BOUNDED_REVIEW"
    )
    assert persisted["opportunity_funnel"]["live_eligibility_status"] == (
        "LIVE_ORDER_BLOCKED"
    )
    assert persisted["private_financial_report"]["cloud_share_allowed"] is False
    assert "runtime/state/private/ykb" in persisted["private_financial_report"][
        "json_path"
    ].replace("\\", "/")
    assert "runtime/reports/ykb" in str(brief.markdown_path).replace("\\", "/")
    assert "## ELI10" in rendered
    assert "## Zaman Standardi" in rendered
    assert "## Son 3 YKB Rapor Tarihcesi" in rendered
    assert "timezone: `Europe/Istanbul`" in rendered
    assert "report_observed_at: `2026-08-08T18:00:00+03:00`" in rendered
    assert "_tr.md" in str(brief.markdown_path)
    assert brief.markdown_path.name in rendered
    assert "## Teknolojik Gelisme Firsatlari ve Oneriler" in rendered
    assert "## Spot Tarafi Firsat Plani" in rendered
    assert "## Futures Tarafi Firsat Plani" in rendered
    assert (
        "Virtual runtime counterfactual note: UNAVAILABLE (virtual runtime evidence mevcut degil)."
    ) in rendered
    assert "Virtual runtime priority signal: UNAVAILABLE" in rendered
    assert "#### Seviyeleri Hazir Trade Plan Adaylari (Live Bloklu)" in rendered
    assert "#### Kacirma Riski Yuksek Izleme / Validasyon Adaylari" in rendered
    watchlist_section = _section(
        rendered,
        "#### Kacirma Riski Yuksek Izleme / Validasyon Adaylari",
    )
    assert (
        "| ETHUSDT | 1h | SPOT | breakout_retest | BUY | 1x | 64.0 | 0.61 |"
        in _normalize_table_spacing(watchlist_section)
    )
    assert "SL/E/TP_VALIDATION_MISSING" in watchlist_section
    assert (
        "| Koin | Timeframe | Market | Setup | Side | Leverage | SL | E | TP1 | "
        "TP2 | TP3 | RR | DGE | Aksiyon |" in normalized_rendered
    )
    assert "## Opportunity Funnel" in rendered
    assert "visible_research_opportunities: `1`" in rendered
    assert "virtual_market_ready_trade_plans: `0`" in rendered
    assert "loss_streak_halted_visible_research: `0`" in rendered
    assert "loss_streak_halted_spot_visible_research: `0`" in rendered
    assert "loss_streak_halted_futures_visible_research: `0`" in rendered
    assert "loss_streak_halt_review_refs: `-`" in rendered
    assert "loss_streak_halt_review_artifact_paths: `-`" in rendered
    assert "loss_streak_halt_reviews_with_resolved_artifacts: `0`" in rendered
    assert "loss_streak_halt_reviews_pending_artifact_resolution: `0`" in rendered
    assert "loss_streak_halted_primary_setup: `NONE`" in rendered
    assert "loss_streak_halted_setup_clusters: `-`" in rendered
    assert "loss_streak_halted_primary_pattern: `NONE`" in rendered
    assert "loss_streak_halted_pattern_clusters: `-`" in rendered
    assert "loss_streak_repeat_offender_visible_research: `0`" in rendered
    assert "loss_streak_repeat_offender_scopes: `-`" in rendered
    assert "loss_streak_priority_queue_summary: `aktif review adayi yok.`" in rendered
    assert "loss_streak_high_escalation_visible_research: `0`" in rendered
    assert "loss_streak_high_escalation_scopes: `-`" in rendered
    assert "loss_streak_fragile_edge_visible_research: `0`" in rendered
    assert "loss_streak_fragile_edge_scopes: `-`" in rendered
    assert "## Loss-Streak Halted Scopes" in rendered
    assert "## Immediate Actions" in rendered
    assert (
        "Loss-streak nedeniyle durdurulan gorunur scope yok; bounded autonomy "
        "bu raporda blocker bazli izleniyor."
        in _section(rendered, "## Loss-Streak Halted Scopes")
    )
    assert (
        "Immediate escalation aksiyonu yok; bounded halt review kuyrugu normal sirada izleniyor."
        in _section(rendered, "## Immediate Actions")
    )
    assert (
        "VIRTUAL_MARKET loss-streak durdurma gorunumu: 0 gorunur aday ard arda "
        "zarar siniri nedeniyle beklemeye alinmis durumda." in rendered
    )
    assert (
        "Loss-streak cluster odagi: `NONE` ana tekrar eden setup olarak izleniyor."
        in rendered
    )
    assert (
        "Pattern cluster odagi: `NONE` en baskin market/setup/side tekrar desenidir; "
        "repeat offender sayisi 0." in rendered
    )
    assert "Oncelikli bounded halt review kuyrugu: aktif review adayi yok." in rendered
    assert "Wallet stress baglami: HIGH_WALLET_STRESS" in rendered
    assert "Wallet KPI ozeti: UNAVAILABLE" in rendered
    assert "Virtual runtime evidence ozeti: UNAVAILABLE" in rendered
    assert "Escalated risk note: UNAVAILABLE" in rendered
    assert "loss_streak_review_priority: `P2_ARTIFACT_RESOLUTION_REQUIRED`" in rendered
    assert (
        "loss_streak_review_rationale: "
        "`Halt review artifact is unresolved and must be recovered before analysis.`"
        in rendered
    )
    assert "loss_streak_escalation_state: `NO_ESCALATION`" in rendered
    assert "loss_streak_first_action: `STANDARD_BOUNDED_REVIEW`" in rendered
    assert "No virtual-market-ready SPOT trade plan rows." in _section(
        rendered,
        "## Spot Tarafi Firsat Plani",
    )
    assert "Firsat yok; tablo satiri olusturulmadi." not in rendered
    assert "| ETHUSDT |" not in _normalize_table_spacing(
        _section(rendered, "## Spot Tarafi Firsat Plani")
    )
    assert "vnext_gap_status" in rendered
    assert "REDACTED_SUMMARY_ONLY" in rendered
    assert "## Wallet / Position / Funding Recommendation" in rendered
    assert "## Spot Inventory Heatmap" in rendered
    assert "spot_inventory_reportable_count_ge_2_usdt: `2`" in rendered
    assert "spot_inventory_dust_omitted_count_lt_2_usdt: `1`" in rendered
    assert "## Open Orders" in rendered
    assert "## Futures Exposure Review" in rendered
    assert "QUOTE_CASH" in rendered
    assert "Spot/Futures Firsat Yonetimi" in rendered
    assert "REVIEW_OPEN_ORDER_THEN_SCAN_SPOT_REBUY_OR_FUTURES_HEDGE" in rendered
    assert "yalniz Wallet/Value heatmap filtresidir" in rendered
    assert "Spot/Futures teknik firsat tablolarini susturmaz" in rendered
    assert "DOGE" not in _section(rendered, "## Spot Inventory Heatmap")
    assert "AUTO_MONEY_MOVEMENT_BLOCKED" in rendered
    assert "total_wallet_balance" not in rendered
    assert "market_value_usdt" not in rendered
    assert "## Local-Only Binance Finansal Deger Eki" in rendered
    assert "cloud_share_allowed: `false`" in rendered
    assert "DGE/Auto-Audit oncelikli karar listesi" in rendered
    assert "Privacy leak guard" in rendered
    assert "Financial leak guard" in rendered
    assert "market_value_usdt" in private_financial
    assert "free_market_value_usdt" in private_financial
    assert "DOGE" in private_financial
    assert "YKB Finansal Deger Yonetim Onerileri" in private_financial
    assert "FIX_RECONCILIATION_BEFORE_ANY_CAPITAL_DECISION" in private_financial
    assert "NO_GITHUB_CLOUD_SHARE" in private_financial


def test_ykb_report_surfaces_runtime_context_validation_and_trade_plan_sections(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(monkeypatch, tmp_path)
    _write_run_card(settings.validation_artifact_directory, "HOTUSDT")
    _write_runtime_research_report(settings.runtime_opportunity_report_path)

    brief = build_ykb_executive_brief(
        settings,
        repository_root=tmp_path,
        symbol="HOTUSDT",
        observed_at=NOW,
        portfolio_builder=lambda settings: _portfolio_payload(blockers=()),
        opportunities_builder=lambda settings, symbol: _spot_futures_payload(symbol),
        auto_audit_runner=lambda *args, **kwargs: _auto_audit(tmp_path, blockers=()),
    )

    assert brief.technology_opportunities[0].title == (
        "Low-latency inference upgrade launch"
    )
    assert brief.important_context[0].category == "SENTIMENT_SHIFT_REVIEW"
    assert brief.latest_validation.latest_run_id == "run:hot-latest"
    assert "ema_fast=9" in brief.latest_validation.tuning_parameters
    assert sum(1 for item in brief.opportunities if item.market == "SPOT") == 1
    assert sum(1 for item in brief.opportunities if "FUTURES" in item.market) == 1

    spot = next(item for item in brief.opportunities if item.market == "SPOT")
    futures = next(item for item in brief.opportunities if "FUTURES" in item.market)
    assert (spot.symbol, spot.entry, spot.stop_loss, spot.take_profit_3) == (
        "HOTUSDT",
        "0.000345",
        "0.000331",
        "0.000390",
    )
    assert (
        futures.symbol,
        futures.entry,
        futures.stop_loss,
        futures.take_profit_3,
        futures.trade_side,
        futures.leverage,
    ) == (
        "BTCUSDT",
        "65000",
        "63200",
        "70400",
        "LONG",
        "3x",
    )

    rendered = brief.markdown_path.read_text(encoding="utf-8")
    normalized_rendered = _normalize_table_spacing(rendered)
    assert (
        "| HOTUSDT | 1h | SPOT | support_reclaim | BUY | 1x | 0.000331 | 0.000345 | "
        "0.000360 | 0.000375 | 0.000390 | 2 |" in normalized_rendered
    )
    assert (
        "| BTCUSDT | 4h | USD_M_FUTURES | breakout_retest | LONG | 3x | "
        "63200 | 65000 | "
        "66800 | 68600 | 70400 | 2 |" in normalized_rendered
    )
    assert "fine_tuning_parameters" in rendered
    assert "backtest_run_created_at: `2026-08-08T18:00:00+03:00`" in rendered
    assert "Firsat ve Oneri Ozeti" in rendered
    assert "#### Seviyeleri Hazir Trade Plan Adaylari (Live Bloklu)" in rendered
    trade_plan_summary = _section(
        rendered,
        "#### Seviyeleri Hazir Trade Plan Adaylari (Live Bloklu)",
    )
    normalized_trade_plan_summary = _normalize_table_spacing(trade_plan_summary)
    assert (
        "| HOTUSDT | 1h | SPOT | support_reclaim | BUY | 1x | 2 |"
        in normalized_trade_plan_summary
    )
    assert (
        "| BTCUSDT | 4h | USD_M_FUTURES | breakout_retest | LONG | 3x | 2 |"
        in normalized_trade_plan_summary
    )
    assert (
        "| Ne olmus? | Kim soyledi? | Nereden dogrulanir? | Ne zaman oldu? | "
        "Etki | AI4BINANCE icin ne yapilabilir? | Sisteme Artisi | "
        "Sisteme Eksisi | YKB Onay Notu |" in normalized_rendered
    )
    technology_table = _table_lines(
        _section(rendered, "## Teknolojik Gelisme Firsatlari ve Oneriler")
    )
    assert _pipe_positions(technology_table[0]) == _pipe_positions(technology_table[2])
    spot_table = _table_lines(_section(rendered, "## Spot Tarafi Firsat Plani"))
    assert _pipe_positions(spot_table[0]) == _pipe_positions(spot_table[2])
    assert "https://tech.example/update-1" in rendered
    assert "Latency evidence improves scanner timing decisions." in rendered
    assert "Requires local benchmark and rollback proof." in rendered
    assert "Approve research spike only." in rendered
    assert "dogrulama_linki" in rendered
    assert "UNAVAILABLE" not in _section(rendered, "## Spot Tarafi Firsat Plani")
    assert "UNAVAILABLE" not in _section(rendered, "## Futures Tarafi Firsat Plani")


def test_ykb_report_uses_runtime_feed_fallback_when_opportunity_report_is_empty(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(monkeypatch, tmp_path)
    _write_run_card(settings.validation_artifact_directory, "BTCUSDT")
    _write_empty_runtime_research_report(settings.runtime_opportunity_report_path)
    _append_jsonl(
        settings.runtime_technology_feed_path,
        {
            "as_of": NOW.isoformat(),
            "category": "binance-market-data-latency",
            "development_id": "binance-spot-sbe-depth-20ms",
            "impact": "HIGH",
            "opportunity_hint": "Review scanner latency assumptions.",
            "source": "Binance Developer Docs",
            "source_url": "https://developers.binance.com/example",
            "symbol": "BTCUSDT",
            "system_benefit": "Order-book latency assumptions become auditable.",
            "system_tradeoff": "Requires adapter compatibility and soak proof.",
            "title": "Binance Spot SBE depth speed changed",
            "ykb_approval_hint": "Approve report-only validation task.",
        },
    )
    _append_jsonl(
        settings.runtime_news_feed_path,
        {
            "event_id": "coindesk-btc-risk",
            "impact": "HIGH",
            "scheduled_at": NOW.isoformat(),
            "source": "CoinDesk",
            "source_url": "https://www.coindesk.com/example",
            "symbol": "BTCUSDT",
            "title": "BTC volatility risk context",
        },
    )

    brief = build_ykb_executive_brief(
        settings,
        repository_root=tmp_path,
        symbol="BTCUSDT",
        observed_at=NOW,
        portfolio_builder=lambda settings: _portfolio_payload(blockers=()),
        opportunities_builder=lambda settings, symbol: _empty_opportunities_payload(
            symbol
        ),
        auto_audit_runner=lambda *args, **kwargs: _auto_audit(tmp_path, blockers=()),
    )

    rendered = brief.markdown_path.read_text(encoding="utf-8")
    assert brief.technology_opportunities[0].title == (
        "Binance Spot SBE depth speed changed"
    )
    assert brief.important_context[0].title == "BTC volatility risk context"
    assert "https://developers.binance.com/example" in rendered
    assert "Order-book latency assumptions become auditable." in rendered
    assert "Requires adapter compatibility and soak proof." in rendered
    assert "Approve report-only validation task." in rendered
    assert "https://www.coindesk.com/example" in rendered
    assert "backtest_run_created_at: `2026-08-08T18:00:00+03:00`" in rendered
    assert (
        "No visible SPOT research candidate and no virtual-market-ready trade plan row."
        in rendered
    )
    assert "Firsat yok; tablo satiri olusturulmadi." not in rendered
    assert "FIRSAT_YOK" not in rendered
    assert "ADAY_YOK" not in rendered


def test_ykb_report_surfaces_open_web_article_pros_cons_with_ykb_approval(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(monkeypatch, tmp_path)
    _write_run_card(settings.validation_artifact_directory, "BTCUSDT")
    _write_empty_runtime_research_report(settings.runtime_opportunity_report_path)
    _write_open_web_article(settings.open_web_evidence_ledger_path)

    brief = build_ykb_executive_brief(
        settings,
        repository_root=tmp_path,
        symbol="BTCUSDT",
        observed_at=NOW,
        portfolio_builder=lambda settings: _portfolio_payload(blockers=()),
        opportunities_builder=lambda settings, symbol: _empty_opportunities_payload(
            symbol
        ),
        auto_audit_runner=lambda *args, **kwargs: _auto_audit(tmp_path, blockers=()),
    )

    rendered = brief.markdown_path.read_text(encoding="utf-8")
    open_web_item = next(
        item
        for item in brief.technology_opportunities
        if item.title.startswith("Web article:")
    )
    assert open_web_item.source == "GitHub Blog"
    assert open_web_item.source_url == "https://github.blog/open-web-rag/"
    assert open_web_item.system_benefit.startswith("WEB_ARTICLE_ARTI:")
    assert open_web_item.system_tradeoff.startswith("WEB_ARTICLE_EKSI:")
    assert open_web_item.ykb_approval_hint == (
        "YKB_APPROVAL_REQUIRED_FOR_VALIDATION_ONLY_LIVE_ORDER_BLOCKED"
    )
    assert open_web_item.recommendation == (
        "YKB_ONAYI_ILE_RESEARCH_SPIKE_UYGULANABILIR_PRODUCTION_DEGIL"
    )
    assert "WEB_ARTICLE_ARTI:" in rendered
    assert "WEB_ARTICLE_EKSI:" in rendered
    assert "YKB_APPROVAL_REQUIRED_FOR_VALIDATION_ONLY_LIVE_ORDER_BLOCKED" in rendered
    assert brief.execution_allowed is False
    assert brief.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_ykb_dust_inventory_filter_does_not_hide_symbol_trade_opportunities(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(monkeypatch, tmp_path)
    _write_run_card(settings.validation_artifact_directory, "DOGEUSDT")

    brief = build_ykb_executive_brief(
        settings,
        repository_root=tmp_path,
        symbol="DOGEUSDT",
        observed_at=NOW,
        portfolio_builder=lambda settings: _portfolio_payload(),
        opportunities_builder=lambda settings, symbol: (
            _dogeusdt_opportunities_payload()
        ),
        auto_audit_runner=lambda *args, **kwargs: _auto_audit(tmp_path),
    )

    rendered = brief.markdown_path.read_text(encoding="utf-8")
    inventory_section = _section(rendered, "## Spot Inventory Heatmap")
    spot_section = _section(rendered, "## Spot Tarafi Firsat Plani")

    assert "DOGE" not in inventory_section
    assert "DOGEUSDT" in spot_section
    assert (
        "| DOGEUSDT | 1h | SPOT | support_reclaim | BUY | 1x | 0.120 | 0.125 | "
        "0.132 | 0.138 | 0.145 | 2.5 |" in _normalize_table_spacing(spot_section)
    )
    assert "opportunity_radar_scope" in rendered
    assert "Wallet/Value, dust veya envanter heatmap esigi" in rendered
    assert "firsat radarini filtreleyemez" in rendered
    assert "LIVE_ORDER_BLOCKED" in rendered
    assert brief.execution_allowed is False


def test_ykb_opportunity_radar_scope_excludes_only_non_coin_token_classes() -> None:
    assert _is_opportunity_radar_scope_symbol("DOGEUSDT") is True
    assert _is_opportunity_radar_scope_symbol("HOTUSDT") is True
    assert _is_opportunity_radar_scope_symbol("BTCUSDT") is True
    assert _is_opportunity_radar_scope_symbol("USDCUSDT") is False
    assert _is_opportunity_radar_scope_symbol("WBTCUSDT") is False
    assert _is_opportunity_radar_scope_symbol("BTCUPUSDT") is False


def test_ykb_fail_closed_dataclasses_reject_authority_and_bad_values(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="cannot authorize execution"):
        YkbContextItem(
            category="TECH",
            title="Unsafe authority",
            impact="HIGH",
            recommendation="Block",
            source="local",
            source_url="artifact://test",
            as_of=NOW.isoformat(),
            execution_allowed=True,
        )
    with pytest.raises(ValueError, match="score"):
        YkbOpportunityBrief(
            **{
                **_valid_opportunity_kwargs(),
                "score": Decimal("101"),
            }
        )
    with pytest.raises(ValueError, match="confidence"):
        YkbOpportunityBrief(
            **{
                **_valid_opportunity_kwargs(),
                "confidence": Decimal("1.1"),
            }
        )
    with pytest.raises(ValueError, match="risk/reward"):
        YkbOpportunityBrief(
            **{
                **_valid_opportunity_kwargs(),
                "target_risk_reward": Decimal("0"),
            }
        )
    with pytest.raises(ValueError, match="trade plan"):
        YkbOpportunityBrief(
            **{
                **_valid_opportunity_kwargs(),
                "entry": " ",
            }
        )
    with pytest.raises(ValueError, match="redact raw values"):
        YkbFinancialSituation(
            status="BLOCKED",
            spot_asset_count=0,
            futures_position_count=0,
            reconciliation_status="UNKNOWN",
            value_disclosure="RAW_VALUES",
            known_value_present=False,
            blockers=("LIVE_ORDER_BLOCKED",),
        )
    with pytest.raises(ValueError, match="counts cannot be negative"):
        YkbWalletPositionManagement(
            status="BLOCKED",
            recommendation="FIX",
            spot_asset_count=-1,
            futures_position_count=0,
            open_position_policy="MANUAL",
            blockers=("LIVE_ORDER_BLOCKED",),
        )
    with pytest.raises(ValueError, match="private financial report"):
        YkbExecutiveBrief(
            **{
                **_valid_brief_kwargs(tmp_path),
                "private_financial_cloud_share_allowed": True,
            }
        )
    with pytest.raises(ValueError, match="risk/OOS live gate"):
        SemiAutoControlManagement(
            **{
                **_valid_semi_auto_kwargs(),
                "risk_oos_live_gate_status": "READY",
            }
        )


def test_ykb_helper_branches_keep_unavailable_and_review_states() -> None:
    pending = YkbOpportunityBrief(**_valid_opportunity_kwargs())
    risk_blocked = YkbOpportunityBrief(
        **{
            **_valid_opportunity_kwargs(),
            "blockers": ("RISK_APPROVAL_MISSING",),
            "entry": "1.01",
            "stop_loss": "0.98",
            "take_profit_1": "1.05",
            "take_profit_2": "1.08",
            "take_profit_3": "1.12",
        }
    )
    wallet_blocked = YkbOpportunityBrief(
        **{
            **_valid_opportunity_kwargs(),
            "blockers": ("WALLET_RECONCILIATION_REQUIRED",),
            "entry": "1.01",
            "stop_loss": "0.98",
            "take_profit_1": "1.05",
            "take_profit_2": "1.08",
            "take_profit_3": "1.12",
        }
    )
    dge_blocked = YkbOpportunityBrief(
        **{
            **_valid_opportunity_kwargs(),
            "blockers": ("CUSTOM_BLOCKER",),
            "entry": "1.01",
            "stop_loss": "0.98",
            "take_profit_1": "1.05",
            "take_profit_2": "1.08",
            "take_profit_3": "1.12",
        }
    )
    ready = YkbOpportunityBrief(
        **{
            **_valid_opportunity_kwargs(),
            "entry": "1.01",
            "stop_loss": "0.98",
            "take_profit_1": "1.05",
            "take_profit_2": "1.08",
            "take_profit_3": "1.12",
            "blockers": (),
        }
    )

    assert _watchlist_gap_summary(pending) == "SL/E/TP_VALIDATION_MISSING"
    assert _watchlist_gap_summary(risk_blocked) == "RISK_REVIEW_MISSING"
    assert _watchlist_gap_summary(wallet_blocked) == "WALLET_RECONCILIATION_MISSING"
    assert _watchlist_gap_summary(dge_blocked) == "DGE_BLOCKERS_PRESENT"
    assert _is_executive_trade_plan_row(ready) is True
    assert _is_directional_executive_candidate(ready) is True
    assert (
        _is_directional_executive_candidate(
            YkbOpportunityBrief(
                **{
                    **_valid_opportunity_kwargs(),
                    "market": "OPTIONS",
                    "trade_side": "BUY",
                }
            )
        )
        is False
    )

    assert _trade_side({"direction": "bearish"}, "SPOT", "HOLD") == "SELL"
    assert _trade_side({"position_side": "short"}, "USD_M_FUTURES", "HOLD") == "SHORT"
    assert _trade_side({}, "USD_M_FUTURES", "HOLD") == "NO_DIRECTION"
    assert _trade_side({}, "SPOT", "HOLD") == "HOLD"
    assert _trade_leverage({"suggested_leverage": "2x"}, "USD_M_FUTURES") == "2x"
    assert _trade_leverage({}, "USD_M_FUTURES") == "NOT_APPROVED"
    assert _trade_plan_value({"entry": ""}, "entry", "fallback") == (
        "PENDING_VALIDATED_LEVEL"
    )
    assert _trade_plan_value({"fallback": "1.2"}, "entry", "fallback") == "1.2"
    assert _timeframe_value({"timeframe": "UNAVAILABLE"}) == "MULTI_TF_REVIEW"
    assert _timeframe_value({"timeframe": "4h"}) == "4h"
    assert _istanbul_time_text("KAYIT_YOK") == "KAYIT_YOK"
    assert _istanbul_time_text("bad-date") == "bad-date"
    assert _metric_texts((("net_return", 0.1), ["trade_count", 5], ("bad",))) == (
        "net_return=0.1",
        "trade_count=5",
    )
    strategy_parameters = {"strategy": {"selected_parameters": {"ema": 9}}}
    assert _tuning_parameter_texts(strategy_parameters) == ("ema=9",)
    assert _tuning_parameter_texts(
        {"tuning": {"selected_parameters": {"atr": "1.5"}}}
    ) == ("atr=1.5",)
    assert _run_card_playbook({"hypothesis_id": "hyp:breakout:1h"}) == "breakout"
    assert _run_card_playbook({"playbook": "fallback"}) == "fallback"


def test_opportunity_funnel_counts_loss_streak_halted_candidates_separately() -> None:
    halted = YkbOpportunityBrief(
        **{
            **_valid_opportunity_kwargs(),
            "blockers": ("VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED",),
        }
    )
    ready = YkbOpportunityBrief(
        **{
            **_valid_opportunity_kwargs(),
            "opportunity_id": "opp-ready",
            "blockers": (),
            "entry": "1.01",
            "stop_loss": "0.98",
            "take_profit_1": "1.05",
            "take_profit_2": "1.08",
            "take_profit_3": "1.12",
        }
    )

    payload = _opportunity_funnel_payload((halted, ready))

    assert payload["visible_research_opportunities"] == 2
    assert payload["blocked_visible_research"] == 1
    assert payload["loss_streak_halted_visible_research"] == 1
    assert payload["loss_streak_halted_spot_visible_research"] == 1
    assert payload["loss_streak_halted_futures_visible_research"] == 0
    assert payload["loss_streak_halted_scopes"] == [
        "SPOT:ETHUSDT:breakout_retest:1h",
    ]
    assert payload["loss_streak_halt_review_refs"] == [
        "virtual-loss-streak-halt:ethusdt:spot:1h"
    ]
    assert payload["loss_streak_halt_review_artifact_paths"] == [
        "ARTIFACT_PATH_UNRESOLVED"
    ]
    assert payload["loss_streak_halt_review_artifacts"] == [
        {
            "scope": "SPOT:ETHUSDT:breakout_retest:1h",
            "review_ref": "virtual-loss-streak-halt:ethusdt:spot:1h",
            "artifact_path": "ARTIFACT_PATH_UNRESOLVED",
        }
    ]
    assert payload["loss_streak_halt_reviews_with_resolved_artifacts"] == 0
    assert payload["loss_streak_halt_reviews_pending_artifact_resolution"] == 1
    assert payload["loss_streak_halted_primary_setup"] == "breakout_retest:1"
    assert payload["loss_streak_halted_setup_clusters"] == ["breakout_retest:1"]
    assert payload["loss_streak_halted_primary_pattern"] == "SPOT:breakout_retest:BUY:1"
    assert payload["loss_streak_halted_pattern_clusters"] == [
        "SPOT:breakout_retest:BUY:1"
    ]
    assert payload["loss_streak_repeat_offender_visible_research"] == 0
    assert payload["loss_streak_repeat_offender_scopes"] == []
    assert payload["loss_streak_high_escalation_visible_research"] == 0
    assert payload["loss_streak_high_escalation_scopes"] == []
    assert payload["loss_streak_fragile_edge_visible_research"] == 0
    assert payload["loss_streak_fragile_edge_scopes"] == []
    assert payload["virtual_market_ready_trade_plans"] == 1


def test_opportunity_funnel_reports_halt_market_mix_and_artifact_resolution() -> None:
    halted_spot = YkbOpportunityBrief(
        **{
            **_valid_opportunity_kwargs(),
            "blockers": ("VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED",),
            "halt_review_artifact_path": (
                "runtime/artifacts/user_reports/virtual_loss_streak_halt_review/spot.json"
            ),
        }
    )
    halted_futures = YkbOpportunityBrief(
        **{
            **_valid_opportunity_kwargs(),
            "opportunity_id": "opp-futures-halt",
            "market": "USDT_FUTURES",
            "requested_action": "LONG",
            "governed_action": "WATCH_ONLY",
            "trade_side": "LONG",
            "leverage": "3x",
            "blockers": ("VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED",),
        }
    )

    payload = _opportunity_funnel_payload((halted_spot, halted_futures))

    assert payload["loss_streak_halted_visible_research"] == 2
    assert payload["loss_streak_halted_spot_visible_research"] == 1
    assert payload["loss_streak_halted_futures_visible_research"] == 1
    assert payload["loss_streak_halt_reviews_with_resolved_artifacts"] == 1
    assert payload["loss_streak_halt_reviews_pending_artifact_resolution"] == 1
    assert payload["loss_streak_halted_primary_setup"] == "breakout_retest:2"
    assert payload["loss_streak_halted_setup_clusters"] == ["breakout_retest:2"]
    assert payload["loss_streak_halted_primary_pattern"] == (
        "SPOT:breakout_retest:BUY:1"
    )
    assert payload["loss_streak_halted_pattern_clusters"] == [
        "SPOT:breakout_retest:BUY:1",
        "USDT_FUTURES:breakout_retest:LONG:1",
    ]
    assert payload["loss_streak_repeat_offender_visible_research"] == 0
    assert payload["loss_streak_repeat_offender_scopes"] == []


def test_opportunity_funnel_clusters_halted_setups_by_frequency() -> None:
    halted_breakout_a = YkbOpportunityBrief(
        **{
            **_valid_opportunity_kwargs(),
            "blockers": ("VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED",),
        }
    )
    halted_breakout_b = YkbOpportunityBrief(
        **{
            **_valid_opportunity_kwargs(),
            "opportunity_id": "opp-breakout-b",
            "symbol": "SOLUSDT",
            "blockers": ("VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED",),
        }
    )
    halted_reclaim = YkbOpportunityBrief(
        **{
            **_valid_opportunity_kwargs(),
            "opportunity_id": "opp-reclaim",
            "symbol": "XRPUSDT",
            "setup_name": "support_reclaim",
            "blockers": ("VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED",),
        }
    )

    payload = _opportunity_funnel_payload(
        (halted_breakout_a, halted_breakout_b, halted_reclaim)
    )

    assert payload["loss_streak_halted_primary_setup"] == "breakout_retest:2"
    assert payload["loss_streak_halted_setup_clusters"] == [
        "breakout_retest:2",
        "support_reclaim:1",
    ]
    assert payload["loss_streak_halted_primary_pattern"] == "SPOT:breakout_retest:BUY:2"
    assert payload["loss_streak_halted_pattern_clusters"] == [
        "SPOT:breakout_retest:BUY:2",
        "SPOT:support_reclaim:BUY:1",
    ]
    assert payload["loss_streak_repeat_offender_visible_research"] == 1
    assert payload["loss_streak_repeat_offender_scopes"] == ["SPOT:breakout_retest:BUY"]


def test_opportunity_funnel_tracks_repeat_offenders_by_market_setup_side() -> None:
    halted_spot_buy_a = YkbOpportunityBrief(
        **{
            **_valid_opportunity_kwargs(),
            "blockers": ("VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED",),
        }
    )
    halted_spot_buy_b = YkbOpportunityBrief(
        **{
            **_valid_opportunity_kwargs(),
            "opportunity_id": "opp-spot-buy-b",
            "symbol": "SOLUSDT",
            "blockers": ("VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED",),
        }
    )
    halted_futures_long = YkbOpportunityBrief(
        **{
            **_valid_opportunity_kwargs(),
            "opportunity_id": "opp-futures-long",
            "market": "USDT_FUTURES",
            "requested_action": "LONG",
            "governed_action": "WATCH_ONLY",
            "trade_side": "LONG",
            "leverage": "3x",
            "blockers": ("VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED",),
        }
    )
    halted_futures_short = YkbOpportunityBrief(
        **{
            **_valid_opportunity_kwargs(),
            "opportunity_id": "opp-futures-short",
            "market": "USDT_FUTURES",
            "requested_action": "SHORT",
            "governed_action": "WATCH_ONLY",
            "trade_side": "SHORT",
            "leverage": "3x",
            "blockers": ("VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED",),
        }
    )

    payload = _opportunity_funnel_payload(
        (
            halted_spot_buy_a,
            halted_spot_buy_b,
            halted_futures_long,
            halted_futures_short,
        ),
        YkbValidationDigest(
            symbol="BTCUSDT",
            status="READY",
            latest_run_id="run:high",
            timeframe="1h",
            playbook="breakout",
            promotion_status="RESEARCH_ONLY",
            run_created_at=NOW.isoformat(),
            metrics=("max_drawdown=0.12", "net_return=-0.07"),
            tuning_parameters=("ema_fast=9",),
            artifact_refs=("artifact:test",),
            blockers=(),
        ),
    )

    assert payload["loss_streak_halted_primary_setup"] == "breakout_retest:4"
    assert payload["loss_streak_halted_primary_pattern"] == "SPOT:breakout_retest:BUY:2"
    assert payload["loss_streak_halted_pattern_clusters"] == [
        "SPOT:breakout_retest:BUY:2",
        "USDT_FUTURES:breakout_retest:LONG:1",
        "USDT_FUTURES:breakout_retest:SHORT:1",
    ]
    assert payload["loss_streak_repeat_offender_visible_research"] == 1
    assert payload["loss_streak_repeat_offender_scopes"] == ["SPOT:breakout_retest:BUY"]
    assert payload["loss_streak_priority_queue_summary"] == (
        "`SPOT:breakout_retest:BUY` -> `P1_REPEAT_PATTERN_REVALIDATION`; "
        "`USDT_FUTURES:breakout_retest:LONG` -> `P2_ARTIFACT_RESOLUTION_REQUIRED`; "
        "`USDT_FUTURES:breakout_retest:SHORT` -> `P2_ARTIFACT_RESOLUTION_REQUIRED`"
    )
    assert payload["loss_streak_high_escalation_visible_research"] == 1
    assert payload["loss_streak_high_escalation_scopes"] == ["SPOT:breakout_retest:BUY"]
    assert payload["loss_streak_fragile_edge_visible_research"] == 0
    assert payload["loss_streak_fragile_edge_scopes"] == []


def test_opportunity_funnel_tracks_fragile_edge_escalation_when_return_stays_positive() -> (
    None
):
    halted_a = YkbOpportunityBrief(
        **{
            **_valid_opportunity_kwargs(),
            "blockers": ("VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED",),
        }
    )
    halted_b = YkbOpportunityBrief(
        **{
            **_valid_opportunity_kwargs(),
            "opportunity_id": "opp-repeat-b",
            "symbol": "SOLUSDT",
            "blockers": ("VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED",),
        }
    )

    payload = _opportunity_funnel_payload(
        (halted_a, halted_b),
        YkbValidationDigest(
            symbol="BTCUSDT",
            status="READY",
            latest_run_id="run:fragile",
            timeframe="1h",
            playbook="breakout",
            promotion_status="RESEARCH_ONLY",
            run_created_at=NOW.isoformat(),
            metrics=("max_drawdown=0.12", "net_return=0.02"),
            tuning_parameters=("ema_fast=9",),
            artifact_refs=("artifact:test",),
            blockers=(),
        ),
    )

    assert payload["loss_streak_high_escalation_visible_research"] == 0
    assert payload["loss_streak_fragile_edge_visible_research"] == 1
    assert payload["loss_streak_high_escalation_scopes"] == []
    assert payload["loss_streak_fragile_edge_scopes"] == ["SPOT:breakout_retest:BUY"]


def test_serialized_opportunity_payloads_include_escalation_fields() -> None:
    halted_a = YkbOpportunityBrief(
        **{
            **_valid_opportunity_kwargs(),
            "blockers": ("VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED",),
        }
    )
    halted_b = YkbOpportunityBrief(
        **{
            **_valid_opportunity_kwargs(),
            "opportunity_id": "opp-repeat-b",
            "symbol": "SOLUSDT",
            "blockers": ("VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED",),
        }
    )

    payloads = ykb_module._serialized_opportunity_payloads(
        (halted_a, halted_b),
        validation=YkbValidationDigest(
            symbol="BTCUSDT",
            status="READY",
            latest_run_id="run:high",
            timeframe="1h",
            playbook="breakout",
            promotion_status="RESEARCH_ONLY",
            run_created_at=NOW.isoformat(),
            metrics=("max_drawdown=0.12", "net_return=-0.07"),
            tuning_parameters=("ema_fast=9",),
            artifact_refs=("artifact:test",),
            blockers=(),
        ),
    )

    assert payloads[0]["loss_streak_escalation_state"] == "HIGH_ESCALATION"
    assert payloads[0]["loss_streak_first_action"] == (
        "FREEZE_PATTERN_AND_RUN_ROOT_CAUSE_REVALIDATION"
    )
    assert payloads[0]["loss_streak_review_priority"] == (
        "P1_REPEAT_PATTERN_REVALIDATION"
    )
    assert payloads[0]["loss_streak_review_rationale"] == (
        "Repeated halted market/setup/side pattern requires bounded revalidation."
    )
    assert payloads[1]["loss_streak_escalation_state"] == "HIGH_ESCALATION"
    assert payloads[1]["loss_streak_first_action"] == (
        "FREEZE_PATTERN_AND_RUN_ROOT_CAUSE_REVALIDATION"
    )
    assert payloads[1]["loss_streak_review_priority"] == (
        "P1_REPEAT_PATTERN_REVALIDATION"
    )
    assert payloads[1]["loss_streak_review_rationale"] == (
        "Repeated halted market/setup/side pattern requires bounded revalidation."
    )


def test_loss_streak_halted_scope_lines_render_halted_candidates() -> None:
    halted = YkbOpportunityBrief(
        **{
            **_valid_opportunity_kwargs(),
            "blockers": ("VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED",),
            "improvement_candidate_hint": "improvement:loss-streak:ethusdt:spot:1h",
            "financial_fit": "VIRTUAL_MARKET_AUTONOMOUS_FIT",
            "halt_root_cause_summary": (
                "Entry gating, regime fit and exit protection require replay review."
            ),
            "halt_next_bounded_experiment": "Replay last three halted losses.",
            "halt_reset_criteria": (
                "consecutive_losses must fall below threshold",
                "fresh validation evidence required",
            ),
            "halt_review_ref": "virtual-loss-streak-halt:ethusdt:spot:1h",
            "halt_review_artifact_path": "runtime/artifacts/user_reports/virtual_loss_streak_halt_review/latest.json",
            "next_evidence_action": "REPLAY_LAST_THREE_LOSSES",
        }
    )

    lines = _loss_streak_halted_scope_lines((halted,))
    normalized = _normalize_table_spacing("\n".join(lines))

    assert "VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED" in normalized
    assert "REPLAY_LAST_THREE_LOSSES" in normalized
    assert "improvement:loss-streak:ethusdt:spot:1h" in normalized
    assert "consecutive_losses must fall below threshold" in normalized
    assert "virtual-loss-streak-halt:ethusdt:spot:1h" in normalized
    assert (
        "runtime/artifacts/user_reports/virtual_loss_streak_halt_review/latest.json"
        in normalized
    )
    assert "SPOT:breakout_retest:BUY" in normalized
    assert "ISOLATED" in normalized
    assert "P5_STANDARD_REVIEW_QUEUE" in normalized
    assert "NO_ESCALATION" in normalized
    assert "STANDARD_BOUNDED_REVIEW" in normalized
    assert "acceptable fit" in normalized
    assert (
        "Entry gating, regime fit and exit protection require replay review."
        in normalized
    )
    assert "Replay last three halted losses." in normalized
    assert "| ETHUSDT | 1h | SPOT | breakout_retest | BUY | WATCH_ONLY |" in normalized


def test_halted_scope_helpers_use_fail_closed_fallbacks() -> None:
    halted = YkbOpportunityBrief(
        **{
            **_valid_opportunity_kwargs(),
            "blockers": ("VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED",),
            "confirmation_requirements": ("refresh_virtual_validation",),
            "promotion_requirements": ("keep_research_only",),
        }
    )

    assert _halted_scope_improvement_candidate(halted) == (
        "improvement:loss-streak:breakout_retest:spot:1h"
    )
    assert _halted_scope_reset_summary(halted) == "refresh_virtual_validation"
    assert _halted_scope_review_ref(halted) == (
        "virtual-loss-streak-halt:ethusdt:spot:1h"
    )
    assert _halted_scope_artifact_path(halted) == "ARTIFACT_PATH_UNRESOLVED"
    assert _loss_streak_pattern_key(halted) == "SPOT:breakout_retest:BUY"
    assert (
        _loss_streak_repeat_offender_state(
            halted,
            repeat_offender_patterns=set(),
        )
        == "ISOLATED"
    )
    assert (
        _loss_streak_review_priority(
            halted,
            repeat_offender_patterns=set(),
        )
        == "P2_ARTIFACT_RESOLUTION_REQUIRED"
    )
    assert (
        _loss_streak_review_rationale(
            halted,
            repeat_offender_patterns=set(),
        )
        == "Halt review artifact is unresolved and must be recovered before analysis."
    )
    assert (
        _loss_streak_scope_escalation_state(
            halted,
            validation=None,
            repeat_offender_patterns=set(),
        )
        == "NO_ESCALATION"
    )
    assert (
        _loss_streak_scope_first_action(
            halted,
            validation=None,
            repeat_offender_patterns=set(),
        )
        == "STANDARD_BOUNDED_REVIEW"
    )


def test_loss_streak_halted_scope_lines_mark_repeat_offenders_with_priority() -> None:
    halted_a = YkbOpportunityBrief(
        **{
            **_valid_opportunity_kwargs(),
            "blockers": ("VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED",),
            "symbol": "ETHUSDT",
        }
    )
    halted_b = YkbOpportunityBrief(
        **{
            **_valid_opportunity_kwargs(),
            "opportunity_id": "opp-repeat-b",
            "blockers": ("VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED",),
            "symbol": "SOLUSDT",
        }
    )

    validation = YkbValidationDigest(
        symbol="BTCUSDT",
        status="READY",
        latest_run_id="run:high",
        timeframe="1h",
        playbook="breakout",
        promotion_status="RESEARCH_ONLY",
        run_created_at=NOW.isoformat(),
        metrics=("max_drawdown=0.12", "net_return=-0.07"),
        tuning_parameters=("ema_fast=9",),
        artifact_refs=("artifact:test",),
        blockers=(),
    )

    lines = _loss_streak_halted_scope_lines((halted_a, halted_b), validation=validation)
    normalized = _normalize_table_spacing("\n".join(lines))

    assert "SPOT:breakout_retest:BUY" in normalized
    assert "REPEAT_OFFENDER" in normalized
    assert "P1_REPEAT_PATTERN_REVALIDATION" in normalized
    assert "HIGH_ESCALATION" in normalized
    assert "FREEZE_PATTERN_AND_RUN_ROOT_CAUSE_REVALIDATION" in normalized
    assert (
        "Repeated halted market/setup/side pattern requires bounded revalidation."
        in normalized
    )


def test_loss_streak_halted_scope_lines_mark_fragile_edge_actions() -> None:
    halted_a = YkbOpportunityBrief(
        **{
            **_valid_opportunity_kwargs(),
            "blockers": ("VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED",),
            "halt_review_artifact_path": "runtime/artifacts/user_reports/virtual_loss_streak_halt_review/a.json",
        }
    )
    halted_b = YkbOpportunityBrief(
        **{
            **_valid_opportunity_kwargs(),
            "opportunity_id": "opp-repeat-b",
            "symbol": "SOLUSDT",
            "blockers": ("VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED",),
            "halt_review_artifact_path": "runtime/artifacts/user_reports/virtual_loss_streak_halt_review/b.json",
        }
    )
    validation = YkbValidationDigest(
        symbol="BTCUSDT",
        status="READY",
        latest_run_id="run:fragile",
        timeframe="1h",
        playbook="breakout",
        promotion_status="RESEARCH_ONLY",
        run_created_at=NOW.isoformat(),
        metrics=("max_drawdown=0.12", "net_return=0.02"),
        tuning_parameters=("ema_fast=9",),
        artifact_refs=("artifact:test",),
        blockers=(),
    )

    lines = _loss_streak_halted_scope_lines((halted_a, halted_b), validation=validation)
    normalized = _normalize_table_spacing("\n".join(lines))

    assert "FRAGILE_EDGE_ESCALATION" in normalized
    assert "KEEP_EDGE_GUARDED_AND_RUN_PROTECTIVE_REVALIDATION" in normalized


def test_immediate_action_section_lists_high_and_fragile_patterns() -> None:
    high_a = YkbOpportunityBrief(
        **{
            **_valid_opportunity_kwargs(),
            "blockers": ("VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED",),
        }
    )
    high_b = YkbOpportunityBrief(
        **{
            **_valid_opportunity_kwargs(),
            "opportunity_id": "opp-high-b",
            "symbol": "SOLUSDT",
            "blockers": ("VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED",),
        }
    )
    fragile_a = YkbOpportunityBrief(
        **{
            **_valid_opportunity_kwargs(),
            "opportunity_id": "opp-fragile-a",
            "symbol": "XRPUSDT",
            "setup_name": "support_reclaim",
            "blockers": ("VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED",),
            "halt_review_artifact_path": "runtime/artifacts/user_reports/virtual_loss_streak_halt_review/a.json",
        }
    )
    fragile_b = YkbOpportunityBrief(
        **{
            **_valid_opportunity_kwargs(),
            "opportunity_id": "opp-fragile-b",
            "symbol": "ADAUSDT",
            "setup_name": "support_reclaim",
            "blockers": ("VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED",),
            "halt_review_artifact_path": "runtime/artifacts/user_reports/virtual_loss_streak_halt_review/b.json",
        }
    )

    high_lines = ykb_module._loss_streak_immediate_action_lines(
        (high_a, high_b),
        validation=YkbValidationDigest(
            symbol="BTCUSDT",
            status="READY",
            latest_run_id="run:high",
            timeframe="1h",
            playbook="breakout",
            promotion_status="RESEARCH_ONLY",
            run_created_at=NOW.isoformat(),
            metrics=("max_drawdown=0.12", "net_return=-0.07"),
            tuning_parameters=("ema_fast=9",),
            artifact_refs=("artifact:test",),
            blockers=(),
        ),
    )
    fragile_lines = ykb_module._loss_streak_immediate_action_lines(
        (fragile_a, fragile_b),
        validation=YkbValidationDigest(
            symbol="BTCUSDT",
            status="READY",
            latest_run_id="run:fragile",
            timeframe="1h",
            playbook="breakout",
            promotion_status="RESEARCH_ONLY",
            run_created_at=NOW.isoformat(),
            metrics=("max_drawdown=0.12", "net_return=0.02"),
            tuning_parameters=("ema_fast=9",),
            artifact_refs=("artifact:test",),
            blockers=(),
        ),
    )

    assert high_lines == [
        "- `SPOT:breakout_retest:BUY` -> `HIGH_ESCALATION` / `FREEZE_PATTERN_AND_RUN_ROOT_CAUSE_REVALIDATION`"
    ]
    assert fragile_lines == [
        (
            "- `SPOT:support_reclaim:BUY` -> `FRAGILE_EDGE_ESCALATION` / "
            "`KEEP_EDGE_GUARDED_AND_RUN_PROTECTIVE_REVALIDATION`"
        )
    ]

    combined_lines = ykb_module._loss_streak_immediate_action_lines(
        (high_a, high_b, fragile_a, fragile_b),
        validation=YkbValidationDigest(
            symbol="BTCUSDT",
            status="READY",
            latest_run_id="run:high",
            timeframe="1h",
            playbook="breakout",
            promotion_status="RESEARCH_ONLY",
            run_created_at=NOW.isoformat(),
            metrics=("max_drawdown=0.12", "net_return=-0.07"),
            tuning_parameters=("ema_fast=9",),
            artifact_refs=("artifact:test",),
            blockers=(),
        ),
    )

    assert combined_lines[0] == (
        "- `SPOT:breakout_retest:BUY` -> `HIGH_ESCALATION` / `FREEZE_PATTERN_AND_RUN_ROOT_CAUSE_REVALIDATION`"
    )


def test_loss_streak_review_priority_detects_financial_fit_and_signal_quality() -> None:
    financially_unfit = YkbOpportunityBrief(
        **{
            **_valid_opportunity_kwargs(),
            "blockers": ("VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED",),
            "halt_review_artifact_path": "runtime/artifacts/user_reports/virtual_loss_streak_halt_review/latest.json",
            "financial_fit": "NOT_FINANCIALLY_ELIGIBLE_YET",
        }
    )
    weak_signal = YkbOpportunityBrief(
        **{
            **_valid_opportunity_kwargs(),
            "opportunity_id": "opp-weak-signal",
            "blockers": ("VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED",),
            "financial_fit": "VIRTUAL_MARKET_AUTONOMOUS_FIT",
            "halt_review_artifact_path": "runtime/artifacts/user_reports/virtual_loss_streak_halt_review/latest.json",
            "score": Decimal("64"),
            "confidence": Decimal("0.59"),
        }
    )

    assert (
        _loss_streak_review_priority(
            financially_unfit,
            repeat_offender_patterns=set(),
        )
        == "P3_FINANCIAL_FIT_RECHECK"
    )
    assert (
        _loss_streak_review_rationale(
            financially_unfit,
            repeat_offender_patterns=set(),
        )
        == "Financial fit is below autonomous threshold and needs manual reassessment."
    )
    assert (
        _loss_streak_review_priority(
            weak_signal,
            repeat_offender_patterns=set(),
        )
        == "P4_SIGNAL_QUALITY_REVIEW"
    )
    assert (
        _loss_streak_review_rationale(
            weak_signal,
            repeat_offender_patterns=set(),
        )
        == "Signal quality is weak for autonomous replay and should be reviewed."
    )


def test_loss_streak_priority_queue_summary_orders_top_patterns() -> None:
    repeat_a = YkbOpportunityBrief(
        **{
            **_valid_opportunity_kwargs(),
            "financial_fit": "VIRTUAL_MARKET_AUTONOMOUS_FIT",
            "blockers": ("VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED",),
            "halt_review_artifact_path": "runtime/artifacts/user_reports/virtual_loss_streak_halt_review/a.json",
        }
    )
    repeat_b = YkbOpportunityBrief(
        **{
            **_valid_opportunity_kwargs(),
            "opportunity_id": "opp-repeat-b",
            "symbol": "SOLUSDT",
            "financial_fit": "VIRTUAL_MARKET_AUTONOMOUS_FIT",
            "blockers": ("VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED",),
            "halt_review_artifact_path": "runtime/artifacts/user_reports/virtual_loss_streak_halt_review/b.json",
        }
    )
    unresolved = YkbOpportunityBrief(
        **{
            **_valid_opportunity_kwargs(),
            "opportunity_id": "opp-unresolved",
            "symbol": "XRPUSDT",
            "setup_name": "support_reclaim",
            "financial_fit": "VIRTUAL_MARKET_AUTONOMOUS_FIT",
            "blockers": ("VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED",),
        }
    )
    weak_signal = YkbOpportunityBrief(
        **{
            **_valid_opportunity_kwargs(),
            "opportunity_id": "opp-weak",
            "symbol": "ADAUSDT",
            "setup_name": "range_reclaim",
            "financial_fit": "VIRTUAL_MARKET_AUTONOMOUS_FIT",
            "blockers": ("VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED",),
            "halt_review_artifact_path": "runtime/artifacts/user_reports/virtual_loss_streak_halt_review/c.json",
            "score": Decimal("64"),
            "confidence": Decimal("0.59"),
        }
    )

    assert _loss_streak_priority_queue_summary(
        (repeat_a, repeat_b, unresolved, weak_signal)
    ) == (
        "`SPOT:breakout_retest:BUY` -> `P1_REPEAT_PATTERN_REVALIDATION`; "
        "`SPOT:support_reclaim:BUY` -> `P2_ARTIFACT_RESOLUTION_REQUIRED`; "
        "`SPOT:range_reclaim:BUY` -> `P4_SIGNAL_QUALITY_REVIEW`"
    )


def test_loss_streak_wallet_stress_context_classifies_risk_levels() -> None:
    high_financial = YkbFinancialSituation(
        status="BLOCKED",
        spot_asset_count=0,
        futures_position_count=0,
        reconciliation_status="MISMATCH",
        value_disclosure="REDACTED_SUMMARY_ONLY",
        known_value_present=False,
        blockers=("RECONCILIATION_REQUIRED",),
    )
    high_wallet = YkbWalletPositionManagement(
        status="BLOCKED",
        recommendation="MANUAL_REVIEW_REQUIRED",
        spot_asset_count=0,
        futures_position_count=0,
        open_position_policy="RESEARCH_ONLY",
        blockers=("RECONCILIATION_REQUIRED",),
        funding_recommendation="BLOCKED_PENDING_RECONCILIATION",
    )
    moderate_financial = YkbFinancialSituation(
        status="READY",
        spot_asset_count=1,
        futures_position_count=1,
        reconciliation_status="CLEAN",
        value_disclosure="REDACTED_SUMMARY_ONLY",
        known_value_present=True,
        blockers=(),
        open_order_count=1,
    )
    moderate_wallet = YkbWalletPositionManagement(
        status="REVIEW_REQUIRED",
        recommendation="KEEP_RESEARCH_ONLY",
        spot_asset_count=1,
        futures_position_count=1,
        open_position_policy="RESEARCH_ONLY",
        blockers=(),
        spot_open_order_count=1,
        futures_open_order_count=0,
        funding_recommendation="QUOTE_LIQUIDITY_AVAILABLE_FOR_MANUAL_REVIEW",
    )
    low_financial = YkbFinancialSituation(
        status="READY",
        spot_asset_count=1,
        futures_position_count=0,
        reconciliation_status="CLEAN",
        value_disclosure="REDACTED_SUMMARY_ONLY",
        known_value_present=True,
        blockers=(),
        open_order_count=0,
    )
    low_wallet = YkbWalletPositionManagement(
        status="READY_FOR_REVIEW",
        recommendation="KEEP_RESEARCH_ONLY",
        spot_asset_count=1,
        futures_position_count=0,
        open_position_policy="RESEARCH_ONLY",
        blockers=(),
        spot_open_order_count=0,
        futures_open_order_count=0,
        funding_recommendation="QUOTE_LIQUIDITY_AVAILABLE_FOR_MANUAL_REVIEW",
    )

    assert _loss_streak_wallet_stress_context(high_financial, high_wallet).startswith(
        "HIGH_WALLET_STRESS"
    )
    assert _loss_streak_wallet_stress_context(
        moderate_financial,
        moderate_wallet,
    ).startswith("MODERATE_WALLET_STRESS")
    assert _loss_streak_wallet_stress_context(low_financial, low_wallet).startswith(
        "LOW_WALLET_STRESS"
    )


def test_virtual_runtime_evidence_context_reads_latest_payload_fail_closed() -> None:
    assert _virtual_runtime_evidence_context(Path("missing-root")).startswith(
        "UNAVAILABLE"
    )
    snapshot = _virtual_runtime_evidence_snapshot(Path("missing-root"))
    assert snapshot["available"] is False
    assert snapshot["status"] == "UNAVAILABLE"
    assert snapshot["blockers"] == []
    assert snapshot["blockers_summary"] == "-"
    assert snapshot["metrics"] == {}
    assert snapshot["net_return"] is None
    assert snapshot["max_drawdown"] is None
    assert snapshot["oos_expectancy_usdt"] is None
    assert snapshot["no_trade_counterfactual_pnl_usdt"] is None
    assert snapshot["no_trade_counterfactual_r"] is None


def test_virtual_runtime_evidence_context_reads_research_surface_summary(
    tmp_path: Path,
) -> None:
    payload_path = (
        tmp_path
        / "runtime"
        / "artifacts"
        / "user_reports"
        / "virtual_evidence"
        / "virtual_research_evidence_latest.json"
    )
    payload_path.parent.mkdir(parents=True, exist_ok=True)
    payload_path.write_text(
        json.dumps(
            {
                "surface_kind": "RESEARCH",
                "status": "READY_WITH_BLOCKERS",
                "telemetry_gate_eligible": False,
                "telemetry_metric_summary": {
                    "virtual.net_return": {"value": "0.11", "unit": "ratio"},
                    "virtual.max_drawdown": {"value": "0.06", "unit": "ratio"},
                    "virtual.oos_expectancy_usdt": {"value": "9", "unit": "USDT"},
                    "virtual.completed_trades": {"value": "12", "unit": "count"},
                    "virtual.daily_sharpe": {"value": "1.40", "unit": "ratio"},
                    "virtual.profit_factor": {"value": "1.80", "unit": "ratio"},
                    "virtual.win_rate": {"value": "0.58", "unit": "ratio"},
                    "virtual.average_r": {"value": "0.42", "unit": "R"},
                },
                "acceptance_results": [{"result_id": "acc-1", "status": "PASS"}],
                "improvement_candidate_ids": ["imp-1", "imp-2"],
                "blockers": [],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    assert _virtual_runtime_evidence_context(tmp_path) == (
        "surface=`RESEARCH` / status=`READY_WITH_BLOCKERS` / gate_eligible=`False` / "
        "acceptance_count=`1` / improvement_candidates=`2` / "
        "net_return=`0.11` / max_drawdown=`0.06` / oos_expectancy_usdt=`9` / "
        "completed_trades=`12` / daily_sharpe=`1.40` / profit_factor=`1.80` / "
        "win_rate=`0.58` / average_r=`0.42`"
    )
    snapshot = _virtual_runtime_evidence_snapshot(tmp_path)
    assert snapshot["available"] is True
    assert snapshot["surface_kind"] == "RESEARCH"
    assert snapshot["status"] == "READY_WITH_BLOCKERS"
    assert snapshot["telemetry_gate_eligible"] is False
    assert snapshot["acceptance_count"] == 1
    assert snapshot["improvement_candidate_count"] == 2
    assert snapshot["blockers"] == []
    assert snapshot["blockers_summary"] == "-"
    assert snapshot["metrics"] == {
        "net_return": {
            "metric_id": "virtual.net_return",
            "value": "0.11",
            "unit": "ratio",
        },
        "max_drawdown": {
            "metric_id": "virtual.max_drawdown",
            "value": "0.06",
            "unit": "ratio",
        },
        "oos_expectancy_usdt": {
            "metric_id": "virtual.oos_expectancy_usdt",
            "value": "9",
            "unit": "USDT",
        },
        "completed_trades": {
            "metric_id": "virtual.completed_trades",
            "value": "12",
            "unit": "count",
        },
        "daily_sharpe": {
            "metric_id": "virtual.daily_sharpe",
            "value": "1.40",
            "unit": "ratio",
        },
        "profit_factor": {
            "metric_id": "virtual.profit_factor",
            "value": "1.80",
            "unit": "ratio",
        },
        "win_rate": {
            "metric_id": "virtual.win_rate",
            "value": "0.58",
            "unit": "ratio",
        },
        "average_r": {
            "metric_id": "virtual.average_r",
            "value": "0.42",
            "unit": "R",
        },
    }
    assert snapshot["net_return"] == "0.11"
    assert snapshot["max_drawdown"] == "0.06"
    assert snapshot["oos_expectancy_usdt"] == "9"
    assert snapshot["completed_trades"] == "12"
    assert snapshot["daily_sharpe"] == "1.40"
    assert snapshot["profit_factor"] == "1.80"
    assert snapshot["win_rate"] == "0.58"
    assert snapshot["average_r"] == "0.42"
    assert snapshot["no_trade_counterfactual_pnl_usdt"] is None
    assert snapshot["no_trade_counterfactual_r"] is None
    assert _virtual_runtime_priority_signal(snapshot) == "RESEARCH_FOLLOW_UP_PRIORITY"
    assert snapshot["metrics_summary"] == (
        "net_return=`0.11` / max_drawdown=`0.06` / oos_expectancy_usdt=`9` / "
        "completed_trades=`12` / daily_sharpe=`1.40` / profit_factor=`1.80` / "
        "win_rate=`0.58` / average_r=`0.42`"
    )


def test_virtual_runtime_evidence_context_reads_no_trade_surface_summary(
    tmp_path: Path,
) -> None:
    payload_path = (
        tmp_path
        / "runtime"
        / "artifacts"
        / "user_reports"
        / "virtual_evidence"
        / "virtual_no_trade_evidence_latest.json"
    )
    payload_path.parent.mkdir(parents=True, exist_ok=True)
    payload_path.write_text(
        json.dumps(
            {
                "surface_kind": "NO_TRADE",
                "status": "RESEARCH_ONLY",
                "telemetry_gate_eligible": False,
                "telemetry_metric_summary": {
                    "virtual.no_trade_counterfactual_r": {
                        "value": "1.20",
                        "unit": "R",
                    },
                    "virtual.no_trade_counterfactual_pnl_usdt": {
                        "value": "14",
                        "unit": "USDT",
                    },
                },
                "acceptance_results": [],
                "improvement_candidate_ids": ["imp-nt-1"],
                "blockers": ["NO_TRADE_MEASUREMENT"],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    assert _virtual_runtime_evidence_context(tmp_path) == (
        "surface=`NO_TRADE` / status=`RESEARCH_ONLY` / gate_eligible=`False` / "
        "acceptance_count=`0` / improvement_candidates=`1` / "
        "no_trade_counterfactual_pnl_usdt=`14` / no_trade_counterfactual_r=`1.20`"
    )
    snapshot = _virtual_runtime_evidence_snapshot(tmp_path)
    assert snapshot["available"] is True
    assert snapshot["surface_kind"] == "NO_TRADE"
    assert snapshot["status"] == "RESEARCH_ONLY"
    assert snapshot["telemetry_gate_eligible"] is False
    assert snapshot["acceptance_count"] == 0
    assert snapshot["improvement_candidate_count"] == 1
    assert snapshot["blockers"] == ["NO_TRADE_MEASUREMENT"]
    assert snapshot["blockers_summary"] == "NO_TRADE_MEASUREMENT"
    assert snapshot["metrics"] == {
        "no_trade_counterfactual_pnl_usdt": {
            "metric_id": "virtual.no_trade_counterfactual_pnl_usdt",
            "value": "14",
            "unit": "USDT",
        },
        "no_trade_counterfactual_r": {
            "metric_id": "virtual.no_trade_counterfactual_r",
            "value": "1.20",
            "unit": "R",
        },
    }
    assert snapshot["net_return"] is None
    assert snapshot["max_drawdown"] is None
    assert snapshot["oos_expectancy_usdt"] is None
    assert snapshot["no_trade_counterfactual_pnl_usdt"] == "14"
    assert snapshot["no_trade_counterfactual_r"] == "1.20"
    assert snapshot["metrics_summary"] == (
        "no_trade_counterfactual_pnl_usdt=`14` / no_trade_counterfactual_r=`1.20`"
    )
    assert _virtual_runtime_counterfactual_note(snapshot) == (
        "counterfactual_pnl_usdt=`14` / counterfactual_r=`1.20`"
    )
    assert _virtual_runtime_priority_signal(snapshot) == (
        "COUNTERFACTUAL_REVIEW_PRIORITY"
    )


def test_virtual_runtime_priority_signal_prefers_trade_sample_priority(
    tmp_path: Path,
) -> None:
    payload_path = (
        tmp_path
        / "runtime"
        / "artifacts"
        / "user_reports"
        / "virtual_evidence"
        / "virtual_research_evidence_latest.json"
    )
    payload_path.parent.mkdir(parents=True, exist_ok=True)
    payload_path.write_text(
        json.dumps(
            {
                "surface_kind": "RESEARCH",
                "status": "READY_WITH_BLOCKERS",
                "telemetry_gate_eligible": False,
                "telemetry_metric_summary": {
                    "virtual.net_return": {"value": "0.09", "unit": "ratio"},
                    "virtual.max_drawdown": {"value": "0.04", "unit": "ratio"},
                    "virtual.oos_expectancy_usdt": {"value": "3", "unit": "USDT"},
                    "virtual.completed_trades": {"value": "12", "unit": "count"},
                },
                "acceptance_results": [{"result_id": "acc-1", "status": "FAIL"}],
                "improvement_candidate_ids": ["imp-1"],
                "blockers": ["TRADE_SAMPLE_INSUFFICIENT"],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    snapshot = _virtual_runtime_evidence_snapshot(tmp_path)
    assert snapshot["blockers"] == ["TRADE_SAMPLE_INSUFFICIENT"]
    assert snapshot["blockers_summary"] == "TRADE_SAMPLE_INSUFFICIENT"
    assert _virtual_runtime_priority_signal(snapshot) == "SAMPLE_BUILD_PRIORITY"


def test_virtual_runtime_priority_signal_prefers_futures_margin_discipline(
    tmp_path: Path,
) -> None:
    report_dir = (
        tmp_path / "runtime" / "artifacts" / "user_reports" / "virtual_evidence"
    )
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "virtual_research_evidence_latest.json").write_text(
        json.dumps(
            {
                "surface_kind": "RESEARCH",
                "status": "READY_WITH_BLOCKERS",
                "telemetry_gate_eligible": False,
                "telemetry_metric_summary": {
                    "virtual.net_return": {"value": "0.12", "unit": "ratio"},
                    "virtual.max_drawdown": {"value": "0.05", "unit": "ratio"},
                    "virtual.oos_expectancy_usdt": {"value": "6", "unit": "USDT"},
                },
                "acceptance_results": [{"result_id": "acc-1", "status": "FAIL"}],
                "improvement_candidate_ids": ["imp-1"],
                "blockers": [],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (report_dir / "virtual_research_spot_evidence_latest.json").write_text(
        json.dumps(
            {
                "surface_kind": "RESEARCH",
                "market": "SPOT",
                "snapshot_id": "snapshot:spot:1",
                "telemetry_id": "telemetry:spot:1",
                "status": "READY_WITH_BLOCKERS",
                "telemetry_gate_eligible": False,
                "telemetry_metric_summary": {
                    "virtual.net_return": {"value": "0.20", "unit": "ratio"}
                },
                "acceptance_policy_id": "virtual-market-research-acceptance-v1",
                "acceptance_results": [
                    {
                        "result_id": "spot-acceptance:1",
                        "status": "PASS",
                        "gate_eligible": True,
                        "blockers": [],
                    }
                ],
                "improvement_candidate_ids": ["spot-candidate:1"],
                "blockers": [],
                "execution_allowed": False,
                "promotion_status": "RESEARCH_ONLY",
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (report_dir / "virtual_research_usd_m_futures_evidence_latest.json").write_text(
        json.dumps(
            {
                "surface_kind": "RESEARCH",
                "market": "USD_M_FUTURES",
                "snapshot_id": "snapshot:futures:1",
                "telemetry_id": "telemetry:futures:1",
                "status": "READY_WITH_BLOCKERS",
                "telemetry_gate_eligible": False,
                "telemetry_metric_summary": {
                    "virtual.net_return": {"value": "0.10", "unit": "ratio"}
                },
                "acceptance_policy_id": "virtual-market-research-acceptance-v1",
                "acceptance_results": [
                    {
                        "result_id": "futures-acceptance:1",
                        "status": "FAIL",
                        "gate_eligible": False,
                        "blockers": ["FUTURES_MARGIN_UTILIZATION_ABOVE_THRESHOLD"],
                    }
                ],
                "improvement_candidate_ids": ["futures-candidate:1"],
                "blockers": ["FUTURES_MARGIN_UTILIZATION_ABOVE_THRESHOLD"],
                "execution_allowed": False,
                "promotion_status": "RESEARCH_ONLY",
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    snapshot = _virtual_runtime_evidence_snapshot(tmp_path)
    assert snapshot["system_acceptance_blockers"] == [
        "FUTURES_MARGIN_UTILIZATION_ABOVE_THRESHOLD",
        "SYSTEM_FAIL",
    ]
    assert _virtual_runtime_priority_signal(snapshot) == (
        "FUTURES_MARGIN_DISCIPLINE_PRIORITY"
    )


def test_virtual_runtime_market_acceptance_context_reads_separate_spot_and_futures_payloads(
    tmp_path: Path,
) -> None:
    report_dir = (
        tmp_path / "runtime" / "artifacts" / "user_reports" / "virtual_evidence"
    )
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "virtual_research_spot_evidence_latest.json").write_text(
        json.dumps(
            {
                "surface_kind": "RESEARCH",
                "market": "SPOT",
                "snapshot_id": "snapshot:spot:1",
                "telemetry_id": "telemetry:spot:1",
                "status": "READY_WITH_BLOCKERS",
                "telemetry_gate_eligible": False,
                "telemetry_metric_summary": {
                    "virtual.net_return": {"value": "0.20", "unit": "ratio"}
                },
                "acceptance_policy_id": "virtual-market-research-acceptance-v1",
                "acceptance_results": [
                    {
                        "result_id": "spot-acceptance:1",
                        "status": "PASS",
                        "gate_eligible": True,
                        "blockers": [],
                    }
                ],
                "improvement_candidate_ids": ["spot-candidate:1"],
                "blockers": [],
                "execution_allowed": False,
                "promotion_status": "RESEARCH_ONLY",
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (report_dir / "virtual_research_usd_m_futures_evidence_latest.json").write_text(
        json.dumps(
            {
                "surface_kind": "RESEARCH",
                "market": "USD_M_FUTURES",
                "snapshot_id": "snapshot:futures:1",
                "telemetry_id": "telemetry:futures:1",
                "status": "READY_WITH_BLOCKERS",
                "telemetry_gate_eligible": False,
                "telemetry_metric_summary": {
                    "virtual.net_return": {"value": "0.10", "unit": "ratio"}
                },
                "acceptance_policy_id": "virtual-market-research-acceptance-v1",
                "acceptance_results": [
                    {
                        "result_id": "futures-acceptance:1",
                        "status": "FAIL",
                        "gate_eligible": False,
                        "blockers": ["FUTURES_MARGIN_UTILIZATION_ABOVE_THRESHOLD"],
                    }
                ],
                "improvement_candidate_ids": ["futures-candidate:1"],
                "blockers": ["FUTURES_MARGIN_UTILIZATION_ABOVE_THRESHOLD"],
                "execution_allowed": False,
                "promotion_status": "RESEARCH_ONLY",
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    assert _virtual_runtime_market_acceptance_context(tmp_path) == (
        "spot_acceptance_status=`PASS` / "
        "spot_acceptance_blockers=`-` / "
        "futures_acceptance_status=`FAIL` / "
        "futures_acceptance_blockers=`FUTURES_MARGIN_UTILIZATION_ABOVE_THRESHOLD` / "
        "system_acceptance_status=`FAIL` / "
        "system_acceptance_blockers=`FUTURES_MARGIN_UTILIZATION_ABOVE_THRESHOLD, SYSTEM_FAIL` / "
        "system_blocked_markets=`USD_M_FUTURES`"
    )


def test_latest_validation_wallet_kpi_context_extracts_governed_metrics() -> None:
    validation = YkbValidationDigest(
        symbol="BTCUSDT",
        status="READY",
        latest_run_id="run:test",
        timeframe="1h",
        playbook="breakout",
        promotion_status="RESEARCH_ONLY",
        run_created_at=NOW.isoformat(),
        metrics=("net_return=0.18", "max_drawdown=0.07", "trade_count=12.0"),
        tuning_parameters=("ema_fast=9",),
        artifact_refs=("artifact:test",),
        blockers=(),
    )

    assert _latest_validation_metric_value(validation, "net_return") == "0.18"
    assert _latest_validation_metric_value(validation, "max_drawdown") == "0.07"
    assert _latest_validation_metric_value(validation, "trade_count") == "12.0"
    assert _latest_validation_metric_value(validation, "missing_metric") is None
    assert _latest_validation_wallet_kpi_context(validation) == (
        "net_return=`0.18` / max_drawdown=`0.07` / trade_count=`12.0`"
    )


def test_latest_validation_wallet_kpi_context_fails_closed_when_metrics_missing() -> (
    None
):
    validation = YkbValidationDigest(
        symbol="BTCUSDT",
        status="BACKTEST_RUN_CARD_MISSING",
        latest_run_id="KAYIT_YOK",
        timeframe="1h",
        playbook="PLAYBOOK_NOT_PROVEN",
        promotion_status="RESEARCH_ONLY",
        run_created_at="KAYIT_YOK",
        metrics=("METRICS_NOT_PUBLISHED",),
        tuning_parameters=("TUNING_PARAMETERS_NOT_PUBLISHED",),
        artifact_refs=("ARTIFACT_REF_NOT_PUBLISHED",),
        blockers=("BACKTEST_RUN_CARD_UNAVAILABLE",),
    )

    assert _latest_validation_metric_value(validation, "net_return") is None
    assert _latest_validation_wallet_kpi_context(validation).startswith("UNAVAILABLE")


def test_loss_streak_escalated_risk_note_tracks_repeat_offender_and_drawdown() -> None:
    no_repeat_validation = YkbValidationDigest(
        symbol="BTCUSDT",
        status="READY",
        latest_run_id="run:no-repeat",
        timeframe="1h",
        playbook="breakout",
        promotion_status="RESEARCH_ONLY",
        run_created_at=NOW.isoformat(),
        metrics=("max_drawdown=0.04",),
        tuning_parameters=("ema_fast=9",),
        artifact_refs=("artifact:test",),
        blockers=(),
    )
    repeated_a = YkbOpportunityBrief(
        **{
            **_valid_opportunity_kwargs(),
            "blockers": ("VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED",),
        }
    )
    repeated_b = YkbOpportunityBrief(
        **{
            **_valid_opportunity_kwargs(),
            "opportunity_id": "opp-repeat-b",
            "symbol": "SOLUSDT",
            "blockers": ("VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED",),
        }
    )
    moderate_validation = YkbValidationDigest(
        symbol="BTCUSDT",
        status="READY",
        latest_run_id="run:moderate",
        timeframe="1h",
        playbook="breakout",
        promotion_status="RESEARCH_ONLY",
        run_created_at=NOW.isoformat(),
        metrics=("max_drawdown=0.08", "net_return=-0.03"),
        tuning_parameters=("ema_fast=9",),
        artifact_refs=("artifact:test",),
        blockers=(),
    )
    high_validation = YkbValidationDigest(
        symbol="BTCUSDT",
        status="READY",
        latest_run_id="run:high",
        timeframe="1h",
        playbook="breakout",
        promotion_status="RESEARCH_ONLY",
        run_created_at=NOW.isoformat(),
        metrics=("max_drawdown=0.12", "net_return=-0.07"),
        tuning_parameters=("ema_fast=9",),
        artifact_refs=("artifact:test",),
        blockers=(),
    )
    fragile_edge_validation = YkbValidationDigest(
        symbol="BTCUSDT",
        status="READY",
        latest_run_id="run:fragile",
        timeframe="1h",
        playbook="breakout",
        promotion_status="RESEARCH_ONLY",
        run_created_at=NOW.isoformat(),
        metrics=("max_drawdown=0.12", "net_return=0.02"),
        tuning_parameters=("ema_fast=9",),
        artifact_refs=("artifact:test",),
        blockers=(),
    )

    assert _loss_streak_escalated_risk_note((repeated_a,), no_repeat_validation) == (
        "LOW_ESCALATION (repeat offender yok; max_drawdown=`0.04` izleme amacli tutuluyor)."
    )
    assert _loss_streak_escalated_risk_note(
        (repeated_a, repeated_b),
        moderate_validation,
    ) == (
        "MODERATE_ESCALATION (repeat offender var; net_return=`-0.03` negatif ve "
        "max_drawdown=`0.08` kritik esik alti olsa da pattern yeniden validasyona alinmali)."
    )
    assert _loss_streak_escalated_risk_note(
        (repeated_a, repeated_b),
        high_validation,
    ) == (
        "HIGH_ESCALATION (repeat offender + max_drawdown=`0.12` + net_return=`-0.07` "
        "negatif; bounded revalidation ve root-cause incelemesi hizlandirilmali)."
    )
    assert _loss_streak_escalated_risk_note(
        (repeated_a, repeated_b),
        fragile_edge_validation,
    ) == (
        "FRAGILE_EDGE_ESCALATION (repeat offender + max_drawdown=`0.12` yuksek ama "
        "net_return=`0.02` pozitif; edge kirilgan olabilir ve koruyucu yeniden "
        "validasyon gerekli)."
    )


def test_resolve_halt_review_artifact_path_prefers_existing_latest_report(
    tmp_path: Path,
) -> None:
    latest_report = (
        tmp_path
        / "runtime"
        / "artifacts"
        / "user_reports"
        / "virtual_loss_streak_halt_review"
        / "latest.json"
    )
    latest_report.parent.mkdir(parents=True, exist_ok=True)
    latest_report.write_text('{"status":"ACTIVE"}\n', encoding="utf-8")

    assert (
        _resolve_halt_review_artifact_path(
            tmp_path,
            "ARTIFACT_REF_NOT_PUBLISHED",
            "ARTIFACT_PATH_UNRESOLVED",
        )
        == "runtime/artifacts/user_reports/virtual_loss_streak_halt_review/latest.json"
    )


def test_find_halt_review_artifact_for_ref_prefers_exact_historical_match(
    tmp_path: Path,
) -> None:
    report_dir = (
        tmp_path
        / "runtime"
        / "artifacts"
        / "user_reports"
        / "virtual_loss_streak_halt_review"
    )
    report_dir.mkdir(parents=True, exist_ok=True)
    older = report_dir / "virtual_loss_streak_halt_review_20260825T090000Z.json"
    latest = report_dir / "latest.json"
    older.write_text(
        '{"review_id":"virtual-loss-streak-halt:ethusdt:spot:1h","status":"ACTIVE"}\n',
        encoding="utf-8",
    )
    latest.write_text(
        '{"review_id":"virtual-loss-streak-halt:other:spot:1h","status":"ACTIVE"}\n',
        encoding="utf-8",
    )

    assert _find_halt_review_artifact_for_ref(
        tmp_path,
        "virtual-loss-streak-halt:ethusdt:spot:1h",
    ) == (
        "runtime/artifacts/user_reports/virtual_loss_streak_halt_review/virtual_loss_streak_halt_review_20260825T090000Z.json"
    )


def test_find_halt_review_artifact_for_ref_prefers_registry_before_scan(
    tmp_path: Path,
) -> None:
    report_dir = (
        tmp_path
        / "runtime"
        / "artifacts"
        / "user_reports"
        / "virtual_loss_streak_halt_review"
    )
    report_dir.mkdir(parents=True, exist_ok=True)
    stamped = report_dir / "virtual_loss_streak_halt_review_20260825T090000Z.json"
    stamped.write_text(
        '{"review_id":"virtual-loss-streak-halt:ethusdt:spot:1h","status":"ACTIVE"}\n',
        encoding="utf-8",
    )
    registry = report_dir / "review_registry_latest.json"
    registry.write_text(
        json.dumps(
            {
                "review_ref": "virtual-loss-streak-halt:ethusdt:spot:1h",
                "artifact_path": (
                    "runtime/artifacts/user_reports/virtual_loss_streak_halt_review/virtual_loss_streak_halt_review_20260825T090000Z.json"
                ),
                "latest_artifact_path": "runtime/artifacts/user_reports/virtual_loss_streak_halt_review/latest.json",
                "generated_at": "20260825T090000Z",
                "status": "ACTIVE",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    assert _find_halt_review_artifact_for_ref(
        tmp_path,
        "virtual-loss-streak-halt:ethusdt:spot:1h",
    ) == (
        "runtime/artifacts/user_reports/virtual_loss_streak_halt_review/virtual_loss_streak_halt_review_20260825T090000Z.json"
    )


def test_find_halt_review_artifact_for_ref_prefers_registry_history_before_latest(
    tmp_path: Path,
) -> None:
    report_dir = (
        tmp_path
        / "runtime"
        / "artifacts"
        / "user_reports"
        / "virtual_loss_streak_halt_review"
    )
    report_dir.mkdir(parents=True, exist_ok=True)
    exact = report_dir / "virtual_loss_streak_halt_review_20260825T090000Z.json"
    latest = report_dir / "latest.json"
    exact.write_text(
        '{"review_id":"virtual-loss-streak-halt:ethusdt:spot:1h","status":"ACTIVE"}\n',
        encoding="utf-8",
    )
    latest.write_text(
        '{"review_id":"virtual-loss-streak-halt:other:spot:1h","status":"ACTIVE"}\n',
        encoding="utf-8",
    )
    registry_history = report_dir / "review_registry.jsonl"
    registry_history.write_text(
        json.dumps(
            {
                "review_ref": "virtual-loss-streak-halt:ethusdt:spot:1h",
                "artifact_path": (
                    "runtime/artifacts/user_reports/virtual_loss_streak_halt_review/virtual_loss_streak_halt_review_20260825T090000Z.json"
                ),
                "latest_artifact_path": "runtime/artifacts/user_reports/virtual_loss_streak_halt_review/latest.json",
                "generated_at": "20260825T090000Z",
                "status": "ACTIVE",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    registry_latest = report_dir / "review_registry_latest.json"
    registry_latest.write_text(
        json.dumps(
            {
                "review_ref": "virtual-loss-streak-halt:ethusdt:spot:1h",
                "artifact_path": "runtime/artifacts/user_reports/virtual_loss_streak_halt_review/latest.json",
                "latest_artifact_path": "runtime/artifacts/user_reports/virtual_loss_streak_halt_review/latest.json",
                "generated_at": "20260825T100000Z",
                "status": "ACTIVE",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    assert _find_halt_review_artifact_for_ref(
        tmp_path,
        "virtual-loss-streak-halt:ethusdt:spot:1h",
    ) == (
        "runtime/artifacts/user_reports/virtual_loss_streak_halt_review/virtual_loss_streak_halt_review_20260825T090000Z.json"
    )


def test_ykb_brief_resolves_loss_streak_halt_artifact_path_from_local_reports(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(monkeypatch, tmp_path)
    latest_report = (
        tmp_path
        / "runtime"
        / "artifacts"
        / "user_reports"
        / "virtual_loss_streak_halt_review"
        / "latest.json"
    )
    latest_report.parent.mkdir(parents=True, exist_ok=True)
    latest_report.write_text(
        '{"review_id":"virtual-loss-streak-halt:ethusdt:spot:1h","status":"ACTIVE"}\n',
        encoding="utf-8",
    )

    def halted_opportunities(symbol: str | None) -> dict[str, object]:
        normalized = (symbol or "ETHUSDT").upper()
        return {
            "command": "opportunities",
            "status": "ACTIVE",
            "inbox": {
                "symbol": normalized,
                "items": (
                    {
                        "market": "SPOT",
                        "symbol": normalized,
                        "setup_name": "breakout_retest",
                        "timeframe": "1h",
                        "direction": "BULLISH",
                        "status": "WATCHLIST",
                        "promotion_status": "RESEARCH_ONLY",
                        "score": 64.0,
                        "confidence": 0.61,
                        "target_risk_reward": "2",
                        "blockers": (
                            "VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED",
                            "RISK_APPROVAL_MISSING",
                        ),
                    },
                ),
            },
            "blockers": (
                "VIRTUAL_LOSS_STREAK_LIMIT_EXCEEDED",
                "RISK_APPROVAL_MISSING",
            ),
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }

    brief = build_ykb_executive_brief(
        settings,
        repository_root=tmp_path,
        symbol="ETHUSDT",
        observed_at=NOW,
        portfolio_builder=lambda settings: _portfolio_payload(),
        opportunities_builder=lambda settings, symbol: halted_opportunities(symbol),
        auto_audit_runner=lambda *args, **kwargs: _auto_audit(tmp_path),
    )

    persisted = json.loads(brief.json_path.read_text(encoding="utf-8"))

    assert persisted["opportunities"][0]["halt_review_artifact_path"] == (
        "runtime/artifacts/user_reports/virtual_loss_streak_halt_review/latest.json"
    )
    assert persisted["opportunity_funnel"][
        "loss_streak_halt_review_artifact_paths"
    ] == ["runtime/artifacts/user_reports/virtual_loss_streak_halt_review/latest.json"]
    assert persisted["opportunity_funnel"]["loss_streak_halt_review_artifacts"][0] == {
        "scope": "SPOT:ETHUSDT:breakout_retest:1h",
        "review_ref": "virtual-loss-streak-halt:ethusdt:spot:1h",
        "artifact_path": "runtime/artifacts/user_reports/virtual_loss_streak_halt_review/latest.json",
    }


def test_ykb_funding_recommendations_are_blocker_aware() -> None:
    quote_ready = YkbFinancialSituation(
        status="READY",
        spot_asset_count=1,
        futures_position_count=0,
        reconciliation_status="CLEAN",
        value_disclosure="REDACTED_SUMMARY_ONLY",
        known_value_present=True,
        blockers=(),
        spot_assets=(
            YkbSpotAssetRow(
                asset="USDT",
                asset_class="QUOTE_CASH",
                free_state="FREE_CAPITAL_PRESENT",
                locked_state="NO_LOCKED_CAPITAL",
                value_bucket="MEDIUM",
                liquidity_bucket="READY",
                value_report_state="REPORTABLE_GE_2_USDT",
            ),
        ),
    )
    no_quote = YkbFinancialSituation(
        status="READY",
        spot_asset_count=0,
        futures_position_count=0,
        reconciliation_status="CLEAN",
        value_disclosure="REDACTED_SUMMARY_ONLY",
        known_value_present=False,
        blockers=(),
    )

    ready_funding = _funding_recommendation(
        {"required_capital_usdt": "10"},
        quote_ready,
        (),
    )
    assert ready_funding.funding_requirement == "CURRENT_QUOTE_CAPITAL_REVIEW"
    assert ready_funding.free_quote_sufficiency == "FREE_QUOTE_POTENTIALLY_SUFFICIENT"
    assert ready_funding.funding_blockers == ()
    assert _portfolio_funding_recommendation(quote_ready) == (
        "QUOTE_LIQUIDITY_AVAILABLE_FOR_MANUAL_REVIEW"
    )

    blocked_funding = _funding_recommendation({}, no_quote, ("OOS_APPROVAL_MISSING",))
    assert blocked_funding.funding_requirement == "MANUAL_LIQUIDITY_REVIEW_REQUIRED"
    assert "REQUIRED_CAPITAL_UNKNOWN" in blocked_funding.funding_blockers
    assert "OOS_APPROVAL_MISSING" in blocked_funding.funding_blockers
    assert _portfolio_funding_recommendation(no_quote) == (
        "MANUAL_LIQUIDITY_PREPARATION_REQUIRED"
    )


def test_ykb_financial_rows_and_wallet_management_stay_fail_closed() -> None:
    with pytest.raises(ValueError, match="spot asset row identity"):
        YkbSpotAssetRow(
            asset=" ",
            asset_class="QUOTE_CASH",
            free_state="FREE",
            locked_state="LOCKED",
            value_bucket="LOW",
            liquidity_bucket="READY",
        )
    with pytest.raises(ValueError, match="spot asset row cannot authorize execution"):
        YkbSpotAssetRow(
            asset="USDT",
            asset_class="QUOTE_CASH",
            free_state="FREE",
            locked_state="LOCKED",
            value_bucket="LOW",
            liquidity_bucket="READY",
            execution_allowed=True,
        )
    with pytest.raises(ValueError, match="futures position row identity"):
        YkbFuturesPositionRow(
            symbol=" ",
            position_side="LONG",
            exposure_bucket="LOW",
            margin_state="OK",
            risk_state="REVIEW",
        )
    with pytest.raises(ValueError, match="open order row cannot authorize execution"):
        YkbOpenOrderRow(
            market="SPOT",
            symbol="HOTUSDT",
            side="BUY",
            order_type="LIMIT",
            status="NEW",
            locked_liquidity_bucket="LOW",
            stale_state="FRESH",
            live_eligibility_status="READY",
        )
    with pytest.raises(ValueError, match="inventory heatmap row identity"):
        YkbInventoryHeatmapRow(
            inventory_group="HOT",
            concentration_bucket=" ",
            liquidity_bucket="READY",
            action_hint="REVIEW",
        )

    futures = (
        YkbFuturesPositionRow(
            symbol="BTCUSDT",
            position_side="SHORT",
            exposure_bucket="HIGH",
            margin_state="REVIEW",
            risk_state="HIGH_RISK",
        ),
    )
    orders = (
        YkbOpenOrderRow(
            market="SPOT",
            symbol="HOTUSDT",
            side="BUY",
            order_type="LIMIT",
            status="NEW",
            locked_liquidity_bucket="MEDIUM",
            stale_state="FRESH",
        ),
    )
    heatmap = _inventory_heatmap_rows((), futures, orders, "MISMATCH")
    groups = {row.inventory_group for row in heatmap}
    assert groups == {"FUTURES_EXPOSURE", "OPEN_ORDERS", "RECONCILIATION"}

    blocked_financial = YkbFinancialSituation(
        status="BLOCKED",
        spot_asset_count=0,
        futures_position_count=0,
        reconciliation_status="MISMATCH",
        value_disclosure="REDACTED_SUMMARY_ONLY",
        known_value_present=False,
        blockers=("RECONCILIATION_REQUIRED",),
    )
    blocked_management = _wallet_position_management(
        blocked_financial,
        {"account_snapshot": {"position_blockers": ("SNAPSHOT_STALE",)}},
    )
    assert blocked_management.status == "BLOCKED"
    assert "SNAPSHOT_STALE" in blocked_management.blockers

    futures_financial = YkbFinancialSituation(
        status="READY",
        spot_asset_count=0,
        futures_position_count=1,
        reconciliation_status="CLEAN",
        value_disclosure="REDACTED_SUMMARY_ONLY",
        known_value_present=True,
        blockers=(),
        futures_positions=futures,
    )
    assert _wallet_position_management(futures_financial, {}).status == (
        "REVIEW_REQUIRED"
    )
    empty_financial = YkbFinancialSituation(
        status="DEGRADED",
        spot_asset_count=0,
        futures_position_count=0,
        reconciliation_status="CLEAN",
        value_disclosure="REDACTED_SUMMARY_ONLY",
        known_value_present=False,
        blockers=(),
    )
    empty_management = _wallet_position_management(empty_financial, {})
    assert empty_management.status == "DEGRADED"
    assert "WALLET_POSITION_CONTEXT_EMPTY" in empty_management.blockers

    spot_financial = YkbFinancialSituation(
        status="READY",
        spot_asset_count=1,
        futures_position_count=0,
        reconciliation_status="CLEAN",
        value_disclosure="REDACTED_SUMMARY_ONLY",
        known_value_present=True,
        blockers=(),
        spot_assets=(
            YkbSpotAssetRow(
                asset="HOT",
                asset_class="BASE_ASSET",
                free_state="FREE_CAPITAL_PRESENT",
                locked_state="NO_LOCKED_CAPITAL",
                value_bucket="MEDIUM",
                liquidity_bucket="READY",
            ),
        ),
    )
    spot_management = _wallet_position_management(spot_financial, {})
    assert spot_management.status == "READY_FOR_REVIEW"
    assert spot_management.recommendation == (
        "MONITOR_SPOT_CONCENTRATION_AND_REBALANCE_ONLY_AFTER_OOS"
    )


def test_ykb_agent_audit_command_names_fail_closed_on_import_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_import = __import__

    def guarded_import(
        name: str,
        globals: Mapping[str, object] | None = None,
        locals: Mapping[str, object] | None = None,
        fromlist: Sequence[str] | None = (),
        level: int = 0,
    ) -> object:
        if name == "ai4binance.cli.commands":
            raise ImportError("commands unavailable")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", guarded_import)

    assert _agent_audit_command_names() == ()


def test_ykb_open_web_helpers_reject_invalid_articles(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(monkeypatch, tmp_path)
    settings.open_web_evidence_ledger_path.parent.mkdir(parents=True, exist_ok=True)
    settings.open_web_evidence_ledger_path.write_text("x" * 2_000_001, encoding="utf-8")

    assert _read_open_web_ledger_mappings(settings) == ()
    assert _is_web_article_record(
        {"source_type": "RSS"}, {"source_type": "WEB_ARTICLE"}
    )
    assert not _is_web_article_record({"source_type": "RSS"}, {"source_type": "NEWS"})
    assert _is_relevant_open_web_article({}, "HOTUSDT")
    assert not _is_relevant_open_web_article({"symbols": ("ETHUSDT",)}, "HOTUSDT")
    assert _aware_datetime(None) is None
    assert _aware_datetime("not-a-date") is None
    assert _aware_datetime("2026-08-13T12:00:00") is None
    assert _unit_float(True, default=0.4) == 0.4
    assert _unit_float("bad", default=0.4) == 0.4
    assert _unit_float("2", default=0.4) == 1.0
    assert _unit_float("-1", default=0.4) == 0.0
    assert _open_web_article_impact(0.8) == "HIGH"
    assert _open_web_article_impact(0.6) == "MEDIUM"
    assert _open_web_article_impact(0.2) == "LOW"
    assert _open_web_retrieved_document({"retrieved_at": "bad"}) is None
    assert (
        _open_web_retrieved_document(
            {
                "retrieved_at": NOW.isoformat(),
                "canonical_uri": "not-a-url",
                "content_sha256": "too-short",
            }
        )
        is None
    )


def test_ykb_runtime_feed_context_filters_irrelevant_or_weak_inputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(monkeypatch, tmp_path)
    _append_jsonl(
        settings.runtime_technology_feed_path,
        {
            "symbol": "ETHUSDT",
            "title": "Wrong symbol upgrade",
            "impact": "CRITICAL",
            "source": "tech",
            "source_url": "https://tech.example/wrong",
            "as_of": NOW.isoformat(),
        },
    )
    _append_jsonl(
        settings.runtime_technology_feed_path,
        {
            "symbol": "HOTUSDT",
            "source": "tech",
            "source_url": "https://tech.example/high",
            "impact": "HIGH",
            "as_of": NOW.isoformat(),
            "opportunity_hint": "Review only after validation",
        },
    )
    _append_jsonl(
        settings.runtime_news_feed_path,
        {
            "symbol": "HOTUSDT",
            "title": "Low impact bulletin",
            "impact": "INFO",
            "source": "news",
            "source_url": "https://news.example/low",
            "scheduled_at": NOW.isoformat(),
        },
    )
    _append_jsonl(
        settings.runtime_news_feed_path,
        {
            "symbol": "ALL",
            "title": "Critical exchange outage",
            "impact": "CRITICAL",
            "source": "news",
            "source_url": "https://news.example/critical",
            "scheduled_at": NOW.isoformat(),
        },
    )
    _append_jsonl(
        settings.runtime_social_feed_path,
        {
            "symbol": "HOTUSDT",
            "event_id": "weak-social",
            "source": "social",
            "source_url": "https://x.com/example/weak",
            "score": 59,
            "directional_vote": 0.9,
            "as_of": NOW.isoformat(),
        },
    )
    _append_jsonl(
        settings.runtime_content_feed_path,
        {
            "symbol": "MARKET_WIDE",
            "event_id": "strong-content",
            "source": "content",
            "source_url": "https://content.example/strong",
            "score": 70,
            "directional_vote": 0.1,
            "as_of": NOW.isoformat(),
        },
    )

    items = _runtime_feed_context_items(settings, "HOTUSDT")

    assert {item.category for item in items} == {
        "TECHNOLOGY_DEVELOPMENT",
        "IMPORTANT_NEWS",
        "IMPORTANT_CONTEXT",
    }
    assert all(item.execution_allowed is False for item in items)
    assert all(item.live_eligibility_status == "LIVE_ORDER_BLOCKED" for item in items)
    assert "Wrong symbol upgrade" not in {item.title for item in items}
    assert "Low impact bulletin" not in {item.title for item in items}
    assert "weak-social" not in {item.title for item in items}
    tech = next(item for item in items if item.category == "TECHNOLOGY_DEVELOPMENT")
    assert tech.title == "Teknolojik gelisme: tech"
    assert tech.recommendation == "Review only after validation"
    content = next(item for item in items if item.category == "IMPORTANT_CONTEXT")
    assert content.impact == "MEDIUM"


def test_ykb_runtime_open_web_context_remains_research_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(monkeypatch, tmp_path)
    _write_open_web_article(settings.open_web_evidence_ledger_path)
    monkeypatch.setattr(ykb_module, "analyze_technology", lambda *args, **kwargs: None)

    assert _runtime_open_web_article_context_items(settings, "HOTUSDT") == ()


def test_ykb_report_excludes_stable_wrapped_and_leveraged_token_opportunities(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(monkeypatch, tmp_path)
    _write_run_card(settings.validation_artifact_directory, "HOTUSDT")

    brief = build_ykb_executive_brief(
        settings,
        repository_root=tmp_path,
        symbol="HOTUSDT",
        observed_at=NOW,
        portfolio_builder=lambda settings: _portfolio_payload(blockers=()),
        opportunities_builder=lambda settings, symbol: {
            "command": "opportunities",
            "status": "ACTIVE",
            "inbox": {
                "symbol": symbol,
                "items": (
                    {
                        "market": "SPOT",
                        "symbol": "USDCUSDT",
                        "setup_name": "stablecoin_noise",
                        "timeframe": "1h",
                        "direction": "BULLISH",
                        "score": 80,
                        "confidence": 0.8,
                    },
                    {
                        "market": "SPOT",
                        "symbol": "WBTCUSDT",
                        "setup_name": "wrapped_noise",
                        "timeframe": "1h",
                        "direction": "BULLISH",
                        "score": 80,
                        "confidence": 0.8,
                    },
                    {
                        "market": "SPOT",
                        "symbol": "BTCUPUSDT",
                        "setup_name": "leveraged_noise",
                        "timeframe": "1h",
                        "direction": "BULLISH",
                        "score": 80,
                        "confidence": 0.8,
                    },
                    {
                        "market": "SPOT",
                        "symbol": "HOTUSDT",
                        "setup_name": "support_reclaim",
                        "timeframe": "1h",
                        "direction": "BULLISH",
                        "score": 66,
                        "confidence": 0.6,
                        "target_risk_reward": "2",
                    },
                ),
            },
            "blockers": ("OOS_APPROVAL_MISSING",),
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        },
        auto_audit_runner=lambda *args, **kwargs: _auto_audit(tmp_path, blockers=()),
    )

    assert [item.symbol for item in brief.opportunities] == ["HOTUSDT"]
    rendered = brief.markdown_path.read_text(encoding="utf-8")
    assert "USDCUSDT" not in rendered
    assert "WBTCUSDT" not in rendered
    assert "BTCUPUSDT" not in rendered


def test_ykb_brief_reports_no_visible_opportunity_without_live_authority(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(monkeypatch, tmp_path)

    brief = build_ykb_executive_brief(
        settings,
        repository_root=tmp_path,
        observed_at=NOW,
        portfolio_builder=lambda settings: _portfolio_payload(blockers=()),
        opportunities_builder=lambda settings, symbol: {
            "command": "opportunities",
            "status": "DEGRADED",
            "inbox": {"symbol": symbol, "items": ()},
            "blockers": ("NO_VISIBLE_OPPORTUNITY_EVIDENCE",),
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        },
        auto_audit_runner=lambda *args, **kwargs: _auto_audit(
            tmp_path,
            blockers=("opportunities:NO_VISIBLE_OPPORTUNITY_EVIDENCE",),
        ),
    )

    assert brief.opportunities == ()
    assert "NO_USER_FRIENDLY_OPPORTUNITY_AVAILABLE" in brief.blockers
    assert brief.execution_allowed is False
    assert brief.promotion_status == "RESEARCH_ONLY"
    assert brief.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    rendered = brief.markdown_path.read_text(encoding="utf-8")
    assert (
        "No visible SPOT research candidate and no virtual-market-ready trade plan row."
        in rendered
    )
    assert "Firsat yok; tablo satiri olusturulmadi." not in rendered
    assert "FIRSAT_YOK" not in rendered
    assert "ADAY_YOK" not in rendered


def test_ykb_consumes_latest_market_wide_radar_snapshot_by_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(monkeypatch, tmp_path)
    radar = build_opportunity_radar_snapshot(
        (_canonical_radar_market_snapshot(),),
        cycle_id="ykb-market-wide",
        observed_at=NOW,
    )
    write_opportunity_radar_snapshot(
        radar,
        settings.evidence_artifact_directory / "opportunity-radar" / "latest.json",
    )

    brief = build_ykb_executive_brief(
        settings,
        repository_root=tmp_path,
        observed_at=NOW,
        portfolio_builder=lambda settings: _portfolio_payload(blockers=()),
        auto_audit_runner=lambda *args, **kwargs: _auto_audit(tmp_path, blockers=()),
    )

    assert [item.symbol for item in brief.opportunities] == ["HOTUSDT"]
    opportunity = brief.opportunities[0]
    assert opportunity.market == "SPOT"
    assert opportunity.setup_name == "session_vwap_reclaim"
    assert opportunity.entry != "PENDING_VALIDATED_LEVEL"
    assert "OOS_NOT_COMPLETE" in opportunity.promotion_requirements
    assert "LIVE_ORDER_BLOCKED" in opportunity.execution_blockers
    assert brief.latest_validation.symbol == settings.validation_symbol
    assert brief.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    rendered = brief.markdown_path.read_text(encoding="utf-8")
    assert "HOTUSDT" in rendered
    assert "session_vwap_reclaim" in rendered


def test_ykb_deduplicates_semantic_opportunities_and_keeps_distinct_setups_visible(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(monkeypatch, tmp_path)

    brief = build_ykb_executive_brief(
        settings,
        repository_root=tmp_path,
        symbol="HOTUSDT",
        observed_at=NOW,
        portfolio_builder=lambda settings: _portfolio_payload(blockers=()),
        opportunities_builder=lambda settings, symbol: {
            "command": "opportunities",
            "status": "ACTIVE",
            "inbox": {
                "symbol": symbol,
                "items": (
                    {
                        "market": "SPOT",
                        "symbol": "HOTUSDT",
                        "setup_name": "support_reclaim",
                        "timeframe": "1h",
                        "direction": "BULLISH",
                        "status": "WATCHLIST",
                        "promotion_status": "RESEARCH_ONLY",
                        "score": 63,
                        "confidence": 0.60,
                        "target_risk_reward": "2",
                        "blockers": ("OOS_APPROVAL_MISSING",),
                    },
                    {
                        "market": "SPOT",
                        "symbol": "HOTUSDT",
                        "setup_name": "support_reclaim",
                        "timeframe": "1h",
                        "direction": "BULLISH",
                        "status": "WATCHLIST",
                        "promotion_status": "RESEARCH_ONLY",
                        "score": 72,
                        "confidence": 0.66,
                        "target_risk_reward": "2",
                        "blockers": ("OOS_APPROVAL_MISSING",),
                    },
                    {
                        "market": "SPOT",
                        "symbol": "HOTUSDT",
                        "setup_name": "breakout_retest",
                        "timeframe": "1h",
                        "direction": "BULLISH",
                        "status": "WATCHLIST",
                        "promotion_status": "RESEARCH_ONLY",
                        "score": 70,
                        "confidence": 0.64,
                        "target_risk_reward": "2",
                        "blockers": ("OOS_APPROVAL_MISSING",),
                    },
                ),
            },
            "blockers": ("OOS_APPROVAL_MISSING",),
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        },
        auto_audit_runner=lambda *args, **kwargs: _auto_audit(tmp_path, blockers=()),
    )

    assert len(brief.opportunities) == 2
    assert [item.setup_name for item in brief.opportunities] == [
        "support_reclaim",
        "breakout_retest",
    ]
    assert [item.pattern_type for item in brief.opportunities] == [
        "REVERSAL_PATTERN",
        "REVERSAL_PATTERN",
    ]
    assert brief.opportunities[0].score == Decimal("72")
    rendered = _normalize_table_spacing(brief.markdown_path.read_text(encoding="utf-8"))
    assert "visible_research_opportunities: `2`" in rendered
    assert "| HOTUSDT | 1h | SPOT | support_reclaim | BUY | 1x |" in rendered
    assert "| HOTUSDT | 1h | SPOT | breakout_retest | BUY | 1x |" in rendered
    assert rendered.count("| HOTUSDT | 1h | SPOT | support_reclaim | BUY | 1x |") == 2


def test_ykb_report_contracts_reject_authority_or_unredacted_financial_values() -> None:
    with pytest.raises(ValueError, match="redact raw values"):
        YkbFinancialSituation(
            status="READY",
            spot_asset_count=1,
            futures_position_count=0,
            reconciliation_status="CLEAN",
            value_disclosure="RAW_VALUES",
            known_value_present=True,
            blockers=(),
        )
    with pytest.raises(ValueError, match="cannot authorize"):
        SemiAutoControlManagement(
            mode="SEMI_AUTO_CONTROL_MANAGEMENT",
            workflow_pattern="HUMAN_IN_THE_LOOP_EVALUATOR_OPTIMIZER",
            blocker_resolution_order_status="PENDING_YKB_APPROVAL",
            risk_oos_live_gate_status="LOCKED_UNTIL_RISK_AND_OOS_EVIDENCE",
            next_management_action="REQUEST_YKB_BLOCKER_ORDER_APPROVAL",
            loop_steps=("AUTO_AUDIT_LOOP",),
            human_approval_gates=("TRADING_SCOPE",),
            stopping_rule="STOP_AT_BLOCKER",
            blockers=("LIVE_ORDER_BLOCKED",),
            execution_allowed=True,
        )


def test_ykb_financial_contract_rejects_negative_counts() -> None:
    with pytest.raises(ValueError, match="counts cannot be negative"):
        YkbFinancialSituation(
            status="BLOCKED",
            spot_asset_count=-1,
            futures_position_count=0,
            reconciliation_status="UNKNOWN",
            value_disclosure="REDACTED_SUMMARY_ONLY",
            known_value_present=False,
            blockers=("RECONCILIATION_REQUIRED",),
        )


@pytest.mark.parametrize(
    ("row_factory", "kwargs", "message"),
    [
        (
            YkbSpotAssetRow,
            {
                "asset": "",
                "asset_class": "QUOTE_CASH",
                "free_state": "FREE_CAPITAL_PRESENT",
                "locked_state": "NO_LOCKED_CAPITAL",
                "value_bucket": "LOW",
                "liquidity_bucket": "READY",
            },
            "identity is required",
        ),
        (
            YkbFuturesPositionRow,
            {
                "symbol": "BTCUSDT",
                "position_side": "LONG",
                "exposure_bucket": "MEDIUM",
                "margin_state": "UNKNOWN",
                "risk_state": "REVIEW_REQUIRED",
                "execution_allowed": True,
            },
            "cannot authorize execution",
        ),
        (
            YkbOpenOrderRow,
            {
                "market": "SPOT",
                "symbol": "",
                "side": "BUY",
                "order_type": "LIMIT",
                "status": "NEW",
                "locked_liquidity_bucket": "LOW",
                "stale_state": "UNKNOWN",
            },
            "identity is required",
        ),
        (
            YkbInventoryHeatmapRow,
            {
                "inventory_group": "QUOTE_CASH",
                "concentration_bucket": "LOW",
                "liquidity_bucket": "READY",
                "action_hint": "REVIEW",
                "live_eligibility_status": "READY",
            },
            "cannot authorize execution",
        ),
    ],
)
def test_ykb_redacted_inventory_rows_reject_invalid_or_authorizing_values(
    row_factory: type[object],
    kwargs: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        row_factory(**kwargs)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("opportunity_id", "", "identity is required"),
        ("score", Decimal("101"), "score must be 0..100"),
        ("confidence", Decimal("1.1"), "confidence must be 0..1"),
        ("target_risk_reward", Decimal("0"), "risk/reward must be positive"),
        ("blockers", ("A", "A"), "blockers must be unique"),
        ("evidence_refs", ("evidence", "evidence"), "evidence refs must be unique"),
        ("execution_allowed", True, "cannot authorize execution"),
        ("promotion_status", "APPROVED", "cannot authorize execution"),
        ("live_eligibility_status", "READY", "cannot authorize execution"),
    ],
)
def test_ykb_opportunity_contract_rejects_unsafe_or_invalid_values(
    field: str,
    value: object,
    message: str,
) -> None:
    kwargs = _valid_opportunity_kwargs()
    kwargs[field] = value

    with pytest.raises(ValueError, match=message):
        YkbOpportunityBrief(**kwargs)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("mode", "AUTO", "mode is invalid"),
        (
            "blocker_resolution_order_status",
            "LIVE_APPROVED",
            "approval status is invalid",
        ),
        (
            "risk_oos_live_gate_status",
            "UNLOCKED",
            "risk/OOS live gate is invalid",
        ),
        ("next_management_action", "", "management action is required"),
        ("loop_steps", (), "requires controls"),
        ("human_approval_gates", (), "requires controls"),
        ("promotion_status", "APPROVED", "cannot authorize execution"),
        ("live_eligibility_status", "READY", "cannot authorize execution"),
    ],
)
def test_semi_auto_management_contract_rejects_control_drift(
    field: str,
    value: object,
    message: str,
) -> None:
    kwargs = _valid_semi_auto_kwargs()
    kwargs[field] = value

    with pytest.raises(ValueError, match=message):
        SemiAutoControlManagement(**kwargs)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("report_id", "", "identity is required"),
        ("executive_summary", "", "identity is required"),
        ("observed_at", datetime(2026, 8, 8, 15, 0), "timezone-aware"),
        ("decision_request", "", "decision request is required"),
        ("blockers", ("A", "A"), "blockers must be unique"),
        ("execution_allowed", True, "cannot authorize execution"),
        ("promotion_status", "APPROVED", "cannot authorize execution"),
        ("live_eligibility_status", "READY", "cannot authorize execution"),
    ],
)
def test_ykb_executive_brief_contract_rejects_unsafe_or_invalid_values(
    tmp_path: Path,
    field: str,
    value: object,
    message: str,
) -> None:
    kwargs = _valid_brief_kwargs(tmp_path)
    kwargs[field] = value

    with pytest.raises(ValueError, match=message):
        YkbExecutiveBrief(**kwargs)


def test_ykb_report_small_helpers_cover_edge_cases() -> None:
    assert _requested_action({"direction": "sell"}) is DgeMarketAction.SELL
    assert _requested_action({"setup_name": "bullish reclaim"}) is DgeMarketAction.BUY
    assert _requested_action({}) is DgeMarketAction.HOLD
    assert _headline("ETHUSDT", "breakout", "APPROVED", ()) == (
        "ETHUSDT breakout: otonom virtual-market simulasyonuna yakin; live yine bloklu."
    )
    assert _financial_fit(_decision(hard_blockers=("OOS_APPROVAL_MISSING",))) == (
        "NOT_FINANCIALLY_ELIGIBLE_YET"
    )
    assert _financial_fit(_decision(soft_blockers=("HUMAN_REVIEW_REQUIRED",))) == (
        "MANUAL_REVIEW_REQUIRED"
    )
    assert _financial_fit(_decision()) == "VIRTUAL_MARKET_AUTONOMOUS_FIT"
    assert _next_action(()) == "PREPARE_VIRTUAL_MARKET_AUTONOMOUS_REVIEW"
    assert _next_action(("BACKTEST_MISSING",)) == "COMPLETE_BACKTEST_WALK_FORWARD_OOS"
    assert _next_action(("RISK_APPROVAL_MISSING",)) == "PREPARE_RISK_REVIEW"
    assert _next_action(("WALLET_POSITION_CONTEXT_UNVERIFIED",)) == (
        "FIX_WALLET_RECONCILIATION"
    )
    assert _next_action(("SOMETHING_ELSE",)) == "REVIEW_TOP_BLOCKER"
    assert _mapping("not-a-map") == {}
    assert _sequence(["a"]) == ("a",)
    assert _sequence("not-a-sequence") == ()
    assert _text_tuple(" blocker ") == ("blocker",)
    assert _text_tuple((" a ", "")) == ("a",)
    assert _safe_int(True) == 0
    assert _safe_int("bad") == 0
    assert _score_decimal("0.5") == Decimal("50.0")
    assert _decimal("bad", Decimal("7")) == Decimal("7")
    assert _decimal("NaN", Decimal("7")) == Decimal("7")
    with pytest.raises(ValueError, match="must be unique"):
        _require_unique_nonblank("items", ("A", "A"))
    with pytest.raises(ValueError, match="cannot contain blanks"):
        _require_unique_nonblank("items", ("",))


def test_ykb_inventory_helper_functions_redact_and_classify_decision_inputs() -> None:
    quote_asset = YkbSpotAssetRow(
        asset="USDT",
        asset_class="QUOTE_CASH",
        free_state="FREE_CAPITAL_PRESENT",
        locked_state="NO_LOCKED_CAPITAL",
        value_bucket="LOW",
        liquidity_bucket="READY",
        value_report_state="REPORTABLE_GE_2_USDT",
    )
    protected_asset = YkbSpotAssetRow(
        asset="HOT",
        asset_class="PROTECTED_POSITION",
        free_state="FREE_CAPITAL_PRESENT",
        locked_state="NO_LOCKED_CAPITAL",
        value_bucket="LOW",
        liquidity_bucket="MANUAL_REVIEW",
        value_report_state="REPORTABLE_GE_2_USDT",
    )
    locked_asset = YkbSpotAssetRow(
        asset="ETH",
        asset_class="SPOT_POSITION",
        free_state="FREE_CAPITAL_PRESENT",
        locked_state="LOCKED_CAPITAL_PRESENT",
        value_bucket="MEDIUM",
        liquidity_bucket="MANUAL_REVIEW",
        value_report_state="REPORTABLE_GE_2_USDT",
    )
    financial = YkbFinancialSituation(
        status="READY",
        spot_asset_count=1,
        futures_position_count=0,
        reconciliation_status="CLEAN",
        value_disclosure="REDACTED_SUMMARY_ONLY",
        known_value_present=True,
        blockers=(),
        spot_assets=(quote_asset,),
    )

    assert _quote_liquidity_bucket(financial) == "READY"
    assert _asset_class("BNB") == "FEE_RESERVE"
    assert _asset_class("HOT") == "PROTECTED_POSITION"
    assert _asset_class("ETH") == "SPOT_POSITION"
    assert _asset_liquidity_bucket("ETH", Decimal("10")) == "MANUAL_REVIEW"
    assert _asset_liquidity_bucket("ETH", None) == "NOT_PROVEN"
    assert _spot_asset_value_report_state("1.99") == (
        "DUST_LT_2_USDT_OMITTED_FROM_PUBLIC_HEATMAP"
    )
    assert _spot_asset_value_report_state("2") == "REPORTABLE_GE_2_USDT"
    assert _spot_asset_value_report_state("") == "VALUE_UNKNOWN_REPORTABLE"
    assert _reportable_spot_assets((quote_asset, protected_asset)) == (
        quote_asset,
        protected_asset,
    )
    assert _asset_action_hint(quote_asset) == "REVIEW_FREE_QUOTE_FOR_MANUAL_LIQUIDITY"
    assert _asset_opportunity_review_hint(quote_asset) == (
        "MANUAL_LIQUIDITY_FOR_APPROVED_SPOT_FUTURES_CANDIDATES"
    )
    assert _asset_action_hint(protected_asset) == (
        "DO_NOT_SELL_WITHOUT_EXPLICIT_OVERRIDE"
    )
    assert _asset_opportunity_review_hint(protected_asset) == (
        "SPOT_FUTURES_VALIDATION_PACKAGE_REQUIRED_NO_AUTO_SELL"
    )
    assert _asset_action_hint(locked_asset) == "REVIEW_LOCKED_ORDERS_NO_AUTO_CANCEL"
    assert (
        _asset_action_hint(
            YkbSpotAssetRow(
                asset="ETH",
                asset_class="SPOT_POSITION",
                free_state="FREE_CAPITAL_PRESENT",
                locked_state="NO_LOCKED_CAPITAL",
                value_bucket="MEDIUM",
                liquidity_bucket="MANUAL_REVIEW",
            )
        )
        == "MONITOR_POSITION_NO_AUTO_ACTION"
    )
    assert _position_side_from_quantity("1") == "LONG"
    assert _position_side_from_quantity("-1") == "SHORT"
    assert _position_side_from_quantity("0") == "UNKNOWN_SIDE"
    assert _highest_bucket(()) == "UNKNOWN"
    assert _highest_bucket(("LOW", "HIGH", "MEDIUM")) == "HIGH"

    ready_funding = _funding_recommendation(
        {"required_capital_usdt": "50"},
        financial,
        blockers=(),
    )
    assert ready_funding.funding_requirement == "CURRENT_QUOTE_CAPITAL_REVIEW"
    assert ready_funding.free_quote_sufficiency == "FREE_QUOTE_POTENTIALLY_SUFFICIENT"

    empty_financial = YkbFinancialSituation(
        status="READY",
        spot_asset_count=0,
        futures_position_count=0,
        reconciliation_status="CLEAN",
        value_disclosure="REDACTED_SUMMARY_ONLY",
        known_value_present=False,
        blockers=(),
        spot_assets=(),
    )
    blocked_funding = _funding_recommendation(
        {"required_capital_usdt": "500"},
        empty_financial,
        blockers=(),
    )
    assert blocked_funding.funding_requirement == (
        "MANUAL_LIQUIDITY_PREPARATION_REQUIRED"
    )
    assert blocked_funding.free_quote_sufficiency == "FREE_QUOTE_NOT_PROVEN"

    unknown_requirement = _funding_recommendation({}, financial, blockers=())
    assert "REQUIRED_CAPITAL_UNKNOWN" in unknown_requirement.funding_blockers


def test_ykb_blocker_order_approval_optimizes_management_without_live_authority(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(monkeypatch, tmp_path)

    brief = build_ykb_executive_brief(
        settings,
        repository_root=tmp_path,
        symbol="ETHUSDT",
        observed_at=NOW,
        blocker_resolution_order_approved=True,
        portfolio_builder=lambda settings: _portfolio_payload(),
        opportunities_builder=lambda settings, symbol: _opportunities_payload(symbol),
        auto_audit_runner=lambda *args, **kwargs: _auto_audit(tmp_path),
    )

    assert brief.semi_auto_control.blocker_resolution_order_status == "APPROVED_BY_YKB"
    assert brief.semi_auto_control.risk_oos_live_gate_status == (
        "LOCKED_UNTIL_RISK_AND_OOS_EVIDENCE"
    )
    assert brief.semi_auto_control.next_management_action == (
        "EXECUTE_APPROVED_BLOCKER_RESOLUTION_ORDER"
    )
    assert "YKB karari kayitli" in brief.decision_request
    assert "ayni onay talebi bu bolumde tekrar listelenmez" in brief.decision_request
    assert "DGE/Auto-Audit takip listesi" not in brief.decision_request
    assert "sahip atanip kanitli kapatma paketi istensin" not in brief.decision_request
    assert all(
        "DGE_HUMAN_REVIEW_RECORDED" in decision.passed_rules
        for decision in brief.dge_decisions
    )
    assert all(
        "HUMAN_REVIEW_REQUIRED" not in decision.soft_blockers
        for decision in brief.dge_decisions
    )
    assert "VAL.OOS_NOT_VALIDATED" in brief.blockers
    assert "RISK.VETO" in brief.blockers
    assert brief.execution_allowed is False
    assert brief.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    rendered = brief.markdown_path.read_text(encoding="utf-8")
    decision_section = _section(rendered, "## YKB Karar Talebi")
    assert "ayni onay talebi bu bolumde tekrar listelenmez" in decision_section
    assert "DGE/Auto-Audit takip listesi" not in decision_section
    assert "sahip atanip kanitli kapatma paketi istensin" not in decision_section


def test_ykb_report_adds_recovery_radar_candidates_through_dge(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(monkeypatch, tmp_path)

    brief = build_ykb_executive_brief(
        settings,
        repository_root=tmp_path,
        symbol="HOTUSDT",
        observed_at=NOW,
        recovery_inventory_units="18400000",
        recovery_range_low="0.000312",
        recovery_range_high="0.000390",
        portfolio_builder=lambda settings: _portfolio_payload(blockers=()),
        opportunities_builder=lambda settings, symbol: _opportunities_payload(symbol),
        auto_audit_runner=lambda *args, **kwargs: _auto_audit(tmp_path),
    )

    assert brief.recovery_radar_status == "RUNNING_WITH_BLOCKERS"
    assert brief.recovery_radar_ref == "recovery-radar:HOTUSDT"
    assert any(
        item.opportunity_id.startswith("recovery:") for item in brief.opportunities
    )
    assert any(
        decision.candidate_id.startswith("recovery:")
        for decision in brief.dge_decisions
    )
    from ai4binance.governance.audit import dge_decision_log_path, dge_event_log_path

    assert dge_event_log_path(tmp_path).exists()
    assert dge_decision_log_path(tmp_path).exists()
    rendered = brief.markdown_path.read_text(encoding="utf-8")
    assert "recovery_radar_status" in rendered
    assert brief.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_ykb_report_cli_renders_user_friendly_text(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from ai4binance import cli

    settings = _settings(monkeypatch, tmp_path)
    brief = build_ykb_executive_brief(
        settings,
        repository_root=tmp_path,
        observed_at=NOW,
        blocker_resolution_order_approved=True,
        portfolio_builder=lambda settings: _portfolio_payload(),
        opportunities_builder=lambda settings, symbol: _opportunities_payload(symbol),
        auto_audit_runner=lambda *args, **kwargs: _auto_audit(tmp_path),
    )
    monkeypatch.setattr(
        cli,
        "build_ykb_executive_brief",
        lambda settings, **kwargs: brief,
    )

    exit_code = cli.main(["ykb-report", "--approve-blocker-order", "--format", "text"])

    output = capsys.readouterr().out
    assert exit_code == 2
    assert "YKB executive brief" in output
    assert "financial:" in output
    assert "blocker_order: APPROVED_BY_YKB" in output
    assert "risk_oos_live_gate: LOCKED_UNTIL_RISK_AND_OOS_EVIDENCE" in output
    assert "opportunities: 1" in output
    assert "LIVE_ORDER_BLOCKED" in output


def _settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    monkeypatch.setenv(
        "AI4BINANCE_RUNTIME_STATE_PATH", str(tmp_path / "state" / "runtime.json")
    )
    monkeypatch.setenv(
        "AI4BINANCE_SKILL_DISCOVERY_STATE_PATH",
        str(tmp_path / "state" / "skill_discovery.json"),
    )
    monkeypatch.setenv(
        "AI4BINANCE_BINANCE_ACCOUNTING_DIRECTORY", str(tmp_path / "Accounting")
    )
    monkeypatch.setenv(
        "AI4BINANCE_VALIDATION_ARTIFACT_DIRECTORY", str(tmp_path / "Validation")
    )
    monkeypatch.setenv("AI4BINANCE_EVIDENCE_ARTIFACT_DIRECTORY", str(tmp_path))
    monkeypatch.setenv(
        "AI4BINANCE_RUNTIME_OPPORTUNITY_REPORT_PATH",
        str(tmp_path / "state" / "runtime_research" / "opportunities-latest.json"),
    )
    monkeypatch.setenv(
        "AI4BINANCE_RUNTIME_TECHNOLOGY_FEED_PATH",
        str(tmp_path / "state" / "runtime_research" / "technology-events.jsonl"),
    )
    monkeypatch.setenv(
        "AI4BINANCE_RUNTIME_NEWS_FEED_PATH",
        str(tmp_path / "state" / "runtime_research" / "news-events.jsonl"),
    )
    monkeypatch.setenv(
        "AI4BINANCE_RUNTIME_SOCIAL_FEED_PATH",
        str(tmp_path / "state" / "runtime_research" / "social-events.jsonl"),
    )
    monkeypatch.setenv(
        "AI4BINANCE_RUNTIME_CONTENT_FEED_PATH",
        str(tmp_path / "state" / "runtime_research" / "content-events.jsonl"),
    )
    monkeypatch.setenv(
        "AI4BINANCE_OPEN_WEB_EVIDENCE_LEDGER_PATH",
        str(tmp_path / "state" / "runtime_research" / "open-web-evidence.jsonl"),
    )
    return Settings()


def _portfolio_payload(
    blockers: tuple[str, ...] = ("RECONCILIATION_REQUIRED",),
) -> dict[str, object]:
    return {
        "command": "portfolio",
        "status": "BLOCKED" if blockers else "READY",
        "account_snapshot": {
            "snapshot_id": "portfolio-1",
            "spot_assets": (
                {
                    "asset": "USDT",
                    "free_qty": "50",
                    "locked_qty": "0",
                    "market_value_usdt": "50",
                    "free_market_value_usdt": "50",
                    "locked_market_value_usdt": "0",
                },
                {
                    "asset": "ETH",
                    "free_qty": "0.5",
                    "locked_qty": "0.1",
                    "market_value_usdt": "100",
                    "free_market_value_usdt": "80",
                    "locked_market_value_usdt": "20",
                },
                {
                    "asset": "DOGE",
                    "free_qty": "5",
                    "locked_qty": "0",
                    "market_value_usdt": "1.50",
                    "free_market_value_usdt": "1.50",
                    "locked_market_value_usdt": "0",
                },
            ),
            "futures": {
                "position_count": 1,
                "positions": (
                    {
                        "symbol": "BTCUSDT",
                        "position_side": "LONG",
                        "notional": "125",
                        "margin_type": "CROSS",
                        "liquidation_price": "50000",
                    },
                ),
                "open_orders": (
                    {
                        "market": "USD_M_FUTURES",
                        "symbol": "BTCUSDT",
                        "side": "SELL",
                        "type": "STOP_MARKET",
                        "status": "NEW",
                        "remaining_quantity": "0.01",
                    },
                ),
            },
            "open_orders": (
                {
                    "market": "SPOT",
                    "symbol": "ETHUSDT",
                    "side": "BUY",
                    "type": "LIMIT",
                    "status": "NEW",
                    "remaining_quantity": "0.1",
                },
            ),
            "total_value_usdt": "150",
            "reconciliation_status": "UNKNOWN" if blockers else "CLEAN",
            "blockers": blockers,
        },
        "blockers": blockers,
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def _opportunities_payload(symbol: str | None) -> dict[str, object]:
    normalized = (symbol or "ETHUSDT").upper()
    return {
        "command": "opportunities",
        "status": "ACTIVE",
        "inbox": {
            "symbol": normalized,
            "items": (
                {
                    "market": "SPOT",
                    "symbol": normalized,
                    "setup_name": "breakout_retest",
                    "timeframe": "1h",
                    "direction": "BULLISH",
                    "status": "WATCHLIST",
                    "promotion_status": "RESEARCH_ONLY",
                    "score": 64.0,
                    "confidence": 0.61,
                    "target_risk_reward": "2",
                    "blockers": (
                        "OOS_APPROVAL_MISSING",
                        "RISK_APPROVAL_MISSING",
                    ),
                },
            ),
        },
        "blockers": ("OOS_APPROVAL_MISSING", "RISK_APPROVAL_MISSING"),
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def _empty_opportunities_payload(symbol: str | None) -> dict[str, object]:
    normalized = (symbol or "BTCUSDT").upper()
    return {
        "command": "opportunities",
        "status": "NO_ACTION",
        "inbox": {"symbol": normalized, "items": ()},
        "blockers": ("NO_READY_CANDIDATE",),
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def _dogeusdt_opportunities_payload() -> dict[str, object]:
    return {
        "command": "opportunities",
        "status": "ACTIVE",
        "inbox": {
            "symbol": "DOGEUSDT",
            "items": (
                {
                    "market": "SPOT",
                    "symbol": "DOGEUSDT",
                    "setup_name": "support_reclaim",
                    "timeframe": "1h",
                    "direction": "BULLISH",
                    "status": "WATCHLIST",
                    "promotion_status": "RESEARCH_ONLY",
                    "score": 72.0,
                    "confidence": 0.68,
                    "target_risk_reward": "2.5",
                    "entry": "0.125",
                    "stop_loss": "0.120",
                    "tp1": "0.132",
                    "tp2": "0.138",
                    "tp3": "0.145",
                    "blockers": (
                        "OOS_APPROVAL_MISSING",
                        "RISK_APPROVAL_MISSING",
                    ),
                },
            ),
        },
        "blockers": ("OOS_APPROVAL_MISSING", "RISK_APPROVAL_MISSING"),
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def _spot_futures_payload(symbol: str | None) -> dict[str, object]:
    normalized = (symbol or "HOTUSDT").upper()
    return {
        "command": "opportunities",
        "status": "ACTIVE",
        "inbox": {
            "symbol": normalized,
            "items": (
                {
                    "market": "SPOT",
                    "symbol": normalized,
                    "setup_name": "support_reclaim",
                    "timeframe": "1h",
                    "direction": "BULLISH",
                    "status": "WATCHLIST",
                    "promotion_status": "RESEARCH_ONLY",
                    "score": 68.0,
                    "confidence": 0.60,
                    "target_risk_reward": "2",
                    "entry": "0.000345",
                    "stop_loss": "0.000331",
                    "tp1": "0.000360",
                    "tp2": "0.000375",
                    "tp3": "0.000390",
                    "blockers": ("OOS_APPROVAL_MISSING",),
                },
                {
                    "market": "USD_M_FUTURES",
                    "symbol": "BTCUSDT",
                    "setup_name": "breakout_retest",
                    "timeframe": "4h",
                    "direction": "BULLISH",
                    "status": "WATCHLIST",
                    "promotion_status": "RESEARCH_ONLY",
                    "score": 66.0,
                    "confidence": 0.58,
                    "target_risk_reward": "2",
                    "leverage": "3x",
                    "entry": "65000",
                    "sl": "63200",
                    "tp1": "66800",
                    "tp2": "68600",
                    "tp3": "70400",
                    "blockers": ("OOS_APPROVAL_MISSING", "FUTURES_REVIEW_REQUIRED"),
                },
            ),
        },
        "blockers": ("OOS_APPROVAL_MISSING",),
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def _write_run_card(root: Path, symbol: str) -> None:
    path = root / symbol / "1h" / "support_reclaim.run-card.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "artifact_sha256": [
                    [
                        f"runtime/artifacts/research/backtest/validation/{symbol}/1h/support_reclaim.jsonl",
                        "sha",
                    ]
                ],
                "blockers": ["OOS_APPROVAL_MISSING"],
                "created_at": NOW.isoformat(),
                "hypothesis_id": "hyp:support_reclaim:1h",
                "metrics": [["net_return", 0.18], ["trade_count", 12.0]],
                "promotion_status": "RESEARCH_ONLY",
                "run_id": "run:hot-latest",
                "selected_parameters": {"ema_fast": 9, "atr_stop_multiplier": "1.5"},
                "symbol": symbol,
                "timeframe": "1h",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    os.utime(path, (NOW.timestamp(), NOW.timestamp()))


def _canonical_radar_market_snapshot() -> MarketSnapshot:
    def rows_for(duration: timedelta) -> tuple[OHLCVCandle, ...]:
        rows: list[OHLCVCandle] = []
        start = NOW - duration * 21
        for index in range(21):
            close = Decimal("100")
            volume = Decimal("100")
            if index == 19:
                close = Decimal("99")
            if index == 20:
                close = Decimal("102")
                volume = Decimal("1000")
            rows.append(
                OHLCVCandle(
                    timestamp=start + duration * index,
                    open=Decimal("100"),
                    high=max(Decimal("103"), close),
                    low=min(Decimal("97"), close),
                    close=close,
                    volume=volume,
                )
            )
        return tuple(rows)

    return MarketSnapshot(
        snapshot_id="ykb-canonical-mtf-snapshot",
        created_at=NOW,
        exchange="Binance",
        market_type="spot",
        symbol="HOTUSDT",
        timeframes=("15m", "1h", "4h", "1d"),
        ohlcv_by_timeframe={
            "15m": rows_for(timedelta(minutes=15)),
            "1h": rows_for(timedelta(hours=1)),
            "4h": rows_for(timedelta(hours=4)),
            "1d": rows_for(timedelta(days=1)),
        },
        latest_price=Decimal("102"),
        bid=Decimal("101.9"),
        ask=Decimal("102.1"),
        spread=Decimal("0.2"),
        data_quality=DataQuality.DATA_VALID,
    )


def _write_runtime_research_report(path: Path) -> None:
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "generated_at": NOW.isoformat(),
                "opportunities": [
                    {
                        "category": "TECHNOLOGY_DEVELOPMENT",
                        "title": "Low-latency inference upgrade launch",
                        "symbol": "AI4BINANCE",
                        "impact": "HIGH",
                        "opportunity_hint": "Review event-level latency pipeline.",
                        "primary_source_url": "https://tech.example/update-1",
                        "source": "tech-feed",
                        "system_benefit": (
                            "Latency evidence improves scanner timing decisions."
                        ),
                        "system_tradeoff": (
                            "Requires local benchmark and rollback proof."
                        ),
                        "as_of": NOW.isoformat(),
                        "ykb_approval_hint": "Approve research spike only.",
                    },
                    {
                        "category": "SENTIMENT_SHIFT_REVIEW",
                        "title": "Social momentum changed",
                        "symbol": "HOTUSDT",
                        "impact": "MEDIUM",
                        "opportunity_hint": "Check sentiment against technical setup.",
                        "primary_source_url": "https://x.com/example/status/9",
                        "source": "social-feed",
                        "as_of": NOW.isoformat(),
                    },
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _write_empty_runtime_research_report(path: Path) -> None:
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "generated_at": NOW.isoformat(),
                "opportunities": [],
                "status": "NO_ACTION",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _append_jsonl(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _write_open_web_article(path: Path) -> None:
    document = RetrievedDocument(
        document_id="web-doc-1",
        observation_id="web-obs-1",
        canonical_uri="https://github.blog/open-web-rag/",
        content_sha256="b" * 64,
        title="Agent orchestration and RAG retrieval security",
        retrieved_at=NOW,
        content_type="text/html",
        byte_count=512,
        text_excerpt=(
            "Agent orchestration, retrieval and context engineering can improve auditable AI systems."
        ),
        author_or_origin="GitHub Blog",
        language="en",
        headings=("Context engineering", "Retrieval hardening"),
        references=("https://github.blog/reference/",),
    )
    observation = ExternalObservation(
        observation_id="web-obs-1",
        provider_id="open_web",
        source_type=SourceType.WEB_ARTICLE,
        source_uri=document.canonical_uri,
        canonical_uri=document.canonical_uri,
        title=document.title,
        content_sha256=document.content_sha256,
        retrieved_at=NOW,
        author_or_origin="GitHub Blog",
        language="en",
        summary=document.text_excerpt,
        raw_reference=document.canonical_uri,
        symbols=("AI4BINANCE",),
        source_credibility=0.85,
        retrieval_confidence=0.9,
        data_quality_status=RetrievalStatus.VALID,
    )
    evidence = ExternalEvidence(
        evidence_id="web-evidence-1",
        source_type=SourceType.WEB_ARTICLE,
        source_uri=document.canonical_uri,
        observed_at=NOW,
        content_sha256=document.content_sha256,
        citation=document.canonical_uri,
        author_or_origin="GitHub Blog",
        reliability=0.85,
        raw_excerpt=document.text_excerpt,
    )
    OpenWebEvidenceStore(path).append(CachedWebRecord(observation, document, evidence))


def _section(markdown: str, heading: str) -> str:
    start = markdown.index(heading)
    next_heading = markdown.find("\n## ", start + len(heading))
    if next_heading == -1:
        return markdown[start:]
    return markdown[start:next_heading]


def _normalize_table_spacing(markdown: str) -> str:
    lines: list[str] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            lines.append(f"| {' | '.join(cells)} |")
        else:
            lines.append(line)
    return "\n".join(lines)


def _pipe_positions(line: str) -> tuple[int, ...]:
    return tuple(index for index, char in enumerate(line) if char == "|")


def _table_lines(markdown: str) -> list[str]:
    return [
        line
        for line in markdown.splitlines()
        if line.startswith("|") and line.endswith("|")
    ]


def _auto_audit(
    root: Path,
    blockers: tuple[str, ...] = ("runtime:RUNTIME_DEGRADED",),
) -> AutoAuditLoopResult:
    cycle = AutoAuditCycle(
        cycle_index=1,
        observed_at=NOW,
        system_status="RUNNING_WITH_BLOCKERS" if blockers else "READY",
        blocker_count=len(blockers),
        blockers=blockers,
        new_blockers=blockers,
        resolved_blockers=(),
        persistent_blockers=(),
        system_report_path=root / "reports" / "operations" / "SYSTEM_REPORT.md",
        system_report_json_path=(
            root / "runtime" / "artifacts" / "system_audit" / "report.json"
        ),
        local_qwen_status="READY",
        local_qwen_report_path=(
            root / "runtime" / "artifacts" / "local-qwen-workbench" / "q.json"
        ),
        local_qwen_blockers=("ADVISORY_ONLY",),
        action_refs=tuple(f"resolve:{blocker}" for blocker in blockers),
    )
    return AutoAuditLoopResult(
        loop_id="auto-audit:test",
        status="RUNNING_WITH_BLOCKERS" if blockers else "READY",
        cycles=(cycle,),
        blockers=blockers,
        json_path=root / "runtime" / "artifacts" / "auto_audit" / "auto-audit.json",
        latest_json_path=(
            root / "runtime" / "artifacts" / "auto_audit" / "latest.json"
        ),
        markdown_path=root / "reports" / "operations" / "AUTO_AUDIT.md",
    )


def _valid_opportunity_kwargs() -> dict[str, Any]:
    return {
        "opportunity_id": "ykb-opportunity:ETHUSDT:1",
        "headline": "ETHUSDT breakout: izlenebilir firsat.",
        "market": "SPOT",
        "symbol": "ETHUSDT",
        "timeframe": "1h",
        "setup_name": "breakout_retest",
        "requested_action": "BUY",
        "governed_action": "NO_TRADE",
        "trade_side": "BUY",
        "leverage": "1x",
        "dge_status": "WATCH_ONLY",
        "score": Decimal("65"),
        "confidence": Decimal("0.60"),
        "target_risk_reward": Decimal("2"),
        "financial_fit": "NOT_FINANCIALLY_ELIGIBLE_YET",
        "funding_requirement": "NO_EXTERNAL_CAPITAL_ALLOWED",
        "required_capital_bucket": "UNKNOWN",
        "free_quote_sufficiency": "UNKNOWN",
        "manual_liquidity_preparation": "MANUAL_REVIEW_REQUIRED",
        "external_capital_policy": "NO_EXTERNAL_CAPITAL_ALLOWED",
        "conversion_or_transfer_policy": "AUTO_MONEY_MOVEMENT_BLOCKED",
        "funding_blockers": ("RECONCILIATION_REQUIRED",),
        "blockers": ("OOS_APPROVAL_MISSING",),
        "next_safe_action": "COMPLETE_BACKTEST_WALK_FORWARD_OOS",
        "evidence_refs": ("opportunities",),
    }


def _valid_semi_auto_kwargs() -> dict[str, Any]:
    return {
        "mode": "SEMI_AUTO_CONTROL_MANAGEMENT",
        "workflow_pattern": "HUMAN_IN_THE_LOOP_EVALUATOR_OPTIMIZER",
        "blocker_resolution_order_status": "PENDING_YKB_APPROVAL",
        "risk_oos_live_gate_status": "LOCKED_UNTIL_RISK_AND_OOS_EVIDENCE",
        "next_management_action": "REQUEST_YKB_BLOCKER_ORDER_APPROVAL",
        "loop_steps": ("AUTO_AUDIT_LOOP",),
        "human_approval_gates": ("TRADING_SCOPE",),
        "stopping_rule": "STOP_AT_BLOCKER",
        "blockers": ("LIVE_ORDER_BLOCKED",),
    }


def _valid_brief_kwargs(tmp_path: Path) -> dict[str, Any]:
    return {
        "report_id": "ykb-report:test",
        "observed_at": NOW,
        "status": "RUNNING_WITH_BLOCKERS",
        "executive_summary": "Sistem izleme modunda.",
        "auto_audit_status": "RUNNING_WITH_BLOCKERS",
        "auto_audit_ref": str(tmp_path / "auto-audit.json"),
        "auto_audit_recommendations": ("resolve:blocker",),
        "agent_audit_status": "REVISION_REQUIRED",
        "agent_audit_ref": "agent-stack-audit:test",
        "agent_audit_recommendations": ("fix:agent-stack",),
        "technology_opportunities": (
            YkbContextItem(
                category="TECHNOLOGY_DEVELOPMENT",
                title="Tech item",
                impact="MEDIUM",
                recommendation="Review",
                source="local",
                source_url="artifact://tech",
                as_of=NOW.isoformat(),
            ),
        ),
        "important_context": (
            YkbContextItem(
                category="NEWS",
                title="News item",
                impact="LOW",
                recommendation="Monitor",
                source="local",
                source_url="artifact://news",
                as_of=NOW.isoformat(),
            ),
        ),
        "latest_validation": YkbValidationDigest(
            symbol="ETHUSDT",
            status="BACKTEST_RUN_CARD_MISSING",
            latest_run_id="KAYIT_YOK",
            timeframe="MULTI_TF_REVIEW",
            playbook="PLAYBOOK_NOT_PROVEN",
            promotion_status="RESEARCH_ONLY",
            run_created_at="KAYIT_YOK",
            metrics=("METRICS_NOT_PUBLISHED",),
            tuning_parameters=("TUNING_PARAMETERS_NOT_PUBLISHED",),
            artifact_refs=("ARTIFACT_REF_NOT_PUBLISHED",),
            blockers=("BACKTEST_RUN_CARD_UNAVAILABLE",),
        ),
        "financial_situation": YkbFinancialSituation(
            status="BLOCKED",
            spot_asset_count=1,
            futures_position_count=0,
            reconciliation_status="UNKNOWN",
            value_disclosure="REDACTED_SUMMARY_ONLY",
            known_value_present=True,
            blockers=("RECONCILIATION_REQUIRED",),
        ),
        "wallet_position_management": YkbWalletPositionManagement(
            status="BLOCKED",
            recommendation="FIX_WALLET_RECONCILIATION_BEFORE_POSITION_ACTION",
            spot_asset_count=1,
            futures_position_count=0,
            open_position_policy="MANUAL_REVIEW_ONLY_NO_AUTO_ORDER",
            blockers=("RECONCILIATION_REQUIRED",),
        ),
        "opportunities": (),
        "dge_decisions": (),
        "semi_auto_control": SemiAutoControlManagement(**_valid_semi_auto_kwargs()),
        "decision_request": "Blocker sirasi onaylansin.",
        "blockers": ("LIVE_ORDER_BLOCKED",),
        "json_path": tmp_path / "ykb.json",
        "markdown_path": tmp_path / "ykb.md",
        "latest_json_path": tmp_path / "latest.json",
    }


def _decision(
    hard_blockers: tuple[str, ...] = (),
    soft_blockers: tuple[str, ...] = (),
) -> GovernedDecision:
    return GovernedDecision(
        decision_id="dge:1",
        candidate_id="candidate:1",
        symbol="ETHUSDT",
        requested_action=DgeMarketAction.BUY,
        governed_action=DgeMarketAction.NO_TRADE
        if hard_blockers
        else DgeMarketAction.BUY,
        governance_status=DgeDecisionStatus.WATCH_ONLY
        if hard_blockers
        else DgeDecisionStatus.MANUAL_REVIEW
        if soft_blockers
        else DgeDecisionStatus.APPROVED_PAPER_ONLY,
        hard_blockers=hard_blockers,
        soft_blockers=soft_blockers,
        passed_rules=("DGE_NO_EXTERNAL_CAPITAL_REQUIRED",),
        failed_rules=(),
        reason_summary="test decision",
        evidence_refs=("opportunities",),
        rule_set_version="test",
        config_hash="hash",
        data_snapshot_id="snapshot",
        semantic_graph_id="graph",
        paper_execution_allowed=not hard_blockers and not soft_blockers,
        requires_manual_confirmation=True,
    )
