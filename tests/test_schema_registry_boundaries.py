"""Offline schema loading rejects malformed contracts and reports compatibility."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from ai4binance.schema_validation import (
    OfflineSchemaRegistry,
    SchemaValidationError,
    compare_object_schema_compatibility,
    validate_contract_schema_mappings,
    validate_local_definition,
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


def _local_definition_schema(tmp_path: Path) -> Path:
    """Create a visibly test-only contract with two independent definitions."""
    path = tmp_path / "test-only-local.schema.json"
    path.write_text(
        json.dumps(
            _schema(
                **{
                    "$id": f"urn:ai4binance:schema:test:{tmp_path.name}",
                    "$defs": {
                        "text": {"type": "string"},
                        "count": {"type": "integer"},
                    },
                }
            )
        ),
        encoding="utf-8",
    )
    return path


def test_exact_schema_reuses_meta_validation_but_checks_every_instance(
    tmp_path: Path,
) -> None:
    path = _local_definition_schema(tmp_path)
    with patch.object(
        Draft202012Validator,
        "check_schema",
        wraps=Draft202012Validator.check_schema,
    ) as check_schema:
        validate_local_definition(path, "text", "valid")
        validate_local_definition(path, "count", 1)
        with pytest.raises(SchemaValidationError, match="instance validation failed"):
            validate_local_definition(path, "text", 1)
        OfflineSchemaRegistry.from_directory(tmp_path)
    assert check_schema.call_count == 1


def test_local_definition_detects_same_size_and_timestamp_schema_change(
    tmp_path: Path,
) -> None:
    path = _local_definition_schema(tmp_path)
    validate_local_definition(path, "text", "valid")
    before = path.stat()
    original = path.read_text(encoding="utf-8")
    changed = original.replace('"type": "string"', '"type": "number"')
    assert len(original) == len(changed)
    path.write_text(changed, encoding="utf-8")
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    with pytest.raises(SchemaValidationError, match="instance validation failed"):
        validate_local_definition(path, "text", "valid")
    validate_local_definition(path, "text", 1)
    path.unlink()
    with pytest.raises(FileNotFoundError):
        validate_local_definition(path, "text", 1)


def test_local_definition_rejects_missing_and_changed_remote_definitions(
    tmp_path: Path,
) -> None:
    path = _local_definition_schema(tmp_path)
    validate_local_definition(path, "text", "valid")
    with pytest.raises(SchemaValidationError, match="unregistered schema definition"):
        validate_local_definition(path, "missing", "valid")
    contents = json.loads(path.read_text(encoding="utf-8"))
    contents["$defs"]["text"] = {"$ref": "https://example.invalid/remote"}
    path.write_text(json.dumps(contents), encoding="utf-8")
    with pytest.raises(SchemaValidationError, match="network schema reference"):
        validate_local_definition(path, "text", "valid")


def test_warm_schema_preparation_preserves_fresh_registry_contents(
    tmp_path: Path,
) -> None:
    path = _local_definition_schema(tmp_path)
    registry = OfflineSchemaRegistry.from_directory(tmp_path)
    schema = registry.schemas[0]
    assert isinstance(schema.contents, dict)
    schema.contents["type"] = "integer"
    fresh = OfflineSchemaRegistry.from_directory(tmp_path)
    fresh.validate(schema.schema_id, {})
    contents = json.loads(path.read_text(encoding="utf-8"))
    contents["type"] = "not-a-schema-type"
    path.write_text(json.dumps(contents), encoding="utf-8")
    with pytest.raises(SchemaValidationError, match="meta-schema validation failed"):
        OfflineSchemaRegistry.from_directory(tmp_path)
