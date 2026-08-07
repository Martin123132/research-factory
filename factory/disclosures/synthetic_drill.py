from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from control_plane.common import ContractError, canonical_json_bytes, sha256_bytes, write_json

from .ledger import SupportDisclosureLedger, load_json_strict


REPORT_KEYS = {"schema_version", "drill_id", "scope", "records", "ended_disclosure", "ledger_sha256", "head_record_sha256", "scientific_standing", "eligible_for_promotion", "report_sha256"}


def _draft(action: str, event_id: str, *, description: str) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "disclosure_id": "support:synthetic-compute-credit",
        "action": action,
        "scope": {"scope_type": "FACTORY_PROJECT", "scope_id": "research-factory"},
        "declarant": {"operator_id": "human:synthetic-discloser", "display_name": "Synthetic Discloser", "identity_assurance": "SELF_ASSERTED_LOCAL", "identity_warning": "IDENTITY_RECORD_IS_NOT_PROOF_OF_AUTHORITY"},
        "disclosure": {"supporter_name": "Synthetic Compute Donor", "supporter_kind": "NONPROFIT", "support_kind": "COMPUTE_CREDIT", "relationship": "Known-answer synthetic commissioning support only.", "materiality": "MATERIAL", "value_visibility": "NOT_QUANTIFIABLE", "public_description": description, "received_or_expected": "EXPECTED" if action == "DECLARE" else "ONGOING"},
        "public_summary": description,
    }


def run_synthetic_drill(output: Path) -> dict[str, Any]:
    output = output.resolve()
    if output.exists():
        raise ContractError(f"synthetic support-disclosure output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    try:
        public = staging / "public"
        public.mkdir()
        ledger = SupportDisclosureLedger(public / "support-disclosures.jsonl")
        ledger.append(_draft("DECLARE", "support-event:synthetic-declare", description="Synthetic compute credit declared for a local construction drill."), recorded_at="2026-08-07T11:00:00Z")
        ended = ledger.append(_draft("END", "support-event:synthetic-end", description="Synthetic compute credit ended after the local construction drill."), recorded_at="2026-08-07T12:00:00Z")
        index = public / "support-disclosure-index.json"
        ledger.export_public_index(index)
        verified = ledger.verify()
        unsigned = {"schema_version": 1, "drill_id": "SUPPORT-DISCLOSURE-SYNTHETIC-001", "scope": "SYNTHETIC_COMMISSIONING_ONLY", "records": verified["records"], "ended_disclosure": ended["status_after"] == "ENDED", "ledger_sha256": verified["ledger_sha256"], "head_record_sha256": verified["head_record_sha256"], "scientific_standing": "NONE_SYNTHETIC_COMMISSIONING_ONLY", "eligible_for_promotion": False}
        report = {**unsigned, "report_sha256": sha256_bytes(canonical_json_bytes(unsigned))}
        write_json(public / "report.json", report)
        ledger.lock_path.unlink(missing_ok=True)
        verify_synthetic_drill(staging)
        os.replace(staging, output)
        return report
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def verify_synthetic_drill(output: Path) -> dict[str, Any]:
    public = output.resolve() / "public"
    expected = {"support-disclosures.jsonl", "support-disclosure-index.json", "report.json"}
    if not public.is_dir() or {path.name for path in public.iterdir()} != expected:
        raise ContractError("synthetic support-disclosure drill has missing or unexpected public files")
    report = load_json_strict(public / "report.json")
    if set(report) != REPORT_KEYS:
        raise ContractError("synthetic support-disclosure report has an invalid closed shape")
    unsigned = {key: value for key, value in report.items() if key != "report_sha256"}
    if sha256_bytes(canonical_json_bytes(unsigned)) != report["report_sha256"]:
        raise ContractError("synthetic support-disclosure report self-hash does not match")
    if report["scope"] != "SYNTHETIC_COMMISSIONING_ONLY" or report["scientific_standing"] != "NONE_SYNTHETIC_COMMISSIONING_ONLY" or report["eligible_for_promotion"] is not False:
        raise ContractError("synthetic support-disclosure drill escaped its construction boundary")
    ledger = SupportDisclosureLedger(public / "support-disclosures.jsonl")
    records = ledger.read()
    verified = ledger.verify()
    if len(records) != 2 or [record["action"] for record in records] != ["DECLARE", "END"] or records[-1]["status_after"] != "ENDED":
        raise ContractError("synthetic support-disclosure lifecycle is invalid")
    if records[1]["previous_disclosure_event_sha256"] != records[0]["record_sha256"]:
        raise ContractError("synthetic support-disclosure chain is broken")
    if verified["ledger_sha256"] != report["ledger_sha256"] or verified["head_record_sha256"] != report["head_record_sha256"]:
        raise ContractError("synthetic support-disclosure hashes do not match the report")
    expected_index = ledger.history(limit=500)
    expected_index["ledger"].pop("ledger", None)
    if load_json_strict(public / "support-disclosure-index.json") != expected_index:
        raise ContractError("synthetic public support-disclosure index does not match the ledger")
    return {"valid": True, "records": 2, "final_status": "ENDED", "report_sha256": report["report_sha256"], "scientific_standing": report["scientific_standing"], "eligible_for_promotion": False}
