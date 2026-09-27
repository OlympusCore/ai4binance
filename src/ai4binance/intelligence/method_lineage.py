"""Immutable, serializable method provenance without trading authority."""

import re
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MethodLineage:
    """The exact rule definition used at production time, never a backfill."""

    method_id: str
    method_version: str
    rule_set_version: str
    registry_version: str
    definition_sha256: str
    rule_refs: tuple[str, ...]
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        for value in (
            self.method_id,
            self.method_version,
            self.rule_set_version,
            self.registry_version,
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError("method lineage identity must be nonblank")
        if not re.fullmatch(r"[0-9a-f]{64}", self.definition_sha256):
            raise ValueError("method lineage requires a definition SHA-256")
        for references in (self.rule_refs, self.source_refs):
            if (
                not isinstance(references, tuple)
                or not references
                or any(
                    not isinstance(item, str) or not item.strip() for item in references
                )
                or len(set(references)) != len(references)
            ):
                raise ValueError(
                    "method lineage references must be unique and nonblank"
                )

    def to_payload(self) -> dict[str, object]:
        return {
            "method_id": self.method_id,
            "method_version": self.method_version,
            "rule_set_version": self.rule_set_version,
            "registry_version": self.registry_version,
            "definition_sha256": self.definition_sha256,
            "rule_refs": self.rule_refs,
            "source_refs": self.source_refs,
        }

    @classmethod
    def from_payload(cls, payload: object) -> MethodLineage:
        """Read recorded provenance without consulting today's registry."""
        fields = (
            "method_id",
            "method_version",
            "rule_set_version",
            "registry_version",
            "definition_sha256",
            "rule_refs",
            "source_refs",
        )
        if not isinstance(payload, Mapping) or set(payload) != set(fields):
            raise ValueError("method lineage payload has missing or unknown fields")
        text = tuple(payload[name] for name in fields[:5])
        if any(not isinstance(value, str) for value in text):
            raise ValueError("method lineage text fields must be strings")
        refs: list[tuple[str, ...]] = []
        for name in fields[5:]:
            values = payload[name]
            if not isinstance(values, (tuple, list)) or any(
                not isinstance(value, str) for value in values
            ):
                raise ValueError("method lineage references must be string arrays")
            refs.append(tuple(values))
        return cls(*text, *refs)
