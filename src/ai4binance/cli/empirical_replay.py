"""Run a frozen Spot component experiment over every declared symbol."""

import argparse
import json
from datetime import datetime
from pathlib import Path

from ai4binance.application.validation_pipeline import VALIDATED_PLAYBOOKS
from ai4binance.config import Settings
from ai4binance.data import ParquetOHLCVArchive
from ai4binance.validation.empirical_replay import (
    EmpiricalReplayWindow,
    run_empirical_spot_study,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--symbols", required=True, help="Comma-separated frozen symbols."
    )
    parser.add_argument("--playbook", required=True, choices=VALIDATED_PLAYBOOKS)
    parser.add_argument(
        "--timeframe", default="1h", choices=("5m", "15m", "1h", "4h", "1d")
    )
    parser.add_argument("--start", required=True, type=datetime.fromisoformat)
    parser.add_argument("--calibration-end", required=True, type=datetime.fromisoformat)
    parser.add_argument("--holdout-start", required=True, type=datetime.fromisoformat)
    parser.add_argument("--end", required=True, type=datetime.fromisoformat)
    parser.add_argument("--hypothesis-count", required=True, type=int)
    parser.add_argument(
        "--archive-root", type=Path, default=Settings().dataset_directory / "spot"
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("runtime/artifacts/validation/empirical_replay"),
    )
    args = parser.parse_args()
    symbols = tuple(args.symbols.split(","))
    if (
        len(set(symbols)) != len(symbols)
        or any(not s.isascii() or not s.isalnum() or not s.isupper() for s in symbols)
        or args.hypothesis_count < len(symbols)
    ):
        parser.error(
            "unique uppercase symbols and full hypothesis accounting are required"
        )
    if not args.output_root.resolve().is_relative_to(
        (Path.cwd() / "runtime").resolve()
    ):
        parser.error("generated evidence must remain under repository runtime")
    window = EmpiricalReplayWindow(
        args.start, args.calibration_end, args.holdout_start, args.end
    )
    failed = False
    for symbol in symbols:
        try:
            result = run_empirical_spot_study(
                archive=ParquetOHLCVArchive(args.archive_root),
                symbol=symbol,
                timeframe=args.timeframe,
                playbook=args.playbook,
                window=window,
                output_root=args.output_root,
                hypothesis_count=args.hypothesis_count,
            )
            print(
                json.dumps(
                    {
                        "symbol": symbol,
                        "run_id": result["run_id"],
                        "metrics": result["holdout_metrics"],
                        "blockers": result["blockers"],
                    }
                ),
                flush=True,
            )
        except (OSError, ValueError) as error:
            failed = True
            print(
                json.dumps(
                    {
                        "symbol": symbol,
                        "status": "BLOCKED",
                        "reason": str(error),
                        "execution_allowed": False,
                    }
                ),
                flush=True,
            )
    return 2 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
