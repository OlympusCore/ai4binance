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

    def query(self, text: str, *, limit: int = 5) -> tuple[RagSearchHit, ...]:
        if not text.strip():
            raise ValueError("RAG query is required")
        if not 1 <= limit <= 20:
            raise ValueError("RAG query limit is invalid")
        query_counts = Counter(_tokens(text))
        scored = tuple(
            hit
            for fragment in self.fragments
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
    )


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(token.lower() for token in _TOKEN_PATTERN.findall(text))


def _is_within(path: Path, root: Path) -> bool:
    candidate = path.resolve(strict=False)
    resolved_root = root.resolve(strict=False)
    return candidate == resolved_root or resolved_root in candidate.parents
