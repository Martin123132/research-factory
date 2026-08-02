from __future__ import annotations

import argparse
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from baseline_frontier import verify_pack_hash
from common import (
    WORKBENCH_ROOT,
    ContractError,
    candidate_artifact_manifest,
    canonical_json_bytes,
    evaluator_software_sha256,
    load_json,
    load_submission,
    load_workbench_config,
    sha256_bytes,
    sha256_file,
    verify_commitment_hash,
    write_json,
)
from compare_frontier import compare_to_frontier
from evaluate_isolated import DockerExecutorFactory
from evaluate_local import CandidateExecutionError, evaluate_submission
from signing import (
    key_id,
    load_private_key,
    load_public_key_document,
    sign_document,
    verify_signed_document,
)


FACTORY_ROOT = WORKBENCH_ROOT.parents[1]


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ContractError("token timestamp has no timezone")
    return parsed


def consume_token(private_root: Path, token: dict[str, Any]) -> Path:
    consumed_root = private_root / "consumed_tokens"
    consumed_root.mkdir(parents=True, exist_ok=True)
    marker = consumed_root / f"{token['token_id']}.used"
    try:
        descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ContractError("blind job token has already been consumed") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(sha256_bytes(canonical_json_bytes(token)) + "\n")
    return marker


def map_verdict(status: str) -> str:
    if status in {"FRONTIER_ADVANCE", "PUBLIC_SIZE_CANDIDATE"}:
        return "PASS"
    if status in {
        "VALID_DOMINATED",
        "VALID_NONDOMINATED_NO_GAIN",
        "VALID_NO_CONFIRMED_GAIN",
    }:
        return "NO_GAIN"
    if status == "INVALID":
        return "INVALID"
    return "ESCALATE"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one signed, blind WB-001 holdout evaluation")
    parser.add_argument("--submission", type=Path, required=True)
    parser.add_argument("--token", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--private-root", type=Path, default=FACTORY_ROOT / "private" / "wb001")
    parser.add_argument(
        "--policy",
        type=Path,
        default=WORKBENCH_ROOT / "isolation" / "docker_policy.toml",
    )
    parser.add_argument(
        "--image-lock",
        type=Path,
        default=WORKBENCH_ROOT / "isolation" / "image.lock.json",
    )
    args = parser.parse_args()

    private_root = args.private_root.resolve()
    token = load_json(args.token)
    public_document = load_json(WORKBENCH_ROOT / "data" / "evaluator_public_key.json")
    public_key = load_public_key_document(public_document)
    verify_signed_document(token, public_key)
    if token.get("token_type") != "wb001_blind_job" or token.get("maximum_uses") != 1:
        raise SystemExit("invalid blind job token contract")
    required_causality = (
        "round_id",
        "round_sha256",
        "attempt_id",
        "rerun_gate_event_sha256",
    )
    if not all(isinstance(token.get(field), str) and token[field] for field in required_causality):
        raise SystemExit("blind job token is missing post-rerun causality bindings")
    current_time = datetime.now(timezone.utc)
    if parse_time(token["issued_at"]) > current_time or parse_time(token["expires_at"]) <= current_time:
        raise SystemExit("blind job token is not yet valid or has expired")

    config = load_workbench_config()
    submission_path = args.submission.resolve()
    submission = load_submission(submission_path, config)
    artifact = candidate_artifact_manifest(submission_path, submission)
    commitment = load_json(WORKBENCH_ROOT / "data" / "holdout_commitment.json")
    verify_commitment_hash(commitment)
    if token["candidate_artifact_sha256"] != artifact["artifact_sha256"]:
        raise SystemExit("submission no longer matches the artifact bound into the token")
    if token["holdout_commitment_sha256"] != commitment["commitment_sha256"]:
        raise SystemExit("token targets a different holdout commitment")
    if token["evaluator_key_id"] != public_document["key_id"]:
        raise SystemExit("token targets a different evaluator key")

    consume_token(private_root, token)
    run_id = uuid.uuid4().hex
    run_root = private_root / "runs" / run_id
    run_root.mkdir(parents=True)
    private_key = load_private_key(private_root / "evaluator_private_key.pem")
    if key_id(private_key.public_key()) != public_document["key_id"]:
        raise SystemExit("private evaluator key no longer matches its public commitment")

    detailed: dict[str, Any]
    try:
        result = evaluate_submission(
            submission_path,
            token["operator_id"],
            manifest_path=private_root / "holdout_manifest.json",
            executor_factory=DockerExecutorFactory(args.policy, args.image_lock),
        )
        pack = load_json(private_root / "reference_pack" / "baseline_pack.json")
        verify_pack_hash(pack)
        decision = compare_to_frontier(pack, result, config)
        verdict = map_verdict(decision["status"])
        detailed = {"token": token, "result": result, "decision": decision}
    except (ContractError, CandidateExecutionError, OSError) as exc:
        verdict = "ESCALATE"
        detailed = {
            "token": token,
            "infrastructure_error": {"type": type(exc).__name__, "message": str(exc)},
        }

    detailed_path = run_root / "private_evidence.json"
    write_json(detailed_path, detailed)
    generated_at = datetime.now(timezone.utc).isoformat()
    unsigned_attestation = {
        "schema_version": 1,
        "attestation_type": "wb001_blind_verdict",
        "run_id": run_id,
        "token_id": token["token_id"],
        "generated_at": generated_at,
        "operator_id": token["operator_id"],
        "round_id": token["round_id"],
        "round_sha256": token["round_sha256"],
        "attempt_id": token["attempt_id"],
        "rerun_gate_event_sha256": token["rerun_gate_event_sha256"],
        "workbench": token["workbench"],
        "candidate_artifact_sha256": artifact["artifact_sha256"],
        "holdout_commitment_sha256": commitment["commitment_sha256"],
        "verdict": verdict,
        "evaluator_key_id": public_document["key_id"],
        "evaluator_software_sha256": evaluator_software_sha256(),
        "image_lock_sha256": load_json(args.image_lock)["image_lock_sha256"],
        "private_evidence_sha256": sha256_file(detailed_path),
        "details_sealed": True,
    }
    attestation = sign_document(unsigned_attestation, private_key)
    write_json(args.output, attestation)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "run_id": run_id,
                "verdict": verdict,
                "details_sealed": True,
                "evaluator_key_id": attestation["evaluator_key_id"],
            },
            indent=2,
        )
    )
    return 0 if verdict in {"PASS", "NO_GAIN"} else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractError as exc:
        raise SystemExit(f"WB-001 blind evaluation refused: {exc}") from exc
