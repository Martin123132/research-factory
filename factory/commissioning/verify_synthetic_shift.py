from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


FACTORY_ROOT = Path(__file__).resolve().parents[1]
if str(FACTORY_ROOT) not in sys.path:
    sys.path.insert(0, str(FACTORY_ROOT))

from commissioning.synthetic_shift import verify_synthetic_dispute_shift  # noqa: E402
from control_plane import ControlPlaneError  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify a completed synthetic dispute shift from its public artifacts."
    )
    parser.add_argument("output", type=Path, help="completed commissioning output directory")
    args = parser.parse_args(argv)
    try:
        result = verify_synthetic_dispute_shift(args.output)
    except ControlPlaneError as exc:
        print(f"verify-synthetic-shift: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
