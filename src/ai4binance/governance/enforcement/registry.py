"""Registry loading and coverage checks for governed-object enforcement profiles."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

import yaml

from ai4binance.governance.enforcement.contracts import (
    ActionTransitionRule,
    EnforcementGate,
    EnforcementProfile,
)
from ai4binance.governance.repository_validator import KnowledgeObjectType
from ai4binance.schema_validation import validate_local_definition

DEFAULT_ENFORCEMENT_PROFILE_REGISTRY_PATH = Path(
    "config/governance/enforcement_profiles.yaml"
)


def expected_governed_object_types() -> tuple[str, ...]:
    return ("REPOSITORY_ARTIFACT", *tuple(item.value for item in KnowledgeObjectType))


@dataclass(frozen=True, slots=True)
class EnforcementProfileRegistry:
    version: str
    profiles: tuple[EnforcementProfile, ...]
    attestation_providers: Mapping[str, Mapping[str, object]] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("enforcement profile registry version is required")
        if not self.profiles:
            raise ValueError("enforcement profile registry requires profiles")
        profile_ids = tuple(profile.profile_id for profile in self.profiles)
        if len(set(profile_ids)) != len(profile_ids):
            raise ValueError("enforcement profile IDs must be unique")
        object_types = tuple(profile.object_type for profile in self.profiles)
        if len(set(object_types)) != len(object_types):
            raise ValueError("enforcement profiles must be unique per object_type")
        providers: dict[str, Mapping[str, object]] = {}
        for name, provider in self.attestation_providers.items():
            gates = provider.get("gates")
            if not isinstance(gates, list | tuple) or not gates:
                raise ValueError("attestation provider gates are required")
            providers[name] = MappingProxyType({**provider, "gates": tuple(gates)})
        object.__setattr__(self, "attestation_providers", MappingProxyType(providers))

    def profile_for_object_type(self, object_type: str) -> EnforcementProfile | None:
        for profile in self.profiles:
            if profile.object_type == object_type:
                return profile
        return None

    def assert_full_coverage(self, expected_types: Iterable[str] | None = None) -> None:
        required = set(expected_types or expected_governed_object_types())
        actual = {profile.object_type for profile in self.profiles}
        missing = sorted(required - actual)
        extra = sorted(actual - required)
        if missing or extra:
            parts: list[str] = []
            if missing:
                parts.append("missing=" + ",".join(missing))
            if extra:
                parts.append("extra=" + ",".join(extra))
            raise ValueError(
                "enforcement profile coverage mismatch: " + "; ".join(parts)
            )


def load_enforcement_profile_registry(
    path: Path = DEFAULT_ENFORCEMENT_PROFILE_REGISTRY_PATH,
) -> EnforcementProfileRegistry:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("enforcement profile registry must be a mapping")
    validate_local_definition(
        Path(__file__).resolve().parents[4]
        / "schemas/governance/governed_object_enforcement.schema.json",
        "EnforcementProfileRegistry",
        payload,
    )
    version = str(payload.get("version", "")).strip()
    raw_profiles = payload.get("profiles")
    if not isinstance(raw_profiles, list):
        raise ValueError("enforcement profile registry profiles must be a list")
    profiles = tuple(_profile_from_payload(item) for item in raw_profiles)
    registry = EnforcementProfileRegistry(
        version=version,
        profiles=profiles,
        attestation_providers=payload.get("attestation_providers", {}),
    )
    registry.assert_full_coverage()
    return registry


def _profile_from_payload(payload: object) -> EnforcementProfile:
    if not isinstance(payload, Mapping):
        raise ValueError("enforcement profile must be a mapping")
    raw_gates = payload.get("required_gates", ())
    if not isinstance(raw_gates, list):
        raise ValueError("enforcement profile required_gates must be a list")
    raw_transitions = payload.get("allowed_lifecycle_transitions", {})
    if not isinstance(raw_transitions, Mapping):
        raise ValueError("allowed_lifecycle_transitions must be a mapping")
    raw_action_rules = payload.get("action_transition_rules", {})
    if not isinstance(raw_action_rules, Mapping):
        raise ValueError("action_transition_rules must be a mapping")
    transitions: dict[str, tuple[str, ...]] = {}
    for source, targets in raw_transitions.items():
        if not isinstance(source, str) or not source.strip():
            raise ValueError("lifecycle transition source must be non-empty string")
        if not isinstance(targets, list):
            raise ValueError("lifecycle transition targets must be a list")
        normalized_targets = tuple(str(target).strip() for target in targets)
        transitions[source] = normalized_targets
    action_transition_rules: dict[str, ActionTransitionRule] = {}
    for action, rule in raw_action_rules.items():
        if not isinstance(action, str) or not action.strip():
            raise ValueError("action transition rule keys must be non-empty strings")
        if not isinstance(rule, Mapping):
            raise ValueError("action transition rule must be a mapping")
        raw_allowed_from = rule.get("allowed_from", ())
        raw_allowed_to = rule.get("allowed_to", ())
        if not isinstance(raw_allowed_from, list) or not isinstance(
            raw_allowed_to, list
        ):
            raise ValueError(
                "action transition rule allowed_from and allowed_to must be lists"
            )
        action_transition_rules[action] = ActionTransitionRule(
            action=action.strip(),
            transition_required=bool(rule.get("transition_required", False)),
            allowed_from=tuple(str(item).strip() for item in raw_allowed_from),
            allowed_to=tuple(str(item).strip() for item in raw_allowed_to),
        )
    return EnforcementProfile(
        profile_id=str(payload.get("profile_id", "")).strip(),
        profile_version=str(payload.get("profile_version", "")).strip(),
        object_type=str(payload.get("object_type", "")).strip(),
        allowed_actions=tuple(
            str(item).strip() for item in payload.get("allowed_actions", ())
        ),
        required_gates=tuple(EnforcementGate(str(item).strip()) for item in raw_gates),
        required_evidence=tuple(
            str(item).strip() for item in payload.get("required_evidence", ())
        ),
        required_authorities=tuple(
            str(item).strip() for item in payload.get("required_authorities", ())
        ),
        allowed_lifecycle_transitions=transitions,
        action_transition_rules=action_transition_rules,
        side_effect_class=str(payload.get("side_effect_class", "NONE")).strip(),
        human_approval_class=str(payload.get("human_approval_class", "NONE")).strip(),
    )
