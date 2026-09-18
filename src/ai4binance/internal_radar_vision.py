"""Fail-closed local vision perception for internal-radar candidates.

The vision model is a sensor, never a decision maker.  It receives one local
image and may return only a deliberately small categorical evidence contract.
Raw image content, paths, filenames, OCR text, and free-form model prose are
never persisted or forwarded to the reasoning model.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Final, TypedDict

from ai4binance.governance.local_model_roles import (
    load_local_model_role,
    validate_role_runtime,
)
from ai4binance.governance.model_registry import (
    ModelGateway,
    ModelInferenceEnvelope,
    ModelRouteDecision,
    build_advisory_inference_envelope,
)

_MODEL_ID: Final = "local-llamacpp-qwen25vl-3b"
_MODEL_VERSION: Final = "Qwen2.5-VL-3B-Instruct-Q4_K_M"
_PROVIDER: Final = "llama.cpp"
_TASK: Final = "LOCAL_IMAGE_ADVISORY_ANALYSIS"
_MAX_IMAGE_BYTES: Final = 25 * 1024 * 1024
_MAX_RESPONSE_BYTES: Final = 64 * 1024
_CATEGORIES: Final = frozenset(
    {
        "MARKET_CHART",
        "DASHBOARD",
        "CODE_OR_ARCHITECTURE",
        "ARCHITECTURE_DIAGRAM",
        "EDUCATIONAL_INFOGRAPHIC",
        "DOCUMENT",
        "UI",
        "OTHER",
    }
)
_EVIDENCE_SCHEMA_VERSION: Final = "1.4"
_CONTRIBUTIONS: Final = frozenset(
    {"RELEVANT", "POTENTIALLY_RELEVANT", "NOT_RELEVANT", "INDETERMINATE"}
)
_BENEFITS: Final = frozenset(
    {
        "RESEARCH_CONTEXT",
        "OPERATIONAL_VISIBILITY",
        "DATA_QUALITY_SIGNAL",
        "ARCHITECTURE_CONTEXT",
        "NO_IDENTIFIED_BENEFIT",
    }
)
_TRADEOFFS: Final = frozenset(
    {
        "HUMAN_REVIEW_REQUIRED",
        "OCR_UNVERIFIED",
        "VISUAL_AMBIGUITY",
        "STALE_CONTEXT_POSSIBLE",
        "NO_IDENTIFIED_TRADEOFF",
    }
)
_UNCERTAINTIES: Final = frozenset(
    {
        "LOW_RESOLUTION",
        "PARTIAL_VIEW",
        "OCR_UNCERTAIN",
        "CONTEXT_MISSING",
        "NO_MATERIAL_UNCERTAINTY",
    }
)


class _Observation(TypedDict):
    image_category: str
    system_contribution: str
    benefit_categories: tuple[str, ...]
    tradeoff_categories: tuple[str, ...]
    extracted_text_present: bool
    uncertainty_categories: tuple[str, ...]
    confidence: float


@dataclass(frozen=True, slots=True)
class VisionEvidence:
    """Validated categorical evidence emitted by the local vision sensor."""

    candidate_id: str
    source_content_sha256: str
    status: str
    image_category: str | None
    system_contribution: str | None
    benefit_categories: tuple[str, ...]
    tradeoff_categories: tuple[str, ...]
    extracted_text_present: bool | None
    uncertainty_categories: tuple[str, ...]
    confidence: float | None
    blockers: tuple[str, ...]
    inference_envelope: ModelInferenceEnvelope
    route_decision: ModelRouteDecision | None
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("vision evidence cannot authorize execution or promotion")

    def to_payload(self) -> dict[str, object]:
        """Return persistent evidence without raw visual or textual content."""
        return {
            "schema_version": _EVIDENCE_SCHEMA_VERSION,
            "candidate_id": self.candidate_id,
            "source_content_sha256": self.source_content_sha256,
            "model_id": _MODEL_ID,
            "model_version": _MODEL_VERSION,
            "provider": _PROVIDER,
            "task_type": _TASK,
            "status": self.status,
            "image_category": self.image_category,
            "system_contribution": self.system_contribution,
            "benefit_categories": list(self.benefit_categories),
            "tradeoff_categories": list(self.tradeoff_categories),
            "extracted_text_present": self.extracted_text_present,
            "uncertainty_categories": list(self.uncertainty_categories),
            "confidence": self.confidence,
            "blockers": list(self.blockers),
            "inference_envelope": {
                "input_snapshot_sha256": self.inference_envelope.input_snapshot_sha256,
                "provenance_sha256": self.inference_envelope.provenance_sha256,
            },
            "route_allowed": (
                self.route_decision.allowed
                if self.route_decision is not None
                else False
            ),
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            "privacy": {
                "source_image_persisted": False,
                "source_path_persisted": False,
                "raw_ocr_text_persisted": False,
                "free_form_model_text_persisted": False,
            },
        }


@dataclass(frozen=True, slots=True)
class LlamaCppVisionRunner:
    """Loopback-only, schema-bounded vision adapter guarded by ModelGateway."""

    base_url: str = "http://127.0.0.1:8081"
    timeout_seconds: float = 60.0
    model_gateway: ModelGateway | None = None
    repository_root: Path | None = None

    def analyze(
        self,
        *,
        candidate_id: str,
        source_content_sha256: str,
        image_path: Path,
    ) -> VisionEvidence:
        """Return validated evidence or a deterministic blocker without fallback."""
        _validate_identity(candidate_id, source_content_sha256)
        envelope = build_advisory_inference_envelope(
            canonical_model_id=_MODEL_ID,
            model_version=_MODEL_VERSION,
            task_type=_TASK,
            prompt_sha256=sha256(_prompt().encode("utf-8")).hexdigest(),
            source_content_sha256=(source_content_sha256,),
        )
        parsed = urllib.parse.urlsplit(self.base_url.rstrip("/"))
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
            return _blocked_evidence(
                candidate_id,
                source_content_sha256,
                envelope,
                ("LOCAL_VISION_PROVIDER_NOT_LOOPBACK",),
            )
        root = self.repository_root or Path(__file__).resolve().parents[2]
        try:
            role = load_local_model_role(root, "VISION_PERCEPTION_AGENT")
            role_blockers = validate_role_runtime(
                role,
                model_id=_MODEL_ID,
                provider=_PROVIDER,
                runtime_model=_MODEL_VERSION,
                task=_TASK,
            )
        except ValueError:
            role_blockers = (
                "LOCAL_MODEL_ROLE_CONTRACT_UNAVAILABLE:VISION_PERCEPTION_AGENT",
            )
        if role_blockers:
            return _blocked_evidence(
                candidate_id,
                source_content_sha256,
                envelope,
                (*role_blockers, "ADVISORY_ONLY"),
            )
        gateway = self.model_gateway or ModelGateway()
        decision = gateway.admit_advisory(
            _MODEL_ID,
            _PROVIDER,
            _MODEL_VERSION,
            _TASK,
        )
        if not decision.allowed:
            return _blocked_evidence(
                candidate_id,
                source_content_sha256,
                envelope,
                (*decision.blockers, "ADVISORY_ONLY"),
                decision.route_decision,
            )
        try:
            image_bytes = image_path.read_bytes()
        except OSError:
            return _blocked_evidence(
                candidate_id,
                source_content_sha256,
                envelope,
                ("INTERNAL_IMAGE_READ_FAILED",),
                decision.route_decision,
            )
        if not image_bytes or len(image_bytes) > _MAX_IMAGE_BYTES:
            return _blocked_evidence(
                candidate_id,
                source_content_sha256,
                envelope,
                ("INTERNAL_IMAGE_SIZE_INVALID",),
                decision.route_decision,
            )
        request_payload = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _prompt()},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "data:image/unknown;base64,"
                                + base64.b64encode(image_bytes).decode("ascii")
                            },
                        },
                    ],
                }
            ],
            "temperature": 0,
            "max_tokens": 384,
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(  # noqa: S310 - guarded loopback URL.
            f"{parsed.geturl().rstrip('/')}/v1/chat/completions",
            data=json.dumps(request_payload, sort_keys=True).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(  # noqa: S310  # nosec B310
                request, timeout=self.timeout_seconds
            ) as response:
                response_payload = json.loads(response.read(_MAX_RESPONSE_BYTES))
        except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            return _blocked_evidence(
                candidate_id,
                source_content_sha256,
                envelope,
                ("LOCAL_VISION_PROVIDER_UNAVAILABLE", "ADVISORY_ONLY"),
                decision.route_decision,
            )
        try:
            content = _completion_content(response_payload)
            observation = _normalize_visual_only_observation(
                _validate_observation(_parse_json_object(content))
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            return _blocked_evidence(
                candidate_id,
                source_content_sha256,
                envelope,
                ("LOCAL_VISION_SCHEMA_INVALID", "ADVISORY_ONLY"),
                decision.route_decision,
            )
        return VisionEvidence(
            candidate_id,
            source_content_sha256,
            "OBSERVED_UNVERIFIED",
            observation["image_category"],
            observation["system_contribution"],
            observation["benefit_categories"],
            observation["tradeoff_categories"],
            observation["extracted_text_present"],
            observation["uncertainty_categories"],
            observation["confidence"],
            ("VISION_OBSERVATION_REQUIRES_HUMAN_REVIEW", "ADVISORY_ONLY"),
            envelope,
            decision.route_decision,
        )


def _prompt() -> str:
    return (
        "You are a local vision perception sensor for the AI4Binance research-only "
        "system. Return JSON only, with exactly "
        "these keys: image_category, system_contribution, benefit_categories, "
        "tradeoff_categories, extracted_text_present, uncertainty_categories, "
        "confidence. Never return image text, names, paths, prices, symbols, "
        "recommendations, trading instructions, free-form prose, or Markdown code "
        "fences. "
        "image_category must be one of MARKET_CHART,DASHBOARD,CODE_OR_ARCHITECTURE,"
        "ARCHITECTURE_DIAGRAM,EDUCATIONAL_INFOGRAPHIC,DOCUMENT,UI,OTHER. Use "
        "ARCHITECTURE_DIAGRAM for a component, data-flow, integration, or system "
        "topology diagram. Use EDUCATIONAL_INFOGRAPHIC for a conceptual learning "
        "map, poster, or general technology explainer. system_contribution must be "
        "one of RELEVANT,"
        "POTENTIALLY_RELEVANT,NOT_RELEVANT,INDETERMINATE. benefit_categories must "
        "contain only RESEARCH_CONTEXT,OPERATIONAL_VISIBILITY,DATA_QUALITY_SIGNAL,"
        "ARCHITECTURE_CONTEXT,NO_IDENTIFIED_BENEFIT. tradeoff_categories must contain "
        "only HUMAN_REVIEW_REQUIRED,OCR_UNVERIFIED,VISUAL_AMBIGUITY,"
        "STALE_CONTEXT_POSSIBLE,NO_IDENTIFIED_TRADEOFF. uncertainty_categories must "
        "contain only LOW_RESOLUTION,PARTIAL_VIEW,OCR_UNCERTAIN,CONTEXT_MISSING,"
        "NO_MATERIAL_UNCERTAINTY. Mark RELEVANT only when the visual itself "
        "directly identifies AI4Binance or an unambiguous system-specific component. "
        "Generic AI, MCP, vector-database, agent, or model-learning material is at "
        "most POTENTIALLY_RELEVANT; use INDETERMINATE when the system link cannot "
        "be established from the visual. confidence is a number from 0 to 1."
    )


def _validate_identity(candidate_id: str, source_content_sha256: str) -> None:
    if not candidate_id.strip() or len(source_content_sha256) != 64:
        raise ValueError("vision candidate identity is invalid")


def _blocked_evidence(
    candidate_id: str,
    source_content_sha256: str,
    envelope: ModelInferenceEnvelope,
    blockers: tuple[str, ...],
    route_decision: ModelRouteDecision | None = None,
) -> VisionEvidence:
    return VisionEvidence(
        candidate_id,
        source_content_sha256,
        "BLOCKED",
        None,
        None,
        (),
        (),
        None,
        (),
        None,
        tuple(dict.fromkeys(blockers)),
        envelope,
        route_decision,
    )


def _completion_content(payload: object) -> str:
    if not isinstance(payload, dict):
        raise ValueError("vision completion payload is invalid")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ValueError("vision completion choices are missing")
    message = choices[0].get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise ValueError("vision completion content is missing")
    return str(message["content"])


def _parse_json_object(content: str) -> object:
    """Accept an otherwise exact JSON object wrapped in one Markdown code fence."""
    normalized = content.strip()
    if normalized.startswith("```json\n") and normalized.endswith("\n```"):
        normalized = normalized.removeprefix("```json\n").removesuffix("\n```")
    return json.loads(normalized)


def _validate_observation(value: object) -> _Observation:
    if not isinstance(value, dict):
        raise ValueError("vision observation must be an object")
    expected = {
        "image_category",
        "system_contribution",
        "benefit_categories",
        "tradeoff_categories",
        "extracted_text_present",
        "uncertainty_categories",
        "confidence",
    }
    if set(value) != expected:
        raise ValueError("vision observation keys are invalid")
    image_category = value["image_category"]
    contribution = value["system_contribution"]
    if image_category not in _CATEGORIES or contribution not in _CONTRIBUTIONS:
        raise ValueError("vision observation category is invalid")
    benefits = _enum_list(value["benefit_categories"], _BENEFITS)
    tradeoffs = _enum_list(value["tradeoff_categories"], _TRADEOFFS)
    uncertainties = _enum_list(value["uncertainty_categories"], _UNCERTAINTIES)
    extracted = value["extracted_text_present"]
    confidence = value["confidence"]
    if not isinstance(extracted, bool):
        raise ValueError("vision extracted-text flag is invalid")
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        raise ValueError("vision confidence is invalid")
    if not 0 <= float(confidence) <= 1:
        raise ValueError("vision confidence is outside bounds")
    return {
        "image_category": image_category,
        "system_contribution": contribution,
        "benefit_categories": benefits,
        "tradeoff_categories": tradeoffs,
        "extracted_text_present": extracted,
        "uncertainty_categories": uncertainties,
        "confidence": float(confidence),
    }


def _normalize_visual_only_observation(observation: _Observation) -> _Observation:
    """Prevent an untrusted image-only model from asserting system-specific proof."""
    category = observation["image_category"]
    if category not in {"ARCHITECTURE_DIAGRAM", "EDUCATIONAL_INFOGRAPHIC"}:
        return observation
    expected_benefit = (
        "ARCHITECTURE_CONTEXT"
        if category == "ARCHITECTURE_DIAGRAM"
        else "RESEARCH_CONTEXT"
    )
    return {
        **observation,
        "system_contribution": (
            "POTENTIALLY_RELEVANT"
            if observation["system_contribution"] == "RELEVANT"
            else observation["system_contribution"]
        ),
        "benefit_categories": (expected_benefit,),
        "uncertainty_categories": tuple(
            dict.fromkeys((*observation["uncertainty_categories"], "CONTEXT_MISSING"))
        ),
    }


def _enum_list(value: object, allowed: frozenset[str]) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or len(value) > 8:
        raise ValueError("vision category list is invalid")
    if not all(isinstance(item, str) and item in allowed for item in value):
        raise ValueError("vision category list value is invalid")
    if len(value) != len(set(value)):
        raise ValueError("vision category list has duplicates")
    return tuple(value)
