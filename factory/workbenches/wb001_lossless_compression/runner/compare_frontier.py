from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from baseline_frontier import (
    compute_frontier,
    dominates,
    execution_class,
    metric_vector,
    verify_pack_hash,
)
from common import (
    ContractError,
    canonical_json_bytes,
    load_json,
    load_workbench_config,
    sha256_bytes,
    verify_result_hash,
    write_json,
)


def compare_to_frontier(
    pack: dict[str, Any],
    candidate: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    verify_pack_hash(pack)
    verify_result_hash(candidate)
    if candidate["workbench"] != pack["workbench"]:
        raise ContractError("candidate and baseline pack target different workbench versions")
    if candidate["corpus"]["corpus_sha256"] != pack["corpus_sha256"]:
        raise ContractError("candidate and baseline pack use different corpus commitments")
    candidate_execution_class = execution_class(candidate)
    if sha256_bytes(canonical_json_bytes(candidate_execution_class)) != pack[
        "execution_class_sha256"
    ]:
        raise ContractError("candidate was not measured in the baseline pack execution class")

    candidate_metrics = metric_vector(candidate) if candidate.get("hard_gate_pass") else {}
    dominated_by: list[str] = []
    dominates_profiles: list[str] = []
    diagnostic_threshold_extremes: list[str] = []
    threshold_extremes: list[str] = []
    frontier_after = list(pack["frontier_profile_ids"])
    reasons: list[str] = []

    if not candidate.get("hard_gate_pass"):
        status = "INVALID"
        reasons.append("candidate failed one or more hard correctness gates")
    else:
        for entry in pack["entries"]:
            if dominates(entry["metrics"], candidate_metrics):
                dominated_by.append(entry["profile_id"])
            if dominates(candidate_metrics, entry["metrics"]):
                dominates_profiles.append(entry["profile_id"])

        promotion = config["promotion"]
        thresholds = {
            "total_compressed_bytes": float(promotion["minimum_size_improvement_fraction"]),
            "encode_wall_ns": float(promotion["minimum_timing_improvement_fraction"]),
            "decode_wall_ns": float(promotion["minimum_timing_improvement_fraction"]),
            "peak_rss_bytes": float(promotion["minimum_timing_improvement_fraction"]),
        }
        for metric, threshold in thresholds.items():
            best = min(entry["metrics"][metric] for entry in pack["entries"])
            if candidate_metrics[metric] <= best * (1 - threshold):
                diagnostic_threshold_extremes.append(metric)

        threshold_extremes = (
            diagnostic_threshold_extremes
            if pack["promotable"]
            else [
                metric
                for metric in diagnostic_threshold_extremes
                if metric == "total_compressed_bytes"
            ]
        )

        synthetic_entry = {"profile_id": "candidate", "metrics": candidate_metrics}
        frontier_after = compute_frontier([*pack["entries"], synthetic_entry])
        if not pack["promotable"]:
            best_size = min(
                entry["metrics"]["total_compressed_bytes"] for entry in pack["entries"]
            )
            required_size_gain = float(promotion["minimum_size_improvement_fraction"])
            exact_size_advance = (
                candidate_metrics["total_compressed_bytes"]
                <= best_size * (1 - required_size_gain)
            )
            if exact_size_advance:
                status = "PUBLIC_SIZE_CANDIDATE"
                reasons.append(
                    "exact compressed size advanced; promotion-grade paired timing remains required"
                )
            else:
                status = "VALID_NO_CONFIRMED_GAIN"
                reasons.append(
                    "advisory timing and memory measurements cannot establish an advance"
                )
        elif dominated_by:
            status = "VALID_DOMINATED"
            reasons.append("one or more pinned reference profiles dominate the candidate")
        elif dominates_profiles or threshold_extremes:
            status = "FRONTIER_ADVANCE"
        else:
            status = "VALID_NONDOMINATED_NO_GAIN"
            reasons.append("candidate is non-dominated but crosses no predeclared improvement threshold")

    unsigned = {
        "schema_version": 2,
        "decision_type": "wb001_frontier_comparison",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workbench": candidate["workbench"],
        "baseline_pack_sha256": pack["pack_sha256"],
        "candidate_result_sha256": candidate["result_sha256"],
        "candidate_artifact_sha256": candidate["candidate_artifact_sha256"],
        "corpus_sha256": candidate["corpus"]["corpus_sha256"],
        "status": status,
        "eligible_for_promotion": status == "FRONTIER_ADVANCE",
        "timing_claim_accepted": bool(pack["promotable"]),
        "candidate_metrics": candidate_metrics,
        "dominated_by": sorted(dominated_by),
        "dominates_profiles": sorted(dominates_profiles),
        "threshold_extremes": sorted(threshold_extremes),
        "diagnostic_threshold_extremes": sorted(diagnostic_threshold_extremes),
        "frontier_before": pack["frontier_profile_ids"],
        "frontier_after": frontier_after,
        "reasons": reasons,
    }
    return {**unsigned, "decision_sha256": sha256_bytes(canonical_json_bytes(unsigned))}


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare a candidate to the entire WB-001 frontier")
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    decision = compare_to_frontier(
        load_json(args.pack),
        load_json(args.candidate),
        load_workbench_config(args.config),
    )
    write_json(args.output, decision)
    print(json.dumps({"output": str(args.output), "status": decision["status"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
