from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ROOT.parents[2]
EVALUATOR = REPOSITORY_ROOT / "factory" / "workbench_standard" / "commissioning" / "runner" / "evaluate_trusted.py"
SUBMISSION = ROOT / "examples" / "zlib_reference" / "submission.json"
FIXTURE = ROOT / "data" / "entry_fixture.txt"
EXPECTED = ROOT / "baselines" / "entry_expected.json"


def stable_evidence(result: dict) -> dict:
    return {"input": result["input"], "artifact": result["artifact"], "hard_gates": result["hard_gates"]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the WB-002 entry-only method gate")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--fixture", action="store_true")
    source.add_argument("--enwik8", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    input_path = FIXTURE if args.fixture else args.enwik8
    command = [
        sys.executable, str(EVALUATOR), "--submission", str(SUBMISSION), "--input", str(input_path),
        "--output", str(args.output), "--timeout-seconds", "900", "--i-understand-this-runs-trusted-local-code",
    ]
    subprocess.run(command, cwd=REPOSITORY_ROOT, check=True)
    result = json.loads(args.output.read_text(encoding="utf-8"))
    if args.fixture:
        expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
        if expected["status"] != "FROZEN" or stable_evidence(result) != expected["stable_evidence"]:
            raise SystemExit("FAIL result does not reproduce the locked entry fixture")
    print("PASS — ENTRY_GATE_ONLY — ZERO SCIENTIFIC CREDIT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
