from __future__ import annotations

import argparse
import json
from pathlib import Path

from .drill import verify_key_person_recovery_drill


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a local key-person recovery drill")
    parser.add_argument("--release", type=Path, required=True, help="Verified offline release directory")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify_key_person_recovery_drill(args.release, args.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
