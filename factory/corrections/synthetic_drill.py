from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from control_plane.common import (
    ContractError,
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
    write_json,
)

from .ledger import CorrectionLedger, load_json_strict


REPORT_KEYS = {
    "schema_version",
    "drill_id",
    "scope",
    "records",
    "original_artifact_sha256",
    "corrected_artifact_sha256",
    "ledger_sha256",
    "head_record_sha256",
    "final_standing",
    "original_bytes_preserved",
    "scientific_standing",
    "eligible_for_promotion",
    "report_sha256",
}


def _artifact_reference(artifact_id: str, digest: str, filename: str) -> dict[str, Any]:
    return {
        "artifact_class": "SHIFT_REPORT",
        "artifact_id": artifact_id,
        "artifact_sha256": digest,
        "locator_kind": "PUBLIC_URL",
        "locator": f"https://example.invalid/research-factory/synthetic/{filename}",
        "media_type": "application/json",
        "visibility": "PUBLIC",
    }


def _draft(
    *,
    correction_id: str,
    action: str,
    target: dict[str, Any],
    replacement: dict[str, Any] | None,
    reason_code: str,
    reason: str,
    public_summary: str,
) -> dict[str, Any]:
    return {
        "correction_id": correction_id,
        "actor": {
            "operator_id": "human:synthetic-commissioner",
            "display_name": "Synthetic Commissioner",
            "identity_assurance": "SELF_ASSERTED_LOCAL",
            "identity_warning": "IDENTITY_RECORD_IS_NOT_PROOF_OF_AUTHORITY",
        },
        "authority": {
            "basis": "MAINTAINER",
            "scope": "Known-answer synthetic correction drill only.",
            "conflict_declaration": (
                "The same local operator created every fixture; no independence is claimed."
            ),
            "authorization_evidence_sha256": [],
        },
        "target": target,
        "action": action,
        "replacement": replacement,
        "reason": {
            "code": reason_code,
            "summary": reason,
            "evidence_references": [],
        },
        "public_summary": public_summary,
    }


