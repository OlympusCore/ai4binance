"""Proofs for the local-only vision perception boundary."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.request import Request

import pytest

from ai4binance.governance.model_registry import ModelGateway
from ai4binance.internal_radar_vision import LlamaCppVisionRunner, _prompt


def test_vision_runner_stays_advisory_when_local_provider_is_unavailable(
    tmp_path: Path,
) -> None:
    image = tmp_path / "private-image.png"
    image.write_bytes(b"image-fixture")

    evidence = LlamaCppVisionRunner(
        base_url="http://127.0.0.1:9", model_gateway=ModelGateway()
    ).analyze(
        candidate_id="internal-image:0123456789abcdef",
        source_content_sha256="a" * 64,
        image_path=image,
    )

    assert evidence.status == "BLOCKED"
    assert evidence.blockers == ("LOCAL_VISION_PROVIDER_UNAVAILABLE", "ADVISORY_ONLY")
    assert evidence.execution_allowed is False
    assert evidence.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_vision_runner_persists_only_validated_categorical_evidence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    image = tmp_path / "private-image.png"
    image.write_bytes(b"image-fixture")
    response = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "image_category": "DASHBOARD",
                            "system_contribution": "RELEVANT",
                            "benefit_categories": ["OPERATIONAL_VISIBILITY"],
                            "tradeoff_categories": ["HUMAN_REVIEW_REQUIRED"],
                            "extracted_text_present": True,
                            "uncertainty_categories": ["OCR_UNCERTAIN"],
                            "confidence": 0.75,
                        }
                    )
                }
            }
        ]
    }

    class AllowedGateway:
        def admit_advisory(self, *_args: object) -> object:
            from ai4binance.governance.model_registry import build_model_route_decision

            return type(
                "Decision",
                (),
                {
                    "allowed": True,
                    "blockers": (),
                    "route_decision": build_model_route_decision(
                        canonical_model_id="local-llamacpp-qwen25vl-3b",
                        provider="llama.cpp",
                        task_type="LOCAL_IMAGE_ADVISORY_ANALYSIS",
                        model_family="LLM",
                        allowed=True,
                        blockers=(),
                    ),
                },
            )()

    class Response:
        def read(self, _limit: int) -> bytes:
            return json.dumps(response).encode("utf-8")

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    captured: dict[str, object] = {}

    def fake_urlopen(request: Request, timeout: float) -> Response:
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    evidence = LlamaCppVisionRunner(model_gateway=AllowedGateway()).analyze(
        candidate_id="internal-image:0123456789abcdef",
        source_content_sha256="b" * 64,
        image_path=image,
    )

    payload = evidence.to_payload()
    assert captured["url"] == "http://127.0.0.1:8081/v1/chat/completions"
    assert evidence.status == "OBSERVED_UNVERIFIED"
    assert payload["image_category"] == "DASHBOARD"
    assert payload["extracted_text_present"] is True
    assert "private-image" not in json.dumps(payload)
    assert payload["privacy"]["raw_ocr_text_persisted"] is False
    assert payload["execution_allowed"] is False


def test_vision_runner_rejects_unstructured_model_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    image = tmp_path / "fixture.png"
    image.write_bytes(b"image-fixture")

    class AllowedGateway:
        def admit_advisory(self, *_args: object) -> object:
            return type("Decision", (), {"allowed": True, "route_decision": None})()

    class Response:
        def read(self, _limit: int) -> bytes:
            return b'{"choices":[{"message":{"content":"not-json"}}]}'

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: Response())
    evidence = LlamaCppVisionRunner(model_gateway=AllowedGateway()).analyze(
        candidate_id="internal-image:0123456789abcdef",
        source_content_sha256="c" * 64,
        image_path=image,
    )

    assert evidence.status == "BLOCKED"
    assert "LOCAL_VISION_SCHEMA_INVALID" in evidence.blockers


def test_vision_runner_accepts_one_json_code_fence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    image = tmp_path / "fixture.png"
    image.write_bytes(b"image-fixture")
    observation = {
        "image_category": "ARCHITECTURE_DIAGRAM",
        "system_contribution": "POTENTIALLY_RELEVANT",
        "benefit_categories": ["ARCHITECTURE_CONTEXT"],
        "tradeoff_categories": ["HUMAN_REVIEW_REQUIRED"],
        "extracted_text_present": True,
        "uncertainty_categories": ["CONTEXT_MISSING"],
        "confidence": 0.5,
    }

    class AllowedGateway:
        def admit_advisory(self, *_args: object) -> object:
            return type(
                "Decision",
                (),
                {"allowed": True, "blockers": (), "route_decision": None},
            )()

    class Response:
        def read(self, _limit: int) -> bytes:
            content = "```json\n" + json.dumps(observation) + "\n```"
            return json.dumps({"choices": [{"message": {"content": content}}]}).encode()

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: Response())
    evidence = LlamaCppVisionRunner(model_gateway=AllowedGateway()).analyze(
        candidate_id="internal-image:0123456789abcdef",
        source_content_sha256="d" * 64,
        image_path=image,
    )

    assert evidence.status == "OBSERVED_UNVERIFIED"
    assert evidence.image_category == "ARCHITECTURE_DIAGRAM"
    assert evidence.system_contribution == "POTENTIALLY_RELEVANT"
    assert evidence.benefit_categories == ("ARCHITECTURE_CONTEXT",)
    assert "CONTEXT_MISSING" in evidence.uncertainty_categories


def test_vision_prompt_distinguishes_system_diagrams_from_generic_infographics() -> (
    None
):
    prompt = _prompt()

    assert "ARCHITECTURE_DIAGRAM" in prompt
    assert "EDUCATIONAL_INFOGRAPHIC" in prompt
    assert "at most POTENTIALLY_RELEVANT" in prompt
