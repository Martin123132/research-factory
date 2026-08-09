from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


WORKBENCH_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKBENCH_ROOT / "runner"))
sys.path.insert(0, str(WORKBENCH_ROOT / "scripts"))

from build_public_corpus import build_corpus  # noqa: E402
from baseline_frontier import build_pack, verify_pack_hash  # noqa: E402
from common import (  # noqa: E402
    ContractError,
    canonical_json_bytes,
    load_json,
    load_workbench_config,
    sha256_bytes,
    sha256_file,
    verify_commitment_hash,
    write_json,
)
from compare_frontier import compare_to_frontier  # noqa: E402
from candidate_package import (  # noqa: E402
    build_candidate_package,
    rehearse_clean_clone,
    verify_candidate_package,
)
from evaluate_isolated import build_docker_command, load_policy, verify_image_lock  # noqa: E402
from evaluate_local import evaluate_submission  # noqa: E402
from signing import sign_document, verify_signed_document  # noqa: E402
from verify_reproductions import verify_reproductions  # noqa: E402

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

BASELINE_SUBMISSION = (
    WORKBENCH_ROOT / "baselines" / "reference_pack" / "zlib-6.submission.json"
)
EXAMPLE_SUBMISSION = WORKBENCH_ROOT / "examples" / "zlib_level9" / "submission.json"
QUALIFICATION_RESULT = WORKBENCH_ROOT / "results" / "qualification_v0_2" / "candidate_result.json"
QUALIFICATION_COMPARISON = WORKBENCH_ROOT / "results" / "qualification_v0_2" / "frontier_comparison.json"


