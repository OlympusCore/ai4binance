"""Standalone CLI for local baseline and pre-extracted evidence evaluation."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from ai4binance.github_radar.engine import GitHubRadarEngine
from ai4binance.github_radar.github_client import (
    HttpsGitHubTransport,
    PublicGitHubClient,
)
from ai4binance.github_radar.models import (
    DimensionRating,
    EvidenceFragment,
    RepositoryEvidence,
    RepositorySource,
)
from ai4binance.github_radar.reporting import (
    assessment_payload,
    baseline_payload,
    discovery_payload,
    write_json_atomic,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m ai4binance.github_radar")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)
    baseline = subparsers.add_parser("baseline")
    baseline.add_argument("--output", type=Path)
    evaluate = subparsers.add_parser("evaluate")
    evaluate.add_argument("--input", type=Path, required=True)
    evaluate.add_argument("--output", type=Path)
    discover = subparsers.add_parser("discover")
    discover.add_argument("--capability", action="append", default=[])
    discover.add_argument("--maximum-queries", type=int, default=20)
    discover.add_argument("--repositories-per-query", type=int, default=3)
    discover.add_argument("--documents-per-repository", type=int, default=20)
    discover.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    engine = GitHubRadarEngine.from_repository(args.repository_root)
    if args.command == "baseline":
        payload = baseline_payload(engine.local_baseline())
    elif args.command == "evaluate":
        evidence = _load_repository_evidence(args.input)
        result = engine.assess(evidence, observed_at=datetime.now(UTC))
        payload = assessment_payload(result)
    else:
        token = os.environ.get("GITHUB_TOKEN")
        client = PublicGitHubClient(HttpsGitHubTransport(token))
        candidates = engine.discover(
            client,
            capability_ids=tuple(args.capability),
            maximum_queries=args.maximum_queries,
            repositories_per_query=args.repositories_per_query,
            documents_per_repository=args.documents_per_repository,
        )
        payload = discovery_payload(candidates)
    if args.output is not None:
        write_json_atomic(args.output, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _load_repository_evidence(path: Path) -> RepositoryEvidence:
    if path.resolve().stat().st_size > 512_000:
        raise ValueError("repository evidence input exceeds the bounded size")
    raw = json.loads(path.resolve().read_text(encoding="utf-8"))
    payload = _mapping(raw, "evidence input")
    source = _mapping(payload.get("source"), "source")
    evidence_items = _sequence(payload.get("evidence"), "evidence")
    rating_items = _sequence(payload.get("ratings"), "ratings")
    return RepositoryEvidence(
        capability_id=str(payload.get("capability_id", "")),
        source=RepositorySource(
            repository=str(source.get("repository", "")),
            url=str(source.get("url", "")),
            pinned_revision=str(source.get("pinned_revision", "")),
            license_id=str(source.get("license_id", "")),
            language=str(source.get("language", "UNKNOWN")),
        ),
        evidence=tuple(
            EvidenceFragment(
                evidence_type=str(item.get("evidence_type", "")),
                reference=str(item.get("reference", "")),
                claim=str(item.get("claim", "")),
                content_sha256=str(item.get("content_sha256", "")),
            )
            for item in (_mapping(value, "evidence item") for value in evidence_items)
        ),
        risks=_strings(payload.get("risks"), "risks"),
        ratings=tuple(
            DimensionRating(
                dimension=str(item.get("dimension", "")),
                rating=float(str(item.get("rating", -1))),
                rationale=str(item.get("rationale", "")),
            )
            for item in (_mapping(value, "rating item") for value in rating_items)
        ),
        passed_gates=_strings(payload.get("passed_gates"), "passed_gates"),
    )


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return cast(Mapping[str, object], value)


def _sequence(value: object, name: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{name} must be a sequence")
    return value


def _strings(value: object, name: str) -> tuple[str, ...]:
    return tuple(str(item) for item in _sequence(value, name))


if __name__ == "__main__":
    raise SystemExit(main())
