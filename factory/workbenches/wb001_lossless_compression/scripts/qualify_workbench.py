from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


WORKBENCH_ROOT = Path(__file__).resolve().parents[1]
FACTORY_ROOT = WORKBENCH_ROOT.parents[1]
RUNNER_ROOT = WORKBENCH_ROOT / "runner"
sys.path.insert(0, str(RUNNER_ROOT))

from baseline_frontier import verify_pack_hash  # noqa: E402
from common import load_json, load_workbench_config, write_json  # noqa: E402
from compare_frontier import compare_to_frontier  # noqa: E402
from evaluate_local import evaluate_submission  # noqa: E402
from package_evidence import package_manifest  # noqa: E402


def run_script(path: Path) -> None:
    subprocess.run([sys.executable, str(path)], cwd=FACTORY_ROOT, check=True)


def evidence_files(candidate_result: Path, comparison: Path, *, include_isolation: bool) -> list[Path]:
    files = [
        FACTORY_ROOT / "README.md",
        FACTORY_ROOT / "pyproject.toml",
        FACTORY_ROOT / "requirements.lock",
        WORKBENCH_ROOT / "README.md",
        WORKBENCH_ROOT / "PROTOCOL.md",
        WORKBENCH_ROOT / "SECURITY.md",
        WORKBENCH_ROOT / "workbench.toml",
        WORKBENCH_ROOT / "data" / "README.md",
        WORKBENCH_ROOT / "data" / "public_manifest.json",
        WORKBENCH_ROOT / "data" / "holdout_commitment.json",
        WORKBENCH_ROOT / "data" / "evaluator_public_key.json",
        WORKBENCH_ROOT / "examples" / "zlib_level9" / "candidate.py",
        WORKBENCH_ROOT / "examples" / "zlib_level9" / "submission.json",
        WORKBENCH_ROOT / "results" / "reference_pack" / "baseline_pack.json",
        candidate_result,
        comparison,
    ]
    for pattern in (
        "baselines/reference_pack/*",
        "runner/*.py",
        "schemas/*.json",
        "scripts/*.py",
        "isolation/Dockerfile",
        "isolation/*.toml",
        "isolation/*.lock",
        "isolation/*.json",
        "results/reference_pack/*.result.json",
    ):
        files.extend(path for path in WORKBENCH_ROOT.glob(pattern) if path.is_file())
    if include_isolation:
        isolation_root = WORKBENCH_ROOT / "results" / "isolation_qualification"
        files.extend(path for path in isolation_root.glob("*.json") if path.is_file())
        blind_attestation = WORKBENCH_ROOT / "results" / "blind_demo" / "public_attestation.json"
        if blind_attestation.is_file():
            files.append(blind_attestation)
    return sorted(set(path.resolve() for path in files), key=lambda path: str(path).lower())


def main() -> int:
    parser = argparse.ArgumentParser(description="Run WB-001 v0.2 qualification")
    parser.add_argument("--full", action="store_true", help="also run Docker adversarial probes")
    parser.add_argument("--reuse-pack", action="store_true", help="reuse the existing public pack")
    args = parser.parse_args()

    result_root = WORKBENCH_ROOT / "results" / "qualification_v0_2"
    result_root.mkdir(parents=True, exist_ok=True)
    run_script(WORKBENCH_ROOT / "scripts" / "build_public_corpus.py")
    pack_path = WORKBENCH_ROOT / "results" / "reference_pack" / "baseline_pack.json"
    if not args.reuse_pack or not pack_path.is_file():
        run_script(WORKBENCH_ROOT / "scripts" / "build_reference_pack.py")

    pack = load_json(pack_path)
    verify_pack_hash(pack)
    candidate_result_path = result_root / "candidate_result.json"
    candidate = evaluate_submission(
        WORKBENCH_ROOT / "examples" / "zlib_level9" / "submission.json",
        "demo:qualification-author",
    )
    write_json(candidate_result_path, candidate)
    comparison = compare_to_frontier(pack, candidate, load_workbench_config())
    comparison_path = result_root / "frontier_comparison.json"
    write_json(comparison_path, comparison)

    if args.full:
        run_script(WORKBENCH_ROOT / "scripts" / "qualify_isolation.py")

    evidence = package_manifest(
        evidence_files(candidate_result_path, comparison_path, include_isolation=args.full),
        root=FACTORY_ROOT,
    )
    evidence_path = result_root / "evidence_manifest.json"
    write_json(evidence_path, evidence)
    summary = {
        "workbench": "WB-001",
        "version": "0.2.0",
        "candidate_hard_gate_pass": candidate["hard_gate_pass"],
        "public_frontier_status": comparison["status"],
        "timing_claim_accepted": comparison["timing_claim_accepted"],
        "reference_profiles": len(pack["entries"]),
        "frontier_profiles": len(pack["frontier_profile_ids"]),
        "pack_state": pack["pack_state"],
        "pack_sha256": pack["pack_sha256"],
        "evidence_manifest": str(evidence_path),
        "evidence_package_sha256": evidence["package_sha256"],
        "isolation_qualified": args.full,
        "note": "Demo identities verify plumbing only and never satisfy human independence.",
    }
    write_json(result_root / "summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
