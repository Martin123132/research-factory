from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPOSITORY_ROOT / ".github" / "scripts" / "verify_asset_provenance.py"
SCHEMA = REPOSITORY_ROOT / ".github" / "schemas" / "asset-provenance-v1.schema.json"
SPEC = importlib.util.spec_from_file_location("verify_asset_provenance", SCRIPT)
assert SPEC and SPEC.loader
VERIFY_ASSETS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY_ASSETS)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class AssetProvenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "assets").mkdir()
        (self.root / ".github" / "schemas").mkdir(parents=True)
        shutil.copy2(SCHEMA, self.root / ".github" / "schemas" / SCHEMA.name)
        self.first = self.root / "assets" / "first.png"
        self.second = self.root / "assets" / "second.svg"
        self.first.write_bytes(b"synthetic-png-fixture")
        self.second.write_bytes(b"<svg>synthetic fixture</svg>")
        self.reset_document()
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        self.write_ledger()
        self.track("assets/first.png", "assets/second.svg")

    def reset_document(self) -> None:
        self.document = {
            "$schema": ".github/schemas/asset-provenance-v1.schema.json",
            "schema_version": 1,
            "generated_on": "2026-08-04",
            "hash_algorithm": "SHA-256",
            "assets": [
                {
                    "paths": ["assets/first.png", "assets/second.svg"],
                    "origin": "Factory-created synthetic test assets",
                    "licence": "CC-BY-4.0",
                    "sha256": {
                        "assets/first.png": digest(self.first.read_bytes()),
                        "assets/second.svg": digest(self.second.read_bytes()),
                    },
                }
            ],
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_ledger(self) -> None:
        (self.root / "ASSET_PROVENANCE.json").write_text(
            json.dumps(self.document, indent=2) + "\n",
            encoding="utf-8",
        )

    def track(self, *paths: str) -> None:
        subprocess.run(["git", "add", "--", *paths], cwd=self.root, check=True)

    def verify(self, tracked_files: dict[str, str] | None = None) -> int:
        return VERIFY_ASSETS.verify(root=self.root, tracked_files=tracked_files)

    def test_valid_ledger_passes(self) -> None:
        self.assertEqual(self.verify(), 2)

    def test_tampered_hash_fails(self) -> None:
        self.document["assets"][0]["sha256"]["assets/first.png"] = "0" * 64
        self.write_ledger()
        with self.assertRaisesRegex(ValueError, "asset hash mismatch"):
            self.verify()

    def test_missing_media_entry_fails(self) -> None:
        group = self.document["assets"][0]
        group["paths"].remove("assets/second.svg")
        del group["sha256"]["assets/second.svg"]
        self.write_ledger()
        with self.assertRaisesRegex(ValueError, "missing=.*assets/second.svg"):
            self.verify()

    def test_duplicate_path_across_groups_fails(self) -> None:
        duplicate = copy.deepcopy(self.document["assets"][0])
        duplicate["paths"] = ["assets/first.png"]
        duplicate["sha256"] = {
            "assets/first.png": digest(self.first.read_bytes()),
        }
        self.document["assets"].append(duplicate)
        self.write_ledger()
        with self.assertRaisesRegex(ValueError, "declared more than once"):
            self.verify()

    def test_unsafe_and_noncanonical_paths_fail_schema(self) -> None:
        unsafe_paths = [
            "../outside.png",
            "/absolute.png",
            "C:/escape.png",
            "assets\\escape.png",
            "./assets/first.png",
            "assets//first.png",
        ]
        for unsafe in unsafe_paths:
            with self.subTest(path=unsafe):
                group = self.document["assets"][0]
                group["paths"] = [unsafe]
                group["sha256"] = {unsafe: "0" * 64}
                self.write_ledger()
                with self.assertRaisesRegex(ValueError, "schema violation"):
                    self.verify()
                self.reset_document()

    def test_safe_path_rejects_windows_drives_and_aliases(self) -> None:
        unsafe_paths = [
            "C:/escape.png",
            "C:\\escape.png",
            "../escape.png",
            "./assets/first.png",
            "assets//first.png",
        ]
        for unsafe in unsafe_paths:
            with self.subTest(path=unsafe):
                with self.assertRaisesRegex(ValueError, "asset path"):
                    VERIFY_ASSETS.safe_path(unsafe)

    def test_symlink_git_mode_fails(self) -> None:
        link = self.root / "assets" / "linked.png"
        link.write_bytes(b"assets/first.png")
        self.document["assets"][0]["paths"].append("assets/linked.png")
        self.document["assets"][0]["sha256"]["assets/linked.png"] = digest(link.read_bytes())
        self.write_ledger()
        tracked = {
            "assets/first.png": "100644",
            "assets/second.svg": "100644",
            "assets/linked.png": "120000",
        }
        with self.assertRaisesRegex(ValueError, "unsafe Git mode 120000"):
            self.verify(tracked)

    def test_newly_tracked_media_fails(self) -> None:
        extra = self.root / "assets" / "undeclared.gif"
        extra.write_bytes(b"synthetic-gif-fixture")
        self.track("assets/undeclared.gif")
        with self.assertRaisesRegex(ValueError, "missing=.*assets/undeclared.gif"):
            self.verify()

    def test_unknown_group_field_fails_closed_schema(self) -> None:
        self.document["assets"][0]["comment"] = "schema drift"
        self.write_ledger()
        with self.assertRaisesRegex(ValueError, "schema violation"):
            self.verify()

    def test_duplicate_json_object_key_fails(self) -> None:
        (self.root / "ASSET_PROVENANCE.json").write_text(
            '{"schema_version":1,"schema_version":1}',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "duplicate JSON object key"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
