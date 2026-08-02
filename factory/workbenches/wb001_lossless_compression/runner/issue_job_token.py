from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from common import (
    WORKBENCH_ROOT,
    candidate_artifact_manifest,
    load_json,
    load_submission,
    load_workbench_config,
    validate_operator_id,
    verify_commitment_hash,
    write_json,
)
from signing import key_id, load_private_key, sign_document


FACTORY_ROOT = WORKBENCH_ROOT.parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Issue a one-shot signed WB-001 blind-evaluation token")
    parser.add_argument("--submission", type=Path, required=True)
    parser.add_argument("--operator-id", required=True)
    parser.add_argument("--round-id", required=True)
    parser.add_argument("--round-sha256", required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--rerun-gate-event-sha256", required=True)
    parser.add_argument("--valid-hours", type=float, default=24.0)
    parser.add_argument("--allow-demo-identity", action="store_true")
    parser.add_argument(
        "--private-key",
        type=Path,
        default=FACTORY_ROOT / "private" / "wb001" / "evaluator_private_key.pem",
    )
    parser.add_argument(
        "--commitment",
        type=Path,
        default=WORKBENCH_ROOT / "data" / "holdout_commitment.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    validate_operator_id(args.operator_id, allow_demo=args.allow_demo_identity)
    for name, value in (
        ("round_sha256", args.round_sha256),
        ("rerun_gate_event_sha256", args.rerun_gate_event_sha256),
    ):
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise SystemExit(f"--{name.replace('_', '-')} must be a lowercase SHA-256 digest")
    config = load_workbench_config()
    submission_path = args.submission.resolve()
    submission = load_submission(submission_path, config)
    artifact = candidate_artifact_manifest(submission_path, submission)
    commitment = load_json(args.commitment)
    verify_commitment_hash(commitment)
    private_key = load_private_key(args.private_key)
    evaluator_key_id = key_id(private_key.public_key())
    if evaluator_key_id != commitment["evaluator_key_id"]:
        raise SystemExit("private signing key does not match the holdout commitment")

    issued_at = datetime.now(timezone.utc)
    unsigned = {
        "schema_version": 1,
        "token_type": "wb001_blind_job",
        "token_id": uuid.uuid4().hex,
        "issued_at": issued_at.isoformat(),
        "expires_at": (issued_at + timedelta(hours=args.valid_hours)).isoformat(),
        "operator_id": args.operator_id,
        "round_id": args.round_id,
        "round_sha256": args.round_sha256,
        "attempt_id": args.attempt_id,
        "rerun_gate_event_sha256": args.rerun_gate_event_sha256,
        "workbench": {"id": config["workbench"]["id"], "version": config["workbench"]["version"]},
        "candidate_artifact_sha256": artifact["artifact_sha256"],
        "holdout_commitment_sha256": commitment["commitment_sha256"],
        "evaluator_key_id": evaluator_key_id,
        "maximum_uses": 1,
    }
    token = sign_document(unsigned, private_key)
    write_json(args.output, token)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "token_id": token["token_id"],
                "expires_at": token["expires_at"],
                "candidate_artifact_sha256": token["candidate_artifact_sha256"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
