from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator


FACTORY_ROOT = Path(__file__).resolve().parents[2]
CONTROL_ROOT = FACTORY_ROOT / "control_plane"
sys.path.insert(0, str(FACTORY_ROOT))

from control_plane.common import canonical_json_bytes, load_json, sha256_bytes  # noqa: E402
from control_plane.ledger import EventLedger  # noqa: E402
from control_plane.workflow import _validate_round_document  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate factory control-plane contracts")
    parser.add_argument(
        "--round",
        type=Path,
        default=FACTORY_ROOT / "rounds" / "WB001-PILOT-001" / "round.json",
    )
    parser.add_argument("--ledger", type=Path, default=FACTORY_ROOT / "state" / "pilot_events.jsonl")
    args = parser.parse_args()

    schemas: dict[str, dict] = {}
    for path in sorted((CONTROL_ROOT / "schemas").glob("*.schema.json")):
        schema = load_json(path)
        Draft202012Validator.check_schema(schema)
        schemas[path.name] = schema

    round_document = load_json(args.round)
    Draft202012Validator(schemas["round.schema.json"]).validate(round_document)
    _validate_round_document(round_document, FACTORY_ROOT)

    checkpoint_path = args.round.parent / "bootstrap_checkpoint.json"
    checkpoint = None
    if checkpoint_path.exists():
        checkpoint = load_json(checkpoint_path)
        Draft202012Validator(schemas["checkpoint.schema.json"]).validate(checkpoint)
        unsigned_checkpoint = {
            key: value for key, value in checkpoint.items() if key != "checkpoint_sha256"
        }
        if checkpoint["checkpoint_sha256"] != sha256_bytes(canonical_json_bytes(unsigned_checkpoint)):
            raise ValueError("bootstrap checkpoint hash does not match its contents")

    ledger_summary = None
    event_count = 0
    if args.ledger.exists():
        ledger = EventLedger(args.ledger)
        events = ledger.read()
        validator = Draft202012Validator(schemas["event.schema.json"])
        for event in events:
            validator.validate(event)
        ledger_summary = ledger.verify()
        event_count = len(events)
        if checkpoint is not None:
            checkpoint_index = checkpoint["events"] - 1
            if (
                checkpoint_index < 0
                or checkpoint_index >= event_count
                or events[checkpoint_index]["event_sha256"] != checkpoint["head_event_sha256"]
            ):
                raise ValueError("live ledger does not contain the anchored bootstrap checkpoint")

    print(
        json.dumps(
            {
                "valid": True,
                "schemas": len(schemas),
                "round_id": round_document["round_id"],
                "round_sha256": round_document["round_sha256"],
                "ledger_events": event_count,
                "ledger": ledger_summary,
                "bootstrap_checkpoint_sha256": (
                    checkpoint["checkpoint_sha256"] if checkpoint is not None else None
                ),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
