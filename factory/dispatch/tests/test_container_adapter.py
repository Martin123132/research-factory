from __future__ import annotations

import copy
import os
import shutil
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from control_plane.common import ContractError, canonical_json_bytes, sha256_bytes
from dispatch.container_adapter import (
    build_docker_command,
    inspect_host,
    run_container,
    validate_request,
    verify_receipt,
)
from dispatch.gate import PROFILE_CONTAINER, REQUIRED_DIMENSIONS, DispatchBudgetGate
from dispatch.synthetic_drill import _budget


FACTORY_ROOT = Path(__file__).resolve().parents[2]


def resign(document: dict[str, object]) -> dict[str, object]:
    unsigned = {key: value for key, value in document.items() if key != "budget_sha256"}
    document["budget_sha256"] = sha256_bytes(canonical_json_bytes(unsigned))
    return document


def request_for(budget: dict[str, object], ticket: dict[str, object]) -> dict[str, object]:
    image = "example.invalid/factory/commissioning@sha256:" + "a" * 64
    unsigned: dict[str, object] = {
        "schema_version": 1,
        "request_type": "CONTAINER_DISPATCH_REQUEST",
        "request_id": "container-request:unit-test",
        "budget_sha256": budget["budget_sha256"],
        "ticket_sha256": ticket["ticket_sha256"],
        "image_ref": image,
        "argv": ["python", "-c", "print('commissioning')"],
        "output_path": "state/dispatch-synthetic/container-unit-test-output",
    }
    return {**unsigned, "request_sha256": sha256_bytes(canonical_json_bytes(unsigned))}


