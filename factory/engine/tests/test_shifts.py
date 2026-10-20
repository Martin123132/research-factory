from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import copy
from io import StringIO
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from control_plane.common import ContractError, canonical_json_bytes
from engine.cli import main
from engine.shifts import ShiftWorkflow, inventory, now, sealed, session_lock
from engine.environments import EnvironmentProfileError
from engine.fixture_packets import FixturePacketController

ROOT = Path(__file__).resolve().parents[2]


class ShiftTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.shift = self.root / "first"
        self.workflow = ShiftWorkflow(ROOT)

    def tearDown(self):
        self.temp.cleanup()

    def start(self, workbench="WB-013"):
        return self.workflow.start(output=self.shift, operator="demo:alice", workbench=workbench)

    def finish(self, outcome="PROGRESS", **kwargs):
        return self.workflow.finish(self.shift, outcome=outcome, summary="Reviewed the known fixture workflow.",
                                    next_lead="Run the same fixture in a fresh environment.", **kwargs)

    def test_discovery_and_clock_in_never_execute_or_claim_work(self):
        with patch.object(FixturePacketController, "execute", side_effect=AssertionError("must not run")):
            tasks = self.workflow.tasks()
            self.assertEqual(["WB-001", "WB-013"], [t["workbench_code"] for t in tasks["tasks"]])
            started = self.start()
            self.assertEqual("NOT_RUN", started["run_state"])
            self.assertFalse(any(started["boundary"].values()))
            self.assertEqual("OPEN", self.workflow.inspect(self.shift)["state"])

    def test_full_fixture_clock_out_copy_verify_and_resume(self):
        for workbench in ("WB-001", "WB-013"):
            with self.subTest(workbench=workbench):
                self.shift = self.root / workbench
                self.start(workbench)
                result = self.workflow.run(self.shift)
                self.assertEqual("PASSED", result["run_state"])
                first = self.finish()
                before = inventory(self.shift)
                package = self.root / (workbench + "-handover")
                self.workflow.export(self.shift, package)
                moved = self.root / (workbench + "-received")
                shutil.copytree(package, moved)
                verified = self.workflow.verify_handover(moved)
                self.assertEqual("CLOSED", verified["shift"]["state"])
                second = self.root / (workbench + "-bob")
                resumed = self.workflow.start(output=second, previous=moved, operator="demo:bob")
                self.assertEqual(1, resumed["report_count"])
                self.assertEqual("demo:alice", resumed["reports"][0]["reporter"]["actorUserId"])
                self.assertEqual("NOT_RUN", resumed["run_state"])
                last = self.workflow.finish(second, outcome="NO_GAIN", summary="No further fixture run was necessary.",
                                            next_lead="Inspect the retained first-shift evidence.")
                self.assertEqual(2, last["report_count"])
                self.assertEqual(first["reports"][0]["reportSha256"], last["reports"][1]["previousReportSha256"])
                self.assertFalse(last["reports"][1]["boundary"]["closesWorkOrder"])
                self.assertEqual(before, inventory(self.shift))
                self.workflow.export(second, self.root / (workbench + "-second-handover"))

    def test_every_operational_outcome_can_be_retained_without_running(self):
        for outcome in ("PROGRESS", "NO_GAIN", "BLOCKED", "UNRUNNABLE"):
            self.shift = self.root / outcome
            self.start()
            kwargs = {"blocker": "Local runtime unavailable."} if outcome in {"BLOCKED", "UNRUNNABLE"} else {}
            self.assertEqual(outcome, self.finish(outcome, **kwargs)["reports"][0]["outcomeClass"])

    def test_failed_run_is_retained_and_cannot_be_relabelled_passed(self):
        self.start()
        with patch.object(FixturePacketController, "execute", side_effect=EnvironmentProfileError("wrong interpreter")):
            result = self.workflow.run(self.shift)
        self.assertEqual("UNRUNNABLE", result["run_state"])
        self.assertIn("wrong interpreter", (self.shift / "run/result.json").read_text())
        with self.assertRaisesRegex(ContractError, "must be retained"):
            self.finish()
        self.finish("UNRUNNABLE", blocker="Install the frozen fixture environment.")

    def test_interruption_is_visible_no_automatic_retry_and_can_clock_out(self):
        self.start()
        with patch.object(FixturePacketController, "execute", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.workflow.run(self.shift)
        self.assertEqual("INTERRUPTED_OR_RUNNING", self.workflow.inspect(self.shift)["run_state"])
        with self.assertRaisesRegex(ContractError, "already ran"):
            self.workflow.run(self.shift)
        self.finish("UNRUNNABLE", blocker="Run was interrupted; do not overwrite partial output.")

    def test_closed_shift_cannot_rerun_reclose_or_overwrite_handover(self):
        self.start()
        self.finish()
        before = inventory(self.shift)
        with self.assertRaises(ContractError):
            self.workflow.run(self.shift)
        with self.assertRaises(ContractError):
            self.finish()
        package = self.root / "package"
        self.workflow.export(self.shift, package)
        with self.assertRaises(ContractError):
            self.workflow.export(self.shift, package)
        self.assertEqual(before, inventory(self.shift))

    def test_missing_added_and_altered_files_invalidate_closed_shift(self):
        self.start()
        self.finish()
        target = self.shift / "session.json"
        original = target.read_bytes()
        target.write_bytes(original + b" ")
        with self.assertRaisesRegex(ContractError, "artifacts changed"):
            self.workflow.inspect(self.shift)
        target.write_bytes(original)
        (self.shift / "extra.txt").write_text("extra")
        with self.assertRaisesRegex(ContractError, "unexpected"):
            self.workflow.inspect(self.shift)

    def test_unknown_boundary_duplicate_key_and_promotion_are_rejected(self):
        self.start()
        target = self.shift / "session.json"
        original = json.loads(target.read_text())
        for mutate in (
            lambda d: d["boundary"].update(eligible_for_promotion=True),
            lambda d: d.update(extra="not allowed"),
            lambda d: d["boundary"].update(scientific_evidence=0),
        ):
            data = copy.deepcopy(original)
            mutate(data)
            del data["sha256"]
            target.write_bytes(canonical_json_bytes(sealed(data)))
            with self.assertRaises(ContractError):
                self.workflow.inspect(self.shift)
        target.write_text('{"format":1,"format":2}')
        with self.assertRaisesRegex(ContractError, "duplicate"):
            self.workflow.inspect(self.shift)

    def test_start_rejects_unregistered_tasks_operator_and_existing_directory(self):
        for operator, bench in (("human:alice", "WB-013"), ("demo:a", "WB-099"), ("demo:../x", "WB-001")):
            with self.assertRaises(ContractError):
                self.workflow.start(output=self.shift, operator=operator, workbench=bench)
            self.assertFalse(self.shift.exists())
        self.start()
        with self.assertRaisesRegex(ContractError, "already exists"):
            self.start()

    def test_blocked_report_requires_reason_and_handover_requires_clock_out(self):
        self.start()
        with self.assertRaisesRegex(ContractError, "requires"):
            self.finish("BLOCKED")
        with self.assertRaisesRegex(ContractError, "clock out"):
            self.workflow.export(self.shift, self.root / "package")

    def test_future_finish_rejected_and_long_shift_can_file_recorded_finish_later(self):
        self.start()
        with self.assertRaisesRegex(ContractError, "0–24"):
            self.finish(ended_at="2099-01-01T00:00:00Z")
        with patch("engine.shifts.now", return_value="2099-01-01T00:00:00Z"):
            with self.assertRaisesRegex(ContractError, "0–24"):
                self.finish()
            self.finish(ended_at=now())

    def test_lock_excludes_another_process_without_modifying_shift(self):
        self.start()
        before = inventory(self.shift)
        with session_lock(self.shift):
            result = subprocess.run([sys.executable, str(ROOT / "enginectl.py"), "shift", "finish",
                                     "--session", str(self.shift), "--outcome", "PROGRESS", "--summary", "Cannot write while busy.",
                                     "--next-lead", "Retry when the other command exits."], capture_output=True, text=True, timeout=30)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("busy", result.stderr)
        self.assertEqual(before, inventory(self.shift))
        self.finish()

    def test_parent_link_is_rejected(self):
        real = self.root / "real"
        real.mkdir()
        link = self.root / "link"
        try:
            link.symlink_to(real, target_is_directory=True)
        except OSError:
            self.skipTest("host does not allow symlink creation")
        with self.assertRaisesRegex(ContractError, "links"):
            self.workflow.start(output=link / "shift", operator="demo:alice", workbench="WB-013")

    def test_tampered_handover_refused_without_new_session(self):
        self.start()
        self.finish()
        package = self.root / "package"
        self.workflow.export(self.shift, package)
        (package / "evidence/files/session.json").write_text("{}")
        target = self.root / "bob"
        with self.assertRaises(ContractError):
            self.workflow.start(output=target, previous=package, operator="demo:bob")
        self.assertFalse(target.exists())

    def test_cli_errors_and_json_are_useful(self):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["shift", "tasks", "--json"])
        self.assertEqual(0, code, stderr.getvalue())
        self.assertEqual(2, len(json.loads(stdout.getvalue())["tasks"]))
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["shift", "inspect", "--session", str(self.root / "missing")])
        self.assertEqual(2, code)
        self.assertIn("does not exist", stderr.getvalue())

    def test_cli_complete_journey_and_explicit_run_acknowledgement(self):
        def invoke(*args):
            stdout, stderr = StringIO(), StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = main(["shift", *args, "--json"])
            self.assertEqual(0, code, stderr.getvalue())
            return json.loads(stdout.getvalue())

        invoke("start", "--workbench", "WB-013", "--operator", "demo:cli", "--output", str(self.shift))
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            main(["shift", "run", "--session", str(self.shift)])
        self.assertEqual("PASSED", invoke("run", "--session", str(self.shift), "--acknowledge-fixture-only")["run_state"])
        invoke("finish", "--session", str(self.shift), "--outcome", "PROGRESS", "--summary", "Fixture verified through CLI.",
               "--next-lead", "Inspect the package on another checkout.")
        package = self.root / "cli-package"
        invoke("export", "--session", str(self.shift), "--output", str(package))
        self.assertEqual("CLOSED", invoke("verify", "--package", str(package))["shift"]["state"])
        next_shift = self.root / "cli-next"
        invoke("resume", "--package", str(package), "--operator", "demo:next", "--output", str(next_shift))
        self.assertEqual(1, invoke("inspect", "--session", str(next_shift))["report_count"])

    def test_changed_contract_blocks_run_and_relabelling_on_export(self):
        self.start()
        target = self.shift / "session.json"
        data = json.loads(target.read_text())
        del data["sha256"]
        data["contract_sha256"] = "0" * 64
        target.write_bytes(canonical_json_bytes(sealed(data)))
        self.assertFalse(self.workflow.inspect(self.shift)["current_contract_match"])
        with self.assertRaisesRegex(ContractError, "locked work changed"):
            self.workflow.run(self.shift)
        self.finish()
        with self.assertRaisesRegex(ContractError, "historical"):
            self.workflow.export(self.shift, self.root / "changed-package")

    def test_hard_links_and_unknown_run_files_are_rejected(self):
        import os
        self.start()
        try:
            os.link(self.shift / "session.json", self.root / "alias.json")
        except OSError:
            self.skipTest("host does not allow hard links")
        with self.assertRaisesRegex(ContractError, "hard links"):
            self.workflow.inspect(self.shift)

    def test_empty_directory_changes_are_detected(self):
        self.start()
        self.finish()
        (self.shift / "run").mkdir()
        with self.assertRaises(ContractError):
            self.workflow.inspect(self.shift)


if __name__ == "__main__":
    unittest.main()
