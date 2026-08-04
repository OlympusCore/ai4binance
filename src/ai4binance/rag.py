"""Local second-brain RAG index, advisory provider runner and tiny UI payloads."""

from __future__ import annotations

import html
import json
import math
import re
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path

from ai4binance.agents.context_budget import TokenBudgetGuard

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]{3,}")
_SECRET_PATTERN = re.compile(
    r"(api[_-]?key|secret|token|signature|private[_-]?key|passphrase)",
    re.IGNORECASE,
)
_ALLOWED_SUFFIXES = frozenset({".md", ".json", ".jsonl", ".txt"})
_BLOCKED_PATH_PARTS = frozenset(
    {".pytest_cache", ".pytest-tmp", "TestTemp", "__pycache__"}
)
_SECOND_BRAIN_PROFILE_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:@/\\-]{4,}")
_SECOND_BRAIN_COMMON_PROFILE_TOKENS = frozenset(
    {
        "ai4binance",
        "binance",
        "codex",
        "computer",
        "docs",
        "local",
        "markdown",
        "profile",
        "python",
        "research",
        "second-brain",
        "system",
        "validation",
        "windows",
        "workspace",
    }
)
_CONTEXT_PRIVATE_PATH_PARTS = frozenset(
    {
        ".env",
        ".git",
        ".venv",
        "Computer.local.md",
        "Computer.md",
        "Secrets",
        "State",
    }
)


class ContextEngineeringReadinessStatus(StrEnum):
    WATCHLIST = "WATCHLIST"
    RESEARCH_ONLY_CONTEXT_PATTERN = "RESEARCH_ONLY_CONTEXT_PATTERN"


class RagEvidenceQualityStatus(StrEnum):
    WATCHLIST = "WATCHLIST"
    RESEARCH_ONLY_RAG_EVIDENCE = "RESEARCH_ONLY_RAG_EVIDENCE"


@dataclass(frozen=True, slots=True)
class SecondBrainPilotPolicy:
    workspace_root: str = "Artifacts/second-brain"
    raw_root: str = "Artifacts/second-brain/raw"
    wiki_root: str = "Artifacts/second-brain/wiki"
    log_path: str = "Artifacts/second-brain/log.md"
    instructions_path: str = "Artifacts/second-brain/CLAUDE.md"
    allowed_suffixes: tuple[str, ...] = (".md", ".json", ".jsonl", ".txt")
    blocked_path_parts: tuple[str, ...] = (
        ".env",
        ".git",
        ".venv",
        "Computer.local.md",
        "Computer.md",
        "Secrets",
        "State",
    )
    maximum_source_bytes: int = 128_000
    require_citations: bool = True
    require_computer_profile_scan: bool = True
    promotion_status: str = "RESEARCH_ONLY"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        for value in (
            self.workspace_root,
            self.raw_root,
            self.wiki_root,
            self.log_path,
            self.instructions_path,
        ):
            _validate_repo_relative_policy_path(value)
        if not self.allowed_suffixes or any(
            not suffix.startswith(".") for suffix in self.allowed_suffixes
        ):
            raise ValueError("second-brain allowed suffixes are invalid")
        if not self.blocked_path_parts or any(
            not value.strip() for value in self.blocked_path_parts
        ):
            raise ValueError("second-brain blocked path parts are required")
        if not 1 <= self.maximum_source_bytes <= 1_000_000:
            raise ValueError("second-brain source byte limit is invalid")
        if self.promotion_status != "RESEARCH_ONLY" or self.execution_allowed:
            raise ValueError("second-brain pilot cannot promote or execute")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("second-brain pilot must keep live trading blocked")


@dataclass(frozen=True, slots=True)
class SecondBrainSourceAdmission:
    source_uri: str
    citation: str
    content_sha256: str
    accepted: bool
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        if Path(self.source_uri).is_absolute() or not self.source_uri.strip():
            raise ValueError("second-brain source URI must be repository-relative")
        if not re.fullmatch(r"[0-9a-f]{64}", self.content_sha256):
            raise ValueError("second-brain source hash is invalid")
        if self.accepted and self.blockers:
            raise ValueError("accepted second-brain sources cannot have blockers")
        if not self.accepted and not self.blockers:
            raise ValueError("blocked second-brain sources require blockers")


