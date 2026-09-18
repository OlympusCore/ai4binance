"""Offline validation for versioned AI4Binance JSON Schema contracts."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from jsonschema import (  # type: ignore[import-untyped]
    Draft202012Validator,
    FormatChecker,
    ValidationError,
)
from jsonschema.exceptions import SchemaError  # type: ignore[import-untyped]
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

SCHEMA_FILE_SUFFIX = ".schema.json"
LOCAL_SCHEMA_ID_PREFIXES = (
    "urn:ai4binance:schema:",
    "https://ai4binance.local/schemas/",
)
_RFC3339_DATETIME_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
STRICT_FORMAT_CHECKER = FormatChecker()


@STRICT_FORMAT_CHECKER.checks("date-time")  # type: ignore[untyped-decorator]
def _is_rfc3339_datetime(value: object) -> bool:
    """Enforce RFC 3339 timestamps even when optional format extras are absent."""

    if not isinstance(value, str):
        return True
    if not _RFC3339_DATETIME_PATTERN.fullmatch(value):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


class SchemaValidationError(ValueError):
    """Raised when a schema corpus or a contract instance is invalid."""


@dataclass(frozen=True, slots=True)
class RegisteredSchema:
    """A locally loaded schema with an immutable identity and source path."""

    schema_id: str
    path: Path
    contents: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ContractSchemaMapping:
    """Scoped authority mapping between a Python boundary contract and wire schema."""

    python_contract: str
    schema_id: str
    schema_family: str


@dataclass(frozen=True, slots=True)
class SchemaCompatibilityResult:
    """Directional compatibility result for two immutable schema versions."""

    backward_read_compatible: bool
    forward_read_compatible: bool
    breaking_changes: tuple[str, ...]


CONTRACT_SCHEMA_MAPPINGS = (
    ContractSchemaMapping(
        "ai4binance.schemas.MarketSnapshot",
        "urn:ai4binance:schema:snapshots:market-snapshot:1.0.0",
        "snapshots",
    ),
    ContractSchemaMapping(
        "ai4binance.governance.evidence_contracts.GovernedArtifactEvidence",
        "urn:ai4binance:schema:evidence:evidence-bundle:1.0.0",
        "evidence",
    ),
    ContractSchemaMapping(
        "ai4binance.governance.dge_models.GovernedDecision",
        "urn:ai4binance:schema:decisions:trade-decision:1.0.0",
        "decisions",
    ),
    ContractSchemaMapping(
        "ai4binance.governance.execution_envelope.ExecutionEnvelope",
        "urn:ai4binance:schema:execution:execution-envelope:1.0.0",
        "execution",
    ),
    ContractSchemaMapping(
        "ai4binance.governance.risk_assessment.RiskAssessmentV2Contract",
        "urn:ai4binance:schema:risk:risk-assessment:2.0.0",
        "risk",
    ),
)


class OfflineSchemaRegistry:
    """Load local Draft 2020-12 schemas without network reference resolution."""

    def __init__(self, schemas: tuple[RegisteredSchema, ...]) -> None:
        if not schemas:
            raise SchemaValidationError("schema registry cannot be empty")
        schema_ids = tuple(schema.schema_id for schema in schemas)
        if len(set(schema_ids)) != len(schema_ids):
            raise SchemaValidationError("duplicate schema $id values are not allowed")
        self._schemas = schemas
        self._by_id = {schema.schema_id: schema for schema in schemas}
        resources = (
            (schema.schema_id, Resource.from_contents(schema.contents, DRAFT202012))
            for schema in schemas
        )
        self._references = Registry().with_resources(resources)

    @classmethod
    def from_directory(cls, schema_root: Path) -> OfflineSchemaRegistry:
        """Load and meta-validate every schema in a local schema root."""

        schema_paths = sorted(schema_root.rglob(f"*{SCHEMA_FILE_SUFFIX}"))
        schemas: list[RegisteredSchema] = []
        for path in schema_paths:
            try:
                contents = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise SchemaValidationError(
                    f"invalid JSON schema file: {path}"
                ) from error
            if not isinstance(contents, dict):
                raise SchemaValidationError(f"schema root must be an object: {path}")
            schema_id = contents.get("$id")
            if not isinstance(schema_id, str) or not schema_id:
                raise SchemaValidationError(
                    f"schema must define a non-empty $id: {path}"
                )
            if not schema_id.startswith(LOCAL_SCHEMA_ID_PREFIXES):
                raise SchemaValidationError(
                    f"schema $id is not locally governed: {path}"
                )
            if contents.get("$schema") != Draft202012Validator.META_SCHEMA["$id"]:
                raise SchemaValidationError(f"schema must use Draft 2020-12: {path}")
            try:
                Draft202012Validator.check_schema(contents)
            except SchemaError as error:
                raise SchemaValidationError(
                    f"meta-schema validation failed: {path}"
                ) from error
            _reject_remote_references(contents, path)
            schemas.append(RegisteredSchema(schema_id, path, contents))
        return cls(tuple(schemas))

    @property
    def schemas(self) -> tuple[RegisteredSchema, ...]:
        """Return all registered schemas in deterministic path order."""

        return self._schemas

    def affected_schema_ids(self, changed_paths: Sequence[str]) -> tuple[str, ...]:
        """Return changed schemas and their local transitive dependents."""

        normalized = {path.replace("\\", "/") for path in changed_paths}
        direct = {
            schema.schema_id
            for schema in self._schemas
            if schema.path.as_posix().endswith(tuple(normalized))
            or schema.path.name in normalized
        }
        if not direct:
            return ()
        dependencies = {
            schema.schema_id: set(_local_references(schema.contents))
            for schema in self._schemas
        }
        affected = set(direct)
        changed = True
        while changed:
            changed = False
            for schema_id, references in dependencies.items():
                if schema_id not in affected and references & affected:
                    affected.add(schema_id)
                    changed = True
        return tuple(sorted(affected))

    def validate(self, schema_id: str, instance: object) -> None:
        """Strictly validate one instance using only local registered references."""

        schema = self._by_id.get(schema_id)
        if schema is None:
            raise SchemaValidationError(f"unregistered schema: {schema_id}")
        validator = Draft202012Validator(
            schema.contents,
            registry=self._references,
            format_checker=STRICT_FORMAT_CHECKER,
        )
        try:
            validator.validate(instance)
        except ValidationError as error:
            raise SchemaValidationError(
                f"instance validation failed for {schema_id}: {error.message}"
            ) from error


def _walk_references(value: object) -> Iterator[str]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key == "$ref" and isinstance(child, str):
                yield child
            yield from _walk_references(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_references(child)


def _reject_remote_references(contents: Mapping[str, object], path: Path) -> None:
    for reference in _walk_references(contents):
        if reference.startswith(("http://", "https://")):
            raise SchemaValidationError(
                f"network schema reference is forbidden: {path} -> {reference}"
            )


def _local_references(contents: Mapping[str, object]) -> Iterator[str]:
    for reference in _walk_references(contents):
        if reference.startswith("urn:ai4binance:schema:"):
            yield reference.split("#", maxsplit=1)[0]


def validate_contract_schema_mappings(registry: OfflineSchemaRegistry) -> None:
    """Reject a Python/wire mapping that points to a missing local schema."""

    registered_ids = {schema.schema_id for schema in registry.schemas}
    missing = sorted(
        mapping.schema_id
        for mapping in CONTRACT_SCHEMA_MAPPINGS
        if mapping.schema_id not in registered_ids
    )
    if missing:
        raise SchemaValidationError(
            "contract mappings reference unregistered schemas: " + ", ".join(missing)
        )


def compare_object_schema_compatibility(
    previous: Mapping[str, object], current: Mapping[str, object]
) -> SchemaCompatibilityResult:
    """Assess closed-object compatibility without claiming semantic equivalence."""

    previous_properties = _properties(previous)
    current_properties = _properties(current)
    previous_required = _required(previous)
    current_required = _required(current)
    breaking: list[str] = []
    for name in sorted(previous_required - current_required):
        breaking.append(f"required field removed: {name}")
    for name in sorted(current_required - previous_required):
        breaking.append(f"required field added: {name}")
    for name in sorted(set(previous_properties) - set(current_properties)):
        breaking.append(f"field removed: {name}")
    for name in sorted(set(previous_properties) & set(current_properties)):
        previous_type = previous_properties[name].get("type")
        current_type = current_properties[name].get("type")
        if previous_type != current_type:
            breaking.append(f"field type changed: {name}")
    closed_previous = previous.get("additionalProperties") is False
    optional_added = (
        set(current_properties) - set(previous_properties) - current_required
    )
    forward = not breaking
    backward = not breaking and not (closed_previous and optional_added)
    if closed_previous and optional_added:
        breaking.append("optional fields reject older closed consumers")
    return SchemaCompatibilityResult(backward, forward, tuple(breaking))


def _properties(schema: Mapping[str, object]) -> Mapping[str, Mapping[str, object]]:
    value = schema.get("properties", {})
    if not isinstance(value, Mapping):
        return {}
    return {
        str(name): child for name, child in value.items() if isinstance(child, Mapping)
    }


def _required(schema: Mapping[str, object]) -> set[str]:
    value = schema.get("required", ())
    if not isinstance(value, Iterable) or isinstance(value, str):
        return set()
    return {item for item in value if isinstance(item, str)}
