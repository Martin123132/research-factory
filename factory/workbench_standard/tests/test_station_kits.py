from __future__ import annotations

import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


STANDARD_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = STANDARD_ROOT.parents[1]
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

    def test_submission_contract_requires_accountability_and_rights_declaration(self) -> None:
        sections = set(self.wb001["submission"]["required_sections"])
        self.assertIn("accountable_human", sections)
        self.assertIn("rights_and_ip", sections)
        self.assertIn("contribution_ledger", sections)
        self.assertNotIn("human_owner", sections)
        self.assertEqual(
            "schemas/rights-and-ip-v1.schema.json",
            self.wb001["submission"]["rights_declaration_schema_path"],
        )
        self.assertEqual(
            "schemas/contribution-ledger-v1.schema.json",
            self.wb001["submission"]["contribution_ledger_schema_path"],
        )
        contract = self.mutated(self.wb001)
        contract["submission"]["required_sections"].remove("rights_and_ip")
        self.assert_rejected(contract)

    def test_rights_schema_rejects_untouched_scaffold_and_fake_legal_clearance(self) -> None:
        schema = json.loads(kits.RIGHTS_SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        files, _ = kits.build_kit_files(self.wb001)
        template = json.loads(files["submission-template.json"].decode("utf-8"))
        self.assertIn("accountable_human", template)
        self.assertNotIn("human_owner", template)
        self.assertTrue(list(validator.iter_errors(template["rights_and_ip"])))
        rights_scaffold = json.loads(files["rights-and-ip-template.json"].decode("utf-8"))
        self.assertTrue(list(validator.iter_errors(rights_scaffold)))
        valid = json.loads(
            (
                REPOSITORY_ROOT
                / "factory/workbenches/wb002_large_text_archive_compression/examples/zlib_reference/submission.json"
            ).read_text(encoding="utf-8")
        )["rights_and_ip"]
        self.assertFalse(list(validator.iter_errors(valid)))
        invalid = copy.deepcopy(valid)
        invalid["freedom_to_operate"] = "CLEARED"
        self.assertTrue(list(validator.iter_errors(invalid)))

    def test_credit_schema_records_roles_without_assigning_prizes_or_inventorship(self) -> None:
        schema = json.loads(kits.CREDIT_SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        files, _ = kits.build_kit_files(self.wb001)
        scaffold = json.loads(files["contribution-ledger-template.json"].decode("utf-8"))
        self.assertTrue(list(validator.iter_errors(scaffold)))
        valid = json.loads(
            (
                REPOSITORY_ROOT
                / "factory/workbenches/wb002_large_text_archive_compression/examples/zlib_reference/submission.json"
            ).read_text(encoding="utf-8")
        )["contribution_ledger"]
        self.assertFalse(list(validator.iter_errors(valid)))
        automatic_cut = copy.deepcopy(valid)
        automatic_cut["factory_automatic_share"] = "TEN_PERCENT"
        self.assertTrue(list(validator.iter_errors(automatic_cut)))
        invented_legal_status = copy.deepcopy(valid)
        invented_legal_status["entries"][0]["inventorship_review"] = "INVENTOR"
        self.assertTrue(list(validator.iter_errors(invented_legal_status)))

    def test_embedded_lane_rights_schemas_match_governed_schema(self) -> None:
        governed = json.loads(kits.RIGHTS_SCHEMA_PATH.read_text(encoding="utf-8"))
        governed_core = {
            key: governed[key]
            for key in ["type", "additionalProperties", "required", "properties"]
        }
        for name in [
            "digital_compression_submission.schema.json",
            "digital_optimization_submission.schema.json",
        ]:
            lane = json.loads((STANDARD_ROOT / "commissioning" / name).read_text(encoding="utf-8"))
            self.assertEqual(governed_core, lane["$defs"]["rightsAndIp"])

    def test_embedded_lane_credit_schemas_match_governed_schema(self) -> None:
        governed = json.loads(kits.CREDIT_SCHEMA_PATH.read_text(encoding="utf-8"))
        governed_core = {
            key: governed[key]
            for key in ["type", "additionalProperties", "required", "properties"]
        }
        for name in [
            "digital_compression_submission.schema.json",
            "digital_optimization_submission.schema.json",
        ]:
            lane = json.loads((STANDARD_ROOT / "commissioning" / name).read_text(encoding="utf-8"))
            self.assertEqual(governed_core, lane["$defs"]["contributionLedger"])

    def test_kit_and_generator_identity_bind_rights_policy_assets(self) -> None:
        files, _ = kits.build_kit_files(self.wb001)
        self.assertIn("schemas/rights-and-ip-v1.schema.json", files)
        self.assertIn("schemas/contribution-ledger-v1.schema.json", files)
        negative = json.loads(files["negative-result-template.json"].decode("utf-8"))
        dispute = json.loads(files["dispute-template.json"].decode("utf-8"))
        for template in [negative, dispute]:
            self.assertIn("rights_and_ip_declaration_path", template)
            self.assertIn("contribution_ledger_path", template)
        self.assertIn(kits.RIGHTS_SCHEMA_PATH, kits.GENERATOR_SOURCE_PATHS)
        self.assertIn(kits.CREDIT_SCHEMA_PATH, kits.GENERATOR_SOURCE_PATHS)
        for template_name in kits.SHARED_TEMPLATE_NAMES:
            self.assertIn(kits.TEMPLATES_ROOT / template_name, kits.GENERATOR_SOURCE_PATHS)

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
