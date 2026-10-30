from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from control_plane import cli as frozen_cli
from control_plane.common import ContractError
from control_plane.workflow import _validate_round_document
from engine.cli import main
from engine.environments import LEGACY_PROFILE, RESEARCH_PROFILE, RESEARCH_ROUND, check_runtime
from engine.research_runtime import prepare_governed
from engine.shifts import ShiftWorkflow, inventory, sealed

ROOT = Path(__file__).resolve().parents[2]


class ResearchSuccessorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ledger = self.root / "events.jsonl"
        self.global_args = [
            "--ledger", str(self.ledger),
            "--evidence-root", str(self.root / "evidence"),
            "--artifact-root", str(self.root / "artifacts"),
            "--private-root", str(self.root / "private"),
        ]

    def invoke(self, arguments, *, frozen=False):
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            if frozen:
                return frozen_cli.main(self.global_args + arguments)
            # Profile enforcement is tested separately; these checks must also
            # run under the maintenance interpreter, which cannot execute research.
            with patch("engine.cli.require_runtime"):
                return main(self.global_args + arguments)

    def test_successor_passes_original_contract_validator_without_old_round_changes(self):
        old = ROOT / "rounds/WB001-PILOT-001/round.json"
        new = ROOT / f"rounds/{RESEARCH_ROUND}/round.json"
        before = old.read_bytes()
        doc = json.loads(new.read_text())
        _validate_round_document(doc, ROOT)
        self.assertEqual(RESEARCH_ROUND, doc["round_id"])
        self.assertNotEqual(json.loads(before)["round_sha256"], doc["round_sha256"])
        self.assertEqual(before, old.read_bytes())

    def test_old_round_cannot_be_opened_under_replacement_and_writes_nothing(self):
        result = self.invoke(["open-round", "--actor", "human:admin",
                              "--config", str(ROOT / "rounds/WB001-PILOT-001/round.json")])
        self.assertEqual(2, result)
        self.assertEqual([], list(self.root.iterdir()))

    def test_historical_ledger_is_readable_but_indirect_mutations_are_rejected(self):
        self.assertEqual(0, self.invoke(["init", "--admin-id", "human:admin",
            "--provider", "local", "--subject", "admin", "--display-name", "Admin"], frozen=True))
        self.assertEqual(0, self.invoke(["open-round", "--actor", "human:admin",
            "--config", str(ROOT / "rounds/WB001-PILOT-001/round.json")], frozen=True))
        before = self.ledger.read_bytes()
        self.assertEqual(0, self.invoke(["status", "--round", "WB001-PILOT-001", "--json"]))
        self.assertEqual(2, self.invoke(["check-in", "--operator-id", "human:new",
            "--provider", "local", "--subject", "new", "--display-name", "New"]))
        self.assertEqual(before, self.ledger.read_bytes())

    def test_successor_defaults_do_not_reuse_historical_state(self):
        parser = frozen_cli.build_parser()
        prepare_governed(parser, ROOT)
        args = parser.parse_args(["status"])
        for name in ("ledger", "evidence_root", "artifact_root", "private_root"):
            self.assertTrue(getattr(args, name).is_relative_to(ROOT / "state" / RESEARCH_ROUND))

    def test_explicit_old_default_state_is_rejected_before_delegation(self):
        with patch("engine.cli.require_runtime"), patch("engine.cli.governed_cli.run") as run:
            with redirect_stderr(StringIO()):
                result = main(["--ledger", str(ROOT / "state/pilot_events.jsonl"),
                               "checkpoint", "--output", str(self.root / "checkpoint.json")])
            self.assertEqual(2, result)
            run.assert_not_called()

    def test_historical_shift_stays_inspectable_but_cannot_run_or_resume(self):
        workflow = ShiftWorkflow(ROOT)
        target = self.root / "old-shift"
        workflow.start(output=target, operator="demo:old", workbench="WB-013")
        path = target / "session.json"
        session = json.loads(path.read_text())
        del session["sha256"]
        session["environment"] = check_runtime(ROOT, LEGACY_PROFILE)
        path.write_text(json.dumps(sealed(session)), encoding="utf-8")
        before = inventory(target)
        self.assertEqual(LEGACY_PROFILE, workflow.inspect(target)["session"]["environment"]["environment_id"])
        with self.assertRaisesRegex(ContractError, "historical environment"):
            workflow.run(target)
        self.assertEqual(before, inventory(target))
        workflow.finish(target, outcome="BLOCKED", summary="Historical environment retired.",
                        next_lead="Create a separate successor task.", blocker="Old runtime is retired.")
        handover = self.root / "old-handover"
        workflow.export(target, handover)
        with self.assertRaisesRegex(ContractError, "historical environment"):
            workflow.start(output=self.root / "new", operator="demo:new", previous=handover)
        self.assertFalse((self.root / "new").exists())
