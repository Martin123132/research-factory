from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import (
    WORKBENCH_ROOT,
    ContractError,
    evaluator_software_sha256,
    load_json,
    verify_commitment_hash,
)
from signing import load_public_key_document, verify_signed_document


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a public WB-001 blind verdict")
    parser.add_argument("--attestation", type=Path, required=True)
    parser.add_argument(
        "--public-key",
        type=Path,
        default=WORKBENCH_ROOT / "data" / "evaluator_public_key.json",
    )
    parser.add_argument(
        "--commitment",
        type=Path,
        default=WORKBENCH_ROOT / "data" / "holdout_commitment.json",
    )
    args = parser.parse_args()

    attestation = load_json(args.attestation)
    public_document = load_json(args.public_key)
    public_key = load_public_key_document(public_document)
    verify_signed_document(attestation, public_key)
    commitment = load_json(args.commitment)
    verify_commitment_hash(commitment)
    if attestation.get("attestation_type") != "wb001_blind_verdict":
        raise ContractError("unexpected attestation type")
    for field in ("round_id", "round_sha256", "attempt_id", "rerun_gate_event_sha256"):
        if not isinstance(attestation.get(field), str) or not attestation[field]:
            raise ContractError(f"attestation is missing causality binding {field}")
    if attestation.get("verdict") not in {"PASS", "NO_GAIN", "INVALID", "ESCALATE"}:
        raise ContractError("unexpected blind verdict")
    if attestation.get("holdout_commitment_sha256") != commitment["commitment_sha256"]:
        raise ContractError("attestation targets a different holdout commitment")
    if attestation.get("evaluator_key_id") != public_document["key_id"]:
        raise ContractError("attestation targets a different evaluator key")
    print(
        json.dumps(
            {
                "valid": True,
                "run_id": attestation["run_id"],
                "verdict": attestation["verdict"],
                "candidate_artifact_sha256": attestation["candidate_artifact_sha256"],
                "details_sealed": attestation["details_sealed"],
                "matches_current_evaluator_software": (
                    attestation.get("evaluator_software_sha256")
                    == evaluator_software_sha256()
                ),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
