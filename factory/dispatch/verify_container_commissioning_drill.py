from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from control_plane.common import ControlPlaneError

from .container_commissioning import (
    verify_container_commissioning_drill,
    verify_prepared_container_commissioning_drill,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify a prepared or executed synthetic container commissioning package."
    )
    parser.add_argument("output", type=Path)
    parser.add_argument("--factory-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--prepared",
        action="store_true",
        help="verify the package before execution instead of a completed commissioning result",
    )
    args = parser.parse_args(argv)
    try:
        verify = verify_prepared_container_commissioning_drill if args.prepared else verify_container_commissioning_drill
        print(json.dumps(verify(args.output, factory_root=args.factory_root.resolve()), indent=2))
        return 0
    except ControlPlaneError as exc:
        print(f"container-commissioning: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
