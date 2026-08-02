from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import (
    ContractError,
    canonical_json_bytes,
    load_json,
    load_workbench_config,
    sha256_bytes,
    validate_operator_id,
    verify_decision_hash,
    verify_result_hash,
    write_json,
)


def _file_fingerprint(result: dict[str, Any]) -> tuple[tuple[str, int, str], ...]:
    return tuple(sorted(
        (
            row["path"],
            row["compressed_bytes"],
            row["compressed_sha256"],
        )
        for row in result.get("files", [])
    ))


def verify_reruns(
    claim: dict[str, Any],
    replicas: list[dict[str, Any]],
    comparison: dict[str, Any],
    config: dict[str, Any],
    *,
    allow_demo_identities: bool = False,
) -> dict[str, Any]:
    verify_decision_hash(comparison)
    required = int(config["promotion"]["required_independent_human_reruns"])
    if len(replicas) != required:
        raise ContractError(f"expected exactly {required} independent reruns")

    results = [claim, *replicas]
    for result in results:
        verify_result_hash(result)
        validate_operator_id(result["operator_id"], allow_demo=allow_demo_identities)
        if not result.get("hard_gate_pass"):
            raise ContractError("a rerun failed the hard correctness gate")

    operator_ids = [result["operator_id"] for result in results]
    if len(set(operator_ids)) != len(operator_ids):
        raise ContractError("author and validators must be distinct human operator IDs")

    artifact_hashes = {result["candidate_artifact_sha256"] for result in results}
    corpus_hashes = {result["corpus"]["corpus_sha256"] for result in results}
    totals = {result["aggregate"]["total_compressed_bytes"] for result in results}
    fingerprints = {_file_fingerprint(result) for result in results}
    if len(artifact_hashes) != 1:
        raise ContractError("reruns did not run the same locked candidate artifact")
    if len(corpus_hashes) != 1:
        raise ContractError("reruns did not use the same corpus commitment")
    if len(totals) != 1 or len(fingerprints) != 1:
        raise ContractError("deterministic compressed results differ between operators")
    if comparison.get("candidate_artifact_sha256") not in artifact_hashes:
        raise ContractError("comparison refers to a different candidate artifact")

    public_status = comparison.get("status")
    if public_status in {"FRONTIER_ADVANCE", "PUBLIC_SIZE_CANDIDATE", "ELIGIBLE_FOR_REPRODUCTION"}:
        status = "RERUN_CONFIRMED_ADVANCE_AWAITING_HIDDEN_HOLDOUT"
    elif public_status in {
        "VALID_DOMINATED",
        "VALID_NONDOMINATED_NO_GAIN",
        "VALID_NO_CONFIRMED_GAIN",
        "VALID_NO_GAIN",
    }:
        status = "RERUN_CONFIRMED_NO_GAIN"
    else:
        status = "DISPUTED"

    unsigned = {
        "schema_version": 1,
        "decision_type": "wb001_rerun_gate",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workbench": claim["workbench"],
        "status": status,
        "operator_ids": operator_ids,
        "claim_result_sha256": claim["result_sha256"],
        "replica_result_sha256": [row["result_sha256"] for row in replicas],
        "comparison_decision_sha256": comparison["decision_sha256"],
        "candidate_artifact_sha256": next(iter(artifact_hashes)),
        "corpus_sha256": next(iter(corpus_hashes)),
        "exact_compressed_bytes": next(iter(totals)),
        "hidden_holdout_required": status.endswith("AWAITING_HIDDEN_HOLDOUT"),
    }
    return {**unsigned, "decision_sha256": sha256_bytes(canonical_json_bytes(unsigned))}


def verify_reproductions(
    claim: dict[str, Any],
    replicas: list[dict[str, Any]],
    comparison: dict[str, Any],
    config: dict[str, Any],
    *,
    allow_demo_identities: bool = False,
) -> dict[str, Any]:
    """Compatibility alias; this gate verifies reruns of one locked artifact."""
    return verify_reruns(
        claim,
        replicas,
        comparison,
        config,
        allow_demo_identities=allow_demo_identities,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply the WB-001 two-other-human rerun gate")
    parser.add_argument("--claim", type=Path, required=True)
    parser.add_argument("--replica", type=Path, action="append", required=True)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--allow-demo-identities", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    decision = verify_reruns(
        load_json(args.claim),
        [load_json(path) for path in args.replica],
        load_json(args.comparison),
        load_workbench_config(args.config),
        allow_demo_identities=args.allow_demo_identities,
    )
    write_json(args.output, decision)
    print(json.dumps({"output": str(args.output), "status": decision["status"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