def run_synthetic_drill(output: Path) -> dict[str, Any]:
    output = output.resolve()
    if output.exists():
        raise ContractError(f"synthetic correction output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    try:
        public = staging / "public"
        public.mkdir()
        original = public / "original-shift-report.json"
        corrected = public / "corrected-shift-report.json"
        write_json(
            original,
            {
                "fixture": "SYNTHETIC_ONLY",
                "statement": "The synthetic calibration checksum passed.",
                "standing": "KNOWN_FALSE_FIXTURE",
            },
        )
        write_json(
            corrected,
            {
                "fixture": "SYNTHETIC_ONLY",
                "statement": "The synthetic calibration checksum failed.",
                "standing": "CORRECTED_FIXTURE",
            },
        )
        original_ref = _artifact_reference(
            "shift-report:synthetic-false-calibration",
            sha256_file(original),
            original.name,
        )
        corrected_ref = _artifact_reference(
            "shift-report:synthetic-corrected-calibration",
            sha256_file(corrected),
            corrected.name,
        )

        ledger = CorrectionLedger(public / "corrections.jsonl")
        ledger.append(
            _draft(
                correction_id="correction:synthetic-corrigendum",
                action="CORRIGENDUM",
                target=original_ref,
                replacement=corrected_ref,
                reason_code="MATERIAL_ERROR",
                reason=(
                    "The visible known-answer fixture proves that the original synthetic "
                    "calibration statement was false."
                ),
                public_summary=(
                    "Correct the false synthetic calibration statement without replacing its bytes."
                ),
            ),
            recorded_at="2026-08-06T10:00:00Z",
        )
        ledger.append(
            _draft(
                correction_id="correction:synthetic-retraction",
                action="RETRACTION",
                target=original_ref,
                replacement=None,
                reason_code="WITHDRAWN_CLAIM",
                reason=(
                    "The synthetic commissioning article is withdrawn after its deliberately "
                    "false conclusion was confirmed."
                ),
                public_summary=(
                    "Retract the synthetic article while retaining the original and corrigendum."
                ),
            ),
            recorded_at="2026-08-06T11:00:00Z",
        )
        index_path = public / "correction-index.json"
        ledger.export_public_index(index_path)
        verified = ledger.verify()
        report_unsigned = {
            "schema_version": 1,
            "drill_id": "CORRECTION-SYNTHETIC-001",
            "scope": "SYNTHETIC_COMMISSIONING_ONLY",
            "records": verified["records"],
            "original_artifact_sha256": sha256_file(original),
            "corrected_artifact_sha256": sha256_file(corrected),
            "ledger_sha256": verified["ledger_sha256"],
            "head_record_sha256": verified["head_record_sha256"],
            "final_standing": "RETRACTED",
            "original_bytes_preserved": True,
            "scientific_standing": "NONE_SYNTHETIC_COMMISSIONING_ONLY",
            "eligible_for_promotion": False,
        }
        report = {
            **report_unsigned,
            "report_sha256": sha256_bytes(canonical_json_bytes(report_unsigned)),
        }
        write_json(public / "report.json", report)
        ledger.lock_path.unlink(missing_ok=True)
        verify_synthetic_drill(staging)
        os.replace(staging, output)
        return report
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def verify_synthetic_drill(output: Path) -> dict[str, Any]:
    output = output.resolve()
    public = output / "public"
    expected_files = {
        "corrected-shift-report.json",
        "correction-index.json",
        "corrections.jsonl",
        "original-shift-report.json",
        "report.json",
    }
    if not public.is_dir() or {path.name for path in public.iterdir()} != expected_files:
        raise ContractError("synthetic correction drill has missing or unexpected public files")
    report = load_json_strict(public / "report.json")
    if set(report) != REPORT_KEYS:
        raise ContractError("synthetic correction report has an invalid closed shape")
    unsigned = {key: value for key, value in report.items() if key != "report_sha256"}
    if sha256_bytes(canonical_json_bytes(unsigned)) != report["report_sha256"]:
        raise ContractError("synthetic correction report self-hash does not match")
    if report["scope"] != "SYNTHETIC_COMMISSIONING_ONLY":
        raise ContractError("synthetic correction drill escaped its commissioning scope")
    if report["scientific_standing"] != "NONE_SYNTHETIC_COMMISSIONING_ONLY":
        raise ContractError("synthetic correction drill claims scientific standing")
    if report["eligible_for_promotion"] is not False:
        raise ContractError("synthetic correction drill claims promotion eligibility")

    original = public / "original-shift-report.json"
    corrected = public / "corrected-shift-report.json"
    if sha256_file(original) != report["original_artifact_sha256"]:
        raise ContractError("synthetic original artifact bytes changed")
    if sha256_file(corrected) != report["corrected_artifact_sha256"]:
        raise ContractError("synthetic corrected artifact bytes changed")
    if report["original_artifact_sha256"] == report["corrected_artifact_sha256"]:
        raise ContractError("synthetic correction did not change the artifact bytes")

    ledger = CorrectionLedger(public / "corrections.jsonl")
    records = ledger.read()
    verified = ledger.verify()
    if len(records) != 2 or [record["action"] for record in records] != [
        "CORRIGENDUM",
        "RETRACTION",
    ]:
        raise ContractError("synthetic correction ledger has the wrong transition sequence")
    if records[0]["standing_before"] != "CURRENT":
        raise ContractError("synthetic correction did not start from CURRENT")
    if records[1]["standing_before"] != "CURRENT_WITH_CORRECTION":
        raise ContractError("synthetic retraction did not retain the corrigendum standing")
    if records[1]["standing_after"] != "RETRACTED":
        raise ContractError("synthetic correction drill did not end retracted")
    if records[0]["target"]["artifact_sha256"] != report["original_artifact_sha256"]:
        raise ContractError("synthetic correction targets the wrong original bytes")
    if records[0]["replacement"]["artifact_sha256"] != report["corrected_artifact_sha256"]:
        raise ContractError("synthetic corrigendum points to the wrong corrected bytes")
    if verified["ledger_sha256"] != report["ledger_sha256"]:
        raise ContractError("synthetic correction ledger hash does not match the report")
    if verified["head_record_sha256"] != report["head_record_sha256"]:
        raise ContractError("synthetic correction head does not match the report")
    if verified["current_standings"] != {"RETRACTED": 1}:
        raise ContractError("synthetic correction current standing is not retracted")

    expected_index = ledger.history(limit=500)
    expected_index["ledger"].pop("ledger", None)
    actual_index = load_json_strict(public / "correction-index.json")
    if actual_index != expected_index:
        raise ContractError("synthetic public correction index does not match the ledger")
    return {
        "valid": True,
        "records": 2,
        "final_standing": "RETRACTED",
        "head_record_sha256": verified["head_record_sha256"],
        "report_sha256": report["report_sha256"],
        "scientific_standing": report["scientific_standing"],
        "eligible_for_promotion": False,
    }
