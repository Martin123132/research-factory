from __future__ import annotations

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

from .ledger import AppealLedger, load_json_strict


REPORT_KEYS = {
    "schema_version",
    "drill_id",
    "scope",
    "records",
    "conflicted_reviewer_rejected",
    "split_routed_to_diagnosis",
    "ledger_sha256",
    "head_record_sha256",
    "scientific_standing",
    "eligible_for_promotion",
    "report_sha256",
}


def _digest(label: str) -> str:
    return sha256_bytes(label.encode("utf-8"))


def _reference(artifact_id: str, digest: str, filename: str) -> dict[str, str]:
    return {
        "artifact_class": "SHIFT_REPORT",
        "artifact_id": artifact_id,
        "artifact_sha256": digest,
        "locator_kind": "PUBLIC_URL",
        "locator": f"https://example.invalid/research-factory/appeals/{filename}",
        "media_type": "application/json",
        "visibility": "PUBLIC",
    }


def _identity(operator_id: str, display_name: str) -> dict[str, str]:
    return {
        "operator_id": operator_id,
        "display_name": display_name,
        "identity_assurance": "SELF_ASSERTED_LOCAL",
        "identity_warning": "IDENTITY_RECORD_IS_NOT_PROOF_OF_A_DISTINCT_HUMAN",
    }


def _reviewer(operator_id: str, display_name: str) -> dict[str, Any]:
    return {
        **_identity(operator_id, display_name),
        "conflict_declaration": "NO_MATERIAL_CONFLICT_DECLARED",
        "conflict_evidence_sha256": [],
    }


def _draft(
    *,
    target_digest: str,
    reviewer_ids: tuple[str, str],
    conclusions: tuple[str, str],
) -> dict[str, Any]:
    reviewers = [_reviewer(reviewer_ids[0], "Synthetic Reviewer A"), _reviewer(reviewer_ids[1], "Synthetic Reviewer B")]
    return {
        "appeal_id": "appeal:synthetic-split-panel",
        "case": {
            "case_id": "case:synthetic-disputed-calibration",
            "case_kind": "SCIENTIFIC_DISPUTE",
            "target": _reference(
                "shift-report:synthetic-disputed-calibration",
                target_digest,
                "disputed-calibration.json",
            ),
            "requester": _identity("human:synthetic-requester", "Synthetic Requester"),
            "materially_involved_identity_ids": [
                "human:synthetic-author",
                "human:synthetic-validator-a",
                "human:synthetic-validator-b",
            ],
            "public_summary": "Known-answer fixture requesting a procedural review of a split rerun.",
            "evidence_references": [],
        },
        "panel": {
            "selection_method": "CONFLICT_EXCLUSION_CHECK_V1",
            "minimum_reviewer_count": 2,
            "reviewer_identity_warning": "IDENTITY_RECORD_IS_NOT_PROOF_OF_A_DISTINCT_HUMAN",
            "reviewers": reviewers,
        },
        "findings": [
            {
                "reviewer_id": reviewer_ids[0],
                "conclusion": conclusions[0],
                "evidence_sha256": _digest("synthetic appeal reviewer a commitment"),
                "public_summary": "Synthetic reviewer A committed a bounded procedural finding.",
            },
            {
                "reviewer_id": reviewer_ids[1],
                "conclusion": conclusions[1],
                "evidence_sha256": _digest("synthetic appeal reviewer b commitment"),
                "public_summary": "Synthetic reviewer B committed a bounded procedural finding.",
            },
        ],
        "outcome": "RETURN_FOR_DIAGNOSIS",
        "follow_up": "FRESH_DIAGNOSTIC_RUN_REQUIRED",
        "decision_public_summary": "The split fixture returns to diagnosis; it cannot be resolved by a vote.",
    }


