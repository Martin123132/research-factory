from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from control_plane.common import ContractError, LedgerIntegrityError, write_json
from disclosures.ledger import SupportDisclosureLedger, load_json_strict
from disclosures.synthetic_drill import run_synthetic_drill, verify_synthetic_drill


def draft(action: str = "DECLARE", event_id: str = "support-event:fixture-declare") -> dict[str, object]:
    return {
        "event_id": event_id,
        "disclosure_id": "support:fixture",
        "action": action,
        "scope": {"scope_type": "FACTORY_PROJECT", "scope_id": "research-factory"},
        "declarant": {"operator_id": "human:fixture-discloser", "display_name": "Fixture Discloser", "identity_assurance": "SELF_ASSERTED_LOCAL", "identity_warning": "IDENTITY_RECORD_IS_NOT_PROOF_OF_AUTHORITY"},
        "disclosure": {"supporter_name": "Fixture Funder", "supporter_kind": "NONPROFIT", "support_kind": "COMPUTE_CREDIT", "relationship": "Synthetic test support for construction verification.", "materiality": "MATERIAL", "value_visibility": "NOT_QUANTIFIABLE", "public_description": "No scientific gate may depend on this synthetic support fixture.", "received_or_expected": "EXPECTED"},
        "public_summary": "Fixture support disclosure with a declared non-influence boundary.",
    }


class SupportDisclosureLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / "support.jsonl"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_declare_end_history_and_export(self) -> None:
        ledger = SupportDisclosureLedger(self.path)
        declared = ledger.append(draft(), recorded_at="2026-08-07T10:00:00Z")
        ended = ledger.append(draft("END", "support-event:fixture-end"), recorded_at="2026-08-07T11:00:00Z")
        self.assertEqual("ACTIVE", declared["status_after"])
        self.assertEqual("ENDED", ended["status_after"])
        self.assertEqual(declared["record_sha256"], ended["previous_disclosure_event_sha256"])
        verified = ledger.verify()
        self.assertEqual(0, verified["active_disclosures"])
        self.assertFalse(verified["eligible_for_promotion"])
        with self.assertRaisesRegex(ContractError, "unknown material-support kind"):
            ledger.history(support_kind="NOT_A_KIND")
        output = self.root / "index.json"
        self.assertEqual(2, ledger.export_public_index(output)["returned"])
        with self.assertRaisesRegex(ContractError, "already exists"):
            ledger.export_public_index(output)

    def test_wrong_lifecycle_boundary_and_tampering_fail_closed(self) -> None:
        ledger = SupportDisclosureLedger(self.path)
        with self.assertRaisesRegex(ContractError, "must use DECLARE"):
            ledger.append(draft("END", "support-event:wrong"))
        record = ledger.append(draft())
        with self.assertRaisesRegex(ContractError, "cannot use DECLARE"):
            ledger.append(draft("DECLARE", "support-event:again"))
        with self.assertRaisesRegex(ContractError, "must change"):
            ledger.append(draft("AMEND", "support-event:empty-amend"))
        altered = copy.deepcopy(record)
        altered["boundary"]["scientific_gates_changed"] = True  # type: ignore[index]
        with self.assertRaises(ContractError):
            SupportDisclosureLedger(self.root / "other.jsonl")._validate_record(altered)
        self.path.write_text(self.path.read_text(encoding="utf-8").replace("Fixture", "Broken"), encoding="utf-8")
        with self.assertRaises(LedgerIntegrityError):
            ledger.read()

    def test_example_and_synthetic_drill(self) -> None:
        example = load_json_strict(Path(__file__).resolve().parents[1] / "support-disclosure.example.json")
        self.assertEqual("ACTIVE", SupportDisclosureLedger(self.path).append(example)["status_after"])
        output = self.root / "synthetic"
        self.assertTrue(run_synthetic_drill(output)["ended_disclosure"])
        self.assertTrue(verify_synthetic_drill(output)["valid"])
        report = output / "public" / "report.json"
        value = load_json_strict(report)
        value["ended_disclosure"] = False
        write_json(report, value)
        with self.assertRaises(ContractError):
            verify_synthetic_drill(output)


if __name__ == "__main__":
    unittest.main()
