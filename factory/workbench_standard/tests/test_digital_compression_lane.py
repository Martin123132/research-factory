from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


STANDARD_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = STANDARD_ROOT.parents[1]
sys.path.insert(0, str(STANDARD_ROOT))

import generate_station_kits as kits  # noqa: E402


WB002 = REPOSITORY_ROOT / "factory" / "workbenches" / "wb002_large_text_archive_compression"
SUBMISSION_SCHEMA = STANDARD_ROOT / "commissioning" / "digital_compression_submission.schema.json"


class DigitalCompressionLaneTests(unittest.TestCase):
    def test_locked_fixture_reproduces_stable_evidence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wb002-test-") as temporary:
            output = Path(temporary) / "result.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(WB002 / "scripts" / "run_entry_gate.py"),
                    "--fixture",
                    "--output",
                    str(output),
                ],
                cwd=REPOSITORY_ROOT,
                text=True,
                capture_output=True,
                timeout=30,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(result["hard_gates"]["exact_round_trip"])
            self.assertTrue(result["hard_gates"]["deterministic_archive"])
            self.assertFalse(result["credit_boundary"]["scientific_evidence"])
            self.assertFalse(result["credit_boundary"]["official_hutter_score"])

    def test_entry_schema_rejects_unimplemented_official_packaging_branches(self) -> None:
        schema = json.loads(SUBMISSION_SCHEMA.read_text(encoding="utf-8"))
        submission = json.loads(
            (WB002 / "examples" / "zlib_reference" / "submission.json").read_text(encoding="utf-8")
        )
        submission["packaging"]["mode"] = "SEPARATE_PROGRAMS"
        self.assertTrue(list(Draft202012Validator(schema).iter_errors(submission)))

    def test_generator_identity_binds_adapter_sources(self) -> None:
        self.assertIn(
            STANDARD_ROOT / "commissioning" / "digital_compression.py",
            kits.GENERATOR_SOURCE_PATHS,
        )
        self.assertNotEqual(
            kits.generator_source_digest(),
            kits.sha256_bytes(Path(kits.__file__).read_bytes()),
        )


if __name__ == "__main__":
    unittest.main()
