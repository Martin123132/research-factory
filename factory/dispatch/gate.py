from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from jsonschema import Draft202012Validator

from control_plane.common import (
    ContractError,
    canonical_json_bytes,
    parse_utc,
    sha256_bytes,
    sha256_file,
    utc_text,
    validate_id,
    validate_sha256,
)


SCHEMAS = Path(__file__).resolve().parent
PROFILE_DRY_RUN = "profile:no-execution-dry-run-v1"
PROFILE_FROZEN_LOCAL = "profile:frozen-local-monitored-v1"
PROFILE_CONTAINER = "profile:container-commissioning-v1"
REQUIRED_DIMENSIONS = (
    "HUMAN_RELEASE",
    "HUMAN_STOP",
    "WALL_TIME",
    "ACTIVE_TIME",
    "IDLE_TIME",
    "CPU_TIME",
    "MEMORY",
    "GPU_TIME",
    "STORAGE",
    "OUTPUT",
    "PROCESS_COUNT",
    "FINANCIAL_SPEND",
    "TOOL_ALLOWLIST",
    "FILESYSTEM_READ",
    "FILESYSTEM_WRITE",
    "NETWORK_EGRESS",
    "HAZARD_STOP",
    "STOP_CONDITIONS",
)
REQUIRED_STOPS = {
    "HUMAN_STOP_REQUESTED",
    "RELEASE_WITHHELD",
    "WALL_TIME_LIMIT_REACHED",
    "ACTIVE_TIME_LIMIT_REACHED",
    "IDLE_TIME_LIMIT_REACHED",
    "CPU_LIMIT_REACHED",
    "MEMORY_LIMIT_REACHED",
    "GPU_LIMIT_REACHED",
    "STORAGE_LIMIT_REACHED",
    "OUTPUT_LIMIT_REACHED",
    "PROCESS_LIMIT_REACHED",
    "COST_LIMIT_REACHED",
    "TOOL_POLICY_VIOLATION",
    "FILESYSTEM_POLICY_VIOLATION",
    "NETWORK_POLICY_VIOLATION",
    "HAZARD_ESCALATED",
    "PROCESS_EXITED",
    "PROCESS_LAUNCH_FAILED",
}
BOUNDARY = {
    "agent_may_expand_scope": False,
    "agent_may_expand_budget": False,
    "agent_may_change_evidence_class": False,
    "agent_may_self_release": False,
    "counts_as_scientific_evidence": False,
    "counts_as_independent_reproduction": False,
    "promotion_eligible": False,
}
FROZEN_LOCAL_SOURCES = {
    "control_plane/envelope.py": "20dc59e02e73c409bab41606407dc599463321536de03c0d666f4064d0042f93",
    "control_plane/schemas/work-order-envelope-v2.schema.json": (
        "5b2d4d1f3908114fcdf3f79373d14c3795cf29fbdcb331c9d80fcd00c4a08b8f"
    ),
    "control_plane/schemas/attempt-receipt-v2.schema.json": (
        "2474c037b80c26f8bac0da1606cc8e3fe4ec6efd68fe22962601cd56efdd9098"
    ),
}
CONTAINER_ADAPTER_SOURCES = {
    "dispatch/container_adapter.py": "db3845de9ea8da2d4c73ed33b91cb766f00e9b34be0463dbb47670fc73740e92",
    "dispatch/container-run-request-v1.schema.json": (
        "6aeacc1ebfd0cb63cc7dd1d5d870775441ee826c0e21d3028febcea28770ea98"
    ),
}


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key!r}")
        value[key] = item
    return value


