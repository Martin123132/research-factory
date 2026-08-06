from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from control_plane.common import (
    ContractError,
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
    write_json,
)

from .gate import (
    BOUNDARY,
    PROFILE_DRY_RUN,
    PROFILE_FROZEN_LOCAL,
    REQUIRED_DIMENSIONS,
    REQUIRED_STOPS,
    DispatchBudgetGate,
    load_json_strict,
)


REPORT_KEYS = {
    "schema_version",
    "drill_id",
    "scope",
    "dry_run_budget_sha256",
    "dry_run_ticket_sha256",
    "dry_run_authorized",
    "dry_run_scope",
    "process_budget_sha256",
    "rejection_ticket_sha256",
    "process_authorized",
    "missing_enforcement_dimensions",
    "process_started",
    "scientific_standing",
    "eligible_for_promotion",
    "report_sha256",
}


def _budget(mode: str) -> dict[str, Any]:
    dry = mode == "DRY_RUN_ONLY"
    budget_id = "dispatch-budget:synthetic-dry-run" if dry else "dispatch-budget:synthetic-process"
    unsigned: dict[str, Any] = {
        "schema_version": 1,
        "budget_type": "AGENT_DISPATCH_BUDGET",
        "budget_id": budget_id,
        "work_order": {
            "work_order_id": "work-order:synthetic-budget-gate",
            "work_order_revision": 1,
            "work_order_sha256": sha256_bytes(b"synthetic-work-order"),
            "station_id": "WB-001",
        },
        "accountable_human": {
            "operator_id": "human:synthetic-budget-operator",
            "display_name": "Synthetic Budget Operator",
            "identity_assurance": "SELF_ASSERTED_LOCAL",
            "identity_warning": "IDENTITY_RECORD_IS_NOT_PROOF_OF_A_DISTINCT_HUMAN",
            "release_capability_sha256": sha256_bytes(b"human-retained-synthetic-release"),
            "retains_release_control": True,
            "may_stop_without_penalty": True,
        },
        "objective": {
            "statement": (
                "Commission the no-execution admission gate."
                if dry
                else "Test whether the frozen local runner satisfies the universal budget."
            ),
            "allowed_tasks": [
                "Validate the visible synthetic dispatch-budget fixture."
                if dry
                else "Evaluate runner enforcement coverage without starting a process."
            ],
            "prohibited_tasks": [
                "Start research, access protected data or claim scientific standing."
            ],
            "evidence_class": "SYNTHETIC_COMMISSIONING_ONLY",
        },
        "requested_execution_mode": mode,
        "time_budget": {
            "issued_at": "2026-08-07T10:00:00Z",
            "expires_at": "2026-08-07T12:00:00Z",
            "max_wall_seconds": 0 if dry else 300,
            "max_active_seconds": 0 if dry else 240,
            "max_idle_seconds": 0 if dry else 60,
            "max_shift_count": 0 if dry else 1,
            "extension_policy": "NEW_BUDGET_AND_HUMAN_RELEASE_ONLY",
        },
        "compute_budget": {
            "max_cpu_seconds": 0 if dry else 240,
            "max_memory_bytes": 0 if dry else 536870912,
            "max_gpu_seconds": 0,
            "max_storage_bytes": 0 if dry else 10485760,
            "max_output_bytes": 0 if dry else 1048576,
            "max_processes": 0 if dry else 4,
        },
        "financial_budget": {
            "max_minor_units": 0,
            "currency": "GBP",
            "allowed_billable_services": [],
        },
        "interface_budget": {
            "allowed_interfaces": (
                ["PREFLIGHT_ONLY"]
                if dry
                else ["LOCAL_SUBPROCESS", "DECLARED_INPUT_FILES", "DECLARED_OUTPUT_FILES"]
            ),
            "allowed_tool_manifest_sha256": (
                [] if dry else [sha256_bytes(b"synthetic-exact-command-manifest")]
            ),
            "shell_policy": "FORBIDDEN" if dry else "EXACT_COMMAND_ONLY",
            "agent_may_add_tools": False,
        },
        "data_budget": {
            "read_paths": [] if dry else ["dispatch/fixtures"],
            "write_paths": [] if dry else ["state/dispatch-synthetic"],
            "network_policy": "DENY_ALL",
            "allowed_domains": [],
        },
        "hazard_budget": {
            "classification": "NONE" if dry else "UNTRUSTED_SOFTWARE",
            "human_review_required": not dry,
            "human_review_sha256": (
                None if dry else sha256_bytes(b"synthetic-human-risk-review")
            ),
        },
        "stop_conditions": sorted(REQUIRED_STOPS),
        "authority_boundary": BOUNDARY,
    }
    return {**unsigned, "budget_sha256": sha256_bytes(canonical_json_bytes(unsigned))}


