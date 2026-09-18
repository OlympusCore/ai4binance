from ai4binance.governance_primitives import (
    AUTHORITY_BASIS_GOVERNED_METADATA_VALIDATED,
    AUTHORITY_BASIS_METADATA_MISSING,
    AUTHORITY_BASIS_PLACEMENT_HINT_ONLY,
    PLACEMENT_HINT_PREFIX,
    TECHNICAL_QUALITY_LEGACY_STATUS,
    TECHNICAL_QUALITY_PRIMARY_STATUS,
    is_technical_quality_pass,
    normalize_technical_quality_status,
)


def test_governance_primitives_accept_canonical_and_legacy_quality_statuses() -> None:
    assert is_technical_quality_pass(TECHNICAL_QUALITY_PRIMARY_STATUS)
    assert is_technical_quality_pass(TECHNICAL_QUALITY_LEGACY_STATUS)
    assert not is_technical_quality_pass("QUALITY_GATE_RED")
    assert (
        normalize_technical_quality_status(TECHNICAL_QUALITY_LEGACY_STATUS)
        == TECHNICAL_QUALITY_PRIMARY_STATUS
    )


def test_governance_primitives_export_canonical_authority_basis_literals() -> None:
    assert AUTHORITY_BASIS_METADATA_MISSING == "validation:authority_metadata_missing"
    assert (
        AUTHORITY_BASIS_GOVERNED_METADATA_VALIDATED
        == "validation:governed_metadata_validated"
    )
    assert AUTHORITY_BASIS_PLACEMENT_HINT_ONLY == "validation:placement_hint_only"
    assert PLACEMENT_HINT_PREFIX == "placement_hint:"
