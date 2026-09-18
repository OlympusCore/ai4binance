"""Exact-bound aggregation of immutable validation evidence, never trade authority.

Producers retain ownership of calculations. A governed specification supplies
every numerical threshold; this module verifies artifacts and combines vetoes.
Missing specifications, holdout history or forward observations cannot be
replaced by a summary or by a high aggregate score.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from itertools import pairwise
from math import isfinite
from pathlib import Path
from typing import cast

from ai4binance.validation.promotion_evidence import (
    PromotionEvidenceQuery,
    PromotionEvidenceRegistry,
    PromotionEvidenceSourceKind,
    _record_from_payload,
)

_HASH = re.compile(r"[0-9a-f]{64}")
MAX_ARTIFACT_BYTES = 8 * 1024 * 1024


def runtime_source_sha256() -> str:
    """Bind a deployment to the installed Python source, including local edits."""
    root = Path(__file__).resolve().parents[1]
    paths = sorted(root.rglob("*.py"))
    if not paths or len(paths) > 2048:
        raise ValueError("OOS_RUNTIME_SOURCE_INVALID")
    identities = []
    for path in paths:
        if path.is_symlink():
            raise ValueError("OOS_RUNTIME_SOURCE_INVALID")
        with path.open("rb") as stream:
            raw = stream.read(MAX_ARTIFACT_BYTES + 1)
        if len(raw) > MAX_ARTIFACT_BYTES:
            raise ValueError("OOS_RUNTIME_SOURCE_INVALID")
        identities.append((path.relative_to(root).as_posix(), sha256(raw).hexdigest()))
    return sha256(json.dumps(identities, separators=(",", ":")).encode()).hexdigest()


# These are evidence obligations, not numerical promotion thresholds.
REQUIRED_MEASUREMENTS: dict[str, tuple[str, ...]] = {
    "dataset": (
        "point_in_time_status",
        "quality_status",
        "revision_status",
        "missing_intervals",
        "duplicate_count",
        "observation_days",
        "cost_data_coverage",
    ),
    "backtest": ("realism_status", "cost_model_sha256", "execution_model_version"),
    "walk_forward": ("fold_count", "train_only_selection", "purge", "embargo"),
    "final_holdout": ("trade_count", "expectancy", "net_return", "max_drawdown"),
    "regime": ("regime_count", "unknown_ratio", "attribution_status"),
    "robustness": (
        "parameter_stability",
        "fold_stability",
        "regime_stability",
        "cpcv_status",
        "monte_carlo_status",
        "selection_overfit_status",
        "edge_concentration",
        "failure_modes_status",
    ),
    "statistics": (
        "effective_sample_size",
        "confidence_interval_lower",
        "profit_factor",
        "profitable_fold_ratio",
        "hypothesis_count",
        "multiple_testing_method",
        "confirmatory",
    ),
    "cost_stress": ("scenario_coverage", "edge_survival"),
    "replication": ("declared_scope_coverage", "stability_status"),
    "paper_forward": (
        "historical_oos_completed_at",
        "observation_started_at",
        "observation_ended_at",
        "observation_days",
        "trade_count",
        "frequency_comparison",
        "cost_comparison",
        "expectancy_comparison",
        "drawdown_comparison",
        "regime_comparison",
        "signal_decay_status",
        "runtime_failures",
    ),
    "reproducibility": ("repository_clean", "replay_equal", "implementation_sha256"),
}


@dataclass(frozen=True, slots=True)
class OOSValidationSubject:
    """Extend the canonical promotion identity without inventing a parallel key."""

    promotion: PromotionEvidenceQuery
    setup_type: str
    feature_definition_sha256: str
    cost_model_sha256: str
    validation_config_sha256: str

    @classmethod
    def from_payload(cls, value: object, *, as_of: datetime) -> OOSValidationSubject:
        """Restore an independently configured exact deployment subject."""
        payload = _object(value)
        promotion = _object(payload.get("promotion"))
        identity = {
            name: _required_text(promotion, name)
            for name in (
                "strategy_id",
                "strategy_version",
                "strategy_sha256",
                "symbol",
                "market_type",
                "timeframe",
                "parameter_set_sha256",
                "dataset_sha256",
                "code_revision",
            )
        }
        return cls(
            promotion=PromotionEvidenceQuery(**identity, as_of=as_of),
            setup_type=_required_text(payload, "setup_type"),
            feature_definition_sha256=_required_text(
                payload, "feature_definition_sha256"
            ),
            cost_model_sha256=_required_text(payload, "cost_model_sha256"),
            validation_config_sha256=_required_text(
                payload, "validation_config_sha256"
            ),
        )

    def __post_init__(self) -> None:
        if not self.setup_type.strip():
            raise ValueError("OOS setup identity is required")
        for digest in (
            self.feature_definition_sha256,
            self.cost_model_sha256,
            self.validation_config_sha256,
        ):
            if not _HASH.fullmatch(digest):
                raise ValueError("OOS subject hashes must be SHA-256")

    @property
    def subject_key(self) -> str:
        values = (
            *self.promotion.subject_key,
            self.setup_type,
            self.feature_definition_sha256,
            self.cost_model_sha256,
            self.validation_config_sha256,
        )
        return sha256(json.dumps(values, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class OOSArtifactReference:
    """A content-addressed artifact relative to an explicitly bounded root."""

    path: str
    sha256: str

    def __post_init__(self) -> None:
        if not self.path.strip() or not _HASH.fullmatch(self.sha256):
            raise ValueError("OOS artifact path and SHA-256 are required")


@dataclass(frozen=True, slots=True)
class OOSMaturityEvidenceBundle:
    """One subject and underlying artifacts; no caller-supplied maturity score."""

    subject: OOSValidationSubject | None
    artifacts: tuple[tuple[str, OOSArtifactReference], ...] = ()
    specification: OOSArtifactReference | None = None
    promotion: PromotionEvidenceRegistry = field(
        default_factory=PromotionEvidenceRegistry
    )
    blockers: tuple[str, ...] = ()

    @property
    def bundle_sha256(self) -> str:
        payload = {
            "subject_key": None if self.subject is None else self.subject.subject_key,
            "artifacts": sorted(
                (stage, ref.path, ref.sha256) for stage, ref in self.artifacts
            ),
            "specification": None
            if self.specification is None
            else (self.specification.path, self.specification.sha256),
            "blockers": sorted(self.blockers),
        }
        return sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class OOSMaturityResult:
    status: str
    subject_key: str | None
    bundle_sha256: str
    blockers: tuple[str, ...]
    stage_results: tuple[tuple[str, str], ...]
    execution_allowed: bool = field(default=False, init=False)
    promotion_status: str = field(default="RESEARCH_ONLY", init=False)
    live_eligibility_status: str = field(default="LIVE_ORDER_BLOCKED", init=False)


@dataclass(frozen=True, slots=True)
class OOSMaturityGate:
    """Verify bytes, identity, chronology, policy checks and exact promotion binding."""

    artifact_root: Path

    def load_deployment(
        self, deployment_path: Path, *, as_of: datetime
    ) -> tuple[tuple[OOSValidationSubject, ...], tuple[OOSMaturityEvidenceBundle, ...]]:
        """Load configured subjects and hash-bound bundles; never infer promotion.

        The deployment file is operator configuration. Evidence remains under the
        bounded artifact root and is independently revalidated at decision time.
        A bundle cannot nominate its own expected deployment identity.
        """
        if not deployment_path.is_file():
            raise ValueError("OOS_DEPLOYMENT_MISSING")
        with deployment_path.open("rb") as stream:
            raw = stream.read(MAX_ARTIFACT_BYTES + 1)
        if len(raw) > MAX_ARTIFACT_BYTES or deployment_path.is_symlink():
            raise ValueError("OOS_DEPLOYMENT_INVALID")
        deployment = _object(json.loads(raw))
        _research_only_payload(deployment)
        if deployment.get("runtime_source_sha256") != runtime_source_sha256():
            raise ValueError("OOS_RUNTIME_SOURCE_MISMATCH")
        entries = deployment.get("subjects")
        if not isinstance(entries, list) or not 1 <= len(entries) <= 256:
            raise ValueError("OOS_DEPLOYMENT_SUBJECTS_INVALID")
        subjects: list[OOSValidationSubject] = []
        bundles: list[OOSMaturityEvidenceBundle] = []
        for raw_entry in entries:
            entry = _object(raw_entry)
            subject = OOSValidationSubject.from_payload(
                entry.get("subject"), as_of=as_of
            )
            payload = self._read(_artifact_reference(entry.get("bundle")))
            _research_only_payload(payload)
            actual = OOSValidationSubject.from_payload(
                payload.get("subject"), as_of=as_of
            )
            if actual.subject_key != subject.subject_key:
                raise ValueError("OOS_DEPLOYMENT_IDENTITY_MISMATCH")
            raw_artifacts = _object(payload.get("artifacts"))
            raw_records = payload.get("promotion_records")
            raw_blockers = payload.get("blockers")
            if (
                not isinstance(raw_records, list)
                or len(raw_records) > 4096
                or not isinstance(raw_blockers, list)
                or any(not isinstance(item, str) or not item for item in raw_blockers)
            ):
                raise ValueError("OOS_BUNDLE_INVALID")
            bundles.append(
                OOSMaturityEvidenceBundle(
                    subject=actual,
                    artifacts=tuple(
                        (name, _artifact_reference(ref))
                        for name, ref in raw_artifacts.items()
                    ),
                    specification=_artifact_reference(payload.get("specification")),
                    promotion=PromotionEvidenceRegistry.from_records(
                        tuple(
                            _record_from_payload(_object(record))
                            for record in raw_records
                        )
                    ),
                    blockers=tuple(raw_blockers),
                )
            )
            subjects.append(subject)
        if len({subject.subject_key for subject in subjects}) != len(subjects):
            raise ValueError("OOS_DEPLOYMENT_DUPLICATE_SUBJECT")
        return tuple(subjects), tuple(bundles)

    def evaluate(self, bundle: OOSMaturityEvidenceBundle) -> OOSMaturityResult:
        blockers = list(bundle.blockers)
        hard: list[str] = []
        stages: list[tuple[str, str]] = []
        subject = bundle.subject
        if subject is None:
            hard.append("EVIDENCE_IDENTITY_MISSING")
        spec: dict[str, object] = {}
        if bundle.specification is None:
            blockers.append("VALIDATION_SPECIFICATION_MISSING")
        else:
            try:
                spec = self._read(bundle.specification)
                if (
                    subject is None
                    or bundle.specification.sha256 != subject.validation_config_sha256
                ):
                    hard.append("VALIDATION_SPECIFICATION_IDENTITY_MISMATCH")
                owner = spec.get("owner")
                if (
                    spec.get("status") != "ACTIVE"
                    or not isinstance(owner, str)
                    or not owner.strip()
                ):
                    hard.append("VALIDATION_SPECIFICATION_NOT_GOVERNED")
                if subject is not None and spec.get("scope") != list(
                    subject.promotion.subject_key[:6]
                ):
                    hard.append("VALIDATION_SCOPE_MISMATCH")
            except (OSError, ValueError) as exc:
                hard.append(str(exc))
        references = dict(bundle.artifacts)
        if len(references) != len(bundle.artifacts):
            hard.append("CONFLICTING_VALIDATION_EVIDENCE")
        if set(references) - set(REQUIRED_MEASUREMENTS):
            hard.append("UNKNOWN_VALIDATION_EVIDENCE_STAGE")
        for stage, required in REQUIRED_MEASUREMENTS.items():
            if stage not in references:
                blockers.append(f"{stage.upper()}_EVIDENCE_MISSING")
                stages.append((stage, "MISSING"))
                continue
            stage_blockers: list[str] = []
            try:
                evidence = self._read(references[stage])
                if (
                    subject is None
                    or evidence.get("subject_key") != subject.subject_key
                ):
                    raise ValueError("EVIDENCE_IDENTITY_MISMATCH")
                self._identity(evidence, subject, bundle.promotion.max_evidence_age)
                if evidence.get("stage") != stage:
                    raise ValueError("EVIDENCE_STAGE_MISMATCH")
                raw_blockers = evidence.get("blockers")
                if not isinstance(raw_blockers, list) or any(
                    not isinstance(b, str) or not b for b in raw_blockers
                ):
                    raise ValueError("EVIDENCE_BLOCKERS_INVALID")
                stage_blockers.extend(raw_blockers)
                measurements = _object(evidence.get("measurements"))
                if measurements.get("blockers") != []:
                    stage_blockers.append("UNDERLYING_VALIDATION_BLOCKERS_PRESENT")
                self._measurement_types(measurements)
                rules = _object(_object(spec.get("requirements")).get(stage))
                if not rules or not {"blockers", *required}.issubset(rules):
                    stage_blockers.append("GOVERNED_THRESHOLDS_MISSING")
                for name, rule in rules.items():
                    if not _matches(measurements.get(name), _object(rule)):
                        stage_blockers.append(f"{stage.upper()}:{name}:INSUFFICIENT")
                if (
                    stage == "backtest"
                    and measurements.get("cost_model_sha256")
                    != subject.cost_model_sha256
                ):
                    raise ValueError("COST_MODEL_IDENTITY_MISMATCH")
                sources = evidence.get("source_artifacts")
                source_documents: list[object] = []
                if not isinstance(sources, list) or not sources:
                    stage_blockers.append("UNDERLYING_EVIDENCE_MISSING")
                else:
                    for source in sources:
                        source_ref = _object(source)
                        raw = self._bytes(
                            OOSArtifactReference(
                                str(source_ref.get("path", "")),
                                str(source_ref.get("sha256", "")),
                            )
                        )
                        try:
                            source_document: object = json.loads(raw)
                        except json.JSONDecodeError:
                            source_document = [
                                json.loads(line)
                                for line in raw.splitlines()
                                if line.strip()
                            ]
                        identity_pointer = source_ref.get(
                            "identity_pointer", ["subject_key"]
                        )
                        if (
                            not isinstance(identity_pointer, list)
                            or _at(source_document, identity_pointer)
                            != subject.subject_key
                        ):
                            raise ValueError("SOURCE_EVIDENCE_IDENTITY_MISMATCH")
                        source_documents.append(source_document)
                bindings = _object(evidence.get("measurement_sources"))
                for name in rules:
                    binding = _object(bindings.get(name))
                    index = binding.get("source_index")
                    pointer = binding.get("pointer")
                    if (
                        type(index) is not int
                        or not 0 <= index < len(source_documents)
                        or not isinstance(pointer, list)
                    ):
                        stage_blockers.append(
                            f"{stage.upper()}:{name}:SOURCE_BINDING_MISSING"
                        )
                        continue
                    actual = _at(source_documents[index], pointer)
                    if type(actual) is not type(
                        measurements.get(name)
                    ) or actual != measurements.get(name):
                        raise ValueError("MEASUREMENT_SOURCE_MISMATCH")
                if (
                    stage == "dataset"
                    and subject.promotion.market_type == "USD_M_FUTURES"
                ):
                    for name in (
                        "funding_data_coverage",
                        "mark_index_coverage",
                        "margin_semantics_status",
                        "liquidation_constraints_status",
                        "long_short_coverage",
                    ):
                        if name not in rules or not _matches(
                            measurements.get(name), _object(rules.get(name))
                        ):
                            stage_blockers.append(
                                f"FUTURES_{name.upper()}_INSUFFICIENT"
                            )
                if stage == "final_holdout":
                    self._holdout(evidence, subject)
                if stage == "paper_forward":
                    completed = _time(measurements.get("historical_oos_completed_at"))
                    started = _time(measurements.get("observation_started_at"))
                    ended = _time(measurements.get("observation_ended_at"))
                    if not completed < started < ended <= subject.promotion.as_of:
                        raise ValueError("PAPER_FORWARD_CHRONOLOGY_INVALID")
            except (OSError, ValueError) as exc:
                hard.append(f"{stage.upper()}:{exc}")
                stages.append((stage, "BLOCKED"))
            else:
                blockers.extend(stage_blockers)
                stages.append((stage, "PASS" if not stage_blockers else "INCOMPLETE"))
        if subject is not None:
            # Resolve the entire registry: filtering first can hide newer vetoes.
            records = tuple(
                record
                for record in bundle.promotion.records
                if record.exact_subject_key == subject.promotion.subject_key
            )
            latest = max(records, key=lambda record: record.observed_at, default=None)
            if (
                not bundle.promotion.has_promotion_evidence(query=subject.promotion)
                or latest is None
                or latest.source_kind
                is not PromotionEvidenceSourceKind.GOVERNED_ARTIFACT
                or latest.source_ref != f"oos-bundle:sha256:{bundle.bundle_sha256}"
            ):
                blockers.append("PROMOTION_EVIDENCE_INCOMPLETE")
        else:
            blockers.append("PROMOTION_EVIDENCE_INCOMPLETE")
        unique = tuple(sorted({*hard, *blockers}))
        status = (
            "OOS_MATURITY_BLOCKED"
            if hard
            else "OOS_MATURITY_INCOMPLETE"
            if unique
            else "OOS_MATURITY_COMPLETE"
        )
        return OOSMaturityResult(
            status,
            None if subject is None else subject.subject_key,
            bundle.bundle_sha256,
            unique,
            tuple(stages),
        )

    def _bytes(self, reference: OOSArtifactReference) -> bytes:
        root = self.artifact_root.resolve()
        relative = Path(reference.path)
        path = (root / relative).resolve()
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or not path.is_relative_to(root)
        ):
            raise ValueError("EVIDENCE_PATH_OUTSIDE_ROOT")
        with path.open("rb") as stream:
            raw = stream.read(MAX_ARTIFACT_BYTES + 1)
        if len(raw) > MAX_ARTIFACT_BYTES:
            raise ValueError("EVIDENCE_SIZE_LIMIT_EXCEEDED")
        if sha256(raw).hexdigest() != reference.sha256:
            raise ValueError("EVIDENCE_HASH_MISMATCH")
        return raw

    def _read(self, reference: OOSArtifactReference) -> dict[str, object]:
        value = json.loads(self._bytes(reference))
        if not isinstance(value, dict):
            raise ValueError("EVIDENCE_OBJECT_REQUIRED")
        return cast(dict[str, object], value)

    @staticmethod
    def _identity(
        evidence: Mapping[str, object],
        subject: OOSValidationSubject,
        max_age: timedelta,
    ) -> None:
        if (
            evidence.get("execution_allowed") is not False
            or evidence.get("live_eligibility_status") != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("EVIDENCE_EXECUTION_AUTHORITY_FORBIDDEN")
        observed = _time(evidence.get("observed_at"))
        expires = _time(evidence.get("expires_at"))
        if (
            observed > subject.promotion.as_of
            or subject.promotion.as_of - observed > max_age
            or expires <= subject.promotion.as_of
            or expires <= observed
        ):
            raise ValueError("STALE_VALIDATION_EVIDENCE")

    @staticmethod
    def _measurement_types(values: Mapping[str, object]) -> None:
        for name in (
            "expectancy",
            "net_return",
            "max_drawdown",
            "confidence_interval_lower",
            "profit_factor",
            "profitable_fold_ratio",
            "edge_concentration",
            "unknown_ratio",
            "observation_days",
        ):
            if name not in values:
                continue
            try:
                number = Decimal(str(values[name]))
            except InvalidOperation as exc:
                raise ValueError("EVIDENCE_NUMERIC_MEASUREMENT_INVALID") from exc
            if isinstance(values[name], bool) or not number.is_finite():
                raise ValueError("EVIDENCE_NUMERIC_MEASUREMENT_INVALID")
        for name in (
            "trade_count",
            "fold_count",
            "regime_count",
            "hypothesis_count",
            "effective_sample_size",
            "missing_intervals",
            "duplicate_count",
            "purge",
            "embargo",
            "runtime_failures",
        ):
            if name in values and (
                type(values[name]) is not int or cast(int, values[name]) < 0
            ):
                raise ValueError("EVIDENCE_COUNT_INVALID")
        for name in ("trade_count", "effective_sample_size", "fold_count"):
            if name in values and values[name] == 0:
                raise ValueError("TRADE_OR_FOLD_SAMPLE_EMPTY")
        for name in ("train_only_selection", "repository_clean", "replay_equal"):
            if name in values and values[name] is not True:
                raise ValueError("VALIDATION_INVARIANT_NOT_PROVEN")

    def _holdout(
        self, evidence: Mapping[str, object], subject: OOSValidationSubject
    ) -> None:
        partitions = _object(evidence.get("partitions"))
        times = [
            _time(partitions.get(name))
            for name in (
                "development_start",
                "development_end",
                "walk_forward_start",
                "walk_forward_end",
                "holdout_start",
                "holdout_end",
            )
        ]
        if any(left >= right for left, right in pairwise(times)):
            raise ValueError("HOLDOUT_PARTITIONS_OVERLAP")
        frozen = _time(evidence.get("candidate_frozen_at"))
        first_access = _time(evidence.get("first_holdout_access_at"))
        if frozen >= first_access or first_access > subject.promotion.as_of:
            raise ValueError("HOLDOUT_NOT_FROZEN_BEFORE_ACCESS")
        history_ref = _object(evidence.get("holdout_history"))
        history = self._read(
            OOSArtifactReference(
                str(history_ref.get("path", "")), str(history_ref.get("sha256", ""))
            )
        )
        if (
            history.get("dataset_sha256") != subject.promotion.dataset_sha256
            or history.get("partitions") != partitions
        ):
            raise ValueError("HOLDOUT_HISTORY_IDENTITY_MISMATCH")
        accesses = history.get("accesses")
        if not isinstance(accesses, list) or not accesses:
            raise ValueError("HOLDOUT_ACCESS_HISTORY_MISSING")
        for access in accesses:
            item = _object(access)
            if (
                item.get("subject_key") != subject.subject_key
                or _time(item.get("accessed_at")) < first_access
            ):
                raise ValueError("HOLDOUT_CONTAMINATED")


def _required_text(payload: Mapping[str, object], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"OOS_FIELD_INVALID:{name}")
    return value


def _artifact_reference(value: object) -> OOSArtifactReference:
    payload = _object(value)
    return OOSArtifactReference(
        _required_text(payload, "path"), _required_text(payload, "sha256")
    )


def _research_only_payload(payload: Mapping[str, object]) -> None:
    if (
        payload.get("schema_version") != "1.0"
        or payload.get("execution_allowed") is not False
        or payload.get("live_eligibility_status") != "LIVE_ORDER_BLOCKED"
    ):
        raise ValueError("OOS_RUNTIME_AUTHORITY_INVALID")


def _object(value: object) -> dict[str, object]:
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def _at(value: object, pointer: list[object]) -> object:
    for part in pointer:
        if isinstance(value, dict) and isinstance(part, str):
            value = value.get(part)
        elif isinstance(value, list) and type(part) is int and 0 <= part < len(value):
            value = value[part]
        else:
            raise ValueError("MEASUREMENT_SOURCE_POINTER_INVALID")
    return value


def _time(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("EVIDENCE_TIMESTAMP_MISSING")
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("EVIDENCE_TIMESTAMP_NOT_AWARE")
    return result


def _matches(value: object, rule: Mapping[str, object]) -> bool:
    if value is None or value == "DATA_UNAVAILABLE":
        return False
    operator, expected = rule.get("operator"), rule.get("value")
    if isinstance(value, float) and not isfinite(value):
        return False
    if isinstance(expected, float) and not isfinite(expected):
        return False
    if operator == "eq":
        return type(value) is type(expected) and value == expected
    if operator == "in":
        return isinstance(expected, list) and any(
            type(value) is type(item) and value == item for item in expected
        )
    if isinstance(value, bool) or isinstance(expected, bool):
        return False
    try:
        actual, threshold = Decimal(str(value)), Decimal(str(expected))
    except InvalidOperation:
        return False
    if not actual.is_finite() or not threshold.is_finite():
        return False
    if operator == "gte":
        return actual >= threshold
    if operator == "gt":
        return actual > threshold
    if operator == "lte":
        return actual <= threshold
    return False
