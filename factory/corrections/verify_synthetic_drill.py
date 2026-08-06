from __future__ import annotations

import argparse
import json
from pathlib import Path

from .synthetic_drill import verify_synthetic_drill


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a public synthetic correction drill")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify_synthetic_drill(args.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
