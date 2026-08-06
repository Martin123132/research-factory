from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from commissioning.synthetic_shift import (
    REPORT_SCHEMA_PATH,
    run_synthetic_dispute_shift,
    verify_synthetic_dispute_shift,
)
from control_plane import ContractError
from control_plane.common import canonical_json_bytes, sha256_bytes


class SyntheticDisputeShiftTests(unittest.TestCase):
    def test_report_schema_is_valid_draft_2020_12(self) -> None:
        Draft202012Validator.check_schema(
            json.loads(REPORT_SCHEMA_PATH.read_text(encoding="utf-8"))
        )

    def test_complete_shift_retains_a_split_and_passes_public_audit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "synthetic-shift"
            report = run_synthetic_dispute_shift(output)
            stored = json.loads((output / "public" / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report, stored)
            unsigned = {key: value for key, value in report.items() if key != "report_sha256"}
            self.assertEqual(report["report_sha256"], sha256_bytes(canonical_json_bytes(unsigned)))
            self.assertEqual(
                report["gate_sequence"],
                ["TIEBREAK_DIAGNOSTIC_REQUIRED", "DISPUTED_REVIEW_REQUIRED"],
            )
            self.assertFalse(report["identities"]["distinct_humans_proven"])
            self.assertFalse(report["execution"]["promotion_eligible"])
            self.assertTrue(report["audit"]["valid"])
            self.assertTrue(all(report["checks"].values()))

            public_ledger = (output / "public" / "events.jsonl").read_text(encoding="utf-8")
            self.assertNotIn('"candidate_metrics"', public_ledger)
            self.assertNotIn('"exact_output_fingerprint_sha256"', public_ledger)
            self.assertNotIn('"salt"', public_ledger)
            exported = {
                path.relative_to(output / "public" / "exported-candidate").as_posix()
                for path in (output / "public" / "exported-candidate").rglob("*")
                if path.is_file()
            }
            self.assertEqual(exported, {"candidate.py", "submission.json"})
            self.assertTrue((output / "private" / "sealed-reruns").is_dir())
            verification = verify_synthetic_dispute_shift(output)
            self.assertTrue(verification["valid"])
            self.assertEqual(verification["events"], 25)

            stored["final_status"] = "RERUN_CONFIRMED_AWAITING_HOLDOUT"
            (output / "public" / "report.json").write_text(
                json.dumps(stored, indent=2) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(ContractError):
                verify_synthetic_dispute_shift(output)

    def test_existing_output_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "already-there"
            output.mkdir()
            marker = output / "keep.txt"
            marker.write_text("keep\n", encoding="utf-8")
            with self.assertRaisesRegex(ContractError, "output already exists"):
                run_synthetic_dispute_shift(output)
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep\n")


if __name__ == "__main__":
    unittest.main()
