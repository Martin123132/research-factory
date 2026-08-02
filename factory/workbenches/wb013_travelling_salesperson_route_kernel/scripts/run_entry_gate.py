from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ROOT.parents[2]
EVALUATOR = REPOSITORY_ROOT / "factory" / "workbench_standard" / "commissioning" / "runner" / "evaluate_optimization_trusted.py"
SUBMISSION = ROOT / "examples" / "reference_solver" / "submission.json"
FIXTURE = ROOT / "data" / "entry_fixture.tsp"
REFERENCE = ROOT / "baselines" / "entry_reference.json"
EXPECTED = ROOT / "baselines" / "entry_expected.json"


def stable_evidence(result: dict) -> dict:
    return {
        "input": result["input"],
        "instance": result["instance"],
        "artifact": result["artifact"],
        "hard_gates": result["hard_gates"],
        "metrics": result["metrics"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the WB-013 entry-only method gate")
    parser.add_argument("--fixture", action="store_true", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
    command = [
        sys.executable,
        str(EVALUATOR),
        "--submission", str(SUBMISSION),
        "--input", str(FIXTURE),
        "--reference-length", str(reference["reference_length"]),
        "--output", str(args.output),
        "--timeout-seconds", "120",
        "--i-understand-this-runs-trusted-local-code",
    ]
    subprocess.run(command, cwd=REPOSITORY_ROOT, check=True)
    result = json.loads(args.output.read_text(encoding="utf-8"))
    expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
    if expected["status"] != "FROZEN" or stable_evidence(result) != expected["stable_evidence"]:
        raise SystemExit("FAIL result does not reproduce the locked WB-013 entry fixture")
    print("PASS — ENTRY_GATE_ONLY — ZERO SCIENTIFIC CREDIT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
