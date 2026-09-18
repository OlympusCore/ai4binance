"""Fail-closed external-authority applicability registry."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path
from typing import cast

import yaml

from ai4binance.schema_validation import OfflineSchemaRegistry, SchemaValidationError

DEFAULT_EXTERNAL_AUTHORITY_REGISTRY_PATH = Path(
    "config/governance/external_authorities.yaml"
)
_EXTERNAL_AUTHORITY_SCHEMA_ID = (
    "https://ai4binance.local/schemas/governance/"
    "external_authority_registry.schema.json"
)


class ExternalAuthorityKind(StrEnum):
    LAW = "LAW"
    STANDARD = "STANDARD"
    FRAMEWORK = "FRAMEWORK"
    PRINCIPLE = "PRINCIPLE"


class ExternalAuthorityEffect(StrEnum):
    MANDATORY = "MANDATORY"
    NORMATIVE = "NORMATIVE"
    GUIDANCE = "GUIDANCE"
    VALUES = "VALUES"


class ExternalApplicabilityStatus(StrEnum):
    ADOPTED_INTERNAL = "ADOPTED_INTERNAL"
    APPLICABLE = "APPLICABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class ExternalSourceStatus(StrEnum):
    """Lifecycle status of the cited source, never inferred from its title."""

    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    REPEALED = "REPEALED"
    DRAFT = "DRAFT"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class ExternalAuthorityEntry:
    authority_id: str
    title: str
    kind: ExternalAuthorityKind
    effect: ExternalAuthorityEffect
    jurisdiction: str
    source_reference: str
    source_status: ExternalSourceStatus
    effective_from: date | None
    last_verified_at: datetime
    review_due_on: date
    applicability_status: ExternalApplicabilityStatus
    applicability_basis: str
    control_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source_status, ExternalSourceStatus):
            raise ValueError("external authority source status is invalid")
        for name in (
            "authority_id",
            "title",
            "jurisdiction",
            "source_reference",
            "applicability_basis",
        ):
            value = str(getattr(self, name))
            if not value.strip():
                raise ValueError(f"external authority {name} is required")
        if self.last_verified_at.tzinfo is None:
            raise ValueError(
                "external authority last_verified_at must be timezone-aware"
            )
        if self.last_verified_at.utcoffset() != UTC.utcoffset(self.last_verified_at):
            raise ValueError("external authority last_verified_at must be UTC")
        if self.review_due_on < self.last_verified_at.date():
            raise ValueError("external authority review cannot already be overdue")
        if len(set(self.control_refs)) != len(self.control_refs) or any(
            not item.strip() for item in self.control_refs
        ):
            raise ValueError(
                "external authority control_refs must be unique and nonblank"
            )
        if (
            self.applicability_status
            in {
                ExternalApplicabilityStatus.APPLICABLE,
                ExternalApplicabilityStatus.ADOPTED_INTERNAL,
            }
            and not self.control_refs
        ):
            raise ValueError(
                "adopted or applicable external authority requires controls"
            )


@dataclass(frozen=True, slots=True)
class ExternalAuthorityRegistry:
    registry_id: str
    version: str
    entries: tuple[ExternalAuthorityEntry, ...]
    source_of_truth: bool = False
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.registry_id.strip() or not self.version.strip():
            raise ValueError("external authority registry identity is required")
        if not self.entries:
            raise ValueError("external authority registry cannot be empty")
        ids = tuple(item.authority_id for item in self.entries)
        if len(set(ids)) != len(ids):
            raise ValueError("external authority identifiers must be unique")
        if self.source_of_truth:
            raise ValueError("external authority registry is a derived projection")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError(
                "external authority registry cannot grant execution authority"
            )

    def applicability_blockers(self, *, as_of: date) -> tuple[str, ...]:
        blockers: list[str] = []
        for entry in self.entries:
            if entry.source_status is not ExternalSourceStatus.ACTIVE:
                blockers.append(
                    f"EXTERNAL_AUTHORITY_SOURCE_UNUSABLE:{entry.authority_id}:"
                    f"{entry.source_status.value}"
                )
            if entry.effective_from is not None and entry.effective_from > as_of:
                blockers.append(
                    f"EXTERNAL_AUTHORITY_NOT_YET_EFFECTIVE:{entry.authority_id}"
                )
            if entry.last_verified_at.date() > as_of:
                blockers.append(
                    f"EXTERNAL_AUTHORITY_VERIFICATION_FROM_FUTURE:{entry.authority_id}"
                )
            if entry.review_due_on < as_of:
                blockers.append(
                    f"EXTERNAL_AUTHORITY_REVIEW_OVERDUE:{entry.authority_id}"
                )
            if (
                entry.applicability_status
                is ExternalApplicabilityStatus.REVIEW_REQUIRED
            ):
                blockers.append(
                    f"EXTERNAL_AUTHORITY_REVIEW_REQUIRED:{entry.authority_id}"
                )
        return tuple(blockers)


def load_external_authority_registry(
    path: Path = DEFAULT_EXTERNAL_AUTHORITY_REGISTRY_PATH,
    *,
    schema_root: Path | None = None,
) -> ExternalAuthorityRegistry:
    """Load the derived registry with local schema resolution only."""
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ValueError(
            f"external authority registry cannot be loaded: {path}"
        ) from error
    if not isinstance(payload, Mapping):
        raise ValueError("external authority registry must be a mapping")
    selected_schema_root = schema_root or Path(__file__).parents[4] / "schemas"
    try:
        OfflineSchemaRegistry.from_directory(selected_schema_root).validate(
            _EXTERNAL_AUTHORITY_SCHEMA_ID, payload
        )
    except SchemaValidationError as error:
        raise ValueError(
            "external authority registry schema validation failed"
        ) from error
    typed = cast(Mapping[str, object], payload)
    return ExternalAuthorityRegistry(
        registry_id=_text(typed, "registry_id"),
        version=_text(typed, "version"),
        source_of_truth=_boolean(typed, "source_of_truth"),
        execution_allowed=_boolean(typed, "execution_allowed"),
        live_eligibility_status=_text(typed, "live_eligibility_status"),
        entries=tuple(_entry(item) for item in _list(typed, "entries")),
    )


def _entry(value: object) -> ExternalAuthorityEntry:
    payload = _mapping(value, "external authority entry")
    effective_from = payload.get("effective_from")
    return ExternalAuthorityEntry(
        authority_id=_text(payload, "authority_id"),
        title=_text(payload, "title"),
        kind=ExternalAuthorityKind(_text(payload, "kind")),
        effect=ExternalAuthorityEffect(_text(payload, "effect")),
        jurisdiction=_text(payload, "jurisdiction"),
        source_reference=_text(payload, "source_reference"),
        source_status=ExternalSourceStatus(_text(payload, "source_status")),
        effective_from=(
            None if effective_from is None else date.fromisoformat(str(effective_from))
        ),
        last_verified_at=datetime.fromisoformat(
            _text(payload, "last_verified_at").replace("Z", "+00:00")
        ),
        review_due_on=date.fromisoformat(_text(payload, "review_due_on")),
        applicability_status=ExternalApplicabilityStatus(
            _text(payload, "applicability_status")
        ),
        applicability_basis=_text(payload, "applicability_basis"),
        control_refs=tuple(str(item) for item in _list(payload, "control_refs")),
    )


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return cast(Mapping[str, object], value)


def _list(payload: Mapping[str, object], key: str) -> list[object]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"external authority {key} must be a list")
    return value


def _text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"external authority {key} is required")
    return value


def _boolean(payload: Mapping[str, object], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"external authority {key} must be boolean")
    return value


__all__ = (
    "DEFAULT_EXTERNAL_AUTHORITY_REGISTRY_PATH",
    "ExternalApplicabilityStatus",
    "ExternalAuthorityEffect",
    "ExternalAuthorityEntry",
    "ExternalAuthorityKind",
    "ExternalAuthorityRegistry",
    "ExternalSourceStatus",
    "load_external_authority_registry",
)
