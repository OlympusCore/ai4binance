"""Regression tests for fail-closed governed-knowledge authority resolution."""

from __future__ import annotations

from ai4binance.governance import (
    AuthorityCandidate,
    AuthorityResolutionStatus,
    resolve_authority,
    resolve_authority_pair,
)


def candidate(
    artifact_id: str,
    *,
    source_of_truth: bool = False,
    authority_scope: str = "live_execution_authority",
    authority_layer: str = "L2_GOVERNANCE_COMPLIANCE",
    lifecycle_status: str = "ACTIVE",
) -> AuthorityCandidate:
    return AuthorityCandidate(
        artifact_id=artifact_id,
        authority_scope=authority_scope,
        authority_layer=authority_layer,
        lifecycle_status=lifecycle_status,
        source_of_truth=source_of_truth,
        canonical_path=f"docs/governance/{artifact_id}.md",
    )


def test_authority_resolution_selects_the_single_active_source_of_truth() -> None:
    resolution = resolve_authority(
        "live_execution_authority",
        (
            candidate("policy", source_of_truth=True),
            candidate(
                "workflow",
                authority_layer="L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS",
            ),
        ),
    )

    assert resolution.status is AuthorityResolutionStatus.A_WINS
    assert resolution.winner_artifact_id == "policy"
    assert resolution.blockers == ("LIVE_ORDER_BLOCKED",)
    assert resolution.execution_allowed is False


def test_authority_resolution_blocks_duplicate_and_missing_source_of_truth() -> None:
    duplicate = resolve_authority(
        "live_execution_authority",
        (
            candidate("policy", source_of_truth=True),
            candidate("contract", source_of_truth=True),
        ),
    )
    missing = resolve_authority(
        "live_execution_authority",
        (candidate("workflow"),),
    )
    absent = resolve_authority("live_execution_authority", ())

    assert duplicate.status is AuthorityResolutionStatus.DUPLICATE_SOURCE_OF_TRUTH
    assert "DUPLICATE_SOURCE_OF_TRUTH" in duplicate.blockers
    assert "GOVERNANCE_CONFLICT" in duplicate.blockers
    assert missing.status is AuthorityResolutionStatus.NO_AUTHORITY
    assert "SOURCE_OF_TRUTH_REQUIRED" in missing.blockers
    assert absent.status is AuthorityResolutionStatus.NO_AUTHORITY
    assert absent.candidate_artifact_ids == ()
    assert "AUTHORITY_UNKNOWN" in absent.blockers


def test_authority_pair_returns_b_wins_and_scope_mismatch_is_ambiguous() -> None:
    a = candidate(
        "workflow", authority_layer="L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS"
    )
    b = candidate("policy", source_of_truth=True)
    winner = resolve_authority_pair(a, b)
    mismatch = resolve_authority_pair(
        a,
        candidate("risk", authority_scope="risk_limit_authority", source_of_truth=True),
    )

    assert winner.status is AuthorityResolutionStatus.B_WINS
    assert winner.winner_artifact_id == "policy"
    assert mismatch.status is AuthorityResolutionStatus.AMBIGUOUS
    assert "AUTHORITY_SCOPE_MISMATCH" in mismatch.blockers
