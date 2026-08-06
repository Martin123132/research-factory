from __future__ import annotations

import argparse
import json
from pathlib import Path

from .synthetic_drill import run_synthetic_drill


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the no-execution dispatch-budget drill")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--factory-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(run_synthetic_drill(args.output, factory_root=args.factory_root), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
