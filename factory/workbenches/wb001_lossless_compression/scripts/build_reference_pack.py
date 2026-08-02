from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


WORKBENCH_ROOT = Path(__file__).resolve().parents[1]
RUNNER_ROOT = WORKBENCH_ROOT / "runner"
sys.path.insert(0, str(RUNNER_ROOT))

from baseline_frontier import build_pack, load_definition  # noqa: E402
from common import write_json  # noqa: E402
from evaluate_local import evaluate_submission  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate all WB-001 reference profiles")
    parser.add_argument(
        "--definition",
        type=Path,
        default=WORKBENCH_ROOT / "baselines" / "reference_pack" / "baseline_pack.toml",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=WORKBENCH_ROOT / "data" / "public_manifest.json",
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=WORKBENCH_ROOT / "results" / "reference_pack",
    )
    args = parser.parse_args()

    definition_path = args.definition.resolve()
    definition = load_definition(definition_path)
    submission_root = definition_path.parent
    output_root = args.output_directory.resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    results = {}
    for index, profile in enumerate(definition["profiles"], start=1):
        profile_id = profile["id"]
        submission_path = submission_root / profile["submission"]
        print(f"[{index}/{len(definition['profiles'])}] evaluating {profile_id}", flush=True)
        result = evaluate_submission(
            submission_path,
            f"demo:central-{profile_id}",
            manifest_path=args.manifest,
        )
        result_path = output_root / f"{profile_id}.result.json"
        write_json(result_path, result)
        if not result["hard_gate_pass"]:
            print(json.dumps(result["failures"], indent=2), flush=True)
            raise SystemExit(f"reference profile failed: {profile_id}")
        results[profile_id] = result

    pack = build_pack(definition, results)
    pack_path = output_root / "baseline_pack.json"
    write_json(pack_path, pack)
    print(
        json.dumps(
            {
                "output": str(pack_path),
                "pack_state": pack["pack_state"],
                "profiles": len(pack["entries"]),
                "frontier": pack["frontier_profile_ids"],
                "pack_sha256": pack["pack_sha256"],
            },
            indent=2,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
