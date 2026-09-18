"""Fail-closed resolution of declared governed-knowledge authority."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ai4binance.governance.authority.model import AUTHORITY_LAYERS


class AuthorityResolutionStatus(StrEnum):
    SAME_AUTHORITY = "SAME_AUTHORITY"
    A_WINS = "A_WINS"
    B_WINS = "B_WINS"
    CONFLICT = "CONFLICT"
    AMBIGUOUS = "AMBIGUOUS"
    DUPLICATE_SOURCE_OF_TRUTH = "DUPLICATE_SOURCE_OF_TRUTH"
    NO_AUTHORITY = "NO_AUTHORITY"


@dataclass(frozen=True, slots=True)
class AuthorityCandidate:
    """A declared, read-only authority claim for one governed concept."""

    artifact_id: str
    authority_scope: str
    authority_layer: str
    lifecycle_status: str
    source_of_truth: bool
    canonical_path: str

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.artifact_id,
                self.authority_scope,
                self.authority_layer,
                self.lifecycle_status,
                self.canonical_path,
            )
        ):
            raise ValueError("authority candidate metadata is required")
        if self.authority_layer not in AUTHORITY_LAYERS:
            raise ValueError("authority candidate layer is invalid")
        if self.canonical_path.startswith("/") or "\\" in self.canonical_path:
            raise ValueError(
                "authority candidate path must be repository-relative posix"
            )


@dataclass(frozen=True, slots=True)
class AuthorityResolution:
    """Deterministic result; it never grants execution or policy authority."""

    authority_scope: str
    status: AuthorityResolutionStatus
    winner_artifact_id: str | None
    candidate_artifact_ids: tuple[str, ...]
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.authority_scope.strip():
            raise ValueError("authority resolution scope is required")
        if (
            not self.candidate_artifact_ids
            and self.status is not AuthorityResolutionStatus.NO_AUTHORITY
        ):
            raise ValueError("authority resolution candidates are required")
        if len(set(self.candidate_artifact_ids)) != len(self.candidate_artifact_ids):
            raise ValueError("authority resolution candidates must be unique")
        if self.status is AuthorityResolutionStatus.AMBIGUOUS and not self.blockers:
            raise ValueError("ambiguous authority resolution requires blockers")
        if (
            self.status
            in {
                AuthorityResolutionStatus.DUPLICATE_SOURCE_OF_TRUTH,
                AuthorityResolutionStatus.NO_AUTHORITY,
                AuthorityResolutionStatus.CONFLICT,
            }
            and "GOVERNANCE_CONFLICT" not in self.blockers
        ):
            raise ValueError("failed authority resolution requires governance conflict")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("authority resolution cannot authorize live execution")


def resolve_authority(
    authority_scope: str,
    candidates: tuple[AuthorityCandidate, ...],
) -> AuthorityResolution:
    """Resolve one scope using declared active source-of-truth metadata only."""
    if not authority_scope.strip():
        raise ValueError("authority scope is required")
    scoped = tuple(
        candidate
        for candidate in candidates
        if candidate.authority_scope == authority_scope
        and candidate.lifecycle_status == "ACTIVE"
    )
    if not scoped:
        return _blocked_resolution(
            authority_scope,
            candidates,
            AuthorityResolutionStatus.NO_AUTHORITY,
            "AUTHORITY_UNKNOWN",
        )
    source_of_truth = tuple(
        candidate for candidate in scoped if candidate.source_of_truth
    )
    if not source_of_truth:
        return _blocked_resolution(
            authority_scope,
            scoped,
            AuthorityResolutionStatus.NO_AUTHORITY,
            "SOURCE_OF_TRUTH_REQUIRED",
        )
    if len(source_of_truth) > 1:
        return _blocked_resolution(
            authority_scope,
            source_of_truth,
            AuthorityResolutionStatus.DUPLICATE_SOURCE_OF_TRUTH,
            "DUPLICATE_SOURCE_OF_TRUTH",
        )
    winner = source_of_truth[0]
    return AuthorityResolution(
        authority_scope=authority_scope,
        status=AuthorityResolutionStatus.A_WINS,
        winner_artifact_id=winner.artifact_id,
        candidate_artifact_ids=tuple(candidate.artifact_id for candidate in scoped),
        blockers=("LIVE_ORDER_BLOCKED",),
    )


def resolve_authority_pair(
    artifact_a: AuthorityCandidate,
    artifact_b: AuthorityCandidate,
) -> AuthorityResolution:
    """Compare two same-scope authority declarations without inferring authority."""
    if artifact_a.authority_scope != artifact_b.authority_scope:
        return AuthorityResolution(
            authority_scope=artifact_a.authority_scope,
            status=AuthorityResolutionStatus.AMBIGUOUS,
            winner_artifact_id=None,
            candidate_artifact_ids=(artifact_a.artifact_id, artifact_b.artifact_id),
            blockers=("AUTHORITY_SCOPE_MISMATCH", "LIVE_ORDER_BLOCKED"),
        )
    if artifact_a.artifact_id == artifact_b.artifact_id:
        return AuthorityResolution(
            authority_scope=artifact_a.authority_scope,
            status=AuthorityResolutionStatus.SAME_AUTHORITY,
            winner_artifact_id=artifact_a.artifact_id,
            candidate_artifact_ids=(artifact_a.artifact_id,),
            blockers=("LIVE_ORDER_BLOCKED",),
        )
    resolution = resolve_authority(
        artifact_a.authority_scope,
        (artifact_a, artifact_b),
    )
    if resolution.winner_artifact_id == artifact_b.artifact_id:
        return AuthorityResolution(
            authority_scope=resolution.authority_scope,
            status=AuthorityResolutionStatus.B_WINS,
            winner_artifact_id=resolution.winner_artifact_id,
            candidate_artifact_ids=resolution.candidate_artifact_ids,
            blockers=resolution.blockers,
        )
    return resolution


def _blocked_resolution(
    authority_scope: str,
    candidates: tuple[AuthorityCandidate, ...],
    status: AuthorityResolutionStatus,
    blocker: str,
) -> AuthorityResolution:
    return AuthorityResolution(
        authority_scope=authority_scope,
        status=status,
        winner_artifact_id=None,
        candidate_artifact_ids=tuple(candidate.artifact_id for candidate in candidates),
        blockers=(blocker, "GOVERNANCE_CONFLICT", "LIVE_ORDER_BLOCKED"),
    )
