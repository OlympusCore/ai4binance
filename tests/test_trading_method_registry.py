"""D0-D1 source, scope, ownership and fail-closed registry contracts."""

import json
from copy import deepcopy
from importlib import import_module
from pathlib import Path

import pytest
import yaml

from ai4binance.intelligence.inventory import TradingIntelligenceInventory
from ai4binance.intelligence.method_registry import (
    REGISTRY_PATH,
    SCHEMA_ID,
    TradingMethodRegistry,
    current_method_registry,
    load_method_registry,
)
from ai4binance.schema_validation import SchemaValidationError

ROOT = Path(__file__).resolve().parents[1]


def test_schema_matches_the_typed_registry_contract() -> None:
    schema = json.loads(
        (
            ROOT / "schemas/registries/trading_intelligence_registry.schema.json"
        ).read_text()
    )
    assert schema.pop("$schema") == "https://json-schema.org/draft/2020-12/schema"
    assert schema.pop("$id") == SCHEMA_ID
    schema.pop("description")
    assert schema == TradingMethodRegistry.model_json_schema()


def test_complete_scope_and_legacy_inventory_share_one_registry() -> None:
    registry = current_method_registry()
    inventory = TradingIntelligenceInventory()
    inventory.validate()
    assert len(inventory.methods) == 11
    assert {row.family for row in registry.scope} >= {
        "market_structure",
        "pattern_lifecycle",
        "trend_geometry",
        "support_resistance",
        "chart_patterns",
        "formations",
        "fibonacci",
        "elliott_waves",
        "harmonic_patterns",
        "dow_theory",
        "wyckoff",
        "alternative_charting",
        "gap_analysis",
        "geometric_tools",
        "volume_order_flow",
        "multi_timeframe_analysis",
        "pattern_failure",
        "futures_derivatives",
        "sentiment_events",
        "method_interactions",
    }
    assert tuple(row.implemented for row in inventory.methods) == tuple(
        row.implemented for row in registry.coverage
    )
    assert all(
        method.governance_status == "RESEARCH_ONLY" for method in registry.methods
    )
    assert not registry.execution_allowed
    assert registry.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_declared_owners_tests_and_baseline_sources_exist() -> None:
    registry = current_method_registry()
    for method in registry.methods:
        if method.module and method.owner:
            owner: object = import_module(method.module)
            for part in method.owner.split("."):
                owner = getattr(owner, part)
    for rule in registry.rules:
        assert all((ROOT / path).is_file() for path in rule.test_refs)
    for source in registry.sources:
        if source.source_type == "REPOSITORY":
            assert (ROOT / source.locator).is_file()
            assert source.content_sha256
            assert source.revision == registry.baseline_commit
        else:
            assert source.verification == "REFERENCE_ONLY"
            assert source.content_sha256 is None


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate",
        "dangling_rule",
        "dangling_source",
        "alias",
        "owner",
        "coverage",
        "catalog_owner",
        "authority",
    ],
)
def test_invalid_registry_links_and_authority_fail_closed(mutation: str) -> None:
    payload = current_method_registry().model_dump(mode="json")
    if mutation == "duplicate":
        payload["methods"].append(deepcopy(payload["methods"][0]))
    elif mutation == "dangling_rule":
        payload["methods"][0]["rule_ids"] = ["unknown"]
    elif mutation == "dangling_source":
        payload["rules"][0]["source_ids"] = ["unknown"]
    elif mutation == "alias":
        payload["aliases"].append(deepcopy(payload["aliases"][0]))
    elif mutation == "owner":
        payload["methods"][0]["owner"] = None
    elif mutation == "coverage":
        payload["coverage"][0]["missing"] = payload["coverage"][0]["implemented"]
    elif mutation == "catalog_owner":
        row = next(
            row
            for row in payload["methods"]
            if row["implementation_status"] == "CATALOG_ONLY"
        )
        row["module"] = "ai4binance.intelligence.patterns"
    else:
        payload["execution_allowed"] = True
    with pytest.raises(
        ValueError, match=r"duplicate|dangling|alias|owner|implemented|literal_error"
    ):
        TradingMethodRegistry.model_validate(payload)


def test_registry_loading_does_not_depend_on_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert load_method_registry() == current_method_registry()


def test_yaml_duplicate_unknown_keys_and_missing_file_fail_closed(
    tmp_path: Path,
) -> None:
    path = tmp_path / "registry.yaml"
    original = (ROOT / REGISTRY_PATH).read_text(encoding="utf-8")
    path.write_text(original + "\nversion: 9.0.0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_method_registry(path)
    path.write_text(original + "\nunknown: true\n", encoding="utf-8")
    with pytest.raises(SchemaValidationError):
        load_method_registry(path)
    with pytest.raises(FileNotFoundError):
        load_method_registry(tmp_path / "missing.yaml")


def test_catalog_and_unknown_versions_cannot_produce_lineage() -> None:
    registry = current_method_registry()
    with pytest.raises(ValueError, match="catalog"):
        registry.lineage("harmonic_patterns.butterfly", "1.0.0", "1.0.0")
    for method_id, version, rule_version in (
        ("unknown", "1.0.0", "1.0.0"),
        ("fibonacci", "2.0.0", "1.0.0"),
        ("fibonacci", "1.0.0", "9.0.0"),
    ):
        with pytest.raises(ValueError, match="unknown"):
            registry.lineage(method_id, version, rule_version)


@pytest.mark.parametrize("mutation", ["coverage_owner", "scope_family"])
def test_coverage_and_scope_cannot_diverge_from_method_definitions(
    mutation: str,
) -> None:
    payload = current_method_registry().model_dump(mode="json")
    if mutation == "coverage_owner":
        payload["coverage"][0]["owner"] = "UnrelatedOwner"
    else:
        payload["scope"][0]["method_ids"] = ["fibonacci"]
    with pytest.raises(ValueError, match=r"coverage owner|another family"):
        TradingMethodRegistry.model_validate(payload)


def test_rule_change_invalidates_exact_lineage_without_rewriting_history() -> None:
    registry = current_method_registry()
    original = registry.lineage("fibonacci", "1.0.0", "1.0.0")
    payload = registry.model_dump(mode="json")
    rule = next(
        row for row in payload["rules"] if row["rule_id"] == "fibonacci.implementation"
    )
    rule["statement"] += " Changed rule."
    changed = TradingMethodRegistry.model_validate(payload)
    assert (
        changed.lineage("fibonacci", "1.0.0", "1.0.0").definition_sha256
        != original.definition_sha256
    )
    with pytest.raises(ValueError, match="registered definition"):
        changed.validate_lineage(original)
    registry.validate_lineage(original)


def test_schema_rejects_unbounded_executable_expressions(tmp_path: Path) -> None:
    payload = current_method_registry().model_dump(mode="json")
    payload["rules"][0]["machine_expression"] = "arbitrary expression"
    path = tmp_path / "registry.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    with pytest.raises(SchemaValidationError):
        load_method_registry(path)
