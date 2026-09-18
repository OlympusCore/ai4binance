"""Default-deny tool policy contracts for advisory orchestration."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum


class ToolPermission(StrEnum):
    READ_ONLY = "READ_ONLY"
    NETWORK_READ = "NETWORK_READ"
    WRITE_APPROVED = "WRITE_APPROVED"


class ToolPermissionAction(StrEnum):
    READ = "READ"
    APPEND = "APPEND"
    DELETE = "DELETE"
    EXECUTE_ORDER = "EXECUTE_ORDER"


class ToolSideEffect(StrEnum):
    READ_LOCAL = "READ_LOCAL"
    NETWORK_READ = "NETWORK_READ"
    WRITE_LOCAL = "WRITE_LOCAL"
    EXTERNAL_WRITE = "EXTERNAL_WRITE"
    FINANCIAL = "FINANCIAL"
    FORBIDDEN = "FORBIDDEN"


class ToolPolicyDecision(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


_DANGEROUS_SIDE_EFFECTS = frozenset(
    {
        ToolSideEffect.EXTERNAL_WRITE,
        ToolSideEffect.FINANCIAL,
        ToolSideEffect.FORBIDDEN,
    }
)

_DANGEROUS_ACTIONS = frozenset(
    {
        ToolPermissionAction.DELETE,
        ToolPermissionAction.EXECUTE_ORDER,
    }
)


@dataclass(frozen=True, slots=True)
class ToolDescriptor:
    name: str
    description: str
    allowed_projects: tuple[str, ...]
    side_effect: ToolSideEffect
    tags: tuple[str, ...] = ()
    schema_tokens: int = 0

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.description.strip():
            raise ValueError("tool descriptor identity is required")
        if not self.allowed_projects or any(
            not project.strip() for project in self.allowed_projects
        ):
            raise ValueError("tool descriptor requires allowed projects")
        if len(set(self.tags)) != len(self.tags):
            raise ValueError("tool descriptor tags must be unique")
        if not 0 <= self.schema_tokens <= 16_384:
            raise ValueError("tool descriptor schema token estimate is invalid")


@dataclass(frozen=True, slots=True)
class CapabilityToolPermission:
    principal: str
    capability_id: str
    resource: str
    tool: str
    actions: tuple[ToolPermissionAction, ...]
    denied: tuple[ToolPermissionAction, ...] = (
        ToolPermissionAction.DELETE,
        ToolPermissionAction.EXECUTE_ORDER,
    )
    llm_based_agent: bool = False
    exposed: bool = True

    def __post_init__(self) -> None:
        for field_name in ("principal", "capability_id", "resource", "tool"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} cannot be empty")
        if not self.actions:
            raise ValueError("tool permission requires actions")
        _require_unique("tool permission actions", self.actions)
        _require_unique("tool permission denied actions", self.denied)
        if set(self.actions) & set(self.denied):
            raise ValueError("tool permission action cannot also be denied")
        if set(self.actions) & _DANGEROUS_ACTIONS:
            raise ValueError("dangerous tool actions cannot be granted")
        if ToolPermissionAction.EXECUTE_ORDER not in self.denied:
            raise ValueError("EXECUTE_ORDER must remain denied")
        if ToolPermissionAction.DELETE not in self.denied:
            raise ValueError("DELETE must remain denied")
        if self.llm_based_agent and self.resource == "OrderGateway" and self.exposed:
            raise ValueError("OrderGateway must not be exposed to LLM-based agents")


@dataclass(frozen=True, slots=True)
class ToolPolicyRule:
    rule_id: str
    effect: ToolPolicyDecision
    tools: tuple[str, ...]
    projects: tuple[str, ...]
    permissions: tuple[ToolPermission, ...]
    side_effects: tuple[ToolSideEffect, ...]

    def __post_init__(self) -> None:
        groups = (self.tools, self.projects, self.permissions, self.side_effects)
        if not self.rule_id.strip() or any(not group for group in groups):
            raise ValueError("tool policy rule identity and selectors are required")
        if any(len(set(group)) != len(group) for group in groups):
            raise ValueError("tool policy rule selectors must be unique")
        if self.effect is not ToolPolicyDecision.DENY and (
            set(self.side_effects) & _DANGEROUS_SIDE_EFFECTS
        ):
            raise ValueError("dangerous side effects cannot be allowed")


@dataclass(frozen=True, slots=True)
class ToolPolicyDocument:
    policy_id: str
    version: str
    default: ToolPolicyDecision = ToolPolicyDecision.DENY
    rules: tuple[ToolPolicyRule, ...] = ()

    def __post_init__(self) -> None:
        if not self.policy_id.strip() or not self.version.strip():
            raise ValueError("tool policy document identity is required")
        if self.default is not ToolPolicyDecision.DENY:
            raise ValueError("tool policy default must deny")
        rule_ids = tuple(rule.rule_id for rule in self.rules)
        if len(set(rule_ids)) != len(rule_ids):
            raise ValueError("tool policy rule IDs must be unique")

    @property
    def sha256(self) -> str:
        payload = json.dumps(
            {
                "default": self.default.value,
                "policy_id": self.policy_id,
                "rules": tuple(
                    {
                        "effect": rule.effect.value,
                        "permissions": tuple(item.value for item in rule.permissions),
                        "projects": rule.projects,
                        "rule_id": rule.rule_id,
                        "side_effects": tuple(item.value for item in rule.side_effects),
                        "tools": rule.tools,
                    }
                    for rule in self.rules
                ),
                "version": self.version,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ToolPolicyEvaluation:
    decision: ToolPolicyDecision
    reason_codes: tuple[str, ...]
    policy_id: str
    policy_version: str
    policy_sha256: str
    rule_id: str | None = None


@dataclass(frozen=True, slots=True)
class ToolPolicyEngine:
    document: ToolPolicyDocument

    def evaluate(
        self,
        descriptor: ToolDescriptor,
        *,
        project: str,
        permission: ToolPermission,
        approved: bool,
    ) -> ToolPolicyEvaluation:
        for rule in self.document.rules:
            if not (
                descriptor.name in rule.tools
                and project in rule.projects
                and permission in rule.permissions
                and descriptor.side_effect in rule.side_effects
            ):
                continue
            decision = rule.effect
            if decision is ToolPolicyDecision.REQUIRE_APPROVAL:
                if not approved:
                    return self._result(
                        decision,
                        ("WRITTEN_APPROVAL_REQUIRED",),
                        rule.rule_id,
                    )
                decision = ToolPolicyDecision.ALLOW
            return self._result(
                decision,
                (f"POLICY_RULE:{rule.rule_id}",),
                rule.rule_id,
            )
        return self._result(
            ToolPolicyDecision.DENY,
            ("POLICY_DEFAULT_DENY",),
            None,
        )

    def _result(
        self,
        decision: ToolPolicyDecision,
        reasons: tuple[str, ...],
        rule_id: str | None,
    ) -> ToolPolicyEvaluation:
        return ToolPolicyEvaluation(
            decision=decision,
            reason_codes=reasons,
            policy_id=self.document.policy_id,
            policy_version=self.document.version,
            policy_sha256=self.document.sha256,
            rule_id=rule_id,
        )


def deny_all_tool_policy() -> ToolPolicyDocument:
    return ToolPolicyDocument(policy_id="ai4binance-deny-all", version="1")


def _require_unique(name: str, values: tuple[StrEnum, ...]) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{name} must be unique")
