from datetime import UTC, datetime
from decimal import Decimal

import pytest

from ai4binance.ontology import (
    SemanticEntityType,
    SemanticRelationType,
    build_position_semantic_graph,
)
from ai4binance.ontology.contracts import (
    SemanticEdge,
    SemanticEntity,
    SemanticGraphContract,
)
from ai4binance.portfolio.asset_policy import AssetPolicy
from ai4binance.portfolio.position_context import (
    CapitalSourceStatus,
    PositionContextBuilder,
    PositionContextRecord,
    PositionContextReport,
    PositionMarket,
    PositionSide,
)
from ai4binance.portfolio.wallet import SpotBalance, WalletSnapshot

NOW = datetime(2026, 8, 8, tzinfo=UTC)


def test_position_semantic_graph_links_positions_assets_and_blockers() -> None:
    wallet = WalletSnapshot(
        NOW,
        "SPOT",
        True,
        (SpotBalance("SOL", Decimal("3"), Decimal("0")),),
        "BTCUSDT",
    )
    report = PositionContextBuilder(
        AssetPolicy(automatic_conversion_enabled=True)
    ).build(
        spot_wallet=wallet,
        prices_usdt={"SOL": Decimal("120")},
    )

    graph = build_position_semantic_graph(report)

    assert graph.graph_id.startswith("semantic-position:")
    assert graph.execution_allowed is False
    assert graph.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert any(
        entity.entity_type is SemanticEntityType.ASSET and entity.label == "SOL"
        for entity in graph.entities
    )
    assert any(
        edge.relation_type is SemanticRelationType.HAS_CAPITAL_SOURCE_STATUS
        for edge in graph.edges
    )
    assert "POSITION_IS_CONTEXT_NOT_THESIS" in graph.blockers


def test_semantic_graph_rejects_edges_to_unknown_entities() -> None:
    entity = SemanticEntity("asset:BTC", SemanticEntityType.ASSET, "BTC")
    edge = SemanticEdge(
        "asset:BTC",
        "missing",
        SemanticRelationType.REPRESENTS,
    )

    with pytest.raises(ValueError, match="unknown entity"):
        SemanticGraphContract("graph:test", (entity,), (edge,), ())


def test_semantic_graph_contracts_reject_blank_duplicate_and_unsafe_values() -> None:
    with pytest.raises(ValueError, match="semantic entity identity"):
        SemanticEntity(" ", SemanticEntityType.ASSET, "BTC")
    with pytest.raises(
        ValueError, match="semantic entity evidence refs must be unique"
    ):
        SemanticEntity(
            "asset:BTC",
            SemanticEntityType.ASSET,
            "BTC",
            ("evidence", "evidence"),
        )
    with pytest.raises(ValueError, match="semantic edge identity"):
        SemanticEdge(" ", "asset:BTC", SemanticRelationType.REPRESENTS)
    with pytest.raises(ValueError, match="self-referential"):
        SemanticEdge("asset:BTC", "asset:BTC", SemanticRelationType.REPRESENTS)
    with pytest.raises(
        ValueError, match="semantic edge evidence refs cannot contain blanks"
    ):
        SemanticEdge(
            "position:1",
            "asset:BTC",
            SemanticRelationType.REPRESENTS,
            (" ",),
        )

    entity = SemanticEntity("asset:BTC", SemanticEntityType.ASSET, "BTC")
    position = SemanticEntity(
        "position:spot:BTCUSDT:1",
        SemanticEntityType.SPOT_POSITION,
        "SPOT:BTC:LONG",
    )
    edge = SemanticEdge(
        "position:spot:BTCUSDT:1",
        "asset:BTC",
        SemanticRelationType.REPRESENTS,
    )

    with pytest.raises(ValueError, match="semantic graph identity"):
        SemanticGraphContract("", (entity, position), (edge,), ())
    with pytest.raises(ValueError, match="semantic graph entity ids must be unique"):
        SemanticGraphContract("graph:test", (entity, entity), (), ())
    with pytest.raises(
        ValueError, match="semantic graph blockers cannot contain blanks"
    ):
        SemanticGraphContract("graph:test", (entity, position), (edge,), (" ",))
    with pytest.raises(ValueError, match="semantic graph cannot promote or execute"):
        SemanticGraphContract(
            "graph:test",
            (entity, position),
            (edge,),
            (),
            promotion_status="LIVE_APPROVED",
        )


def test_position_semantic_graph_adds_review_edges_and_deduplicates_entities() -> None:
    shared_blocker = "MANUAL_CAPITAL_RELEASE_REVIEW_REQUIRED"
    report = PositionContextReport(
        records=(
            PositionContextRecord(
                asset="SOL",
                market=PositionMarket.SPOT,
                side=PositionSide.LONG,
                quantity=Decimal("2"),
                available_quantity=Decimal("2"),
                symbol="SOLUSDT",
                notional_usdt=Decimal("240"),
                capital_source_status=CapitalSourceStatus.REVIEWABLE_POSITION,
                blockers=("POSITION_IS_CONTEXT_NOT_THESIS", shared_blocker),
                evidence_refs=("spot_wallet",),
            ),
            PositionContextRecord(
                asset="SOL",
                market=PositionMarket.SPOT,
                side=PositionSide.LONG,
                quantity=Decimal("1"),
                available_quantity=Decimal("1"),
                symbol="SOLUSDT",
                notional_usdt=Decimal("120"),
                capital_source_status=CapitalSourceStatus.PROTECTED_REVIEW_REQUIRED,
                blockers=(
                    "POSITION_IS_CONTEXT_NOT_THESIS",
                    "PROTECTED_ASSET_REQUIRES_EXPLICIT_OVERRIDE",
                ),
                evidence_refs=("spot_wallet",),
            ),
        ),
        blockers=(shared_blocker,),
    )

    graph = build_position_semantic_graph(report)

    asset_entities = [
        entity
        for entity in graph.entities
        if entity.entity_type is SemanticEntityType.ASSET
    ]
    review_edges = [
        edge
        for edge in graph.edges
        if edge.relation_type is SemanticRelationType.REQUIRES_REVIEW
    ]

    assert len(asset_entities) == 1
    assert len(review_edges) == 2
    assert graph.blockers.count(shared_blocker) == 1


def test_position_semantic_graph_skips_review_edge_for_available_cash() -> None:
    report = PositionContextReport(
        records=(
            PositionContextRecord(
                asset="USDT",
                market=PositionMarket.SPOT,
                side=PositionSide.LONG,
                quantity=Decimal("100"),
                available_quantity=Decimal("100"),
                symbol="USDT",
                notional_usdt=Decimal("100"),
                capital_source_status=CapitalSourceStatus.AVAILABLE_CASH,
                blockers=("POSITION_IS_CONTEXT_NOT_THESIS",),
                evidence_refs=("spot_wallet",),
            ),
        ),
        blockers=(),
    )

    graph = build_position_semantic_graph(report)

    assert all(
        edge.relation_type is not SemanticRelationType.REQUIRES_REVIEW
        for edge in graph.edges
    )
