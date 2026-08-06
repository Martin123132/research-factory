from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


RELEASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RELEASE_DIR))

from build_offline_release import build_release  # noqa: E402
from verify_offline_release import verify_release  # noqa: E402


def run(command: list[str], *, cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True, capture_output=True)


class OfflineReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repository = self.root / "repository"
        self.repository.mkdir()
        (self.repository / "factory").mkdir()
        (self.repository / "README.md").write_text("# Fixture factory\n", encoding="utf-8")
        (self.repository / "factory" / "ENGINE.md").write_text(
            "# Fixture engine\n", encoding="utf-8"
        )
        run(["git", "init", "--initial-branch=main"], cwd=self.repository)
        run(["git", "config", "user.name", "Release test"], cwd=self.repository)
        run(["git", "config", "user.email", "release-test@example.invalid"], cwd=self.repository)
        run(["git", "add", "README.md", "factory/ENGINE.md"], cwd=self.repository)
        run(["git", "commit", "-m", "Fixture"], cwd=self.repository)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_build_and_verify_round_trip(self) -> None:
        output = self.root / "release"
        manifest = build_release(self.repository, output)
        document = verify_release(output)

        self.assertEqual(output / "offline-release-manifest-v1.json", manifest)
        self.assertEqual("Research Factory", document["project"])
        self.assertEqual(2, len(document["artifacts"]))

    def test_changed_artifact_is_rejected(self) -> None:
        output = self.root / "release"
        build_release(self.repository, output)
        source = next(output.glob("research-factory-source-*.tar"))
        with source.open("ab") as stream:
            stream.write(b"tamper")

        with self.assertRaisesRegex(ValueError, "artifact size differs"):
            verify_release(output)

    def test_extra_release_file_is_rejected(self) -> None:
        output = self.root / "release"
        build_release(self.repository, output)
        (output / "unlisted.txt").write_text("not in manifest\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "file set differs"):
            verify_release(output)

    def test_dirty_checkout_is_rejected(self) -> None:
        (self.repository / "untracked.txt").write_text("local only\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "require a clean checkout"):
            build_release(self.repository, self.root / "release")


if __name__ == "__main__":
    unittest.main()
