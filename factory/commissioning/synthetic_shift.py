from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from control_plane import ContractError, TransitionError
from control_plane.common import (
    canonical_json_bytes,
    load_json,
    sha256_bytes,
    sha256_file,
    utc_text,
    write_json,
)
from control_plane.evidence import EvidenceStore
from control_plane.ledger import EventLedger
from control_plane.audit import audit_public_ledger_blindness
from control_plane.workflow import ControlPlane


FACTORY_ROOT = Path(__file__).resolve().parents[1]
ROUND_PATH = FACTORY_ROOT / "rounds" / "WB001-PILOT-001" / "round.json"
POLICY_PATH = (
    FACTORY_ROOT
    / "control_plane"
    / "examples"
    / "wb001-synthetic-envelope-policy.json"
)
REPORT_SCHEMA_PATH = (
    FACTORY_ROOT
    / "commissioning"
    / "schemas"
    / "synthetic-shift-report-v1.schema.json"
)
AUDIT_SCHEMA_PATH = (
    FACTORY_ROOT
    / "control_plane"
    / "schemas"
    / "blind-audit-v1.schema.json"
)
PUBLIC_MANIFEST_PATH = (
    FACTORY_ROOT
    / "workbenches"
    / "wb001_lossless_compression"
    / "data"
    / "public_manifest.json"
)
CONTROL_LOCK_PATH = FACTORY_ROOT / "control_plane" / "software.lock.json"

ROUND_ID = "WB001-PILOT-001"
SHIFT_ID = "shift:wb001-synthetic-dispute-001"
ATTEMPT_ID = "attempt:wb001-synthetic-dispute-001"
ADMIN_ID = "fixture:administrator"
AUTHOR_ID = "fixture:author"
VALIDATOR_IDS = (
    "fixture:validator-a",
    "fixture:validator-b",
    "fixture:validator-c",
)


class CommissioningClock:
    """Fixed, timezone-aware clock for a normalized synthetic shift."""

    def __init__(self) -> None:
        self.value = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value


def _validate_document(document: dict[str, Any], schema_path: Path, label: str) -> None:
    try:
        Draft202012Validator(load_json(schema_path)).validate(document)
    except ValidationError as exc:
        location = ".".join(str(part) for part in exc.absolute_path) or "document"
        raise ContractError(f"{label} schema failed at {location}: {exc.message}") from exc


def _logical_contract(round_document: dict[str, Any], name: str) -> str:
    return next(
        row["logical_commitment_sha256"]
        for row in round_document["frozen_contracts"]
        if row["name"] == name
    )


def _entry_document(
    *,
    operator_id: str,
    round_document: dict[str, Any],
) -> dict[str, Any]:
    unsigned = {
        "schema_version": 1,
        "evidence_type": "worker_entry_gate",
        "generated_at": "2026-08-06T12:00:00Z",
        "started_at": "2026-08-06T11:59:00Z",
        "round_id": ROUND_ID,
        "round_sha256": round_document["round_sha256"],
        "operator_id": operator_id,
        "checks": {
            "frozen_contracts_match": True,
            "schemas_validate": True,
            "reference_round_trip_exact": True,
            "reference_output_deterministic": True,
            "rules_acknowledged": True,
        },
        "reference_result": {"result_sha256": "c" * 64},
        "environment": {
            "profile": "synthetic-commissioning",
            "scientific_standing": "NONE",
        },
        "commands": [
            {"command": ["validate-frozen-contracts"]},
            {"command": ["run-known-answer-fixture"]},
        ],
    }
    return {
        **unsigned,
        "entry_evidence_sha256": sha256_bytes(canonical_json_bytes(unsigned)),
    }


