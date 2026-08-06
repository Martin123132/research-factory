from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest


QUALITY_DIR = Path(__file__).resolve().parents[1]
ROOT = QUALITY_DIR.parents[1]
sys.path.insert(0, str(QUALITY_DIR))

from verify_quality import (  # noqa: E402
    ASSESSMENT,
    STANDARD,
    load_json_strict,
    verify,
)


class FactoryQualityVerifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assessment = load_json_strict(ASSESSMENT)
        self.standard = load_json_strict(STANDARD)
        assert isinstance(self.assessment, dict)
        assert isinstance(self.standard, dict)

    @staticmethod
    def write_json(directory: Path, name: str, value: object) -> Path:
        path = directory / name
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    def verify_assessment(self, directory: Path, value: object) -> dict[str, object]:
        assessment = self.write_json(directory, "assessment.json", value)
        return verify(assessment_path=assessment, require_hangar_summary=False)

    def test_repository_quality_profile_verifies_without_certification(self) -> None:
        value = verify()
        self.assertEqual("FOUNDATION_ONLY", value["profile"])
        self.assertEqual(
            {"controls": 28, "meets": 19, "partial": 7, "blocked": 2},
            value["summary"],
        )
        self.assertFalse(any(value["certifications"].values()))
        self.assertEqual(0, value["operating_facts"]["live_research_stations"])

    def test_duplicate_json_keys_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            path = Path(raw_directory) / "duplicate.json"
            path.write_text('{"assessment_version": 1, "assessment_version": 1}\n')
            with self.assertRaisesRegex(ValueError, "duplicate JSON object key"):
                load_json_strict(path)

    def test_control_order_cannot_hide_a_missing_gate(self) -> None:
        value = copy.deepcopy(self.assessment)
        value["results"][0], value["results"][1] = value["results"][1], value["results"][0]
        with tempfile.TemporaryDirectory() as raw_directory:
            with self.assertRaisesRegex(ValueError, "exactly match standard order"):
                self.verify_assessment(Path(raw_directory), value)

    def test_changed_standard_bytes_invalidate_the_assessment(self) -> None:
        value = copy.deepcopy(self.standard)
        value["domains"][0]["controls"][0]["requirement"] += " The changed rule is material."
        with tempfile.TemporaryDirectory() as raw_directory:
            standard = self.write_json(Path(raw_directory), "standard.json", value)
            with self.assertRaisesRegex(ValueError, "standard SHA-256"):
                verify(standard_path=standard, require_hangar_summary=False)

    def test_changed_evidence_invalidates_the_assessment(self) -> None:
        value = copy.deepcopy(self.assessment)
        value["results"][0]["evidence"][0]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw_directory:
            with self.assertRaisesRegex(ValueError, "evidence SHA-256 differs"):
                self.verify_assessment(Path(raw_directory), value)

    def test_meets_cannot_claim_less_than_required_evidence(self) -> None:
        value = copy.deepcopy(self.assessment)
        value["results"][0]["evidence_level"] = "DECLARED"
        with tempfile.TemporaryDirectory() as raw_directory:
            with self.assertRaisesRegex(ValueError, "below its minimum evidence level"):
                self.verify_assessment(Path(raw_directory), value)

    def test_summary_is_derived_not_decorative(self) -> None:
        value = copy.deepcopy(self.assessment)
        value["summary"]["meets"] = 28
        value["summary"]["partial"] = 0
        value["summary"]["blocked"] = 0
        with tempfile.TemporaryDirectory() as raw_directory:
            with self.assertRaisesRegex(ValueError, "summary is not derived"):
                self.verify_assessment(Path(raw_directory), value)

    def test_strong_domains_cannot_compensate_for_open_gates(self) -> None:
        value = copy.deepcopy(self.assessment)
        value["profile"] = "OPERATIONALLY_CONFORMANT"
        value["certifications"]["operationally_conformant"] = True
        with tempfile.TemporaryDirectory() as raw_directory:
            with self.assertRaisesRegex(ValueError, "incomplete quality profile"):
                self.verify_assessment(Path(raw_directory), value)

    def test_scientific_certification_requires_live_two_human_evidence(self) -> None:
        value = copy.deepcopy(self.assessment)
        for result in value["results"]:
            result["outcome"] = "MEETS"
            result["evidence_level"] = "INDEPENDENTLY_AUDITED"
            result["limitation"] = None
            if not result["evidence"]:
                result["evidence"] = [copy.deepcopy(value["results"][0]["evidence"][0])]
        value["summary"] = {"controls": 28, "meets": 28, "partial": 0, "blocked": 0}
        value["profile"] = "SCIENTIFICALLY_DEMONSTRATED"
        value["certifications"]["operationally_conformant"] = True
        value["certifications"]["scientifically_demonstrated"] = True
        with tempfile.TemporaryDirectory() as raw_directory:
            with self.assertRaisesRegex(ValueError, "live two-human operating evidence"):
                self.verify_assessment(Path(raw_directory), value)


if __name__ == "__main__":
    unittest.main()
