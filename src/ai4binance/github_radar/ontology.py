"""Bounded YAML loader for the canonical GitHub Radar ontology."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

import yaml

from ai4binance.agents.catalog import build_default_registry
from ai4binance.enterprise.agent_stack import modern_agent_stack_requirements
from ai4binance.github_radar.models import (
    AtomicCapability,
    ResearchDomain,
    ResearchOntology,
    VerificationProfile,
)

MAX_ONTOLOGY_BYTES = 512_000


def default_ontology_path(repository_root: Path | None = None) -> Path:
    root = (repository_root or Path.cwd()).resolve()
    return root / "config" / "research" / "github_research_ontology.yaml"


def load_default_ontology(repository_root: Path | None = None) -> ResearchOntology:
    """Load and validate the repository's canonical ontology."""
    return load_ontology(default_ontology_path(repository_root))


def load_ontology(path: Path) -> ResearchOntology:
    """Load bounded YAML and reject unknown agent/layer references."""
    resolved = path.resolve()
    if resolved.stat().st_size > MAX_ONTOLOGY_BYTES:
        raise ValueError("GitHub Radar ontology exceeds the bounded size")
    raw = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("GitHub Radar ontology must be a mapping")
    payload = cast(Mapping[str, object], raw)
    domains = tuple(
        ResearchDomain(str(item["id"]), str(item["title"]))
        for item in _mapping_items(payload, "domains", maximum=31)
    )
    profiles = tuple(
        VerificationProfile(str(item["id"]), str(item["title"]))
        for item in _mapping_items(payload, "verification_profiles", maximum=12)
    )
    capabilities = tuple(
        _capability(item)
        for item in _mapping_items(payload, "capabilities", maximum=500)
    )
    authority = _mapping(payload.get("authority"), "authority")
    ontology = ResearchOntology(
        ontology_id=str(payload.get("ontology_id", "")),
        schema_version=str(payload.get("schema_version", "")),
        domains=domains,
        verification_profiles=profiles,
        capabilities=capabilities,
        execution_allowed=bool(authority.get("execution_allowed", True)),
        promotion_status=str(authority.get("promotion_status", "")),
        live_eligibility_status=str(authority.get("live_eligibility_status", "")),
    )
    expected_domains = {f"R{index:02d}" for index in range(31)}
    if {item.domain_id for item in ontology.domains} != expected_domains:
        raise ValueError("canonical ontology must contain exactly R00 through R30")
    expected_profiles = {f"V{index:02d}" for index in range(1, 13)}
    actual_profiles = {item.profile_id for item in ontology.verification_profiles}
    if actual_profiles != expected_profiles:
        raise ValueError("canonical ontology must contain exactly V01 through V12")
    known_agents = {item.name for item in build_default_registry().definitions}
    known_layers = {item.layer_id for item in modern_agent_stack_requirements()}
    unknown_agents = {
        agent
        for capability in ontology.capabilities
        for agent in capability.target_agents
        if agent not in known_agents
    }
    unknown_layers = {
        layer
        for capability in ontology.capabilities
        for layer in capability.target_layers
        if layer not in known_layers
    }
    if unknown_agents or unknown_layers:
        raise ValueError(
            "ontology contains unknown local targets: "
            f"agents={sorted(unknown_agents)}, layers={sorted(unknown_layers)}"
        )
    return ontology


def _capability(item: Mapping[str, object]) -> AtomicCapability:
    return AtomicCapability(
        capability_id=str(item["id"]),
        domain_id=str(item["domain"]),
        title=str(item["title"]),
        search_query=str(item["query"]),
        target_layers=_strings(item.get("target_layers"), "target_layers"),
        target_agents=_strings(item.get("target_agents"), "target_agents"),
        local_evidence=_strings(item.get("local_evidence"), "local_evidence"),
        verification_profiles=_strings(item.get("verification"), "verification"),
    )


def _mapping_items(
    payload: Mapping[str, object], key: str, *, maximum: int
) -> tuple[Mapping[str, object], ...]:
    value = payload.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"ontology {key} must be a sequence")
    if not value or len(value) > maximum:
        raise ValueError(f"ontology {key} is empty or unbounded")
    return tuple(_mapping(item, key) for item in value)


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"ontology {name} item must be a mapping")
    return cast(Mapping[str, object], value)


def _strings(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"ontology {name} must be a sequence")
    return tuple(str(item) for item in value)
