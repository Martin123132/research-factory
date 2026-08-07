from __future__ import annotations
import argparse
import json
from pathlib import Path
from .synthetic_drill import run_synthetic_drill

def main() -> int:
    parser = argparse.ArgumentParser(description="Run the synthetic material-support disclosure drill")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "state" / "support-disclosure-synthetic-001")
    args = parser.parse_args()
    print(json.dumps(run_synthetic_drill(args.output), indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
