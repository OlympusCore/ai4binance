"""Deterministic enforcement for technology-language ownership boundaries."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import yaml

from ai4binance.schema_validation import OfflineSchemaRegistry, SchemaValidationError

POLICY_PATH = Path("config/governance/technology_language_ownership.yaml")
STANDARD_PATH = Path("docs/standards/standard_technology_language_ownership.md")
SCHEMA_PATH = Path("schemas/governance/technology_language_ownership.schema.json")
SCHEMA_ID = (
    "https://ai4binance.local/schemas/governance/"
    "technology_language_ownership.schema.json"
)


@dataclass(frozen=True, slots=True)
class LanguageRule:
    """One language's bounded ownership and repository-placement rule."""

    language: str
    role: str
    suffixes: tuple[str, ...]
    enforce_placement: bool
    allowed_paths: tuple[str, ...]
    allowed_capabilities: tuple[str, ...]
    forbidden_capabilities: tuple[str, ...]
    forbidden_content_patterns: tuple[str, ...]
    evidence_required_if_present: bool
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TechnologyLanguagePolicy:
    """Schema-validated projection of the human normative standard."""

    policy_id: str
    version: str
    human_authority_ref: str
    authority_scope: str
    production_roots: tuple[str, ...]
    research_only_roots: tuple[str, ...]
    forbidden_production_references: tuple[str, ...]
    languages: tuple[LanguageRule, ...]
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if self.human_authority_ref != STANDARD_PATH.as_posix():
            raise ValueError("technology policy human authority reference is invalid")
        if self.authority_scope != "technology_language_ownership":
            raise ValueError("technology policy authority scope is invalid")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("technology policy cannot widen trading authority")
        suffix_owners: dict[str, str] = {}
        for rule in self.languages:
            for suffix in rule.suffixes:
                previous = suffix_owners.setdefault(suffix.lower(), rule.language)
                if previous != rule.language:
                    raise ValueError(
                        f"technology suffix has duplicate owners: {suffix}"
                    )
            for pattern in rule.forbidden_content_patterns:
                try:
                    re.compile(pattern)
                except re.error as exc:
                    raise ValueError(
                        f"invalid forbidden content pattern for {rule.language}"
                    ) from exc


@dataclass(frozen=True, slots=True)
class TechnologyLanguageViolation:
    """One fail-closed repository technology-boundary violation."""

    code: str
    path: str
    detail: str


def load_technology_language_policy(
    repository_root: Path,
) -> TechnologyLanguagePolicy:
    """Load and schema-validate the policy projection without network access."""

    root = repository_root.resolve()
    policy_path = root / POLICY_PATH
    try:
        payload = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
        OfflineSchemaRegistry.from_directory(root / "schemas").validate(
            SCHEMA_ID,
            payload,
        )
    except (OSError, UnicodeError, yaml.YAMLError, SchemaValidationError) as exc:
        raise ValueError("technology language policy validation failed") from exc
    policy_mapping = _mapping(payload, "technology language policy")
    authority = _mapping(policy_mapping["authority"], "authority")
    safety = _mapping(policy_mapping["safety"], "safety")
    interoperability = _mapping(
        policy_mapping["interoperability"],
        "interoperability",
    )
    language_payload = _mapping(policy_mapping["languages"], "languages")
    language_rules: list[LanguageRule] = []
    for language, raw_rule in language_payload.items():
        rule = _mapping(raw_rule, f"language rule {language}")
        adoption_gate = _mapping(rule["adoption_gate"], "adoption_gate")
        language_rules.append(
            LanguageRule(
                language=language,
                role=_string(rule["role"], "role"),
                suffixes=_strings(rule["suffixes"], "suffixes"),
                enforce_placement=_boolean(
                    rule["enforce_placement"],
                    "enforce_placement",
                ),
                allowed_paths=_safe_paths(rule["allowed_paths"], "allowed_paths"),
                allowed_capabilities=_strings(
                    rule["allowed_capabilities"],
                    "allowed_capabilities",
                ),
                forbidden_capabilities=_strings(
                    rule["forbidden_capabilities"],
                    "forbidden_capabilities",
                ),
                forbidden_content_patterns=_strings(
                    rule["forbidden_content_patterns"],
                    "forbidden_content_patterns",
                ),
                evidence_required_if_present=_boolean(
                    adoption_gate["evidence_required_if_present"],
                    "evidence_required_if_present",
                ),
                evidence_refs=_safe_paths(
                    adoption_gate["evidence_refs"],
                    "evidence_refs",
                ),
            )
        )
    return TechnologyLanguagePolicy(
        policy_id=_string(policy_mapping["policy_id"], "policy_id"),
        version=_string(policy_mapping["version"], "version"),
        human_authority_ref=_string(
            authority["human_authority_ref"],
            "human_authority_ref",
        ),
        authority_scope=_string(authority["authority_scope"], "authority_scope"),
        production_roots=_safe_paths(
            interoperability["production_roots"],
            "production_roots",
        ),
        research_only_roots=_safe_paths(
            interoperability["research_only_roots"],
            "research_only_roots",
        ),
        forbidden_production_references=_strings(
            interoperability["forbidden_production_references"],
            "forbidden_production_references",
        ),
        languages=tuple(language_rules),
        execution_allowed=_boolean(safety["execution_allowed"], "execution_allowed"),
        promotion_status=_string(safety["promotion_status"], "promotion_status"),
        live_eligibility_status=_string(
            safety["live_eligibility_status"],
            "live_eligibility_status",
        ),
    )


