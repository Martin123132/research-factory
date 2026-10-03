from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "verify_python_lock.py"
SPEC = importlib.util.spec_from_file_location("verify_python_lock", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


class VerifyPythonLockTests(unittest.TestCase):
    def check_fixture(self, dependencies: str, lock: str) -> int:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pyproject.toml").write_text(
                f"[project]\ndependencies = [{dependencies}]\n", encoding="utf-8"
            )
            (root / "requirements.lock").write_text(lock, encoding="utf-8")
            return verifier.verify(root)

    def test_matching_pins_allow_transitive_dependencies_and_comments(self):
        self.assertEqual(
            self.check_fixture('"cryptography==50.0.2"', "# lock\ncryptography==50.0.2\ncffi==2.1.0\n"),
            1,
        )

    def test_rejects_original_stale_cryptography_lock(self):
        with self.assertRaisesRegex(ValueError, "project=50.0.2, lock=50.0.0"):
            self.check_fixture('"cryptography==50.0.2"', "cryptography==50.0.0\n")

    def test_rejects_missing_direct_dependency(self):
        with self.assertRaisesRegex(ValueError, "lock=MISSING"):
            self.check_fixture('"cryptography==50.0.2"', "cffi==2.1.0\n")

    def test_normalizes_python_package_names(self):
        self.assertEqual(self.check_fixture('"Example_Package==1.2.3"', "example-package==1.2.3\n"), 1)

    def test_rejects_duplicate_normalized_names(self):
        with self.assertRaisesRegex(ValueError, "duplicate pin"):
            self.check_fixture('"Example_Package==1.2.3"', "example-package==1.2.3\nexample.package==1.2.3\n")

    def test_rejects_unpinned_or_wildcard_requirements(self):
        for value in ("example>=1.2.3", "example==1.2.*", "-r other.txt"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "exact name==version"):
                verifier.parse_pins([value], "fixture")

    def test_rejects_empty_direct_dependencies(self):
        with self.assertRaisesRegex(ValueError, "must not be empty"):
            self.check_fixture("", "cffi==2.1.0\n")


if __name__ == "__main__":
    unittest.main()
