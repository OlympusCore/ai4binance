"""Fail-closed coverage for the external-authority derived registry."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from ai4binance.governance.authority import external

NOW = datetime(2026, 9, 15, tzinfo=UTC)


def entry(**overrides: object) -> external.ExternalAuthorityEntry:
    values: dict[str, object] = {
        "authority_id": "AUTH-1",
        "title": "External Authority",
        "kind": external.ExternalAuthorityKind.LAW,
        "effect": external.ExternalAuthorityEffect.MANDATORY,
        "jurisdiction": "TR",
        "source_reference": "Official Gazette",
        "source_status": external.ExternalSourceStatus.ACTIVE,
        "effective_from": None,
        "last_verified_at": NOW,
        "review_due_on": NOW.date() + timedelta(days=1),
        "applicability_status": external.ExternalApplicabilityStatus.REVIEW_REQUIRED,
        "applicability_basis": "Pending human legal review.",
        "control_refs": (),
    }
    values.update(overrides)
    return external.ExternalAuthorityEntry(**values)  # type: ignore[arg-type]


def test_external_authority_rejects_invalid_or_authorizing_states() -> None:
    invalid_cases: tuple[tuple[dict[str, object], str], ...] = (
        ({"source_status": "ACTIVE"}, "source status is invalid"),
        ({"title": " "}, "title is required"),
        ({"last_verified_at": datetime(2026, 9, 15)}, "timezone-aware"),
        (
            {"last_verified_at": datetime(2026, 9, 15, tzinfo=UTC).astimezone()},
            "must be UTC",
        ),
        ({"review_due_on": NOW.date() - timedelta(days=1)}, "already be overdue"),
        ({"control_refs": ("CONTROL", "CONTROL")}, "unique and nonblank"),
        (
            {"applicability_status": external.ExternalApplicabilityStatus.APPLICABLE},
            "requires controls",
        ),
    )
    for overrides, message in invalid_cases:
        with pytest.raises(ValueError, match=message):
            entry(**overrides)

    base = entry()
    values: dict[str, object] = {
        "registry_id": "external-authorities",
        "version": "1.0",
        "entries": (base,),
    }
    registry_cases: tuple[tuple[dict[str, object], str], ...] = (
        ({"registry_id": " "}, "identity is required"),
        ({"entries": ()}, "cannot be empty"),
        ({"entries": (base, base)}, "identifiers must be unique"),
        ({"source_of_truth": True}, "derived projection"),
        ({"execution_allowed": True}, "cannot grant execution authority"),
    )
    for overrides, message in registry_cases:
        attempt = dict(values)
        attempt.update(overrides)
        with pytest.raises(ValueError, match=message):
            external.ExternalAuthorityRegistry(**attempt)  # type: ignore[arg-type]


def test_external_authority_registry_collects_independent_applicability_blockers() -> (
    None
):
    registry = external.ExternalAuthorityRegistry(
        registry_id="external-authorities",
        version="1.0",
        entries=(
            entry(
                authority_id="DRAFT",
                source_status=external.ExternalSourceStatus.DRAFT,
                effective_from=date(2026, 9, 16),
                last_verified_at=NOW - timedelta(days=2),
                review_due_on=date(2026, 9, 14),
            ),
            entry(
                authority_id="FUTURE",
                last_verified_at=NOW + timedelta(days=1),
                review_due_on=date(2026, 9, 17),
            ),
        ),
    )

    assert registry.applicability_blockers(as_of=NOW.date()) == (
        "EXTERNAL_AUTHORITY_SOURCE_UNUSABLE:DRAFT:DRAFT",
        "EXTERNAL_AUTHORITY_NOT_YET_EFFECTIVE:DRAFT",
        "EXTERNAL_AUTHORITY_REVIEW_OVERDUE:DRAFT",
        "EXTERNAL_AUTHORITY_REVIEW_REQUIRED:DRAFT",
        "EXTERNAL_AUTHORITY_VERIFICATION_FROM_FUTURE:FUTURE",
        "EXTERNAL_AUTHORITY_REVIEW_REQUIRED:FUTURE",
    )


def test_external_authority_loader_helpers_reject_untyped_payloads(
    tmp_path: Path,
) -> None:
    path = tmp_path / "external.yaml"
    path.write_text("- invalid\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a mapping"):
        external.load_external_authority_registry(path)
    with pytest.raises(ValueError, match="cannot be loaded"):
        external.load_external_authority_registry(tmp_path / "missing.yaml")
    with pytest.raises(ValueError, match="entry must be a mapping"):
        external._entry("invalid")
    with pytest.raises(ValueError, match="entries must be a list"):
        external._list({}, "entries")
    with pytest.raises(ValueError, match="title is required"):
        external._text({}, "title")
    with pytest.raises(ValueError, match="must be boolean"):
        external._boolean({}, "source_of_truth")


def test_external_authority_loader_reads_the_canonical_derived_projection() -> None:
    root = Path(__file__).resolve().parents[1]
    registry = external.load_external_authority_registry(
        root / "config" / "governance" / "external_authorities.yaml",
        schema_root=root / "schemas",
    )

    assert registry.registry_id == "AI4B-GOV-EXT-AUTH-001"
    assert registry.entries[0].authority_id == "EU_AI_ACT"