def run_synthetic_drill(output: Path) -> dict[str, Any]:
    output = output.resolve()
    if output.exists():
        raise ContractError(f"synthetic appeal output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    try:
        public = staging / "public"
        public.mkdir()
        disputed = public / "disputed-calibration.json"
        write_json(
            disputed,
            {
                "fixture": "SYNTHETIC_ONLY",
                "statement": "Two blind synthetic reruns produced incompatible deterministic outputs.",
                "required_route": "DIAGNOSIS_NOT_MAJORITY",
            },
        )
        ledger = AppealLedger(public / "appeals.jsonl")
        target_digest = sha256_file(disputed)

        conflicted_reviewer_rejected = False
        conflict = _draft(
            target_digest=target_digest,
            reviewer_ids=("human:synthetic-author", "human:synthetic-reviewer-b"),
            conclusions=("UPHOLD_APPEAL", "DENY_APPEAL"),
        )
        try:
            ledger.append(conflict, recorded_at="2026-08-07T09:00:00Z")
        except ContractError:
            conflicted_reviewer_rejected = True
        if not conflicted_reviewer_rejected:
            raise ContractError("synthetic conflict fixture unexpectedly entered the appeal ledger")

        record = ledger.append(
            _draft(
                target_digest=target_digest,
                reviewer_ids=("human:synthetic-reviewer-a", "human:synthetic-reviewer-b"),
                conclusions=("UPHOLD_APPEAL", "DENY_APPEAL"),
            ),
            recorded_at="2026-08-07T09:05:00Z",
        )
        index_path = public / "appeal-index.json"
        ledger.export_public_index(index_path)
        verified = ledger.verify()
        report_unsigned = {
            "schema_version": 1,
            "drill_id": "APPEAL-SYNTHETIC-001",
            "scope": "SYNTHETIC_COMMISSIONING_ONLY",
            "records": verified["records"],
            "conflicted_reviewer_rejected": conflicted_reviewer_rejected,
            "split_routed_to_diagnosis": record["outcome"] == "RETURN_FOR_DIAGNOSIS",
            "ledger_sha256": verified["ledger_sha256"],
            "head_record_sha256": verified["head_record_sha256"],
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
    expected = {"appeal-index.json", "appeals.jsonl", "disputed-calibration.json", "report.json"}
    if not public.is_dir() or {path.name for path in public.iterdir()} != expected:
        raise ContractError("synthetic appeal drill has missing or unexpected public files")
    report = load_json_strict(public / "report.json")
    if set(report) != REPORT_KEYS:
        raise ContractError("synthetic appeal report has an invalid closed shape")
    unsigned = {key: value for key, value in report.items() if key != "report_sha256"}
    if sha256_bytes(canonical_json_bytes(unsigned)) != report["report_sha256"]:
        raise ContractError("synthetic appeal report self-hash does not match")
    if report["scope"] != "SYNTHETIC_COMMISSIONING_ONLY":
        raise ContractError("synthetic appeal drill escaped its commissioning scope")
    if report["scientific_standing"] != "NONE_SYNTHETIC_COMMISSIONING_ONLY":
        raise ContractError("synthetic appeal drill claims scientific standing")
    if report["eligible_for_promotion"] is not False:
        raise ContractError("synthetic appeal drill claims promotion eligibility")
    if report["conflicted_reviewer_rejected"] is not True:
        raise ContractError("synthetic appeal drill did not reject a conflicted reviewer")
    if report["split_routed_to_diagnosis"] is not True:
        raise ContractError("synthetic appeal drill did not route a split to diagnosis")

    ledger = AppealLedger(public / "appeals.jsonl")
    records = ledger.read()
    verified = ledger.verify()
    if len(records) != 1 or records[0]["outcome"] != "RETURN_FOR_DIAGNOSIS":
        raise ContractError("synthetic appeal drill has the wrong procedural outcome")
    record = records[0]
    reviewer_ids = {row["operator_id"] for row in record["panel"]["reviewers"]}
    involved = set(record["case"]["materially_involved_identity_ids"])
    if reviewer_ids & (involved | {record["case"]["requester"]["operator_id"]}):
        raise ContractError("synthetic appeal panel is not conflict excluded")
    if verified["ledger_sha256"] != report["ledger_sha256"]:
        raise ContractError("synthetic appeal ledger hash does not match the report")
    if verified["head_record_sha256"] != report["head_record_sha256"]:
        raise ContractError("synthetic appeal head does not match the report")

    expected_index = ledger.history(limit=500)
    expected_index["ledger"].pop("ledger", None)
    if load_json_strict(public / "appeal-index.json") != expected_index:
        raise ContractError("synthetic public appeal index does not match the ledger")
    return {
        "valid": True,
        "records": 1,
        "outcome": "RETURN_FOR_DIAGNOSIS",
        "head_record_sha256": verified["head_record_sha256"],
        "report_sha256": report["report_sha256"],
        "scientific_standing": report["scientific_standing"],
        "eligible_for_promotion": False,
    }
