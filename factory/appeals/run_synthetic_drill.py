from __future__ import annotations

import argparse
import json
from pathlib import Path

from .synthetic_drill import run_synthetic_drill


FACTORY_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the synthetic conflict-independent appeal drill")
    parser.add_argument(
        "--output",
        type=Path,
        default=FACTORY_ROOT / "state" / "appeal-synthetic-001",
    )
    args = parser.parse_args()
    print(json.dumps(run_synthetic_drill(args.output), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
