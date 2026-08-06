from __future__ import annotations

import argparse
import json
from pathlib import Path

from .synthetic_drill import run_synthetic_drill


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the zero-credit correction drill")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run_synthetic_drill(args.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
