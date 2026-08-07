"""Portable, local commissioning drill for the constrained container adapter.

This module deliberately exercises an engineering control, not a workbench.  It
creates a small public package, waits for a human-held release capability before
starting the fixed fixture, and leaves a result that can be checked later
without contacting Docker.  It never issues scientific, identity, replication,
or promotion authority.
"""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from pathlib import Path, PurePosixPath
from typing import Any

from control_plane.common import (
    ContractError,
    canonical_json_bytes,
    sha256_bytes,
    utc_now,
    utc_text,
    validate_id,
)

from .container_adapter import (
    inspect_host,
    load_request,
    run_container,
    validate_request,
    verify_receipt,
)
from .gate import BOUNDARY, PROFILE_CONTAINER, REQUIRED_STOPS, DispatchBudgetGate, load_json_strict


DEFAULT_IMAGE_REF = (
    "python:3.13-slim@sha256:"
    "c33f0bc4364a6881bed1ec0cc2665e6c53c87a43e774aaeab88e6f17af105e4f"
)
FIXTURE_ARGV = [
    "python",
    "-c",
    "print('container-commissioned')",
]
PREPARED_FILES = {"budget.json", "ticket.json", "request.json"}
FINAL_FILES = {*PREPARED_FILES, "receipt.json", "report.json", "runner-output"}
REPORT_KEYS = {
    "schema_version",
    "drill_id",
    "scope",
    "budget_sha256",
    "ticket_sha256",
    "request_sha256",
    "receipt_sha256",
    "output_sha256",
    "process_started",
    "exit_code",
    "stop_conditions_triggered",
    "scientific_standing",
    "counts_as_independent_reproduction",
    "eligible_for_promotion",
    "host_boundary",
    "fixture_output_scope",
    "report_sha256",
}