def _candidate_fixture(private_root: Path) -> tuple[Path, dict[str, Any]]:
    candidate_root = private_root / "author" / "candidate"
    candidate_root.mkdir(parents=True, exist_ok=True)
    source_path = candidate_root / "candidate.py"
    source_path.write_text(
        "\"\"\"Metric-free synthetic candidate used only to commission workflow gates.\"\"\"\n"
        "\n"
        "def round_trip(payload: bytes) -> bytes:\n"
        "    return bytes(payload)\n",
        encoding="utf-8",
    )
    submission_path = candidate_root / "submission.json"
    submission = {
        "schema_version": 1,
        "submission_id": "wb001-synthetic-dispute-candidate",
        "workbench": {"id": "WB-001", "version": "0.2.0"},
        "candidate": {
            "name": "synthetic dispute candidate",
            "version": "1.0.0",
            "protocol": "wb001-batch-v1",
            "command": ["{python}", "candidate.py"],
            "source_files": ["candidate.py"],
            "deterministic": True,
        },
        "method": {
            "summary": "Known-answer fixture for a zero-credit workflow drill.",
            "license": "CC0-1.0",
        },
    }
    write_json(submission_path, submission)
    artifact_core = {
        "submission": submission,
        "submission_sha256": sha256_file(submission_path),
        "source_files": [
            {
                "path": "candidate.py",
                "bytes": source_path.stat().st_size,
                "sha256": sha256_file(source_path),
            }
        ],
    }
    artifact_manifest = {
        **artifact_core,
        "artifact_sha256": sha256_bytes(canonical_json_bytes(artifact_core)),
    }
    return submission_path, artifact_manifest


