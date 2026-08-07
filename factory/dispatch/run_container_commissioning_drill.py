from __future__ import annotations

import argparse
from getpass import getpass
import json
import sys
from pathlib import Path

from control_plane.common import ControlPlaneError

from .container_commissioning import (
    DEFAULT_IMAGE_REF,
    prepare_container_commissioning_drill,
    run_prepared_container_commissioning_drill,
)


def _release_capability(path: Path | None, *, prompt: str) -> str:
    return path.read_text(encoding="utf-8").strip() if path else getpass(prompt)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m dispatch.run_container_commissioning_drill",
        description="Prepare or run the fixed, synthetic container commissioning fixture.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare", help="write an inspectable package without starting Docker")
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--factory-root", type=Path, default=Path(__file__).resolve().parents[1])
    prepare.add_argument("--image-ref", default=DEFAULT_IMAGE_REF)
    prepare.add_argument("--operator-id", default="human:container-commissioning-operator")
    prepare.add_argument("--release-capability-file", type=Path)

    run = sub.add_parser("run", help="run one already-prepared package after human release")
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--factory-root", type=Path, default=Path(__file__).resolve().parents[1])
    run.add_argument("--release-capability-file", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "prepare":
            value = prepare_container_commissioning_drill(
                args.output,
                factory_root=args.factory_root.resolve(),
                image_ref=args.image_ref,
                operator_id=args.operator_id,
                release_capability=_release_capability(
                    args.release_capability_file,
                    prompt="Human release capability to hash (not echoed): ",
                ),
            )
        else:
            value = run_prepared_container_commissioning_drill(
                args.output,
                factory_root=args.factory_root.resolve(),
                release_capability=_release_capability(
                    args.release_capability_file,
                    prompt="Human release capability to authorise this run (not echoed): ",
                ),
            )
        print(json.dumps(value, indent=2))
        return 0
    except ControlPlaneError as exc:
        print(f"container-commissioning: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
