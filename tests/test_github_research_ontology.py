"""Canonical GitHub Radar ontology contract tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai4binance.github_radar.ontology import load_default_ontology, load_ontology


def test_default_ontology_covers_domains_profiles_and_initial_batch() -> None:
    ontology = load_default_ontology()

    assert {item.domain_id for item in ontology.domains} == {
        f"R{index:02d}" for index in range(31)
    }
    assert {item.profile_id for item in ontology.verification_profiles} == {
        f"V{index:02d}" for index in range(1, 13)
    }
    assert len(ontology.capabilities) == 76
    assert all(item.target_agents for item in ontology.capabilities)
    assert all(item.target_layers for item in ontology.capabilities)
    assert ontology.execution_allowed is False
    assert ontology.promotion_status == "RESEARCH_ONLY"
    assert ontology.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_repository_evaluation_schema_keeps_authority_fail_closed() -> None:
    path = Path("config/research/repository_evaluation_schema.json")
    schema = json.loads(path.read_text(encoding="utf-8"))

    properties = schema["properties"]
    assert properties["execution_allowed"] == {"const": False}
    assert properties["promotion_status"] == {"const": "RESEARCH_ONLY"}
    assert properties["live_eligibility_status"] == {"const": "LIVE_ORDER_BLOCKED"}


def test_github_radar_ontology_rejects_unbounded_or_invalid_yaml(
    tmp_path: Path,
) -> None:
    oversized = tmp_path / "ontology.yaml"
    oversized.write_text("x" * 512_001, encoding="utf-8")
    with pytest.raises(ValueError, match="bounded size"):
        load_ontology(oversized)

    invalid_mapping = tmp_path / "invalid.yaml"
    invalid_mapping.write_text("- not-a-mapping\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a mapping"):
        load_ontology(invalid_mapping)

    missing_sequences = tmp_path / "missing-sequences.yaml"
    missing_sequences.write_text(
        json.dumps(
            {
                "ontology_id": "ontology",
                "schema_version": "1",
                "authority": {
                    "execution_allowed": False,
                    "promotion_status": "RESEARCH_ONLY",
                    "live_eligibility_status": "LIVE_ORDER_BLOCKED",
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="domains must be a sequence"):
        load_ontology(missing_sequences)


def test_github_radar_ontology_rejects_unknown_targets(tmp_path: Path) -> None:
    domains = [
        {"id": f"R{index:02d}", "title": f"Domain {index}"} for index in range(31)
    ]
    profiles = [
        {"id": f"V{index:02d}", "title": f"Profile {index}"} for index in range(1, 13)
    ]
    payload = {
        "ontology_id": "ontology",
        "schema_version": "1",
        "domains": domains,
        "verification_profiles": profiles,
        "capabilities": [
            {
                "id": "R00-C01",
                "domain": "R00",
                "title": "Unknown target capability",
                "query": "deterministic evidence fabric",
                "target_layers": ["UNKNOWN_LAYER"],
                "target_agents": ["UNKNOWN_AGENT"],
                "local_evidence": ["README.md"],
                "verification": ["V01"],
            }
        ],
        "authority": {
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        },
    }
    path = tmp_path / "ontology.yaml"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="unknown local targets"):
        load_ontology(path)


def test_github_radar_ontology_rejects_wrong_domain_profile_and_item_shapes(
    tmp_path: Path,
) -> None:
    def write_payload(name: str, payload: object) -> Path:
        path = tmp_path / f"{name}.yaml"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    profiles = [
        {"id": f"V{index:02d}", "title": f"Profile {index}"} for index in range(1, 13)
    ]
    authority = {
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    base_capability = {
        "id": "R00-C01",
        "domain": "R00",
        "title": "Capability",
        "query": "deterministic evidence fabric",
        "target_layers": ["GOVERNANCE_AUTHORITY"],
        "target_agents": ["qaqc_agent"],
        "local_evidence": ["src/ai4binance/governance/authority.py"],
        "verification": ["V10"],
    }

    with pytest.raises(ValueError, match="R00 through R30"):
        load_ontology(
            write_payload(
                "missing-domain",
                {
                    "ontology_id": "ontology",
                    "schema_version": "1",
                    "domains": [
                        {"id": f"R{index:02d}", "title": f"Domain {index}"}
                        for index in range(30)
                    ],
                    "verification_profiles": profiles,
                    "capabilities": [base_capability],
                    "authority": authority,
                },
            )
        )
    with pytest.raises(ValueError, match="V01 through V12"):
        load_ontology(
            write_payload(
                "missing-profile",
                {
                    "ontology_id": "ontology",
                    "schema_version": "1",
                    "domains": [
                        {"id": f"R{index:02d}", "title": f"Domain {index}"}
                        for index in range(31)
                    ],
                    "verification_profiles": profiles[:-1],
                    "capabilities": [base_capability],
                    "authority": authority,
                },
            )
        )
    with pytest.raises(ValueError, match="item must be a mapping"):
        load_ontology(
            write_payload(
                "bad-item",
                {
                    "ontology_id": "ontology",
                    "schema_version": "1",
                    "domains": ["not-a-mapping"],
                    "verification_profiles": profiles,
                    "capabilities": [base_capability],
                    "authority": authority,
                },
            )
        )
    with pytest.raises(ValueError, match="target_layers must be a sequence"):
        load_ontology(
            write_payload(
                "bad-strings",
                {
                    "ontology_id": "ontology",
                    "schema_version": "1",
                    "domains": [
                        {"id": f"R{index:02d}", "title": f"Domain {index}"}
                        for index in range(31)
                    ],
                    "verification_profiles": profiles,
                    "capabilities": [
                        base_capability | {"target_layers": "not-a-sequence"}
                    ],
                    "authority": authority,
                },
            )
        )


def test_github_radar_ontology_rejects_missing_authority_and_empty_capabilities(
    tmp_path: Path,
) -> None:
    domains = [
        {"id": f"R{index:02d}", "title": f"Domain {index}"} for index in range(31)
    ]
    profiles = [
        {"id": f"V{index:02d}", "title": f"Profile {index}"} for index in range(1, 13)
    ]

    missing_authority = tmp_path / "missing-authority.yaml"
    missing_authority.write_text(
        json.dumps(
            {
                "ontology_id": "ontology",
                "schema_version": "1",
                "domains": domains,
                "verification_profiles": profiles,
                "capabilities": [],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="ontology capabilities is empty or unbounded"):
        load_ontology(missing_authority)

    missing_capabilities = tmp_path / "missing-capabilities.yaml"
    missing_capabilities.write_text(
        json.dumps(
            {
                "ontology_id": "ontology",
                "schema_version": "1",
                "domains": domains,
                "verification_profiles": profiles,
                "authority": {
                    "execution_allowed": False,
                    "promotion_status": "RESEARCH_ONLY",
                    "live_eligibility_status": "LIVE_ORDER_BLOCKED",
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="ontology capabilities must be a sequence"):
        load_ontology(missing_capabilities)
