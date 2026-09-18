"""Offline schema loading rejects malformed contracts and reports compatibility."""

import json
from pathlib import Path

import pytest

from ai4binance.schema_validation import (
    OfflineSchemaRegistry,
    SchemaValidationError,
    compare_object_schema_compatibility,
    validate_contract_schema_mappings,
)

SCHEMA_ID = "urn:ai4binance:schema:test:boundary:1.0.0"
DIALECT = "https://json-schema.org/draft/2020-12/schema"


def _schema(**changes: object) -> dict[str, object]:
    return {"$id": SCHEMA_ID, "$schema": DIALECT, "type": "object", **changes}


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        ("{", "invalid JSON"),
        ("[]", "root must be an object"),
        (json.dumps(_schema(**{"$id": ""})), "non-empty"),
        (
            json.dumps(_schema(**{"$id": "https://example.invalid/schema"})),
            "locally governed",
        ),
        (json.dumps(_schema(**{"$schema": "old"})), "Draft 2020-12"),
        (json.dumps(_schema(type="unknown")), "meta-schema"),
        (
            json.dumps(_schema(**{"$ref": "https://example.invalid/remote"})),
            "network schema reference",
        ),
    ],
)
def test_registry_rejects_malformed_schema_files(
    tmp_path: Path, contents: str, message: str
) -> None:
    (tmp_path / "bad.schema.json").write_text(contents, encoding="utf-8")
    with pytest.raises(SchemaValidationError, match=message):
        OfflineSchemaRegistry.from_directory(tmp_path)


def test_registry_rejects_empty_duplicate_and_unknown_contracts(tmp_path: Path) -> None:
    with pytest.raises(SchemaValidationError, match="cannot be empty"):
        OfflineSchemaRegistry.from_directory(tmp_path)
    (tmp_path / "one.schema.json").write_text(json.dumps(_schema()), encoding="utf-8")
    registry = OfflineSchemaRegistry.from_directory(tmp_path)
    assert registry.affected_schema_ids(("unrelated.txt",)) == ()
    with pytest.raises(SchemaValidationError, match="unregistered schema:"):
        registry.validate("urn:unknown", {})
    with pytest.raises(SchemaValidationError, match="contract mappings reference"):
        validate_contract_schema_mappings(registry)
    (tmp_path / "two.schema.json").write_text(json.dumps(_schema()), encoding="utf-8")
    with pytest.raises(SchemaValidationError, match="duplicate schema"):
        OfflineSchemaRegistry.from_directory(tmp_path)


def test_registry_strict_datetime_rejects_calendar_errors(tmp_path: Path) -> None:
    (tmp_path / "date.schema.json").write_text(
        json.dumps(_schema(type="string", format="date-time")), encoding="utf-8"
    )
    registry = OfflineSchemaRegistry.from_directory(tmp_path)
    with pytest.raises(SchemaValidationError, match="instance validation failed"):
        registry.validate(SCHEMA_ID, "2026-02-30T00:00:00Z")
    registry.validate(SCHEMA_ID, "2026-02-28T00:00:00Z")
    assert registry.schemas[0].schema_id == SCHEMA_ID


@pytest.mark.parametrize(
    ("previous", "current", "expected"),
    [
        (
            {"required": ["a"], "properties": {"a": {"type": "string"}}},
            {},
            ("required field removed: a", "field removed: a"),
        ),
        ({}, {"required": ["a"]}, ("required field added: a",)),
        (
            {"properties": {"a": {"type": "string"}}},
            {"properties": {"a": {"type": "number"}}},
            ("field type changed: a",),
        ),
        (
            {"additionalProperties": False},
            {"properties": {"a": {}}},
            ("optional fields reject older closed consumers",),
        ),
    ],
)
def test_schema_compatibility_reports_exact_breaking_changes(
    previous: dict[str, object], current: dict[str, object], expected: tuple[str, ...]
) -> None:
    result = compare_object_schema_compatibility(previous, current)
    assert result.breaking_changes == expected
    assert result.backward_read_compatible is False
    assert result.forward_read_compatible is (
        expected == ("optional fields reject older closed consumers",)
    )


def test_schema_compatibility_ignores_non_schema_property_values() -> None:
    result = compare_object_schema_compatibility(
        {"properties": [], "required": "invalid"},
        {"properties": {"ignored": False}, "required": None},
    )
    assert result.breaking_changes == ()
    assert result.backward_read_compatible is True
    assert result.forward_read_compatible is True
