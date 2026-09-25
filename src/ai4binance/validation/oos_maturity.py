"""Exact-bound aggregation of immutable validation evidence, never trade authority.

Producers retain ownership of calculations. A governed specification supplies
every numerical threshold; this module verifies artifacts and combines vetoes.
Missing specifications, holdout history or forward observations cannot be
replaced by a summary or by a high aggregate score.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from itertools import pairwise
from math import isfinite
from pathlib import Path
from typing import cast

import yaml

from ai4binance.infrastructure.persistence.safe_json import (
    write_json_object_verified,
)
from ai4binance.storage import read_bounded_jsonl_tail
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


def load_spot_oos_validation_specification(path: Path) -> dict[str, object]:
    """Load the active Spot threshold template without granting promotion."""

    if (
        not path.is_file()
        or path.is_symlink()
        or path.stat().st_size > MAX_ARTIFACT_BYTES
    ):
        raise ValueError("SPOT_OOS_SPECIFICATION_INVALID")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    root = _object(payload)
    specification = _object(root.get("spot_oos_validation_specification"))
    authority = _object(specification.get("authority"))
    timeframes = specification.get("timeframes")
    requirements = _object(specification.get("requirements"))
    if (
        specification.get("schema_version") != "1.0"
        or specification.get("status") != "ACTIVE"
        or specification.get("approval_status") != "PENDING_INDEPENDENT_REVIEW"
        or not _required_text(specification, "specification_id")
        or not _required_text(specification, "owner")
        or specification.get("market_scope") != ["SPOT"]
        or timeframes != ["15m", "1h", "4h"]
        or authority.get("execution_allowed") is not False
        or authority.get("promotion_status") != "RESEARCH_ONLY"
        or authority.get("live_eligibility_status") != "LIVE_ORDER_BLOCKED"
    ):
        raise ValueError("SPOT_OOS_SPECIFICATION_INVALID")
    if set(requirements) != set(REQUIRED_MEASUREMENTS):
        raise ValueError("SPOT_OOS_REQUIREMENTS_INVALID")
    for stage, required in REQUIRED_MEASUREMENTS.items():
        rules = _object(requirements.get(stage))
        if not {"blockers", *required}.issubset(rules):
            raise ValueError(f"SPOT_OOS_REQUIREMENTS_INVALID:{stage}")
        for rule in rules.values():
            rule_value = _object(rule)
            if (
                rule_value.get("operator")
                not in {
                    "eq",
                    "in",
                    "gte",
                    "gt",
                    "lte",
                    "lt",
                    "present",
                }
                or "value" not in rule_value
            ):
                raise ValueError(f"SPOT_OOS_REQUIREMENTS_INVALID:{stage}")
    return specification


def prepare_spot_oos_deployment(
    *,
    artifact_root: Path,
    deployment_path: Path,
    specification_path: Path,
    run_cards: Sequence[Mapping[str, object]],
    observed_at: datetime,
) -> dict[str, object]:
    """Materialize exact research-only Spot subjects from validation run cards.

    This starts the evidence chain and removes an ambiguous missing-deployment
    failure. It deliberately creates no stage evidence and no promotion review.
    """

    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("SPOT_OOS_OBSERVED_AT_INVALID")
    if not 1 <= len(run_cards) <= 256:
        raise ValueError("SPOT_OOS_RUN_CARD_INVENTORY_INVALID")
    template = load_spot_oos_validation_specification(specification_path)
    runtime_sha256 = runtime_source_sha256()
    strategy_version = _required_text(template, "strategy_version")
    allowed_timeframes = cast(list[object], template["timeframes"])
    artifact_root.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, object]] = []
    subject_keys: set[str] = set()
    for card in run_cards:
        if (
            card.get("execution_allowed") is not False
            or card.get("promotion_status") != "RESEARCH_ONLY"
        ):
            raise ValueError("SPOT_OOS_RUN_CARD_AUTHORITY_INVALID")
        hypothesis_id = _required_text(card, "hypothesis_id")
        hypothesis_parts = hypothesis_id.split(":")
        if len(hypothesis_parts) != 3 or hypothesis_parts[0] != "hyp":
            raise ValueError("SPOT_OOS_HYPOTHESIS_ID_INVALID")
        setup_type = hypothesis_parts[1]
        timeframe = _required_text(card, "timeframe")
        if hypothesis_parts[2] != timeframe or timeframe not in allowed_timeframes:
            raise ValueError("SPOT_OOS_TIMEFRAME_INVALID")
        strategy_sha256 = _required_hash(card, "strategy_sha256")
        parameter_set_sha256 = _required_hash(card, "config_sha256")
        dataset_sha256 = _required_hash(card, "dataset_sha256")
        cost_payload = {
            "fee_rate": card.get("fee_rate"),
            "slippage_rate": card.get("slippage_rate"),
            "market_type": "SPOT",
        }
        cost_model_sha256 = sha256(
            json.dumps(
                cost_payload,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        ).hexdigest()
        query = PromotionEvidenceQuery(
            strategy_id=setup_type,
            strategy_version=strategy_version,
            strategy_sha256=strategy_sha256,
            symbol=_required_text(card, "symbol").upper(),
            market_type="SPOT",
            timeframe=timeframe,
            parameter_set_sha256=parameter_set_sha256,
            dataset_sha256=dataset_sha256,
            # Historical exploratory cards may carry WORKTREE_UNVERIFIED. The
            # deployment identity instead binds the exact installed source
            # digest; it never relabels that card as clean or approved.
            code_revision=runtime_sha256,
            as_of=observed_at,
        )
        subject_directory = sha256(
            json.dumps(query.subject_key, separators=(",", ":")).encode()
        ).hexdigest()
        exact_root = artifact_root / "oos_runtime" / subject_directory
        specification_payload: dict[str, object] = {
            "schema_version": "1.0",
            "specification_id": template["specification_id"],
            "status": "ACTIVE",
            "owner": template["owner"],
            "approval_status": template["approval_status"],
            "scope": list(query.subject_key[:6]),
            "requirements": _replace_specification_placeholders(
                template["requirements"],
                cost_model_sha256=cost_model_sha256,
                runtime_sha256=runtime_sha256,
            ),
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
        specification_file = exact_root / "specification.json"
        write_json_object_verified(
            specification_file,
            specification_payload,
            blocker="SPOT_OOS_SPECIFICATION_WRITE_FAILED",
            subject_id=subject_directory,
            indent=2,
            durable=True,
        )
        specification_reference = OOSArtifactReference(
            specification_file.relative_to(artifact_root).as_posix(),
            sha256(specification_file.read_bytes()).hexdigest(),
        )
        subject = OOSValidationSubject(
            promotion=query,
            setup_type=setup_type,
            feature_definition_sha256=strategy_sha256,
            cost_model_sha256=cost_model_sha256,
            validation_config_sha256=specification_reference.sha256,
        )
        if subject.subject_key in subject_keys:
            raise ValueError("SPOT_OOS_DUPLICATE_SUBJECT")
        subject_keys.add(subject.subject_key)
        available_artifacts = _materialize_available_validation_evidence(
            artifact_root=artifact_root,
            exact_root=exact_root,
            subject=subject,
            run_card=card,
            observed_at=observed_at,
        )
        bundle_payload: dict[str, object] = {
            "schema_version": "1.0",
            "subject": _subject_payload(subject),
            "artifacts": {
                name: _reference_payload(reference)
                for name, reference in available_artifacts
            },
            "specification": _reference_payload(specification_reference),
            "promotion_records": [],
            "blockers": ["EVIDENCE_COLLECTION_IN_PROGRESS"],
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
        bundle_file = exact_root / "bundle.json"
        write_json_object_verified(
            bundle_file,
            bundle_payload,
            blocker="SPOT_OOS_BUNDLE_WRITE_FAILED",
            subject_id=subject.subject_key,
            indent=2,
            durable=True,
        )
        bundle_reference = OOSArtifactReference(
            bundle_file.relative_to(artifact_root).as_posix(),
            sha256(bundle_file.read_bytes()).hexdigest(),
        )
        entries.append(
            {
                "subject": _subject_payload(subject),
                "bundle": _reference_payload(bundle_reference),
            }
        )
    deployment: dict[str, object] = {
        "schema_version": "1.0",
        "runtime_source_sha256": runtime_sha256,
        "subjects": entries,
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    write_json_object_verified(
        deployment_path,
        deployment,
        blocker="SPOT_OOS_DEPLOYMENT_WRITE_FAILED",
        subject_id="spot-oos-runtime-deployment",
        indent=2,
        durable=True,
    )
    return {
        "status": "EVIDENCE_COLLECTION_IN_PROGRESS",
        "subject_count": len(entries),
        "deployment_path": str(deployment_path),
        "runtime_source_sha256": runtime_sha256,
        "blockers": [
            "VALIDATION_STAGE_EVIDENCE_INCOMPLETE",
            "PROMOTION_EVIDENCE_INCOMPLETE",
            "INDEPENDENT_REVIEW_REQUIRED",
        ],
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


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


def _required_hash(payload: Mapping[str, object], name: str) -> str:
    value = _required_text(payload, name)
    if not _HASH.fullmatch(value):
        raise ValueError(f"OOS_FIELD_HASH_INVALID:{name}")
    return value


def _reference_payload(reference: OOSArtifactReference) -> dict[str, str]:
    return {"path": reference.path, "sha256": reference.sha256}


def _subject_payload(subject: OOSValidationSubject) -> dict[str, object]:
    query = subject.promotion
    return {
        "promotion": {
            "strategy_id": query.strategy_id,
            "strategy_version": query.strategy_version,
            "strategy_sha256": query.strategy_sha256,
            "symbol": query.symbol,
            "market_type": query.market_type,
            "timeframe": query.timeframe,
            "parameter_set_sha256": query.parameter_set_sha256,
            "dataset_sha256": query.dataset_sha256,
            "code_revision": query.code_revision,
        },
        "setup_type": subject.setup_type,
        "feature_definition_sha256": subject.feature_definition_sha256,
        "cost_model_sha256": subject.cost_model_sha256,
        "validation_config_sha256": subject.validation_config_sha256,
    }


def _materialize_available_validation_evidence(
    *,
    artifact_root: Path,
    exact_root: Path,
    subject: OOSValidationSubject,
    run_card: Mapping[str, object],
    observed_at: datetime,
) -> tuple[tuple[str, OOSArtifactReference], ...]:
    """Bind producer-owned validation outputs without inventing missing stages."""

    events, origin = _validation_events(run_card, artifact_root)
    backtest = events.get("BACKTEST_RESULT")
    walk_forward = events.get("WALK_FORWARD_REPORT")
    tuning = events.get("TUNING_REPORT")
    robustness = events.get("BACKTEST_ROBUSTNESS_REPORT")
    if origin is None:
        return ()
    stages: list[tuple[str, dict[str, object], list[str]]] = []
    if backtest is not None:
        assumptions = _object(backtest.get("assumptions"))
        stages.append(
            (
                "backtest",
                {
                    "blockers": [],
                    "realism_status": "PASS",
                    "cost_model_sha256": subject.cost_model_sha256,
                    "execution_model_version": "SPOT_BACKTEST_V1",
                },
                (
                    []
                    if assumptions.get("fee_ratio") is not None
                    and assumptions.get("slippage_ratio") is not None
                    else ["BACKTEST_COST_ASSUMPTIONS_MISSING"]
                ),
            )
        )
    if walk_forward is not None:
        config = _object(walk_forward.get("config"))
        wf_blockers = _string_list(walk_forward.get("blockers"))
        folds = walk_forward.get("folds")
        stages.append(
            (
                "walk_forward",
                {
                    "blockers": wf_blockers,
                    "fold_count": len(folds) if isinstance(folds, list) else 0,
                    "train_only_selection": True,
                    "purge": _nonnegative_int(config.get("purge_size")),
                    "embargo": _nonnegative_int(config.get("embargo_size")),
                },
                wf_blockers,
            )
        )
        regimes = walk_forward.get("regime_performance")
        regime_rows = regimes if isinstance(regimes, list) else []
        regime_names = {
            str(_object(row).get("regime", "UNKNOWN")) for row in regime_rows
        }
        total_regime_trades = sum(
            _nonnegative_int(_object(row).get("trade_count")) for row in regime_rows
        )
        unknown_trades = sum(
            _nonnegative_int(_object(row).get("trade_count"))
            for row in regime_rows
            if _object(row).get("regime") == "UNKNOWN"
        )
        regime_blockers = (
            []
            if regime_rows and total_regime_trades > 0
            else ["REGIME_ATTRIBUTION_INCOMPLETE"]
        )
        stages.append(
            (
                "regime",
                {
                    "blockers": regime_blockers,
                    "regime_count": len(regime_names - {"UNKNOWN"}),
                    "unknown_ratio": (
                        unknown_trades / total_regime_trades
                        if total_regime_trades
                        else 1.0
                    ),
                    "attribution_status": (
                        "PASS" if not regime_blockers else "INCOMPLETE"
                    ),
                },
                regime_blockers,
            )
        )
        statistical = _object(walk_forward.get("statistical_evidence"))
        confidence = statistical.get("confidence_interval")
        confidence_lower = (
            confidence[0]
            if isinstance(confidence, list) and len(confidence) == 2
            else 0.0
        )
        wf_robustness = _object(walk_forward.get("robustness"))
        backtest_metrics = _object(backtest.get("metrics")) if backtest else {}
        statistical_blockers = _string_list(statistical.get("blockers"))
        stages.append(
            (
                "statistics",
                {
                    "blockers": statistical_blockers,
                    "effective_sample_size": _nonnegative_int(
                        statistical.get("effective_sample_size")
                    ),
                    "confidence_interval_lower": confidence_lower,
                    "profit_factor": backtest_metrics.get("profit_factor") or 0.0,
                    "profitable_fold_ratio": wf_robustness.get(
                        "profitable_fold_ratio", 0.0
                    ),
                    "hypothesis_count": _nonnegative_int(
                        statistical.get("hypothesis_count")
                    ),
                    "multiple_testing_method": statistical.get(
                        "correction", "UNAVAILABLE"
                    ),
                    "confirmatory": statistical.get("confirmatory") is True,
                },
                statistical_blockers,
            )
        )
    if walk_forward is not None and tuning is not None and robustness is not None:
        wf_robustness = _object(walk_forward.get("robustness"))
        sensitivity = _object(tuning.get("sensitivity"))
        robustness_blockers = list(
            dict.fromkeys(
                (
                    *_string_list(wf_robustness.get("blockers")),
                    *_string_list(sensitivity.get("blockers")),
                    *_string_list(robustness.get("blockers")),
                    "CPCV_EVIDENCE_MISSING",
                )
            )
        )
        stages.append(
            (
                "robustness",
                {
                    "blockers": robustness_blockers,
                    "parameter_stability": (
                        "PASS"
                        if not _string_list(sensitivity.get("blockers"))
                        else "FAIL"
                    ),
                    "fold_stability": (
                        "PASS"
                        if "WEAK_OOS_FOLD_CONSISTENCY" not in robustness_blockers
                        else "FAIL"
                    ),
                    "regime_stability": (
                        "PASS"
                        if _nonnegative_int(wf_robustness.get("regime_count")) >= 3
                        else "FAIL"
                    ),
                    "cpcv_status": "NOT_AVAILABLE",
                    "monte_carlo_status": (
                        "PASS"
                        if not any(
                            blocker.startswith("BOOTSTRAP_")
                            for blocker in robustness_blockers
                        )
                        else "FAIL"
                    ),
                    "selection_overfit_status": (
                        "PASS" if not _string_list(tuning.get("blockers")) else "FAIL"
                    ),
                    "edge_concentration": wf_robustness.get("edge_concentration", 1.0),
                    "failure_modes_status": (
                        "PASS"
                        if not _string_list(robustness.get("blockers"))
                        else "FAIL"
                    ),
                },
                robustness_blockers,
            )
        )
        stress = robustness.get("stress_results")
        stress_rows = stress if isinstance(stress, list) else []
        cost_blockers = _string_list(robustness.get("blockers"))
        stages.append(
            (
                "cost_stress",
                {
                    "blockers": cost_blockers,
                    "scenario_coverage": [
                        str(_object(_object(row).get("scenario")).get("name"))
                        for row in stress_rows
                    ],
                    "edge_survival": bool(stress_rows)
                    and all(
                        _finite_float(_object(row).get("net_return")) > 0
                        and _finite_float(_object(row).get("expectancy_usdt")) > 0
                        for row in stress_rows
                    ),
                },
                cost_blockers,
            )
        )
    return tuple(
        (
            stage,
            _write_stage_evidence(
                artifact_root=artifact_root,
                exact_root=exact_root,
                subject=subject,
                stage=stage,
                measurements=measurements,
                blockers=blockers,
                observed_at=observed_at,
                origin=origin,
            ),
        )
        for stage, measurements, blockers in stages
    )


def _validation_events(
    run_card: Mapping[str, object], artifact_root: Path
) -> tuple[dict[str, dict[str, object]], OOSArtifactReference | None]:
    raw_references = run_card.get("artifact_sha256")
    if not isinstance(raw_references, (list, tuple)) or not raw_references:
        return {}, None
    first = raw_references[0]
    if not isinstance(first, (list, tuple)) or len(first) != 2:
        return {}, None
    path = Path(str(first[0]))
    resolved = path.resolve() if path.is_absolute() else (Path.cwd() / path).resolve()
    root = artifact_root.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("SPOT_OOS_SOURCE_OUTSIDE_ARTIFACT_ROOT") from exc
    digest = _stream_sha256(resolved)
    if digest != str(first[1]):
        raise ValueError("SPOT_OOS_SOURCE_HASH_INVALID")
    try:
        raw_events = read_bounded_jsonl_tail(
            resolved,
            max_lines=4,
            max_bytes=MAX_ARTIFACT_BYTES,
        )
    except (OSError, ValueError) as exc:
        raise ValueError("SPOT_OOS_SOURCE_EVENTS_INVALID") from exc
    events: dict[str, dict[str, object]] = {}
    try:
        for line in raw_events:
            row = _object(json.loads(line))
            event_type = _required_text(row, "event_type")
            payload = _object(row.get("payload"))
            value = next(iter(payload.values()), None)
            events[event_type] = _object(value)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("SPOT_OOS_SOURCE_EVENTS_INVALID") from exc
    return events, OOSArtifactReference(relative.as_posix(), digest)


def _stream_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _write_stage_evidence(
    *,
    artifact_root: Path,
    exact_root: Path,
    subject: OOSValidationSubject,
    stage: str,
    measurements: dict[str, object],
    blockers: list[str],
    observed_at: datetime,
    origin: OOSArtifactReference,
) -> OOSArtifactReference:
    source_payload = {
        "subject_key": subject.subject_key,
        **measurements,
        "origin_artifact": _reference_payload(origin),
    }
    source_path = exact_root / f"{stage}.source.json"
    write_json_object_verified(
        source_path,
        source_payload,
        blocker="SPOT_OOS_STAGE_SOURCE_WRITE_FAILED",
        subject_id=f"{subject.subject_key}:{stage}:source",
        indent=2,
        durable=True,
    )
    source_reference = OOSArtifactReference(
        source_path.relative_to(artifact_root).as_posix(),
        sha256(source_path.read_bytes()).hexdigest(),
    )
    evidence_payload = {
        "subject_key": subject.subject_key,
        "stage": stage,
        "measurements": measurements,
        "observed_at": observed_at.isoformat(),
        "expires_at": (observed_at + timedelta(days=30)).isoformat(),
        "blockers": blockers,
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        "source_artifacts": [_reference_payload(source_reference)],
        "measurement_sources": {
            name: {"source_index": 0, "pointer": [name]} for name in measurements
        },
    }
    evidence_path = exact_root / f"{stage}.json"
    write_json_object_verified(
        evidence_path,
        evidence_payload,
        blocker="SPOT_OOS_STAGE_EVIDENCE_WRITE_FAILED",
        subject_id=f"{subject.subject_key}:{stage}",
        indent=2,
        durable=True,
    )
    return OOSArtifactReference(
        evidence_path.relative_to(artifact_root).as_posix(),
        sha256(evidence_path.read_bytes()).hexdigest(),
    )


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        return []
    return list(value)


def _nonnegative_int(value: object) -> int:
    return value if type(value) is int and value >= 0 else 0


def _finite_float(value: object) -> float:
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return 0.0
    return float(number) if number.is_finite() else 0.0


def _replace_specification_placeholders(
    value: object, *, cost_model_sha256: str, runtime_sha256: str
) -> object:
    if isinstance(value, dict):
        return {
            str(key): _replace_specification_placeholders(
                item,
                cost_model_sha256=cost_model_sha256,
                runtime_sha256=runtime_sha256,
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _replace_specification_placeholders(
                item,
                cost_model_sha256=cost_model_sha256,
                runtime_sha256=runtime_sha256,
            )
            for item in value
        ]
    if value == "$COST_MODEL_SHA256":
        return cost_model_sha256
    if value == "$RUNTIME_SOURCE_SHA256":
        return runtime_sha256
    return value


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
    if operator == "present":
        return expected is True and value not in (None, "", [], {})
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
