from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


STANDARD_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = STANDARD_ROOT.parents[1]
RUNNER_ROOT = STANDARD_ROOT / "commissioning" / "runner"
sys.path.insert(0, str(STANDARD_ROOT))
sys.path.insert(0, str(RUNNER_ROOT))

import generate_station_kits as kits  # noqa: E402


EVALUATOR_PATH = RUNNER_ROOT / "evaluate_optimization_trusted.py"
SPEC = importlib.util.spec_from_file_location("evaluate_optimization_trusted", EVALUATOR_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot import optimisation evaluator")
evaluator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluator)

WB013 = REPOSITORY_ROOT / "factory" / "workbenches" / "wb013_travelling_salesperson_route_kernel"
SUBMISSION_SCHEMA = STANDARD_ROOT / "commissioning" / "digital_optimization_submission.schema.json"


class DigitalOptimizationLaneTests(unittest.TestCase):
    def load_submission_contract(self) -> tuple[dict, dict]:
        schema = json.loads(SUBMISSION_SCHEMA.read_text(encoding="utf-8"))
        submission = json.loads(
            (WB013 / "examples" / "reference_solver" / "submission.json").read_text(
                encoding="utf-8"
            )
        )
        return schema, submission

    def test_locked_fixture_reproduces_exact_stable_evidence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wb013-test-") as temporary:
            output = Path(temporary) / "result.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(WB013 / "scripts" / "run_entry_gate.py"),
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
            self.assertEqual(33, result["metrics"]["route_length"])
            self.assertEqual(0, result["metrics"]["optimality_gap_fraction"])
            self.assertTrue(all(result["hard_gates"].values()))
            self.assertFalse(result["credit_boundary"]["scientific_evidence"])
            self.assertFalse(result["credit_boundary"]["official_tsplib_score"])
            self.assertFalse(result["credit_boundary"]["optimum_claim_verified"])
            unsigned = copy.deepcopy(result)
            claimed = unsigned.pop("result_sha256")
            self.assertEqual(claimed, evaluator.sha256_bytes(evaluator.canonical_bytes(unsigned)))

    def test_symmetric_tour_rotations_and_reversals_are_equivalent(self) -> None:
        expected = [1, 2, 3, 4, 5]
        self.assertEqual(expected, evaluator.canonical_tour([3, 4, 5, 1, 2], 5))
        self.assertEqual(expected, evaluator.canonical_tour([1, 5, 4, 3, 2], 5))

    def test_duplicate_missing_and_candidate_reported_scores_fail_closed(self) -> None:
        with self.assertRaises(evaluator.EvaluationError):
            evaluator.canonical_tour([1, 2, 2, 4], 4)
        with tempfile.TemporaryDirectory(prefix="wb013-output-") as temporary:
            output = Path(temporary) / "tour.json"
            output.write_text('{"tour":[1,2,3,4],"length":1}\n', encoding="utf-8")
            with self.assertRaises(evaluator.EvaluationError):
                evaluator.load_candidate_tour(output, 4)

    def test_asymmetric_matrix_is_rejected_by_symmetric_plugin(self) -> None:
        fixture = """NAME: bad\nTYPE: TSP\nDIMENSION: 3\nEDGE_WEIGHT_TYPE: EXPLICIT\nEDGE_WEIGHT_FORMAT: FULL_MATRIX\nEDGE_WEIGHT_SECTION\n0 1 2\n9 0 3\n2 3 0\nEOF\n"""
        with tempfile.TemporaryDirectory(prefix="wb013-instance-") as temporary:
            path = Path(temporary) / "bad.tsp"
            path.write_text(fixture, encoding="utf-8")
            with self.assertRaises(evaluator.EvaluationError):
                evaluator.parse_explicit_symmetric_tsp(path)

    def test_entry_schema_requires_accountable_human_and_honest_rights_status(self) -> None:
        schema, submission = self.load_submission_contract()
        validator = Draft202012Validator(schema)
        self.assertFalse(list(validator.iter_errors(submission)))
        legacy = copy.deepcopy(submission)
        legacy["human_owner"] = legacy.pop("accountable_human")
        self.assertTrue(list(validator.iter_errors(legacy)))
        false_clearance = copy.deepcopy(submission)
        false_clearance["rights_and_ip"]["freedom_to_operate"] = "CLEARED"
        self.assertTrue(list(validator.iter_errors(false_clearance)))

    def test_generator_identity_binds_optimization_sources(self) -> None:
        for path in [
            STANDARD_ROOT / "commissioning" / "digital_optimization.py",
            STANDARD_ROOT / "commissioning" / "digital-optimization-override-v1.schema.json",
            EVALUATOR_PATH,
        ]:
            self.assertIn(path, kits.GENERATOR_SOURCE_PATHS)


if __name__ == "__main__":
    unittest.main()