class ContainerAdapterTests(unittest.TestCase):
    def process_budget_and_ticket(self) -> tuple[dict[str, object], dict[str, object]]:
        budget = copy.deepcopy(_budget("PROCESS_EXECUTION"))
        image = "example.invalid/factory/commissioning@sha256:" + "a" * 64
        argv = ["python", "-c", "print('commissioning')"]
        budget["interface_budget"]["allowed_tool_manifest_sha256"] = [  # type: ignore[index]
            sha256_bytes(canonical_json_bytes({"image_ref": image, "argv": argv}))
        ]
        budget["data_budget"]["read_paths"] = ["dispatch/tests"]  # type: ignore[index]
        resign(budget)
        gate = DispatchBudgetGate(FACTORY_ROOT)
        ticket = gate.build_ticket(
            budget,
            profile_id=PROFILE_CONTAINER,
            ticket_id="dispatch-ticket:container-unit-test",
            created_at="2026-08-07T11:00:00Z",
        )
        return budget, ticket

    def test_container_profile_has_complete_machine_enforcement_contract(self) -> None:
        budget, ticket = self.process_budget_and_ticket()
        self.assertTrue(ticket["authorized"])
        self.assertEqual("PROCESS_EXECUTION", ticket["authorization_scope"])
        self.assertEqual(
            set(REQUIRED_DIMENSIONS),
            {name for name, value in ticket["profile"]["capabilities"].items() if value == "ENFORCED"},  # type: ignore[index]
        )
        self.assertEqual(budget["budget_sha256"], ticket["budget_sha256"])

    def test_exact_manifest_and_no_network_plan_are_required(self) -> None:
        budget, ticket = self.process_budget_and_ticket()
        request = request_for(budget, ticket)
        validate_request(request, budget=budget, ticket=ticket, factory_root=FACTORY_ROOT)
        command = build_docker_command(
            request,
            budget=budget,
            factory_root=FACTORY_ROOT,
            container_name="factory-unit-test",
        )
        self.assertIn("--pull", command)
        self.assertIn("never", command)
        self.assertIn("--read-only", command)
        self.assertIn("--network", command)
        self.assertIn("none", command)
        self.assertIn("--cap-drop", command)
        self.assertIn("ALL", command)
        self.assertIn("--pids-limit", command)
        self.assertIn("--memory", command)
        self.assertIn("--ulimit", command)
        self.assertIn("cpu=240", command)
        self.assertIn("--tmpfs", command)
        self.assertIn("--user", command)
        self.assertIn("65534:65534", command)
        self.assertNotIn("--gpus", command)
        self.assertIn("/inputs/0,readonly", " ".join(command))

        changed = copy.deepcopy(request)
        changed["argv"] = ["sh", "-c", "network request"]
        changed["request_sha256"] = sha256_bytes(
            canonical_json_bytes({key: value for key, value in changed.items() if key != "request_sha256"})
        )
        with self.assertRaisesRegex(ContractError, "not allowlisted"):
            validate_request(changed, budget=budget, ticket=ticket, factory_root=FACTORY_ROOT)

    def test_adapter_rejects_external_costs_network_gpu_and_unbounded_output_location(self) -> None:
        budget, ticket = self.process_budget_and_ticket()
        request = request_for(budget, ticket)
        outside = copy.deepcopy(request)
        outside["output_path"] = "elsewhere/out"
        outside["request_sha256"] = sha256_bytes(
            canonical_json_bytes({key: value for key, value in outside.items() if key != "request_sha256"})
        )
        with self.assertRaisesRegex(ContractError, "outside the immutable write allowlist"):
            validate_request(outside, budget=budget, ticket=ticket, factory_root=FACTORY_ROOT)

        network = copy.deepcopy(budget)
        network["data_budget"]["network_policy"] = "DOMAIN_ALLOWLIST"  # type: ignore[index]
        network["data_budget"]["allowed_domains"] = ["example.com"]  # type: ignore[index]
        network["interface_budget"]["allowed_interfaces"].append("NETWORK_HTTPS")  # type: ignore[index]
        resign(network)
        network_ticket = DispatchBudgetGate(FACTORY_ROOT).build_ticket(
            network,
            profile_id=PROFILE_CONTAINER,
            ticket_id="dispatch-ticket:network-rejected",
            created_at="2026-08-07T11:00:00Z",
        )
        network_request = request_for(network, network_ticket)
        with self.assertRaisesRegex(ContractError, "three declared local container interfaces"):
            validate_request(network_request, budget=network, ticket=network_ticket, factory_root=FACTORY_ROOT)

    def test_host_probe_is_non_executing_and_explicit(self) -> None:
        value = inspect_host()
        self.assertIn("ready", value)
        self.assertIn("reason", value)
        self.assertIn("limitations", value)

    @unittest.skipUnless(
        os.environ.get("FACTORY_CONTAINER_E2E") == "1",
        "set FACTORY_CONTAINER_E2E=1 to run the local Docker commissioning check",
    )
    def test_digest_pinned_container_commissioning_run(self) -> None:
        if not inspect_host()["ready"]:
            self.skipTest("Docker daemon is not available")
        release = "container-adapter-e2e-human-release"
        image = "python:3.13-slim@sha256:c33f0bc4364a6881bed1ec0cc2665e6c53c87a43e774aaeab88e6f17af105e4f"
        argv = [
            "python",
            "-c",
            "from pathlib import Path; Path('result.txt').write_text('ok\\n'); print('container-adapter-e2e')",
        ]
        budget = copy.deepcopy(_budget("PROCESS_EXECUTION"))
        now = datetime.now(timezone.utc)
        budget["time_budget"].update(  # type: ignore[index]
            {
                "issued_at": (now - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
                "expires_at": (now + timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
                "max_wall_seconds": 30,
                "max_active_seconds": 30,
                "max_idle_seconds": 10,
            }
        )
        budget["compute_budget"].update(  # type: ignore[index]
            {
                "max_cpu_seconds": 30,
                "max_memory_bytes": 67108864,
                "max_storage_bytes": 4096,
                "max_output_bytes": 8192,
                "max_processes": 8,
            }
        )
        budget["data_budget"]["read_paths"] = ["dispatch/tests"]  # type: ignore[index]
        budget["accountable_human"]["release_capability_sha256"] = sha256_bytes(release.encode("utf-8"))  # type: ignore[index]
        budget["interface_budget"]["allowed_tool_manifest_sha256"] = [  # type: ignore[index]
            sha256_bytes(canonical_json_bytes({"image_ref": image, "argv": argv}))
        ]
        resign(budget)
        gate = DispatchBudgetGate(FACTORY_ROOT)
        ticket = gate.build_ticket(
            budget,
            profile_id=PROFILE_CONTAINER,
            ticket_id="dispatch-ticket:container-e2e",
            created_at=now.isoformat().replace("+00:00", "Z"),
        )
        output_path = f"state/dispatch-synthetic/container-e2e-{uuid.uuid4().hex}"
        unsigned = {
            "schema_version": 1,
            "request_type": "CONTAINER_DISPATCH_REQUEST",
            "request_id": "container-request:e2e",
            "budget_sha256": budget["budget_sha256"],
            "ticket_sha256": ticket["ticket_sha256"],
            "image_ref": image,
            "argv": argv,
            "output_path": output_path,
        }
        request = {**unsigned, "request_sha256": sha256_bytes(canonical_json_bytes(unsigned))}
        with tempfile.TemporaryDirectory() as raw:
            temporary = Path(raw)
            receipt_path = temporary / "receipt.json"
            try:
                receipt = run_container(
                    request,
                    budget=budget,
                    ticket=ticket,
                    factory_root=FACTORY_ROOT,
                    release_capability=release,
                    stop_file=temporary / "human-stop.request",
                    receipt_output=receipt_path,
                )
                self.assertTrue(receipt["started"])
                self.assertEqual(0, receipt["exit_code"])
                self.assertEqual("NONE_CONTAINER_COMMISSIONING_ONLY", receipt["scientific_standing"])
                self.assertFalse(receipt["promotion_eligible"])
                verified = verify_receipt(
                    receipt,
                    request=request,
                    budget=budget,
                    ticket=ticket,
                    factory_root=FACTORY_ROOT,
                )
                self.assertTrue(verified["valid"])
            finally:
                output = FACTORY_ROOT / output_path
                if output.exists():
                    shutil.rmtree(output)


if __name__ == "__main__":
    unittest.main()
