"""Conservative text-only risk indicators for pinned repository evidence."""

from __future__ import annotations

import re

from ai4binance.github_radar.models import FetchedDocument

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "POSSIBLE_FUTURE_INDEX_ACCESS",
        re.compile(r"shift\s*\(\s*-|iloc\s*\[[^]]*\+\s*1"),
    ),
    ("POSSIBLE_CENTERED_WINDOW", re.compile(r"center\s*=\s*True")),
    ("DYNAMIC_CODE_EXECUTION_SURFACE", re.compile(r"\b(?:eval|exec)\s*\(")),
    ("SUBPROCESS_EXECUTION_SURFACE", re.compile(r"\bsubprocess\.|\bos\.system\s*\(")),
    (
        "POSSIBLE_HARDCODED_SECRET",
        re.compile(r"(?i)(?:api[_-]?key|secret)\s*=\s*['\"][^'\"]+"),
    ),
    (
        "LIVE_ORDER_SURFACE",
        re.compile(r"\b(?:create_order|order_market_buy|order_market_sell)\b"),
    ),
)


def scan_static_risks(documents: tuple[FetchedDocument, ...]) -> tuple[str, ...]:
    findings: list[str] = []
    for document in documents:
        for code, pattern in _PATTERNS:
            if pattern.search(document.content):
                findings.append(f"{code}:{document.path}")
    return tuple(dict.fromkeys(findings))
