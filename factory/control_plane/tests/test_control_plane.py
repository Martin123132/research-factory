from __future__ import annotations

import base64
import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from control_plane import ContractError, LedgerIntegrityError, TransitionError
from control_plane.common import canonical_json_bytes, sha256_bytes, sha256_file, write_json
from control_plane.envelope import build_receipt
from control_plane.workflow import ControlPlane


FACTORY_ROOT = Path(__file__).resolve().parents[2]
ROUND_PATH = FACTORY_ROOT / "rounds" / "WB001-PILOT-001" / "round.json"
ROUND_DOCUMENT = json.loads(ROUND_PATH.read_text(encoding="utf-8"))
PUBLIC_MANIFEST_PATH = (
    FACTORY_ROOT / "workbenches" / "wb001_lossless_compression" / "data" / "public_manifest.json"
)
PUBLIC_MANIFEST = json.loads(PUBLIC_MANIFEST_PATH.read_text(encoding="utf-8"))
DEMO_SUBMISSION = (
    FACTORY_ROOT / "workbenches" / "wb001_lossless_compression" / "examples" / "zlib_level9" / "submission.json"
)
TEST_EVALUATOR_PUBLIC_KEY = (
    FACTORY_ROOT
    / "control_plane"
    / "tests"
    / "fixtures"
    / "evaluator_test_public_key.json"
)
ENVELOPE_POLICY_PATH = (
    FACTORY_ROOT / "control_plane" / "examples" / "wb001-synthetic-envelope-policy.json"
)


def logical_contract(round_document: dict, name: str) -> str:
    return next(
        row["logical_commitment_sha256"]
        for row in round_document["frozen_contracts"]
        if row["name"] == name
    )


class MutableClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 8, 2, 9, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, **kwargs: int) -> None:
        self.value += timedelta(**kwargs)


class ControlPlaneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.clock = MutableClock()
        self.test_evaluator_private_key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
        test_key_document = json.loads(TEST_EVALUATOR_PUBLIC_KEY.read_text(encoding="utf-8"))
        self.test_evaluator_key_id = test_key_document["key_id"]
        self.round_document = copy.deepcopy(ROUND_DOCUMENT)
        key_contract = next(
            row
            for row in self.round_document["frozen_contracts"]
            if row["name"] == "evaluator_public_key"
        )
        key_contract["path"] = TEST_EVALUATOR_PUBLIC_KEY.relative_to(FACTORY_ROOT).as_posix()
        key_contract["sha256"] = sha256_file(TEST_EVALUATOR_PUBLIC_KEY)
        round_unsigned = {
            key: value for key, value in self.round_document.items() if key != "round_sha256"
        }
        self.round_document["round_sha256"] = sha256_bytes(canonical_json_bytes(round_unsigned))
        self.round_path = self.root / "round.json"
        write_json(self.round_path, self.round_document)
        self.plane = ControlPlane(
            self.root / "events.jsonl",
            factory_root=FACTORY_ROOT,
            evidence_root=self.root / "private" / "evidence",
            private_root=self.root / "private" / "reruns",
            clock=self.clock,
        )
        self.evidence = self.root / "evidence.json"
        self.evidence.write_text('{"measurement":"sealed-test-evidence"}\n', encoding="utf-8")
        self.candidate_root = self.root / "candidate"
        self.candidate_root.mkdir()
        self.candidate_source = self.candidate_root / "candidate.py"
        self.candidate_source.write_text("# deterministic test candidate\n", encoding="utf-8")
        self.candidate_submission = self.candidate_root / "submission.json"
        submission = {
            "schema_version": 1,
            "submission_id": "wb001-control-plane-test-candidate",
            "workbench": {"id": "WB-001", "version": "0.2.0"},
            "candidate": {
                "name": "control-plane fixture",
                "version": "1.0.0",
                "protocol": "wb001-batch-v1",
                "command": ["{python}", "candidate.py"],
                "source_files": ["candidate.py"],
                "deterministic": True,
            },
            "method": {"summary": "Deterministic control-plane fixture.", "license": "test-only"},
        }
        write_json(self.candidate_submission, submission)
        artifact_core = {
            "submission": submission,
            "submission_sha256": sha256_file(self.candidate_submission),
            "source_files": [
                {
                    "path": "candidate.py",
                    "bytes": self.candidate_source.stat().st_size,
                    "sha256": sha256_file(self.candidate_source),
                }
            ],
        }
        self.artifact_manifest = {
            **artifact_core,
            "artifact_sha256": sha256_bytes(canonical_json_bytes(artifact_core)),
        }
        self.artifact_hash = self.artifact_manifest["artifact_sha256"]
        demo_submission = json.loads(DEMO_SUBMISSION.read_text(encoding="utf-8"))
        demo_source_files = [
            {
                "path": relative,
                "bytes": (DEMO_SUBMISSION.parent / relative).stat().st_size,
                "sha256": sha256_file(DEMO_SUBMISSION.parent / relative),
            }
            for relative in demo_submission["candidate"]["source_files"]
        ]
        demo_artifact_core = {
            "submission": demo_submission,
            "submission_sha256": sha256_file(DEMO_SUBMISSION),
            "source_files": demo_source_files,
        }
        self.demo_artifact_manifest = {
            **demo_artifact_core,
            "artifact_sha256": sha256_bytes(canonical_json_bytes(demo_artifact_core)),
        }
        self.plane.initialize(
            factory_id="factory:test",
            admin_id="local:admin",
            provider="local-test",
            subject="admin-subject",
            display_name="Test administrator",
        )
        self.plane.open_round(actor_id="local:admin", round_path=self.round_path)
        for operator_id in ("local:author", "local:validator-a", "local:validator-b", "local:validator-c"):
            self.plane.check_in(
                operator_id=operator_id,
                provider="local-test",
                subject=f"subject-{operator_id}",
                display_name=operator_id,
            )
            entry_unsigned = {
                "schema_version": 1,
                "evidence_type": "worker_entry_gate",
                "generated_at": "2026-08-02T09:00:00Z",
                "started_at": "2026-08-02T08:59:00Z",
                "round_id": "WB001-PILOT-001",
                "round_sha256": self.round_document["round_sha256"],
                "operator_id": operator_id,
                "checks": {
                    "frozen_contracts_match": True,
                    "schemas_validate": True,
                    "reference_round_trip_exact": True,
                    "reference_output_deterministic": True,
                    "rules_acknowledged": True,
                },
                "reference_result": {"result_sha256": "c" * 64},
                "environment": {"test": True},
                "commands": [{"command": ["validate"]}, {"command": ["rerun"]}],
            }
            entry = {
                **entry_unsigned,
                "entry_evidence_sha256": sha256_bytes(canonical_json_bytes(entry_unsigned)),
            }
            entry_path = self.root / f"entry-{operator_id.replace(':', '-')}.json"
            write_json(entry_path, entry)
            self.plane.complete_entry_gate(
                operator_id=operator_id,
                round_id="WB001-PILOT-001",
                evidence_path=entry_path,
            )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def sign_evaluator_document(self, unsigned: dict) -> dict:
        signature = self.test_evaluator_private_key.sign(canonical_json_bytes(unsigned))
        return {**unsigned, "signature_base64": base64.b64encode(signature).decode("ascii")}

    def make_holdout_job_and_attestation(
        self,
        *,
        attempt_id: str,
        gate_event: dict,
        verdict: str = "NO_GAIN",
    ) -> tuple[Path, Path]:
        self.clock.advance(minutes=1)
        issued_at = self.clock.value
        artifact_sha256 = self.plane.state()["attempts"][attempt_id]["result"][
            "candidate_artifact_sha256"
        ]
        token_unsigned = {
            "schema_version": 1,
            "token_type": "wb001_blind_job",
            "token_id": f"token:{attempt_id.split(':')[-1]}",
            "issued_at": issued_at.isoformat().replace("+00:00", "Z"),
            "expires_at": (issued_at + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
            "operator_id": "local:author",
            "round_id": "WB001-PILOT-001",
            "round_sha256": self.round_document["round_sha256"],
            "attempt_id": attempt_id,
            "rerun_gate_event_sha256": gate_event["event_sha256"],
            "workbench": {"id": "WB-001", "version": "0.2.0"},
            "candidate_artifact_sha256": artifact_sha256,
            "holdout_commitment_sha256": logical_contract(
                self.round_document, "sealed_holdout_commitment"
            ),
            "evaluator_key_id": self.test_evaluator_key_id,
            "maximum_uses": 1,
        }
        token = self.sign_evaluator_document(token_unsigned)
        token_path = self.root / "holdout-job-token.json"
        write_json(token_path, token)

        generated_at = issued_at + timedelta(minutes=1)
        attestation_unsigned = {
            "schema_version": 1,
            "attestation_type": "wb001_blind_verdict",
            "run_id": f"run:{attempt_id.split(':')[-1]}",
            "token_id": token["token_id"],
            "generated_at": generated_at.isoformat().replace("+00:00", "Z"),
            "operator_id": "local:author",
            "round_id": "WB001-PILOT-001",
            "round_sha256": self.round_document["round_sha256"],
            "attempt_id": attempt_id,
            "rerun_gate_event_sha256": gate_event["event_sha256"],
            "workbench": {"id": "WB-001", "version": "0.2.0"},
            "candidate_artifact_sha256": artifact_sha256,
            "holdout_commitment_sha256": logical_contract(
                self.round_document, "sealed_holdout_commitment"
            ),
            "verdict": verdict,
            "evaluator_key_id": token["evaluator_key_id"],
            "evaluator_software_sha256": self.round_document["evaluator_software_sha256"],
            "image_lock_sha256": logical_contract(self.round_document, "evaluator_image_lock"),
            "private_evidence_sha256": "e" * 64,
            "details_sealed": True,
        }
        attestation = self.sign_evaluator_document(attestation_unsigned)
        attestation_path = self.root / "holdout-attestation.json"
        write_json(attestation_path, attestation)
        return token_path, attestation_path

    def make_wb_result(
        self,
        operator_id: str,
        *,
        artifact_sha256: str | None = None,
        variant: int = 0,
        hard_gate_pass: bool = True,
    ) -> Path:
        artifact_sha256 = artifact_sha256 or self.artifact_hash
        artifact_manifest = (
            self.demo_artifact_manifest
            if artifact_sha256 == self.demo_artifact_manifest["artifact_sha256"]
            else self.artifact_manifest
        )
        if artifact_manifest["artifact_sha256"] != artifact_sha256:
            raise AssertionError("test has no source fixture for requested artifact")
        file_rows = []
        for index, original in enumerate(PUBLIC_MANIFEST["files"]):
            compressed_bytes = max(1, original["bytes"] // 20) + index
            compressed_fingerprint = f"{original['path']}:variant:{variant}".encode("utf-8")
            file_rows.append(
                {
                    "path": original["path"],
                    "original_bytes": original["bytes"],
                    "original_sha256": original["sha256"],
                    "compressed_bytes": compressed_bytes,
                    "compressed_sha256": sha256_bytes(compressed_fingerprint),
                    "deterministic": hard_gate_pass,
                    "round_trip_pass": hard_gate_pass,
                }
            )
        unsigned = {
            "schema_version": 2,
            "result_type": "wb001_evaluation",
            "runner_version": "0.2.0",
            "workbench": {"id": "WB-001", "version": "0.2.0"},
            "operator_id": operator_id,
            "candidate_artifact_sha256": artifact_sha256,
            "artifact_manifest": artifact_manifest,
            "execution_boundary": {
                "mode": (
                    "docker-isolated-process"
                    if operator_id.startswith("local:validator")
                    else "trusted-local-process"
                ),
                "security_boundary": operator_id.startswith("local:validator"),
                "promotion_grade": False,
                "timing_grade": "advisory",
            },
            "runtime_fingerprint_sha256": sha256_bytes(
                f"test-runtime:{operator_id}".encode("utf-8")
            ),
            "corpus": {
                "profile": PUBLIC_MANIFEST["profile"],
                "manifest_sha256": sha256_file(PUBLIC_MANIFEST_PATH),
                "corpus_sha256": logical_contract(self.round_document, "public_corpus_manifest"),
                "files": len(PUBLIC_MANIFEST["files"]),
            },
            "hard_gate_pass": hard_gate_pass,
            "failures": [] if hard_gate_pass else ["fixture hard-gate failure"],
            "files": file_rows,
            "aggregate": {
                "files": len(file_rows),
                "total_input_bytes": sum(row["original_bytes"] for row in file_rows),
                "total_compressed_bytes": sum(row["compressed_bytes"] for row in file_rows),
            },
        }
        result = {
            **unsigned,
            "result_sha256": sha256_bytes(canonical_json_bytes(unsigned)),
        }
        safe_operator = operator_id.replace(":", "-")
        path = self.root / f"result-{safe_operator}-{variant}-{int(hard_gate_pass)}.json"
        write_json(path, result)
        return path

    def make_comparison(self, result_path: Path, *, status: str = "PUBLIC_SIZE_CANDIDATE") -> Path:
        result = json.loads(result_path.read_text(encoding="utf-8"))
        unsigned = {
            "schema_version": 2,
            "decision_type": "wb001_frontier_comparison",
            "workbench": result["workbench"],
            "baseline_pack_sha256": logical_contract(
                self.round_document, "reference_frontier_pack"
            ),
            "candidate_result_sha256": result["result_sha256"],
            "candidate_artifact_sha256": result["candidate_artifact_sha256"],
            "corpus_sha256": result["corpus"]["corpus_sha256"],
            "status": status,
            "eligible_for_promotion": False,
            "candidate_metrics": {
                "total_compressed_bytes": result["aggregate"]["total_compressed_bytes"]
            },
        }
        comparison = {
            **unsigned,
            "decision_sha256": sha256_bytes(canonical_json_bytes(unsigned)),
        }
        path = self.root / f"comparison-{result['operator_id'].replace(':', '-')}.json"
        write_json(path, comparison)
        return path

    def start_enveloped_attempt(
        self,
        *,
        work_claim: dict,
        attempt_id: str,
        record_receipt: bool = True,
    ) -> dict:
        claim_id = work_claim["payload"]["work_claim_id"]
        capability = sha256_bytes(f"release\0{claim_id}".encode("utf-8"))
        envelope_id = f"envelope:{sha256_bytes(claim_id.encode('utf-8'))[:32]}"
        issued = self.plane.issue_work_envelope(
            actor_id="local:admin",
            work_claim_id=claim_id,
            policy_path=ENVELOPE_POLICY_PATH,
            release_capability=capability,
            envelope_id=envelope_id,
        )
        event = self.plane.start_attempt(
            operator_id=work_claim["actor_id"],
            work_claim_id=claim_id,
            envelope_id=envelope_id,
            release_capability=capability,
            attempt_id=attempt_id,
        )
        if record_receipt:
            envelope = issued["event"]["payload"]["envelope"]
            moment = self.clock.value.isoformat().replace("+00:00", "Z")
            receipt = build_receipt(
                attempt_id=attempt_id,
                envelope=envelope,
                started_at=moment,
                finished_at=moment,
                exit_code=0,
                termination_reason="COMPLETED",
                wall_seconds=0.0,
                output_bytes=0,
                stdout_sha256=sha256_bytes(b""),
                stderr_sha256=sha256_bytes(b""),
            )
            self.plane.record_attempt_receipt(
                operator_id=work_claim["actor_id"],
                attempt_id=attempt_id,
                receipt=receipt,
            )
        return event

    def start_result(
        self,
        *,
        negative: bool = False,
        artifact_sha256: str | None = None,
    ) -> str:
        artifact_sha256 = artifact_sha256 or self.artifact_hash
        claim = self.plane.claim_work(
            operator_id="local:author",
            round_id="WB001-PILOT-001",
            work_unit_id="wu:preprocess-integers",
        )
        attempt = self.start_enveloped_attempt(
            work_claim=claim,
            attempt_id="attempt:test-one",
        )
        attempt_id = attempt["payload"]["attempt_id"]
        if negative:
            self.plane.record_negative(
                operator_id="local:author",
                attempt_id=attempt_id,
                evidence_path=self.evidence,
                candidate_artifact_sha256=artifact_sha256,
                classification="HYPOTHESIS_REJECTED",
                reason_code="HEADER_COST_EXCEEDS_GAIN",
                hypothesis="Small-block delta transforms improve total size.",
                public_summary="The transform was valid but its headers cost more than it saved.",
            )
        else:
            result_path = self.make_wb_result("local:author", artifact_sha256=artifact_sha256)
            comparison_path = self.make_comparison(result_path)
            self.plane.submit_result(
                operator_id="local:author",
                attempt_id=attempt_id,
                evidence_path=result_path,
                comparison_path=comparison_path,
                candidate_submission_path=(
                    DEMO_SUBMISSION
                    if artifact_sha256 == self.demo_artifact_manifest["artifact_sha256"]
                    else self.candidate_submission
                ),
                candidate_artifact_sha256=artifact_sha256,
                result_kind="CANDIDATE",
                public_summary="Candidate sealed for blind reruns; metrics withheld.",
            )
        return attempt_id

    def start_empty_attempt(
        self,
        *,
        work_unit_id: str = "wu:selector-policy",
        attempt_id: str = "attempt:empty-test",
    ) -> str:
        claim = self.plane.claim_work(
            operator_id="local:author",
            round_id="WB001-PILOT-001",
            work_unit_id=work_unit_id,
        )
        event = self.start_enveloped_attempt(
            work_claim=claim,
            attempt_id=attempt_id,
        )
        return event["payload"]["attempt_id"]

    def commit_rerun(self, attempt_id: str, operator_id: str, conclusion: str) -> None:
        lease = self.claim_rerun(operator_id=operator_id, attempt_id=attempt_id)
        variant = 0 if conclusion == "AGREES" else 1
        hard_gate_pass = conclusion != "INVALID"
        result_path = self.make_wb_result(
            operator_id,
            artifact_sha256=self.plane.state()["attempts"][attempt_id]["result"]["candidate_artifact_sha256"],
            variant=variant,
            hard_gate_pass=hard_gate_pass,
        )
        self.plane.submit_rerun(
            operator_id=operator_id,
            rerun_claim_id=lease["event"]["payload"]["rerun_claim_id"],
            capability=lease["lease_capability"],
            evidence_path=result_path,
        )

    def claim_rerun(
        self,
        *,
        operator_id: str,
        attempt_id: str,
        request_id: str | None = None,
    ) -> dict:
        capability = sha256_bytes(f"{operator_id}\0{attempt_id}\0test-capability".encode("utf-8"))
        return self.plane.claim_rerun(
            operator_id=operator_id,
            attempt_id=attempt_id,
            capability=capability,
            conflict_declaration=True,
            request_id=request_id,
        )

    def test_round_is_frozen_and_all_nine_units_start_open(self) -> None:
        snapshot = self.plane.snapshot(round_id="WB001-PILOT-001")
        self.assertTrue(snapshot["ledger"]["valid"])
        self.assertEqual(snapshot["rounds"][0]["contract_status"], "MATCH")
        self.assertEqual(len(snapshot["rounds"][0]["work_units"]), 9)
        self.assertEqual({row["status"] for row in snapshot["rounds"][0]["work_units"]}, {"OPEN"})

    def test_active_work_claim_is_exclusive(self) -> None:
        self.plane.claim_work(
            operator_id="local:author",
            round_id="WB001-PILOT-001",
            work_unit_id="wu:preprocess-integers",
        )
        with self.assertRaises(TransitionError):
            self.plane.claim_work(
                operator_id="local:validator-a",
                round_id="WB001-PILOT-001",
                work_unit_id="wu:preprocess-integers",
            )

    def test_worker_cannot_claim_before_standard_entry_gate(self) -> None:
        self.plane.check_in(
            operator_id="local:not-ready",
            provider="local-test",
            subject="not-ready-subject",
            display_name="Not ready",
        )
        with self.assertRaises(TransitionError):
            self.plane.claim_work(
                operator_id="local:not-ready",
                round_id="WB001-PILOT-001",
                work_unit_id="wu:selector-features",
            )

    def test_attempt_cannot_start_without_issued_envelope(self) -> None:
        claim = self.plane.claim_work(
            operator_id="local:author",
            round_id="WB001-PILOT-001",
            work_unit_id="wu:selector-features",
        )
        with self.assertRaises(TransitionError):
            self.plane.start_attempt(
                operator_id="local:author",
                work_claim_id=claim["payload"]["work_claim_id"],
                envelope_id="envelope:" + "0" * 32,
                release_capability="x" * 32,
            )

    def test_human_release_capability_is_required_to_start(self) -> None:
        claim = self.plane.claim_work(
            operator_id="local:author",
            round_id="WB001-PILOT-001",
            work_unit_id="wu:selector-features",
        )
        claim_id = claim["payload"]["work_claim_id"]
        issued = self.plane.issue_work_envelope(
            actor_id="local:admin",
            work_claim_id=claim_id,
            policy_path=ENVELOPE_POLICY_PATH,
            release_capability="correct-human-retained-capability-1234",
        )
        with self.assertRaises(TransitionError):
            self.plane.start_attempt(
                operator_id="local:author",
                work_claim_id=claim_id,
                envelope_id=issued["event"]["payload"]["envelope"]["envelope_id"],
                release_capability="wrong-human-retained-capability-56789",
            )

    def test_local_monitored_executor_records_non_promotion_receipt(self) -> None:
        claim = self.plane.claim_work(
            operator_id="local:author",
            round_id="WB001-PILOT-001",
            work_unit_id="wu:selector-features",
        )
        self.start_enveloped_attempt(
            work_claim=claim,
            attempt_id="attempt:synthetic-executor",
            record_receipt=False,
        )
        executed = self.plane.execute_attempt(
            operator_id="local:author",
            attempt_id="attempt:synthetic-executor",
        )
        self.assertTrue(executed["within_envelope"])
        self.assertFalse(executed["promotion_eligible"])
        snapshot = self.plane.snapshot()
        attempt = next(
            row for row in snapshot["attempts"] if row["attempt_id"] == "attempt:synthetic-executor"
        )
        self.assertTrue(attempt["within_envelope"])
        self.assertEqual(attempt["status"], "EXECUTION_RECORDED_AWAITING_RESULT")
        with self.assertRaises(TransitionError):
            self.plane.execute_attempt(
                operator_id="local:author",
                attempt_id="attempt:synthetic-executor",
            )

    def test_human_stopped_execution_is_retained_not_promoted(self) -> None:
        claim = self.plane.claim_work(
            operator_id="local:author",
            round_id="WB001-PILOT-001",
            work_unit_id="wu:selector-features",
        )
        self.start_enveloped_attempt(
            work_claim=claim,
            attempt_id="attempt:human-stop",
            record_receipt=False,
        )
        self.plane.request_attempt_stop(
            actor_id="local:admin",
            attempt_id="attempt:human-stop",
            reason="Commissioning stop-control test.",
        )
        with self.assertRaises(TransitionError):
            self.plane.execute_attempt(
                operator_id="local:author",
                attempt_id="attempt:human-stop",
            )
        state = self.plane.state()
        attempt = state["attempts"]["attempt:human-stop"]
        envelope = state["work_envelopes"][attempt["envelope_id"]]
        moment = self.clock.value.isoformat().replace("+00:00", "Z")
        receipt = build_receipt(
            attempt_id="attempt:human-stop",
            envelope=envelope,
            started_at=moment,
            finished_at=moment,
            exit_code=None,
            termination_reason="HUMAN_STOP",
            wall_seconds=0.0,
            output_bytes=0,
            stdout_sha256=sha256_bytes(b""),
            stderr_sha256=sha256_bytes(b""),
        )
        self.plane.record_attempt_receipt(
            operator_id="local:author",
            attempt_id="attempt:human-stop",
            receipt=receipt,
        )
        self.plane.terminate_attempt(
            actor_id="local:admin",
            attempt_id="attempt:human-stop",
            reason="Stop receipt retained for audit.",
        )
        self.assertEqual(
            self.plane.snapshot()["attempts"][0]["status"],
            "TERMINATED_RETAINED",
        )

    def test_expired_claim_can_be_superseded_but_old_owner_cannot_start(self) -> None:
        old = self.plane.claim_work(
            operator_id="local:author",
            round_id="WB001-PILOT-001",
            work_unit_id="wu:preprocess-integers",
        )
        old_claim_id = old["payload"]["work_claim_id"]
        capability = sha256_bytes(f"release\0{old_claim_id}".encode("utf-8"))
        envelope_id = f"envelope:{sha256_bytes(old_claim_id.encode('utf-8'))[:32]}"
        self.plane.issue_work_envelope(
            actor_id="local:admin",
            work_claim_id=old_claim_id,
            policy_path=ENVELOPE_POLICY_PATH,
            release_capability=capability,
            envelope_id=envelope_id,
        )
        self.clock.advance(hours=7)
        new = self.plane.claim_work(
            operator_id="local:validator-a",
            round_id="WB001-PILOT-001",
            work_unit_id="wu:preprocess-integers",
        )
        self.assertIn(old["payload"]["work_claim_id"], new["payload"]["supersedes_claim_ids"])
        with self.assertRaises(TransitionError):
            self.plane.start_attempt(
                operator_id="local:author",
                work_claim_id=old_claim_id,
                envelope_id=envelope_id,
                release_capability=capability,
            )

    def test_duplicate_canonical_identity_is_rejected(self) -> None:
        with self.assertRaises(TransitionError):
            self.plane.check_in(
                operator_id="local:alias",
                provider="local-test",
                subject="subject-local:author",
                display_name="Author alias",
            )

    def test_author_cannot_claim_own_rerun(self) -> None:
        attempt_id = self.start_result()
        with self.assertRaises(TransitionError):
            self.claim_rerun(operator_id="local:author", attempt_id=attempt_id)

    def test_same_operator_cannot_take_two_rerun_slots(self) -> None:
        attempt_id = self.start_result()
        self.commit_rerun(attempt_id, "local:validator-a", "AGREES")
        with self.assertRaises(TransitionError):
            self.claim_rerun(operator_id="local:validator-a", attempt_id=attempt_id)

    def test_work_unit_reopens_with_history_after_a_completed_shift(self) -> None:
        self.start_result()
        snapshot = self.plane.snapshot()
        unit = next(
            row for row in snapshot["rounds"][0]["work_units"]
            if row["work_unit_id"] == "wu:preprocess-integers"
        )
        self.assertEqual(unit["status"], "OPEN_WITH_HISTORY")
        self.assertEqual(unit["completed_attempts"], 1)
        new_claim = self.plane.claim_work(
            operator_id="local:validator-a",
            round_id="WB001-PILOT-001",
            work_unit_id="wu:preprocess-integers",
        )
        self.assertEqual(new_claim["payload"]["work_unit_id"], "wu:preprocess-integers")

    def test_two_other_people_confirm_without_publicly_revealing_conclusions(self) -> None:
        attempt_id = self.start_result()
        self.commit_rerun(attempt_id, "local:validator-a", "AGREES")
        self.commit_rerun(attempt_id, "local:validator-b", "AGREES")

        public_ledger = (self.root / "events.jsonl").read_text(encoding="utf-8")
        self.assertNotIn('"conclusion":"AGREES"', public_ledger)
        self.assertNotIn("exact_output_fingerprint_sha256", public_ledger)
        self.assertNotIn("candidate_total_compressed_bytes", public_ledger)
        self.assertNotIn('"total_compressed_bytes"', public_ledger)
        gate = self.plane.evaluate_reruns(actor_id="local:admin", attempt_id=attempt_id)
        self.assertEqual(gate["payload"]["status"], "RERUN_CONFIRMED_AWAITING_HOLDOUT")
        self.assertTrue(gate["payload"]["individual_conclusions_sealed"])
        self.assertEqual(self.plane.snapshot()["attempts"][0]["status"], "RERUN_CONFIRMED_AWAITING_HOLDOUT")
        audit = self.plane.audit_blindness()
        self.assertTrue(audit["valid"])
        self.assertEqual(audit["sealed_rerun_commitments"], 2)
        self.assertEqual(audit["violations"], [])

    def test_relabelled_result_without_recomputed_hash_cannot_fill_a_rerun_slot(self) -> None:
        attempt_id = self.start_result()
        lease = self.claim_rerun(operator_id="local:validator-a", attempt_id=attempt_id)
        original_path = self.make_wb_result("local:author")
        relabelled = json.loads(original_path.read_text(encoding="utf-8"))
        relabelled["operator_id"] = "local:validator-a"
        relabelled_path = self.root / "relabelled-result.json"
        write_json(relabelled_path, relabelled)
        with self.assertRaises(ContractError):
            self.plane.submit_rerun(
                operator_id="local:validator-a",
                rerun_claim_id=lease["event"]["payload"]["rerun_claim_id"],
                capability=lease["lease_capability"],
                evidence_path=relabelled_path,
            )

    def test_candidate_comparison_must_bind_the_exact_result(self) -> None:
        claim = self.plane.claim_work(
            operator_id="local:author",
            round_id="WB001-PILOT-001",
            work_unit_id="wu:selector-policy",
        )
        attempt = self.start_enveloped_attempt(
            work_claim=claim,
            attempt_id="attempt:bad-comparison",
        )
        result_path = self.make_wb_result("local:author")
        comparison_path = self.make_comparison(result_path)
        comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
        comparison["candidate_result_sha256"] = "d" * 64
        comparison.pop("decision_sha256")
        comparison["decision_sha256"] = sha256_bytes(canonical_json_bytes(comparison))
        write_json(comparison_path, comparison)
        with self.assertRaises(ContractError):
            self.plane.submit_result(
                operator_id="local:author",
                attempt_id=attempt["payload"]["attempt_id"],
                evidence_path=result_path,
                comparison_path=comparison_path,
                candidate_submission_path=self.candidate_submission,
                candidate_artifact_sha256=self.artifact_hash,
                result_kind="CANDIDATE",
                public_summary="Comparison binding fixture.",
            )

    def test_result_must_cover_the_exact_frozen_public_manifest(self) -> None:
        attempt_id = self.start_empty_attempt()
        result_path = self.make_wb_result("local:author")
        result = json.loads(result_path.read_text(encoding="utf-8"))
        result["files"].pop()
        result["aggregate"]["files"] = len(result["files"])
        result["aggregate"]["total_input_bytes"] = sum(
            row["original_bytes"] for row in result["files"]
        )
        result["aggregate"]["total_compressed_bytes"] = sum(
            row["compressed_bytes"] for row in result["files"]
        )
        result.pop("result_sha256")
        result["result_sha256"] = sha256_bytes(canonical_json_bytes(result))
        write_json(result_path, result)
        comparison_path = self.make_comparison(result_path)
        with self.assertRaises(ContractError):
            self.plane.submit_result(
                operator_id="local:author",
                attempt_id=attempt_id,
                evidence_path=result_path,
                comparison_path=comparison_path,
                candidate_submission_path=self.candidate_submission,
                candidate_artifact_sha256=self.artifact_hash,
                result_kind="CANDIDATE",
                public_summary="Incomplete corpus fixture.",
            )

    def test_frontier_status_is_recomputed_not_trusted(self) -> None:
        attempt_id = self.start_empty_attempt()
        result_path = self.make_wb_result("local:author")
        comparison_path = self.make_comparison(
            result_path,
            status="VALID_NO_CONFIRMED_GAIN",
        )
        with self.assertRaises(ContractError):
            self.plane.submit_result(
                operator_id="local:author",
                attempt_id=attempt_id,
                evidence_path=result_path,
                comparison_path=comparison_path,
                candidate_submission_path=self.candidate_submission,
                candidate_artifact_sha256=self.artifact_hash,
                result_kind="CANDIDATE",
                public_summary="Forged comparison status fixture.",
            )

    def test_locked_metric_free_artifact_is_exportable_and_tamper_checked(self) -> None:
        attempt_id = self.start_result()
        attempt = self.plane.state()["attempts"][attempt_id]
        package = attempt["result"]["candidate_artifact_package_sha256"]
        output = self.root / "rerunner-artifact"
        exported = self.plane.artifacts.export(package, output)
        self.assertEqual(exported["package_sha256"], package)
        self.assertEqual(
            {path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file()},
            {"candidate.py", "submission.json"},
        )
        self.assertNotIn("result", " ".join(path.name for path in output.rglob("*")))
        stored_source = self.plane.artifacts.root / "sha256" / package / "files" / "candidate.py"
        stored_source.chmod(0o644)
        stored_source.write_text("tampered\n", encoding="utf-8")
        with self.assertRaises(ContractError):
            self.plane.artifacts.export(package, self.root / "second-export")

    def test_tampered_candidate_source_cannot_be_handed_to_rerunners(self) -> None:
        attempt_id = self.start_empty_attempt()
        result_path = self.make_wb_result("local:author")
        comparison_path = self.make_comparison(result_path)
        self.candidate_source.write_text("changed after measurement\n", encoding="utf-8")
        with self.assertRaises(ContractError):
            self.plane.submit_result(
                operator_id="local:author",
                attempt_id=attempt_id,
                evidence_path=result_path,
                comparison_path=comparison_path,
                candidate_submission_path=self.candidate_submission,
                candidate_artifact_sha256=self.artifact_hash,
                result_kind="CANDIDATE",
                public_summary="Tampered artifact fixture.",
            )

    def test_expired_work_claim_cannot_submit_a_late_result(self) -> None:
        attempt_id = self.start_empty_attempt()
        self.clock.advance(hours=7)
        result_path = self.make_wb_result("local:author")
        comparison_path = self.make_comparison(result_path)
        with self.assertRaises(TransitionError):
            self.plane.submit_result(
                operator_id="local:author",
                attempt_id=attempt_id,
                evidence_path=result_path,
                comparison_path=comparison_path,
                candidate_submission_path=self.candidate_submission,
                candidate_artifact_sha256=self.artifact_hash,
                result_kind="CANDIDATE",
                public_summary="Expired work fixture.",
            )

    def test_split_result_opens_one_diagnostic_rerun_and_never_majority_promotes(self) -> None:
        attempt_id = self.start_result()
        self.commit_rerun(attempt_id, "local:validator-a", "AGREES")
        self.commit_rerun(attempt_id, "local:validator-b", "DISAGREES")
        first_gate = self.plane.evaluate_reruns(actor_id="local:admin", attempt_id=attempt_id)
        self.assertEqual(first_gate["payload"]["status"], "TIEBREAK_DIAGNOSTIC_REQUIRED")

        self.commit_rerun(attempt_id, "local:validator-c", "AGREES")
        second_gate = self.plane.evaluate_reruns(actor_id="local:admin", attempt_id=attempt_id)
        self.assertEqual(second_gate["payload"]["status"], "DISPUTED_REVIEW_REQUIRED")
        with self.assertRaises(TransitionError):
            self.claim_rerun(operator_id="local:admin", attempt_id=attempt_id)

    def test_invalid_rerun_can_be_replaced_once(self) -> None:
        attempt_id = self.start_result()
        self.commit_rerun(attempt_id, "local:validator-a", "INVALID")
        self.commit_rerun(attempt_id, "local:validator-b", "AGREES")
        first_gate = self.plane.evaluate_reruns(actor_id="local:admin", attempt_id=attempt_id)
        self.assertEqual(first_gate["payload"]["status"], "REPLACEMENT_RERUN_REQUIRED")
        self.commit_rerun(attempt_id, "local:validator-c", "AGREES")
        second_gate = self.plane.evaluate_reruns(actor_id="local:admin", attempt_id=attempt_id)
        self.assertEqual(second_gate["payload"]["status"], "RERUN_CONFIRMED_AWAITING_HOLDOUT")

    def test_plaintext_annotations_are_blocked_during_blind_reruns(self) -> None:
        attempt_id = self.start_result()
        with self.assertRaises(TransitionError):
            self.plane.annotate_attempt(
                actor_id="local:author",
                attempt_id=attempt_id,
                note="exact result is 123 bytes",
            )

    def test_non_admin_cannot_reveal_committed_reruns(self) -> None:
        attempt_id = self.start_result()
        self.commit_rerun(attempt_id, "local:validator-a", "AGREES")
        self.commit_rerun(attempt_id, "local:validator-b", "AGREES")
        with self.assertRaises(TransitionError):
            self.plane.evaluate_reruns(actor_id="local:author", attempt_id=attempt_id)

    def test_negative_result_is_searchable_and_can_be_confirmed(self) -> None:
        attempt_id = self.start_result(negative=True)
        snapshot = self.plane.snapshot()
        self.assertEqual(len(snapshot["negative_results"]), 1)
        self.assertEqual(snapshot["negative_results"][0]["reason_code"], "HEADER_COST_EXCEEDS_GAIN")
        self.assertEqual(snapshot["attempts"][0]["status"], "NEGATIVE_RESULT_RETAINED")
        with self.assertRaises(TransitionError):
            self.claim_rerun(operator_id="local:validator-a", attempt_id=attempt_id)

    def test_signed_holdout_attestation_is_joined_only_after_two_reruns(self) -> None:
        attempt_id = self.start_result()
        with self.assertRaises(TransitionError):
            self.plane.record_holdout_attestation(
                actor_id="local:admin",
                attempt_id=attempt_id,
                attestation_path=self.evidence,
            )
        self.commit_rerun(attempt_id, "local:validator-a", "AGREES")
        self.commit_rerun(attempt_id, "local:validator-b", "AGREES")
        gate_event = self.plane.evaluate_reruns(actor_id="local:admin", attempt_id=attempt_id)
        token_path, attestation_path = self.make_holdout_job_and_attestation(
            attempt_id=attempt_id,
            gate_event=gate_event,
        )
        self.plane.record_holdout_job(
            actor_id="local:admin",
            attempt_id=attempt_id,
            token_path=token_path,
        )
        self.clock.advance(minutes=1)
        event = self.plane.record_holdout_attestation(
            actor_id="local:admin",
            attempt_id=attempt_id,
            attestation_path=attestation_path,
        )
        self.assertEqual(event["payload"]["verdict"], "NO_GAIN")
        self.assertTrue(event["payload"]["signature_verified"])
        self.assertEqual(self.plane.snapshot()["attempts"][0]["status"], "RETAINED_NO_GAIN")

    def test_tampered_holdout_attestation_is_rejected(self) -> None:
        attempt_id = self.start_result()
        self.commit_rerun(attempt_id, "local:validator-a", "AGREES")
        self.commit_rerun(attempt_id, "local:validator-b", "AGREES")
        gate_event = self.plane.evaluate_reruns(actor_id="local:admin", attempt_id=attempt_id)
        token_path, attestation_path = self.make_holdout_job_and_attestation(
            attempt_id=attempt_id,
            gate_event=gate_event,
        )
        self.plane.record_holdout_job(
            actor_id="local:admin",
            attempt_id=attempt_id,
            token_path=token_path,
        )
        tampered = json.loads(attestation_path.read_text(encoding="utf-8"))
        tampered["verdict"] = "PASS"
        path = self.root / "tampered-attestation.json"
        write_json(path, tampered)
        with self.assertRaises(ContractError):
            self.plane.record_holdout_attestation(
                actor_id="local:admin",
                attempt_id=attempt_id,
                attestation_path=path,
            )

    def test_rerun_capability_is_required_and_expiry_is_enforced(self) -> None:
        attempt_id = self.start_result()
        lease = self.claim_rerun(operator_id="local:validator-a", attempt_id=attempt_id)
        with self.assertRaises(TransitionError):
            self.plane.submit_rerun(
                operator_id="local:validator-a",
                rerun_claim_id=lease["event"]["payload"]["rerun_claim_id"],
                capability="wrong-capability",
                evidence_path=self.make_wb_result("local:validator-a"),
            )
        self.clock.advance(hours=7)
        with self.assertRaises(TransitionError):
            self.plane.submit_rerun(
                operator_id="local:validator-a",
                rerun_claim_id=lease["event"]["payload"]["rerun_claim_id"],
                capability=lease["lease_capability"],
                evidence_path=self.make_wb_result("local:validator-a"),
            )

    def test_request_id_is_idempotent_but_cannot_be_repurposed(self) -> None:
        first = self.plane.claim_work(
            operator_id="local:author",
            round_id="WB001-PILOT-001",
            work_unit_id="wu:preprocess-integers",
            request_id="request:stable-test",
        )
        retry = self.plane.claim_work(
            operator_id="local:author",
            round_id="WB001-PILOT-001",
            work_unit_id="wu:preprocess-integers",
            request_id="request:stable-test",
        )
        self.assertEqual(first, retry)
        with self.assertRaises((ContractError, TransitionError)):
            self.plane.claim_work(
                operator_id="local:author",
                round_id="WB001-PILOT-001",
                work_unit_id="wu:selector-features",
                request_id="request:stable-test",
            )
        self.assertEqual(first["request_id"], "request:stable-test")

    def test_rerun_claim_retry_recovers_client_retained_capability(self) -> None:
        attempt_id = self.start_result()
        first = self.claim_rerun(
            operator_id="local:validator-a",
            attempt_id=attempt_id,
            request_id="request:rerun-lease",
        )
        self.assertIsInstance(first["lease_capability"], str)
        retry = self.claim_rerun(
            operator_id="local:validator-a",
            attempt_id=attempt_id,
            request_id="request:rerun-lease",
        )
        self.assertEqual(first["lease_capability"], retry["lease_capability"])
        self.assertEqual(first["event"], retry["event"])

    def test_rerun_submission_retry_succeeds_after_lease_expiry(self) -> None:
        attempt_id = self.start_result()
        lease = self.claim_rerun(
            operator_id="local:validator-a",
            attempt_id=attempt_id,
            request_id="request:rerun-claim-stable",
        )
        result_path = self.make_wb_result("local:validator-a")
        first = self.plane.submit_rerun(
            operator_id="local:validator-a",
            rerun_claim_id=lease["event"]["payload"]["rerun_claim_id"],
            capability=lease["lease_capability"],
            evidence_path=result_path,
            request_id="request:rerun-submit-stable",
        )
        self.clock.advance(hours=7)
        retry = self.plane.submit_rerun(
            operator_id="local:validator-a",
            rerun_claim_id=lease["event"]["payload"]["rerun_claim_id"],
            capability=lease["lease_capability"],
            evidence_path=result_path,
            request_id="request:rerun-submit-stable",
        )
        self.assertEqual(first, retry)

    def test_rerun_gate_evaluation_is_idempotent(self) -> None:
        attempt_id = self.start_result()
        self.commit_rerun(attempt_id, "local:validator-a", "AGREES")
        self.commit_rerun(attempt_id, "local:validator-b", "AGREES")
        first = self.plane.evaluate_reruns(
            actor_id="local:admin",
            attempt_id=attempt_id,
            request_id="request:gate-stable",
        )
        retry = self.plane.evaluate_reruns(
            actor_id="local:admin",
            attempt_id=attempt_id,
            request_id="request:gate-stable",
        )
        self.assertEqual(first, retry)

    def test_ledger_tampering_is_detected(self) -> None:
        ledger_path = self.root / "events.jsonl"
        lines = ledger_path.read_text(encoding="utf-8").splitlines()
        first = json.loads(lines[0])
        first["payload"]["factory_id"] = "factory:altered"
        lines[0] = json.dumps(first, sort_keys=True, separators=(",", ":"))
        ledger_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with self.assertRaises(LedgerIntegrityError):
            self.plane.ledger.verify()

    def test_round_contract_drift_blocks_new_work_without_rewriting_history(self) -> None:
        with tempfile.TemporaryDirectory() as factory_temp:
            factory_root = Path(factory_temp)
            contract = factory_root / "contract.txt"
            contract.write_text("frozen\n", encoding="utf-8")
            unsigned = {
                "schema_version": 1,
                "round_id": "ROUND-DRIFT-001",
                "title": "Drift test",
                "status": "LOCAL_PILOT",
                "workbench": {"id": "TEST", "version": "1", "evidence_lane": "digital-exact"},
                "identity_assurance": "self-asserted-local",
                "promotion_scope": "technical-workflow-pilot-no-public-promotion",
                "worker_timebox_hours": 4,
                "default_claim_lease_hours": 6,
                "required_independent_reruns": 2,
                "max_diagnostic_reruns": 1,
                "disagreement_policy": "human_review_no_majority_promotion",
                "evaluator_software_sha256": "b" * 64,
                "promotion_grade_execution_required": True,
                "worker_entry_gate": {
                    "required": True,
                    "estimated_minutes": 1,
                    "tasks": ["Run the drift fixture."],
                },
                "hard_rules": ["The frozen contract must continue to match."],
                "frozen_contracts": [
                    {"name": "test_contract", "path": "contract.txt", "sha256": sha256_file(contract)}
                ],
                "lanes": [
                    {
                        "lane_id": "lane:test",
                        "title": "Test",
                        "goal": "Test drift handling.",
                        "economic_question": "Does the test remain bounded?",
                    }
                ],
                "work_units": [
                    {
                        "work_unit_id": "wu:test",
                        "lane_id": "lane:test",
                        "title": "Test work",
                        "brief": "Exercise one frozen-contract transition.",
                    }
                ],
                "negative_result_taxonomy": ["NO_GAIN"],
            }
            round_document = {
                **unsigned,
                "round_sha256": sha256_bytes(canonical_json_bytes(unsigned)),
            }
            round_path = factory_root / "round.json"
            write_json(round_path, round_document)
            plane = ControlPlane(
                self.root / "drift-events.jsonl",
                factory_root=factory_root,
                clock=self.clock,
            )
            plane.initialize(
                factory_id="factory:drift",
                admin_id="local:drift-admin",
                provider="local-test",
                subject="drift-admin",
                display_name="Drift admin",
            )
            plane.open_round(actor_id="local:drift-admin", round_path=round_path)
            entry_unsigned = {
                "schema_version": 1,
                "evidence_type": "worker_entry_gate",
                "generated_at": "2026-08-02T09:00:00Z",
                "started_at": "2026-08-02T08:59:00Z",
                "round_id": "ROUND-DRIFT-001",
                "round_sha256": round_document["round_sha256"],
                "operator_id": "local:drift-admin",
                "checks": {
                    "frozen_contracts_match": True,
                    "schemas_validate": True,
                    "reference_round_trip_exact": True,
                    "reference_output_deterministic": True,
                    "rules_acknowledged": True,
                },
                "reference_result": {"result_sha256": "c" * 64},
                "environment": {"test": True},
                "commands": [{"command": ["validate"]}, {"command": ["rerun"]}],
            }
            entry = {
                **entry_unsigned,
                "entry_evidence_sha256": sha256_bytes(canonical_json_bytes(entry_unsigned)),
            }
            entry_path = factory_root / "entry.json"
            write_json(entry_path, entry)
            plane.complete_entry_gate(
                operator_id="local:drift-admin",
                round_id="ROUND-DRIFT-001",
                evidence_path=entry_path,
            )
            contract.write_text("changed\n", encoding="utf-8")
            with self.assertRaises(TransitionError):
                plane.claim_work(
                    operator_id="local:drift-admin",
                    round_id="ROUND-DRIFT-001",
                    work_unit_id="wu:test",
                )
            snapshot = plane.snapshot()
            self.assertEqual(snapshot["rounds"][0]["contract_status"], "DRIFTED")
            self.assertEqual(snapshot["ledger"]["events"], 3)


if __name__ == "__main__":
    unittest.main()