def _result_document(
    *,
    operator_id: str,
    artifact_manifest: dict[str, Any],
    round_document: dict[str, Any],
    public_manifest: dict[str, Any],
    variant: int,
) -> dict[str, Any]:
    file_rows = []
    for index, original in enumerate(public_manifest["files"]):
        compressed_bytes = max(1, original["bytes"] // 20) + index
        output_fingerprint = f"{original['path']}:synthetic-variant:{variant}".encode("utf-8")
        file_rows.append(
            {
                "path": original["path"],
                "original_bytes": original["bytes"],
                "original_sha256": original["sha256"],
                "compressed_bytes": compressed_bytes,
                "compressed_sha256": sha256_bytes(output_fingerprint),
                "deterministic": True,
                "round_trip_pass": True,
            }
        )
    validator = operator_id in VALIDATOR_IDS
    unsigned = {
        "schema_version": 2,
        "result_type": "wb001_evaluation",
        "runner_version": "0.2.0",
        "workbench": {"id": "WB-001", "version": "0.2.0"},
        "operator_id": operator_id,
        "candidate_artifact_sha256": artifact_manifest["artifact_sha256"],
        "artifact_manifest": artifact_manifest,
        "execution_boundary": {
            "mode": "docker-isolated-process" if validator else "trusted-local-process",
            "security_boundary": validator,
            "promotion_grade": False,
            "timing_grade": "advisory",
        },
        "runtime_fingerprint_sha256": sha256_bytes(
            f"synthetic-runtime:{operator_id}".encode("utf-8")
        ),
        "corpus": {
            "profile": public_manifest["profile"],
            "manifest_sha256": sha256_file(PUBLIC_MANIFEST_PATH),
            "corpus_sha256": _logical_contract(round_document, "public_corpus_manifest"),
            "files": len(public_manifest["files"]),
        },
        "hard_gate_pass": True,
        "failures": [],
        "files": file_rows,
        "aggregate": {
            "files": len(file_rows),
            "total_input_bytes": sum(row["original_bytes"] for row in file_rows),
            "total_compressed_bytes": sum(row["compressed_bytes"] for row in file_rows),
        },
    }
    return {**unsigned, "result_sha256": sha256_bytes(canonical_json_bytes(unsigned))}


def _comparison_document(
    *,
    result: dict[str, Any],
    round_document: dict[str, Any],
) -> dict[str, Any]:
    unsigned = {
        "schema_version": 2,
        "decision_type": "wb001_frontier_comparison",
        "workbench": result["workbench"],
        "baseline_pack_sha256": _logical_contract(round_document, "reference_frontier_pack"),
        "candidate_result_sha256": result["result_sha256"],
        "candidate_artifact_sha256": result["candidate_artifact_sha256"],
        "corpus_sha256": result["corpus"]["corpus_sha256"],
        "status": "PUBLIC_SIZE_CANDIDATE",
        "eligible_for_promotion": False,
        "candidate_metrics": {
            "total_compressed_bytes": result["aggregate"]["total_compressed_bytes"]
        },
    }
    return {
        **unsigned,
        "decision_sha256": sha256_bytes(canonical_json_bytes(unsigned)),
    }


def _expect_transition_rejection(label: str, action: Callable[[], Any]) -> bool:
    try:
        action()
    except TransitionError:
        return True
    raise ContractError(f"commissioning invariant failed: {label} was accepted")


def _commit_rerun(
    *,
    plane: ControlPlane,
    private_root: Path,
    operator_id: str,
    attempt_id: str,
    artifact_manifest: dict[str, Any],
    round_document: dict[str, Any],
    public_manifest: dict[str, Any],
    variant: int,
) -> None:
    capability = sha256_bytes(
        f"{SHIFT_ID}\0{operator_id}\0rerun-capability".encode("utf-8")
    )
    lease = plane.claim_rerun(
        operator_id=operator_id,
        attempt_id=attempt_id,
        capability=capability,
        conflict_declaration=True,
        request_id=f"request:{operator_id.split(':')[-1]}-claim-rerun",
    )
    result = _result_document(
        operator_id=operator_id,
        artifact_manifest=artifact_manifest,
        round_document=round_document,
        public_manifest=public_manifest,
        variant=variant,
    )
    result_path = private_root / "reruns" / f"{operator_id.split(':')[-1]}.json"
    write_json(result_path, result)
    plane.submit_rerun(
        operator_id=operator_id,
        rerun_claim_id=lease["event"]["payload"]["rerun_claim_id"],
        capability=capability,
        evidence_path=result_path,
        request_id=f"request:{operator_id.split(':')[-1]}-submit-rerun",
    )


def _run_shift(staging_root: Path) -> dict[str, Any]:
    public_root = staging_root / "public"
    private_root = staging_root / "private"
    public_root.mkdir(parents=True)
    private_root.mkdir(parents=True)
    clock = CommissioningClock()
    round_document = load_json(ROUND_PATH)
    public_manifest = load_json(PUBLIC_MANIFEST_PATH)
    control_lock = load_json(CONTROL_LOCK_PATH)
    plane = ControlPlane(
        public_root / "events.jsonl",
        factory_root=FACTORY_ROOT,
        evidence_root=private_root / "evidence",
        artifact_root=public_root / "artifacts",
        private_root=private_root / "sealed-reruns",
        clock=clock,
    )

    plane.initialize(
        factory_id="factory:synthetic-commissioning",
        admin_id=ADMIN_ID,
        provider="commissioning-fixture",
        subject="administrator-record",
        display_name="Synthetic commissioning administrator",
        request_id="request:initialize-synthetic-shift",
    )
    plane.open_round(
        actor_id=ADMIN_ID,
        round_path=ROUND_PATH,
        request_id="request:open-frozen-pilot-round",
    )

    identities = (
        (AUTHOR_ID, "author-record", "Synthetic author"),
        (VALIDATOR_IDS[0], "validator-a-record", "Synthetic validator A"),
        (VALIDATOR_IDS[1], "validator-b-record", "Synthetic validator B"),
        (VALIDATOR_IDS[2], "validator-c-record", "Synthetic diagnostic validator"),
    )
    for operator_id, subject, display_name in identities:
        plane.check_in(
            operator_id=operator_id,
            provider="commissioning-fixture",
            subject=subject,
            display_name=display_name,
            request_id=f"request:{operator_id.split(':')[-1]}-check-in",
        )
        entry_path = private_root / "entry" / f"{operator_id.split(':')[-1]}.json"
        write_json(
            entry_path,
            _entry_document(operator_id=operator_id, round_document=round_document),
        )
        plane.complete_entry_gate(
            operator_id=operator_id,
            round_id=ROUND_ID,
            evidence_path=entry_path,
            request_id=f"request:{operator_id.split(':')[-1]}-entry-gate",
        )

    submission_path, artifact_manifest = _candidate_fixture(private_root)
    claim = plane.claim_work(
        operator_id=AUTHOR_ID,
        round_id=ROUND_ID,
        work_unit_id="wu:selector-policy",
        request_id="request:author-claim-work",
    )
    work_claim_id = claim["payload"]["work_claim_id"]
    release_capability = sha256_bytes(
        f"{SHIFT_ID}\0{work_claim_id}\0human-release".encode("utf-8")
    )
    envelope_id = f"envelope:{sha256_bytes(SHIFT_ID.encode('utf-8'))[:32]}"
    plane.issue_work_envelope(
        actor_id=ADMIN_ID,
        work_claim_id=work_claim_id,
        policy_path=POLICY_PATH,
        release_capability=release_capability,
        envelope_id=envelope_id,
        request_id="request:issue-synthetic-envelope",
    )
    plane.start_attempt(
        operator_id=AUTHOR_ID,
        work_claim_id=work_claim_id,
        envelope_id=envelope_id,
        release_capability=release_capability,
        attempt_id=ATTEMPT_ID,
        request_id="request:start-synthetic-attempt",
    )
    execution = plane.execute_attempt(
        operator_id=AUTHOR_ID,
        attempt_id=ATTEMPT_ID,
        request_id="request:execute-synthetic-envelope",
    )
    if execution["within_envelope"] is not True or execution["promotion_eligible"] is not False:
        raise ContractError("synthetic work-envelope execution did not remain in commissioning scope")

    author_result = _result_document(
        operator_id=AUTHOR_ID,
        artifact_manifest=artifact_manifest,
        round_document=round_document,
        public_manifest=public_manifest,
        variant=0,
    )
    author_result_path = private_root / "author" / "result.json"
    comparison_path = private_root / "author" / "comparison.json"
    write_json(author_result_path, author_result)
    write_json(
        comparison_path,
        _comparison_document(result=author_result, round_document=round_document),
    )
    plane.submit_result(
        operator_id=AUTHOR_ID,
        attempt_id=ATTEMPT_ID,
        evidence_path=author_result_path,
        comparison_path=comparison_path,
        candidate_submission_path=submission_path,
        candidate_artifact_sha256=artifact_manifest["artifact_sha256"],
        result_kind="CANDIDATE",
        public_summary="Known-answer candidate sealed for a zero-credit blind workflow drill.",
        request_id="request:submit-synthetic-candidate",
    )

    self_rerun_rejected = _expect_transition_rejection(
        "author self-rerun",
        lambda: plane.claim_rerun(
            operator_id=AUTHOR_ID,
            attempt_id=ATTEMPT_ID,
            capability="author-must-not-rerun-this-candidate-0001",
            conflict_declaration=True,
        ),
    )
    blind_annotation_rejected = _expect_transition_rejection(
        "plaintext annotation while blind",
        lambda: plane.annotate_attempt(
            actor_id=ADMIN_ID,
            attempt_id=ATTEMPT_ID,
            note="This note must not enter the ledger while conclusions are blind.",
        ),
    )

    _commit_rerun(
        plane=plane,
        private_root=private_root,
        operator_id=VALIDATOR_IDS[0],
        attempt_id=ATTEMPT_ID,
        artifact_manifest=artifact_manifest,
        round_document=round_document,
        public_manifest=public_manifest,
        variant=0,
    )
    _commit_rerun(
        plane=plane,
        private_root=private_root,
        operator_id=VALIDATOR_IDS[1],
        attempt_id=ATTEMPT_ID,
        artifact_manifest=artifact_manifest,
        round_document=round_document,
        public_manifest=public_manifest,
        variant=1,
    )
    first_gate = plane.evaluate_reruns(
        actor_id=ADMIN_ID,
        attempt_id=ATTEMPT_ID,
        request_id="request:evaluate-initial-reruns",
    )
    if first_gate["payload"]["status"] != "TIEBREAK_DIAGNOSTIC_REQUIRED":
        raise ContractError("synthetic split did not open the diagnostic route")
    early_holdout_rejected = _expect_transition_rejection(
        "holdout after split",
        lambda: plane.record_holdout_job(
            actor_id=ADMIN_ID,
            attempt_id=ATTEMPT_ID,
            token_path=private_root / "must-not-be-read.json",
        ),
    )

    _commit_rerun(
        plane=plane,
        private_root=private_root,
        operator_id=VALIDATOR_IDS[2],
        attempt_id=ATTEMPT_ID,
        artifact_manifest=artifact_manifest,
        round_document=round_document,
        public_manifest=public_manifest,
        variant=0,
    )
    second_gate = plane.evaluate_reruns(
        actor_id=ADMIN_ID,
        attempt_id=ATTEMPT_ID,
        request_id="request:evaluate-diagnostic-rerun",
    )
    if second_gate["payload"]["status"] != "DISPUTED_REVIEW_REQUIRED":
        raise ContractError("a diagnostic majority incorrectly erased the synthetic contradiction")
    majority_holdout_rejected = _expect_transition_rejection(
        "holdout after diagnostic majority",
        lambda: plane.record_holdout_job(
            actor_id=ADMIN_ID,
            attempt_id=ATTEMPT_ID,
            token_path=private_root / "must-not-be-read.json",
        ),
    )

    plane.escalate_dispute(
        actor_id=ADMIN_ID,
        attempt_id=ATTEMPT_ID,
        reason="ENVIRONMENT_MISMATCH",
        request_id="request:escalate-synthetic-dispute",
    )
    diagnosis = {
        "schema_version": 1,
        "diagnostic_type": "SYNTHETIC_COMMISSIONING_DIVERGENCE",
        "scientific_standing": "NONE",
        "first_divergence": "A deliberately injected output-fingerprint variant.",
        "interpretation": "The evidence is internally valid but contradictory by construction.",
        "required_action": "Retain every commitment, block promotion and open human review.",
    }
    diagnosis_path = private_root / "diagnosis.json"
    write_json(diagnosis_path, diagnosis)
    plane.annotate_attempt(
        actor_id=ADMIN_ID,
        attempt_id=ATTEMPT_ID,
        note=(
            "Synthetic diagnosis completed after the blind gate: retain all three reruns; "
            "the deliberate divergence cannot be removed by majority vote."
        ),
        evidence_path=diagnosis_path,
        request_id="request:annotate-synthetic-diagnosis",
    )

    state = plane.state()
    attempt = state["attempts"][ATTEMPT_ID]
    package_sha256 = attempt["result"]["candidate_artifact_package_sha256"]
    plane.artifacts.export(package_sha256, public_root / "exported-candidate")
    audit = plane.audit_blindness()
    _validate_document(audit, AUDIT_SCHEMA_PATH, "blind audit")
    if audit["valid"] is not True:
        raise ContractError(f"public-ledger blindness audit failed: {audit['violations']}")
    write_json(public_root / "blind-audit.json", audit)

    ledger_summary = plane.ledger.verify()
    checkpoint_unsigned = {
        "schema_version": 1,
        "checkpoint_type": "research_factory_ledger_head",
        "label": "synthetic-dispute-shift-final",
        "generated_at": utc_text(clock()),
        "factory_id": "factory:synthetic-commissioning",
        "ledger_name": "public/events.jsonl",
        "events": ledger_summary["events"],
        "head_event_sha256": ledger_summary["head_event_sha256"],
    }
    checkpoint = {
        **checkpoint_unsigned,
        "checkpoint_sha256": sha256_bytes(canonical_json_bytes(checkpoint_unsigned)),
    }
    write_json(public_root / "checkpoint.json", checkpoint)

    snapshot = plane.snapshot(round_id=ROUND_ID)
    attempt_snapshot = next(row for row in snapshot["attempts"] if row["attempt_id"] == ATTEMPT_ID)
    if attempt_snapshot["status"] != "DISPUTED_REVIEW_REQUIRED":
        raise ContractError("synthetic shift did not finish in the required disputed state")
    if ledger_summary["events"] != 25:
        raise ContractError(
            f"synthetic shift emitted {ledger_summary['events']} events; expected the frozen 25-event route"
        )

    report_unsigned = {
        "schema_version": 1,
        "report_type": "SYNTHETIC_FACTORY_SHIFT",
        "shift_id": SHIFT_ID,
        "scientific_standing": "NONE_SYNTHETIC_COMMISSIONING_ONLY",
        "round_id": ROUND_ID,
        "attempt_id": ATTEMPT_ID,
        "commitments": {
            "round_sha256": round_document["round_sha256"],
            "control_plane_software_sha256": control_lock["software_sha256"],
            "commissioning_harness_sha256": sha256_file(Path(__file__)),
            "report_schema_sha256": sha256_file(REPORT_SCHEMA_PATH),
            "candidate_artifact_package_sha256": package_sha256,
        },
        "identities": {
            "registered_operator_records": snapshot["operators"],
            "rerunner_identity_records": len(attempt["rerun_claim_ids"]),
            "identity_records_distinct": audit["checks"]["distinct_identity_records"],
            "identity_assurance": "self-asserted-local",
            "distinct_humans_proven": False,
        },
        "execution": {
            "enforcement_profile": "LOCAL_MONITORED_V1",
            "within_envelope": True,
            "promotion_eligible": False,
        },
        "gate_sequence": [
            "TIEBREAK_DIAGNOSTIC_REQUIRED",
            "DISPUTED_REVIEW_REQUIRED",
        ],
        "final_status": "DISPUTED_REVIEW_REQUIRED",
        "diagnosis": {
            "classification": "DELIBERATE_SYNTHETIC_VARIANT",
            "first_divergence": "OUTPUT_FINGERPRINT",
            "action": "RETAIN_CONTRADICTION_AND_BLOCK_PROMOTION",
        },
        "checks": {
            "exact_work_envelope_executed": True,
            "author_self_rerun_rejected": self_rerun_rejected,
            "plaintext_annotation_while_blind_rejected": blind_annotation_rejected,
            "two_initial_reruns_committed_blind": True,
            "split_opened_diagnostic_route": True,
            "diagnostic_majority_did_not_promote": True,
            "holdout_blocked_without_unanimous_confirmation": (
                early_holdout_rejected and majority_holdout_rejected
            ),
            "dispute_escalated": attempt["dispute"] is not None,
            "diagnosis_appended_after_blind_gate": attempt_snapshot["annotations"] == 1,
            "public_ledger_audit_passed": audit["valid"],
            "no_scientific_credit": True,
        },
        "audit": audit,
        "artifacts": {
            "public_ledger": "public/events.jsonl",
            "blind_audit": "public/blind-audit.json",
            "checkpoint": "public/checkpoint.json",
            "metric_free_candidate": "public/exported-candidate",
            "sealed_working_material": "private/",
        },
    }
    report = {
        **report_unsigned,
        "report_sha256": sha256_bytes(canonical_json_bytes(report_unsigned)),
    }
    _validate_document(report, REPORT_SCHEMA_PATH, "synthetic shift report")
    if not all(report["checks"].values()):
        raise ContractError("one or more normalized commissioning checks did not pass")
    write_json(public_root / "report.json", report)
    plane.ledger.lock_path.unlink(missing_ok=True)
    return report


def run_synthetic_dispute_shift(output_root: Path) -> dict[str, Any]:
    """Run the complete zero-credit dispute drill into a new output directory."""

    destination = output_root.resolve()
    if destination.exists():
        raise ContractError(f"commissioning output already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent)
    )
    try:
        report = _run_shift(staging)
        os.replace(staging, destination)
        verification = verify_synthetic_dispute_shift(destination)
        if verification["report_sha256"] != report["report_sha256"]:
            raise ContractError("post-write commissioning verification returned a different report")
        return report
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def verify_synthetic_dispute_shift(output_root: Path) -> dict[str, Any]:
    """Verify a completed drill using only its public artifacts and current contracts."""

    root = output_root.resolve()
    public_root = root / "public"
    report = load_json(public_root / "report.json")
    _validate_document(report, REPORT_SCHEMA_PATH, "synthetic shift report")
    report_unsigned = {key: value for key, value in report.items() if key != "report_sha256"}
    if report["report_sha256"] != sha256_bytes(canonical_json_bytes(report_unsigned)):
        raise ContractError("synthetic shift report self-hash does not match")

    expected_commitments = {
        "round_sha256": load_json(ROUND_PATH)["round_sha256"],
        "control_plane_software_sha256": load_json(CONTROL_LOCK_PATH)["software_sha256"],
        "commissioning_harness_sha256": sha256_file(Path(__file__)),
        "report_schema_sha256": sha256_file(REPORT_SCHEMA_PATH),
    }
    for field, expected in expected_commitments.items():
        if report["commitments"].get(field) != expected:
            raise ContractError(f"synthetic shift report commitment drifted: {field}")

    ledger = EventLedger(public_root / "events.jsonl")
    events = ledger.read()
    ledger_summary = ledger.verify()
    recomputed_audit = audit_public_ledger_blindness(events)
    stored_audit = load_json(public_root / "blind-audit.json")
    _validate_document(stored_audit, AUDIT_SCHEMA_PATH, "blind audit")
    if stored_audit != recomputed_audit or report["audit"] != recomputed_audit:
        raise ContractError("stored blindness audit does not match the public ledger")
    if recomputed_audit["valid"] is not True:
        raise ContractError("public ledger failed its blindness audit")

    checkpoint = load_json(public_root / "checkpoint.json")
    checkpoint_schema = load_json(
        FACTORY_ROOT / "control_plane" / "schemas" / "checkpoint.schema.json"
    )
    try:
        Draft202012Validator(checkpoint_schema).validate(checkpoint)
    except ValidationError as exc:
        location = ".".join(str(part) for part in exc.absolute_path) or "document"
        raise ContractError(
            f"synthetic shift checkpoint schema failed at {location}: {exc.message}"
        ) from exc
    checkpoint_unsigned = {
        key: value for key, value in checkpoint.items() if key != "checkpoint_sha256"
    }
    if checkpoint["checkpoint_sha256"] != sha256_bytes(
        canonical_json_bytes(checkpoint_unsigned)
    ):
        raise ContractError("synthetic shift checkpoint self-hash does not match")
    if (
        checkpoint["events"] != ledger_summary["events"]
        or checkpoint["head_event_sha256"] != ledger_summary["head_event_sha256"]
    ):
        raise ContractError("synthetic shift checkpoint does not bind the public ledger head")

    package_sha256 = report["commitments"]["candidate_artifact_package_sha256"]
    artifact_store = EvidenceStore(public_root / "artifacts")
    reingested = artifact_store.ingest(public_root / "exported-candidate")
    if reingested["package_sha256"] != package_sha256:
        raise ContractError("metric-free candidate export does not match its public package")

    plane = ControlPlane(
        public_root / "events.jsonl",
        factory_root=FACTORY_ROOT,
        evidence_root=root / "private" / "evidence",
        artifact_root=public_root / "artifacts",
        private_root=root / "private" / "sealed-reruns",
        clock=CommissioningClock(),
    )
    snapshot = plane.snapshot(round_id=ROUND_ID)
    attempt = next(row for row in snapshot["attempts"] if row["attempt_id"] == ATTEMPT_ID)
    if attempt["status"] != report["final_status"]:
        raise ContractError("materialized attempt state does not match the normalized report")
    state = plane.state()
    attempt_state = state["attempts"][ATTEMPT_ID]
    actual_gates = [row["status"] for row in attempt_state["gate_history"]]
    if actual_gates != report["gate_sequence"]:
        raise ContractError("public ledger gate sequence does not match the normalized report")
    if (
        len(state["operators"]) != report["identities"]["registered_operator_records"]
        or len(attempt_state["rerun_claim_ids"])
        != report["identities"]["rerunner_identity_records"]
    ):
        raise ContractError("public ledger identities do not match the normalized report")
    envelope = state["work_envelopes"][attempt_state["envelope_id"]]
    receipt = attempt_state["execution_receipt"]
    if (
        envelope["enforcement_profile"] != report["execution"]["enforcement_profile"]
        or receipt is None
        or receipt["within_envelope"] != report["execution"]["within_envelope"]
        or receipt["promotion_eligible"] != report["execution"]["promotion_eligible"]
    ):
        raise ContractError("public execution receipt does not match the normalized report")
    if (
        attempt_state["result"]["candidate_artifact_package_sha256"]
        != report["commitments"]["candidate_artifact_package_sha256"]
    ):
        raise ContractError("public candidate-package commitment does not match the attempt")
    return {
        "valid": True,
        "shift_id": report["shift_id"],
        "events": ledger_summary["events"],
        "final_status": attempt["status"],
        "report_sha256": report["report_sha256"],
        "public_ledger_audit": "PASS",
        "scientific_standing": report["scientific_standing"],
    }
