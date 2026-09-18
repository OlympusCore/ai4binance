"""Governed technology and strategy research radar with no install authority."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from math import isfinite
from pathlib import Path
from urllib.parse import urlparse

from ai4binance.reporting import to_primitive
from ai4binance.storage import AuditEvent, JsonlAuditStore


class CatalogStatus(StrEnum):
    DISCOVERED = "DISCOVERED"
    HYPOTHESIS_REGISTERED = "HYPOTHESIS_REGISTERED"
    REPRODUCTION_PENDING = "REPRODUCTION_PENDING"
    RESEARCH_ONLY = "RESEARCH_ONLY"
    OOS_REJECTED = "OOS_REJECTED"
    STAGED_CANDIDATE = "STAGED_CANDIDATE"
    PAPER_APPROVED = "PAPER_APPROVED"


_TRANSITIONS = {
    CatalogStatus.DISCOVERED: frozenset({CatalogStatus.HYPOTHESIS_REGISTERED}),
    CatalogStatus.HYPOTHESIS_REGISTERED: frozenset(
        {CatalogStatus.REPRODUCTION_PENDING}
    ),
    CatalogStatus.REPRODUCTION_PENDING: frozenset(
        {CatalogStatus.RESEARCH_ONLY, CatalogStatus.OOS_REJECTED}
    ),
    CatalogStatus.RESEARCH_ONLY: frozenset(
        {CatalogStatus.STAGED_CANDIDATE, CatalogStatus.OOS_REJECTED}
    ),
    CatalogStatus.STAGED_CANDIDATE: frozenset(
        {CatalogStatus.PAPER_APPROVED, CatalogStatus.OOS_REJECTED}
    ),
    CatalogStatus.OOS_REJECTED: frozenset(),
    CatalogStatus.PAPER_APPROVED: frozenset(),
}


def _require_text(**values: str) -> None:
    if any(not value.strip() or len(value) > 2_000 for value in values.values()):
        raise ValueError("catalog text fields must be non-empty and bounded")


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("catalog timestamps must be timezone-aware")


_GIT_COMMIT_RE = re.compile(r"[0-9a-f]{40}")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GITHUB_OWNER_REPO_RE = re.compile(r"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?")
_EXTERNAL_REPO_ALLOWED_PATH_PREFIXES = (
    "README",
    "docs/",
    "examples/",
    "tests/",
)
_EXTERNAL_REPO_TOOL_TERMS = frozenset(
    {
        "agent skill",
        "allowed-tools",
        "claude skill",
        "hook",
        "mcp",
        "plugin",
        "script",
        "subprocess",
        "tool declaration",
    }
)
_EXTERNAL_REPO_FINANCIAL_TERMS = frozenset(
    {
        "auto order",
        "exchange order",
        "financial",
        "leverage",
        "live order",
        "margin",
        "risk limit",
        "trading",
        "wallet",
        "withdraw",
    }
)
_QUESTION_BANK_ALLOWED_PATH_PREFIXES = (
    "README",
    "LICENSE",
    "100-questions-of-",
    "docs/",
    "examples/",
    "tests/",
)
_QUESTION_BANK_ALLOWED_LICENSES = frozenset(
    {"apache-2.0", "bsd-2-clause", "bsd-3-clause", "cc-by-4.0", "mit"}
)
_QUESTION_BANK_TRADING_SCOPE_TERMS = frozenset(
    {
        "auto order",
        "binance",
        "exchange order",
        "futures",
        "leverage",
        "live order",
        "margin",
        "portfolio",
        "risk limit",
        "signal",
        "spot",
        "trade",
        "trading",
        "wallet",
        "withdraw",
    }
)
_QUESTION_BANK_PRIVACY_SCOPE_TERMS = frozenset(
    {
        "browser",
        "computer use",
        "credential",
        "personal data",
        "pii",
        "privacy",
        "secret",
        "user data",
    }
)
_QUANT_LECTURE_SPOT_TERMS = frozenset(
    {
        "binance spot",
        "crypto spot",
        "crypto_spot",
        "spot",
        "spot execution",
        "spot market",
    }
)
_QUANT_LECTURE_DERIVATIVES_TERMS = frozenset(
    {
        "black-scholes",
        "derivative",
        "derivatives",
        "funding",
        "greeks",
        "implied volatility",
        "option",
        "options",
        "perpetual",
        "volatility smile",
    }
)
_QUANT_LECTURE_INSTITUTIONAL_ONLY_TERMS = frozenset(
    {
        "dark pool",
        "dark-pool",
        "hidden liquidity",
        "institutional execution",
        "order splitting",
    }
)


class ExternalRepoWatchlistCategory(StrEnum):
    VALIDATION = "validation"
    BACKTEST = "backtest"
    AGENT_WORKFLOW = "agent-workflow"
    OBSERVABILITY = "observability"
    PRIVACY_SECURITY = "privacy-security"
    DOCS_REPORTING = "docs-reporting"
    MARKET_DATA = "market-data"
    PORTFOLIO_RISK = "portfolio-risk"


class VolatilityAssumptionReviewStatus(StrEnum):
    BLOCKED = "BLOCKED"
    WATCHLIST = "WATCHLIST"
    RESEARCH_ONLY = "RESEARCH_ONLY"


class QuantResearchReviewerResult(StrEnum):
    PASSED = "PASSED"
    WATCHLIST = "WATCHLIST"
    REJECTED = "REJECTED"
    CONFLICTING = "CONFLICTING"


class QuantResearchHypothesisStatus(StrEnum):
    WATCHLIST = "WATCHLIST"
    RESEARCH_ONLY_OPPORTUNITY = "RESEARCH_ONLY_OPPORTUNITY"


class ExternalQuestionBankReviewStatus(StrEnum):
    WATCHLIST = "WATCHLIST"
    RESEARCH_ONLY_QUESTION_BANK = "RESEARCH_ONLY_QUESTION_BANK"


class ExternalQuantLectureReviewStatus(StrEnum):
    WATCHLIST = "WATCHLIST"
    RESEARCH_ONLY_LECTURE = "RESEARCH_ONLY_LECTURE"
    REJECTED_AS_SPOT_IRRELEVANT = "REJECTED_AS_SPOT_IRRELEVANT"


class AgentEngineeringLayer(StrEnum):
    LOOP = "LOOP"
    GRAPH = "GRAPH"
    HARNESS = "HARNESS"


class AgentEngineeringLayerReviewStatus(StrEnum):
    BLOCKED = "BLOCKED"
    WATCHLIST = "WATCHLIST"
    RESEARCH_ONLY_AGENT_PATTERN = "RESEARCH_ONLY_AGENT_PATTERN"


class AgentRuntimeEconomicsReviewStatus(StrEnum):
    BLOCKED = "BLOCKED"
    WATCHLIST = "WATCHLIST"
    RESEARCH_ONLY_RUNTIME_PATTERN = "RESEARCH_ONLY_RUNTIME_PATTERN"


class SecondBrainMemoryReviewStatus(StrEnum):
    CAPTURED = "CAPTURED"
    BLOCKED = "BLOCKED"
    WATCHLIST = "WATCHLIST"
    RESEARCH_ONLY_MEMORY = "RESEARCH_ONLY_MEMORY"


_AGENT_ENGINEERING_DEFAULT_CONTROLS: dict[AgentEngineeringLayer, tuple[str, ...]] = {
    AgentEngineeringLayer.LOOP: (
        "trigger",
        "bounded_context",
        "tool_contract",
        "verification_check",
        "retry_budget",
        "stop_condition",
    ),
    AgentEngineeringLayer.GRAPH: (
        "nodes",
        "edges",
        "guards",
        "reviewer_node",
        "deterministic_reducer",
        "terminal_states",
    ),
    AgentEngineeringLayer.HARNESS: (
        "least_privilege_tools",
        "memory_boundary",
        "permission_model",
        "sandbox",
        "trace_logging",
        "human_approval_gate",
    ),
}


@dataclass(frozen=True, slots=True)
class ExternalRepoWatchlistCandidate:
    """Read-only metadata for a public GitHub repository watchlist candidate."""

    repo_url: str
    title: str
    category: ExternalRepoWatchlistCategory
    pinned_revision: str = ""
    license_id: str = ""
    reviewed_paths: tuple[str, ...] = ("README.md",)
    evidence_citations: tuple[str, ...] = ()
    declared_features: tuple[str, ...] = ()
    execution_allowed: bool = False
    installation_allowed: bool = False
    clone_allowed: bool = False

    def __post_init__(self) -> None:
        _require_text(repo_url=self.repo_url, title=self.title)
        parsed = urlparse(self.repo_url)
        if (
            parsed.scheme != "https"
            or parsed.netloc.casefold() != "github.com"
            or parsed.username
            or not _GITHUB_OWNER_REPO_RE.fullmatch(parsed.path)
        ):
            raise ValueError("external repo watchlist requires a public GitHub URL")
        if len(set(self.reviewed_paths)) != len(self.reviewed_paths) or any(
            not path.strip() for path in self.reviewed_paths
        ):
            raise ValueError(
                "external repo reviewed paths must be unique and non-empty"
            )
        if len(set(self.evidence_citations)) != len(self.evidence_citations) or any(
            not citation.strip() for citation in self.evidence_citations
        ):
            raise ValueError("external repo citations must be unique and non-empty")
        if len(set(self.declared_features)) != len(self.declared_features) or any(
            not feature.strip() for feature in self.declared_features
        ):
            raise ValueError("external repo features must be unique and non-empty")
        if self.execution_allowed or self.installation_allowed or self.clone_allowed:
            raise ValueError("external repo watchlist cannot grant authority")


@dataclass(frozen=True, slots=True)
class ExternalRepoWatchlistAdmission:
    """Fail-closed admission result for a GitHub repo research watchlist item."""

    repo_url: str
    category: ExternalRepoWatchlistCategory
    status: str
    blockers: tuple[str, ...]
    reviewed_paths: tuple[str, ...]
    evidence_citations: tuple[str, ...]
    promotion_status: str = "RESEARCH_ONLY_REPO_CANDIDATE"
    execution_allowed: bool = False
    installation_allowed: bool = False
    clone_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if self.status not in {"WATCHLIST", "BLOCKED"}:
            raise ValueError("external repo admission status is invalid")
        if not self.blockers:
            raise ValueError("external repo admission must retain review blockers")
        if self.status == "BLOCKED" and not any(
            blocker.endswith("_BLOCKED") or blocker.endswith("_REQUIRED")
            for blocker in self.blockers
        ):
            raise ValueError("blocked external repo admission requires hard blockers")
        if self.promotion_status != "RESEARCH_ONLY_REPO_CANDIDATE":
            raise ValueError("external repo admission must remain research-only")
        if self.execution_allowed or self.installation_allowed or self.clone_allowed:
            raise ValueError("external repo admission cannot grant authority")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("external repo admission must keep live trading blocked")


def external_repo_watchlist_admission(
    candidate: ExternalRepoWatchlistCandidate,
) -> ExternalRepoWatchlistAdmission:
    blockers: list[str] = []
    if not _GIT_COMMIT_RE.fullmatch(candidate.pinned_revision):
        blockers.append("PINNED_REVISION_REQUIRED")
    if not candidate.license_id.strip() or candidate.license_id.casefold() in {
        "unknown",
        "none",
        "unlicensed",
    }:
        blockers.append("LICENSE_REVIEW_REQUIRED")
    if not candidate.evidence_citations:
        blockers.append("SOURCE_CITATION_REQUIRED")
    if any(not _is_review_path_allowed(path) for path in candidate.reviewed_paths):
        blockers.append("EXTERNAL_REPO_REVIEW_SCOPE_BLOCKED")
    features = " ".join(candidate.declared_features).casefold()
    if any(term in features for term in _EXTERNAL_REPO_TOOL_TERMS):
        blockers.append("HUMAN_REVIEW_REQUIRED")
    if any(term in features for term in _EXTERNAL_REPO_FINANCIAL_TERMS):
        blockers.append("FINANCIAL_SENSITIVE_REVIEW")
    blockers.extend(
        (
            "EXTERNAL_REPO_CLONE_BLOCKED",
            "EXTERNAL_REPO_INSTALL_BLOCKED",
            "EXTERNAL_REPO_EXECUTION_BLOCKED",
            "LIVE_ORDER_BLOCKED",
        )
    )
    hard_blocked = any(
        blocker
        in {
            "PINNED_REVISION_REQUIRED",
            "LICENSE_REVIEW_REQUIRED",
            "SOURCE_CITATION_REQUIRED",
            "EXTERNAL_REPO_REVIEW_SCOPE_BLOCKED",
        }
        for blocker in blockers
    )
    return ExternalRepoWatchlistAdmission(
        repo_url=candidate.repo_url,
        category=candidate.category,
        status="BLOCKED" if hard_blocked else "WATCHLIST",
        blockers=tuple(dict.fromkeys(blockers)),
        reviewed_paths=candidate.reviewed_paths,
        evidence_citations=candidate.evidence_citations,
    )


def _is_review_path_allowed(path: str) -> bool:
    normalized = path.strip().replace("\\", "/")
    return any(
        normalized == prefix or normalized.startswith(prefix)
        for prefix in _EXTERNAL_REPO_ALLOWED_PATH_PREFIXES
    )


@dataclass(frozen=True, slots=True)
class ExternalQuestionBankEvidence:
    """Hash-bound external question bank evidence; never executable guidance."""

    repository: str
    source_url: str
    pinned_revision: str
    license_id: str
    reviewed_paths: tuple[str, ...]
    content_sha256: str
    topic_tags: tuple[str, ...]
    mapped_ai4binance_domains: tuple[str, ...]
    evidence_citations: tuple[str, ...] = ()
    privacy_controls: tuple[str, ...] = ()
    declared_blockers: tuple[str, ...] = ()
    execution_allowed: bool = False
    installation_allowed: bool = False
    clone_allowed: bool = False
    signal_authority: bool = False
    live_order_authority: bool = False

    def __post_init__(self) -> None:
        _require_text(
            repository=self.repository,
            source_url=self.source_url,
            content_sha256=self.content_sha256,
        )
        parsed = urlparse(self.source_url)
        if (
            parsed.scheme != "https"
            or parsed.netloc.casefold() != "github.com"
            or parsed.username
            or not _GITHUB_OWNER_REPO_RE.fullmatch(parsed.path)
        ):
            raise ValueError("question bank source must be a public GitHub URL")
        if not _SHA256_RE.fullmatch(self.content_sha256):
            raise ValueError("question bank content hash must be lowercase SHA-256")
        _require_unique_nonblank(
            "question bank reviewed paths",
            self.reviewed_paths,
        )
        _require_unique_nonblank("question bank topic tags", self.topic_tags)
        _require_unique_nonblank(
            "question bank domain mappings",
            self.mapped_ai4binance_domains,
        )
        _require_unique_nonblank(
            "question bank citations",
            self.evidence_citations,
        )
        _require_unique_nonblank(
            "question bank privacy controls",
            self.privacy_controls,
        )
        _require_unique_nonblank(
            "question bank declared blockers",
            self.declared_blockers,
        )
        if (
            self.execution_allowed
            or self.installation_allowed
            or self.clone_allowed
            or self.signal_authority
            or self.live_order_authority
        ):
            raise ValueError("question bank evidence cannot grant authority")


@dataclass(frozen=True, slots=True)
class ExternalQuestionBankReview:
    """Fail-closed review result for external question banks used as research."""

    repository: str
    source_url: str
    pinned_revision: str
    license_id: str
    reviewed_paths: tuple[str, ...]
    content_sha256: str
    topic_tags: tuple[str, ...]
    mapped_ai4binance_domains: tuple[str, ...]
    status: ExternalQuestionBankReviewStatus
    blockers: tuple[str, ...]
    evidence_citations: tuple[str, ...]
    privacy_controls: tuple[str, ...]
    promotion_status: str = "RESEARCH_ONLY_QUESTION_BANK"
    execution_allowed: bool = False
    installation_allowed: bool = False
    clone_allowed: bool = False
    signal_authority: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text(
            repository=self.repository,
            source_url=self.source_url,
            content_sha256=self.content_sha256,
        )
        if not _SHA256_RE.fullmatch(self.content_sha256):
            raise ValueError("question bank review hash must be lowercase SHA-256")
        if self.status not in set(ExternalQuestionBankReviewStatus):
            raise ValueError("question bank review status is invalid")
        _require_unique_nonblank("question bank blockers", self.blockers)
        _require_unique_nonblank(
            "question bank reviewed paths",
            self.reviewed_paths,
        )
        _require_unique_nonblank("question bank topic tags", self.topic_tags)
        _require_unique_nonblank(
            "question bank domain mappings",
            self.mapped_ai4binance_domains,
        )
        _require_unique_nonblank(
            "question bank citations",
            self.evidence_citations,
        )
        _require_unique_nonblank(
            "question bank privacy controls",
            self.privacy_controls,
        )
        if "HUMAN_REVIEW_REQUIRED" not in self.blockers:
            raise ValueError("question bank review must require human review")
        if "LIVE_ORDER_BLOCKED" not in self.blockers:
            raise ValueError("question bank review must keep live blocked")
        if "NO_TRADE_SIGNAL_AUTHORITY" not in self.blockers:
            raise ValueError("question bank review cannot become a signal")
        if self.promotion_status != "RESEARCH_ONLY_QUESTION_BANK":
            raise ValueError("question bank review must remain research-only")
        if (
            self.execution_allowed
            or self.installation_allowed
            or self.clone_allowed
            or self.signal_authority
        ):
            raise ValueError("question bank review cannot grant authority")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("question bank review must block live trading")


def review_external_question_bank(
    evidence: ExternalQuestionBankEvidence,
) -> ExternalQuestionBankReview:
    blockers: list[str] = list(evidence.declared_blockers)
    if not _GIT_COMMIT_RE.fullmatch(evidence.pinned_revision):
        blockers.append("QUESTION_BANK_PIN_REQUIRED")
    if evidence.license_id.casefold() not in _QUESTION_BANK_ALLOWED_LICENSES:
        blockers.append("QUESTION_BANK_LICENSE_REVIEW_REQUIRED")
    if not evidence.reviewed_paths:
        blockers.append("QUESTION_BANK_PATH_REVIEW_REQUIRED")
    elif any(
        not _is_question_bank_review_path_allowed(path)
        for path in evidence.reviewed_paths
    ):
        blockers.append("QUESTION_BANK_REVIEW_SCOPE_BLOCKED")
    if not evidence.evidence_citations:
        blockers.append("QUESTION_BANK_CITATION_REQUIRED")
    if not evidence.topic_tags:
        blockers.append("QUESTION_BANK_TOPIC_TAG_REQUIRED")
    if not evidence.mapped_ai4binance_domains:
        blockers.append("QUESTION_BANK_DOMAIN_MAPPING_REQUIRED")

    scope_text = " ".join(
        (
            evidence.repository,
            evidence.source_url,
            *evidence.reviewed_paths,
            *evidence.topic_tags,
            *evidence.mapped_ai4binance_domains,
        )
    ).casefold()
    if any(term in scope_text for term in _QUESTION_BANK_TRADING_SCOPE_TERMS):
        blockers.append("QUESTION_BANK_TRADING_SCOPE_REVIEW_REQUIRED")
    if (
        any(term in scope_text for term in _QUESTION_BANK_PRIVACY_SCOPE_TERMS)
        and not evidence.privacy_controls
    ):
        blockers.append("QUESTION_BANK_PRIVACY_REVIEW_REQUIRED")

    status = (
        ExternalQuestionBankReviewStatus.WATCHLIST
        if blockers
        else ExternalQuestionBankReviewStatus.RESEARCH_ONLY_QUESTION_BANK
    )
    blockers.extend(
        (
            "NO_TRADE_SIGNAL_AUTHORITY",
            "QUESTION_BANK_REVIEW_READ_ONLY",
            "HUMAN_REVIEW_REQUIRED",
            "LIVE_ORDER_BLOCKED",
        )
    )
    return ExternalQuestionBankReview(
        repository=evidence.repository,
        source_url=evidence.source_url,
        pinned_revision=evidence.pinned_revision,
        license_id=evidence.license_id,
        reviewed_paths=evidence.reviewed_paths,
        content_sha256=evidence.content_sha256,
        topic_tags=evidence.topic_tags,
        mapped_ai4binance_domains=evidence.mapped_ai4binance_domains,
        status=status,
        blockers=tuple(dict.fromkeys(blockers)),
        evidence_citations=evidence.evidence_citations,
        privacy_controls=evidence.privacy_controls,
    )


def _is_question_bank_review_path_allowed(path: str) -> bool:
    normalized = path.strip().replace("\\", "/")
    return any(
        normalized == prefix or normalized.startswith(prefix)
        for prefix in _QUESTION_BANK_ALLOWED_PATH_PREFIXES
    )


@dataclass(frozen=True, slots=True)
class ExternalQuantLectureEvidence:
    """Hash-bound quant lecture evidence; never signal or execution authority."""

    lecture_id: str
    title: str
    source_url: str
    source_sha256: str
    topics: tuple[str, ...]
    asset_classes: tuple[str, ...]
    claimed_techniques: tuple[str, ...]
    oos_requirement: str
    transaction_cost_requirement: str
    reviewer_result: QuantResearchReviewerResult
    evidence_citations: tuple[str, ...] = ()
    rejection_reason: str = ""
    source_available: bool = True
    credential_free_source: bool = True
    maker_checker_separated: bool = False
    execution_allowed: bool = False
    signal_authority: bool = False
    live_order_authority: bool = False

    def __post_init__(self) -> None:
        _require_text(
            lecture_id=self.lecture_id,
            title=self.title,
            source_url=self.source_url,
            source_sha256=self.source_sha256,
        )
        parsed = urlparse(self.source_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username:
            raise ValueError("quant lecture source URL must be credential-free HTTPS")
        if not _SHA256_RE.fullmatch(self.source_sha256):
            raise ValueError("quant lecture source hash must be lowercase SHA-256")
        _require_unique_nonblank("quant lecture topics", self.topics)
        _require_unique_nonblank("quant lecture asset classes", self.asset_classes)
        _require_unique_nonblank(
            "quant lecture claimed techniques",
            self.claimed_techniques,
        )
        _require_unique_nonblank("quant lecture citations", self.evidence_citations)
        _require_bounded_optional_text(
            oos_requirement=self.oos_requirement,
            transaction_cost_requirement=self.transaction_cost_requirement,
            rejection_reason=self.rejection_reason,
        )
        if self.reviewer_result not in set(QuantResearchReviewerResult):
            raise ValueError("quant lecture reviewer result is invalid")
        if self.execution_allowed or self.signal_authority or self.live_order_authority:
            raise ValueError("quant lecture evidence cannot grant authority")


@dataclass(frozen=True, slots=True)
class ExternalQuantLectureReview:
    """Fail-closed review for external quant lectures and threads."""

    lecture_id: str
    title: str
    source_url: str
    source_sha256: str
    status: ExternalQuantLectureReviewStatus
    reviewer_result: QuantResearchReviewerResult
    topics: tuple[str, ...]
    asset_classes: tuple[str, ...]
    claimed_techniques: tuple[str, ...]
    oos_requirement: str
    transaction_cost_requirement: str
    rejection_reason: str
    blockers: tuple[str, ...]
    evidence_citations: tuple[str, ...]
    promotion_status: str = "RESEARCH_ONLY_QUANT_LECTURE"
    execution_allowed: bool = False
    signal_authority: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text(
            lecture_id=self.lecture_id,
            title=self.title,
            source_url=self.source_url,
            source_sha256=self.source_sha256,
        )
        if not _SHA256_RE.fullmatch(self.source_sha256):
            raise ValueError("quant lecture review hash must be lowercase SHA-256")
        if self.status not in set(ExternalQuantLectureReviewStatus):
            raise ValueError("quant lecture review status is invalid")
        if self.reviewer_result not in set(QuantResearchReviewerResult):
            raise ValueError("quant lecture reviewer result is invalid")
        _require_unique_nonblank("quant lecture topics", self.topics)
        _require_unique_nonblank("quant lecture asset classes", self.asset_classes)
        _require_unique_nonblank(
            "quant lecture claimed techniques",
            self.claimed_techniques,
        )
        _require_unique_nonblank("quant lecture blockers", self.blockers)
        _require_unique_nonblank("quant lecture citations", self.evidence_citations)
        _require_bounded_optional_text(
            oos_requirement=self.oos_requirement,
            transaction_cost_requirement=self.transaction_cost_requirement,
            rejection_reason=self.rejection_reason,
        )
        if "HUMAN_REVIEW_REQUIRED" not in self.blockers:
            raise ValueError("quant lecture review must require human review")
        if "LIVE_ORDER_BLOCKED" not in self.blockers:
            raise ValueError("quant lecture review must keep live blocked")
        if "NO_TRADE_SIGNAL_AUTHORITY" not in self.blockers:
            raise ValueError("quant lecture review cannot become a signal")
        if self.promotion_status != "RESEARCH_ONLY_QUANT_LECTURE":
            raise ValueError("quant lecture review must remain research-only")
        if self.execution_allowed or self.signal_authority:
            raise ValueError("quant lecture review cannot grant authority")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("quant lecture review must block live trading")


def review_external_quant_lecture(
    evidence: ExternalQuantLectureEvidence,
) -> ExternalQuantLectureReview:
    blockers: list[str] = []
    evidence_text = " ".join(
        (
            evidence.title,
            evidence.source_url,
            *evidence.topics,
            *evidence.asset_classes,
            *evidence.claimed_techniques,
        )
    ).casefold()
    has_spot_context = any(term in evidence_text for term in _QUANT_LECTURE_SPOT_TERMS)
    has_derivatives_context = any(
        term in evidence_text for term in _QUANT_LECTURE_DERIVATIVES_TERMS
    )
    has_institutional_only_context = any(
        term in evidence_text for term in _QUANT_LECTURE_INSTITUTIONAL_ONLY_TERMS
    )

    if not evidence.source_available:
        blockers.append("QUANT_LECTURE_SOURCE_UNAVAILABLE")
    if not evidence.credential_free_source:
        blockers.append("QUANT_LECTURE_CREDENTIAL_BOUNDARY_REQUIRED")
    if not evidence.evidence_citations:
        blockers.append("SOURCE_CITATION_REQUIRED")
    if not evidence.oos_requirement.strip():
        blockers.append("OOS_REQUIREMENT_REQUIRED")
    if not evidence.transaction_cost_requirement.strip():
        blockers.append("TRANSACTION_COST_REQUIREMENT_REQUIRED")
    if not evidence.maker_checker_separated:
        blockers.append("MAKER_CHECKER_SEPARATION_REQUIRED")
    if not has_spot_context:
        blockers.append("SPOT_RELEVANCE_REVIEW_REQUIRED")
    if has_derivatives_context:
        blockers.append("DERIVATIVES_DATA_SUPPLEMENTARY_ONLY")
    if has_institutional_only_context:
        blockers.append("INSTITUTIONAL_MARKET_STRUCTURE_NOT_BINANCE_SPOT")

    if evidence.reviewer_result is QuantResearchReviewerResult.WATCHLIST:
        blockers.append("QUANT_LECTURE_REVIEWER_WATCHLIST")
    elif evidence.reviewer_result is QuantResearchReviewerResult.REJECTED:
        blockers.append("QUANT_LECTURE_REVIEWER_REJECTED")
    elif evidence.reviewer_result is QuantResearchReviewerResult.CONFLICTING:
        blockers.append("QUANT_LECTURE_REVIEWER_CONFLICTING")
    if (
        evidence.reviewer_result is not QuantResearchReviewerResult.PASSED
        and not evidence.rejection_reason.strip()
    ):
        blockers.append("REJECTION_REASON_REQUIRED")

    if evidence.reviewer_result is QuantResearchReviewerResult.REJECTED or (
        not has_spot_context and has_institutional_only_context
    ):
        status = ExternalQuantLectureReviewStatus.REJECTED_AS_SPOT_IRRELEVANT
    elif blockers:
        status = ExternalQuantLectureReviewStatus.WATCHLIST
    else:
        status = ExternalQuantLectureReviewStatus.RESEARCH_ONLY_LECTURE

    blockers.extend(
        (
            "NO_TRADE_SIGNAL_AUTHORITY",
            "QUANT_LECTURE_REVIEW_READ_ONLY",
            "HUMAN_REVIEW_REQUIRED",
            "LIVE_ORDER_BLOCKED",
        )
    )
    return ExternalQuantLectureReview(
        lecture_id=evidence.lecture_id,
        title=evidence.title,
        source_url=evidence.source_url,
        source_sha256=evidence.source_sha256,
        status=status,
        reviewer_result=evidence.reviewer_result,
        topics=evidence.topics,
        asset_classes=evidence.asset_classes,
        claimed_techniques=evidence.claimed_techniques,
        oos_requirement=evidence.oos_requirement,
        transaction_cost_requirement=evidence.transaction_cost_requirement,
        rejection_reason=evidence.rejection_reason,
        blockers=tuple(dict.fromkeys(blockers)),
        evidence_citations=evidence.evidence_citations,
    )


@dataclass(frozen=True, slots=True)
class AgentEngineeringLayerEvidence:
    """Source-bound loop/graph/harness pattern evidence; never execution authority."""

    artifact_id: str
    title: str
    source_url: str
    source_sha256: str
    layer: AgentEngineeringLayer
    observed_controls: tuple[str, ...]
    reviewer_result: QuantResearchReviewerResult
    evidence_citations: tuple[str, ...] = ()
    required_controls: tuple[str, ...] = ()
    rejection_reason: str = ""
    source_available: bool = True
    credential_free_source: bool = True
    execution_allowed: bool = False
    signal_authority: bool = False
    live_order_authority: bool = False

    def __post_init__(self) -> None:
        _require_text(
            artifact_id=self.artifact_id,
            title=self.title,
            source_url=self.source_url,
            source_sha256=self.source_sha256,
        )
        parsed = urlparse(self.source_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username:
            raise ValueError(
                "agent engineering source URL must be credential-free HTTPS"
            )
        if not _SHA256_RE.fullmatch(self.source_sha256):
            raise ValueError("agent engineering source hash must be lowercase SHA-256")
        if self.layer not in set(AgentEngineeringLayer):
            raise ValueError("agent engineering layer is invalid")
        if self.reviewer_result not in set(QuantResearchReviewerResult):
            raise ValueError("agent engineering reviewer result is invalid")
        _require_unique_nonblank(
            "agent engineering observed controls",
            self.observed_controls,
        )
        _require_unique_nonblank(
            "agent engineering required controls",
            self.required_controls,
        )
        _require_unique_nonblank(
            "agent engineering citations",
            self.evidence_citations,
        )
        _require_bounded_optional_text(rejection_reason=self.rejection_reason)
        if self.execution_allowed or self.signal_authority or self.live_order_authority:
            raise ValueError("agent engineering evidence cannot grant authority")


@dataclass(frozen=True, slots=True)
class AgentEngineeringLayerReview:
    """Fail-closed review result for loop, graph, and harness agent patterns."""

    artifact_id: str
    title: str
    source_url: str
    source_sha256: str
    layer: AgentEngineeringLayer
    status: AgentEngineeringLayerReviewStatus
    reviewer_result: QuantResearchReviewerResult
    required_controls: tuple[str, ...]
    observed_controls: tuple[str, ...]
    missing_controls: tuple[str, ...]
    blockers: tuple[str, ...]
    evidence_citations: tuple[str, ...]
    rejection_reason: str = ""
    promotion_status: str = "RESEARCH_ONLY_AGENT_PATTERN"
    execution_allowed: bool = False
    signal_authority: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text(
            artifact_id=self.artifact_id,
            title=self.title,
            source_url=self.source_url,
            source_sha256=self.source_sha256,
        )
        if not _SHA256_RE.fullmatch(self.source_sha256):
            raise ValueError("agent engineering review hash must be lowercase SHA-256")
        if self.layer not in set(AgentEngineeringLayer):
            raise ValueError("agent engineering review layer is invalid")
        if self.status not in set(AgentEngineeringLayerReviewStatus):
            raise ValueError("agent engineering review status is invalid")
        if self.reviewer_result not in set(QuantResearchReviewerResult):
            raise ValueError("agent engineering reviewer result is invalid")
        _require_unique_nonblank(
            "agent engineering required controls",
            self.required_controls,
        )
        _require_unique_nonblank(
            "agent engineering observed controls",
            self.observed_controls,
        )
        _require_unique_nonblank(
            "agent engineering missing controls",
            self.missing_controls,
        )
        _require_unique_nonblank("agent engineering blockers", self.blockers)
        _require_unique_nonblank(
            "agent engineering citations",
            self.evidence_citations,
        )
        _require_bounded_optional_text(rejection_reason=self.rejection_reason)
        if (
            self.status is AgentEngineeringLayerReviewStatus.RESEARCH_ONLY_AGENT_PATTERN
            and self.missing_controls
        ):
            raise ValueError("research-only agent pattern cannot miss controls")
        if "HUMAN_REVIEW_REQUIRED" not in self.blockers:
            raise ValueError("agent engineering review must require human review")
        if "LIVE_ORDER_BLOCKED" not in self.blockers:
            raise ValueError("agent engineering review must keep live blocked")
        if "NO_TRADE_SIGNAL_AUTHORITY" not in self.blockers:
            raise ValueError("agent engineering review cannot become a signal")
        if self.promotion_status != "RESEARCH_ONLY_AGENT_PATTERN":
            raise ValueError("agent engineering review must remain research-only")
        if self.execution_allowed or self.signal_authority:
            raise ValueError("agent engineering review cannot grant authority")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("agent engineering review must block live trading")


def review_agent_engineering_layer(
    evidence: AgentEngineeringLayerEvidence,
) -> AgentEngineeringLayerReview:
    required_controls = (
        evidence.required_controls
        if evidence.required_controls
        else _AGENT_ENGINEERING_DEFAULT_CONTROLS[evidence.layer]
    )
    observed = {
        _normalize_control_name(control) for control in evidence.observed_controls
    }
    missing_controls = tuple(
        control
        for control in required_controls
        if _normalize_control_name(control) not in observed
    )
    blockers: list[str] = []

    if not evidence.source_available:
        blockers.append("AGENT_PATTERN_SOURCE_UNAVAILABLE")
    if not evidence.credential_free_source:
        blockers.append("AGENT_PATTERN_CREDENTIAL_BOUNDARY_REQUIRED")
    if not evidence.evidence_citations:
        blockers.append("SOURCE_CITATION_REQUIRED")
    for control in missing_controls:
        blockers.append(f"MISSING_CONTROL_{_blocker_suffix(control)}")
    if evidence.reviewer_result is QuantResearchReviewerResult.WATCHLIST:
        blockers.append("AGENT_PATTERN_REVIEWER_WATCHLIST")
    elif evidence.reviewer_result is QuantResearchReviewerResult.REJECTED:
        blockers.append("AGENT_PATTERN_REVIEWER_REJECTED")
    elif evidence.reviewer_result is QuantResearchReviewerResult.CONFLICTING:
        blockers.append("AGENT_PATTERN_REVIEWER_CONFLICTING")
    if (
        evidence.reviewer_result is not QuantResearchReviewerResult.PASSED
        and not evidence.rejection_reason.strip()
    ):
        blockers.append("REJECTION_REASON_REQUIRED")

    hard_blockers = {
        "AGENT_PATTERN_SOURCE_UNAVAILABLE",
        "AGENT_PATTERN_CREDENTIAL_BOUNDARY_REQUIRED",
        "SOURCE_CITATION_REQUIRED",
        "AGENT_PATTERN_REVIEWER_REJECTED",
    }
    if any(blocker in hard_blockers for blocker in blockers):
        status = AgentEngineeringLayerReviewStatus.BLOCKED
    elif blockers:
        status = AgentEngineeringLayerReviewStatus.WATCHLIST
    else:
        status = AgentEngineeringLayerReviewStatus.RESEARCH_ONLY_AGENT_PATTERN

    blockers.extend(
        (
            "NO_TRADE_SIGNAL_AUTHORITY",
            "AGENT_ENGINEERING_REVIEW_READ_ONLY",
            "HUMAN_REVIEW_REQUIRED",
            "LIVE_ORDER_BLOCKED",
        )
    )
    return AgentEngineeringLayerReview(
        artifact_id=evidence.artifact_id,
        title=evidence.title,
        source_url=evidence.source_url,
        source_sha256=evidence.source_sha256,
        layer=evidence.layer,
        status=status,
        reviewer_result=evidence.reviewer_result,
        required_controls=required_controls,
        observed_controls=evidence.observed_controls,
        missing_controls=missing_controls,
        blockers=tuple(dict.fromkeys(blockers)),
        evidence_citations=evidence.evidence_citations,
        rejection_reason=evidence.rejection_reason,
    )


def _normalize_control_name(control: str) -> str:
    return control.strip().replace("-", "_").casefold()


def _blocker_suffix(control: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", control.strip().upper()).strip("_")


@dataclass(frozen=True, slots=True)
class AgentRuntimeEconomicsEvidence:
    """Source-bound runtime cost evidence; never provider or execution authority."""

    artifact_id: str
    title: str
    source_url: str
    source_sha256: str
    hardware_profile: str
    runtime_stack: str
    reviewer_result: QuantResearchReviewerResult
    claimed_monthly_cost_usd: float | None = None
    measured_latency_ms: float | None = None
    measured_tokens_per_second: float | None = None
    measured_power_watts: float | None = None
    benchmark_citations: tuple[str, ...] = ()
    privacy_controls: tuple[str, ...] = ()
    operational_controls: tuple[str, ...] = ()
    rejection_reason: str = ""
    source_available: bool = True
    credential_free_source: bool = True
    execution_allowed: bool = False
    installation_allowed: bool = False
    provider_switch_allowed: bool = False
    signal_authority: bool = False
    live_order_authority: bool = False

    def __post_init__(self) -> None:
        _require_text(
            artifact_id=self.artifact_id,
            title=self.title,
            source_url=self.source_url,
            source_sha256=self.source_sha256,
            hardware_profile=self.hardware_profile,
            runtime_stack=self.runtime_stack,
        )
        parsed = urlparse(self.source_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username:
            raise ValueError("agent runtime source URL must be credential-free HTTPS")
        if not _SHA256_RE.fullmatch(self.source_sha256):
            raise ValueError("agent runtime source hash must be lowercase SHA-256")
        if self.reviewer_result not in set(QuantResearchReviewerResult):
            raise ValueError("agent runtime reviewer result is invalid")
        _require_unique_nonblank(
            "agent runtime benchmark citations",
            self.benchmark_citations,
        )
        _require_unique_nonblank(
            "agent runtime privacy controls",
            self.privacy_controls,
        )
        _require_unique_nonblank(
            "agent runtime operational controls",
            self.operational_controls,
        )
        _require_bounded_optional_text(rejection_reason=self.rejection_reason)
        numeric_values = tuple(
            value
            for value in (
                self.claimed_monthly_cost_usd,
                self.measured_latency_ms,
                self.measured_tokens_per_second,
                self.measured_power_watts,
            )
            if value is not None
        )
        if any(not isfinite(value) or value < 0.0 for value in numeric_values):
            raise ValueError(
                "agent runtime measurements must be finite and non-negative"
            )
        if (
            self.execution_allowed
            or self.installation_allowed
            or self.provider_switch_allowed
            or self.signal_authority
            or self.live_order_authority
        ):
            raise ValueError("agent runtime evidence cannot grant authority")


@dataclass(frozen=True, slots=True)
class AgentRuntimeEconomicsReview:
    """Fail-closed review for local GPU/workstation/runtime economics claims."""

    artifact_id: str
    title: str
    source_url: str
    source_sha256: str
    hardware_profile: str
    runtime_stack: str
    status: AgentRuntimeEconomicsReviewStatus
    reviewer_result: QuantResearchReviewerResult
    blockers: tuple[str, ...]
    benchmark_citations: tuple[str, ...]
    privacy_controls: tuple[str, ...]
    operational_controls: tuple[str, ...]
    claimed_monthly_cost_usd: float | None = None
    measured_latency_ms: float | None = None
    measured_tokens_per_second: float | None = None
    measured_power_watts: float | None = None
    rejection_reason: str = ""
    promotion_status: str = "RESEARCH_ONLY_RUNTIME_PATTERN"
    execution_allowed: bool = False
    installation_allowed: bool = False
    provider_switch_allowed: bool = False
    signal_authority: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text(
            artifact_id=self.artifact_id,
            title=self.title,
            source_url=self.source_url,
            source_sha256=self.source_sha256,
            hardware_profile=self.hardware_profile,
            runtime_stack=self.runtime_stack,
        )
        if not _SHA256_RE.fullmatch(self.source_sha256):
            raise ValueError("agent runtime review hash must be lowercase SHA-256")
        if self.status not in set(AgentRuntimeEconomicsReviewStatus):
            raise ValueError("agent runtime review status is invalid")
        if self.reviewer_result not in set(QuantResearchReviewerResult):
            raise ValueError("agent runtime reviewer result is invalid")
        _require_unique_nonblank("agent runtime blockers", self.blockers)
        _require_unique_nonblank(
            "agent runtime benchmark citations",
            self.benchmark_citations,
        )
        _require_unique_nonblank(
            "agent runtime privacy controls",
            self.privacy_controls,
        )
        _require_unique_nonblank(
            "agent runtime operational controls",
            self.operational_controls,
        )
        _require_bounded_optional_text(rejection_reason=self.rejection_reason)
        numeric_values = tuple(
            value
            for value in (
                self.claimed_monthly_cost_usd,
                self.measured_latency_ms,
                self.measured_tokens_per_second,
                self.measured_power_watts,
            )
            if value is not None
        )
        if any(not isfinite(value) or value < 0.0 for value in numeric_values):
            raise ValueError(
                "agent runtime measurements must be finite and non-negative"
            )
        if "HUMAN_REVIEW_REQUIRED" not in self.blockers:
            raise ValueError("agent runtime review must require human review")
        if "LIVE_ORDER_BLOCKED" not in self.blockers:
            raise ValueError("agent runtime review must keep live blocked")
        if "NO_TRADE_SIGNAL_AUTHORITY" not in self.blockers:
            raise ValueError("agent runtime review cannot become a signal")
        if self.promotion_status != "RESEARCH_ONLY_RUNTIME_PATTERN":
            raise ValueError("agent runtime review must remain research-only")
        if (
            self.execution_allowed
            or self.installation_allowed
            or self.provider_switch_allowed
            or self.signal_authority
        ):
            raise ValueError("agent runtime review cannot grant authority")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("agent runtime review must block live trading")


def review_agent_runtime_economics(
    evidence: AgentRuntimeEconomicsEvidence,
) -> AgentRuntimeEconomicsReview:
    blockers: list[str] = []
    if not evidence.source_available:
        blockers.append("AGENT_RUNTIME_SOURCE_UNAVAILABLE")
    if not evidence.credential_free_source:
        blockers.append("AGENT_RUNTIME_CREDENTIAL_BOUNDARY_REQUIRED")
    if not evidence.benchmark_citations:
        blockers.append("RUNTIME_BENCHMARK_CITATION_REQUIRED")
    if evidence.claimed_monthly_cost_usd is None:
        blockers.append("RUNTIME_COST_MEASUREMENT_REQUIRED")
    if evidence.measured_latency_ms is None:
        blockers.append("RUNTIME_LATENCY_MEASUREMENT_REQUIRED")
    if evidence.measured_tokens_per_second is None:
        blockers.append("RUNTIME_THROUGHPUT_MEASUREMENT_REQUIRED")
    if evidence.measured_power_watts is None:
        blockers.append("POWER_THERMAL_REVIEW_REQUIRED")
    if not evidence.privacy_controls:
        blockers.append("RUNTIME_PRIVACY_CONTROL_REQUIRED")
    if not evidence.operational_controls:
        blockers.append("RUNTIME_OPERATIONAL_CONTROL_REQUIRED")
    if evidence.reviewer_result is QuantResearchReviewerResult.WATCHLIST:
        blockers.append("AGENT_RUNTIME_REVIEWER_WATCHLIST")
    elif evidence.reviewer_result is QuantResearchReviewerResult.REJECTED:
        blockers.append("AGENT_RUNTIME_REVIEWER_REJECTED")
    elif evidence.reviewer_result is QuantResearchReviewerResult.CONFLICTING:
        blockers.append("AGENT_RUNTIME_REVIEWER_CONFLICTING")
    if (
        evidence.reviewer_result is not QuantResearchReviewerResult.PASSED
        and not evidence.rejection_reason.strip()
    ):
        blockers.append("REJECTION_REASON_REQUIRED")

    hard_blockers = {
        "AGENT_RUNTIME_SOURCE_UNAVAILABLE",
        "AGENT_RUNTIME_CREDENTIAL_BOUNDARY_REQUIRED",
        "RUNTIME_BENCHMARK_CITATION_REQUIRED",
        "AGENT_RUNTIME_REVIEWER_REJECTED",
    }
    if any(blocker in hard_blockers for blocker in blockers):
        status = AgentRuntimeEconomicsReviewStatus.BLOCKED
    elif blockers:
        status = AgentRuntimeEconomicsReviewStatus.WATCHLIST
    else:
        status = AgentRuntimeEconomicsReviewStatus.RESEARCH_ONLY_RUNTIME_PATTERN

    blockers.extend(
        (
            "NO_TRADE_SIGNAL_AUTHORITY",
            "AGENT_RUNTIME_REVIEW_READ_ONLY",
            "HUMAN_REVIEW_REQUIRED",
            "LIVE_ORDER_BLOCKED",
        )
    )
    return AgentRuntimeEconomicsReview(
        artifact_id=evidence.artifact_id,
        title=evidence.title,
        source_url=evidence.source_url,
        source_sha256=evidence.source_sha256,
        hardware_profile=evidence.hardware_profile,
        runtime_stack=evidence.runtime_stack,
        status=status,
        reviewer_result=evidence.reviewer_result,
        blockers=tuple(dict.fromkeys(blockers)),
        benchmark_citations=evidence.benchmark_citations,
        privacy_controls=evidence.privacy_controls,
        operational_controls=evidence.operational_controls,
        claimed_monthly_cost_usd=evidence.claimed_monthly_cost_usd,
        measured_latency_ms=evidence.measured_latency_ms,
        measured_tokens_per_second=evidence.measured_tokens_per_second,
        measured_power_watts=evidence.measured_power_watts,
        rejection_reason=evidence.rejection_reason,
    )


@dataclass(frozen=True, slots=True)
class SecondBrainMemoryEvidence:
    """Hash-bound memory capture evidence; never trading or sync authority."""

    memory_id: str
    title: str
    source_url: str
    source_sha256: str
    vault_path_sha256: str
    topic_tags: tuple[str, ...]
    staleness_policy: str
    reviewer_result: QuantResearchReviewerResult
    evidence_citations: tuple[str, ...] = ()
    privacy_controls: tuple[str, ...] = ()
    redaction_controls: tuple[str, ...] = ()
    rejection_reason: str = ""
    source_available: bool = True
    credential_free_source: bool = True
    reviewed: bool = True
    execution_allowed: bool = False
    sync_allowed: bool = False
    context_export_allowed: bool = False
    signal_authority: bool = False
    live_order_authority: bool = False

    def __post_init__(self) -> None:
        _require_text(
            memory_id=self.memory_id,
            title=self.title,
            source_url=self.source_url,
            source_sha256=self.source_sha256,
            vault_path_sha256=self.vault_path_sha256,
        )
        parsed = urlparse(self.source_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username:
            raise ValueError(
                "second brain memory source URL must be credential-free HTTPS"
            )
        if not _SHA256_RE.fullmatch(self.source_sha256):
            raise ValueError("second brain source hash must be lowercase SHA-256")
        if not _SHA256_RE.fullmatch(self.vault_path_sha256):
            raise ValueError("second brain vault path hash must be lowercase SHA-256")
        if self.reviewer_result not in set(QuantResearchReviewerResult):
            raise ValueError("second brain reviewer result is invalid")
        _require_unique_nonblank("second brain topic tags", self.topic_tags)
        _require_unique_nonblank(
            "second brain citations",
            self.evidence_citations,
        )
        _require_unique_nonblank(
            "second brain privacy controls",
            self.privacy_controls,
        )
        _require_unique_nonblank(
            "second brain redaction controls",
            self.redaction_controls,
        )
        _require_bounded_optional_text(
            staleness_policy=self.staleness_policy,
            rejection_reason=self.rejection_reason,
        )
        if (
            self.execution_allowed
            or self.sync_allowed
            or self.context_export_allowed
            or self.signal_authority
            or self.live_order_authority
        ):
            raise ValueError("second brain memory evidence cannot grant authority")


@dataclass(frozen=True, slots=True)
class SecondBrainMemoryReview:
    """Fail-closed review for local second-brain research memory entries."""

    memory_id: str
    title: str
    source_url: str
    source_sha256: str
    vault_path_sha256: str
    status: SecondBrainMemoryReviewStatus
    reviewer_result: QuantResearchReviewerResult
    topic_tags: tuple[str, ...]
    staleness_policy: str
    blockers: tuple[str, ...]
    evidence_citations: tuple[str, ...]
    privacy_controls: tuple[str, ...]
    redaction_controls: tuple[str, ...]
    rejection_reason: str = ""
    promotion_status: str = "RESEARCH_ONLY_MEMORY"
    execution_allowed: bool = False
    sync_allowed: bool = False
    context_export_allowed: bool = False
    signal_authority: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text(
            memory_id=self.memory_id,
            title=self.title,
            source_url=self.source_url,
            source_sha256=self.source_sha256,
            vault_path_sha256=self.vault_path_sha256,
        )
        if not _SHA256_RE.fullmatch(self.source_sha256):
            raise ValueError(
                "second brain review source hash must be lowercase SHA-256"
            )
        if not _SHA256_RE.fullmatch(self.vault_path_sha256):
            raise ValueError(
                "second brain review vault path hash must be lowercase SHA-256"
            )
        if self.status not in set(SecondBrainMemoryReviewStatus):
            raise ValueError("second brain memory review status is invalid")
        if self.reviewer_result not in set(QuantResearchReviewerResult):
            raise ValueError("second brain reviewer result is invalid")
        _require_unique_nonblank("second brain topic tags", self.topic_tags)
        _require_unique_nonblank("second brain blockers", self.blockers)
        _require_unique_nonblank(
            "second brain citations",
            self.evidence_citations,
        )
        _require_unique_nonblank(
            "second brain privacy controls",
            self.privacy_controls,
        )
        _require_unique_nonblank(
            "second brain redaction controls",
            self.redaction_controls,
        )
        _require_bounded_optional_text(
            staleness_policy=self.staleness_policy,
            rejection_reason=self.rejection_reason,
        )
        if (
            self.status is SecondBrainMemoryReviewStatus.RESEARCH_ONLY_MEMORY
            and "SECOND_BRAIN_REVIEW_PENDING" in self.blockers
        ):
            raise ValueError("research-only second brain memory cannot be pending")
        if "HUMAN_REVIEW_REQUIRED" not in self.blockers:
            raise ValueError("second brain memory review must require human review")
        if "LIVE_ORDER_BLOCKED" not in self.blockers:
            raise ValueError("second brain memory review must keep live blocked")
        if "NO_TRADE_SIGNAL_AUTHORITY" not in self.blockers:
            raise ValueError("second brain memory review cannot become a signal")
        if self.promotion_status != "RESEARCH_ONLY_MEMORY":
            raise ValueError("second brain memory review must remain research-only")
        if (
            self.execution_allowed
            or self.sync_allowed
            or self.context_export_allowed
            or self.signal_authority
        ):
            raise ValueError("second brain memory review cannot grant authority")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("second brain memory review must block live trading")


def review_second_brain_memory(
    evidence: SecondBrainMemoryEvidence,
) -> SecondBrainMemoryReview:
    blockers: list[str] = []
    if not evidence.source_available:
        blockers.append("SECOND_BRAIN_SOURCE_UNAVAILABLE")
    if not evidence.credential_free_source:
        blockers.append("SECOND_BRAIN_CREDENTIAL_BOUNDARY_REQUIRED")
    if not evidence.evidence_citations:
        blockers.append("SOURCE_CITATION_REQUIRED")
    if not evidence.privacy_controls:
        blockers.append("SECOND_BRAIN_PRIVACY_CONTROL_REQUIRED")
    if not evidence.redaction_controls:
        blockers.append("SECOND_BRAIN_REDACTION_CONTROL_REQUIRED")
    if not evidence.staleness_policy.strip():
        blockers.append("SECOND_BRAIN_STALENESS_POLICY_REQUIRED")
    if not evidence.reviewed:
        blockers.append("SECOND_BRAIN_REVIEW_PENDING")
    if evidence.reviewer_result is QuantResearchReviewerResult.WATCHLIST:
        blockers.append("SECOND_BRAIN_REVIEWER_WATCHLIST")
    elif evidence.reviewer_result is QuantResearchReviewerResult.REJECTED:
        blockers.append("SECOND_BRAIN_REVIEWER_REJECTED")
    elif evidence.reviewer_result is QuantResearchReviewerResult.CONFLICTING:
        blockers.append("SECOND_BRAIN_REVIEWER_CONFLICTING")
    if (
        evidence.reviewer_result is not QuantResearchReviewerResult.PASSED
        and not evidence.rejection_reason.strip()
    ):
        blockers.append("REJECTION_REASON_REQUIRED")

    hard_blockers = {
        "SECOND_BRAIN_SOURCE_UNAVAILABLE",
        "SECOND_BRAIN_CREDENTIAL_BOUNDARY_REQUIRED",
        "SOURCE_CITATION_REQUIRED",
        "SECOND_BRAIN_REVIEWER_REJECTED",
    }
    if any(blocker in hard_blockers for blocker in blockers):
        status = SecondBrainMemoryReviewStatus.BLOCKED
    elif "SECOND_BRAIN_REVIEW_PENDING" in blockers:
        status = SecondBrainMemoryReviewStatus.CAPTURED
    elif blockers:
        status = SecondBrainMemoryReviewStatus.WATCHLIST
    else:
        status = SecondBrainMemoryReviewStatus.RESEARCH_ONLY_MEMORY

    blockers.extend(
        (
            "NO_TRADE_SIGNAL_AUTHORITY",
            "SECOND_BRAIN_MEMORY_READ_ONLY",
            "HUMAN_REVIEW_REQUIRED",
            "LIVE_ORDER_BLOCKED",
        )
    )
    return SecondBrainMemoryReview(
        memory_id=evidence.memory_id,
        title=evidence.title,
        source_url=evidence.source_url,
        source_sha256=evidence.source_sha256,
        vault_path_sha256=evidence.vault_path_sha256,
        status=status,
        reviewer_result=evidence.reviewer_result,
        topic_tags=evidence.topic_tags,
        staleness_policy=evidence.staleness_policy,
        blockers=tuple(dict.fromkeys(blockers)),
        evidence_citations=evidence.evidence_citations,
        privacy_controls=evidence.privacy_controls,
        redaction_controls=evidence.redaction_controls,
        rejection_reason=evidence.rejection_reason,
    )


@dataclass(frozen=True, slots=True)
class QuantResearchHypothesisEvidence:
    """Mechanism-first quant hypothesis evidence, not a trading signal."""

    hypothesis_id: str
    symbol: str
    timeframe: str
    market_mechanism: str
    measurable_footprint: str
    universe: str
    liquidity_assumption: str
    feature_horizon: str
    oos_requirement: str
    transaction_cost_requirement: str
    reviewer_result: QuantResearchReviewerResult
    data_citations: tuple[str, ...] = ()
    leakage_checks: tuple[str, ...] = ()
    robustness_checks: tuple[str, ...] = ()
    rejection_reason: str = ""
    maker_checker_separated: bool = False
    execution_allowed: bool = False
    signal_authority: bool = False
    live_order_authority: bool = False

    def __post_init__(self) -> None:
        _require_text(
            hypothesis_id=self.hypothesis_id,
            symbol=self.symbol,
            timeframe=self.timeframe,
        )
        _require_bounded_optional_text(
            market_mechanism=self.market_mechanism,
            measurable_footprint=self.measurable_footprint,
            universe=self.universe,
            liquidity_assumption=self.liquidity_assumption,
            feature_horizon=self.feature_horizon,
            oos_requirement=self.oos_requirement,
            transaction_cost_requirement=self.transaction_cost_requirement,
            rejection_reason=self.rejection_reason,
        )
        _require_unique_nonblank("quant hypothesis citations", self.data_citations)
        _require_unique_nonblank("quant hypothesis leakage checks", self.leakage_checks)
        _require_unique_nonblank(
            "quant hypothesis robustness checks",
            self.robustness_checks,
        )
        if self.execution_allowed or self.signal_authority or self.live_order_authority:
            raise ValueError("quant hypothesis evidence cannot grant authority")


@dataclass(frozen=True, slots=True)
class QuantResearchHypothesisReview:
    """Fail-closed review that tries to kill an alpha hypothesis before capital."""

    hypothesis_id: str
    symbol: str
    timeframe: str
    status: QuantResearchHypothesisStatus
    reviewer_result: QuantResearchReviewerResult
    market_mechanism: str
    measurable_footprint: str
    universe: str
    liquidity_assumption: str
    feature_horizon: str
    oos_requirement: str
    transaction_cost_requirement: str
    rejection_reason: str
    blockers: tuple[str, ...]
    data_citations: tuple[str, ...]
    leakage_checks: tuple[str, ...]
    robustness_checks: tuple[str, ...]
    promotion_status: str = "RESEARCH_ONLY_QUANT_HYPOTHESIS"
    execution_allowed: bool = False
    signal_authority: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text(
            hypothesis_id=self.hypothesis_id,
            symbol=self.symbol,
            timeframe=self.timeframe,
        )
        _require_bounded_optional_text(
            market_mechanism=self.market_mechanism,
            measurable_footprint=self.measurable_footprint,
            universe=self.universe,
            liquidity_assumption=self.liquidity_assumption,
            feature_horizon=self.feature_horizon,
            oos_requirement=self.oos_requirement,
            transaction_cost_requirement=self.transaction_cost_requirement,
            rejection_reason=self.rejection_reason,
        )
        if self.status not in set(QuantResearchHypothesisStatus):
            raise ValueError("quant hypothesis review status is invalid")
        if self.reviewer_result not in set(QuantResearchReviewerResult):
            raise ValueError("quant hypothesis reviewer result is invalid")
        _require_unique_nonblank("quant hypothesis blockers", self.blockers)
        _require_unique_nonblank("quant hypothesis citations", self.data_citations)
        _require_unique_nonblank("quant hypothesis leakage checks", self.leakage_checks)
        _require_unique_nonblank(
            "quant hypothesis robustness checks",
            self.robustness_checks,
        )
        if "LIVE_ORDER_BLOCKED" not in self.blockers:
            raise ValueError("quant hypothesis review must keep live blocked")
        if "NO_TRADE_SIGNAL_AUTHORITY" not in self.blockers:
            raise ValueError("quant hypothesis review cannot become a signal")
        if self.promotion_status != "RESEARCH_ONLY_QUANT_HYPOTHESIS":
            raise ValueError("quant hypothesis review must remain research-only")
        if self.execution_allowed or self.signal_authority:
            raise ValueError("quant hypothesis review cannot grant authority")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("quant hypothesis review must block live trading")


def review_quant_research_hypothesis(
    evidence: QuantResearchHypothesisEvidence,
) -> QuantResearchHypothesisReview:
    blockers: list[str] = []
    if not evidence.market_mechanism.strip():
        blockers.append("MARKET_MECHANISM_REQUIRED")
    if not evidence.measurable_footprint.strip():
        blockers.append("MEASURABLE_FOOTPRINT_REQUIRED")
    if not evidence.universe.strip():
        blockers.append("RESEARCH_UNIVERSE_REQUIRED")
    if not evidence.liquidity_assumption.strip():
        blockers.append("LIQUIDITY_ASSUMPTION_REQUIRED")
    if not evidence.feature_horizon.strip():
        blockers.append("FEATURE_HORIZON_REQUIRED")
    if not evidence.data_citations:
        blockers.append("SOURCE_CITATION_REQUIRED")
    if not evidence.leakage_checks:
        blockers.append("LEAKAGE_CHECK_REQUIRED")
    if not evidence.oos_requirement.strip():
        blockers.append("OOS_REQUIREMENT_REQUIRED")
    if not evidence.transaction_cost_requirement.strip():
        blockers.append("TRANSACTION_COST_REQUIREMENT_REQUIRED")
    if not evidence.robustness_checks:
        blockers.append("ROBUSTNESS_CHECK_REQUIRED")
    if not evidence.maker_checker_separated:
        blockers.append("MAKER_CHECKER_SEPARATION_REQUIRED")
    if evidence.reviewer_result is QuantResearchReviewerResult.WATCHLIST:
        blockers.append("QUANT_REVIEWER_WATCHLIST")
    elif evidence.reviewer_result is QuantResearchReviewerResult.REJECTED:
        blockers.append("QUANT_REVIEWER_REJECTED")
    elif evidence.reviewer_result is QuantResearchReviewerResult.CONFLICTING:
        blockers.append("QUANT_REVIEWER_CONFLICTING")
    if (
        evidence.reviewer_result is not QuantResearchReviewerResult.PASSED
        and not evidence.rejection_reason.strip()
    ):
        blockers.append("REJECTION_REASON_REQUIRED")

    status = (
        QuantResearchHypothesisStatus.WATCHLIST
        if blockers
        else QuantResearchHypothesisStatus.RESEARCH_ONLY_OPPORTUNITY
    )
    blockers.extend(
        (
            "NO_TRADE_SIGNAL_AUTHORITY",
            "QUANT_HYPOTHESIS_REVIEW_READ_ONLY",
            "LIVE_ORDER_BLOCKED",
        )
    )
    return QuantResearchHypothesisReview(
        hypothesis_id=evidence.hypothesis_id,
        symbol=evidence.symbol,
        timeframe=evidence.timeframe,
        status=status,
        reviewer_result=evidence.reviewer_result,
        market_mechanism=evidence.market_mechanism,
        measurable_footprint=evidence.measurable_footprint,
        universe=evidence.universe,
        liquidity_assumption=evidence.liquidity_assumption,
        feature_horizon=evidence.feature_horizon,
        oos_requirement=evidence.oos_requirement,
        transaction_cost_requirement=evidence.transaction_cost_requirement,
        rejection_reason=evidence.rejection_reason,
        blockers=tuple(dict.fromkeys(blockers)),
        data_citations=evidence.data_citations,
        leakage_checks=evidence.leakage_checks,
        robustness_checks=evidence.robustness_checks,
    )


@dataclass(frozen=True, slots=True)
class VolatilityAssumptionEvidence:
    """Read-only evidence for reviewing a volatility assumption, not a signal."""

    symbol: str
    timeframe: str
    observed_at: datetime
    model_family: str
    assumption_name: str
    horizon_days: int
    sample_size: int
    realized_volatility: float
    assumed_volatility: float
    evidence_citations: tuple[str, ...] = ()
    implied_volatility: float | None = None
    notes: tuple[str, ...] = ()
    execution_allowed: bool = False
    signal_authority: bool = False

    def __post_init__(self) -> None:
        _require_text(
            symbol=self.symbol,
            timeframe=self.timeframe,
            model_family=self.model_family,
            assumption_name=self.assumption_name,
        )
        _require_aware(self.observed_at)
        if self.horizon_days < 1 or self.sample_size < 1:
            raise ValueError("volatility horizon and sample size must be positive")
        numeric_values: tuple[float, ...] = (
            self.realized_volatility,
            self.assumed_volatility,
        )
        if self.implied_volatility is not None:
            numeric_values = (*numeric_values, self.implied_volatility)
        if any(not isfinite(value) or value <= 0.0 for value in numeric_values):
            raise ValueError("volatility values must be finite and positive")
        _require_unique_nonblank("volatility citations", self.evidence_citations)
        _require_unique_nonblank("volatility notes", self.notes)
        if self.execution_allowed or self.signal_authority:
            raise ValueError("volatility assumption evidence cannot grant authority")


@dataclass(frozen=True, slots=True)
class VolatilityAssumptionReview:
    """Fail-closed advisory review for volatility model assumptions."""

    symbol: str
    timeframe: str
    model_family: str
    assumption_name: str
    status: VolatilityAssumptionReviewStatus
    observed_relative_gap: float
    max_relative_gap: float
    blockers: tuple[str, ...]
    evidence_citations: tuple[str, ...]
    promotion_status: str = "RESEARCH_ONLY_VOLATILITY_ASSUMPTION"
    execution_allowed: bool = False
    signal_authority: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text(
            symbol=self.symbol,
            timeframe=self.timeframe,
            model_family=self.model_family,
            assumption_name=self.assumption_name,
        )
        if self.status not in set(VolatilityAssumptionReviewStatus):
            raise ValueError("volatility assumption review status is invalid")
        if not isfinite(self.observed_relative_gap) or self.observed_relative_gap < 0.0:
            raise ValueError("volatility gap must be finite and non-negative")
        if not isfinite(self.max_relative_gap) or self.max_relative_gap <= 0.0:
            raise ValueError("volatility gap threshold must be finite and positive")
        _require_unique_nonblank("volatility blockers", self.blockers)
        _require_unique_nonblank("volatility citations", self.evidence_citations)
        if "LIVE_ORDER_BLOCKED" not in self.blockers:
            raise ValueError("volatility assumption review must keep live blocked")
        if "NO_TRADE_SIGNAL_AUTHORITY" not in self.blockers:
            raise ValueError("volatility assumption review cannot become a signal")
        if self.promotion_status != "RESEARCH_ONLY_VOLATILITY_ASSUMPTION":
            raise ValueError("volatility assumption review must remain research-only")
        if self.execution_allowed or self.signal_authority:
            raise ValueError("volatility assumption review cannot grant authority")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("volatility assumption review must block live trading")


def review_volatility_assumption(
    evidence: VolatilityAssumptionEvidence,
    *,
    max_relative_gap: float = 0.25,
    min_sample_size: int = 30,
) -> VolatilityAssumptionReview:
    """Classify a volatility assumption as advisory research, watchlist, or blocked."""
    if not isfinite(max_relative_gap) or max_relative_gap <= 0.0:
        raise ValueError("volatility gap threshold must be finite and positive")
    if min_sample_size < 2:
        raise ValueError("minimum volatility sample size must be at least two")

    blockers: list[str] = []
    if not evidence.evidence_citations:
        blockers.append("SOURCE_CITATION_REQUIRED")
    if evidence.sample_size < min_sample_size:
        blockers.append("VOLATILITY_SAMPLE_TOO_SMALL")
    if evidence.implied_volatility is not None:
        blockers.append("DERIVATIVES_DATA_SUPPLEMENTARY_ONLY")

    model_terms = evidence.model_family.casefold()
    if "black" in model_terms or "scholes" in model_terms or "option" in model_terms:
        blockers.append("BLACK_SCHOLES_SPOT_LIMITATION_REVIEW_REQUIRED")

    observed_relative_gap = (
        abs(evidence.realized_volatility - evidence.assumed_volatility)
        / evidence.assumed_volatility
    )
    if observed_relative_gap > max_relative_gap:
        blockers.append("VOLATILITY_ASSUMPTION_DIVERGENCE")

    hard_blockers = {
        "SOURCE_CITATION_REQUIRED",
        "VOLATILITY_SAMPLE_TOO_SMALL",
    }
    if any(blocker in hard_blockers for blocker in blockers):
        status = VolatilityAssumptionReviewStatus.BLOCKED
    elif blockers:
        status = VolatilityAssumptionReviewStatus.WATCHLIST
    else:
        status = VolatilityAssumptionReviewStatus.RESEARCH_ONLY

    blockers.extend(
        (
            "NO_TRADE_SIGNAL_AUTHORITY",
            "VOLATILITY_REVIEW_READ_ONLY",
            "LIVE_ORDER_BLOCKED",
        )
    )
    return VolatilityAssumptionReview(
        symbol=evidence.symbol,
        timeframe=evidence.timeframe,
        model_family=evidence.model_family,
        assumption_name=evidence.assumption_name,
        status=status,
        observed_relative_gap=observed_relative_gap,
        max_relative_gap=max_relative_gap,
        blockers=tuple(dict.fromkeys(blockers)),
        evidence_citations=evidence.evidence_citations,
    )


def _require_unique_nonblank(name: str, values: tuple[str, ...]) -> None:
    if len(set(values)) != len(values) or any(
        not value.strip() or len(value) > 2_000 for value in values
    ):
        raise ValueError(f"{name} must be unique, non-empty and bounded")


def _require_bounded_optional_text(**values: str) -> None:
    if any(len(value) > 2_000 for value in values.values()):
        raise ValueError("catalog optional text fields must be bounded")


@dataclass(frozen=True, slots=True)
class ResearchCatalogEntry:
    """One provenance-bound idea or dependency candidate."""

    entry_id: str
    title: str
    source_url: str
    source_revision: str
    license_id: str
    hypothesis: str
    asset_classes: tuple[str, ...]
    timeframes: tuple[str, ...]
    leakage_risks: tuple[str, ...]
    data_requirements: tuple[str, ...]
    cost_assumptions: tuple[str, ...]
    discovered_at: datetime
    updated_at: datetime
    status: CatalogStatus = CatalogStatus.DISCOVERED
    artifact_ids: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ("SOURCE_EVIDENCE_NOT_REPRODUCED",)
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        _require_text(
            entry_id=self.entry_id,
            title=self.title,
            source_url=self.source_url,
            source_revision=self.source_revision,
            license_id=self.license_id,
            hypothesis=self.hypothesis,
        )
        _require_aware(self.discovered_at)
        _require_aware(self.updated_at)
        parsed = urlparse(self.source_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username:
            raise ValueError("catalog source URL must be credential-free HTTPS")
        required_groups = (
            self.asset_classes,
            self.timeframes,
            self.leakage_risks,
            self.data_requirements,
            self.cost_assumptions,
        )
        if any(
            not group or any(not item.strip() for item in group)
            for group in required_groups
        ):
            raise ValueError("catalog evidence groups must be non-empty")
        if len(set(self.artifact_ids)) != len(self.artifact_ids):
            raise ValueError("catalog artifact identities must be unique")
        if self.status is CatalogStatus.STAGED_CANDIDATE and self.blockers:
            raise ValueError("staged catalog candidate cannot contain blockers")
        if self.status is CatalogStatus.PAPER_APPROVED and not self.artifact_ids:
            raise ValueError("paper approval requires immutable artifacts")
        if self.execution_allowed:
            raise ValueError("research catalog cannot authorize execution")

    def transition(
        self,
        status: CatalogStatus,
        *,
        updated_at: datetime,
        artifact_ids: tuple[str, ...] = (),
        blockers: tuple[str, ...] = (),
        human_approved: bool = False,
    ) -> ResearchCatalogEntry:
        """Apply an explicit lifecycle transition; paper approval is human-only."""
        if status not in _TRANSITIONS[self.status]:
            raise ValueError(f"invalid catalog transition: {self.status}->{status}")
        _require_aware(updated_at)
        if status is CatalogStatus.PAPER_APPROVED and not human_approved:
            raise ValueError("paper approval requires explicit human approval")
        merged = tuple(dict.fromkeys((*self.artifact_ids, *artifact_ids)))
        return replace(
            self,
            status=status,
            updated_at=updated_at,
            artifact_ids=merged,
            blockers=blockers,
        )


@dataclass(frozen=True, slots=True)
class TechnologyAssessment:
    """Pre-install evaluation; approval still creates no installation authority."""

    entry_id: str
    license_compatible: bool
    actively_maintained: bool
    canonical_python_supported: bool
    deterministic_or_seeded: bool
    lookahead_reviewed: bool
    security_reviewed: bool
    benchmark_gain_percent: float | None
    removal_cost_documented: bool
    blockers: tuple[str, ...]
    approved_for_experiment: bool
    installation_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.entry_id.strip():
            raise ValueError("technology assessment identity is required")
        if self.benchmark_gain_percent is not None and not (
            -100.0 <= self.benchmark_gain_percent <= 100_000.0
        ):
            raise ValueError("technology benchmark gain is invalid")
        if self.approved_for_experiment == bool(self.blockers):
            raise ValueError("technology assessment and blockers disagree")
        if self.installation_allowed:
            raise ValueError("technology assessment cannot install dependencies")


def assess_technology_candidate(
    *,
    entry_id: str,
    license_compatible: bool,
    actively_maintained: bool,
    canonical_python_supported: bool,
    deterministic_or_seeded: bool,
    lookahead_reviewed: bool,
    security_reviewed: bool,
    benchmark_gain_percent: float | None,
    removal_cost_documented: bool,
) -> TechnologyAssessment:
    checks = (
        (license_compatible, "LICENSE_INCOMPATIBLE_OR_UNKNOWN"),
        (actively_maintained, "MAINTENANCE_STATUS_WEAK"),
        (canonical_python_supported, "CANONICAL_PYTHON_UNSUPPORTED"),
        (deterministic_or_seeded, "DETERMINISM_NOT_PROVEN"),
        (lookahead_reviewed, "LOOKAHEAD_RISK_NOT_REVIEWED"),
        (security_reviewed, "SECURITY_REVIEW_MISSING"),
        (benchmark_gain_percent is not None, "BENCHMARK_EVIDENCE_MISSING"),
        (removal_cost_documented, "REMOVAL_COST_UNDOCUMENTED"),
    )
    blockers = tuple(code for passed, code in checks if not passed)
    return TechnologyAssessment(
        entry_id,
        license_compatible,
        actively_maintained,
        canonical_python_supported,
        deterministic_or_seeded,
        lookahead_reviewed,
        security_reviewed,
        benchmark_gain_percent,
        removal_cost_documented,
        blockers,
        not blockers,
    )


@dataclass(frozen=True, slots=True)
class ResearchCatalog:
    entries: tuple[ResearchCatalogEntry, ...] = ()
    ledger: JsonlAuditStore | None = field(default=None, compare=False, repr=False)

    def add(self, entry: ResearchCatalogEntry) -> ResearchCatalog:
        if any(item.entry_id == entry.entry_id for item in self.entries):
            raise ValueError("catalog entry identity already exists")
        self._record("RESEARCH_CATALOG_ENTRY_ADDED", entry)
        return ResearchCatalog((*self.entries, entry), self.ledger)

    def update(self, entry: ResearchCatalogEntry) -> ResearchCatalog:
        matches = tuple(
            index
            for index, item in enumerate(self.entries)
            if item.entry_id == entry.entry_id
        )
        if len(matches) != 1:
            raise KeyError(entry.entry_id)
        items = list(self.entries)
        items[matches[0]] = entry
        self._record("RESEARCH_CATALOG_ENTRY_TRANSITIONED", entry)
        return ResearchCatalog(tuple(items), self.ledger)

    def _record(self, event_type: str, entry: ResearchCatalogEntry) -> None:
        if self.ledger is not None:
            self.ledger.append_verified(
                AuditEvent(
                    event_type=event_type,
                    timestamp=entry.updated_at,
                    snapshot_id=entry.entry_id,
                    payload={"entry": entry},
                )
            )


@dataclass(frozen=True, slots=True)
class ReproductionQueueWriter:
    """Atomically persist only human-governed pending reproduction work."""

    path: Path

    def write(self, catalog: ResearchCatalog) -> None:
        pending = tuple(
            sorted(
                (
                    entry
                    for entry in catalog.entries
                    if entry.status is CatalogStatus.REPRODUCTION_PENDING
                ),
                key=lambda entry: entry.entry_id,
            )
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary.write_text(
            json.dumps(
                {
                    "entries": to_primitive(pending),
                    "execution_allowed": False,
                    "schema_version": "1.0",
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.path)
