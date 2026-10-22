"""Resolve Core evidence through existing registries, quality and trace owners."""

from __future__ import annotations

import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

import yaml

from ai4binance.governance.architecture.model import (
    CORE_EVIDENCE_DIMENSIONS,
    CoreModule,
    LogicalArchitectureRegistry,
    LogicalRelationType,
)
from ai4binance.ops.performance import (
    OperationResourceLimits,
    OperationResourceMeasurement,
    aggregate_resource_measurements,
    resource_budget_blockers,
)
from ai4binance.schema_validation import validate_local_definition


@dataclass(frozen=True, slots=True)
class CoreAssuranceResult:
    """Technical evidence conclusion, never policy eligibility or human approval."""

    dimensions: Mapping[str, str]
    blockers: tuple[str, ...]
    missing_interface_components: tuple[str, ...]
    unobserved_interfaces: tuple[str, ...]
    resource_blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        if set(self.dimensions) != set(CORE_EVIDENCE_DIMENSIONS):
            raise ValueError("core assurance result must contain all eight dimensions")
        object.__setattr__(self, "dimensions", MappingProxyType(dict(self.dimensions)))

    @property
    def operationally_verified(self) -> bool:
        return (
            not self.blockers
            and set(self.dimensions) == set(CORE_EVIDENCE_DIMENSIONS)
            and all(state == "PROVEN" for state in self.dimensions.values())
        )


def resolve_core_assurance(
    registry: LogicalArchitectureRegistry,
    module: CoreModule,
    root: Path,
    *,
    quality: object,
    quality_blockers: tuple[str, ...],
    consumption: Sequence[dict[str, object]],
    trace_blockers: Sequence[str] = (),
) -> CoreAssuranceResult:
    """Require complete component coverage; one receipt cannot prove a whole Core."""
    components = [
        item
        for item in registry.components
        if item.component_id in module.component_ids
    ]
    contract = module.assurance
    bindings = () if contract is None else contract.interfaces
    missing = tuple(
        sorted(set(module.component_ids) - {item.component_id for item in bindings})
    )
    consumption = _latest_consumption(consumption)
    observed = {
        str(item["interface_id"]): item
        for item in consumption
        if item.get("core_id") == module.core_id
        and item.get("observation_class") == "OBSERVED_LOCAL_CALL"
        and item.get("operation_status") == "SUCCESS"
    }
    unobserved = tuple(
        sorted(
            item.interface_id for item in bindings if item.interface_id not in observed
        )
    )
    same_cycle = len({item.get("cycle_id") for item in observed.values()}) == 1
    complete = bool(bindings) and not missing and not unobserved and same_cycle
    ownership = (
        len(components) == len(module.component_ids)
        and module.accountable_component_id in module.component_ids
        and len(module.accountability_refs) == 4
        and all(
            (root / reference).is_file()
            for reference in module.accountability_refs.values()
        )
    )
    failure_tests = () if contract is None else contract.failure_test_refs
    results = quality.get("test_results", []) if isinstance(quality, dict) else []
    passed = {
        str(item.get("node_id"))
        for item in results
        if isinstance(item, dict) and item.get("result") == "PASS"
    }
    failures_proven = (
        bool(failure_tests)
        and not quality_blockers
        and all(
            any(
                node == reference or node.startswith(reference + "[") for node in passed
            )
            for reference in failure_tests
        )
    )
    safe_boundary = (
        all(
            not item.execution_allowed
            and not item.risk_override
            and not item.validation_override
            and not item.decision_authority
            for item in components
        )
        and contract is not None
        and bool(contract.veto_boundary_refs)
        and all(
            (root / reference).is_file() for reference in contract.veto_boundary_refs
        )
    )
    resources = _resource_blockers(root, module, observed, complete)
    dependencies_proven = complete and _dependencies_proven(
        registry, module, consumption
    )
    dimensions = {
        "ownership": "PROVEN" if ownership else "UNKNOWN",
        "input_output": "PROVEN" if complete else "DECLARED" if bindings else "UNKNOWN",
        "dependencies": "PROVEN" if dependencies_proven else "DECLARED",
        "veto_boundary": "PROVEN" if safe_boundary and failures_proven else "PARTIAL",
        "failure_behavior": "PROVEN" if failures_proven else "UNKNOWN",
        "resource_budget": "PROVEN"
        if not resources
        else "PARTIAL"
        if observed
        else "UNKNOWN",
        "tests_evidence": "PROVEN"
        if isinstance(quality, dict) and not quality_blockers
        else "UNKNOWN",
        "runtime_consumer": "PROVEN"
        if complete
        else "PARTIAL"
        if observed
        else "UNKNOWN",
    }
    blockers = tuple(
        dict.fromkeys(
            (
                *(
                    f"CORE_{name.upper()}_NOT_PROVEN"
                    for name, value in dimensions.items()
                    if value != "PROVEN"
                ),
                *(f"CORE_INTERFACE_COMPONENT_UNDECLARED:{item}" for item in missing),
                *(f"CORE_INTERFACE_UNOBSERVED:{item}" for item in unobserved),
                *(
                    "CORE_INTERFACE_CYCLE_MISMATCH"
                    for _ in (0,)
                    if observed and not same_cycle
                ),
                *quality_blockers,
                *trace_blockers,
                *resources,
            )
        )
    )
    return CoreAssuranceResult(dimensions, blockers, missing, unobserved, resources)


