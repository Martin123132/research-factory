from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from control_plane.common import (
    ContractError,
    canonical_json_bytes,
    sha256_bytes,
    write_json,
)
from engine.portable import PortableEvidencePackage


FACTORY_ROOT = Path(__file__).resolve().parents[2]


class PortableEvidencePackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "evidence"
        self.source.mkdir()
        (self.source / "result.json").write_text(
            json.dumps({"measurement": 42, "status": "construction"}) + "\n",
            encoding="utf-8",
        )
        nested = self.source / "logs"
        nested.mkdir()
        (nested / "run.txt").write_text("reproducible output\n", encoding="utf-8")
        self.portable = PortableEvidencePackage(FACTORY_ROOT)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def create(self, **overrides: object) -> tuple[Path, dict[str, object]]:
        output = self.root / "portable-package"
        values: dict[str, object] = {
            "workbench": "WB-002",
            "attempt_id": "attempt:portable-test",
            "operator_id": "human:local-test",
            "operating_mode": "HANGAR_CONSTRUCTION",
            "evidence_kind": "CONSTRUCTION",
            "summary": "Record a deterministic construction measurement.",
            "commands": ["python runner.py --fixture"],
            "seeds": [],
            "stochastic": False,
            "source": self.source,
            "output": output,
        }
        values.update(overrides)
        result = self.portable.create(**values)  # type: ignore[arg-type]
        return Path(values["output"]), result  # type: ignore[arg-type]

    def test_create_and_verify_closed_portable_package(self) -> None:
        path, created = self.create()
        verified = self.portable.verify(path)
        self.assertTrue(created["created"])
        self.assertTrue(verified["valid"])
        self.assertEqual(created["package_sha256"], verified["package_sha256"])
        self.assertEqual(2, verified["files"])
        self.assertTrue(verified["current_contract_match"])
        self.assertFalse(verified["scientific_evidence"])
        self.assertFalse(verified["eligible_for_promotion"])

    def test_commissioning_requires_a_commissioning_ready_station(self) -> None:
        with self.assertRaisesRegex(ContractError, "not commissioning-ready"):
            self.create(operating_mode="SYNTHETIC_COMMISSIONING")

        path, _ = self.create(
            workbench="WB-001",
            operating_mode="SYNTHETIC_COMMISSIONING",
            output=self.root / "wb001-commissioning",
        )
        verified = self.portable.verify(path)
        self.assertEqual("SYNTHETIC_COMMISSIONING", verified["operating_mode"])
        self.assertFalse(verified["scientific_evidence"])

    def test_stochastic_package_requires_a_seed(self) -> None:
        with self.assertRaisesRegex(ContractError, "record at least one seed"):
            self.create(stochastic=True)

    def test_tampered_evidence_is_rejected(self) -> None:
        path, _ = self.create()
        (path / "evidence" / "files" / "result.json").write_text(
            "tampered\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(ContractError, "evidence file does not match"):
            self.portable.verify(path)

    def test_rehashed_envelope_cannot_invent_commissioning_readiness(self) -> None:
        path, _ = self.create()
        envelope_path = path / "package.json"
        envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
        envelope["operating_mode"] = "SYNTHETIC_COMMISSIONING"
        unsigned = {key: value for key, value in envelope.items() if key != "package_sha256"}
        envelope["package_sha256"] = sha256_bytes(canonical_json_bytes(unsigned))
        write_json(envelope_path, envelope)
        with self.assertRaisesRegex(ContractError, "commissioning for an unready contract"):
            self.portable.verify(path)

    def test_rehashed_envelope_cannot_replace_catalogue_provenance(self) -> None:
        path, _ = self.create()
        envelope_path = path / "package.json"
        envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
        envelope["provenance"]["catalogue_sha256"] = "0" * 64
        unsigned = {key: value for key, value in envelope.items() if key != "package_sha256"}
        envelope["package_sha256"] = sha256_bytes(canonical_json_bytes(unsigned))
        write_json(envelope_path, envelope)
        with self.assertRaisesRegex(ContractError, "catalogue commitment differs"):
            self.portable.verify(path)

    def test_unexpected_file_and_directory_are_rejected(self) -> None:
        path, _ = self.create()
        (path / "evidence" / "unexpected.txt").write_text("extra\n", encoding="utf-8")
        with self.assertRaisesRegex(ContractError, "evidence directory is incomplete"):
            self.portable.verify(path)

        path_two, _ = self.create(output=self.root / "portable-package-two")
        (path_two / "evidence" / "files" / "empty").mkdir()
        with self.assertRaisesRegex(ContractError, "unexpected directories"):
            self.portable.verify(path_two)

    def test_duplicate_json_key_is_rejected_before_interpretation(self) -> None:
        path, _ = self.create()
        envelope = path / "package.json"
        envelope.write_text(
            envelope.read_text(encoding="utf-8").replace(
                "{\n",
                '{\n  "schema_version": 1,\n',
                1,
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ContractError, "duplicate JSON object key"):
            self.portable.verify(path)

    def test_destination_inside_source_is_rejected(self) -> None:
        with self.assertRaisesRegex(ContractError, "outside its evidence source"):
            self.create(output=self.source / "package")

    def test_linked_source_and_package_are_rejected_when_supported(self) -> None:
        linked_source = self.root / "linked-source"
        try:
            linked_source.symlink_to(self.source, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"directory symlinks are unavailable: {exc}")

        with self.assertRaisesRegex(ContractError, "symbolic link or junction"):
            self.create(source=linked_source)

        path, _ = self.create(output=self.root / "real-package")
        linked_package = self.root / "linked-package"
        linked_package.symlink_to(path, target_is_directory=True)
        with self.assertRaisesRegex(ContractError, "symbolic link or junction"):
            self.portable.verify(linked_package)


if __name__ == "__main__":
    unittest.main()
