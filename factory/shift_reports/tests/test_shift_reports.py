from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SHIFT_REPORTS_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = SHIFT_REPORTS_ROOT.parents[1]
VALIDATOR_PATH = SHIFT_REPORTS_ROOT / "validate_shift_reports.py"
SPEC = importlib.util.spec_from_file_location("validate_shift_reports", VALIDATOR_PATH)
assert SPEC and SPEC.loader
VALIDATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATE)


class ShiftReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.validator = VALIDATE.load_validator()
        cls.paths = sorted((SHIFT_REPORTS_ROOT / "examples").glob("*.json"))
        cls.reports = [VALIDATE.load_json_strict(path) for path in cls.paths]

    def cloned(self) -> list[dict]:
        return copy.deepcopy(self.reports)

    def test_all_four_outcomes_form_one_valid_chain(self) -> None:
        self.assertEqual(VALIDATE.verify_reports(self.cloned()), 4)
        self.assertEqual(
            {report["outcomeClass"] for report in self.reports},
            {"PROGRESS", "NO_GAIN", "BLOCKED", "UNRUNNABLE"},
        )

    def test_every_report_has_zero_scientific_standing(self) -> None:
        for report in self.reports:
            with self.subTest(report=report["reportId"]):
                self.assertEqual(
                    report["boundary"],
                    {
                        "scope": "HANGAR_OPERATIONS_ONLY",
                        "scientificEvidence": False,
                        "countsAsIndependentReproduction": False,
                        "eligibleForPromotion": False,
                        "closesWorkOrder": False,
                        "operationalRecordOnly": True,
                    },
                )

    def test_scientific_standing_cannot_be_set_true(self) -> None:
        report = self.cloned()[0]
        report["boundary"]["scientificEvidence"] = True
        report["reportSha256"] = VALIDATE.canonical_report_hash(report)
        with self.assertRaisesRegex(ValueError, "schema violation"):
            VALIDATE.verify_report(report, validator=self.validator)

    def test_live_research_and_validator_verdict_fields_are_rejected(self) -> None:
        for forbidden in ("liveResearch", "validatorVerdict"):
            with self.subTest(field=forbidden):
                report = self.cloned()[0]
                report[forbidden] = "PASS"
                report["reportSha256"] = VALIDATE.canonical_report_hash(report)
                with self.assertRaisesRegex(ValueError, "schema violation"):
                    VALIDATE.verify_report(report, validator=self.validator)

    def test_inline_artifact_content_is_rejected(self) -> None:
        report = self.cloned()[0]
        report["artifactReferences"][0]["inlineContent"] = "hidden bytes"
        report["reportSha256"] = VALIDATE.canonical_report_hash(report)
        with self.assertRaisesRegex(ValueError, "schema violation"):
            VALIDATE.verify_report(report, validator=self.validator)

    def test_repository_path_traversal_is_rejected(self) -> None:
        report = self.cloned()[0]
        report["artifactReferences"][0]["locator"] = "../hidden-answer.json"
        report["reportSha256"] = VALIDATE.canonical_report_hash(report)
        with self.assertRaisesRegex(ValueError, "schema violation"):
            VALIDATE.verify_report(report, validator=self.validator)

    def test_private_or_hidden_artifact_paths_are_rejected(self) -> None:
        for locator in ("factory/private/result.json", "factory/HIDDEN/answer.json", ".env"):
            with self.subTest(locator=locator):
                report = self.cloned()[0]
                report["artifactReferences"][0]["locator"] = locator
                report["reportSha256"] = VALIDATE.canonical_report_hash(report)
                with self.assertRaisesRegex(ValueError, "not public provenance"):
                    VALIDATE.verify_report(report, validator=self.validator)

    def test_artifact_hash_is_verified(self) -> None:
        report = self.cloned()[0]
        report["artifactReferences"][0]["sha256"] = "0" * 64
        report["reportSha256"] = VALIDATE.canonical_report_hash(report)
        with self.assertRaisesRegex(ValueError, "artifact SHA-256 mismatch"):
            VALIDATE.verify_report(report, validator=self.validator)

    def test_mutating_a_report_breaks_its_self_hash(self) -> None:
        reports = self.cloned()
        reports[0]["observations"][0] = "Rewritten history"
        with self.assertRaisesRegex(ValueError, "reportSha256 mismatch"):
            VALIDATE.verify_reports(reports)

    def test_shift_duration_must_match_the_timestamps(self) -> None:
        report = self.cloned()[0]
        report["shift"]["durationMinutes"] = 239
        report["reportSha256"] = VALIDATE.canonical_report_hash(report)
        with self.assertRaisesRegex(ValueError, "durationMinutes mismatch"):
            VALIDATE.verify_report(report, validator=self.validator)

    def test_work_order_revision_cannot_move_backwards_in_a_chain(self) -> None:
        reports = self.cloned()
        reports[3]["workOrderSnapshot"]["revision"] = 1
        reports[3]["reportSha256"] = VALIDATE.canonical_report_hash(reports[3])
        with self.assertRaisesRegex(ValueError, "revision moved backwards"):
            VALIDATE.verify_reports(reports)

    def test_rehashing_an_earlier_mutation_breaks_the_next_link(self) -> None:
        reports = self.cloned()
        reports[0]["observations"][0] = "A correction cannot replace old bytes"
        reports[0]["reportSha256"] = VALIDATE.canonical_report_hash(reports[0])
        with self.assertRaisesRegex(ValueError, "previous-report hash mismatch"):
            VALIDATE.verify_reports(reports)

    def test_blocked_and_unrunnable_require_a_blocker(self) -> None:
        for index in (2, 3):
            with self.subTest(outcome=self.reports[index]["outcomeClass"]):
                report = self.cloned()[index]
                report["blockers"] = []
                report["reportSha256"] = VALIDATE.canonical_report_hash(report)
                with self.assertRaisesRegex(ValueError, "schema violation"):
                    VALIDATE.verify_report(report, validator=self.validator)

    def test_duplicate_json_keys_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "duplicate.json"
            path.write_text('{"schemaVersion":1,"schemaVersion":1}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                VALIDATE.load_json_strict(path)

    def test_hangar_public_schema_is_byte_identical(self) -> None:
        public_schema = REPOSITORY_ROOT / "factory" / "hangar" / "public" / "shift-report-v1.schema.json"
        self.assertEqual(
            (SHIFT_REPORTS_ROOT / "shift-report-v1.schema.json").read_bytes(),
            public_schema.read_bytes(),
        )


if __name__ == "__main__":
    unittest.main()
