"""Bound actual producer/consumer calls to the existing canonical trace journal."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from ai4binance.core.contracts.core_observation import (
    consume_core_output as consume_core_output,
)
from ai4binance.core.contracts.core_observation import (
    current_core_output_observer,
    use_core_output_observer,
)
from ai4binance.core.serialization import to_primitive
from ai4binance.events.traceability import CanonicalTraceJournal, canonical_trace_sha256
from ai4binance.governance.architecture.model import LogicalArchitectureRegistry
from ai4binance.ops.performance import (
    OperationResourceMeasurement,
    measure_resource_operation,
)

if TYPE_CHECKING:
    from ai4binance.governance.enforcement.contracts import CoreConsumptionReceipt


@dataclass(frozen=True, slots=True)
class CoreObservationScope:
    """One explicit local cycle; observations confer no execution authority."""

    repository_root: Path
    registry: LogicalArchitectureRegistry
    cycle_id: str
    subject_sha256: str
    journal: CanonicalTraceJournal | None = None
    _pending: list[CoreConsumptionReceipt] = field(
        default_factory=list, repr=False, compare=False
    )
    _test_provenance: set[str] = field(default_factory=set, repr=False, compare=False)

    def consume[T, U](
        self,
        interface_id: str,
        *,
        inputs: object,
        produce: Callable[[], T],
        consume: Callable[[T], U],
    ) -> U:
        """Persist only after the named consumer finishes, including failures."""
        from ai4binance.governance.enforcement.contracts import CoreConsumptionReceipt
        from ai4binance.governance.enforcement.receipt import _core_source_hashes

        matches = [
            module
            for module in self.registry.core_modules
            if module.assurance is not None
            and any(
                item.interface_id == interface_id
                for item in module.assurance.interfaces
            )
        ]
        if len(matches) != 1:
            raise ValueError("CORE_OBSERVATION_INTERFACE_AMBIGUOUS_OR_UNKNOWN")
        module = matches[0]
        if module.assurance is None:
            raise ValueError("CORE_OBSERVATION_ASSURANCE_REQUIRED")
        binding = next(
            item
            for item in module.assurance.interfaces
            if item.interface_id == interface_id
        )
        sources = _core_source_hashes(
            self.repository_root,
            module,
            self.registry,
            workspace_subject_sha256=self.subject_sha256,
        )
        input_hash = self._digest(inputs)
        output_hash: str | None = None
        outcome_hash: str | None = None
        observations: list[OperationResourceMeasurement] = []

        def handoff() -> U:
            nonlocal output_hash, outcome_hash
            output = produce()
            output_hash = self._digest(output)
            result = consume(output)
            outcome_hash = self._digest(result)
            return result

        def persist(status: str) -> None:
            self._pending.append(
                CoreConsumptionReceipt(
                    core_id=module.core_id,
                    interface_id=interface_id,
                    component_id=binding.component_id,
                    cycle_id=self.cycle_id,
                    producer_ref=binding.producer_ref,
                    consumer_ref=binding.consumer_ref,
                    contract_ref=binding.contract_ref,
                    observed_at=datetime.now(UTC).isoformat(),
                    observation_class="TEST_ONLY"
                    if os.environ.get("PYTEST_CURRENT_TEST")
                    else "OBSERVED_LOCAL_CALL",
                    input_sha256=input_hash,
                    output_sha256=output_hash,
                    outcome_sha256=outcome_hash,
                    resources=asdict(
                        replace(observations[-1], operation_scope="CORE_HANDOFF")
                    ),
                    operation_status=status,
                    source_hashes=sources,
                )
            )

        try:
            result, _ = measure_resource_operation(
                handoff, on_measurement=observations.append
            )
        except BaseException as error:
            if observations:
                try:
                    persist(observations[-1].operation_status)
                except Exception as evidence_error:
                    raise error from evidence_error
            raise
        persist("SUCCESS")
        return result

    def _digest(self, value: object) -> str:
        primitive = to_primitive(value)
        if _contains_test_fixture(primitive):
            self._test_provenance.add("TEST_FIXTURE")
        return canonical_trace_sha256(primitive)

    def flush(self) -> None:
        """Commit observed facts only after checking the complete cycle subject."""
        from ai4binance.governance.enforcement.receipt import (
            persist_core_consumption_batch,
        )

        if self._pending:
            receipts = tuple(
                replace(item, observation_class="TEST_ONLY")
                if self._test_provenance
                else item
                for item in self._pending
            )
            persist_core_consumption_batch(
                self.repository_root,
                self.registry,
                receipts,
                source_subject_sha256=self.subject_sha256,
                journal=self.journal,
            )
            self._pending.clear()


def _contains_test_fixture(value: object) -> bool:
    if isinstance(value, Mapping):
        return value.get("provenance_class") == "TEST_FIXTURE" or any(
            _contains_test_fixture(item) for item in value.values()
        )
    if isinstance(value, list):
        return any(_contains_test_fixture(item) for item in value)
    return False


@contextmanager
def core_observation_scope(
    repository_root: Path,
    cycle_id: str,
    *,
    journal: CanonicalTraceJournal | None = None,
) -> Iterator[CoreObservationScope]:
    """Activate evidence on the caller's stack, never a background observer."""
    from ai4binance.governance.architecture.loader import (
        load_logical_architecture_registry,
    )
    from ai4binance.governance.enforcement.receipt import (
        core_consumption_subject_sha256,
    )

    if not cycle_id.strip():
        raise ValueError("CORE_OBSERVATION_CYCLE_REQUIRED")
    root = repository_root.resolve()
    previous = current_core_output_observer()
    if previous is not None:
        if not isinstance(previous, CoreObservationScope):
            raise ValueError("CORE_OBSERVATION_PROVIDER_MISMATCH")
        if previous.repository_root != root:
            raise ValueError("CORE_OBSERVATION_REPOSITORY_MISMATCH")
        yield previous
        return
    scope = CoreObservationScope(
        root,
        load_logical_architecture_registry(
            root / "docs/registries/registry_logical_architecture.yaml",
            repository_root=root,
        ),
        cycle_id,
        core_consumption_subject_sha256(root),
        journal
        or (
            CanonicalTraceJournal(
                Path(tempfile.gettempdir()) / f"core-test-only-{uuid4().hex}.jsonl"
            )
            if os.environ.get("PYTEST_CURRENT_TEST")
            else None
        ),
    )
    with use_core_output_observer(scope):
        try:
            yield scope
        except BaseException as operation_error:
            try:
                scope.flush()
            except Exception as evidence_error:
                raise operation_error from evidence_error
            raise
        else:
            scope.flush()
