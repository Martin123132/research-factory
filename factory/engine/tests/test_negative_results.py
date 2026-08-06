from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from control_plane.common import ContractError, sha256_file
from control_plane.ledger import EventLedger
from engine.cli import main
from engine.negative_results import search_rows


FACTORY_ROOT = Path(__file__).resolve().parents[2]


def append(ledger: EventLedger, event_type: str, actor: str, payload: dict) -> None:
    ledger.append(
        event_type,
        actor,
        payload,
        validator=lambda events, kind, actor_id, body, recorded_at: None,
        recorded_at=f"2026-08-0{len(ledger.read()) + 1}T09:00:00Z",
    )


def add_negative(
    ledger: EventLedger,
    *,
    suffix: str,
    work_unit: str,
    classification: str,
    reason: str,
    hypothesis: str,
    summary: str,
) -> None:
    claim_id = f"claim:{suffix}"
    attempt_id = f"attempt:{suffix}"
    append(
        ledger,
        "WORK_CLAIMED",
        "human:alice",
        {
            "work_claim_id": claim_id,
            "round_id": "WB001-PILOT-001",
            "work_unit_id": work_unit,
        },
    )
    append(
        ledger,
        "ATTEMPT_STARTED",
        "human:alice",
        {"work_claim_id": claim_id, "attempt_id": attempt_id},
    )
    append(
        ledger,
        "NEGATIVE_RESULT_RECORDED",
        "human:alice",
        {
            "attempt_id": attempt_id,
            "classification": classification,
            "reason_code": reason,
            "hypothesis": hypothesis,
            "candidate_artifact_sha256": "a" * 64,
            "evidence_package_sha256": ("b" if suffix == "headers" else "c") * 64,
            "public_summary": summary,
            "details_sealed": True,
        },
    )


class NegativeResultSearchTests(unittest.TestCase):
    def invoke(self, argv: list[str]) -> tuple[int, str, str]:
        stdout = StringIO()
        stderr = StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            returncode = main(argv)
        return returncode, stdout.getvalue(), stderr.getvalue()

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.ledger_path = Path(self.temporary.name) / "events.jsonl"
        ledger = EventLedger(self.ledger_path)
        add_negative(
            ledger,
            suffix="headers",
            work_unit="wu:small-blocks",
            classification="HYPOTHESIS_REJECTED",
            reason="HEADER_COST_EXCEEDS_GAIN",
            hypothesis="Small block delta transforms reduce total size.",
            summary="Headers cost more bytes than the transform saved.",
        )
        add_negative(
            ledger,
            suffix="memory",
            work_unit="wu:dictionary",
            classification="RESOURCE_BOUNDARY",
            reason="MEMORY_LIMIT",
            hypothesis="A much larger dictionary remains economical.",
            summary="Peak memory exceeded the station resource ceiling.",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_words_and_exact_filters_narrow_results(self) -> None:
        returncode, stdout, stderr = self.invoke(
            [
                "negative-results",
                "--ledger",
                str(self.ledger_path),
                "--query",
                "SMALL headers",
                "--classification",
                "hypothesis_rejected",
                "--reason-code",
                "header_cost_exceeds_gain",
                "--json",
            ]
        )
        self.assertEqual(0, returncode, stderr)
        value = json.loads(stdout)
        self.assertEqual(1, value["total_matches"])
        self.assertEqual("attempt:headers", value["results"][0]["attempt_id"])
        self.assertNotIn("measurement", json.dumps(value))

    def test_search_is_read_only_and_limit_is_reported_honestly(self) -> None:
        before_bytes = self.ledger_path.read_bytes()
        before_hash = sha256_file(self.ledger_path)
        returncode, stdout, stderr = self.invoke(
            [
                "negative-results",
                "--ledger",
                str(self.ledger_path),
                "--limit",
                "1",
                "--json",
            ]
        )
        self.assertEqual(0, returncode, stderr)
        value = json.loads(stdout)
        self.assertEqual(2, value["total_matches"])
        self.assertEqual(1, value["returned"])
        self.assertEqual(before_bytes, self.ledger_path.read_bytes())
        self.assertEqual(before_hash, sha256_file(self.ledger_path))

    def test_zero_matches_have_a_clear_human_result(self) -> None:
        returncode, stdout, stderr = self.invoke(
            [
                "negative-results",
                "--ledger",
                str(self.ledger_path),
                "--query",
                "not-present-anywhere",
            ]
        )
        self.assertEqual(0, returncode, stderr)
        self.assertEqual("No retained negative results matched.\n", stdout)

    def test_missing_ledger_and_out_of_range_limit_fail_closed(self) -> None:
        missing = Path(self.temporary.name) / "missing.jsonl"
        returncode, _, stderr = self.invoke(
            ["negative-results", "--ledger", str(missing), "--json"]
        )
        self.assertEqual(2, returncode)
        self.assertIn("ledger does not exist", stderr)

        rows = [
            {
                "attempt_id": "attempt:test",
                "round_id": "round:test",
                "work_unit_id": "wu:test",
                "author_operator_id": "human:test",
                "classification": "NO_GAIN",
                "reason_code": "NO_GAIN",
                "hypothesis": "test",
                "public_summary": "test",
                "submitted_at": "2026-08-01T00:00:00Z",
            }
        ]
        with self.assertRaisesRegex(ContractError, "between 1 and 500"):
            search_rows(rows, limit=0)


if __name__ == "__main__":
    unittest.main()