def _write_json_exclusive(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
    except FileExistsError as exc:
        raise ContractError(f"container commissioning artifact already exists: {path}") from exc


def _relative_state_output(output: Path, *, factory_root: Path) -> tuple[Path, str]:
    root = factory_root.resolve()
    resolved = output.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise ContractError("container commissioning output must be inside the factory root") from exc
    path = PurePosixPath(relative.as_posix())
    if len(path.parts) < 2 or path.parts[0] != "state" or any(part in {".", ".."} for part in path.parts):
        raise ContractError("container commissioning output must be a fresh directory under factory/state")
    return resolved, path.as_posix()


def _manifest(image_ref: str) -> dict[str, Any]:
    return {"image_ref": image_ref, "argv": FIXTURE_ARGV}


def _build_budget(
    *,
    output_relative: str,
    image_ref: str,
    operator_id: str,
    release_capability: str,
) -> dict[str, Any]:
    if not release_capability:
        raise ContractError("container commissioning requires a non-empty human release capability")
    validate_id(operator_id, field="operator_id")
    now = utc_now()
    unsigned: dict[str, Any] = {
        "schema_version": 1,
        "budget_type": "AGENT_DISPATCH_BUDGET",
        "budget_id": f"dispatch-budget:container-commissioning-{uuid.uuid4().hex}",
        "work_order": {
            "work_order_id": "work-order:container-commissioning-fixture-v1",
            "work_order_revision": 1,
            "work_order_sha256": sha256_bytes(b"container-commissioning-fixture-v1"),
            "station_id": "WB-001",
        },
        "accountable_human": {
            "operator_id": operator_id,
            "display_name": "Container Commissioning Operator",
            "identity_assurance": "SELF_ASSERTED_LOCAL",
            "identity_warning": "IDENTITY_RECORD_IS_NOT_PROOF_OF_A_DISTINCT_HUMAN",
            "release_capability_sha256": sha256_bytes(release_capability.encode("utf-8")),
            "retains_release_control": True,
            "may_stop_without_penalty": True,
        },
        "objective": {
            "statement": "Commission the bounded digest-pinned Docker adapter using its fixed local fixture.",
            "allowed_tasks": [
                "Run only the fixed container commissioning fixture and preserve its bounded output."
            ],
            "prohibited_tasks": [
                "Perform research, access protected data, claim a result, or promote any output."
            ],
            "evidence_class": "SYNTHETIC_COMMISSIONING_ONLY",
        },
        "requested_execution_mode": "PROCESS_EXECUTION",
        "time_budget": {
            "issued_at": utc_text(now),
            "expires_at": utc_text(now + timedelta(minutes=30)),
            "max_wall_seconds": 30,
            "max_active_seconds": 30,
            "max_idle_seconds": 10,
            "max_shift_count": 1,
            "extension_policy": "NEW_BUDGET_AND_HUMAN_RELEASE_ONLY",
        },
        "compute_budget": {
            "max_cpu_seconds": 30,
            "max_memory_bytes": 67108864,
            "max_gpu_seconds": 0,
            "max_storage_bytes": 4096,
            "max_output_bytes": 8192,
            "max_processes": 8,
        },
        "financial_budget": {
            "max_minor_units": 0,
            "currency": "GBP",
            "allowed_billable_services": [],
        },
        "interface_budget": {
            "allowed_interfaces": [
                "LOCAL_SUBPROCESS",
                "DECLARED_INPUT_FILES",
                "DECLARED_OUTPUT_FILES",
            ],
            "allowed_tool_manifest_sha256": [
                sha256_bytes(canonical_json_bytes(_manifest(image_ref)))
            ],
            "shell_policy": "EXACT_COMMAND_ONLY",
            "agent_may_add_tools": False,
        },
        "data_budget": {
            "read_paths": ["dispatch/tests"],
            "write_paths": [f"{output_relative}/public"],
            "network_policy": "DENY_ALL",
            "allowed_domains": [],
        },
        "hazard_budget": {
            "classification": "UNTRUSTED_SOFTWARE",
            "human_review_required": True,
            "human_review_sha256": sha256_bytes(b"container-commissioning-fixture-risk-review-v1"),
        },
        "stop_conditions": sorted(REQUIRED_STOPS),
        "authority_boundary": BOUNDARY,
    }
    return {**unsigned, "budget_sha256": sha256_bytes(canonical_json_bytes(unsigned))}


def _build_request(
    *,
    output_relative: str,
    image_ref: str,
    budget: dict[str, Any],
    ticket: dict[str, Any],
) -> dict[str, Any]:
    unsigned: dict[str, Any] = {
        "schema_version": 1,
        "request_type": "CONTAINER_DISPATCH_REQUEST",
        "request_id": f"container-request:commissioning-{uuid.uuid4().hex}",
        "budget_sha256": budget["budget_sha256"],
        "ticket_sha256": ticket["ticket_sha256"],
        "image_ref": image_ref,
        "argv": FIXTURE_ARGV,
        "output_path": f"{output_relative}/public/runner-output",
    }
    return {**unsigned, "request_sha256": sha256_bytes(canonical_json_bytes(unsigned))}


def prepare_container_commissioning_drill(
    output: Path,
    *,
    factory_root: Path,
    image_ref: str = DEFAULT_IMAGE_REF,
    operator_id: str = "human:container-commissioning-operator",
    release_capability: str,
) -> dict[str, Any]:
    """Create a fresh, inspectable package without starting Docker."""

    output, relative = _relative_state_output(output, factory_root=factory_root)
    if output.exists():
        raise ContractError(f"container commissioning output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        output.mkdir()
    except FileExistsError as exc:
        raise ContractError(f"container commissioning output already exists: {output}") from exc
    public = output / "public"
    public.mkdir()
    budget = _build_budget(
        output_relative=relative,
        image_ref=image_ref,
        operator_id=operator_id,
        release_capability=release_capability,
    )
    gate = DispatchBudgetGate(factory_root)
    gate.validate_budget(budget)
    ticket = gate.write_ticket(
        budget,
        profile_id=PROFILE_CONTAINER,
        output=public / "ticket.json",
        ticket_id=f"dispatch-ticket:container-commissioning-{uuid.uuid4().hex}",
    )
    request = _build_request(
        output_relative=relative,
        image_ref=image_ref,
        budget=budget,
        ticket=ticket,
    )
    validate_request(request, budget=budget, ticket=ticket, factory_root=factory_root)
    _write_json_exclusive(public / "budget.json", budget)
    _write_json_exclusive(public / "request.json", request)
    return verify_prepared_container_commissioning_drill(output, factory_root=factory_root)


def _load_prepared(
    output: Path,
    *,
    factory_root: Path,
    expected_files: set[str],
) -> tuple[Path, dict[str, Any], dict[str, Any], dict[str, Any]]:
    output, _ = _relative_state_output(output, factory_root=factory_root)
    public = output / "public"
    if not public.is_dir() or {item.name for item in public.iterdir()} != expected_files:
        raise ContractError("container commissioning drill has missing or unexpected public artifacts")
    gate = DispatchBudgetGate(factory_root)
    budget = gate.load_budget(public / "budget.json")
    ticket = gate.load_and_validate_ticket(public / "ticket.json", budget=budget)
    request = load_request(public / "request.json")
    validate_request(request, budget=budget, ticket=ticket, factory_root=factory_root, output_must_be_new=False)
    if budget["objective"]["evidence_class"] != "SYNTHETIC_COMMISSIONING_ONLY":
        raise ContractError("container commissioning package escaped its synthetic scope")
    if budget["authority_boundary"] != BOUNDARY:
        raise ContractError("container commissioning package changed the authority boundary")
    if request["argv"] != FIXTURE_ARGV:
        raise ContractError("container commissioning package changed the fixed fixture command")
    return public, budget, ticket, request


def verify_prepared_container_commissioning_drill(
    output: Path,
    *,
    factory_root: Path,
) -> dict[str, Any]:
    """Verify an unexecuted package before a human authorises its run."""

    _, budget, ticket, request = _load_prepared(
        output,
        factory_root=factory_root,
        expected_files=PREPARED_FILES,
    )
    if not ticket["authorized"] or ticket["authorization_scope"] != "PROCESS_EXECUTION":
        raise ContractError("container commissioning package was not authorised for its bounded fixture")
    return {
        "valid": True,
        "state": "PREPARED_AWAITING_HUMAN_RELEASE",
        "budget_sha256": budget["budget_sha256"],
        "ticket_sha256": ticket["ticket_sha256"],
        "request_sha256": request["request_sha256"],
        "scientific_standing": "NONE_SYNTHETIC_COMMISSIONING_ONLY",
        "counts_as_independent_reproduction": False,
        "eligible_for_promotion": False,
    }


def run_prepared_container_commissioning_drill(
    output: Path,
    *,
    factory_root: Path,
    release_capability: str,
) -> dict[str, Any]:
    """Run exactly one prepared fixture after a retained human release."""

    public, budget, ticket, request = _load_prepared(
        output,
        factory_root=factory_root,
        expected_files=PREPARED_FILES,
    )
    if not release_capability:
        raise ContractError("container commissioning requires a non-empty human release capability")
    host = inspect_host()
    if not host["ready"]:
        raise ContractError(f"container host is not ready: {host['reason']}")
    receipt = run_container(
        request,
        budget=budget,
        ticket=ticket,
        factory_root=factory_root,
        release_capability=release_capability,
        stop_file=output.resolve() / "human-stop.request",
        receipt_output=public / "receipt.json",
    )
    if not receipt["started"] or receipt["exit_code"] != 0:
        raise ContractError("container commissioning fixture did not complete successfully")
    if receipt["stop_conditions_triggered"] != ["PROCESS_EXITED"]:
        raise ContractError("container commissioning fixture did not exit through its expected bounded path")
    report_unsigned = {
        "schema_version": 1,
        "drill_id": "DISPATCH-CONTAINER-COMMISSIONING-001",
        "scope": "SYNTHETIC_CONTAINER_COMMISSIONING_ONLY",
        "budget_sha256": budget["budget_sha256"],
        "ticket_sha256": ticket["ticket_sha256"],
        "request_sha256": request["request_sha256"],
        "receipt_sha256": receipt["receipt_sha256"],
        "output_sha256": receipt["output_sha256"],
        "process_started": receipt["started"],
        "exit_code": receipt["exit_code"],
        "stop_conditions_triggered": receipt["stop_conditions_triggered"],
        "scientific_standing": "NONE_SYNTHETIC_COMMISSIONING_ONLY",
        "counts_as_independent_reproduction": False,
        "eligible_for_promotion": False,
        "host_boundary": "LOCAL_DOCKER_DAEMON_KERNEL_AND_HOST_CONFIGURATION_REMAIN_TRUSTED_COMPUTING_BASES",
        "fixture_output_scope": "CAPTURED_STDOUT_ONLY_NO_DURABLE_CONTAINER_WORK_FILES_CLAIMED",
    }
    report = {
        **report_unsigned,
        "report_sha256": sha256_bytes(canonical_json_bytes(report_unsigned)),
    }
    _write_json_exclusive(public / "report.json", report)
    return verify_container_commissioning_drill(output, factory_root=factory_root)


def verify_container_commissioning_drill(
    output: Path,
    *,
    factory_root: Path,
) -> dict[str, Any]:
    """Verify an executed drill and its preserved local output without Docker."""

    public, budget, ticket, request = _load_prepared(
        output,
        factory_root=factory_root,
        expected_files=FINAL_FILES,
    )
    report = load_json_strict(public / "report.json")
    if set(report) != REPORT_KEYS:
        raise ContractError("container commissioning report has an invalid closed shape")
    unsigned = {key: value for key, value in report.items() if key != "report_sha256"}
    if sha256_bytes(canonical_json_bytes(unsigned)) != report["report_sha256"]:
        raise ContractError("container commissioning report self-hash does not match")
    expected_report = {
        "schema_version": 1,
        "drill_id": "DISPATCH-CONTAINER-COMMISSIONING-001",
        "scope": "SYNTHETIC_CONTAINER_COMMISSIONING_ONLY",
        "budget_sha256": budget["budget_sha256"],
        "ticket_sha256": ticket["ticket_sha256"],
        "request_sha256": request["request_sha256"],
        "process_started": True,
        "exit_code": 0,
        "stop_conditions_triggered": ["PROCESS_EXITED"],
        "scientific_standing": "NONE_SYNTHETIC_COMMISSIONING_ONLY",
        "counts_as_independent_reproduction": False,
        "eligible_for_promotion": False,
        "host_boundary": "LOCAL_DOCKER_DAEMON_KERNEL_AND_HOST_CONFIGURATION_REMAIN_TRUSTED_COMPUTING_BASES",
        "fixture_output_scope": "CAPTURED_STDOUT_ONLY_NO_DURABLE_CONTAINER_WORK_FILES_CLAIMED",
    }
    for field, expected in expected_report.items():
        if report[field] != expected:
            raise ContractError(f"container commissioning report differs at {field}")
    receipt = load_json_strict(public / "receipt.json")
    receipt_verification = verify_receipt(
        receipt,
        request=request,
        budget=budget,
        ticket=ticket,
        factory_root=factory_root,
    )
    if report["receipt_sha256"] != receipt["receipt_sha256"]:
        raise ContractError("container commissioning report is bound to a different receipt")
    if report["output_sha256"] != receipt["output_sha256"]:
        raise ContractError("container commissioning report is bound to a different output")
    runner_output = public / "runner-output"
    if b"container-commissioned" not in (runner_output / "stdout.log").read_bytes():
        raise ContractError("container commissioning fixture stdout is not the expected known answer")
    if (runner_output / "stderr.log").read_bytes():
        raise ContractError("container commissioning fixture unexpectedly wrote stderr")
    return {
        "valid": True,
        "state": "COMMISSIONED",
        "report_sha256": report["report_sha256"],
        "receipt_sha256": receipt_verification["receipt_sha256"],
        "output_sha256": receipt_verification["output_sha256"],
        "scientific_standing": "NONE_SYNTHETIC_COMMISSIONING_ONLY",
        "counts_as_independent_reproduction": False,
        "eligible_for_promotion": False,
    }
