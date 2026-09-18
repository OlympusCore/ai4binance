"""Deterministic terminology-projection validation and bounded scanning."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import yaml

from ai4binance.schema_validation import OfflineSchemaRegistry, SchemaValidationError

POLICY_PATH = Path("config/governance/canonical_terminology_registry.yaml")
STANDARD_PATH = Path("docs/standards/standard_terminology_governance.md")
SCHEMA_PATH = Path("schemas/governance/canonical_terminology_registry.schema.json")
SCHEMA_ID = (
    "https://ai4binance.local/schemas/governance/"
    "canonical_terminology_registry.schema.json"
)


@dataclass(frozen=True, slots=True)
class TerminologyTerm:
    """One non-authoritative canonical terminology projection entry."""

    term_id: str
    canonical_term: str
    domain: str
    allowed_aliases: tuple[str, ...]
    deprecated_aliases: tuple[str, ...]
    prohibited_terms: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TerminologyPolicy:
    """Schema-validated terminology enforcement projection."""

    policy_id: str
    version: str
    standard_id: str
    standard_path: str
    standard_version: str
    authority_scope: str
    scan_roots: tuple[str, ...]
    excluded_paths: tuple[str, ...]
    terms: tuple[TerminologyTerm, ...]

    def __post_init__(self) -> None:
        if self.standard_path != STANDARD_PATH.as_posix():
            raise ValueError("terminology policy standard path is invalid")
        if self.standard_id != "AI4B-GOV-STD-TERM-001":
            raise ValueError("terminology policy standard identifier is invalid")
        if self.authority_scope != "terminology_governance":
            raise ValueError("terminology policy authority scope is invalid")
        _validate_term_uniqueness(self.terms)


@dataclass(frozen=True, slots=True)
class TerminologyViolation:
    """One deterministic terminology-policy result."""

    code: str
    path: str
    detail: str
    blocker: bool


def load_terminology_policy(repository_root: Path) -> TerminologyPolicy:
    """Load the terminology projection without assigning it normative authority."""

    root = repository_root.resolve()
    try:
        payload = yaml.safe_load((root / POLICY_PATH).read_text(encoding="utf-8"))
        OfflineSchemaRegistry.from_directory(root / "schemas").validate(
            SCHEMA_ID,
            payload,
        )
    except (OSError, UnicodeError, yaml.YAMLError, SchemaValidationError) as exc:
        raise ValueError("terminology policy validation failed") from exc
    mapping = _mapping(payload, "terminology policy")
    authority = _mapping(mapping["authority"], "authority")
    enforcement = _mapping(mapping["enforcement"], "enforcement")
    terms = tuple(_term(item) for item in _items(mapping["terms"], "terms"))
    return TerminologyPolicy(
        policy_id=_string(mapping["registry_id"], "registry_id"),
        version=_string(mapping["version"], "version"),
        standard_id=_string(authority["standard_id"], "standard_id"),
        standard_path=_safe_path(authority["standard_path"], "standard_path"),
        standard_version=_string(authority["standard_version"], "standard_version"),
        authority_scope=_string(authority["authority_scope"], "authority_scope"),
        scan_roots=_safe_paths(enforcement["scan_roots"], "scan_roots"),
        excluded_paths=_safe_paths(
            enforcement["excluded_paths"],
            "excluded_paths",
        ),
        terms=terms,
    )


def evaluate_terminology_policy(
    repository_root: Path,
    policy: TerminologyPolicy,
    repository_paths: Iterable[str],
) -> tuple[TerminologyViolation, ...]:
    """Evaluate only registered lexical constraints; never infer prose semantics."""

    root = repository_root.resolve()
    violations = list(_projection_integrity_violations(root, policy))
    prohibited = _term_owners(policy.terms, "prohibited_terms")
    deprecated = _term_owners(policy.terms, "deprecated_aliases")
    for relative in _normalized_paths(repository_paths):
        if relative in policy.excluded_paths or not _is_scanned_path(
            relative,
            policy.scan_roots,
        ):
            continue
        text = _read_bounded_text(root, relative)
        if text is None:
            continue
        for term, owners in prohibited.items():
            if _contains_term(text, term):
                violations.append(
                    TerminologyViolation(
                        code="TERMINOLOGY_PROHIBITED_TERM",
                        path=relative,
                        detail=(
                            f"Prohibited terminology {term!r} is reserved against "
                            f"{', '.join(owners)}."
                        ),
                        blocker=True,
                    )
                )
        for alias, owners in deprecated.items():
            if _contains_term(text, alias):
                violations.append(
                    TerminologyViolation(
                        code="TERMINOLOGY_DEPRECATED_ALIAS",
                        path=relative,
                        detail=(
                            f"Deprecated terminology {alias!r} maps to "
                            f"{', '.join(owners)} and requires migration review."
                        ),
                        blocker=False,
                    )
                )
    return tuple(violations)


def _projection_integrity_violations(
    root: Path,
    policy: TerminologyPolicy,
) -> Iterable[TerminologyViolation]:
    standard = root / STANDARD_PATH
    if not standard.is_file():
        yield TerminologyViolation(
            "STANDARD_MISSING",
            STANDARD_PATH.as_posix(),
            "Terminology normative standard is missing.",
            True,
        )
        return
    metadata = _frontmatter(standard)
    expected = {
        "document_id": policy.standard_id,
        "version": policy.standard_version,
        "canonical_path": policy.standard_path,
        "authority_scope": policy.authority_scope,
    }
    for field, value in expected.items():
        if metadata.get(field) != value:
            yield TerminologyViolation(
                "TERMINOLOGY_PROJECTION_DRIFT",
                POLICY_PATH.as_posix(),
                f"Terminology standard {field} does not match its projection.",
                True,
            )


def _validate_term_uniqueness(terms: tuple[TerminologyTerm, ...]) -> None:
    seen_ids: set[str] = set()
    canonical_by_scope: set[tuple[str, str]] = set()
    aliases: dict[str, str] = {}
    for term in terms:
        if term.term_id in seen_ids:
            raise ValueError(f"duplicate terminology term identifier: {term.term_id}")
        seen_ids.add(term.term_id)
        scope_key = (term.domain.casefold(), term.canonical_term.casefold())
        if scope_key in canonical_by_scope:
            raise ValueError(
                "duplicate canonical terminology term in semantic scope: "
                f"{term.canonical_term}"
            )
        canonical_by_scope.add(scope_key)
        for alias in (*term.allowed_aliases, *term.deprecated_aliases):
            normalized = alias.casefold()
            owner = aliases.setdefault(normalized, term.term_id)
            if owner != term.term_id:
                raise ValueError(f"terminology alias collision: {alias}")
        overlap = set(term.deprecated_aliases) & set(term.prohibited_terms)
        if overlap:
            raise ValueError("deprecated terminology must not also be prohibited")


def _term_owners(
    terms: tuple[TerminologyTerm, ...],
    attribute: str,
) -> dict[str, tuple[str, ...]]:
    owners: dict[str, list[str]] = {}
    for term in terms:
        for value in cast(tuple[str, ...], getattr(term, attribute)):
            owners.setdefault(value, []).append(term.term_id)
    return {value: tuple(term_ids) for value, term_ids in owners.items()}


def _term(value: object) -> TerminologyTerm:
    mapping = _mapping(value, "terminology term")
    return TerminologyTerm(
        term_id=_string(mapping["term_id"], "term_id"),
        canonical_term=_string(mapping["canonical_term"], "canonical_term"),
        domain=_string(mapping["domain"], "domain"),
        allowed_aliases=_strings(mapping["allowed_aliases"], "allowed_aliases"),
        deprecated_aliases=_strings(
            mapping["deprecated_aliases"],
            "deprecated_aliases",
        ),
        prohibited_terms=_strings(
            mapping["prohibited_terms"],
            "prohibited_terms",
        ),
    )


def _frontmatter(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    value = yaml.safe_load(text.split("---", maxsplit=2)[1])
    return _mapping(value, "standard metadata")


def _normalized_paths(paths: Iterable[str]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                path.replace("\\", "/").removeprefix("./")
                for path in paths
                if path.strip()
            }
        )
    )


def _is_scanned_path(relative: str, roots: tuple[str, ...]) -> bool:
    return any(relative.startswith(root.rstrip("/") + "/") for root in roots)


def _contains_term(text: str, term: str) -> bool:
    pattern = rf"(?<![A-Za-z0-9_]){re.escape(term)}(?![A-Za-z0-9_])"
    return re.search(pattern, text, re.I) is not None


def _read_bounded_text(root: Path, relative: str) -> str | None:
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
        if not path.is_file() or path.stat().st_size > 2_000_000:
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError, ValueError):
        return None


def _mapping(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return {str(key): child for key, child in value.items()}


def _items(value: object, name: str) -> tuple[object, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be an array")
    return tuple(value)


def _string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value


def _strings(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ValueError(f"{name} must be a string array")
    return tuple(cast(list[str], value))


def _safe_paths(value: object, name: str) -> tuple[str, ...]:
    return tuple(_safe_path(item, name) for item in _strings(value, name))


def _safe_path(value: object, name: str) -> str:
    path = _string(value, name)
    if Path(path).is_absolute() or "\\" in path or ".." in Path(path).parts:
        raise ValueError(f"{name} must be a repository-relative POSIX path")
    return path
