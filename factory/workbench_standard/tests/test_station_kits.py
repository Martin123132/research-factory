from __future__ import annotations

import copy
import hashlib
import sys
import unittest
from pathlib import Path


STANDARD_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STANDARD_ROOT))

import generate_station_kits as kits  # noqa: E402


class StationKitContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contracts = kits.build_contracts()
        cls.wb001 = cls.contracts[0]
        cls.wb002 = cls.contracts[1]
        cls.wb003 = cls.contracts[2]
        cls.wb013 = cls.contracts[12]
        cls.rh = cls.contracts[98]

    def mutated(self, contract: dict) -> dict:
        return copy.deepcopy(contract)

    def assert_rejected(self, contract: dict) -> None:
        with self.assertRaises(kits.ContractError):
            kits.validate_contract(contract)

    def test_catalogue_yields_exactly_100_honest_stages(self) -> None:
        self.assertEqual(100, len(self.contracts))
        self.assertEqual(1, sum(c["readiness"]["current_stage"] == "COMMISSIONING_READY" for c in self.contracts))
        self.assertEqual(99, sum(c["readiness"]["current_stage"] == "CONTRACT_DRAFT" for c in self.contracts))
        self.assertFalse(any(c["readiness"]["live_research_enabled"] for c in self.contracts))

    def test_rejects_missing_or_subjective_truth_condition(self) -> None:
        contract = self.mutated(self.wb002)
        contract["problem"]["structured_predicate"]["pass_rule"] = None
        self.assert_rejected(contract)

    def test_rejects_unhashed_or_candidate_controlled_verifier(self) -> None:
        contract = self.mutated(self.wb001)
        contract["problem"]["structured_predicate"]["verifier_sha256"] = None
        self.assert_rejected(contract)
        contract = self.mutated(self.wb001)
        contract["problem"]["structured_predicate"]["verifier_path_or_protocol"] = "candidate/verifier.py"
        self.assert_rejected(contract)

    def test_rejects_score_that_can_override_hard_failure(self) -> None:
        contract = self.mutated(self.wb001)
        contract["measurement"]["criteria"][0]["score_may_override_failure"] = True
        self.assert_rejected(contract)

    def test_rejects_missing_economic_formula_units_baseline_or_system_boundary(self) -> None:
        for field in ["formula", "system_boundary", "comparator", "decision_threshold"]:
            contract = self.mutated(self.wb001)
            contract["measurement"]["economic_or_physical_accounting"][field] = None
            self.assert_rejected(contract)

    def test_economic_and_slowdown_thresholds_are_explicit_and_gap_is_not_hidden(self) -> None:
        tolerance = self.wb001["measurement"]["tolerance"]
        self.assertIn("minimum-cost-gain", {rule["rule_id"] for rule in tolerance["improvement_thresholds"]})
        self.assertEqual(
            {"maximum-encode-slowdown", "maximum-decode-slowdown"},
            {rule["rule_id"] for rule in tolerance["safety_limits"]},
        )
        self.assertIn("ECONOMIC_DECISION_ENFORCEMENT_GAP", self.wb001["readiness"]["unresolved"])

    def test_rejects_nonzero_tolerance_for_exact_predicate(self) -> None:
        contract = self.mutated(self.rh)
        contract["measurement"]["tolerance"]["logical_tolerance"] = 0.02
        self.assert_rejected(contract)

    def test_rejects_relative_tolerance_without_zero_policy(self) -> None:
        contract = self.mutated(self.wb001)
        contract["measurement"]["tolerance"]["improvement_thresholds"][0]["zero_reference_policy"] = "NOT_APPLICABLE"
        self.assert_rejected(contract)

    def test_rejects_stochastic_metric_without_repetitions_seeds_and_confidence_rule(self) -> None:
        contract = self.mutated(self.wb001)
        contract["measurement"]["tolerance"]["stochastic_protocol"]["confidence_rule"] = None
        self.assert_rejected(contract)

    def test_rejects_equivalence_tolerance_reused_as_improvement_threshold(self) -> None:
        contract = self.mutated(self.wb001)
        rule = copy.deepcopy(contract["measurement"]["tolerance"]["reproduction_equivalence"][0])
        contract["measurement"]["tolerance"]["improvement_thresholds"].append(rule)
        self.assert_rejected(contract)

    def test_rejects_generic_or_unbounded_starter_pack(self) -> None:
        contract = self.mutated(self.wb003)
        contract["starter_pack"]["fixture_status"] = "KNOWN_ANSWER_READY"
        contract["starter_pack"]["command"] = "echo pass"
        contract["starter_pack"]["expected_outputs"] = ["pass"]
        self.assert_rejected(contract)

    def test_rejects_starter_pack_requiring_unsafe_trusted_execution(self) -> None:
        contract = self.mutated(self.wb003)
        contract["runner"]["arbitrary_public_code_allowed"] = True
        self.assert_rejected(contract)

    def test_rejects_self_duplicate_or_majority_vote_reproduction_policy(self) -> None:
        for field, value in [
            ("author_may_validate", True),
            ("distinct_people_required", False),
            ("majority_vote_resolves_deterministic_dispute", True),
        ]:
            contract = self.mutated(self.wb001)
            contract["reproduction"][field] = value
            self.assert_rejected(contract)

    def test_rejects_generation_from_invalid_draft(self) -> None:
        contract = self.mutated(self.wb003)
        contract["readiness"]["current_stage"] = "COMMISSIONING_READY"
        self.assert_rejected(contract)

    def test_wb002_is_adapter_bound_but_fail_closed(self) -> None:
        self.assertEqual("ADAPTER_BOUND", self.wb002["commissioning"]["profile_status"])
        self.assertEqual("DIGITAL_COMPRESSION_V1", self.wb002["commissioning"]["adapter_id"])
        self.assertEqual("KNOWN_ANSWER_READY", self.wb002["starter_pack"]["fixture_status"])
        self.assertEqual("CONTRACT_DRAFT", self.wb002["readiness"]["current_stage"])
        self.assertFalse(self.wb002["readiness"]["facets"]["frozen_public_inputs"])
        self.assertIn("ENWIK9_FACTORY_SHA256_MISSING", self.wb002["readiness"]["unresolved"])
        self.assertEqual("NOT_APPLICABLE", self.wb002["measurement"]["hidden_inputs"]["policy"])
        self.assertEqual("NOT_DEFINED", self.wb002["runner"]["isolation_status"])
        self.assertEqual("NOT_DEFINED", self.wb002["runner"]["network_policy"])

    def test_rejects_adapter_dossier_commitment_drift(self) -> None:
        contract = self.mutated(self.wb002)
        contract["commissioning"]["dossier_sha256"] = "0" * 64
        self.assert_rejected(contract)

    def test_wb002_exactness_and_result_scopes_are_separate(self) -> None:
        tolerance = self.wb002["measurement"]["tolerance"]
        self.assertEqual(0, tolerance["logical_tolerance"])
        self.assertIn(
            "Official Hutter score and practical archive utility are separate result scopes.",
            tolerance["reproduction_rules"],
        )
        self.assertFalse(self.wb002["readiness"]["promotion_claims_allowed"])

    def test_wb013_is_strictly_adapter_bound_to_symmetric_tsp(self) -> None:
        self.assertEqual("WB-013", self.wb013["workbench"]["code"])
        self.assertEqual("ADAPTER_BOUND", self.wb013["commissioning"]["profile_status"])
        self.assertEqual("DIGITAL_OPTIMIZATION_V1", self.wb013["commissioning"]["adapter_id"])
        self.assertEqual("KNOWN_ANSWER_READY", self.wb013["starter_pack"]["fixture_status"])
        self.assertEqual("CONTRACT_DRAFT", self.wb013["readiness"]["current_stage"])
        self.assertEqual(0, self.wb013["measurement"]["tolerance"]["logical_tolerance"])
        self.assertEqual("REQUIRED", self.wb013["measurement"]["hidden_inputs"]["policy"])
        self.assertEqual("UNFROZEN", self.wb013["measurement"]["public_inputs"]["status"])
        self.assertEqual("UNDEFINED", self.wb013["measurement"]["compute_budget"]["status"])
        self.assertEqual("NOT_DEFINED", self.wb013["runner"]["isolation_status"])
        self.assertEqual("NOT_DEFINED", self.wb013["runner"]["network_policy"])
        self.assertIn("FULL_TSPLIB_DISTANCE_CONFORMANCE_MISSING", self.wb013["readiness"]["unresolved"])
        self.assertFalse(self.wb013["readiness"]["promotion_claims_allowed"])

    def test_rejects_traversal_or_private_contract_paths(self) -> None:
        contract = self.mutated(self.wb002)
        contract["source"]["factory_path"] = "../private/answers"
        self.assert_rejected(contract)

    def test_rejects_missing_extra_or_tampered_kit_files(self) -> None:
        files, manifest = kits.build_kit_files(self.wb001)
        files_without_manifest = {key: value for key, value in files.items() if key != "kit-manifest.json"}
        tampered = dict(files_without_manifest)
        tampered["contract.json"] += b" "
        with self.assertRaises(kits.ContractError):
            kits.validate_kit_manifest(tampered, manifest)
        missing = dict(files_without_manifest)
        missing.pop("contract.json")
        with self.assertRaises(kits.ContractError):
            kits.validate_kit_manifest(missing, manifest)
        extra = dict(files_without_manifest)
        extra["private/answer.txt"] = b"hidden"
        with self.assertRaises(kits.ContractError):
            kits.validate_kit_manifest(extra, manifest)

    def test_same_inputs_produce_identical_kit_digest(self) -> None:
        _, first = kits.build_kit_files(self.wb001)
        _, second = kits.build_kit_files(self.wb001)
        self.assertEqual(first["kit_sha256"], second["kit_sha256"])

    def test_contract_change_invalidates_existing_kit_digest(self) -> None:
        _, first = kits.build_kit_files(self.wb002)
        changed = self.mutated(self.wb002)
        changed["problem"]["objective"] += " — successor"
        _, second = kits.build_kit_files(changed)
        self.assertNotEqual(first["contract_sha256"], second["contract_sha256"])
        self.assertNotEqual(first["kit_sha256"], second["kit_sha256"])

    def test_rejects_any_scientific_reproduction_or_promotion_credit_in_hangar_kit(self) -> None:
        files, manifest = kits.build_kit_files(self.wb001)
        manifest = copy.deepcopy(manifest)
        manifest["construction_boundary"]["scientific_evidence"] = True
        without_hash = {key: value for key, value in manifest.items() if key != "kit_sha256"}
        manifest["kit_sha256"] = hashlib.sha256(kits.canonical_bytes(without_hash)).hexdigest()
        with self.assertRaises(kits.ContractError):
            kits.validate_kit_manifest(
                {key: value for key, value in files.items() if key != "kit-manifest.json"}, manifest
            )


if __name__ == "__main__":
    unittest.main()
