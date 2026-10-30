"""Select the successor pilot without writing into historical round state."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from control_plane.ledger import EventLedger
from .environments import EnvironmentProfileError, RESEARCH_PROFILE, RESEARCH_ROUND, profiles


READ_ONLY = {"status", "verify-ledger", "audit-blindness"}


def prepare_governed(parser: argparse.ArgumentParser, root: Path) -> None:
    state = root / "state" / RESEARCH_ROUND
    parser.set_defaults(
        ledger=state / "events.jsonl",
        evidence_root=state / "private/evidence",
        artifact_root=state / "public/artifacts",
        private_root=state / "private/rerun_results",
    )


def guard_round(args: argparse.Namespace, root: Path) -> None:
    """Validate selection before the frozen dispatcher can create or append state.

    Historical ledgers remain readable. Mutations require the separately frozen
    successor document, including commands whose round is indirect via a claim.
    This CLI guard is not an OS isolation or concurrent-writer security boundary.
    """
    _, loaded = profiles(root)
    binding = loaded[RESEARCH_PROFILE]["round_binding"]
    expected = json.loads((root / binding["path"]).read_text(encoding="utf-8"))
    if args.command in READ_ONLY:
        return
    if getattr(args, "round_id", RESEARCH_ROUND) != RESEARCH_ROUND:
        raise EnvironmentProfileError("replacement runtime requires its own successor round")
    if args.command == "open-round":
        if hashlib.sha256(args.config.read_bytes()).hexdigest() != binding["sha256"]:
            raise EnvironmentProfileError("replacement runtime requires the frozen successor round document")
    historical = {
        "ledger": root / "state/pilot_events.jsonl",
        "evidence_root": root / "state/private/evidence",
        "artifact_root": root / "state/public/artifacts",
        "private_root": root / "state/private/rerun_results",
    }
    for name, old in historical.items():
        path = getattr(args, name).resolve()
        if path == old.resolve() or path.is_relative_to(old.resolve()):
            raise EnvironmentProfileError("historical state is retained read-only; use a fresh successor state directory")
    for event in EventLedger(args.ledger).read():
        if event["event_type"] == "ROUND_OPENED" and event["payload"]["round"] != expected:
            raise EnvironmentProfileError("ledger contains another round; retain it and use a fresh successor ledger")
