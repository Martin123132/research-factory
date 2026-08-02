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
    verify_result_hash,
    write_json,
)


def fractional_gain(baseline: float, candidate: float) -> float:
    if baseline == 0:
        return 0.0 if candidate == 0 else float("-inf")
    return (baseline - candidate) / baseline


def compare(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    verify_result_hash(baseline)
    verify_result_hash(candidate)
    if baseline["workbench"] != candidate["workbench"]:
        raise ContractError("baseline and candidate target different workbench versions")
    if baseline["corpus"]["corpus_sha256"] != candidate["corpus"]["corpus_sha256"]:
        raise ContractError("baseline and candidate used different corpus commitments")

    reasons: list[str] = []
    if not baseline.get("hard_gate_pass"):
        raise ContractError("the selected baseline did not pass its hard gates")
    if not candidate.get("hard_gate_pass"):
        reasons.append("candidate failed one or more hard correctness gates")
        status = "INVALID"
        deltas: dict[str, Any] = {}
        guardrails: dict[str, bool] = {"hard_gate_pass": False}
        improvements: dict[str, bool] = {}
    else:
        baseline_metrics = baseline["aggregate"]
        candidate_metrics = candidate["aggregate"]
        promotion = config["promotion"]

        size_gain = fractional_gain(
            baseline_metrics["total_compressed_bytes"],
            candidate_metrics["total_compressed_bytes"],
        )
        encode_gain = fractional_gain(
            baseline_metrics["encode_wall_ns"],
            candidate_metrics["encode_wall_ns"],
        )
        decode_gain = fractional_gain(
            baseline_metrics["decode_wall_ns"],
            candidate_metrics["decode_wall_ns"],
        )
        cost_gain = fractional_gain(
            baseline_metrics["economic_scenario"]["total_gbp"],
            candidate_metrics["economic_scenario"]["total_gbp"],
        )
        deltas = {
            "compressed_size_gain_fraction": size_gain,
            "encode_time_gain_fraction": encode_gain,
            "decode_time_gain_fraction": decode_gain,
            "annualized_cost_gain_fraction": cost_gain,
            "compressed_bytes_delta": (
                candidate_metrics["total_compressed_bytes"]
                - baseline_metrics["total_compressed_bytes"]
            ),
        }

        guardrails = {
            "hard_gate_pass": True,
            "size_not_larger": candidate_metrics["total_compressed_bytes"]
            <= baseline_metrics["total_compressed_bytes"],
            "encode_within_limit": candidate_metrics["encode_wall_ns"]
            <= baseline_metrics["encode_wall_ns"]
            * (1 + float(promotion["max_encode_slowdown_fraction"])),
            "decode_within_limit": candidate_metrics["decode_wall_ns"]
            <= baseline_metrics["decode_wall_ns"]
            * (1 + float(promotion["max_decode_slowdown_fraction"])),
            "annualized_cost_not_higher": candidate_metrics["economic_scenario"]["total_gbp"]
            <= baseline_metrics["economic_scenario"]["total_gbp"],
        }
        improvements = {
            "size": size_gain >= float(promotion["minimum_size_improvement_fraction"]),
            "encode_time": encode_gain >= float(promotion["minimum_timing_improvement_fraction"]),
            "decode_time": decode_gain >= float(promotion["minimum_timing_improvement_fraction"]),
            "annualized_cost": cost_gain >= float(promotion["minimum_cost_improvement_fraction"]),
        }

        for name, passed in guardrails.items():
            if not passed:
                reasons.append(f"guardrail failed: {name}")
        if not any(improvements.values()):
            reasons.append("no metric crossed its predeclared minimum improvement")

        status = (
            "ELIGIBLE_FOR_REPRODUCTION"
            if all(guardrails.values()) and any(improvements.values())
            else "VALID_NO_GAIN"
        )

    unsigned = {
        "schema_version": 1,
        "decision_type": "wb001_public_baseline_comparison",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workbench": candidate["workbench"],
        "baseline_result_sha256": baseline["result_sha256"],
        "candidate_result_sha256": candidate["result_sha256"],
        "candidate_artifact_sha256": candidate["candidate_artifact_sha256"],
        "corpus_sha256": candidate["corpus"]["corpus_sha256"],
        "status": status,
        "guardrails": guardrails,
        "minimum_improvements_met": improvements,
        "deltas": deltas,
        "reasons": reasons,
    }
    return {**unsigned, "decision_sha256": sha256_bytes(canonical_json_bytes(unsigned))}


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare a WB-001 candidate with a pinned baseline")
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    decision = compare(
        load_json(args.baseline),
        load_json(args.candidate),
        load_workbench_config(args.config),
    )
    write_json(args.output, decision)
    print(json.dumps({"output": str(args.output), "status": decision["status"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

