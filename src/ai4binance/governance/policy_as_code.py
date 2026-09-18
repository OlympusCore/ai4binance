"""Default-deny policy-as-code engine for governed framework decisions."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType


class PolicyEffect(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    RESTRICT = "RESTRICT"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


class PolicyConditionOperator(StrEnum):
    EQUALS = "EQUALS"
    NOT_EQUALS = "NOT_EQUALS"
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    IN = "IN"


_TRADING_AUTHORITY_ACTIONS = frozenset(
    {
        "AUTHORIZE_TRADE",
        "EXECUTE_ORDER",
        "ENABLE_LIVE",
        "PROMOTE_LIVE",
        "OVERRIDE_RISK",
    }
)


@dataclass(frozen=True, slots=True)
class PolicyCondition:
    key: str
    operator: PolicyConditionOperator
    values: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise ValueError("policy condition key cannot be empty")
        if (
            self.operator
            in {
                PolicyConditionOperator.EQUALS,
                PolicyConditionOperator.NOT_EQUALS,
                PolicyConditionOperator.IN,
            }
            and not self.values
        ):
            raise ValueError("policy condition values are required")
        if (
            self.operator
            in {
                PolicyConditionOperator.PRESENT,
                PolicyConditionOperator.ABSENT,
            }
            and self.values
        ):
            raise ValueError("presence policy conditions cannot contain values")
        _require_unique("policy condition values", self.values)

    def matches(self, facts: Mapping[str, str]) -> bool:
        present = self.key in facts
        if self.operator is PolicyConditionOperator.PRESENT:
            return present
        if self.operator is PolicyConditionOperator.ABSENT:
            return not present
        if not present:
            return False
        value = facts[self.key]
        if self.operator is PolicyConditionOperator.EQUALS:
            return value == self.values[0]
        if self.operator is PolicyConditionOperator.NOT_EQUALS:
            return value != self.values[0]
        return value in self.values


@dataclass(frozen=True, slots=True)
class PolicyAsCodeRule:
    rule_id: str
    effect: PolicyEffect
    resource_types: tuple[str, ...]
    actions: tuple[str, ...]
    conditions: tuple[PolicyCondition, ...] = ()
    reason_code: str = "POLICY_RULE_MATCH"
    priority: int = 100

    def __post_init__(self) -> None:
        if not self.rule_id.strip() or not self.reason_code.strip():
            raise ValueError("policy rule identity is required")
        if not self.resource_types or not self.actions:
            raise ValueError("policy rule selectors are required")
        _require_unique("policy resource types", self.resource_types)
        _require_unique("policy actions", self.actions)
        condition_keys = tuple(item.key for item in self.conditions)
        _require_unique("policy condition keys", condition_keys)
        if self.priority < 0:
            raise ValueError("policy priority cannot be negative")
        if self.effect is PolicyEffect.ALLOW and (
            set(self.actions) & _TRADING_AUTHORITY_ACTIONS
        ):
            raise ValueError("policy-as-code cannot allow trading authority actions")


@dataclass(frozen=True, slots=True)
class PolicyAsCodeDocument:
    policy_id: str
    version: str
    rules: tuple[PolicyAsCodeRule, ...] = ()
    default_effect: PolicyEffect = PolicyEffect.DENY

    def __post_init__(self) -> None:
        if not self.policy_id.strip() or not self.version.strip():
            raise ValueError("policy-as-code document identity is required")
        if self.default_effect is not PolicyEffect.DENY:
            raise ValueError("policy-as-code default must deny")
        rule_ids = tuple(item.rule_id for item in self.rules)
        _require_unique("policy rule IDs", rule_ids)

    @property
    def sha256(self) -> str:
        payload = {
            "default_effect": self.default_effect.value,
            "policy_id": self.policy_id,
            "rules": tuple(
                {
                    "actions": rule.actions,
                    "conditions": tuple(
                        {
                            "key": condition.key,
                            "operator": condition.operator.value,
                            "values": condition.values,
                        }
                        for condition in rule.conditions
                    ),
                    "effect": rule.effect.value,
                    "priority": rule.priority,
                    "reason_code": rule.reason_code,
                    "resource_types": rule.resource_types,
                    "rule_id": rule.rule_id,
                }
                for rule in self.rules
            ),
            "version": self.version,
        }
        canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PolicyRequest:
    resource_type: str
    action: str
    facts: Mapping[str, str] = field(default_factory=dict)
    approved: bool = False

    def __post_init__(self) -> None:
        if not self.resource_type.strip() or not self.action.strip():
            raise ValueError("policy request identity is required")
        if any(
            not key.strip() or not value.strip() for key, value in self.facts.items()
        ):
            raise ValueError("policy facts must be non-empty strings")
        object.__setattr__(self, "facts", MappingProxyType(dict(self.facts)))


@dataclass(frozen=True, slots=True)
class PolicyEvaluation:
    effect: PolicyEffect
    reason_codes: tuple[str, ...]
    policy_id: str
    policy_version: str
    policy_sha256: str
    rule_id: str | None = None
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        live_unblocked = self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        if self.execution_allowed or live_unblocked:
            raise ValueError("policy evaluation cannot grant execution authority")


@dataclass(frozen=True, slots=True)
class PolicyAsCodeEngine:
    document: PolicyAsCodeDocument

    def evaluate(self, request: PolicyRequest) -> PolicyEvaluation:
        for rule in sorted(
            self.document.rules,
            key=lambda item: (item.priority, item.rule_id),
        ):
            if request.resource_type not in rule.resource_types:
                continue
            if request.action not in rule.actions:
                continue
            conditions_match = all(
                condition.matches(request.facts) for condition in rule.conditions
            )
            if not conditions_match:
                continue
            if rule.effect is PolicyEffect.REQUIRE_APPROVAL and request.approved:
                return self._result(
                    PolicyEffect.ALLOW,
                    (f"POLICY_RULE:{rule.rule_id}", "APPROVAL_RECORDED"),
                    rule.rule_id,
                )
            if rule.effect is PolicyEffect.REQUIRE_APPROVAL:
                return self._result(
                    PolicyEffect.REQUIRE_APPROVAL,
                    (rule.reason_code, "APPROVAL_REQUIRED"),
                    rule.rule_id,
                )
            return self._result(
                rule.effect,
                (f"POLICY_RULE:{rule.rule_id}", rule.reason_code),
                rule.rule_id,
            )
        return self._result(
            self.document.default_effect,
            ("POLICY_AS_CODE_DEFAULT_DENY",),
            None,
        )

    def _result(
        self,
        effect: PolicyEffect,
        reason_codes: tuple[str, ...],
        rule_id: str | None,
    ) -> PolicyEvaluation:
        return PolicyEvaluation(
            effect=effect,
            reason_codes=reason_codes,
            policy_id=self.document.policy_id,
            policy_version=self.document.version,
            policy_sha256=self.document.sha256,
            rule_id=rule_id,
        )


def deny_all_policy_as_code() -> PolicyAsCodeDocument:
    return PolicyAsCodeDocument(policy_id="AI4BINANCE-PAC-DENY-ALL", version="1")


def _require_unique(name: str, values: tuple[str, ...]) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{name} must be unique")
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain empty values")
