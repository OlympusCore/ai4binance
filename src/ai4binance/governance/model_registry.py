"""Fail-closed reader and validator for the canonical model registry."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
from pathlib import Path

_MODEL_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_MODEL_FAMILIES = frozenset(
    {
        "LLM",
        "SCENARIO_MODEL",
        "STATISTICAL_MODEL",
        "TABULAR_ML_MODEL",
        "REGIME_MODEL",
        "ANOMALY_MODEL",
        "TIME_SERIES_MODEL",
        "TIME_SERIES_FOUNDATION_MODEL",
        "EMBEDDING_MODEL",
        "RERANKER_MODEL",
        "EVALUATOR_MODEL",
        "ENSEMBLE_MODEL",
        "META_MODEL",
    }
)
_LIFECYCLE_STATUSES = frozenset(
    {"OBSERVED_UNVERIFIED", "RESEARCH_ONLY", "OOS_VALIDATED"}
)
_ARTIFACT_TYPES = frozenset({"LOCAL_MODEL_MANIFEST", "SOURCE_CONTRACT"})
_ADVISORY_TASK_FAMILIES = {
    "ADVISORY_RESEARCH_SYNTHESIS": frozenset({"LLM"}),
    "READ_ONLY_LOCAL_WORKBENCH": frozenset({"LLM"}),
    "LOCAL_IMAGE_ADVISORY_ANALYSIS": frozenset({"LLM"}),
}
_REGISTRY_FENCE = re.compile(
    r"```json model-registry\s*\n(?P<payload>.*?)\n```", re.DOTALL
)


@dataclass(frozen=True, slots=True)
class ModelDefinition:
    model_id: str
    name: str
    model_family: str
    provider: str
    owner: str
    intended_use: tuple[str, ...]
    prohibited_use: tuple[str, ...]
    authority_ceiling: str
    decision_authority: bool
    risk_override: bool
    strategy_promotion: bool
    execution_authority: bool
    live_order_authority: bool

    def __post_init__(self) -> None:
        if not _MODEL_ID.fullmatch(self.model_id):
            raise ValueError("model definition model_id is invalid")
        if self.model_family not in _MODEL_FAMILIES:
            raise ValueError("model definition family is invalid")
        if not all(
            value.strip()
            for value in (self.name, self.provider, self.owner, self.authority_ceiling)
        ):
            raise ValueError("model definition identity is required")
        if not self.intended_use or not self.prohibited_use:
            raise ValueError("model definition use boundaries are required")
        if self.authority_ceiling != "ADVISORY_ONLY":
            raise ValueError("model definition authority ceiling must be advisory-only")
        if any(
            (
                self.decision_authority,
                self.risk_override,
                self.strategy_promotion,
                self.execution_authority,
                self.live_order_authority,
            )
        ):
            raise ValueError("model definition cannot grant authority")


@dataclass(frozen=True, slots=True)
class ModelVersion:
    model_id: str
    model_version: str
    lifecycle_status: str
    input_contract_version: str
    output_contract_version: str
    source_path: str

    def __post_init__(self) -> None:
        if not _MODEL_ID.fullmatch(self.model_id):
            raise ValueError("model version model_id is invalid")
        if not all(
            value.strip()
            for value in (
                self.model_version,
                self.input_contract_version,
                self.output_contract_version,
                self.source_path,
            )
        ):
            raise ValueError("model version identity is required")
        if self.lifecycle_status not in _LIFECYCLE_STATUSES:
            raise ValueError("model version lifecycle status is invalid")
        if Path(self.source_path).is_absolute() or not self.source_path.startswith(
            ("src/", "config/")
        ):
            raise ValueError("model version source path must be repository-relative")


@dataclass(frozen=True, slots=True)
class ModelArtifact:
    artifact_type: str
    artifact_uri: str
    artifact_sha256: str | None
    license_status: str
    rollback_binding: str

    def __post_init__(self) -> None:
        if self.artifact_type not in _ARTIFACT_TYPES:
            raise ValueError("model artifact type is invalid")
        if not self.artifact_uri.strip() or not self.rollback_binding.strip():
            raise ValueError("model artifact identity is required")
        if self.artifact_sha256 is not None and not _SHA256.fullmatch(
            self.artifact_sha256
        ):
            raise ValueError("model artifact hash is invalid")
        if self.license_status not in {"UNVERIFIED", "VERIFIED"}:
            raise ValueError("model artifact license status is invalid")


@dataclass(frozen=True, slots=True)
class ModelRegistryEntry:
    definition: ModelDefinition
    version: ModelVersion
    artifact: ModelArtifact

    def __post_init__(self) -> None:
        if self.definition.model_id != self.version.model_id:
            raise ValueError("model registry entry identity mismatch")
        if self.artifact.artifact_sha256 is None and (
            self.version.lifecycle_status != "OBSERVED_UNVERIFIED"
        ):
            raise ValueError("verified model lifecycle requires an artifact hash")


@dataclass(frozen=True, slots=True)
class ModelRegistryReport:
    entries: tuple[ModelRegistryEntry, ...]
    blockers: tuple[str, ...]
    status: str
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.entries:
            raise ValueError("model registry requires at least one entry")
        if self.status not in {"PASS", "RUNNING_WITH_BLOCKERS"}:
            raise ValueError("model registry status is invalid")
        if self.status == "PASS" and self.blockers:
            raise ValueError("passing model registry cannot contain blockers")
        if self.status == "RUNNING_WITH_BLOCKERS" and not self.blockers:
            raise ValueError("blocked model registry requires blockers")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("model registry cannot authorize execution or promotion")


@dataclass(frozen=True, slots=True)
class ModelRouteDecision:
    """Deterministic, non-authoritative route record for an advisory request."""

    canonical_model_id: str
    provider: str
    task_type: str
    model_family: str | None
    allowed: bool
    blockers: tuple[str, ...]
    route_sha256: str
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not _MODEL_ID.fullmatch(self.canonical_model_id):
            raise ValueError("model route model_id is invalid")
        if not all(value.strip() for value in (self.provider, self.task_type)):
            raise ValueError("model route identity is required")
        if self.model_family is not None and self.model_family not in _MODEL_FAMILIES:
            raise ValueError("model route family is invalid")
        if self.allowed and self.blockers:
            raise ValueError("allowed model route cannot contain blockers")
        if not self.allowed and not self.blockers:
            raise ValueError("blocked model route requires blockers")
        if not _SHA256.fullmatch(self.route_sha256):
            raise ValueError("model route hash is invalid")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("model route cannot authorize execution")


def build_model_route_decision(
    *,
    canonical_model_id: str,
    provider: str,
    task_type: str,
    model_family: str | None,
    allowed: bool,
    blockers: tuple[str, ...],
) -> ModelRouteDecision:
    """Build a deterministic route record without selecting or promoting a model."""

    payload = {
        "allowed": allowed,
        "blockers": blockers,
        "canonical_model_id": canonical_model_id,
        "model_family": model_family,
        "provider": provider,
        "task_type": task_type,
    }
    return ModelRouteDecision(
        canonical_model_id=canonical_model_id,
        provider=provider,
        task_type=task_type,
        model_family=model_family,
        allowed=allowed,
        blockers=blockers,
        route_sha256=_canonical_sha256(payload),
    )


@dataclass(frozen=True, slots=True)
class ModelGatewayDecision:
    """Fail-closed admission result for an advisory model invocation."""

    model_id: str
    provider: str
    allowed: bool
    blockers: tuple[str, ...]
    route_decision: ModelRouteDecision | None = None
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not _MODEL_ID.fullmatch(self.model_id):
            raise ValueError("model gateway model_id is invalid")
        if not self.provider.strip():
            raise ValueError("model gateway provider is required")
        if self.allowed and self.blockers:
            raise ValueError("admitted model invocation cannot contain blockers")
        if not self.allowed and not self.blockers:
            raise ValueError("blocked model invocation requires blockers")
        if self.route_decision is not None and (
            self.route_decision.canonical_model_id != self.model_id
            or self.route_decision.provider != self.provider
            or self.route_decision.allowed != self.allowed
            or self.route_decision.blockers != self.blockers
        ):
            raise ValueError("model gateway route decision mismatch")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("model gateway cannot authorize execution or promotion")


@dataclass(frozen=True, slots=True)
class ModelInferenceEnvelope:
    """Deterministic provenance attached to an advisory model output."""

    canonical_model_id: str
    model_version: str
    task_type: str
    input_snapshot_sha256: str
    provenance_sha256: str
    artifact_sha256: str | None = None
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not _MODEL_ID.fullmatch(self.canonical_model_id):
            raise ValueError("inference envelope model_id is invalid")
        if not all(value.strip() for value in (self.model_version, self.task_type)):
            raise ValueError("inference envelope identity is required")
        if not _SHA256.fullmatch(self.input_snapshot_sha256):
            raise ValueError("inference envelope input snapshot hash is invalid")
        if not _SHA256.fullmatch(self.provenance_sha256):
            raise ValueError("inference envelope provenance hash is invalid")
        if self.artifact_sha256 is not None and not _SHA256.fullmatch(
            self.artifact_sha256
        ):
            raise ValueError("inference envelope artifact hash is invalid")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("inference envelope cannot authorize execution")


def build_advisory_inference_envelope(
    *,
    canonical_model_id: str,
    model_version: str,
    task_type: str,
    prompt_sha256: str,
    source_content_sha256: tuple[str, ...],
    artifact_sha256: str | None = None,
) -> ModelInferenceEnvelope:
    """Build a deterministic advisory provenance envelope without raw inputs."""

    if not _SHA256.fullmatch(prompt_sha256):
        raise ValueError("inference envelope prompt hash is invalid")
    if any(not _SHA256.fullmatch(value) for value in source_content_sha256):
        raise ValueError("inference envelope source hash is invalid")
    snapshot_payload = {
        "prompt_sha256": prompt_sha256,
        "source_content_sha256": sorted(source_content_sha256),
    }
    input_snapshot_sha256 = _canonical_sha256(snapshot_payload)
    provenance_payload = {
        "artifact_sha256": artifact_sha256,
        "canonical_model_id": canonical_model_id,
        "input_snapshot_sha256": input_snapshot_sha256,
        "model_version": model_version,
        "task_type": task_type,
    }
    return ModelInferenceEnvelope(
        canonical_model_id=canonical_model_id,
        model_version=model_version,
        task_type=task_type,
        input_snapshot_sha256=input_snapshot_sha256,
        provenance_sha256=_canonical_sha256(provenance_payload),
        artifact_sha256=artifact_sha256,
    )


@dataclass(frozen=True, slots=True)
class ModelGateway:
    """Single fail-closed admission surface for advisory model providers."""

    repository_root: Path | None = None
    registry_path: Path | None = None

    def admit_advisory(
        self,
        model_id: str,
        provider: str,
        runtime_model: str,
        task: str = "ADVISORY_RESEARCH_SYNTHESIS",
    ) -> ModelGatewayDecision:
        root = self.repository_root or default_model_registry_path().parents[2]
        return admit_advisory_model_invocation(
            root,
            model_id,
            provider,
            runtime_model,
            self.registry_path,
            task,
        )


def default_model_registry_path(repository_root: Path | None = None) -> Path:
    root = repository_root or Path(__file__).resolve().parents[3]
    return root / "docs" / "registries" / "registry_model_registry.md"


def load_model_registry(path: Path | None = None) -> tuple[ModelRegistryEntry, ...]:
    document = (path or default_model_registry_path()).resolve()
    match = _REGISTRY_FENCE.search(document.read_text(encoding="utf-8"))
    if match is None:
        raise ValueError("model registry canonical JSON block is missing")
    try:
        payload = json.loads(match.group("payload"))
    except json.JSONDecodeError as error:
        raise ValueError("model registry canonical JSON is invalid") from error
    registry = _mapping(payload, "model registry")
    _require_keys(registry, {"schema_version", "entries"}, "model registry")
    if registry["schema_version"] != "1.0.0":
        raise ValueError("model registry schema version is unsupported")
    raw_entries = registry["entries"]
    if not isinstance(raw_entries, list) or not raw_entries:
        raise ValueError("model registry entries are required")
    entries = tuple(_entry(item) for item in raw_entries)
    identifiers = tuple(entry.definition.model_id for entry in entries)
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("model registry model identifiers must be unique")
    return entries


def validate_model_registry(
    repository_root: Path,
    path: Path | None = None,
) -> ModelRegistryReport:
    entries = load_model_registry(path or default_model_registry_path(repository_root))
    blockers: list[str] = []
    root = repository_root.resolve()
    for entry in entries:
        model_id = entry.definition.model_id
        if entry.version.lifecycle_status == "OBSERVED_UNVERIFIED":
            blockers.append(f"MODEL_OBSERVED_UNVERIFIED:{model_id}")
        if entry.artifact.artifact_sha256 is None:
            blockers.append(f"ARTIFACT_HASH_UNVERIFIED:{model_id}")
        if entry.artifact.license_status != "VERIFIED":
            blockers.append(f"LICENSE_UNVERIFIED:{model_id}")
        if entry.artifact.artifact_sha256 is None:
            continue
        source = (root / entry.artifact.artifact_uri).resolve()
        try:
            source.relative_to(root)
        except ValueError:
            blockers.append(f"ARTIFACT_URI_OUTSIDE_REPOSITORY:{model_id}")
            continue
        if not source.is_file():
            blockers.append(f"ARTIFACT_MISSING:{model_id}")
            continue
        actual_hash = _sha256_file(source)
        if actual_hash != entry.artifact.artifact_sha256:
            blockers.append(f"ARTIFACT_HASH_MISMATCH:{model_id}")
            continue
        if entry.artifact.artifact_type == "LOCAL_MODEL_MANIFEST":
            blockers.extend(_local_model_manifest_blockers(root, model_id, source))
    unique_blockers = tuple(dict.fromkeys(blockers))
    return ModelRegistryReport(
        entries=entries,
        blockers=unique_blockers,
        status="RUNNING_WITH_BLOCKERS" if unique_blockers else "PASS",
    )


def _local_model_manifest_blockers(
    repository_root: Path,
    model_id: str,
    manifest_path: Path,
) -> tuple[str, ...]:
    """Validate a local GGUF manifest without persisting machine paths."""

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = _mapping(payload, "local model manifest")
        _require_keys(
            manifest,
            {
                "schema_version",
                "model_id",
                "provider",
                "model_version",
                "runtime_boundary",
                "artifacts",
            },
            "local model manifest",
        )
        if manifest["schema_version"] != "1.0.0":
            raise ValueError("local model manifest schema version is unsupported")
        if manifest["model_id"] != model_id:
            raise ValueError("local model manifest model identity mismatch")
        artifacts = manifest["artifacts"]
        if not isinstance(artifacts, list) or not artifacts:
            raise ValueError("local model manifest artifacts are required")
    except (OSError, ValueError, json.JSONDecodeError):
        return (f"LOCAL_MODEL_MANIFEST_INVALID:{model_id}",)

    blockers: list[str] = []
    for item in artifacts:
        if not isinstance(item, Mapping):
            return (f"LOCAL_MODEL_MANIFEST_INVALID:{model_id}",)
        try:
            _require_keys(
                item,
                {"role", "path", "byte_length", "sha256"},
                "local model artifact",
            )
            artifact_path = _text(item["path"], "local model artifact path")
            expected_sha256 = _text(item["sha256"], "local model artifact sha256")
            expected_length = item["byte_length"]
            if (
                not _SHA256.fullmatch(expected_sha256)
                or not isinstance(expected_length, int)
                or expected_length < 1
                or Path(artifact_path).is_absolute()
                or not artifact_path.startswith("models/")
            ):
                raise ValueError("local model artifact contract is invalid")
            candidate = (repository_root / artifact_path).resolve()
            candidate.relative_to(repository_root)
        except (TypeError, ValueError):
            return (f"LOCAL_MODEL_MANIFEST_INVALID:{model_id}",)
        if not candidate.is_file():
            blockers.append(f"LOCAL_MODEL_ARTIFACT_MISSING:{model_id}:{item['role']}")
            continue
        if candidate.stat().st_size != expected_length:
            blockers.append(
                f"LOCAL_MODEL_ARTIFACT_SIZE_MISMATCH:{model_id}:{item['role']}"
            )
            continue
        if _sha256_file(candidate) != expected_sha256:
            blockers.append(
                f"LOCAL_MODEL_ARTIFACT_HASH_MISMATCH:{model_id}:{item['role']}"
            )
    return tuple(blockers)


def _sha256_file(path: Path) -> str:
    stat = path.stat()
    return _sha256_file_cached(str(path), stat.st_size, stat.st_mtime_ns)


@lru_cache(maxsize=64)
def _sha256_file_cached(path: str, byte_length: int, modified_at_ns: int) -> str:
    del byte_length, modified_at_ns
    digest = sha256()
    with Path(path).open("rb") as source:
        while chunk := source.read(1_048_576):
            digest.update(chunk)
    return digest.hexdigest()


def require_registered_model(
    model_id: str,
    entries: tuple[ModelRegistryEntry, ...],
) -> ModelRegistryEntry:
    for entry in entries:
        if entry.definition.model_id == model_id:
            return entry
    raise ValueError(f"UNREGISTERED_MODEL:{model_id}")


def admit_advisory_model_invocation(
    repository_root: Path,
    model_id: str,
    provider: str,
    runtime_model: str,
    path: Path | None = None,
    task: str = "ADVISORY_RESEARCH_SYNTHESIS",
) -> ModelGatewayDecision:
    """Require a registered, route-permitted, verified advisory model.

    This gateway produces an admission decision rather than raising into a
    runtime provider path. A registry parse or verification failure therefore
    prevents the network call while retaining deterministic evidence.
    """

    try:
        report = validate_model_registry(repository_root, path)
        entry = require_registered_model(model_id, report.entries)
    except (OSError, ValueError) as error:
        blocker = str(error)
        if not blocker.startswith("UNREGISTERED_MODEL:"):
            blocker = f"MODEL_REGISTRY_UNAVAILABLE:{model_id}"
        failure_blockers = (blocker,)
        return ModelGatewayDecision(
            model_id,
            provider,
            False,
            failure_blockers,
            build_model_route_decision(
                canonical_model_id=model_id,
                provider=provider,
                task_type=task,
                model_family=None,
                allowed=False,
                blockers=failure_blockers,
            ),
        )

    blockers: list[str] = []
    permitted_families = _ADVISORY_TASK_FAMILIES.get(task)
    if permitted_families is None:
        blockers.append(f"MODEL_TASK_UNSUPPORTED:{task}")
    elif entry.definition.model_family not in permitted_families:
        blockers.append(
            f"MODEL_TASK_FAMILY_NOT_PERMITTED:{task}:{entry.definition.model_family}"
        )
    elif task not in entry.definition.intended_use:
        blockers.append(f"MODEL_TASK_NOT_PERMITTED:{task}:{model_id}")
    if entry.definition.provider.casefold() != provider.casefold():
        blockers.append(f"MODEL_PROVIDER_MISMATCH:{model_id}:{provider}")
    if entry.version.model_version != runtime_model:
        blockers.append(f"MODEL_VERSION_MISMATCH:{model_id}:{runtime_model}")
    blockers.extend(
        blocker for blocker in report.blockers if blocker.endswith(f":{model_id}")
    )
    unique_blockers = tuple(dict.fromkeys(blockers))
    route = build_model_route_decision(
        canonical_model_id=model_id,
        provider=provider,
        task_type=task,
        model_family=entry.definition.model_family,
        allowed=not unique_blockers,
        blockers=unique_blockers,
    )
    return ModelGatewayDecision(
        model_id,
        provider,
        not unique_blockers,
        unique_blockers,
        route,
    )


def _entry(value: object) -> ModelRegistryEntry:
    payload = _mapping(value, "model registry entry")
    _require_keys(
        payload, {"definition", "version", "artifact"}, "model registry entry"
    )
    definition = _mapping(payload["definition"], "model definition")
    _require_keys(
        definition,
        {
            "model_id",
            "name",
            "model_family",
            "provider",
            "owner",
            "intended_use",
            "prohibited_use",
            "authority",
        },
        "model definition",
    )
    authority = _mapping(definition["authority"], "model authority")
    _require_keys(
        authority,
        {
            "authority_ceiling",
            "decision_authority",
            "risk_override",
            "strategy_promotion",
            "execution_authority",
            "live_order_authority",
        },
        "model authority",
    )
    version = _mapping(payload["version"], "model version")
    _require_keys(
        version,
        {
            "model_id",
            "model_version",
            "lifecycle_status",
            "input_contract_version",
            "output_contract_version",
            "source_path",
        },
        "model version",
    )
    artifact = _mapping(payload["artifact"], "model artifact")
    _require_keys(
        artifact,
        {
            "artifact_type",
            "artifact_uri",
            "artifact_sha256",
            "license_status",
            "rollback_binding",
        },
        "model artifact",
    )
    return ModelRegistryEntry(
        definition=ModelDefinition(
            model_id=_text(definition["model_id"], "model_id"),
            name=_text(definition["name"], "name"),
            model_family=_text(definition["model_family"], "model_family"),
            provider=_text(definition["provider"], "provider"),
            owner=_text(definition["owner"], "owner"),
            intended_use=_texts(definition["intended_use"], "intended_use"),
            prohibited_use=_texts(definition["prohibited_use"], "prohibited_use"),
            authority_ceiling=_text(
                authority["authority_ceiling"], "authority_ceiling"
            ),
            decision_authority=_bool(
                authority["decision_authority"], "decision_authority"
            ),
            risk_override=_bool(authority["risk_override"], "risk_override"),
            strategy_promotion=_bool(
                authority["strategy_promotion"], "strategy_promotion"
            ),
            execution_authority=_bool(
                authority["execution_authority"], "execution_authority"
            ),
            live_order_authority=_bool(
                authority["live_order_authority"], "live_order_authority"
            ),
        ),
        version=ModelVersion(
            model_id=_text(version["model_id"], "model_id"),
            model_version=_text(version["model_version"], "model_version"),
            lifecycle_status=_text(version["lifecycle_status"], "lifecycle_status"),
            input_contract_version=_text(
                version["input_contract_version"], "input_contract_version"
            ),
            output_contract_version=_text(
                version["output_contract_version"], "output_contract_version"
            ),
            source_path=_text(version["source_path"], "source_path"),
        ),
        artifact=ModelArtifact(
            artifact_type=_text(artifact["artifact_type"], "artifact_type"),
            artifact_uri=_text(artifact["artifact_uri"], "artifact_uri"),
            artifact_sha256=_optional_sha256(artifact["artifact_sha256"]),
            license_status=_text(artifact["license_status"], "license_status"),
            rollback_binding=_text(artifact["rollback_binding"], "rollback_binding"),
        ),
    )


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def _require_keys(value: Mapping[str, object], expected: set[str], name: str) -> None:
    if set(value) != expected:
        raise ValueError(
            f"{name} keys mismatch: missing={sorted(expected - set(value))}, "
            f"extra={sorted(set(value) - expected)}"
        )


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonblank text")
    return value


def _texts(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{name} must be a non-empty list")
    values = tuple(_text(item, name) for item in value)
    if len(values) != len(set(values)):
        raise ValueError(f"{name} entries must be unique")
    return values


def _bool(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be boolean")
    return value


def _optional_sha256(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError("artifact_sha256 must be a lowercase SHA-256 or null")
    return value


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()