def run_synthetic_drill(output: Path, *, factory_root: Path) -> dict[str, Any]:
    output = output.resolve()
    if output.exists():
        raise ContractError(f"synthetic dispatch output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    try:
        public = staging / "public"
        public.mkdir()
        gate = DispatchBudgetGate(factory_root)
        dry_budget = _budget("DRY_RUN_ONLY")
        process_budget = _budget("PROCESS_EXECUTION")
        gate.validate_budget(dry_budget)
        gate.validate_budget(process_budget)
        write_json(public / "dry-run-budget.json", dry_budget)
        write_json(public / "process-budget.json", process_budget)
        dry_ticket = gate.write_ticket(
            dry_budget,
            profile_id=PROFILE_DRY_RUN,
            output=public / "dry-run-ticket.json",
            ticket_id="dispatch-ticket:synthetic-dry-run",
            created_at="2026-08-07T11:00:00Z",
        )
        rejection = gate.write_ticket(
            process_budget,
            profile_id=PROFILE_FROZEN_LOCAL,
            output=public / "local-profile-rejection-ticket.json",
            ticket_id="dispatch-ticket:synthetic-local-rejection",
            created_at="2026-08-07T11:00:00Z",
        )
        missing = [
            name
            for name in REQUIRED_DIMENSIONS
            if rejection["profile"]["capabilities"][name] != "ENFORCED"
        ]
        report_unsigned = {
            "schema_version": 1,
            "drill_id": "DISPATCH-BUDGET-SYNTHETIC-001",
            "scope": "SYNTHETIC_COMMISSIONING_ONLY",
            "dry_run_budget_sha256": dry_budget["budget_sha256"],
            "dry_run_ticket_sha256": dry_ticket["ticket_sha256"],
            "dry_run_authorized": dry_ticket["authorized"],
            "dry_run_scope": dry_ticket["authorization_scope"],
            "process_budget_sha256": process_budget["budget_sha256"],
            "rejection_ticket_sha256": rejection["ticket_sha256"],
            "process_authorized": rejection["authorized"],
            "missing_enforcement_dimensions": missing,
            "process_started": False,
            "scientific_standing": "NONE_SYNTHETIC_COMMISSIONING_ONLY",
            "eligible_for_promotion": False,
        }
        report = {
            **report_unsigned,
            "report_sha256": sha256_bytes(canonical_json_bytes(report_unsigned)),
        }
        write_json(public / "report.json", report)
        verify_synthetic_drill(staging, factory_root=factory_root)
        os.replace(staging, output)
        return report
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def verify_synthetic_drill(output: Path, *, factory_root: Path) -> dict[str, Any]:
    output = output.resolve()
    public = output / "public"
    expected_files = {
        "dry-run-budget.json",
        "dry-run-ticket.json",
        "local-profile-rejection-ticket.json",
        "process-budget.json",
        "report.json",
    }
    if not public.is_dir() or {path.name for path in public.iterdir()} != expected_files:
        raise ContractError("synthetic dispatch drill has missing or unexpected public files")
    report = load_json_strict(public / "report.json")
    if set(report) != REPORT_KEYS:
        raise ContractError("synthetic dispatch report has an invalid closed shape")
    unsigned = {key: value for key, value in report.items() if key != "report_sha256"}
    if sha256_bytes(canonical_json_bytes(unsigned)) != report["report_sha256"]:
        raise ContractError("synthetic dispatch report self-hash does not match")
    if report["scope"] != "SYNTHETIC_COMMISSIONING_ONLY":
        raise ContractError("synthetic dispatch drill escaped its commissioning scope")
    if report["scientific_standing"] != "NONE_SYNTHETIC_COMMISSIONING_ONLY":
        raise ContractError("synthetic dispatch drill claims scientific standing")
    if report["eligible_for_promotion"] is not False or report["process_started"] is not False:
        raise ContractError("synthetic dispatch drill claims execution or promotion")

    gate = DispatchBudgetGate(factory_root)
    dry_budget = gate.load_budget(public / "dry-run-budget.json")
    process_budget = gate.load_budget(public / "process-budget.json")
    dry_ticket = gate.load_and_validate_ticket(
        public / "dry-run-ticket.json",
        budget=dry_budget,
    )
    rejection = gate.load_and_validate_ticket(
        public / "local-profile-rejection-ticket.json",
        budget=process_budget,
    )
    if dry_ticket["authorized"] is not True:
        raise ContractError("synthetic no-execution preflight was not authorized")
    if dry_ticket["authorization_scope"] != "NO_EXECUTION_PREFLIGHT_ONLY":
        raise ContractError("synthetic dry-run ticket claims the wrong scope")
    if rejection["authorized"] is not False or rejection["authorization_scope"] != "REJECTED":
        raise ContractError("incomplete local enforcement profile was not rejected")
    missing = [
        name
        for name in REQUIRED_DIMENSIONS
        if rejection["profile"]["capabilities"][name] != "ENFORCED"
    ]
    if missing != report["missing_enforcement_dimensions"]:
        raise ContractError("synthetic report hides or invents missing enforcement dimensions")
    checks = {
        "dry_run_budget_sha256": dry_budget["budget_sha256"],
        "dry_run_ticket_sha256": dry_ticket["ticket_sha256"],
        "process_budget_sha256": process_budget["budget_sha256"],
        "rejection_ticket_sha256": rejection["ticket_sha256"],
    }
    for field, expected in checks.items():
        if report[field] != expected:
            raise ContractError(f"synthetic dispatch report differs at {field}")
    return {
        "valid": True,
        "dry_run_authorized": True,
        "process_authorized": False,
        "process_started": False,
        "missing_enforcement_dimensions": missing,
        "report_sha256": report["report_sha256"],
        "scientific_standing": report["scientific_standing"],
        "eligible_for_promotion": False,
    }
