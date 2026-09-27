"""D0-D1 source, scope, ownership and fail-closed registry contracts."""

import json
from copy import deepcopy
from hashlib import sha256
from importlib import import_module
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from ai4binance.intelligence.inventory import TradingIntelligenceInventory
from ai4binance.intelligence.method_lineage import MethodLineage
from ai4binance.intelligence.method_registry import (
    REGISTRY_PATH,
    SCHEMA_ID,
    MethodReference,
    RuleDefinition,
    SourceBibliography,
    TradingMethodRegistry,
    current_method_registry,
    load_method_registry,
    restore_registry_snapshot,
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


@pytest.mark.parametrize(
    "mutation", ["orphan_rule", "orphan_method", "duplicate", "reverse"]
)
def test_registry_rejects_orphans_and_duplicate_interactions(mutation: str) -> None:
    payload = current_method_registry().model_dump(mode="json")
    if mutation == "orphan_rule":
        rule = deepcopy(payload["rules"][0])
        rule["rule_id"] = "test_only.orphan_rule"
        payload["rules"].append(rule)
    elif mutation == "orphan_method":
        method = deepcopy(payload["methods"][0])
        method["method_id"] = "test_only.orphan_method"
        payload["methods"].append(method)
    else:
        edge = deepcopy(payload["interactions"][0])
        if mutation == "reverse":
            edge["left"], edge["right"] = edge["right"], edge["left"]
            edge["relationship"] = "CONTEXT_ONLY"
        payload["interactions"].append(edge)
    with pytest.raises(ValueError, match=r"orphan|duplicate undirected"):
        TradingMethodRegistry.model_validate(payload)


@pytest.mark.parametrize(
    "rule_type",
    [
        "AI4BINANCE_IMPLEMENTATION_RULE",
        "SOURCE_DEFINITION",
        "SOURCE_RULE",
        "SOURCE_GUIDELINE",
        "INDUSTRY_CONVENTION",
        "EMPIRICAL_FINDING",
        "AI4BINANCE_CANONICAL_RULE",
        "AI4BINANCE_VALIDATION_RULE",
        "AI4BINANCE_RISK_RULE",
    ],
)
def test_rule_classification_is_explicit_without_granting_authority(
    rule_type: str,
) -> None:
    payload = current_method_registry().model_dump(mode="json")
    payload["rules"][0]["rule_type"] = rule_type
    registry = TradingMethodRegistry.model_validate(payload)
    assert registry.rules[0].rule_type == rule_type
    assert registry.authority_effect == "EVIDENCE_ONLY"
    assert not registry.execution_allowed
    assert registry.promotion_status == "RESEARCH_ONLY"


def bibliography_payload() -> dict[str, object]:
    """Test-only bibliographic metadata; not external source verification."""
    return {
        "title": "Test-only source",
        "organization": "Test fixture",
        "author": None,
        "source_family": "Test methodology",
        "primary_or_secondary": "SECONDARY",
        "publication_date": None,
        "source_version": None,
        "accessed_at": "2026-09-27T00:00:00Z",
        "licensing_notes": "Test fixture; no external content.",
        "conflict_notes": "No source comparison performed for this fixture.",
    }


def reference_payload() -> dict[str, object]:
    """Test-only interpretation for contract validation, not a market claim."""
    return {
        "definition": "Test-only deterministic method description.",
        "purpose": "Exercise reference validation.",
        "origin_or_school": "Test fixture",
        "standardization_status": "NOT_VERIFIED",
        "market_context": ["Test-only context"],
        "direction_semantics": "Advisory only",
        "timeframe_semantics": "Use the recorded source timeframe.",
        "known_failure_modes": ["Missing inputs"],
        "ambiguity_notes": "This fixture has no empirical evidence.",
    }


@pytest.mark.parametrize("mutation", ["naive_time", "source_kind", "blank_title"])
def test_invalid_bibliography_fails_closed(mutation: str) -> None:
    payload = bibliography_payload()
    if mutation == "naive_time":
        payload["accessed_at"] = "2026-09-27T00:00:00"
    elif mutation == "source_kind":
        payload["primary_or_secondary"] = "VERIFIED_AUTHORITY"
    else:
        payload["title"] = " "
    with pytest.raises(ValidationError):
        SourceBibliography.model_validate(payload)


@pytest.mark.parametrize(
    "field", ["standardization_status", "market_context", "known_failure_modes"]
)
def test_invalid_method_reference_fails_closed(field: str) -> None:
    payload = reference_payload()
    payload[field] = "UNIVERSAL_TRUTH" if field == "standardization_status" else []
    with pytest.raises(ValidationError):
        MethodReference.model_validate(payload)


def test_unknown_rule_classification_is_rejected() -> None:
    payload = current_method_registry().rules[0].model_dump(mode="json")
    payload["rule_type"] = "GUARANTEED_TRADING_AUTHORITY"
    with pytest.raises(ValidationError):
        RuleDefinition.model_validate(payload)


@pytest.mark.parametrize(
    "locator",
    [
        "javascript:test_only",
        "not a URL",
        "//example.test/reference",
        "https:///reference",
        "https://example.test/reference)injected(",
        "https://example.test/<injected>",
        "https://test_user:test_only_password@example.test/reference",
        "https://@example.test/reference",
        "https://example.test/reference\nnext",
        "https://example.test/reference%0Anext",
        "https://example.test:invalid/reference",
        "https://example.test:70000/reference",
        "https://example.test\\other/reference",
    ],
)
def test_external_source_rejects_unsafe_or_malformed_links(locator: str) -> None:
    payload = current_method_registry().model_dump(mode="json")
    source = next(
        row for row in payload["sources"] if row["source_type"] == "EXTERNAL_REFERENCE"
    )
    source["locator"] = locator
    with pytest.raises(ValueError, match="safe absolute HTTP"):
        TradingMethodRegistry.model_validate(payload)


@pytest.mark.parametrize("scheme", ["http", "https"])
def test_external_source_accepts_passive_documentation_links(scheme: str) -> None:
    payload = current_method_registry().model_dump(mode="json")
    source = next(
        row for row in payload["sources"] if row["source_type"] == "EXTERNAL_REFERENCE"
    )
    source["locator"] = (
        f"{scheme}://docs.example.test/methods/fibonacci?ratio=0.618#rules"
    )
    registry = TradingMethodRegistry.model_validate(payload)
    restored = next(
        row for row in registry.sources if row.source_id == source["source_id"]
    )
    assert restored.locator == source["locator"]
    assert restored.verification == "REFERENCE_ONLY"


def test_legacy_snapshot_restores_original_lineage_without_optional_metadata() -> None:
    # Reconstruct the pre-extension wire format before parsing the new models.
    raw = current_method_registry().model_dump(mode="json")
    for method in raw["methods"]:
        method.pop("reference")
        method.pop("rule_stages")
    for rule in raw["rules"]:
        rule.pop("semantics")
    for source in raw["sources"]:
        source.pop("bibliography")
    method = next(row for row in raw["methods"] if row["method_id"] == "fibonacci")
    rules = sorted(
        (row for row in raw["rules"] if row["rule_id"] in method["rule_ids"]),
        key=lambda row: row["rule_id"],
    )
    source_ids = set(method["source_ids"]).union(*(row["source_ids"] for row in rules))
    definition = {
        "method": method,
        "rules": rules,
        "sources": sorted(
            (row for row in raw["sources"] if row["source_id"] in source_ids),
            key=lambda row: row["source_id"],
        ),
    }
    legacy = MethodLineage(
        method["method_id"],
        method["version"],
        method["rule_set_version"],
        raw["version"],
        sha256(
            json.dumps(definition, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        tuple(f"{row['rule_id']}@{row['version']}" for row in rules),
        tuple(sorted(source_ids)),
    )
    snapshot = {
        "definition": raw,
        "sha256": sha256(
            json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }
    restored = restore_registry_snapshot(snapshot)
    restored.validate_lineage(legacy)
    assert restored.method("fibonacci").reference is None
    assert all(source.bibliography is None for source in restored.sources)
    # Both newly supplied metadata objects become part of the exact definition.
    method["reference"] = reference_payload()
    referenced_source = next(
        row for row in raw["sources"] if row["source_id"] in source_ids
    )
    referenced_source["bibliography"] = bibliography_payload()
    changed = TradingMethodRegistry.model_validate(raw)
    assert changed.method("fibonacci").reference is not None
    with pytest.raises(ValueError, match="registered definition"):
        changed.validate_lineage(legacy)


@pytest.mark.parametrize(
    "mutation", ["missing", "self", "cycle", "conflict", "duplicate", "foreign_stage"]
)
def test_rule_dependency_graph_rejects_invalid_links(mutation: str) -> None:
    raw = current_method_registry().model_dump(mode="json")
    first, second = raw["rules"][:2]
    semantics = {
        "invalidation_effect": "Test-only invalidation",
        "prerequisite_rules": [second["rule_id"]],
    }
    first["semantics"] = semantics
    if mutation == "missing":
        semantics["prerequisite_rules"] = ["missing.rule"]
    elif mutation == "self":
        semantics["prerequisite_rules"] = [first["rule_id"]]
    elif mutation == "cycle":
        second["semantics"] = {
            "invalidation_effect": "Test-only",
            "prerequisite_rules": [first["rule_id"]],
        }
    elif mutation == "conflict":
        semantics["conflicting_rules"] = [second["rule_id"]]
    elif mutation == "duplicate":
        semantics["prerequisite_rules"] = [second["rule_id"], second["rule_id"]]
    else:
        method = raw["methods"][0]
        foreign = next(
            rule["rule_id"]
            for rule in raw["rules"]
            if rule["rule_id"] not in method["rule_ids"]
        )
        method["rule_stages"] = {"anchor": [foreign]}
    with pytest.raises(ValueError, match=r"reference|rule|prerequisite"):
        TradingMethodRegistry.model_validate(raw)


def test_reference_manual_projects_chapter_gaps_and_rule_stages() -> None:
    from ai4binance.intelligence.inventory import (
        reference_gaps,
        render_reference_manual,
    )

    raw = current_method_registry().model_dump(mode="json")
    method = raw["methods"][0]
    method["reference"] = reference_payload()
    method["reference"]["chapter"] = {
        "bullish_interpretation": "Test-only bullish context"
    }
    method["rule_stages"] = {"formation": method["rule_ids"]}
    registry = TradingMethodRegistry.model_validate(raw)
    gaps = reference_gaps(registry.methods[0])
    assert "bearish_interpretation" in gaps
    assert "bullish_interpretation" not in gaps
    assert "rule_stages" not in gaps
    manual = render_reference_manual(registry)
    assert "Bullish Interpretation: Test-only bullish context" in manual
    assert "Bearish Interpretation: NOT_VERIFIED" in manual
    assert "Formation: " + method["rule_ids"][0] in manual
    assert "LIVE_ORDER_BLOCKED" in manual


def test_reference_acceptance_projects_limits_without_claiming_master_completion() -> (
    None
):
    from ai4binance.intelligence.inventory import reference_acceptance_projection

    registry = current_method_registry()
    report = reference_acceptance_projection(registry)
    assert report["registry_sha256"] == registry.snapshot_payload()["sha256"]
    assert report["status"] == "PARTIALLY_VERIFIED"
    assert not report["execution_allowed"]
    methods = report["methods"]
    assert isinstance(methods, list)
    assert len(methods) == len(registry.methods)
    assert all(method.reference is not None for method in registry.methods)
    assert any(row["missing_reference_fields"] for row in methods)
    assert all(row["oos_status"] == "METHOD_LEVEL_OOS_NOT_VERIFIED" for row in methods)


def test_source_rules_remain_distinct_from_executable_implementation_rules() -> None:
    registry = current_method_registry()
    source_rules = [
        rule for rule in registry.rules if rule.rule_type.startswith("SOURCE_")
    ]
    assert {rule.rule_type for rule in source_rules} >= {
        "SOURCE_RULE",
        "SOURCE_GUIDELINE",
        "SOURCE_DEFINITION",
    }
    assert all(rule.implementation_ref is None for rule in source_rules)
    assert (
        registry.method("harmonic_patterns.ab_cd").implementation_status
        == "CATALOG_ONLY"
    )
    with pytest.raises(ValueError, match="catalog method"):
        registry.lineage("harmonic_patterns.ab_cd", "1.0.0", "1.0.0")
