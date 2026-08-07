from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from control_plane.common import ContractError, canonical_json_bytes, sha256_bytes
from dispatch.gate import (
    PROFILE_CONTAINER,
    PROFILE_DRY_RUN,
    PROFILE_FROZEN_LOCAL,
    REQUIRED_DIMENSIONS,
    DispatchBudgetGate,
    load_json_strict,
)
from dispatch.synthetic_drill import _budget, run_synthetic_drill, verify_synthetic_drill


FACTORY_ROOT = Path(__file__).resolve().parents[2]


def resign(document: dict[str, object], field: str) -> dict[str, object]:
    unsigned = {key: value for key, value in document.items() if key != field}
    document[field] = sha256_bytes(canonical_json_bytes(unsigned))
    return document


class DispatchBudgetGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.gate = DispatchBudgetGate(FACTORY_ROOT)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_tracked_example_and_closed_schemas_validate(self) -> None:
        example = self.gate.load_budget(FACTORY_ROOT / "dispatch" / "dispatch-budget.example.json")
        self.assertEqual("DRY_RUN_ONLY", example["requested_execution_mode"])
        self.assertFalse(example["authority_boundary"]["promotion_eligible"])

    def test_no_execution_profile_authorizes_only_preflight(self) -> None:
        budget = _budget("DRY_RUN_ONLY")
        ticket = self.gate.build_ticket(
            budget,
            profile_id=PROFILE_DRY_RUN,
            ticket_id="dispatch-ticket:test-dry-run",
            created_at="2026-08-07T11:00:00Z",
        )
        self.assertTrue(ticket["authorized"])
        self.assertEqual("NO_EXECUTION_PREFLIGHT_ONLY", ticket["authorization_scope"])
        self.assertEqual([], ticket["violations"])
        self.assertTrue(ticket["human_release_required"])
        self.assertEqual("NONE", ticket["scientific_standing"])
        self.gate.validate_ticket(ticket, budget=budget)

    def test_frozen_local_runner_is_rejected_for_every_unenforced_dimension(self) -> None:
        budget = _budget("PROCESS_EXECUTION")
        ticket = self.gate.build_ticket(
            budget,
            profile_id=PROFILE_FROZEN_LOCAL,
            ticket_id="dispatch-ticket:test-local-rejection",
            created_at="2026-08-07T11:00:00Z",
        )
        self.assertFalse(ticket["authorized"])
        self.assertEqual("REJECTED", ticket["authorization_scope"])
        missing = {
            name
            for name in REQUIRED_DIMENSIONS
            if ticket["profile"]["capabilities"][name] == "NOT_ENFORCED"
        }
        self.assertEqual(
            {
                "ACTIVE_TIME",
                "IDLE_TIME",
                "CPU_TIME",
                "MEMORY",
                "GPU_TIME",
                "STORAGE",
                "PROCESS_COUNT",
                "FINANCIAL_SPEND",
                "TOOL_ALLOWLIST",
                "FILESYSTEM_READ",
                "FILESYSTEM_WRITE",
                "NETWORK_EGRESS",
                "HAZARD_STOP",
                "STOP_CONDITIONS",
            },
            missing,
        )
        reported = {row["dimension"] for row in ticket["violations"]}
        self.assertEqual(missing, reported)

    def test_agent_cannot_expand_budget_or_smuggle_private_paths(self) -> None:
        expanded = copy.deepcopy(_budget("DRY_RUN_ONLY"))
        expanded["authority_boundary"]["agent_may_expand_budget"] = True
        resign(expanded, "budget_sha256")
        with self.assertRaisesRegex(ContractError, "schema violation"):
            self.gate.validate_budget(expanded)

        private = copy.deepcopy(_budget("PROCESS_EXECUTION"))
        private["data_budget"]["read_paths"] = ["private/answer.json"]
        resign(private, "budget_sha256")
        with self.assertRaisesRegex(ContractError, "protected or hidden"):
            self.gate.validate_budget(private)

    def test_dry_run_cannot_hide_compute_tools_or_network(self) -> None:
        budget = copy.deepcopy(_budget("DRY_RUN_ONLY"))
        budget["compute_budget"]["max_cpu_seconds"] = 1
        resign(budget, "budget_sha256")
        with self.assertRaisesRegex(ContractError, "must grant zero"):
            self.gate.validate_budget(budget)

    def test_expired_budget_and_execution_mode_mismatch_fail_closed(self) -> None:
        budget = _budget("DRY_RUN_ONLY")
        expired = self.gate.build_ticket(
            budget,
            profile_id=PROFILE_DRY_RUN,
            ticket_id="dispatch-ticket:test-expired",
            created_at="2026-08-07T12:00:00Z",
        )
        self.assertFalse(expired["authorized"])
        self.assertEqual("BUDGET_NOT_ACTIVE", expired["violations"][0]["code"])

        mismatch = self.gate.build_ticket(
            budget,
            profile_id=PROFILE_FROZEN_LOCAL,
            ticket_id="dispatch-ticket:test-mode-mismatch",
            created_at="2026-08-07T11:00:00Z",
        )
        self.assertFalse(mismatch["authorized"])
        self.assertEqual("EXECUTION_MODE_MISMATCH", mismatch["violations"][0]["code"])

    def test_ticket_tampering_and_overwrite_are_rejected(self) -> None:
        budget = _budget("DRY_RUN_ONLY")
        output = self.root / "ticket.json"
        ticket = self.gate.write_ticket(
            budget,
            profile_id=PROFILE_DRY_RUN,
            output=output,
            ticket_id="dispatch-ticket:test-output",
            created_at="2026-08-07T11:00:00Z",
        )
        with self.assertRaisesRegex(ContractError, "already exists"):
            self.gate.write_ticket(budget, profile_id=PROFILE_DRY_RUN, output=output)
        tampered = copy.deepcopy(ticket)
        tampered["authorization_scope"] = "PROCESS_EXECUTION"
        with self.assertRaisesRegex(ContractError, "ticket_sha256"):
            self.gate.validate_ticket(tampered, budget=budget)

    def test_unknown_or_drifted_profile_cannot_authorize(self) -> None:
        with self.assertRaisesRegex(ContractError, "unknown built-in"):
            self.gate.enforcement_profile("profile:invented-perfect-runner")
        drifted_gate = DispatchBudgetGate(self.root)
        with self.assertRaisesRegex(ContractError, "source drifted"):
            drifted_gate.enforcement_profile(PROFILE_FROZEN_LOCAL)
        with self.assertRaisesRegex(ContractError, "source drifted"):
            drifted_gate.enforcement_profile(PROFILE_CONTAINER)

    def test_strict_loader_rejects_duplicate_keys(self) -> None:
        path = self.root / "duplicate.json"
        path.write_text('{"budget_type":"A","budget_type":"B"}\n', encoding="utf-8")
        with self.assertRaisesRegex(ContractError, "duplicate JSON key"):
            load_json_strict(path)

    def test_complete_synthetic_drill_and_tamper_detection(self) -> None:
        output = self.root / "drill"
        report = run_synthetic_drill(output, factory_root=FACTORY_ROOT)
        self.assertTrue(report["dry_run_authorized"])
        self.assertFalse(report["process_authorized"])
        verified = verify_synthetic_drill(output, factory_root=FACTORY_ROOT)
        self.assertTrue(verified["valid"])
        self.assertFalse(verified["process_started"])

        path = output / "public" / "dry-run-ticket.json"
        ticket = json.loads(path.read_text(encoding="utf-8"))
        ticket["authorized"] = False
        path.write_text(json.dumps(ticket) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ContractError, "ticket_sha256"):
            verify_synthetic_drill(output, factory_root=FACTORY_ROOT)

    def test_synthetic_drill_refuses_to_overwrite(self) -> None:
        output = self.root / "existing"
        output.mkdir()
        marker = output / "keep.txt"
        marker.write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(ContractError, "already exists"):
            run_synthetic_drill(output, factory_root=FACTORY_ROOT)
        self.assertEqual("keep", marker.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
