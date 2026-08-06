from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


FACTORY_ROOT = Path(__file__).resolve().parents[1]
if str(FACTORY_ROOT) not in sys.path:
    sys.path.insert(0, str(FACTORY_ROOT))

from commissioning.synthetic_shift import (  # noqa: E402
    run_synthetic_dispute_shift,
    verify_synthetic_dispute_shift,
)
from control_plane import ControlPlaneError  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run a zero-credit synthetic factory shift through blind disagreement, "
            "diagnostic rerun, dispute and public-ledger audit."
        )
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=FACTORY_ROOT / "state" / "commissioning" / "wb001-synthetic-dispute-001",
        help="new directory for public and private commissioning artifacts",
    )
    args = parser.parse_args(argv)
    try:
        report = run_synthetic_dispute_shift(args.output)
        verification = verify_synthetic_dispute_shift(args.output)
    except ControlPlaneError as exc:
        print(f"synthetic-shift: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "valid": True,
                "output": str(args.output.resolve()),
                "shift_id": report["shift_id"],
                "final_status": report["final_status"],
                "scientific_standing": report["scientific_standing"],
                "report_sha256": report["report_sha256"],
                "public_ledger_audit": verification["public_ledger_audit"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
