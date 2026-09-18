"""Create a local-only, secret-scanned AI4BINANCE public showcase staging tree."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from ai4binance.ops.public_showcase import (  # noqa: E402
    PublicShowcaseError,
    load_public_showcase_manifest,
    run_gitleaks_scan,
    stage_public_showcase,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=REPOSITORY_ROOT
        / "config"
        / "publication"
        / "public_showcase_manifest.yaml",
    )
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--report-path", required=True, type=Path)
    args = parser.parse_args()
    root = args.repository_root.resolve()
    output_directory = args.output_directory.resolve()
    report_path = args.report_path.resolve()
    if report_path.is_relative_to(output_directory):
        print(
            "PUBLIC_SHOWCASE_BLOCKED: report path must be outside the showcase output",
            file=sys.stderr,
        )
        return 1
    try:
        manifest = load_public_showcase_manifest(args.manifest.resolve())
        executable = (
            root
            / "tools"
            / "gitleaks"
            / f"v{manifest.gitleaks_version}"
            / "gitleaks.exe"
        )
        report = stage_public_showcase(
            root,
            manifest,
            output_directory,
            secret_scanner=lambda stage: run_gitleaks_scan(stage, executable),
        )
    except PublicShowcaseError as error:
        print(f"PUBLIC_SHOWCASE_BLOCKED: {error}", file=sys.stderr)
        return 1
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
