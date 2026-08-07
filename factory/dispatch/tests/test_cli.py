from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from control_plane.common import write_json
from dispatch.gate import PROFILE_CONTAINER, PROFILE_DRY_RUN, PROFILE_FROZEN_LOCAL
from dispatch.synthetic_drill import _budget


FACTORY_ROOT = Path(__file__).resolve().parents[2]
ENGINECTL = FACTORY_ROOT / "enginectl.py"


class DispatchCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def ctl(self, *arguments: str, expected_status: int = 0) -> dict[str, object]:
        completed = subprocess.run(
            [sys.executable, str(ENGINECTL), *arguments, "--json"],
            cwd=FACTORY_ROOT,
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
            check=False,
        )
        self.assertEqual(
            expected_status,
            completed.returncode,
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
        )
        return json.loads(completed.stdout)

    def test_profiles_budget_preflight_and_ticket_verification(self) -> None:
        profiles = self.ctl("dispatch-profiles")
        self.assertEqual(3, len(profiles["profiles"]))
        self.assertTrue(profiles["process_execution_profile_can_be_authorized"])
        self.assertTrue(profiles["runtime_host_attestation_required"])
        self.assertIn(PROFILE_CONTAINER, [profile["profile_id"] for profile in profiles["profiles"]])  # type: ignore[index]

        budget_path = self.root / "dry-budget.json"
        write_json(budget_path, _budget("DRY_RUN_ONLY"))
        budget = self.ctl("dispatch-budget-verify", "--budget", str(budget_path))
        self.assertEqual("DRY_RUN_ONLY", budget["requested_execution_mode"])

        ticket_path = self.root / "dry-ticket.json"
        ticket = self.ctl(
            "dispatch-preflight",
            "--budget",
            str(budget_path),
            "--profile",
            PROFILE_DRY_RUN,
            "--output",
            str(ticket_path),
            "--ticket-id",
            "dispatch-ticket:cli-dry-run",
            "--created-at",
            "2026-08-07T11:00:00Z",
            "--require-authorized",
        )
        self.assertTrue(ticket["authorized"])
        verified = self.ctl(
            "dispatch-ticket-verify",
            "--budget",
            str(budget_path),
            "--ticket",
            str(ticket_path),
        )
        self.assertEqual(ticket["ticket_sha256"], verified["ticket_sha256"])

    def test_require_authorized_returns_nonzero_for_incomplete_runner(self) -> None:
        budget_path = self.root / "process-budget.json"
        ticket_path = self.root / "rejection.json"
        write_json(budget_path, _budget("PROCESS_EXECUTION"))
        ticket = self.ctl(
            "dispatch-preflight",
            "--budget",
            str(budget_path),
            "--profile",
            PROFILE_FROZEN_LOCAL,
            "--output",
            str(ticket_path),
            "--ticket-id",
            "dispatch-ticket:cli-local-rejection",
            "--created-at",
            "2026-08-07T11:00:00Z",
            "--require-authorized",
            expected_status=3,
        )
        self.assertFalse(ticket["authorized"])
        self.assertEqual("REJECTED", ticket["authorization_scope"])
        self.assertTrue(ticket_path.is_file())


if __name__ == "__main__":
    unittest.main()
