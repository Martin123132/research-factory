from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPOSITORY_ROOT / ".github" / "scripts" / "verify_public_readiness.py"
SPEC = importlib.util.spec_from_file_location("verify_public_readiness", SCRIPT)
assert SPEC and SPEC.loader
VERIFY_PUBLIC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY_PUBLIC)


class PublicReadinessTests(unittest.TestCase):
    def test_current_repository_passes(self) -> None:
        self.assertGreater(VERIFY_PUBLIC.verify(), 2_000)

    def test_candidate_intake_rejects_artifact_and_reproduction_form(self) -> None:
        with self.assertRaisesRegex(ValueError, "candidate intake"):
            VERIFY_PUBLIC.verify_candidate_boundary(
                {
                    "candidate_artifacts/README.md",
                    "candidate_artifacts/result.json",
                }
            )
        with self.assertRaisesRegex(ValueError, "reproduction intake"):
            VERIFY_PUBLIC.verify_candidate_boundary(
                {
                    "candidate_artifacts/README.md",
                    ".github/ISSUE_TEMPLATE/reproduction.yaml",
                }
            )

    def test_private_and_credential_shaped_paths_fail(self) -> None:
        unsafe_paths = [
            "factory/private/holdout.json",
            "config/.env.production",
            "keys/operator.pem",
            "deployment/credentials.json",
        ]
        for unsafe in unsafe_paths:
            with self.subTest(path=unsafe):
                with self.assertRaisesRegex(ValueError, "credential-shaped"):
                    VERIFY_PUBLIC.verify_no_private_material({unsafe})

    def test_sanitized_environment_example_is_allowed(self) -> None:
        VERIFY_PUBLIC.verify_no_private_material({"factory/.env.example"})

    def test_gitleaks_baseline_rejects_wildcard(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".gitleaksignore").write_text("generic-api-key\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "two reviewed fixture fingerprints"):
                VERIFY_PUBLIC.verify_gitleaks_baseline(root)


if __name__ == "__main__":
    unittest.main()
