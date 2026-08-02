from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator


WORKBENCH_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKBENCH_ROOT / "runner"))

from baseline_frontier import verify_pack_hash  # noqa: E402
from common import (  # noqa: E402
    load_json,
    verify_commitment_hash,
    verify_decision_hash,
    verify_result_hash,
)
from evaluate_isolated import verify_image_lock  # noqa: E402
from signing import load_public_key_document, verify_signed_document  # noqa: E402


def validate(schema_name: str, document_path: Path) -> None:
    schema = load_json(WORKBENCH_ROOT / "schemas" / schema_name)
    Draft202012Validator(schema).validate(load_json(document_path))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate WB-001 JSON contracts and commitments")
    parser.add_argument("--require-generated", action="store_true")
    args = parser.parse_args()

    schema_paths = sorted((WORKBENCH_ROOT / "schemas").glob("*.schema.json"))
    for path in schema_paths:
        Draft202012Validator.check_schema(load_json(path))

    validated: list[str] = []
    for submission in sorted(
        [
            *(WORKBENCH_ROOT / "baselines" / "reference_pack").glob("*.submission.json"),
            WORKBENCH_ROOT / "examples" / "zlib_level9" / "submission.json",
            *(WORKBENCH_ROOT / "tests" / "fixtures").glob("*_submission.json"),
        ]
    ):
        validate("submission.schema.json", submission)
        validated.append(str(submission.relative_to(WORKBENCH_ROOT)))

    commitment_path = WORKBENCH_ROOT / "data" / "holdout_commitment.json"
    validate("holdout-commitment.schema.json", commitment_path)
    verify_commitment_hash(load_json(commitment_path))
    validated.append(str(commitment_path.relative_to(WORKBENCH_ROOT)))

    image_lock_path = WORKBENCH_ROOT / "isolation" / "image.lock.json"
    validate("image-lock.schema.json", image_lock_path)
    verify_image_lock(
        load_json(image_lock_path),
        WORKBENCH_ROOT / "isolation" / "docker_policy.toml",
    )
    validated.append(str(image_lock_path.relative_to(WORKBENCH_ROOT)))

    generated = {
        "baseline_pack": WORKBENCH_ROOT / "results" / "reference_pack" / "baseline_pack.json",
        "candidate_result": WORKBENCH_ROOT / "results" / "qualification_v0_2" / "candidate_result.json",
        "comparison": WORKBENCH_ROOT / "results" / "qualification_v0_2" / "frontier_comparison.json",
        "job_token": WORKBENCH_ROOT / "results" / "blind_demo" / "job_token_v3.json",
        "attestation": WORKBENCH_ROOT / "results" / "blind_demo" / "public_attestation.json",
    }
    if args.require_generated:
        missing = [name for name, path in generated.items() if not path.is_file()]
        if missing:
            raise SystemExit(f"missing required generated contracts: {missing}")

    public_key = load_public_key_document(
        load_json(WORKBENCH_ROOT / "data" / "evaluator_public_key.json")
    )
    if generated["baseline_pack"].is_file():
        validate("baseline-pack.schema.json", generated["baseline_pack"])
        verify_pack_hash(load_json(generated["baseline_pack"]))
        validated.append(str(generated["baseline_pack"].relative_to(WORKBENCH_ROOT)))
        for result_path in sorted(
            (WORKBENCH_ROOT / "results" / "reference_pack").glob("*.result.json")
        ):
            validate("result.schema.json", result_path)
            verify_result_hash(load_json(result_path))
            validated.append(str(result_path.relative_to(WORKBENCH_ROOT)))
    if generated["candidate_result"].is_file():
        validate("result.schema.json", generated["candidate_result"])
        verify_result_hash(load_json(generated["candidate_result"]))
        validated.append(str(generated["candidate_result"].relative_to(WORKBENCH_ROOT)))
    if generated["comparison"].is_file():
        validate("comparison.schema.json", generated["comparison"])
        verify_decision_hash(load_json(generated["comparison"]))
        validated.append(str(generated["comparison"].relative_to(WORKBENCH_ROOT)))
    if generated["job_token"].is_file():
        validate("job-token.schema.json", generated["job_token"])
        verify_signed_document(load_json(generated["job_token"]), public_key)
        validated.append(str(generated["job_token"].relative_to(WORKBENCH_ROOT)))
    if generated["attestation"].is_file():
        validate("blind-attestation.schema.json", generated["attestation"])
        verify_signed_document(load_json(generated["attestation"]), public_key)
        validated.append(str(generated["attestation"].relative_to(WORKBENCH_ROOT)))

    print(json.dumps({"schemas": len(schema_paths), "contracts_validated": len(validated)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
