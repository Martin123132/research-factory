from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


FACTORY_ROOT = Path(__file__).resolve().parents[2]
WB_ROOT = FACTORY_ROOT / "workbenches" / "wb001_lossless_compression"
sys.path.insert(0, str(FACTORY_ROOT))

from control_plane.common import canonical_json_bytes, load_json, sha256_bytes, write_json  # noqa: E402
from control_plane.workflow import _validate_round_document  # noqa: E402


def _run(command: list[str], *, timeout: int = 600) -> dict[str, object]:
    completed = subprocess.run(
        command,
        cwd=FACTORY_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    output = completed.stdout[-65536:]
    if completed.returncode != 0:
        raise RuntimeError(f"entry-gate command failed ({completed.returncode}):\n{output}")
    return {
        "command": command,
        "returncode": completed.returncode,
        "output_sha256": sha256_bytes(completed.stdout.encode("utf-8")),
        "output_tail": output,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the WB-001 standard worker entry gate")
    parser.add_argument("--operator", required=True)
    parser.add_argument(
        "--round",
        type=Path,
        default=FACTORY_ROOT / "rounds" / "WB001-PILOT-001" / "round.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--acknowledge-rules",
        action="store_true",
        help="confirm that the operator read the no-holdout and full-cost-accounting rules",
    )
    args = parser.parse_args()
    if not args.acknowledge_rules:
        parser.error("--acknowledge-rules is required")

    started = datetime.now(timezone.utc)
    round_document = load_json(args.round)
    _validate_round_document(round_document, FACTORY_ROOT)
    commands: list[dict[str, object]] = []
    commands.append(
        _run(
            [
                sys.executable,
                str(WB_ROOT / "scripts" / "validate_contracts.py"),
                "--require-generated",
            ]
        )
    )
    with tempfile.TemporaryDirectory() as temporary:
        result_path = Path(temporary) / "reference_result.json"
        commands.append(
            _run(
                [
                    sys.executable,
                    str(WB_ROOT / "runner" / "evaluate_local.py"),
                    "--submission",
                    str(WB_ROOT / "baselines" / "reference_pack" / "zlib-6.submission.json"),
                    "--operator-id",
                    args.operator,
                    "--output",
                    str(result_path),
                ]
            )
        )
        result = load_json(result_path)

    exact = bool(result.get("hard_gate_pass")) and all(
        row.get("round_trip_pass") is True for row in result.get("files", [])
    )
    deterministic = bool(result.get("files")) and all(
        row.get("deterministic") is True for row in result["files"]
    )
    checks = {
        "frozen_contracts_match": True,
        "schemas_validate": True,
        "reference_round_trip_exact": exact,
        "reference_output_deterministic": deterministic,
        "rules_acknowledged": True,
    }
    if not all(checks.values()):
        raise RuntimeError(f"entry gate did not pass: {checks}")

    unsigned = {
        "schema_version": 1,
        "evidence_type": "worker_entry_gate",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "started_at": started.isoformat(),
        "round_id": round_document["round_id"],
        "round_sha256": round_document["round_sha256"],
        "operator_id": args.operator,
        "checks": checks,
        "reference_result": {
            "result_sha256": result["result_sha256"],
            "candidate_artifact_sha256": result["candidate_artifact_sha256"],
            "corpus_sha256": result["corpus"]["corpus_sha256"],
            "files": result["aggregate"]["files"],
            "total_input_bytes": result["aggregate"]["total_input_bytes"],
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "commands": commands,
    }
    document = {
        **unsigned,
        "entry_evidence_sha256": sha256_bytes(canonical_json_bytes(unsigned)),
    }
    write_json(args.output, document)
    print(
        json.dumps(
            {
                "passed": True,
                "output": str(args.output.resolve()),
                "entry_evidence_sha256": document["entry_evidence_sha256"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
