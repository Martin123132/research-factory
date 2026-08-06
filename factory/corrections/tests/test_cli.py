from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from control_plane.common import sha256_bytes


FACTORY_ROOT = Path(__file__).resolve().parents[2]
ENGINECTL = FACTORY_ROOT / "enginectl.py"


def reference(artifact_id: str, label: str) -> dict[str, object]:
    return {
        "artifact_class": "PUBLIC_ARTIFACT",
        "artifact_id": artifact_id,
        "artifact_sha256": sha256_bytes(label.encode("utf-8")),
        "locator_kind": "PUBLIC_URL",
        "locator": f"https://example.invalid/{label}.json",
        "media_type": "application/json",
        "visibility": "PUBLIC",
    }


def draft(action: str, target: dict[str, object], replacement: dict[str, object] | None) -> dict[str, object]:
    return {
        "actor": {
            "operator_id": "human:cli-operator",
            "display_name": "CLI Operator",
            "identity_assurance": "SELF_ASSERTED_LOCAL",
            "identity_warning": "IDENTITY_RECORD_IS_NOT_PROOF_OF_AUTHORITY",
        },
        "authority": {
            "basis": "AUTHOR",
            "scope": "CLI construction test only.",
            "conflict_declaration": "The author is correcting their own synthetic artifact.",
            "authorization_evidence_sha256": [],
        },
        "target": target,
        "action": action,
        "replacement": replacement,
        "reason": {
            "code": "MATERIAL_ERROR" if action == "CORRIGENDUM" else "WITHDRAWN_CLAIM",
            "summary": "The public synthetic artifact needs an append-only standing change.",
            "evidence_references": [],
        },
        "public_summary": "Exercise the public correction command without scientific standing.",
    }


class CorrectionCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.ledger = self.root / "corrections.jsonl"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def ctl(self, *arguments: str) -> dict[str, object]:
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
            0,
            completed.returncode,
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
        )
        return json.loads(completed.stdout)

    def test_append_verify_search_and_export_through_engine_front_door(self) -> None:
        target = reference("artifact:cli-original", "cli-original")
        replacement = reference("artifact:cli-corrected", "cli-corrected")
        first_draft = self.root / "first.json"
        first_draft.write_text(
            json.dumps(draft("CORRIGENDUM", target, replacement)),
            encoding="utf-8",
        )
        first = self.ctl(
            "correction-append",
            "--ledger",
            str(self.ledger),
            "--draft",
            str(first_draft),
        )
        self.assertEqual("CURRENT_WITH_CORRECTION", first["standing_after"])

        second_draft = self.root / "second.json"
        second_draft.write_text(
            json.dumps(draft("RETRACTION", target, None)),
            encoding="utf-8",
        )
        second = self.ctl(
            "correction-append",
            "--ledger",
            str(self.ledger),
            "--draft",
            str(second_draft),
        )
        self.assertEqual("RETRACTED", second["standing_after"])

        verified = self.ctl("correction-verify", "--ledger", str(self.ledger))
        self.assertEqual(2, verified["records"])
        self.assertEqual({"RETRACTED": 1}, verified["current_standings"])
        history = self.ctl(
            "correction-history",
            "--ledger",
            str(self.ledger),
            "--standing",
            "RETRACTED",
        )
        self.assertEqual(2, history["returned"])
        self.assertTrue(all(row["current_standing"] == "RETRACTED" for row in history["records"]))

        output = self.root / "index.json"
        exported = self.ctl(
            "correction-export",
            "--ledger",
            str(self.ledger),
            "--output",
            str(output),
        )
        self.assertEqual(2, exported["returned"])
        self.assertNotIn("ledger", exported["ledger"])
        self.assertTrue(output.is_file())


if __name__ == "__main__":
    unittest.main()