def evaluate_technology_language_policy(
    repository_root: Path,
    policy: TechnologyLanguagePolicy,
    repository_paths: Iterable[str],
) -> tuple[TechnologyLanguageViolation, ...]:
    """Evaluate tracked repository paths against the policy projection."""

    root = repository_root.resolve()
    paths = tuple(
        sorted(
            {
                (
                    path.replace("\\", "/")[2:]
                    if path.replace("\\", "/").startswith("./")
                    else path.replace("\\", "/")
                )
                for path in repository_paths
                if path.strip()
            }
        )
    )
    violations: list[TechnologyLanguageViolation] = []
    present_languages: set[str] = set()
    for relative in paths:
        if _excluded_path(relative):
            continue
        rule = _rule_for_path(policy.languages, relative)
        if rule is None:
            continue
        present_languages.add(rule.language)
        if rule.enforce_placement and not any(
            _path_matches_allowed(relative, allowed) for allowed in rule.allowed_paths
        ):
            violations.append(
                TechnologyLanguageViolation(
                    code="LANGUAGE_PLACEMENT_VIOLATION",
                    path=relative,
                    detail=(
                        f"{rule.language} source is outside its allowed repository "
                        "boundary."
                    ),
                )
            )
        source = _read_bounded_text(root, relative)
        if source is None:
            violations.append(
                TechnologyLanguageViolation(
                    code="TECHNOLOGY_SOURCE_UNREADABLE",
                    path=relative,
                    detail="Technology-boundary source could not be read safely.",
                )
            )
            continue
        for pattern in rule.forbidden_content_patterns:
            if re.search(pattern, source):
                violations.append(
                    TechnologyLanguageViolation(
                        code="FORBIDDEN_CAPABILITY_OWNERSHIP",
                        path=relative,
                        detail=(
                            f"{rule.language} source declares a capability forbidden "
                            "by the canonical technology standard."
                        ),
                    )
                )
                break
        if any(
            _path_matches_allowed(relative, production_root)
            for production_root in policy.production_roots
        ):
            normalized_source = source.replace("\\", "/")
            for forbidden_reference in policy.forbidden_production_references:
                if forbidden_reference in normalized_source:
                    violations.append(
                        TechnologyLanguageViolation(
                            code="RESEARCH_TO_PRODUCTION_DEPENDENCY",
                            path=relative,
                            detail=(
                                "Production source references a research-only "
                                "technology boundary."
                            ),
                        )
                    )
                    break
    for rule in policy.languages:
        if (
            rule.language not in present_languages
            or not rule.evidence_required_if_present
        ):
            continue
        if not rule.evidence_refs:
            violations.append(
                TechnologyLanguageViolation(
                    code="ADOPTION_EVIDENCE_MISSING",
                    path=POLICY_PATH.as_posix(),
                    detail=(
                        f"{rule.language} is present without required adoption "
                        "evidence references."
                    ),
                )
            )
            continue
        for evidence_ref in rule.evidence_refs:
            if not (root / evidence_ref).is_file():
                violations.append(
                    TechnologyLanguageViolation(
                        code="ADOPTION_EVIDENCE_UNAVAILABLE",
                        path=evidence_ref,
                        detail=(
                            f"{rule.language} adoption evidence reference is missing."
                        ),
                    )
                )
    return tuple(violations)


def _rule_for_path(
    rules: tuple[LanguageRule, ...],
    relative: str,
) -> LanguageRule | None:
    matches = [
        (len(suffix), rule)
        for rule in rules
        for suffix in rule.suffixes
        if relative.lower().endswith(suffix.lower())
    ]
    return max(matches, key=lambda item: item[0])[1] if matches else None


def _path_matches_allowed(relative: str, allowed: str) -> bool:
    normalized = allowed.rstrip("/")
    return relative == normalized or relative.startswith(f"{normalized}/")


def _excluded_path(relative: str) -> bool:
    return relative.startswith(
        (".git/", ".venv/", "archive/", "runtime/", "node_modules/")
    )


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


def _string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value


def _boolean(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be boolean")
    return value


def _strings(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise ValueError(f"{name} must be a string array")
    return tuple(cast(list[str], value))


def _safe_paths(value: object, name: str) -> tuple[str, ...]:
    paths = _strings(value, name)
    if any(
        Path(path).is_absolute()
        or "\\" in path
        or ".." in Path(path.replace("/", "\\")).parts
        for path in paths
    ):
        raise ValueError(f"{name} must contain repository-relative POSIX paths")
    return paths
