from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from control_plane.common import ContractError, LedgerIntegrityError, sha256_bytes
from corrections.ledger import CorrectionLedger, load_json_strict
from corrections.synthetic_drill import run_synthetic_drill, verify_synthetic_drill


def digest(label: str) -> str:
    return sha256_bytes(label.encode("utf-8"))


def reference(
    artifact_id: str,
    label: str,
    *,
    artifact_class: str = "SHIFT_REPORT",
) -> dict[str, object]:
    return {
        "artifact_class": artifact_class,
        "artifact_id": artifact_id,
        "artifact_sha256": digest(label),
        "locator_kind": "REPOSITORY_PATH",
        "locator": f"factory/corrections/examples/{label}.json",
        "media_type": "application/json",
        "visibility": "PUBLIC",
    }


def draft(
    *,
    correction_id: str,
    action: str,
    target: dict[str, object],
    replacement: dict[str, object] | None,
    reason_code: str = "MATERIAL_ERROR",
) -> dict[str, object]:
    return {
        "correction_id": correction_id,
        "actor": {
            "operator_id": "human:synthetic-maintainer",
            "display_name": "Synthetic Maintainer",
            "identity_assurance": "SELF_ASSERTED_LOCAL",
            "identity_warning": "IDENTITY_RECORD_IS_NOT_PROOF_OF_AUTHORITY",
        },
        "authority": {
            "basis": "MAINTAINER",
            "scope": "Synthetic construction fixture only.",
            "conflict_declaration": "The operator created the synthetic fixture and claims no independence.",
            "authorization_evidence_sha256": [],
        },
        "target": target,
        "action": action,
        "replacement": replacement,
        "reason": {
            "code": reason_code,
            "summary": "A known synthetic statement was deliberately shown to be materially wrong.",
            "evidence_references": [],
        },
        "public_summary": "Correct the known synthetic statement while retaining the original bytes.",
    }


class CorrectionLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.ledger_path = self.root / "corrections.jsonl"
        self.ledger = CorrectionLedger(self.ledger_path)
        self.target = reference("shift-report:synthetic-original", "original")
        self.replacement = reference("shift-report:synthetic-corrected", "corrected")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_correction_then_retraction_preserves_history_and_derives_current_standing(self) -> None:
        first = self.ledger.append(
            draft(
                correction_id="correction:synthetic-corrigendum",
                action="CORRIGENDUM",
                target=self.target,
                replacement=self.replacement,
            ),
            recorded_at="2026-08-06T10:00:00Z",
        )
        self.assertEqual("CURRENT", first["standing_before"])
        self.assertEqual("CURRENT_WITH_CORRECTION", first["standing_after"])
        second = self.ledger.append(
            draft(
                correction_id="correction:synthetic-retraction",
                action="RETRACTION",
                target=self.target,
                replacement=None,
                reason_code="WITHDRAWN_CLAIM",
            ),
            recorded_at="2026-08-06T11:00:00Z",
        )
        self.assertEqual(first["record_sha256"], second["previous_record_sha256"])
        self.assertEqual("CURRENT_WITH_CORRECTION", second["standing_before"])
        self.assertEqual("RETRACTED", second["standing_after"])

        verified = self.ledger.verify()
        self.assertTrue(verified["valid"])
        self.assertEqual(2, verified["records"])
        self.assertEqual({"RETRACTED": 1}, verified["current_standings"])
        history = self.ledger.history(target_sha256=self.target["artifact_sha256"])
        self.assertEqual(2, history["returned"])
        self.assertTrue(all(row["current_standing"] == "RETRACTED" for row in history["records"]))
        self.assertTrue(all(row["boundary"]["original_bytes_preserved"] for row in history["records"]))
        self.assertFalse(history["boundary"]["eligible_for_promotion"])

    def test_terminal_standing_cannot_be_restored(self) -> None:
        self.ledger.append(
            draft(
                correction_id="correction:synthetic-invalidation",
                action="INVALIDATION",
                target=self.target,
                replacement=None,
                reason_code="INTEGRITY_FAILURE",
            ),
            recorded_at="2026-08-06T10:00:00Z",
        )
        with self.assertRaisesRegex(ContractError, "terminal standing INVALIDATED"):
            self.ledger.append(
                draft(
                    correction_id="correction:forbidden-restoration",
                    action="CORRIGENDUM",
                    target=self.target,
                    replacement=self.replacement,
                ),
                recorded_at="2026-08-06T11:00:00Z",
            )

    def test_artifact_identity_cannot_be_rebound_to_different_original_bytes(self) -> None:
        self.ledger.append(
            draft(
                correction_id="correction:first-binding",
                action="CORRIGENDUM",
                target=self.target,
                replacement=self.replacement,
            ),
            recorded_at="2026-08-06T10:00:00Z",
        )
        changed_target = {**self.target, "artifact_sha256": digest("different-original")}
        with self.assertRaisesRegex(ContractError, "cannot be rebound"):
            self.ledger.append(
                draft(
                    correction_id="correction:changed-binding",
                    action="CORRIGENDUM",
                    target=changed_target,
                    replacement=self.replacement,
                ),
                recorded_at="2026-08-06T11:00:00Z",
            )
        self.assertEqual(1, self.ledger.verify()["records"])

    def test_tampered_record_is_rejected(self) -> None:
        self.ledger.append(
            draft(
                correction_id="correction:tamper-target",
                action="CORRIGENDUM",
                target=self.target,
                replacement=self.replacement,
            ),
            recorded_at="2026-08-06T10:00:00Z",
        )
        value = json.loads(self.ledger_path.read_text(encoding="utf-8"))
        value["public_summary"] = "Polished history must not pass verification."
        self.ledger_path.write_text(json.dumps(value) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(LedgerIntegrityError, "record hash mismatch"):
            self.ledger.read()

    def test_action_shape_and_private_locators_fail_closed(self) -> None:
        invalid = draft(
            correction_id="correction:missing-replacement",
            action="CORRIGENDUM",
            target=self.target,
            replacement=None,
        )
        with self.assertRaisesRegex(ContractError, "correction schema violation"):
            self.ledger.append(invalid, recorded_at="2026-08-06T10:00:00Z")

        private_target = {**self.target, "locator": "factory/private/answer.json"}
        with self.assertRaisesRegex(ContractError, "protected or hidden"):
            self.ledger.append(
                draft(
                    correction_id="correction:private-target",
                    action="CORRIGENDUM",
                    target=private_target,
                    replacement=self.replacement,
                ),
                recorded_at="2026-08-06T10:00:00Z",
            )

    def test_public_export_refuses_overwrite_and_strips_local_ledger_path(self) -> None:
        self.ledger.append(
            draft(
                correction_id="correction:export-fixture",
                action="CORRIGENDUM",
                target=self.target,
                replacement=self.replacement,
            ),
            recorded_at="2026-08-06T10:00:00Z",
        )
        output = self.root / "public-index.json"
        value = self.ledger.export_public_index(output)
        self.assertTrue(output.is_file())
        self.assertNotIn("ledger", value["ledger"])
        with self.assertRaisesRegex(ContractError, "already exists"):
            self.ledger.export_public_index(output)

    def test_strict_draft_loader_rejects_duplicate_keys(self) -> None:
        path = self.root / "duplicate.json"
        path.write_text('{"action":"CORRIGENDUM","action":"RETRACTION"}\n', encoding="utf-8")
        with self.assertRaisesRegex(ContractError, "duplicate JSON key"):
            load_json_strict(path)

    def test_complete_synthetic_drill_and_tamper_detection(self) -> None:
        output = self.root / "synthetic-drill"
        report = run_synthetic_drill(output)
        self.assertEqual("RETRACTED", report["final_standing"])
        verified = verify_synthetic_drill(output)
        self.assertTrue(verified["valid"])
        self.assertEqual("NONE_SYNTHETIC_COMMISSIONING_ONLY", verified["scientific_standing"])

        original = output / "public" / "original-shift-report.json"
        original.write_text('{"fixture":"tampered"}\n', encoding="utf-8")
        with self.assertRaisesRegex(ContractError, "original artifact bytes changed"):
            verify_synthetic_drill(output)

    def test_synthetic_drill_refuses_to_overwrite_history(self) -> None:
        output = self.root / "existing-output"
        output.mkdir()
        marker = output / "keep.txt"
        marker.write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(ContractError, "already exists"):
            run_synthetic_drill(output)
        self.assertEqual("keep", marker.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