def load_json_strict(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ContractError(f"could not load strict JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"expected a JSON object in {path}")
    return value


def _write_json_exclusive(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
    except FileExistsError as exc:
        raise ContractError(f"dispatch ticket destination already exists: {path}") from exc


def _verify_self_hash(document: dict[str, Any], field: str) -> None:
    validate_sha256(document[field], field=field)
    unsigned = {key: value for key, value in document.items() if key != field}
    actual = sha256_bytes(canonical_json_bytes(unsigned))
    if document[field] != actual:
        raise ContractError(f"{field} does not match the canonical document")


def _safe_repository_path(value: str, *, field: str) -> None:
    path = PurePosixPath(value)
    windows = PureWindowsPath(value)
    if (
        not value
        or "\\" in value
        or path.is_absolute()
        or windows.is_absolute()
        or windows.drive
        or "." in path.parts
        or ".." in path.parts
        or path.as_posix() != value
    ):
        raise ContractError(f"{field} must be a safe repository-relative path")
    sensitive = {
        "private",
        "secret",
        "secrets",
        "credential",
        "credentials",
        "hidden",
        "holdout",
        "holdouts",
        "key",
        "keys",
    }
    if any(part.casefold() in sensitive or part.casefold().startswith(".env") for part in path.parts):
        raise ContractError(f"{field} cannot grant protected or hidden material")


def _profile(
    *,
    profile_id: str,
    runner_name: str,
    execution_mode: str,
    authority: str,
    capabilities: dict[str, str],
    limitations: list[str],
) -> dict[str, Any]:
    if set(capabilities) != set(REQUIRED_DIMENSIONS):
        raise ContractError("built-in dispatch profile has incomplete enforcement dimensions")
    unsigned = {
        "profile_id": profile_id,
        "runner_name": runner_name,
        "execution_mode": execution_mode,
        "authority": authority,
        "capabilities": {name: capabilities[name] for name in REQUIRED_DIMENSIONS},
        "limitations": limitations,
    }
    return {**unsigned, "profile_sha256": sha256_bytes(canonical_json_bytes(unsigned))}


class DispatchBudgetGate:
    """Verify immutable budgets and issue fail-closed runner-admission tickets."""

    def __init__(self, factory_root: Path) -> None:
        self.factory_root = factory_root.resolve()
        self.budget_validator = self._load_validator("dispatch-budget-v1.schema.json")
        self.ticket_validator = self._load_validator("dispatch-ticket-v1.schema.json")

    @staticmethod
    def _load_validator(name: str) -> Draft202012Validator:
        schema = load_json_strict(SCHEMAS / name)
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as exc:  # pragma: no cover - jsonschema owns exception types
            raise ContractError(f"dispatch schema {name} is invalid: {exc}") from exc
        return Draft202012Validator(schema)

    @staticmethod
    def _validate_schema(
        validator: Draft202012Validator,
        document: dict[str, Any],
        *,
        label: str,
    ) -> None:
        errors = sorted(
            validator.iter_errors(document),
            key=lambda error: tuple(str(part) for part in error.absolute_path),
        )
        if errors:
            error = errors[0]
            location = "/".join(str(part) for part in error.absolute_path) or "$"
            raise ContractError(f"{label} schema violation at {location}: {error.message}")

    def validate_budget(self, budget: dict[str, Any]) -> dict[str, Any]:
        self._validate_schema(self.budget_validator, budget, label="dispatch budget")
        _verify_self_hash(budget, "budget_sha256")
        validate_id(budget["budget_id"], field="budget_id")
        validate_id(budget["accountable_human"]["operator_id"], field="operator_id")
        validate_sha256(
            budget["accountable_human"]["release_capability_sha256"],
            field="release_capability_sha256",
        )
        if budget["authority_boundary"] != BOUNDARY:
            raise ContractError("dispatch authority boundary differs from the fail-closed contract")

        issued = parse_utc(budget["time_budget"]["issued_at"], field="issued_at")
        expires = parse_utc(budget["time_budget"]["expires_at"], field="expires_at")
        if expires <= issued:
            raise ContractError("dispatch budget must expire after it is issued")
        time_budget = budget["time_budget"]
        if time_budget["max_active_seconds"] > time_budget["max_wall_seconds"]:
            raise ContractError("max_active_seconds cannot exceed max_wall_seconds")
        if time_budget["max_idle_seconds"] > time_budget["max_wall_seconds"]:
            raise ContractError("max_idle_seconds cannot exceed max_wall_seconds")

        if set(budget["stop_conditions"]) != REQUIRED_STOPS:
            raise ContractError("dispatch budget must contain every fixed fail-closed stop condition")
        for collection_name in ("read_paths", "write_paths"):
            for index, value in enumerate(budget["data_budget"][collection_name]):
                _safe_repository_path(value, field=f"data_budget.{collection_name}[{index}]")

        data = budget["data_budget"]
        interfaces = set(budget["interface_budget"]["allowed_interfaces"])
        if data["network_policy"] == "DENY_ALL" and data["allowed_domains"]:
            raise ContractError("DENY_ALL cannot carry allowed network domains")
        if data["network_policy"] == "DOMAIN_ALLOWLIST":
            if not data["allowed_domains"]:
                raise ContractError("DOMAIN_ALLOWLIST requires at least one domain")
            if not interfaces.intersection({"NETWORK_HTTPS", "MODEL_API"}):
                raise ContractError("network domains require a declared network-capable interface")

        finance = budget["financial_budget"]
        if finance["max_minor_units"] == 0 and finance["allowed_billable_services"]:
            raise ContractError("a zero-cost budget cannot allow billable services")
        if finance["max_minor_units"] > 0 and not finance["allowed_billable_services"]:
            raise ContractError("a positive financial budget must name every billable service")

        hazard = budget["hazard_budget"]
        if hazard["classification"] == "NONE":
            if hazard["human_review_required"] or hazard["human_review_sha256"] is not None:
                raise ContractError("a NONE hazard budget cannot invent a risk review")
        elif not hazard["human_review_required"] or hazard["human_review_sha256"] is None:
            raise ContractError("non-NONE hazards require a hash-bound human review")

        if budget["requested_execution_mode"] == "DRY_RUN_ONLY":
            nonzero = [
                *[value for key, value in time_budget.items() if key.startswith("max_")],
                *budget["compute_budget"].values(),
                finance["max_minor_units"],
            ]
            if any(nonzero):
                raise ContractError("DRY_RUN_ONLY must grant zero time, compute, storage and spend")
            if interfaces != {"PREFLIGHT_ONLY"}:
                raise ContractError("DRY_RUN_ONLY may grant only PREFLIGHT_ONLY")
            if budget["interface_budget"]["allowed_tool_manifest_sha256"]:
                raise ContractError("DRY_RUN_ONLY cannot grant tools")
            if budget["interface_budget"]["shell_policy"] != "FORBIDDEN":
                raise ContractError("DRY_RUN_ONLY must forbid a shell")
            if data["read_paths"] or data["write_paths"] or data["allowed_domains"]:
                raise ContractError("DRY_RUN_ONLY cannot grant data or network access")
            if hazard["classification"] != "NONE":
                raise ContractError("DRY_RUN_ONLY cannot carry an execution hazard")
        else:
            if "PREFLIGHT_ONLY" in interfaces:
                raise ContractError("PROCESS_EXECUTION cannot use PREFLIGHT_ONLY")
            if time_budget["max_wall_seconds"] < 1 or time_budget["max_shift_count"] < 1:
                raise ContractError("PROCESS_EXECUTION requires positive wall time and shift count")
            if budget["compute_budget"]["max_output_bytes"] < 1:
                raise ContractError("PROCESS_EXECUTION requires a positive output ceiling")
        return budget

    def load_budget(self, path: Path) -> dict[str, Any]:
        return self.validate_budget(load_json_strict(path))

    def enforcement_profile(self, profile_id: str) -> dict[str, Any]:
        if profile_id == PROFILE_DRY_RUN:
            return _profile(
                profile_id=PROFILE_DRY_RUN,
                runner_name="Built-in no-execution preflight",
                execution_mode="DRY_RUN_ONLY",
                authority="BUILTIN_NO_EXECUTION_GATE",
                capabilities={name: "ENFORCED" for name in REQUIRED_DIMENSIONS},
                limitations=[
                    "No process, tool, file, network, model or billable service is started.",
                    "Authorization proves the admission gate only and cannot execute research.",
                ],
            )
        if profile_id == PROFILE_FROZEN_LOCAL:
            for relative, expected in FROZEN_LOCAL_SOURCES.items():
                path = self.factory_root / relative
                if not path.is_file() or sha256_file(path) != expected:
                    raise ContractError(f"frozen local profile source drifted: {relative}")
            enforced = {"HUMAN_RELEASE", "HUMAN_STOP", "WALL_TIME", "OUTPUT"}
            return _profile(
                profile_id=PROFILE_FROZEN_LOCAL,
                runner_name="Frozen Pilot LOCAL_MONITORED_V1",
                execution_mode="PROCESS_EXECUTION",
                authority="FROZEN_SOFTWARE_LOCK_ANALYSIS",
                capabilities={
                    name: "ENFORCED" if name in enforced else "NOT_ENFORCED"
                    for name in REQUIRED_DIMENSIONS
                },
                limitations=[
                    "The frozen pilot does not isolate CPU, memory, GPU, storage or child processes.",
                    "The frozen pilot does not enforce filesystem scope, network egress, tool closure or spend.",
                    "Its partial envelope remains synthetic commissioning only and is not modified here.",
                ],
            )
        if profile_id == PROFILE_CONTAINER:
            for relative, expected in CONTAINER_ADAPTER_SOURCES.items():
                path = self.factory_root / relative
                if not path.is_file() or sha256_file(path) != expected:
                    raise ContractError(f"container adapter source drifted: {relative}")
            return _profile(
                profile_id=PROFILE_CONTAINER,
                runner_name="Digest-pinned Docker commissioning adapter",
                execution_mode="PROCESS_EXECUTION",
                authority="CONTAINER_ADAPTER_SOURCE_LOCK",
                capabilities={name: "ENFORCED" for name in REQUIRED_DIMENSIONS},
                limitations=[
                    "The adapter fails closed unless a local Docker daemon applies its exact no-network, no-GPU, read-only command plan.",
                    "Only digest-pinned images, allowlisted exact commands, read-only declared inputs and temporary bounded output are accepted.",
                    "A successful container run remains commissioning-only, has no scientific standing and cannot promote a result.",
                    "Docker daemon, kernel and host configuration remain trusted computing-base assumptions outside this profile.",
                ],
            )
        raise ContractError(f"unknown built-in dispatch enforcement profile: {profile_id}")

    def build_ticket(
        self,
        budget: dict[str, Any],
        *,
        profile_id: str,
        ticket_id: str | None = None,
        created_at: str | None = None,
    ) -> dict[str, Any]:
        self.validate_budget(budget)
        profile = self.enforcement_profile(profile_id)
        ticket_id = ticket_id or f"dispatch-ticket:{uuid.uuid4().hex}"
        validate_id(ticket_id, field="ticket_id")
        created_at = created_at or utc_text(datetime.now(timezone.utc))
        created = parse_utc(created_at, field="created_at")
        issued = parse_utc(budget["time_budget"]["issued_at"], field="issued_at")
        expires = parse_utc(budget["time_budget"]["expires_at"], field="expires_at")

        violations: list[dict[str, str]] = []
        if profile["execution_mode"] != budget["requested_execution_mode"]:
            violations.append(
                {
                    "dimension": "STOP_CONDITIONS",
                    "code": "EXECUTION_MODE_MISMATCH",
                    "summary": (
                        f"Budget requests {budget['requested_execution_mode']} but profile provides "
                        f"{profile['execution_mode']}."
                    ),
                }
            )
        if created < issued or created >= expires:
            violations.append(
                {
                    "dimension": "WALL_TIME",
                    "code": "BUDGET_NOT_ACTIVE",
                    "summary": "The preflight ticket was requested outside the immutable budget window.",
                }
            )
        for dimension in REQUIRED_DIMENSIONS:
            if profile["capabilities"][dimension] != "ENFORCED":
                violations.append(
                    {
                        "dimension": dimension,
                        "code": "NOT_ENFORCED",
                        "summary": f"The selected runner cannot enforce {dimension.lower().replace('_', ' ')}.",
                    }
                )
        authorized = not violations
        if authorized and budget["requested_execution_mode"] == "DRY_RUN_ONLY":
            scope = "NO_EXECUTION_PREFLIGHT_ONLY"
        elif authorized:
            scope = "PROCESS_EXECUTION"
        else:
            scope = "REJECTED"
        unsigned = {
            "schema_version": 1,
            "ticket_type": "DISPATCH_PREFLIGHT_TICKET",
            "ticket_id": ticket_id,
            "created_at": created_at,
            "budget_id": budget["budget_id"],
            "budget_sha256": budget["budget_sha256"],
            "profile": profile,
            "required_dimensions": list(REQUIRED_DIMENSIONS),
            "violations": violations,
            "authorized": authorized,
            "authorization_scope": scope,
            "human_release_required": True,
            "release_capability_sha256": budget["accountable_human"][
                "release_capability_sha256"
            ],
            "scientific_standing": "NONE",
            "promotion_eligible": False,
        }
        ticket = {
            **unsigned,
            "ticket_sha256": sha256_bytes(canonical_json_bytes(unsigned)),
        }
        self._validate_schema(self.ticket_validator, ticket, label="dispatch ticket")
        return ticket

    def validate_ticket(
        self,
        ticket: dict[str, Any],
        *,
        budget: dict[str, Any],
    ) -> dict[str, Any]:
        self._validate_schema(self.ticket_validator, ticket, label="dispatch ticket")
        _verify_self_hash(ticket, "ticket_sha256")
        expected = self.build_ticket(
            budget,
            profile_id=ticket["profile"]["profile_id"],
            ticket_id=ticket["ticket_id"],
            created_at=ticket["created_at"],
        )
        if ticket != expected:
            raise ContractError("dispatch ticket differs from the gate-derived decision")
        return ticket

    def write_ticket(
        self,
        budget: dict[str, Any],
        *,
        profile_id: str,
        output: Path,
        ticket_id: str | None = None,
        created_at: str | None = None,
    ) -> dict[str, Any]:
        output = output.resolve()
        ticket = self.build_ticket(
            budget,
            profile_id=profile_id,
            ticket_id=ticket_id,
            created_at=created_at,
        )
        _write_json_exclusive(output, ticket)
        return ticket

    def load_and_validate_ticket(self, path: Path, *, budget: dict[str, Any]) -> dict[str, Any]:
        return self.validate_ticket(load_json_strict(path), budget=budget)
