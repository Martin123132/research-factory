from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


WORKBENCH_ROOT = Path(__file__).resolve().parents[1]
FACTORY_ROOT = WORKBENCH_ROOT.parents[1]
RUNNER_ROOT = WORKBENCH_ROOT / "runner"
sys.path.insert(0, str(RUNNER_ROOT))

from baseline_frontier import build_pack, load_definition  # noqa: E402
from common import ContractError, load_json, sha256_file, verify_commitment_hash, write_json  # noqa: E402
from evaluate_isolated import DockerExecutorFactory  # noqa: E402
from evaluate_local import evaluate_submission  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the private isolated WB-001 reference pack")
    parser.add_argument("--private-root", type=Path, default=FACTORY_ROOT / "private" / "wb001")
    parser.add_argument(
        "--definition",
        type=Path,
        default=WORKBENCH_ROOT / "baselines" / "reference_pack" / "baseline_pack.toml",
    )
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
    manifest_path = private_root / "holdout_manifest.json"
    commitment = load_json(WORKBENCH_ROOT / "data" / "holdout_commitment.json")
    verify_commitment_hash(commitment)
    manifest = load_json(manifest_path)
    if commitment["manifest_sha256"] != sha256_file(manifest_path):
        raise ContractError("private holdout no longer matches the public manifest commitment")
    if commitment["corpus_sha256"] != manifest["corpus_sha256"]:
        raise ContractError("private holdout no longer matches the public corpus commitment")

    definition_path = args.definition.resolve()
    definition = load_definition(definition_path)
    submission_root = definition_path.parent
    output_root = private_root / "reference_pack"
    output_root.mkdir(parents=True, exist_ok=True)
    executor_factory = DockerExecutorFactory(args.policy, args.image_lock)

    results = {}
    for index, profile in enumerate(definition["profiles"], start=1):
        profile_id = profile["id"]
        print(f"[{index}/{len(definition['profiles'])}] sealed reference {profile_id}", flush=True)
        result = evaluate_submission(
            submission_root / profile["submission"],
            f"demo:sealed-{profile_id}",
            manifest_path=manifest_path,
            executor_factory=executor_factory,
        )
        write_json(output_root / f"{profile_id}.result.json", result)
        if not result["hard_gate_pass"]:
            raise SystemExit(f"sealed reference profile failed: {profile_id}")
        results[profile_id] = result

    pack = build_pack(definition, results)
    pack_path = output_root / "baseline_pack.json"
    write_json(pack_path, pack)
    print(
        json.dumps(
            {
                "private_pack": str(pack_path),
                "profiles": len(pack["entries"]),
                "frontier_profiles": len(pack["frontier_profile_ids"]),
                "pack_state": pack["pack_state"],
                "pack_sha256": pack["pack_sha256"],
                "holdout_commitment_sha256": commitment["commitment_sha256"],
            },
            indent=2,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
