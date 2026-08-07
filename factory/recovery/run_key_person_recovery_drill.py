from __future__ import annotations

import argparse
import json
from pathlib import Path

from .drill import run_key_person_recovery_drill


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a local key-person recovery drill from a verified offline release")
    parser.add_argument("--release", type=Path, required=True, help="Verified offline release directory")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--operator-id", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--identity-assurance", default="SELF_ASSERTED_LOCAL")
    parser.add_argument("--recovery-id")
    parser.add_argument("--recorded-at")
    args = parser.parse_args()
    print(json.dumps(run_key_person_recovery_drill(args.release, args.output, operator_id=args.operator_id, display_name=args.display_name, identity_assurance=args.identity_assurance, recovery_id=args.recovery_id, recorded_at=args.recorded_at), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
