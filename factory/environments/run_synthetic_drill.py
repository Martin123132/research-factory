"""Exercise two trusted local interpreters without changing either profile."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


FACTORY = Path(__file__).resolve().parents[1]


def run_report(python: Path, profile: str) -> dict:
    completed = subprocess.run(
        [str(python.resolve()), str(FACTORY / "enginectl.py"), "environment", "rehearse", "--profile", profile, "--json"],
        cwd=FACTORY, capture_output=True, text=True, encoding="utf-8", timeout=30, check=True,
    )
    report = json.loads(completed.stdout)
    digest = report.pop("report_sha256")
    if digest != hashlib.sha256(json.dumps(report, sort_keys=True, separators=(",", ":")).encode()).hexdigest():
        raise ValueError("rehearsal report hash mismatch")
    report["report_sha256"] = digest
    if report["environment_id"] != profile or not report["matches"] or any(report["boundary"].values()):
        raise ValueError("rehearsal report scope mismatch")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy-python", type=Path, required=True)
    parser.add_argument("--engine-python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists; retain previous evidence and use a new directory")
    legacy = run_report(args.legacy_python, "wb001-pilot-001-v1")
    engine = run_report(args.engine_python, "engine-v1")
    if legacy["lock_sha256"] == engine["lock_sha256"]:
        raise ValueError("transition must retain distinct dependency locks")
    if legacy["fixture"] != engine["fixture"]:
        raise ValueError("synthetic fixture outputs diverged; do not claim equivalence")
    # The maintenance interpreter must refuse the old profile, not silently run it.
    rejected = subprocess.run(
        [str(args.engine_python.resolve()), str(FACTORY / "enginectl.py"), "environment", "check", "--profile", "wb001-pilot-001-v1", "--json"],
        cwd=FACTORY, capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    mismatch = json.loads(rejected.stdout)
    if rejected.returncode != 2 or mismatch.get("matches") is not False:
        raise ValueError("wrong-environment rejection failed")
    result = {
        "drill_id": "environment-transition-v1",
        "fixture_outputs_equal": True,
        "wrong_environment_rejected": True,
        "reports": {"legacy": legacy["report_sha256"], "engine": engine["report_sha256"]},
        "boundary": legacy["boundary"],
        "limitation": "One public synthetic fixture, not benchmark requalification or independent reproduction.",
    }
    args.output.mkdir(parents=True, exist_ok=False)
    for name, value in (("legacy.json", legacy), ("engine.json", engine), ("wrong-environment.json", mismatch), ("drill.json", result)):
        with (args.output / name).open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(value, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
