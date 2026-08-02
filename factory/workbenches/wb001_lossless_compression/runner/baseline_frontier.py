from __future__ import annotations

import argparse
import json
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import (
    ContractError,
    canonical_json_bytes,
    load_json,
    sha256_bytes,
    verify_result_hash,
    write_json,
)


DIMENSIONS = (
    "total_compressed_bytes",
    "encode_wall_ns",
    "decode_wall_ns",
    "peak_rss_bytes",
)


def metric_vector(result: dict[str, Any]) -> dict[str, int]:
    aggregate = result.get("aggregate")
    if not isinstance(aggregate, dict):
        raise ContractError("result has no aggregate metrics")
    try:
        return {name: int(aggregate[name]) for name in DIMENSIONS}
    except (KeyError, TypeError, ValueError) as exc:
        raise ContractError("result is missing a baseline-frontier metric") from exc


def dominates(left: dict[str, int], right: dict[str, int]) -> bool:
    return all(left[name] <= right[name] for name in DIMENSIONS) and any(
        left[name] < right[name] for name in DIMENSIONS
    )


def execution_class(result: dict[str, Any]) -> dict[str, Any]:
    environment = result.get("environment", {})
    boundary = result.get("execution_boundary", {})
    return {
        "system": environment.get("system"),
        "release": environment.get("release"),
        "machine": environment.get("machine"),
        "python": environment.get("python"),
        "python_executable_sha256": environment.get("python_executable_sha256"),
        "boundary": boundary,
    }


def compute_frontier(entries: list[dict[str, Any]]) -> list[str]:
    frontier: list[str] = []
    for candidate in entries:
        if not any(
            other["profile_id"] != candidate["profile_id"]
            and dominates(other["metrics"], candidate["metrics"])
            for other in entries
        ):
            frontier.append(candidate["profile_id"])
    return sorted(frontier)


def verify_pack_hash(pack: dict[str, Any]) -> None:
    expected = pack.get("pack_sha256")
    unsigned = {key: value for key, value in pack.items() if key != "pack_sha256"}
    if expected != sha256_bytes(canonical_json_bytes(unsigned)):
        raise ContractError("baseline pack hash does not match its contents")


def load_definition(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            definition = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ContractError(f"could not load baseline definition: {exc}") from exc
    if definition.get("schema_version") != 1:
        raise ContractError("unsupported baseline definition schema")
    return definition


def build_pack(
    definition: dict[str, Any],
    results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    declared_ids = [profile["id"] for profile in definition["profiles"]]
    if set(results) != set(declared_ids):
        missing = sorted(set(declared_ids) - set(results))
        extra = sorted(set(results) - set(declared_ids))
        raise ContractError(f"baseline result set mismatch; missing={missing}, extra={extra}")

    entries: list[dict[str, Any]] = []
    workbench: dict[str, Any] | None = None
    corpus: dict[str, Any] | None = None
    class_document: dict[str, Any] | None = None
    for profile_id in declared_ids:
        result = results[profile_id]
        verify_result_hash(result)
        if not result.get("hard_gate_pass"):
            raise ContractError(f"baseline profile {profile_id} failed a hard gate")
        reported_profile = result.get("candidate", {}).get("metadata", {}).get("profile_id")
        if reported_profile != profile_id:
            raise ContractError(f"baseline profile identity mismatch for {profile_id}")
        if workbench is None:
            workbench = result["workbench"]
            corpus = result["corpus"]
            class_document = execution_class(result)
        elif result["workbench"] != workbench:
            raise ContractError("baseline results target different workbench versions")
        elif result["corpus"]["corpus_sha256"] != corpus["corpus_sha256"]:
            raise ContractError("baseline results use different corpus commitments")
        elif execution_class(result) != class_document:
            raise ContractError("baseline results were not measured in one execution class")

        file_fingerprint = [
            {
                "path": row["path"],
                "compressed_bytes": row["compressed_bytes"],
                "compressed_sha256": row["compressed_sha256"],
            }
            for row in result["files"]
        ]
        entries.append(
            {
                "profile_id": profile_id,
                "submission_id": result["submission_id"],
                "candidate_artifact_sha256": result["candidate_artifact_sha256"],
                "result_sha256": result["result_sha256"],
                "runtime_fingerprint_sha256": result["runtime_fingerprint_sha256"],
                "metrics": metric_vector(result),
                "annualized_scenario_cost_gbp": result["aggregate"]["economic_scenario"]["total_gbp"],
                "file_fingerprint_sha256": sha256_bytes(canonical_json_bytes(file_fingerprint)),
            }
        )

    assert workbench is not None and corpus is not None and class_document is not None
    declared_promotable = bool(definition.get("promotable"))
    secure_boundary = bool(class_document.get("boundary", {}).get("security_boundary"))
    promotion_grade = bool(class_document.get("boundary", {}).get("promotion_grade"))
    promotable = declared_promotable and secure_boundary and promotion_grade
    unsigned = {
        "schema_version": 1,
        "pack_type": "wb001_baseline_frontier",
        "pack_id": definition["pack_id"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workbench": workbench,
        "corpus_sha256": corpus["corpus_sha256"],
        "corpus_manifest_sha256": corpus["manifest_sha256"],
        "timing_grade": definition["timing_grade"],
        "promotable": promotable,
        "pack_state": "PINNED_PROMOTION_PACK" if promotable else "LOCAL_QUALIFICATION_ONLY",
        "execution_class": class_document,
        "execution_class_sha256": sha256_bytes(canonical_json_bytes(class_document)),
        "dimensions": list(DIMENSIONS),
        "entries": entries,
        "frontier_profile_ids": compute_frontier(entries),
    }
    return {**unsigned, "pack_sha256": sha256_bytes(canonical_json_bytes(unsigned))}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and hash a WB-001 reference frontier")
    parser.add_argument("--definition", type=Path, required=True)
    parser.add_argument("--result", action="append", default=[], metavar="PROFILE=PATH")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    results: dict[str, dict[str, Any]] = {}
    for value in args.result:
        if "=" not in value:
            raise SystemExit("--result must use PROFILE=PATH")
        profile_id, raw_path = value.split("=", 1)
        if profile_id in results:
            raise SystemExit(f"duplicate result profile: {profile_id}")
        results[profile_id] = load_json(Path(raw_path))
    pack = build_pack(load_definition(args.definition), results)
    write_json(args.output, pack)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "pack_state": pack["pack_state"],
                "profiles": len(pack["entries"]),
                "frontier": pack["frontier_profile_ids"],
                "pack_sha256": pack["pack_sha256"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
