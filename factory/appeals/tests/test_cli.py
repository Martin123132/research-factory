from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from appeals.tests.test_appeals import draft


FACTORY_ROOT = Path(__file__).resolve().parents[2]


class AppealCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.ledger = self.root / "appeals.jsonl"
        self.draft = self.root / "appeal.json"
        self.draft.write_text(json.dumps(draft()), encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def ctl(self, *args: str, expected: int = 0) -> dict[str, object]:
        completed = subprocess.run(
            [sys.executable, "enginectl.py", *args, "--json"],
            cwd=FACTORY_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(expected, completed.returncode, completed.stderr)
        return json.loads(completed.stdout) if completed.stdout else {}

    def test_complete_appeal_cli_path(self) -> None:
        appended = self.ctl("appeal-append", "--ledger", str(self.ledger), "--draft", str(self.draft))
        self.assertEqual("RETURN_FOR_DIAGNOSIS", appended["outcome"])
        verified = self.ctl("appeal-verify", "--ledger", str(self.ledger))
        self.assertEqual(1, verified["records"])
        history = self.ctl(
            "appeal-history",
            "--ledger",
            str(self.ledger),
            "--outcome",
            "RETURN_FOR_DIAGNOSIS",
        )
        self.assertEqual(1, history["returned"])
        output = self.root / "appeal-index.json"
        exported = self.ctl("appeal-export", "--ledger", str(self.ledger), "--output", str(output))
        self.assertEqual(1, exported["returned"])
        self.assertTrue(output.is_file())


if __name__ == "__main__":
    unittest.main()
