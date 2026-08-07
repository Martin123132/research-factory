from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from engine.cli import main


FACTORY_ROOT = Path(__file__).resolve().parents[2]
ENGINECTL = FACTORY_ROOT / "enginectl.py"
ROUND = FACTORY_ROOT / "rounds" / "WB001-PILOT-001" / "round.json"
ENTRY_GATE = FACTORY_ROOT / "control_plane" / "scripts" / "run_entry_gate.py"
ENVELOPE_POLICY = (
    FACTORY_ROOT / "control_plane" / "examples" / "wb001-synthetic-envelope-policy.json"
)


class LocalCliTests(unittest.TestCase):
    def invoke(self, argv: list[str]) -> tuple[int, str, str]:
        stdout = StringIO()
        stderr = StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            returncode = main(argv)
        return returncode, stdout.getvalue(), stderr.getvalue()

    def test_doctor_json_is_machine_readable(self) -> None:
        returncode, stdout, stderr = self.invoke(["doctor", "--json"])
        self.assertEqual(0, returncode, stderr)
        value = json.loads(stdout)
        self.assertTrue(value["engine_ready"])
        self.assertEqual(100, value["catalogue"]["stations"])
        self.assertFalse(value["provider_dependencies"]["github_required"])

    def test_list_and_inspect_are_available_without_state(self) -> None:
        returncode, stdout, stderr = self.invoke(["list", "--entry-ready", "--json"])
        self.assertEqual(0, returncode, stderr)
        self.assertEqual(3, len(json.loads(stdout)))

        returncode, stdout, stderr = self.invoke(["inspect", "13", "--json"])
        self.assertEqual(0, returncode, stderr)
        value = json.loads(stdout)
        self.assertEqual("WB-013", value["registry"]["workbench_code"])
        self.assertFalse(value["live_research_allowed"])

    def test_quality_profile_is_machine_readable_and_not_certified(self) -> None:
        returncode, stdout, stderr = self.invoke(["quality", "--json"])
        self.assertEqual(0, returncode, stderr)
        value = json.loads(stdout)
        self.assertEqual("FOUNDATION_ONLY", value["profile"])
        self.assertEqual(28, value["summary"]["controls"])
        self.assertEqual(0, value["operating_facts"]["live_research_stations"])
        self.assertFalse(any(value["certifications"].values()))

    def test_support_disclosure_commands_are_local_and_non_promotional(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            root = Path(raw_directory)
            ledger = root / "support-disclosures.jsonl"
            draft = FACTORY_ROOT / "disclosures" / "support-disclosure.example.json"

            returncode, stdout, stderr = self.invoke(
                ["support-append", "--ledger", str(ledger), "--draft", str(draft), "--json"]
            )
            self.assertEqual(0, returncode, stderr)
            appended = json.loads(stdout)
            self.assertEqual("ACTIVE", appended["status_after"])
            self.assertFalse(appended["boundary"]["scientific_gates_changed"])

            returncode, stdout, stderr = self.invoke(
                ["support-history", "--ledger", str(ledger), "--support-kind", "compute_credit", "--json"]
            )
            self.assertEqual(0, returncode, stderr)
            history = json.loads(stdout)
            self.assertEqual(1, history["returned"])
            self.assertFalse(history["ledger"]["eligible_for_promotion"])

            returncode, stdout, stderr = self.invoke(
                ["support-export", "--ledger", str(ledger), "--output", str(root / "index.json"), "--json"]
            )
            self.assertEqual(0, returncode, stderr)
            self.assertEqual(1, json.loads(stdout)["returned"])


class GovernedCliSubprocessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.ledger = self.root / "state" / "events.jsonl"
        self.evidence = self.root / "state" / "private" / "evidence"
        self.artifacts = self.root / "state" / "public" / "artifacts"
        self.private = self.root / "state" / "private" / "reruns"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_process(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            command,
            cwd=FACTORY_ROOT,
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=600,
            check=False,
        )
        self.assertEqual(
            0,
            completed.returncode,
            f"command failed: {command}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
        )
        return completed

    def ctl(self, *arguments: str) -> dict[str, object]:
        command = [
            sys.executable,
            str(ENGINECTL),
            "--ledger",
            str(self.ledger),
            "--evidence-root",
            str(self.evidence),
            "--artifact-root",
            str(self.artifacts),
            "--private-root",
            str(self.private),
            *arguments,
        ]
        return json.loads(self.run_process(command).stdout)

    def test_clean_state_can_enter_the_governed_workflow_through_enginectl(self) -> None:
        self.ctl(
            "init",
            "--admin-id",
            "human:admin",
            "--provider",
            "local-test",
            "--subject",
            "admin-subject",
            "--display-name",
            "Local Admin",
        )
        self.ctl("open-round", "--actor", "human:admin", "--config", str(ROUND))
        self.ctl(
            "check-in",
            "--operator-id",
            "human:worker",
            "--provider",
            "local-test",
            "--subject",
            "worker-subject",
            "--display-name",
            "Local Worker",
        )

        entry_path = self.root / "worker-entry.json"
        self.run_process(
            [
                sys.executable,
                str(ENTRY_GATE),
                "--operator",
                "human:worker",
                "--acknowledge-rules",
                "--output",
                str(entry_path),
            ]
        )
        self.ctl(
            "complete-entry-gate",
            "--operator",
            "human:worker",
            "--round",
            "WB001-PILOT-001",
            "--evidence",
            str(entry_path),
        )
        claim = self.ctl(
            "claim-work",
            "--operator",
            "human:worker",
            "--round",
            "WB001-PILOT-001",
            "--work-unit",
            "wu:preprocess-integers",
        )
        release_capability = "engine-cli-human-release-capability-123456"
        issued = self.ctl(
            "issue-work-envelope",
            "--actor",
            "human:admin",
            "--work-claim",
            str(claim["payload"]["work_claim_id"]),  # type: ignore[index]
            "--policy",
            str(ENVELOPE_POLICY),
            "--release-capability",
            release_capability,
        )
        envelope_id = issued["event"]["payload"]["envelope"]["envelope_id"]  # type: ignore[index]
        attempt = self.ctl(
            "start-attempt",
            "--operator",
            "human:worker",
            "--work-claim",
            str(claim["payload"]["work_claim_id"]),  # type: ignore[index]
            "--envelope",
            str(envelope_id),
            "--release-capability",
            release_capability,
            "--attempt-id",
            "attempt:cli-smoke",
        )
        self.assertEqual(
            "attempt:cli-smoke",
            attempt["payload"]["attempt_id"],  # type: ignore[index]
        )

        status = self.ctl("status", "--round", "WB001-PILOT-001", "--json")
        self.assertIn(
            "attempt:cli-smoke",
            [row["attempt_id"] for row in status["attempts"]],  # type: ignore[index]
        )
        verified = self.ctl("verify-ledger")
        self.assertGreaterEqual(verified["events"], 6)


if __name__ == "__main__":
    unittest.main()