class WorkbenchTests(unittest.TestCase):
    def make_tiny_corpus(self, root: Path) -> Path:
        corpus = root / "public"
        corpus.mkdir(parents=True)
        payloads = {
            "repetitive.txt": b"factory evidence line\n" * 4096,
            "mixed.bin": bytes(range(256)) * 256,
        }
        files = []
        for name, payload in payloads.items():
            path = corpus / name
            path.write_bytes(payload)
            files.append(
                {
                    "path": name,
                    "class": "test",
                    "bytes": len(payload),
                    "sha256": sha256_bytes(payload),
                }
            )
        core = {"schema_version": 1, "profile": "tiny-test", "root": "public", "files": files}
        manifest = {**core, "corpus_sha256": sha256_bytes(canonical_json_bytes(core))}
        manifest_path = root / "manifest.json"
        write_json(manifest_path, manifest)
        return manifest_path

    def rehash(self, result: dict, operator_id: str) -> dict:
        clone = copy.deepcopy(result)
        clone["operator_id"] = operator_id
        clone.pop("result_sha256", None)
        clone["result_sha256"] = sha256_bytes(canonical_json_bytes(clone))
        return clone

    def rehash_mutated(self, result: dict) -> dict:
        clone = copy.deepcopy(result)
        clone.pop("result_sha256", None)
        clone["result_sha256"] = sha256_bytes(canonical_json_bytes(clone))
        return clone

    def comparison_for(self, result: dict, status: str = "VALID_NO_CONFIRMED_GAIN") -> dict:
        unsigned = {
            "schema_version": 2,
            "decision_type": "wb001_frontier_comparison",
            "status": status,
            "candidate_artifact_sha256": result["candidate_artifact_sha256"],
            "candidate_result_sha256": result["result_sha256"],
        }
        return {**unsigned, "decision_sha256": sha256_bytes(canonical_json_bytes(unsigned))}

    def test_public_corpus_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = build_corpus(root / "a" / "public", root / "a" / "manifest.json")
            second = build_corpus(root / "b" / "public", root / "b" / "manifest.json")
            self.assertEqual(first["corpus_sha256"], second["corpus_sha256"])
            self.assertEqual(first["files"], second["files"])

    def test_reference_candidate_passes_exact_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = self.make_tiny_corpus(Path(temporary))
            result = evaluate_submission(
                BASELINE_SUBMISSION,
                "demo:test-baseline",
                manifest_path=manifest,
            )
            self.assertTrue(result["hard_gate_pass"])
            self.assertEqual(result["aggregate"]["files"], 2)
            self.assertTrue(all(row["round_trip_pass"] for row in result["files"]))
            self.assertEqual(result["measurement_contract"]["scope"], "whole-corpus process per operation")
            self.assertEqual(len(result["aggregate"]["encode_samples_ns"]), 3)

    def test_broken_candidate_fails_exact_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = self.make_tiny_corpus(Path(temporary))
            result = evaluate_submission(
                WORKBENCH_ROOT / "tests" / "fixtures" / "broken_submission.json",
                "demo:test-broken",
                manifest_path=manifest,
            )
            self.assertFalse(result["hard_gate_pass"])
            self.assertGreater(len(result["failures"]), 0)

    def test_identical_result_is_valid_but_not_an_improvement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = self.make_tiny_corpus(Path(temporary))
            result = evaluate_submission(
                BASELINE_SUBMISSION,
                "demo:test-baseline",
                manifest_path=manifest,
            )
            definition = {
                "schema_version": 1,
                "pack_id": "single-reference-test",
                "timing_grade": "advisory-local",
                "promotable": False,
                "profiles": [{"id": "zlib-6"}],
            }
            pack = build_pack(definition, {"zlib-6": result})
            decision = compare_to_frontier(pack, result, load_workbench_config())
            self.assertEqual(decision["status"], "VALID_NO_CONFIRMED_GAIN")

    def test_reproduction_gate_rejects_one_person_twice(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = self.make_tiny_corpus(Path(temporary))
            result = evaluate_submission(
                BASELINE_SUBMISSION,
                "demo:author",
                manifest_path=manifest,
            )
            comparison = self.comparison_for(result)
            replica = self.rehash(result, "demo:validator-a")
            with self.assertRaises(ContractError):
                verify_reproductions(
                    result,
                    [replica, replica],
                    comparison,
                    load_workbench_config(),
                    allow_demo_identities=True,
                )

    def test_reproduction_gate_accepts_two_other_people(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = self.make_tiny_corpus(Path(temporary))
            claim = evaluate_submission(
                BASELINE_SUBMISSION,
                "demo:author",
                manifest_path=manifest,
            )
            comparison = self.comparison_for(claim)
            replica_a = self.rehash(claim, "demo:validator-a")
            replica_b = self.rehash(claim, "demo:validator-b")

            decision = verify_reproductions(
                claim,
                [replica_a, replica_b],
                comparison,
                load_workbench_config(),
                allow_demo_identities=True,
            )

            self.assertEqual(decision["status"], "RERUN_CONFIRMED_NO_GAIN")
            self.assertEqual(
                decision["operator_ids"],
                ["demo:author", "demo:validator-a", "demo:validator-b"],
            )

    def test_reproduction_gate_rejects_tampered_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = self.make_tiny_corpus(Path(temporary))
            claim = evaluate_submission(
                BASELINE_SUBMISSION,
                "demo:author",
                manifest_path=manifest,
            )
            replica_a = self.rehash(claim, "demo:validator-a")
            replica_b = self.rehash(claim, "demo:validator-b")
            comparison = self.comparison_for(claim)
            comparison["status"] = "PUBLIC_SIZE_CANDIDATE"

            with self.assertRaises(ContractError):
                verify_reproductions(
                    claim,
                    [replica_a, replica_b],
                    comparison,
                    load_workbench_config(),
                    allow_demo_identities=True,
                )

    def test_advisory_timing_cannot_create_a_frontier_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = self.make_tiny_corpus(Path(temporary))
            zlib_one = evaluate_submission(
                WORKBENCH_ROOT / "baselines" / "reference_pack" / "zlib-1.submission.json",
                "demo:zlib-one",
                manifest_path=manifest,
            )
            zlib_six = evaluate_submission(
                BASELINE_SUBMISSION,
                "demo:zlib-six",
                manifest_path=manifest,
            )
            definition = {
                "schema_version": 1,
                "pack_id": "test-reference-pack",
                "timing_grade": "advisory-local",
                "promotable": False,
                "profiles": [{"id": "zlib-1"}, {"id": "zlib-6"}],
            }
            pack = build_pack(definition, {"zlib-1": zlib_one, "zlib-6": zlib_six})
            candidate = copy.deepcopy(zlib_six)
            candidate["operator_id"] = "demo:noisy-candidate"
            candidate["aggregate"]["encode_wall_ns"] = 1
            candidate["aggregate"]["decode_wall_ns"] = 1
            candidate["aggregate"]["peak_rss_bytes"] = 1
            candidate = self.rehash_mutated(candidate)

            decision = compare_to_frontier(pack, candidate, load_workbench_config())

            self.assertEqual(decision["status"], "VALID_NO_CONFIRMED_GAIN")
            self.assertFalse(decision["timing_claim_accepted"])

    def test_baseline_pack_hash_rejects_tampering(self) -> None:
        unsigned = {
            "schema_version": 1,
            "pack_type": "wb001_baseline_frontier",
            "frontier_profile_ids": ["baseline"],
        }
        pack = {**unsigned, "pack_sha256": sha256_bytes(canonical_json_bytes(unsigned))}
        verify_pack_hash(pack)
        pack["frontier_profile_ids"] = []
        with self.assertRaises(ContractError):
            verify_pack_hash(pack)

    def test_docker_command_contains_required_isolation_controls(self) -> None:
        policy = load_policy(WORKBENCH_ROOT / "isolation" / "docker_policy.toml")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("candidate", "corpus", "work"):
                (root / name).mkdir()
            command = build_docker_command(
                policy=policy,
                image_id="sha256:" + "a" * 64,
                container_name="wb001-test",
                session_label="test",
                candidate_root=root / "candidate",
                corpus_root=root / "corpus",
                work_root=root / "work",
                candidate_command=["python", "candidate.py", "metadata"],
                include_data_mounts=True,
            )
        joined = " ".join(command)
        self.assertIn("--network none", joined)
        self.assertIn("--read-only", command)
        self.assertIn("--cap-drop ALL", joined)
        self.assertIn("no-new-privileges=true", command)
        self.assertIn("seccomp=builtin", command)
        self.assertIn("--user 65532:65532", joined)
        self.assertIn("--pids-limit 64", joined)
        self.assertNotIn("--privileged", command)

    def test_image_lock_matches_policy_and_build_inputs(self) -> None:
        verify_image_lock(
            load_json(WORKBENCH_ROOT / "isolation" / "image.lock.json"),
            WORKBENCH_ROOT / "isolation" / "docker_policy.toml",
        )

    def test_holdout_commitment_rejects_tampering(self) -> None:
        commitment = load_json(WORKBENCH_ROOT / "data" / "holdout_commitment.json")
        verify_commitment_hash(commitment)
        commitment["total_bytes"] += 1
        with self.assertRaises(ContractError):
            verify_commitment_hash(commitment)

    def test_ed25519_signature_rejects_tampering(self) -> None:
        private_key = Ed25519PrivateKey.generate()
        document = sign_document({"verdict": "NO_GAIN", "run": "test"}, private_key)
        verify_signed_document(document, private_key.public_key())
        document["verdict"] = "PASS"
        with self.assertRaises(ContractError):
            verify_signed_document(document, private_key.public_key())

    def test_all_json_schemas_parse(self) -> None:
        schemas = list((WORKBENCH_ROOT / "schemas").glob("*.json"))
        self.assertGreaterEqual(len(schemas), 8)
        for schema in schemas:
            self.assertIsInstance(json.loads(schema.read_text(encoding="utf-8")), dict)

    def build_candidate_package(self, root: Path) -> Path:
        output = root / "candidate-package"
        build_candidate_package(
            submission_path=EXAMPLE_SUBMISSION,
            result_path=QUALIFICATION_RESULT,
            comparison_path=QUALIFICATION_COMPARISON,
            output=output,
        )
        return output

    def test_candidate_package_is_closed_and_handoff_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            package = self.build_candidate_package(Path(temporary))
            verified = verify_candidate_package(package)
            handoff = load_json(package / "handoff.json")

            self.assertTrue(verified["valid"])
            self.assertEqual(
                "BLOCKED_AWAITING_TWO_OTHER_HUMAN_RERUNS",
                verified["handoff_state"],
            )
            self.assertFalse(handoff["admission"]["may_contact_evaluator"])
            self.assertFalse(verified["scientific_evidence"])
            self.assertFalse(verified["counts_as_independent_reproduction"])

    def test_candidate_package_rejects_tampered_candidate_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            package = self.build_candidate_package(Path(temporary))
            candidate = package / "artifact" / "candidate.py"
            candidate.write_text(candidate.read_text(encoding="utf-8") + "# tampered\n", encoding="utf-8")

            with self.assertRaisesRegex(ContractError, "payload file does not match"):
                verify_candidate_package(package)

    def test_candidate_package_rejects_rehashed_handoff_that_grants_access(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            package = self.build_candidate_package(Path(temporary))
            package_path = package / "package.json"
            handoff_path = package / "handoff.json"
            package_document = load_json(package_path)
            handoff = load_json(handoff_path)
            handoff["admission"]["may_contact_evaluator"] = True
            handoff_unsigned = {key: value for key, value in handoff.items() if key != "handoff_sha256"}
            handoff["handoff_sha256"] = sha256_bytes(canonical_json_bytes(handoff_unsigned))
            write_json(handoff_path, handoff)

            handoff_record = next(
                row for row in package_document["payload"]["files"] if row["path"] == "handoff.json"
            )
            handoff_record["bytes"] = handoff_path.stat().st_size
            handoff_record["sha256"] = sha256_file(handoff_path)
            package_document["payload"]["total_bytes"] = sum(
                row["bytes"] for row in package_document["payload"]["files"]
            )
            payload_core = {
                "schema_version": 1,
                "files": sorted(package_document["payload"]["files"], key=lambda row: row["path"]),
            }
            package_document["payload"]["payload_sha256"] = sha256_bytes(
                canonical_json_bytes(payload_core)
            )
            package_unsigned = {
                key: value for key, value in package_document.items() if key != "package_sha256"
            }
            package_document["package_sha256"] = sha256_bytes(canonical_json_bytes(package_unsigned))
            write_json(package_path, package_document)

            with self.assertRaisesRegex(ContractError, "validation failed|incorrectly grants evaluator access"):
                verify_candidate_package(package)

    def test_clean_clone_rehearsal_is_limited_to_demo_reference_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = self.build_candidate_package(root)
            receipt = rehearse_clean_clone(
                package_root=package,
                operator_id="demo:clean-clone",
                output=root / "rehearsal-receipt.json",
            )

            self.assertTrue(all(receipt["exact_comparisons"].values()))
            self.assertFalse(receipt["construction_boundary"]["scientific_evidence"])
            with self.assertRaisesRegex(ContractError, "demo: operator identity"):
                rehearse_clean_clone(
                    package_root=package,
                    operator_id="human:pretend-validator",
                    output=root / "not-written.json",
                )


if __name__ == "__main__":
    unittest.main()
