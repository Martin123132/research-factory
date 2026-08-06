from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest


REFERENCE_DIR = Path(__file__).resolve().parents[1]
ROOT = REFERENCE_DIR.parents[1]
sys.path.insert(0, str(REFERENCE_DIR))

from verify_reference_provenance import (  # noqa: E402
    CATALOGUE,
    MANIFEST,
    MANIFESTS,
    SCHEMA,
    load_json_strict,
    verify,
)


class ReferenceProvenanceVerifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = load_json_strict(MANIFEST)
        self.catalogue = load_json_strict(CATALOGUE)
        assert isinstance(self.manifest, dict)
        assert isinstance(self.catalogue, dict)

    @staticmethod
    def write_json(directory: Path, name: str, value: object) -> Path:
        path = directory / name
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    def verify_manifest(
        self,
        directory: Path,
        manifest: object,
        catalogue: object | None = None,
    ) -> int:
        manifest_path = self.write_json(directory, "manifest.json", manifest)
        catalogue_path = CATALOGUE
        if catalogue is not None:
            catalogue_path = self.write_json(directory, "catalogue.json", catalogue)
        return verify(
            root=ROOT,
            manifest_path=manifest_path,
            schema_path=SCHEMA,
            catalogue_path=catalogue_path,
            expected_numbers=tuple(range(1, 11)),
        )

    def test_repository_manifests_verify(self) -> None:
        self.assertEqual(40, verify())

    def test_second_repository_manifest_verifies(self) -> None:
        self.assertEqual(
            10,
            verify(
                manifest_path=MANIFESTS[1][0],
                expected_numbers=MANIFESTS[1][1],
            ),
        )

    def test_third_repository_manifest_verifies(self) -> None:
        self.assertEqual(
            10,
            verify(
                manifest_path=MANIFESTS[2][0],
                expected_numbers=MANIFESTS[2][1],
            ),
        )

    def test_fourth_repository_manifest_verifies(self) -> None:
        self.assertEqual(
            10,
            verify(
                manifest_path=MANIFESTS[3][0],
                expected_numbers=MANIFESTS[3][1],
            ),
        )

    def test_station_ids_must_match_catalogue_scope_and_order(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["stations"][0], manifest["stations"][1] = (
            manifest["stations"][1],
            manifest["stations"][0],
        )
        with tempfile.TemporaryDirectory() as raw_directory:
            with self.assertRaisesRegex(ValueError, "station IDs must be exactly"):
                self.verify_manifest(Path(raw_directory), manifest)

    def test_station_fields_must_match_canonical_catalogue(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["stations"][0]["catalogue_title"] = "Drifted title"
        with tempfile.TemporaryDirectory() as raw_directory:
            with self.assertRaisesRegex(ValueError, "catalogue_title diverges"):
                self.verify_manifest(Path(raw_directory), manifest)

    def test_manifest_id_range_must_match_scope(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["manifest_id"] = "WB011-WB020-2026-08-06"
        with tempfile.TemporaryDirectory() as raw_directory:
            with self.assertRaisesRegex(ValueError, "manifest ID range must match"):
                self.verify_manifest(Path(raw_directory), manifest)

    def test_retrieved_response_requires_exact_byte_hash(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["stations"][0]["retrievals"][0]["response_sha256"] = None
        with tempfile.TemporaryDirectory() as raw_directory:
            with self.assertRaisesRegex(ValueError, "lacks an exact-byte SHA-256"):
                self.verify_manifest(Path(raw_directory), manifest)

    def test_failed_retrieval_cannot_claim_response_bytes(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        failed = manifest["stations"][1]["retrievals"][0]
        failed["response_size_bytes"] = 12
        failed["response_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw_directory:
            with self.assertRaisesRegex(ValueError, "must not claim unverified response bytes"):
                self.verify_manifest(Path(raw_directory), manifest)

    def test_terms_url_requires_retrieval_or_failure_record(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["stations"][5]["retrievals"] = [manifest["stations"][5]["retrievals"][0]]
        with tempfile.TemporaryDirectory() as raw_directory:
            with self.assertRaisesRegex(ValueError, "terms URL lacks a retrieval or failure record"):
                self.verify_manifest(Path(raw_directory), manifest)

    def test_composite_catalogue_reference_requires_each_component_in_order(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        catalogue = copy.deepcopy(self.catalogue)
        first_url = manifest["stations"][0]["catalogue_reference_url"]
        second_url = "https://example.test/second-official-reference"
        composite = f"{first_url} | {second_url}"
        catalogue["workbenches"][0]["reference_url"] = composite
        manifest["stations"][0]["catalogue_reference_url"] = composite
        second_retrieval = copy.deepcopy(manifest["stations"][0]["retrievals"][0])
        second_retrieval["requested_url"] = second_url
        second_retrieval["final_url"] = second_url
        manifest["stations"][0]["retrievals"].insert(1, second_retrieval)

        with tempfile.TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            catalogue_path = self.write_json(directory, "catalogue.json", catalogue)
            manifest["catalogue_sha256"] = hashlib.sha256(catalogue_path.read_bytes()).hexdigest()
            manifest_path = self.write_json(directory, "manifest.json", manifest)
            self.assertEqual(
                10,
                verify(
                    root=ROOT,
                    manifest_path=manifest_path,
                    schema_path=SCHEMA,
                    catalogue_path=catalogue_path,
                    expected_numbers=tuple(range(1, 11)),
                ),
            )

            manifest["stations"][0]["retrievals"].pop(1)
            manifest_path = self.write_json(directory, "missing-component.json", manifest)
            with self.assertRaisesRegex(ValueError, "must exactly match"):
                verify(
                    root=ROOT,
                    manifest_path=manifest_path,
                    schema_path=SCHEMA,
                    catalogue_path=catalogue_path,
                    expected_numbers=tuple(range(1, 11)),
                )

    def test_catalogue_drift_is_rejected_even_with_updated_catalogue_hash(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        catalogue = copy.deepcopy(self.catalogue)
        catalogue["workbenches"][0]["workbench"] = "Changed canonical title"
        with tempfile.TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            catalogue_path = self.write_json(directory, "catalogue.json", catalogue)
            manifest["catalogue_sha256"] = hashlib.sha256(catalogue_path.read_bytes()).hexdigest()
            manifest_path = self.write_json(directory, "manifest.json", manifest)
            with self.assertRaisesRegex(ValueError, "catalogue_title diverges"):
                verify(
                    root=ROOT,
                    manifest_path=manifest_path,
                    schema_path=SCHEMA,
                    catalogue_path=catalogue_path,
                    expected_numbers=tuple(range(1, 11)),
                )

    def test_duplicate_json_keys_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            duplicate = Path(raw_directory) / "duplicate.json"
            duplicate.write_text('{"schema_version": 1, "schema_version": 1}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate JSON object key"):
                load_json_strict(duplicate)


if __name__ == "__main__":
    unittest.main()
