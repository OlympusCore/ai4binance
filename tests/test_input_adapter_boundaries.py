"""Reject malformed external input while preserving canonical wire behavior."""

import json
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from ai4binance.core.errors import ExchangePayloadError
from ai4binance.external_intel.retrieval.source_config import load_open_web_policy
from ai4binance.github_radar.__main__ import _load_repository_evidence
from ai4binance.github_radar.engine import GitHubRadarEngine
from ai4binance.research_catalog import ResearchCatalog
from ai4binance.whale_fusion.social.normalizer import CanonicalSocialPostNormalizer
from ai4binance.wire_contracts import market_snapshot_from_wire, market_snapshot_to_wire
from tests.test_github_radar_discovery import FakeDiscoveryClient
from tests.test_schemas import build_snapshot
from tests.test_whale_fusion_social import SOURCE


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("created_at", 123, "timestamp string"),
        ("created_at", "2026-01-01T00:00:00", "timezone"),
        ("bid", 123, "decimal string"),
    ],
)
def test_snapshot_rejects_ambiguous_wire_values(
    field: str, value: object, message: str
) -> None:
    payload = market_snapshot_to_wire(build_snapshot())
    payload[field] = value
    with pytest.raises(ValueError, match=message):
        market_snapshot_from_wire(payload)


def test_snapshot_preserves_nested_precision_and_missing_quotes() -> None:
    snapshot = replace(
        build_snapshot(),
        bid=None,
        ask=None,
        spread=None,
        data_freshness={
            "samples": (Decimal("0.00000001"), {"at": datetime(2026, 1, 1, tzinfo=UTC)})
        },
    )
    payload = market_snapshot_to_wire(snapshot)
    assert payload["data_freshness"] == {
        "samples": ["0.00000001", {"at": "2026-01-01T00:00:00Z"}]
    }
    restored = market_snapshot_from_wire(payload)
    assert restored.bid is restored.ask is restored.spread is None
    assert restored.ohlcv_by_timeframe == snapshot.ohlcv_by_timeframe


@pytest.mark.parametrize(
    ("source", "field", "value", "message"),
    [
        (False, "sources", "invalid", "sequence"),
        (False, "sources", [123], "mapping"),
        (False, "network_mode", "OPEN", "allowlisted"),
        (False, "search_mode", "UNBOUNDED", "allowlisted"),
        (False, "llm_mode", "CLOUD", "LLM mode"),
        (False, "cloud_llm_allowed", 1, "boolean"),
        (True, "reliability", True, "numeric"),
        (True, "reliability", "0.8", "numeric"),
        (True, "max_items", True, "integer"),
        (True, "max_items", 1.5, "integer"),
        (True, "max_items", 0, "between 1 and 20"),
        (True, "max_items", 21, "between 1 and 20"),
        (True, "feed_url", "https://EXAMPLE.COM/feed", "canonical"),
        (True, "allowed_hosts", ["EXAMPLE.COM"], "normalized"),
        (True, "allowed_hosts", ["example.com/path"], "normalized"),
        (True, "unexpected", True, "keys mismatch"),
    ],
)
def test_open_web_policy_rejects_invalid_configuration(
    tmp_path: Path, source: bool, field: str, value: object, message: str
) -> None:
    payload = json.loads(
        Path("config/research/open_web_sources.json").read_text(encoding="utf-8")
    )
    target = payload["sources"][0] if source else payload
    target[field] = value
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_open_web_policy(path)


def test_open_web_policy_rejects_non_object_and_oversized_documents(
    tmp_path: Path,
) -> None:
    path = tmp_path / "policy.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="mapping"):
        load_open_web_policy(path)
    path.write_text(" " * 256_001, encoding="utf-8")
    with pytest.raises(ValueError, match="bounded size"):
        load_open_web_policy(path)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("post_id", " ", "post_id"),
        ("timestamp", True, "integer"),
        ("timestamp", "1000", "integer"),
        ("platform", 1, "platform must be text"),
        ("assets", [1], "contain strings"),
        ("source_confidence", True, "decimal"),
        ("source_confidence", [], "decimal"),
        ("source_confidence", "invalid", "decimal"),
        ("source_confidence", "NaN", "finite"),
        ("source_confidence", "Infinity", "finite"),
    ],
)
def test_social_normalizer_rejects_untrusted_field_types(
    field: str, value: object, message: str
) -> None:
    payload = {
        "post_id": "post-1",
        "platform": "X",
        "account_id": "project-founder",
        "timestamp": 1000,
        "text": "announcement",
        "event_type": "PROJECT_ANNOUNCEMENT",
        "stance": "SUPPORTIVE",
        "assets": ["HOT"],
        "source_confidence": "0.8",
    }
    payload[field] = value
    with pytest.raises(ExchangePayloadError, match=message):
        CanonicalSocialPostNormalizer().normalize(payload, provenance=SOURCE)


def test_radar_discovery_and_catalog_identity_are_connected() -> None:
    engine = GitHubRadarEngine.from_repository()
    discovered = engine.discover(
        FakeDiscoveryClient(),
        capability_ids=("R26-C01",),
        maximum_queries=1,
        repositories_per_query=1,
        documents_per_repository=2,
    )
    assert discovered
    evidence = _load_repository_evidence(
        Path("tests/fixtures/github_radar/repository_evidence.json")
    )
    result = engine.assess(evidence, observed_at=datetime(2026, 8, 9, tzinfo=UTC))
    assert result.catalog_entry.execution_allowed is False
    alternate = replace(result.catalog_entry, entry_id="another-research-unit")
    with pytest.raises(ValueError, match="identity must match"):
        replace(result, catalog_entry=alternate)
    with pytest.raises(ValueError, match="connection is incomplete"):
        replace(result, catalog=ResearchCatalog((alternate,)))
    with pytest.raises(ValueError, match="not in the ontology"):
        engine.assess(
            replace(evidence, capability_id="R26-C99"),
            observed_at=datetime(2026, 8, 9, tzinfo=UTC),
        )
