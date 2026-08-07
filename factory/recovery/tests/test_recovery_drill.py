from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from control_plane.common import ContractError, write_json
from recovery.drill import run_key_person_recovery_drill, verify_key_person_recovery_drill
from release.build_offline_release import build_release


FACTORY_ROOT = Path(__file__).resolve().parents[2]


def run(command: list[str], *, cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True, encoding="utf-8")


class KeyPersonRecoveryDrillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repository = self.root / "repository"
        self.repository.mkdir()
        (self.repository / "factory").mkdir()
        (self.repository / "README.md").write_text("# Fixture factory\n", encoding="utf-8")
        (self.repository / "OFFLINE_RECOVERY.md").write_text("# Fixture recovery\n", encoding="utf-8")
        (self.repository / "factory" / "ENGINE.md").write_text("# Fixture engine\n", encoding="utf-8")
        run(["git", "init", "--initial-branch=main"], cwd=self.repository)
        run(["git", "config", "user.name", "Recovery test"], cwd=self.repository)
        run(["git", "config", "user.email", "recovery-test@example.invalid"], cwd=self.repository)
        run(["git", "add", "README.md", "OFFLINE_RECOVERY.md", "factory/ENGINE.md"], cwd=self.repository)
        run(["git", "commit", "-m", "Fixture"], cwd=self.repository)
        self.release = self.root / "offline-release"
        build_release(self.repository, self.release)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_drill(self) -> Path:
        output = self.root / "recovery-drill"
        report = run_key_person_recovery_drill(
            self.release,
            output,
            operator_id="human:fixture-second-maintainer",
            display_name="Fixture Second Maintainer",
            recovery_id="recovery:fixture-001",
            recorded_at="2026-08-07T17:00:00Z",
        )
        self.assertFalse(report["boundary"]["resilience_04_satisfied"])
        self.assertFalse(report["declared_conditions"]["operator_identity_proven"])
        return output

    def test_runs_and_verifies_without_claiming_human_independence(self) -> None:
        output = self.run_drill()
        verified = verify_key_person_recovery_drill(self.release, output)
        self.assertTrue(verified["valid"])
        self.assertFalse(verified["scientific_evidence"])
        self.assertFalse(verified["resilience_04_satisfied"])
        self.assertEqual({"key-person-recovery-report.json"}, {path.name for path in (output / "public").iterdir()})

    def test_tampering_and_overwrite_fail_closed(self) -> None:
        output = self.run_drill()
        with self.assertRaisesRegex(ContractError, "already exists"):
            run_key_person_recovery_drill(
                self.release,
                output,
                operator_id="human:fixture-second-maintainer",
                display_name="Fixture Second Maintainer",
            )
        report_path = output / "public" / "key-person-recovery-report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["boundary"]["resilience_04_satisfied"] = True
        write_json(report_path, report)
        with self.assertRaises(ContractError):
            verify_key_person_recovery_drill(self.release, output)

    def test_bad_operator_fails_before_recovery(self) -> None:
        with self.assertRaisesRegex(ContractError, "operator_id"):
            run_key_person_recovery_drill(
                self.release,
                self.root / "bad-operator",
                operator_id="?",
                display_name="Fixture Second Maintainer",
            )

    def test_module_commands_create_and_verify_the_report(self) -> None:
        output = self.root / "module-recovery-drill"
        created = subprocess.run(
            [
                sys.executable,
                "-m",
                "recovery.run_key_person_recovery_drill",
                "--release",
                str(self.release),
                "--output",
                str(output),
                "--operator-id",
                "human:module-second-maintainer",
                "--display-name",
                "Module Second Maintainer",
                "--recovery-id",
                "recovery:module-001",
                "--recorded-at",
                "2026-08-07T17:30:00Z",
            ],
            cwd=FACTORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertFalse(json.loads(created.stdout)["boundary"]["resilience_04_satisfied"])
        verified = subprocess.run(
            [
                sys.executable,
                "-m",
                "recovery.verify_key_person_recovery_drill",
                "--release",
                str(self.release),
                str(output),
            ],
            cwd=FACTORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertTrue(json.loads(verified.stdout)["valid"])


if __name__ == "__main__":
    unittest.main()