def _latest_consumption(
    consumption: Sequence[dict[str, object]],
) -> tuple[dict[str, object], ...]:
    latest: dict[tuple[str, str], dict[str, object]] = {}
    for item in consumption:
        if item.get("observation_class") == "OBSERVED_LOCAL_CALL":
            key = (str(item["core_id"]), str(item["interface_id"]))
            previous = latest.get(key)
            if (
                previous is not None
                and item.get("observed_at")
                and previous.get("observed_at")
            ):
                current_at = datetime.fromisoformat(str(item["observed_at"]))
                previous_at = datetime.fromisoformat(str(previous["observed_at"]))
                if current_at < previous_at or (
                    current_at == previous_at
                    and previous.get("operation_status") != "SUCCESS"
                    and item.get("operation_status") == "SUCCESS"
                ):
                    continue
            latest[key] = item
    return tuple(latest.values())


def _dependencies_proven(
    registry: LogicalArchitectureRegistry,
    module: CoreModule,
    consumption: Sequence[dict[str, object]],
) -> bool:
    for relation in registry.relations:
        if (
            relation.from_component_id not in module.component_ids
            or relation.relation_type
            not in {
                LogicalRelationType.CONSUMES,
                LogicalRelationType.DEPENDS_ON,
            }
        ):
            continue
        producers = [
            item
            for item in consumption
            if item.get("component_id") == relation.to_component_id
            and item.get("operation_status") == "SUCCESS"
            and item.get("observation_class") == "OBSERVED_LOCAL_CALL"
        ]
        consumers = [
            item
            for item in consumption
            if item.get("component_id") == relation.from_component_id
            and item.get("operation_status") == "SUCCESS"
            and item.get("observation_class") == "OBSERVED_LOCAL_CALL"
        ]
        if not any(
            a["cycle_id"] == b["cycle_id"] and a["output_sha256"] == b["input_sha256"]
            for a in producers
            for b in consumers
        ):
            return False
    return True


def _resource_blockers(
    root: Path,
    module: CoreModule,
    observed: Mapping[str, dict[str, object]],
    complete: bool,
) -> tuple[str, ...]:
    contract = module.assurance
    if contract is None or contract.resource_budget_ref is None:
        return ("CORE_RESOURCE_BUDGET_UNDECLARED",)
    path = (root / contract.resource_budget_ref).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        return ("CORE_RESOURCE_BUDGET_UNAVAILABLE",)
    try:
        text = path.read_text(encoding="utf-8")
        payload = (
            tomllib.loads(text) if path.suffix == ".toml" else yaml.safe_load(text)
        )
        validate_local_definition(
            root / "schemas/governance/governed_object_enforcement.schema.json",
            "OperationResourceLimits",
            payload,
        )
        limits = OperationResourceLimits(**payload)
        blockers = [] if complete else ["CORE_RESOURCE_MEASUREMENT_INCOMPLETE"]
        if len({proof.get("cycle_id") for proof in observed.values()}) != 1:
            blockers.append("CORE_RESOURCE_CYCLE_INCOMPLETE")
        measurements = []
        for interface_id, proof in observed.items():
            raw = proof.get("resources")
            if not isinstance(raw, dict):
                raise ValueError("resource counters are missing")
            measured = OperationResourceMeasurement(**cast(dict[str, Any], raw))
            measurements.append(measured)
            if measured.operation_scope != "CORE_HANDOFF":
                blockers.append(f"{interface_id}:CORE_RESOURCE_SCOPE_INCOMPLETE")
        if measurements:
            blockers.extend(
                resource_budget_blockers(
                    aggregate_resource_measurements(measurements),
                    limits,
                )
            )
        return tuple(blockers)
    except OSError, ValueError, TypeError, yaml.YAMLError:
        return ("CORE_RESOURCE_EVIDENCE_INVALID",)
