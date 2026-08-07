from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from control_plane.common import ContractError, LedgerIntegrityError, sha256_bytes, write_json

from appeals.ledger import AppealLedger, load_json_strict
from appeals.synthetic_drill import run_synthetic_drill, verify_synthetic_drill


def digest(label: str) -> str:
    return sha256_bytes(label.encode("utf-8"))


def identity(operator_id: str, name: str) -> dict[str, str]:
    return {
        "operator_id": operator_id,
        "display_name": name,
        "identity_assurance": "SELF_ASSERTED_LOCAL",
        "identity_warning": "IDENTITY_RECORD_IS_NOT_PROOF_OF_A_DISTINCT_HUMAN",
    }


def reviewer(operator_id: str, name: str) -> dict[str, object]:
    return {
        **identity(operator_id, name),
        "conflict_declaration": "NO_MATERIAL_CONFLICT_DECLARED",
        "conflict_evidence_sha256": [],
    }


def draft(
    *,
    appeal_id: str = "appeal:fixture-one",
    case_id: str = "case:fixture-one",
    conclusions: tuple[str, str] = ("UPHOLD_APPEAL", "DENY_APPEAL"),
) -> dict[str, object]:
    reviewer_a = "human:fixture-reviewer-a"
    reviewer_b = "human:fixture-reviewer-b"
    outcome = "RETURN_FOR_DIAGNOSIS"
    follow_up = "FRESH_DIAGNOSTIC_RUN_REQUIRED"
    if conclusions == ("UPHOLD_APPEAL", "UPHOLD_APPEAL"):
        outcome = "UPHOLD_PROCEDURALLY"
        follow_up = "SEPARATE_CORRECTION_OR_REMEDY_RECORD_REQUIRED"
    elif conclusions == ("DENY_APPEAL", "DENY_APPEAL"):
        outcome = "DENY_PROCEDURALLY"
        follow_up = "NO_AUTOMATIC_STANDING_CHANGE"
    return {
        "appeal_id": appeal_id,
        "case": {
            "case_id": case_id,
            "case_kind": "SCIENTIFIC_DISPUTE",
            "target": {
                "artifact_class": "SHIFT_REPORT",
                "artifact_id": "shift-report:fixture",
                "artifact_sha256": digest("target"),
                "locator_kind": "REPOSITORY_PATH",
                "locator": "factory/appeals/tests/public-fixture.json",
                "media_type": "application/json",
                "visibility": "PUBLIC",
            },
            "requester": identity("human:fixture-requester", "Fixture Requester"),
            "materially_involved_identity_ids": [
                "human:fixture-author",
                "human:fixture-validator",
            ],
            "public_summary": "Fixture procedural appeal over a deliberately split synthetic result.",
            "evidence_references": [],
        },
        "panel": {
            "selection_method": "CONFLICT_EXCLUSION_CHECK_V1",
            "minimum_reviewer_count": 2,
            "reviewer_identity_warning": "IDENTITY_RECORD_IS_NOT_PROOF_OF_A_DISTINCT_HUMAN",
            "reviewers": [reviewer(reviewer_a, "Fixture Reviewer A"), reviewer(reviewer_b, "Fixture Reviewer B")],
        },
        "findings": [
            {
                "reviewer_id": reviewer_a,
                "conclusion": conclusions[0],
                "evidence_sha256": digest("reviewer a"),
                "public_summary": "Fixture reviewer A committed a bounded procedural finding.",
            },
            {
                "reviewer_id": reviewer_b,
                "conclusion": conclusions[1],
                "evidence_sha256": digest("reviewer b"),
                "public_summary": "Fixture reviewer B committed a bounded procedural finding.",
            },
        ],
        "outcome": outcome,
        "follow_up": follow_up,
        "decision_public_summary": "Fixture decision never changes scientific standing automatically.",
    }


class AppealLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.ledger = self.root / "appeals.jsonl"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_split_is_not_resolved_by_majority_and_is_hash_linked(self) -> None:
        ledger = AppealLedger(self.ledger)
        record = ledger.append(draft(), recorded_at="2026-08-07T10:00:00Z")
        self.assertEqual("RETURN_FOR_DIAGNOSIS", record["outcome"])
        self.assertEqual("FRESH_DIAGNOSTIC_RUN_REQUIRED", record["follow_up"])
        verified = ledger.verify()
        self.assertEqual({"RETURN_FOR_DIAGNOSIS": 1}, verified["outcomes"])
        self.assertEqual("NONE", verified["scientific_standing"])

        history = ledger.history(case_kind="SCIENTIFIC_DISPUTE", outcome="RETURN_FOR_DIAGNOSIS")
        self.assertEqual(1, history["returned"])
        self.assertFalse(history["boundary"]["automatic_scientific_standing_change"])

    def test_conflicted_or_nonindependent_panels_are_rejected(self) -> None:
        ledger = AppealLedger(self.ledger)

        conflicted = draft()
        conflicted["panel"]["reviewers"][0]["operator_id"] = "human:fixture-author"  # type: ignore[index]
        conflicted["findings"][0]["reviewer_id"] = "human:fixture-author"  # type: ignore[index]
        with self.assertRaisesRegex(ContractError, "materially involved"):
            ledger.append(conflicted)

        duplicate = draft()
        duplicate["panel"]["reviewers"][1]["operator_id"] = "human:fixture-reviewer-a"  # type: ignore[index]
        duplicate["findings"][1]["reviewer_id"] = "human:fixture-reviewer-a"  # type: ignore[index]
        with self.assertRaisesRegex(ContractError, "distinct identity"):
            ledger.append(duplicate)

        repeated_evidence = draft()
        repeated_evidence["findings"][1]["evidence_sha256"] = repeated_evidence["findings"][0]["evidence_sha256"]  # type: ignore[index]
        with self.assertRaisesRegex(ContractError, "distinct evidence"):
            ledger.append(repeated_evidence)

    def test_unanimity_mapping_tampering_and_no_overwrite_export(self) -> None:
        ledger = AppealLedger(self.ledger)
        upheld = ledger.append(
            draft(conclusions=("UPHOLD_APPEAL", "UPHOLD_APPEAL")),
            recorded_at="2026-08-07T10:00:00Z",
        )
        self.assertEqual("UPHOLD_PROCEDURALLY", upheld["outcome"])
        self.assertEqual(
            "SEPARATE_CORRECTION_OR_REMEDY_RECORD_REQUIRED",
            upheld["follow_up"],
        )

        invalid = draft(appeal_id="appeal:fixture-two", case_id="case:fixture-two")
        invalid["outcome"] = "UPHOLD_PROCEDURALLY"
        invalid["follow_up"] = "SEPARATE_CORRECTION_OR_REMEDY_RECORD_REQUIRED"
        with self.assertRaisesRegex(ContractError, "unanimous"):
            ledger.append(invalid, recorded_at="2026-08-07T10:01:00Z")

        index = self.root / "appeal-index.json"
        exported = ledger.export_public_index(index)
        self.assertEqual(1, exported["returned"])
        with self.assertRaisesRegex(ContractError, "already exists"):
            ledger.export_public_index(index)

        self.ledger.write_text(self.ledger.read_text(encoding="utf-8").replace("UPHOLD", "BROKEN"), encoding="utf-8")
        with self.assertRaises(LedgerIntegrityError):
            ledger.read()

    def test_example_is_appendable_and_synthetic_drill_detects_tampering(self) -> None:
        example = load_json_strict(Path(__file__).resolve().parents[1] / "appeal-draft.example.json")
        record = AppealLedger(self.ledger).append(example, recorded_at="2026-08-07T10:00:00Z")
        self.assertEqual("RETURN_FOR_DIAGNOSIS", record["outcome"])

        output = self.root / "synthetic"
        report = run_synthetic_drill(output)
        self.assertTrue(report["conflicted_reviewer_rejected"])
        self.assertTrue(verify_synthetic_drill(output)["valid"])
        report_file = output / "public" / "report.json"
        value = load_json_strict(report_file)
        value["split_routed_to_diagnosis"] = False
        write_json(report_file, value)
        with self.assertRaises(ContractError):
            verify_synthetic_drill(output)


if __name__ == "__main__":
    unittest.main()
