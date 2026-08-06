from __future__ import annotations

import sys
from pathlib import Path


FACTORY_ROOT = Path(__file__).resolve().parents[2]
if str(FACTORY_ROOT) not in sys.path:
    sys.path.insert(0, str(FACTORY_ROOT))

from control_plane.common import canonical_json_bytes, sha256_bytes, sha256_file, write_json


CONTROL_FILES = [
    "factoryctl.py",
    "control_plane/__init__.py",
    "control_plane/attestation.py",
    "control_plane/audit.py",
    "control_plane/cli.py",
    "control_plane/common.py",
    "control_plane/evidence.py",
    "control_plane/envelope.py",
    "control_plane/ledger.py",
    "control_plane/sealed.py",
    "control_plane/wb001_adapter.py",
    "control_plane/workflow.py",
    "control_plane/schemas/checkpoint.schema.json",
    "control_plane/schemas/blind-audit-v1.schema.json",
    "control_plane/schemas/attempt-receipt-v2.schema.json",
    "control_plane/schemas/entry-gate.schema.json",
    "control_plane/schemas/event.schema.json",
    "control_plane/schemas/round.schema.json",
    "control_plane/schemas/work-order-envelope-policy-v2.schema.json",
    "control_plane/schemas/work-order-envelope-v2.schema.json",
    "control_plane/examples/wb001-synthetic-envelope-policy.json",
    "control_plane/scripts/run_entry_gate.py",
    "control_plane/scripts/validate_control_plane.py",
    "rounds/WB001-PILOT-001/STARTER_PACK.md",
]

EVALUATOR_FILES = [
    "workbenches/wb001_lossless_compression/workbench.toml",
    "workbenches/wb001_lossless_compression/runner/baseline_frontier.py",
    "workbenches/wb001_lossless_compression/runner/blind_evaluate.py",
    "workbenches/wb001_lossless_compression/runner/common.py",
    "workbenches/wb001_lossless_compression/runner/compare_frontier.py",
    "workbenches/wb001_lossless_compression/runner/evaluate_isolated.py",
    "workbenches/wb001_lossless_compression/runner/evaluate_local.py",
    "workbenches/wb001_lossless_compression/runner/issue_job_token.py",
    "workbenches/wb001_lossless_compression/runner/process_control.py",
    "workbenches/wb001_lossless_compression/runner/signing.py",
    "workbenches/wb001_lossless_compression/runner/verify_attestation.py",
    "workbenches/wb001_lossless_compression/runner/verify_reproductions.py",
    "workbenches/wb001_lossless_compression/schemas/result.schema.json",
    "workbenches/wb001_lossless_compression/schemas/submission.schema.json",
]


def build(lock_type: str, relative_paths: list[str]) -> dict:
    files = [
        {"path": relative, "sha256": sha256_file(FACTORY_ROOT / relative)}
        for relative in sorted(relative_paths)
    ]
    core = {"schema_version": 1, "lock_type": lock_type, "files": files}
    return {**core, "software_sha256": sha256_bytes(canonical_json_bytes(core))}


def main() -> int:
    control = build("research_factory_control_plane", CONTROL_FILES)
    evaluator = build("wb001_evaluator", EVALUATOR_FILES)
    write_json(FACTORY_ROOT / "control_plane" / "software.lock.json", control)
    write_json(
        FACTORY_ROOT
        / "workbenches"
        / "wb001_lossless_compression"
        / "isolation"
        / "evaluator_software.lock.json",
        evaluator,
    )
    print(f"control_plane={control['software_sha256']}")
    print(f"wb001_evaluator={evaluator['software_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