@dataclass(frozen=True, slots=True)
class SecondBrainPilotAdmission:
    status: str
    workspace_root: str
    raw_root: str
    wiki_root: str
    log_path: str
    instructions_path: str
    sources: tuple[SecondBrainSourceAdmission, ...]
    blockers: tuple[str, ...]
    promotion_status: str = "RESEARCH_ONLY"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if (
            self.promotion_status != "RESEARCH_ONLY"
            or self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("second-brain admission must remain research-only")
        if self.status not in {"PASSED", "BLOCKED"}:
            raise ValueError("second-brain admission status is invalid")
        if self.status == "PASSED" and not self.sources:
            raise ValueError("passed second-brain admission requires source evidence")
        if self.status == "PASSED" and self.blockers:
            raise ValueError("passed second-brain admission cannot have blockers")
        if self.status == "BLOCKED" and not self.blockers:
            raise ValueError("blocked second-brain admission requires blockers")


@dataclass(frozen=True, slots=True)
class ContextSourceEvidence:
    """Hash-bound context source metadata; never stores source text."""

    source_uri: str
    content_sha256: str
    collected_at: datetime
    token_count: int
    citations: tuple[str, ...]
    redacted: bool = True
    private_path_detected: bool = False
    secret_marker_detected: bool = False
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if (
            Path(self.source_uri).is_absolute()
            or not self.source_uri.strip()
            or not re.fullmatch(r"[0-9a-f]{64}", self.content_sha256)
        ):
            raise ValueError("context source identity is invalid")
        if self.collected_at.tzinfo is None or self.collected_at.utcoffset() is None:
            raise ValueError("context source timestamp must be timezone-aware")
        if not 1 <= self.token_count <= 1_000_000:
            raise ValueError("context source token count is invalid")
        _require_unique_nonblank("context source citations", self.citations)
        if self.execution_allowed:
            raise ValueError("context source cannot authorize execution")


@dataclass(frozen=True, slots=True)
class ContextEngineeringReadinessEvidence:
    """Inputs for reviewing a prompt/context pack before advisory model use."""

    context_pack_id: str
    task_id: str
    sources: tuple[ContextSourceEvidence, ...]
    prompt_sections: tuple[str, ...]
    retrieval_strategy: str
    max_context_tokens: int
    output_reserve_tokens: int
    instruction_tokens: int
    history_tokens: int = 0
    tool_schema_tokens: int = 0
    privacy_scan_passed: bool = True
    redaction_required: bool = True
    human_review_required: bool = True
    execution_allowed: bool = False
    llm_signal_authority: bool = False

    def __post_init__(self) -> None:
        if (
            not self.context_pack_id.strip()
            or not self.task_id.strip()
            or not self.retrieval_strategy.strip()
        ):
            raise ValueError("context readiness evidence identity is required")
        _require_unique_nonblank("context prompt sections", self.prompt_sections)
        source_uris = tuple(source.source_uri for source in self.sources)
        _require_unique_nonblank("context source URIs", source_uris)
        token_limits = (
            self.max_context_tokens,
            self.output_reserve_tokens,
            self.instruction_tokens,
            self.history_tokens,
            self.tool_schema_tokens,
        )
        if any(value < 0 for value in token_limits) or self.max_context_tokens < 2:
            raise ValueError("context token budgets are invalid")
        if self.output_reserve_tokens >= self.max_context_tokens:
            raise ValueError("context output reserve must fit the context window")
        if self.execution_allowed or self.llm_signal_authority:
            raise ValueError("context readiness evidence cannot grant authority")

    @property
    def source_tokens(self) -> int:
        return sum(source.token_count for source in self.sources)

    @property
    def used_tokens(self) -> int:
        return (
            self.instruction_tokens
            + self.history_tokens
            + self.tool_schema_tokens
            + self.source_tokens
        )


@dataclass(frozen=True, slots=True)
class ContextEngineeringReadinessReview:
    context_pack_id: str
    task_id: str
    status: ContextEngineeringReadinessStatus
    blockers: tuple[str, ...]
    source_uris: tuple[str, ...]
    source_sha256: tuple[str, ...]
    citation_count: int
    used_tokens: int
    max_context_tokens: int
    output_reserve_tokens: int
    promotion_status: str = "RESEARCH_ONLY_CONTEXT_PATTERN"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.context_pack_id.strip() or not self.task_id.strip():
            raise ValueError("context readiness review identity is required")
        for values in (self.blockers, self.source_uris, self.source_sha256):
            _require_unique_nonblank("context readiness review lists", values)
        if any(
            not re.fullmatch(r"[0-9a-f]{64}", digest) for digest in self.source_sha256
        ):
            raise ValueError("context readiness review source hash is invalid")
        if self.citation_count < 0:
            raise ValueError("context readiness citation count is invalid")
        if (
            self.used_tokens < 0
            or self.max_context_tokens < 2
            or self.output_reserve_tokens >= self.max_context_tokens
        ):
            raise ValueError("context readiness token budgets are invalid")
        if "HUMAN_REVIEW_REQUIRED" not in self.blockers:
            raise ValueError("context readiness review requires human review")
        if "LIVE_ORDER_BLOCKED" not in self.blockers:
            raise ValueError("context readiness review must keep live blocker visible")
        if (
            self.promotion_status != "RESEARCH_ONLY_CONTEXT_PATTERN"
            or self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("context readiness review cannot promote or execute")


def assess_second_brain_pilot(
    repository_root: Path,
    source_paths: tuple[Path, ...],
    *,
    citations: tuple[str, ...] = (),
    policy: SecondBrainPilotPolicy | None = None,
    computer_md: Path | None = None,
) -> SecondBrainPilotAdmission:
    policy = policy or SecondBrainPilotPolicy()
    repository = repository_root.resolve(strict=False)
    profile_path = (computer_md or repository / "Computer.md").resolve(strict=False)
    profile_candidates, profile_blocker = _second_brain_profile_candidates(
        profile_path,
        required=policy.require_computer_profile_scan,
    )
    admitted: list[SecondBrainSourceAdmission] = []
    root_blockers: list[str] = []
    if profile_blocker is not None:
        root_blockers.append(profile_blocker)
    if not source_paths:
        root_blockers.append("SECOND_BRAIN_SOURCE_REQUIRED")
    for index, source_path in enumerate(source_paths):
        citation = citations[index] if index < len(citations) else ""
        admitted.append(
            _assess_second_brain_source(
                repository,
                source_path,
                citation=citation,
                policy=policy,
                profile_candidates=profile_candidates,
            )
        )
    source_blockers = tuple(blocker for item in admitted for blocker in item.blockers)
    blockers = tuple(dict.fromkeys((*root_blockers, *source_blockers)))
    return SecondBrainPilotAdmission(
        status="BLOCKED" if blockers else "PASSED",
        workspace_root=policy.workspace_root,
        raw_root=policy.raw_root,
        wiki_root=policy.wiki_root,
        log_path=policy.log_path,
        instructions_path=policy.instructions_path,
        sources=tuple(admitted),
        blockers=blockers,
    )


def review_context_engineering_readiness(
    evidence: ContextEngineeringReadinessEvidence,
    *,
    now: datetime,
    max_source_age_days: int = 14,
) -> ContextEngineeringReadinessReview:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("context readiness review time must be timezone-aware")
    if max_source_age_days < 1:
        raise ValueError("context source age limit is invalid")
    blockers: list[str] = []
    if not evidence.sources:
        blockers.append("CONTEXT_SOURCE_REQUIRED")
    if not evidence.prompt_sections:
        blockers.append("CONTEXT_PROMPT_SECTION_REQUIRED")
    if evidence.retrieval_strategy.casefold() not in {
        "just-in-time",
        "artifact-gated",
        "metadata-filtered",
    }:
        blockers.append("CONTEXT_RETRIEVAL_STRATEGY_REVIEW_REQUIRED")
    if (
        evidence.used_tokens + evidence.output_reserve_tokens
        > evidence.max_context_tokens
    ):
        blockers.append("CONTEXT_TOKEN_BUDGET_EXCEEDED")
    if not evidence.privacy_scan_passed:
        blockers.append("CONTEXT_PRIVACY_SCAN_REQUIRED")
    if not evidence.human_review_required:
        blockers.append("CONTEXT_HUMAN_REVIEW_REQUIRED")
    for source in evidence.sources:
        if not source.citations:
            blockers.append("CONTEXT_CITATION_REQUIRED")
        if evidence.redaction_required and not source.redacted:
            blockers.append("CONTEXT_REDACTION_REQUIRED")
        if source.private_path_detected or _has_private_context_path(source.source_uri):
            blockers.append("CONTEXT_PRIVATE_PATH_BLOCKED")
        if source.secret_marker_detected or _SECRET_PATTERN.search(source.source_uri):
            blockers.append("CONTEXT_SECRET_MARKER_BLOCKED")
        if source.collected_at > now:
            blockers.append("CONTEXT_SOURCE_FROM_FUTURE")
        elif (now - source.collected_at).days > max_source_age_days:
            blockers.append("CONTEXT_SOURCE_STALE")
    blockers.extend(("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED"))
    hard_blockers = {
        "CONTEXT_SOURCE_REQUIRED",
        "CONTEXT_PROMPT_SECTION_REQUIRED",
        "CONTEXT_TOKEN_BUDGET_EXCEEDED",
        "CONTEXT_PRIVACY_SCAN_REQUIRED",
        "CONTEXT_HUMAN_REVIEW_REQUIRED",
        "CONTEXT_CITATION_REQUIRED",
        "CONTEXT_REDACTION_REQUIRED",
        "CONTEXT_PRIVATE_PATH_BLOCKED",
        "CONTEXT_SECRET_MARKER_BLOCKED",
        "CONTEXT_SOURCE_FROM_FUTURE",
        "CONTEXT_SOURCE_STALE",
    }
    status = (
        ContextEngineeringReadinessStatus.WATCHLIST
        if any(blocker in hard_blockers for blocker in blockers)
        else ContextEngineeringReadinessStatus.RESEARCH_ONLY_CONTEXT_PATTERN
    )
    citations = tuple(
        citation for source in evidence.sources for citation in source.citations
    )
    return ContextEngineeringReadinessReview(
        context_pack_id=evidence.context_pack_id,
        task_id=evidence.task_id,
        status=status,
        blockers=tuple(dict.fromkeys(blockers)),
        source_uris=tuple(source.source_uri for source in evidence.sources),
        source_sha256=tuple(source.content_sha256 for source in evidence.sources),
        citation_count=len(set(citations)),
        used_tokens=evidence.used_tokens,
        max_context_tokens=evidence.max_context_tokens,
        output_reserve_tokens=evidence.output_reserve_tokens,
    )


@dataclass(frozen=True, slots=True)
class RagFragment:
    fragment_id: str
    source_uri: str
    content_sha256: str
    collected_at: datetime
    text: str
    token_counts: tuple[tuple[str, int], ...]
    authority: str = "READ_ONLY"
    classification: str = "PUBLIC_RESEARCH"
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if (
            not self.fragment_id.strip()
            or not self.source_uri.strip()
            or not re.fullmatch(r"[0-9a-f]{64}", self.content_sha256)
        ):
            raise ValueError("RAG fragment identity is invalid")
        if self.collected_at.tzinfo is None or self.collected_at.utcoffset() is None:
            raise ValueError("RAG fragment timestamp must be timezone-aware")
        if not self.text.strip() or _SECRET_PATTERN.search(self.text):
            raise ValueError("RAG fragment text is empty or restricted")
        if self.execution_allowed:
            raise ValueError("RAG fragments cannot authorize execution")


@dataclass(frozen=True, slots=True)
class RagSearchHit:
    fragment_id: str
    source_uri: str
    score: float
    excerpt: str
    content_sha256: str
    collected_at: datetime
    authority: str = "READ_ONLY"
    classification: str = "PUBLIC_RESEARCH"

    def __post_init__(self) -> None:
        if (
            not self.fragment_id.strip()
            or not self.source_uri.strip()
            or not re.fullmatch(r"[0-9a-f]{64}", self.content_sha256)
        ):
            raise ValueError("RAG search hit identity is invalid")
        if not math.isfinite(self.score) or self.score < 0.0:
            raise ValueError("RAG search hit score must be finite and non-negative")
        if not self.excerpt.strip() or _SECRET_PATTERN.search(self.excerpt):
            raise ValueError("RAG search hit excerpt is empty or restricted")
        if self.collected_at.tzinfo is None or self.collected_at.utcoffset() is None:
            raise ValueError("RAG search hit timestamp must be timezone-aware")
        if not self.authority.strip() or not self.classification.strip():
            raise ValueError("RAG search hit metadata is required")


@dataclass(frozen=True, slots=True)
class RagEvidenceQualityReview:
    query_id: str
    status: RagEvidenceQualityStatus
    blockers: tuple[str, ...]
    accepted_hit_ids: tuple[str, ...]
    rejected_hit_ids: tuple[str, ...]
    source_uris: tuple[str, ...]
    source_sha256: tuple[str, ...]
    citation_coverage: float
    minimum_score: float
    minimum_citation_coverage: float
    promotion_status: str = "RESEARCH_ONLY_RAG_EVIDENCE"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.query_id.strip():
            raise ValueError("RAG evidence quality query id is required")
        for values in (
            self.blockers,
            self.accepted_hit_ids,
            self.rejected_hit_ids,
            self.source_uris,
            self.source_sha256,
        ):
            _require_unique_nonblank("RAG evidence quality lists", values)
        if any(
            not re.fullmatch(r"[0-9a-f]{64}", digest) for digest in self.source_sha256
        ):
            raise ValueError("RAG evidence quality source hash is invalid")
        if (
            not 0.0 <= self.citation_coverage <= 1.0
            or not 0.0 <= self.minimum_score <= 1.0
            or not 0.0 <= self.minimum_citation_coverage <= 1.0
        ):
            raise ValueError("RAG evidence quality thresholds are invalid")
        if "HUMAN_REVIEW_REQUIRED" not in self.blockers:
            raise ValueError("RAG evidence quality requires human review")
        if "LIVE_ORDER_BLOCKED" not in self.blockers:
            raise ValueError("RAG evidence quality must keep live blocker visible")
        if (
            self.promotion_status != "RESEARCH_ONLY_RAG_EVIDENCE"
            or self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("RAG evidence quality cannot promote or execute")


@dataclass(frozen=True, slots=True)
class RagIndex:
    index_id: str
    created_at: datetime
    fragments: tuple[RagFragment, ...]
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.index_id.startswith("rag:") or not self.fragments:
            raise ValueError("RAG index identity and fragments are required")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("RAG index timestamp must be timezone-aware")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("RAG index cannot authorize live execution")

    def query(
        self,
        text: str,
        *,
        limit: int = 5,
        source_prefixes: tuple[str, ...] = (),
        authorities: tuple[str, ...] = (),
        classifications: tuple[str, ...] = (),
    ) -> tuple[RagSearchHit, ...]:
        if not text.strip():
            raise ValueError("RAG query is required")
        if not 1 <= limit <= 20:
            raise ValueError("RAG query limit is invalid")
        for values in (source_prefixes, authorities, classifications):
            _require_unique_nonblank("RAG query metadata filters", values)
        query_counts = Counter(_tokens(text))
        scored = tuple(
            hit
            for fragment in self.fragments
            if _fragment_matches_metadata(
                fragment,
                source_prefixes=source_prefixes,
                authorities=authorities,
                classifications=classifications,
            )
            if (hit := _score_fragment(query_counts, fragment)).score > 0.0
        )
        return tuple(
            sorted(scored, key=lambda item: (-item.score, item.source_uri))[:limit]
        )

    def write(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        payload = {
            "schema_version": "1.0",
            "index_id": self.index_id,
            "created_at": self.created_at.isoformat(),
            "fragments": [asdict(fragment) for fragment in self.fragments],
            "execution_allowed": self.execution_allowed,
            "live_eligibility_status": self.live_eligibility_status,
        }
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
        return path


@dataclass(frozen=True, slots=True)
class LocalRagIndexer:
    repository_root: Path
    allowed_roots: tuple[str, ...] = (
        "Docs",
        "Artifacts",
        "Backtest/validation",
        "Data/market",
        "Logs",
    )
    maximum_file_bytes: int = 256_000
    maximum_fragments: int = 1_000

    def build(self, *, now: datetime | None = None) -> RagIndex:
        timestamp = now or datetime.now(UTC)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("RAG index timestamp must be timezone-aware")
        repository_root = self.repository_root.resolve(strict=False)
        fragments: list[RagFragment] = []
        for root_name in self.allowed_roots:
            root = (repository_root / root_name).resolve(strict=False)
            if not _is_within(root, repository_root):
                raise ValueError("RAG root escapes repository")
            if not root.exists():
                continue
            for path in sorted(root.rglob("*")):
                if len(fragments) >= self.maximum_fragments:
                    break
                if not self._accepts(path, repository_root):
                    continue
                raw = path.read_bytes()
                if _SECRET_PATTERN.search(path.as_posix()) or _SECRET_PATTERN.search(
                    raw.decode("utf-8", errors="ignore")
                ):
                    continue
                text = raw.decode("utf-8", errors="ignore").strip()
                if not text:
                    continue
                fragments.append(_fragment(repository_root, path, text, timestamp))
        if not fragments:
            raise ValueError("RAG index has no approved fragments")
        digest = sha256(
            "\n".join(item.content_sha256 for item in fragments).encode("utf-8")
        ).hexdigest()[:24]
        return RagIndex(f"rag:{digest}", timestamp, tuple(fragments))

    def _accepts(self, path: Path, repository_root: Path) -> bool:
        try:
            relative_parts = path.relative_to(repository_root).parts
        except ValueError:
            return False
        return (
            path.is_file()
            and path.suffix.lower() in _ALLOWED_SUFFIXES
            and not any(part in _BLOCKED_PATH_PARTS for part in relative_parts)
            and path.stat().st_size <= self.maximum_file_bytes
        )


@dataclass(frozen=True, slots=True)
class AdvisoryProviderResult:
    provider: str
    model: str
    prompt_sha256: str
    response_text: str
    citations: tuple[str, ...]
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("advisory provider cannot authorize execution")


@dataclass(frozen=True, slots=True)
class AdvisoryProviderGuard:
    max_prompt_chars: int = 16_000
    max_response_bytes: int = 1_000_000
    minimum_timeout_seconds: float = 0.01
    maximum_timeout_seconds: float = 180.0
    token_budget_guard: TokenBudgetGuard | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.max_prompt_chars <= 64_000:
            raise ValueError("advisory provider prompt limit is invalid")
        if not 1_024 <= self.max_response_bytes <= 5_000_000:
            raise ValueError("advisory provider response limit is invalid")
        if not 0 < self.minimum_timeout_seconds <= self.maximum_timeout_seconds:
            raise ValueError("advisory provider timeout range is invalid")

    def validate_request(self, prompt: str, timeout_seconds: float) -> None:
        if not prompt.strip():
            raise ValueError("advisory prompt is required")
        if len(prompt) > self.max_prompt_chars:
            raise ValueError("advisory prompt exceeds bounded context")
        if self.token_budget_guard is not None:
            usage = self.token_budget_guard.measure(
                system="",
                current_input=prompt,
                history="",
                context="",
                tool_schemas="",
            )
            self.token_budget_guard.validate(usage)
        if (
            not self.minimum_timeout_seconds
            <= timeout_seconds
            <= self.maximum_timeout_seconds
        ):
            raise ValueError("advisory timeout is outside policy")


@dataclass(frozen=True, slots=True)
class LlamaCppAdvisoryRunner:
    base_url: str = "http://127.0.0.1:8080"
    model: str = "qwen3:8b"
    timeout_seconds: float = 30.0
    guard: AdvisoryProviderGuard = AdvisoryProviderGuard()

    def run(
        self,
        prompt: str,
        hits: tuple[RagSearchHit, ...],
    ) -> AdvisoryProviderResult:
        self.guard.validate_request(prompt, self.timeout_seconds)
        parsed = urllib.parse.urlsplit(self.base_url.rstrip("/"))
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
            raise ValueError("llama.cpp advisory runner must be loopback-only")
        citations = tuple(hit.source_uri for hit in hits)
        body = json.dumps(
            {
                "prompt": prompt,
                "temperature": 0,
                "n_predict": 384,
                "stop": ["</s>"],
            },
            sort_keys=True,
        ).encode("utf-8")
        request = urllib.request.Request(  # noqa: S310 - loopback-only URL.
            f"{parsed.geturl().rstrip('/')}/completion",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        prompt_hash = sha256(prompt.encode("utf-8")).hexdigest()
        try:
            with urllib.request.urlopen(  # noqa: S310  # nosec B310
                request,
                timeout=self.timeout_seconds,
            ) as response:
                payload = json.loads(response.read(self.guard.max_response_bytes))
        except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            return AdvisoryProviderResult(
                "llama.cpp",
                self.model,
                prompt_hash,
                "",
                citations,
                ("LOCAL_LLM_PROVIDER_UNAVAILABLE", "ADVISORY_ONLY"),
            )
        content = payload.get("content") if isinstance(payload, dict) else None
        text = content.strip() if isinstance(content, str) else ""
        blockers = ("ADVISORY_ONLY",) if text else ("LOCAL_LLM_EMPTY_RESPONSE",)
        return AdvisoryProviderResult(
            "llama.cpp",
            self.model,
            prompt_hash,
            text,
            citations,
            blockers,
        )


@dataclass(frozen=True, slots=True)
class OllamaAdvisoryRunner:
    base_url: str = "http://127.0.0.1:11434"
    model: str = "qwen3:8b"
    timeout_seconds: float = 30.0
    guard: AdvisoryProviderGuard = AdvisoryProviderGuard()

    def run(
        self,
        prompt: str,
        hits: tuple[RagSearchHit, ...],
    ) -> AdvisoryProviderResult:
        self.guard.validate_request(prompt, self.timeout_seconds)
        parsed = urllib.parse.urlsplit(self.base_url.rstrip("/"))
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
            raise ValueError("Ollama advisory runner must be loopback-only")
        citations = tuple(hit.source_uri for hit in hits)
        body = json.dumps(
            {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "think": False,
                "options": {"temperature": 0, "num_predict": 384},
            },
            sort_keys=True,
        ).encode("utf-8")
        request = urllib.request.Request(  # noqa: S310 - loopback-only URL.
            f"{parsed.geturl().rstrip('/')}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        prompt_hash = sha256(prompt.encode("utf-8")).hexdigest()
        try:
            with urllib.request.urlopen(  # noqa: S310  # nosec B310
                request,
                timeout=self.timeout_seconds,
            ) as response:
                payload = json.loads(response.read(self.guard.max_response_bytes))
        except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            return AdvisoryProviderResult(
                "ollama",
                self.model,
                prompt_hash,
                "",
                citations,
                ("LOCAL_LLM_PROVIDER_UNAVAILABLE", "ADVISORY_ONLY"),
            )
        content = payload.get("response") if isinstance(payload, dict) else None
        text = content.strip() if isinstance(content, str) else ""
        blockers = ("ADVISORY_ONLY",) if text else ("LOCAL_LLM_EMPTY_RESPONSE",)
        return AdvisoryProviderResult(
            "ollama",
            self.model,
            prompt_hash,
            text,
            citations,
            blockers,
        )


def render_rag_ui(index: RagIndex, hits: tuple[RagSearchHit, ...]) -> str:
    items = "\n".join(
        "<li><code>"
        + html.escape(hit.source_uri)
        + "</code> score="
        + f"{hit.score:.3f}"
        + "<p>"
        + html.escape(hit.excerpt)
        + "</p></li>"
        for hit in hits
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>AI4BINANCE Second Brain</title></head><body>"
        f"<h1>AI4BINANCE Second Brain</h1><p>{html.escape(index.index_id)}</p>"
        f"<p>execution_allowed=false | LIVE_ORDER_BLOCKED</p><ol>{items}</ol>"
        "</body></html>"
    )


def review_rag_evidence_quality(
    *,
    query_id: str,
    hits: tuple[RagSearchHit, ...],
    citations: tuple[str, ...],
    now: datetime,
    max_source_age_days: int = 14,
    minimum_score: float = 0.35,
    minimum_citation_coverage: float = 1.0,
) -> RagEvidenceQualityReview:
    if not query_id.strip():
        raise ValueError("RAG evidence quality query id is required")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("RAG evidence quality time must be timezone-aware")
    if max_source_age_days < 1:
        raise ValueError("RAG evidence quality source age limit is invalid")
    if not 0.0 <= minimum_score <= 1.0:
        raise ValueError("RAG evidence quality minimum score is invalid")
    if not 0.0 <= minimum_citation_coverage <= 1.0:
        raise ValueError("RAG evidence quality citation threshold is invalid")
    _require_unique_nonblank("RAG evidence quality citations", citations)

    blockers: list[str] = []
    accepted_hit_ids: list[str] = []
    rejected_hit_ids: list[str] = []
    if not hits:
        blockers.append("RAG_RETRIEVAL_EMPTY")
    if not citations:
        blockers.append("RAG_CITATION_REQUIRED")
    citation_set = frozenset(citations)
    cited_hit_count = 0
    for hit in hits:
        hit_blocked = False
        if _hit_is_cited(hit, citation_set):
            cited_hit_count += 1
        else:
            hit_blocked = True
        if hit.score < minimum_score:
            blockers.append("RAG_RETRIEVAL_SCORE_LOW")
            hit_blocked = True
        if hit.collected_at > now:
            blockers.append("RAG_SOURCE_FROM_FUTURE")
            hit_blocked = True
        elif (now - hit.collected_at).days > max_source_age_days:
            blockers.append("RAG_SOURCE_STALE")
            hit_blocked = True
        if _has_private_context_path(hit.source_uri):
            blockers.append("RAG_PRIVATE_PATH_BLOCKED")
            hit_blocked = True
        if _SECRET_PATTERN.search(hit.source_uri) or _SECRET_PATTERN.search(
            hit.excerpt
        ):
            blockers.append("RAG_SECRET_MARKER_BLOCKED")
            hit_blocked = True
        if hit.authority.casefold() not in {"read_only", "research_only"}:
            blockers.append("RAG_AUTHORITY_NOT_READ_ONLY")
            hit_blocked = True
        if hit.classification.casefold() in {"restricted", "secret", "private"}:
            blockers.append("RAG_CLASSIFICATION_BLOCKED")
            hit_blocked = True
        if hit_blocked:
            rejected_hit_ids.append(hit.fragment_id)
        else:
            accepted_hit_ids.append(hit.fragment_id)
    citation_coverage = cited_hit_count / len(hits) if hits else 0.0
    if citation_coverage < minimum_citation_coverage:
        blockers.append("RAG_CITATION_COVERAGE_INSUFFICIENT")
    if hits and not accepted_hit_ids:
        blockers.append("RAG_EVIDENCE_QUALITY_BLOCKED")
    blockers.extend(("HUMAN_REVIEW_REQUIRED", "LIVE_ORDER_BLOCKED"))
    hard_blockers = {
        "RAG_RETRIEVAL_EMPTY",
        "RAG_CITATION_REQUIRED",
        "RAG_CITATION_COVERAGE_INSUFFICIENT",
        "RAG_RETRIEVAL_SCORE_LOW",
        "RAG_SOURCE_FROM_FUTURE",
        "RAG_SOURCE_STALE",
        "RAG_PRIVATE_PATH_BLOCKED",
        "RAG_SECRET_MARKER_BLOCKED",
        "RAG_AUTHORITY_NOT_READ_ONLY",
        "RAG_CLASSIFICATION_BLOCKED",
        "RAG_EVIDENCE_QUALITY_BLOCKED",
    }
    normalized_blockers = tuple(dict.fromkeys(blockers))
    status = (
        RagEvidenceQualityStatus.WATCHLIST
        if any(blocker in hard_blockers for blocker in normalized_blockers)
        else RagEvidenceQualityStatus.RESEARCH_ONLY_RAG_EVIDENCE
    )
    return RagEvidenceQualityReview(
        query_id=query_id,
        status=status,
        blockers=normalized_blockers,
        accepted_hit_ids=tuple(dict.fromkeys(accepted_hit_ids)),
        rejected_hit_ids=tuple(dict.fromkeys(rejected_hit_ids)),
        source_uris=tuple(dict.fromkeys(hit.source_uri for hit in hits)),
        source_sha256=tuple(dict.fromkeys(hit.content_sha256 for hit in hits)),
        citation_coverage=citation_coverage,
        minimum_score=minimum_score,
        minimum_citation_coverage=minimum_citation_coverage,
    )


def _assess_second_brain_source(
    repository_root: Path,
    source_path: Path,
    *,
    citation: str,
    policy: SecondBrainPilotPolicy,
    profile_candidates: frozenset[str],
) -> SecondBrainSourceAdmission:
    candidate = (
        source_path if source_path.is_absolute() else repository_root / source_path
    ).resolve(strict=False)
    blockers: list[str] = []
    if not _is_within(candidate, repository_root):
        blockers.append("SECOND_BRAIN_SOURCE_ESCAPES_REPOSITORY")
        source_uri = source_path.name or "unknown"
    else:
        source_uri = candidate.relative_to(repository_root).as_posix()
    relative_parts = tuple(part.casefold() for part in Path(source_uri).parts)
    blocked_parts = tuple(part.casefold() for part in policy.blocked_path_parts)
    if any(part in blocked_parts for part in relative_parts):
        blockers.append("SECOND_BRAIN_PRIVATE_PATH_BLOCKED")
    if candidate.suffix.lower() not in policy.allowed_suffixes:
        blockers.append("SECOND_BRAIN_SUFFIX_BLOCKED")
    if policy.require_citations and not citation.strip():
        blockers.append("SECOND_BRAIN_CITATION_REQUIRED")
    raw = b""
    if not candidate.is_file():
        blockers.append("SECOND_BRAIN_SOURCE_NOT_FOUND")
    else:
        try:
            size = candidate.stat().st_size
            if size > policy.maximum_source_bytes:
                blockers.append("SECOND_BRAIN_SOURCE_TOO_LARGE")
            raw = candidate.read_bytes()[: policy.maximum_source_bytes + 1]
        except OSError:
            blockers.append("SECOND_BRAIN_SOURCE_UNREADABLE")
    text = raw.decode("utf-8", errors="ignore")
    if _SECRET_PATTERN.search(source_uri) or _SECRET_PATTERN.search(text):
        blockers.append("SECOND_BRAIN_SECRET_MARKER_BLOCKED")
    if profile_candidates and any(token in text for token in profile_candidates):
        blockers.append("SECOND_BRAIN_COMPUTER_PROFILE_TOKEN_BLOCKED")
    return SecondBrainSourceAdmission(
        source_uri=source_uri,
        citation=citation.strip(),
        content_sha256=sha256(raw).hexdigest(),
        accepted=not blockers,
        blockers=tuple(dict.fromkeys(blockers)),
    )


def _second_brain_profile_candidates(
    computer_md: Path,
    *,
    required: bool,
) -> tuple[frozenset[str], str | None]:
    if not required:
        return frozenset(), None
    if not computer_md.is_file():
        return frozenset(), "SECOND_BRAIN_COMPUTER_MD_NOT_FOUND"
    try:
        text = computer_md.read_text(encoding="utf-8")
    except OSError:
        return frozenset(), "SECOND_BRAIN_COMPUTER_MD_UNREADABLE"
    return (
        frozenset(
            token
            for token in _SECOND_BRAIN_PROFILE_TOKEN.findall(text)
            if _is_second_brain_profile_token(token)
        ),
        None,
    )


def _is_second_brain_profile_token(token: str) -> bool:
    normalized = token.casefold().strip("`'\"()[]{}.,;:")
    if len(normalized) < 5 or normalized in _SECOND_BRAIN_COMMON_PROFILE_TOKENS:
        return False
    return any(character.isdigit() for character in token) or any(
        marker in token for marker in (":", "\\", "/", "-", "_", ".")
    )


def _validate_repo_relative_policy_path(value: str) -> None:
    path = Path(value)
    if path.is_absolute() or not value.strip() or ".." in path.parts:
        raise ValueError("second-brain policy paths must be repository-relative")


def _has_private_context_path(source_uri: str) -> bool:
    parts = tuple(part.casefold() for part in Path(source_uri).parts)
    private_parts = tuple(part.casefold() for part in _CONTEXT_PRIVATE_PATH_PARTS)
    return any(part in private_parts for part in parts)


def _require_unique_nonblank(name: str, values: tuple[str, ...]) -> None:
    if len(set(values)) != len(values) or any(
        not value.strip() or len(value) > 2_000 for value in values
    ):
        raise ValueError(f"{name} must be unique, non-empty and bounded")


def _fragment(
    repository_root: Path,
    path: Path,
    text: str,
    collected_at: datetime,
) -> RagFragment:
    digest = sha256(text.encode("utf-8")).hexdigest()
    relative = path.relative_to(repository_root).as_posix()
    excerpt = text[:2_000]
    counts = tuple(sorted(Counter(_tokens(excerpt)).items()))
    return RagFragment(
        fragment_id=f"fragment:{digest[:24]}",
        source_uri=relative,
        content_sha256=digest,
        collected_at=collected_at,
        text=excerpt,
        token_counts=counts,
    )


def _fragment_matches_metadata(
    fragment: RagFragment,
    *,
    source_prefixes: tuple[str, ...],
    authorities: tuple[str, ...],
    classifications: tuple[str, ...],
) -> bool:
    return (
        (
            not source_prefixes
            or any(fragment.source_uri.startswith(prefix) for prefix in source_prefixes)
        )
        and (
            not authorities
            or fragment.authority.casefold()
            in {authority.casefold() for authority in authorities}
        )
        and (
            not classifications
            or fragment.classification.casefold()
            in {classification.casefold() for classification in classifications}
        )
    )


def _score_fragment(query_counts: Counter[str], fragment: RagFragment) -> RagSearchHit:
    fragment_counts = Counter(dict(fragment.token_counts))
    numerator = sum(
        query_counts[token] * fragment_counts[token] for token in query_counts
    )
    query_norm = math.sqrt(sum(value * value for value in query_counts.values()))
    fragment_norm = math.sqrt(sum(value * value for value in fragment_counts.values()))
    score = (
        numerator / (query_norm * fragment_norm)
        if query_norm and fragment_norm
        else 0.0
    )
    return RagSearchHit(
        fragment.fragment_id,
        fragment.source_uri,
        score,
        fragment.text[:320],
        fragment.content_sha256,
        fragment.collected_at,
        fragment.authority,
        fragment.classification,
    )


def _hit_is_cited(hit: RagSearchHit, citations: frozenset[str]) -> bool:
    return any(
        value in citations
        for value in (
            hit.fragment_id,
            hit.source_uri,
            hit.content_sha256,
            f"{hit.source_uri}#{hit.content_sha256[:12]}",
        )
    )


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(token.lower() for token in _TOKEN_PATTERN.findall(text))


def _is_within(path: Path, root: Path) -> bool:
    candidate = path.resolve(strict=False)
    resolved_root = root.resolve(strict=False)
    return candidate == resolved_root or resolved_root in candidate.parents
