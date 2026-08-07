from __future__ import annotations

import argparse
from getpass import getpass
import json
import sys
from pathlib import Path

from control_plane.common import ControlPlaneError

from .container_adapter import (
    inspect_host,
    load_request,
    run_container,
    validate_request,
    verify_receipt,
)
from .gate import DispatchBudgetGate, load_json_strict


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m dispatch.run_container_adapter",
        description="Run one digest-pinned, budget-bound commissioning container or verify its receipt.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("host", help="inspect Docker availability without starting a container")

    run = sub.add_parser("run", help="run an already-authorised exact command")
    run.add_argument("--factory-root", type=Path, default=Path(__file__).resolve().parents[1])
    run.add_argument("--budget", type=Path, required=True)
    run.add_argument("--ticket", type=Path, required=True)
    run.add_argument("--request", type=Path, required=True)
    run.add_argument(
        "--release-capability-file",
        type=Path,
        help="read a human-retained capability from a local file instead of prompting",
    )
    run.add_argument("--stop-file", type=Path, required=True)
    run.add_argument("--receipt", type=Path, required=True)

    verify = sub.add_parser("verify", help="verify an existing receipt and its preserved output")
    verify.add_argument("--factory-root", type=Path, default=Path(__file__).resolve().parents[1])
    verify.add_argument("--budget", type=Path, required=True)
    verify.add_argument("--ticket", type=Path, required=True)
    verify.add_argument("--request", type=Path, required=True)
    verify.add_argument("--receipt", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "host":
            print(json.dumps(inspect_host(), indent=2))
            return 0
        root = args.factory_root.resolve()
        gate = DispatchBudgetGate(root)
        budget = gate.load_budget(args.budget)
        ticket = gate.load_and_validate_ticket(args.ticket, budget=budget)
        request = load_request(args.request)
        if args.command == "run":
            validate_request(request, budget=budget, ticket=ticket, factory_root=root)
            host = inspect_host()
            if not host["ready"]:
                raise ControlPlaneError(f"container host is not ready: {host['reason']}")
            if args.release_capability_file:
                release_capability = args.release_capability_file.read_text(encoding="utf-8").strip()
            else:
                release_capability = getpass("Human release capability (not echoed): ")
            value = run_container(
                request,
                budget=budget,
                ticket=ticket,
                factory_root=root,
                release_capability=release_capability,
                stop_file=args.stop_file,
                receipt_output=args.receipt,
            )
        else:
            value = verify_receipt(
                load_json_strict(args.receipt),
                request=request,
                budget=budget,
                ticket=ticket,
                factory_root=root,
            )
        print(json.dumps(value, indent=2))
        return 0
    except ControlPlaneError as exc:
        print(f"container-adapter: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
