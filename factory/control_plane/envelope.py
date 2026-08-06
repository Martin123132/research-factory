from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from .common import (
    ContractError,
    canonical_json_bytes,
    load_json,
    parse_utc,
    sha256_bytes,
    sha256_file,
    utc_text,
)


SCHEMAS = Path(__file__).resolve().parent / "schemas"


def _validate_schema(document: dict[str, Any], name: str) -> None:
    schema = load_json(SCHEMAS / name)
    try:
        Draft202012Validator(schema).validate(document)
    except ValidationError as exc:
        location = ".".join(str(part) for part in exc.absolute_path) or "document"
        raise ContractError(f"{name} validation failed at {location}: {exc.message}") from exc


def _verify_self_hash(document: dict[str, Any], field: str) -> None:
    unsigned = {key: value for key, value in document.items() if key != field}
    actual = sha256_bytes(canonical_json_bytes(unsigned))
    if document.get(field) != actual:
        raise ContractError(f"{field} does not match the canonical document")


def _resolve_working_directory(factory_root: Path, relative_text: str) -> Path:
    relative = Path(relative_text)
    if relative.is_absolute():
        raise ContractError("work-envelope working_directory must be relative to the factory root")
    target = (factory_root.resolve() / relative).resolve()
    if not target.is_relative_to(factory_root.resolve()):
        raise ContractError("work-envelope working_directory escapes the factory root")
    if not target.is_dir():
        raise ContractError("work-envelope working_directory does not exist")
    return target


def load_envelope_policy(path: Path, *, factory_root: Path) -> dict[str, Any]:
    policy = load_json(path)
    _validate_schema(policy, "work-order-envelope-policy-v2.schema.json")
    _verify_self_hash(policy, "policy_sha256")
    _resolve_working_directory(factory_root, policy["working_directory"])
    if "LOCAL_SUBPROCESS" not in policy["allowed_interfaces"]:
        raise ContractError("LOCAL_MONITORED_V1 requires the LOCAL_SUBPROCESS interface")
    required_stops = {
        "HUMAN_STOP_REQUESTED",
        "WALL_TIME_LIMIT_REACHED",
        "OUTPUT_LIMIT_REACHED",
        "PROCESS_EXITED",
        "PROCESS_LAUNCH_FAILED",
    }
    if not required_stops.issubset(policy["stop_conditions"]):
        raise ContractError("work-envelope policy omits a mandatory fail-closed stop condition")
    return policy


def build_envelope(
    *,
    envelope_id: str,
    policy: dict[str, Any],
    factory_id: str,
    round_id: str,
    round_sha256: str,
    work_unit_id: str,
    work_claim_id: str,
    operator_id: str,
    issued_by: str,
    issued_at: str,
    expires_at: str,
    release_capability_sha256: str,
) -> dict[str, Any]:
    unsigned = {
        "schema_version": 2,
        "envelope_type": "WORK_ORDER_ENVELOPE",
        "envelope_id": envelope_id,
        "policy_sha256": policy["policy_sha256"],
        "factory_id": factory_id,
        "round_id": round_id,
        "round_sha256": round_sha256,
        "work_unit_id": work_unit_id,
        "work_claim_id": work_claim_id,
        "operator_id": operator_id,
        "issued_by": issued_by,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "release_capability_sha256": release_capability_sha256,
        "scope": policy["scope"],
        "enforcement_profile": policy["enforcement_profile"],
        "allowed_command": policy["allowed_command"],
        "working_directory": policy["working_directory"],
        "allowed_interfaces": policy["allowed_interfaces"],
        "network_policy": policy["network_policy"],
        "resource_limits": policy["resource_limits"],
        "stop_conditions": policy["stop_conditions"],
        "extension_policy": policy["extension_policy"],
        "promotion_eligible": policy["promotion_eligible"],
    }
    envelope = {
        **unsigned,
        "envelope_sha256": sha256_bytes(canonical_json_bytes(unsigned)),
    }
    _validate_schema(envelope, "work-order-envelope-v2.schema.json")
    return envelope


def validate_envelope(envelope: dict[str, Any], *, factory_root: Path) -> None:
    document = {
        key: value
        for key, value in envelope.items()
        if key not in {"revoked_at", "revocation_reason"}
    }
    _validate_schema(document, "work-order-envelope-v2.schema.json")
    _verify_self_hash(document, "envelope_sha256")
    _resolve_working_directory(factory_root, document["working_directory"])
    if parse_utc(document["expires_at"], field="expires_at") <= parse_utc(
        document["issued_at"], field="issued_at"
    ):
        raise ContractError("work envelope must expire after it is issued")


def command_sha256(command: list[str]) -> str:
    return sha256_bytes(canonical_json_bytes(command))


def build_receipt(
    *,
    attempt_id: str,
    envelope: dict[str, Any],
    started_at: str,
    finished_at: str,
    exit_code: int | None,
    termination_reason: str,
    wall_seconds: float,
    output_bytes: int,
    stdout_sha256: str,
    stderr_sha256: str,
) -> dict[str, Any]:
    limits = envelope["resource_limits"]
    within = (
        termination_reason == "COMPLETED"
        and exit_code == 0
        and wall_seconds <= limits["max_wall_seconds"]
        and output_bytes <= limits["max_output_bytes"]
        and parse_utc(finished_at, field="finished_at")
        <= parse_utc(envelope["expires_at"], field="expires_at")
    )
    unsigned = {
        "schema_version": 2,
        "receipt_type": "MONITORED_ATTEMPT_EXECUTION",
        "attempt_id": attempt_id,
        "envelope_id": envelope["envelope_id"],
        "envelope_sha256": envelope["envelope_sha256"],
        "operator_id": envelope["operator_id"],
        "started_at": started_at,
        "finished_at": finished_at,
        "command_sha256": command_sha256(envelope["allowed_command"]),
        "working_directory": envelope["working_directory"],
        "exit_code": exit_code,
        "termination_reason": termination_reason,
        "wall_seconds": round(max(0.0, wall_seconds), 6),
        "output_bytes": output_bytes,
        "stdout_sha256": stdout_sha256,
        "stderr_sha256": stderr_sha256,
        "cost_minor_units": 0,
        "currency": limits["currency"],
        "network_enforcement": "NOT_VERIFIED_LOCAL_PROFILE",
        "within_envelope": within,
        "promotion_eligible": False,
    }
    receipt = {**unsigned, "receipt_sha256": sha256_bytes(canonical_json_bytes(unsigned))}
    _validate_schema(receipt, "attempt-receipt-v2.schema.json")
    return receipt


def validate_receipt(
    receipt: dict[str, Any],
    *,
    envelope: dict[str, Any],
    attempt_id: str,
    factory_root: Path,
) -> None:
    _validate_schema(receipt, "attempt-receipt-v2.schema.json")
    _verify_self_hash(receipt, "receipt_sha256")
    validate_envelope(envelope, factory_root=factory_root)
    expected = {
        "attempt_id": attempt_id,
        "envelope_id": envelope["envelope_id"],
        "envelope_sha256": envelope["envelope_sha256"],
        "operator_id": envelope["operator_id"],
        "command_sha256": command_sha256(envelope["allowed_command"]),
        "working_directory": envelope["working_directory"],
        "currency": envelope["resource_limits"]["currency"],
    }
    for field, value in expected.items():
        if receipt.get(field) != value:
            raise ContractError(f"attempt receipt is not bound to the envelope field {field}")
    started = parse_utc(receipt["started_at"], field="started_at")
    finished = parse_utc(receipt["finished_at"], field="finished_at")
    if finished < started:
        raise ContractError("attempt receipt finished_at precedes started_at")
    limits = envelope["resource_limits"]
    derived_within = (
        receipt["termination_reason"] == "COMPLETED"
        and receipt["exit_code"] == 0
        and receipt["wall_seconds"] <= limits["max_wall_seconds"]
        and receipt["output_bytes"] <= limits["max_output_bytes"]
        and finished <= parse_utc(envelope["expires_at"], field="expires_at")
    )
    if receipt["within_envelope"] is not derived_within:
        raise ContractError("attempt receipt within_envelope flag is inconsistent with its measurements")


def _minimal_environment() -> dict[str, str]:
    environment = {
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
    }
    for name in ("SYSTEMROOT", "WINDIR", "COMSPEC", "TMP", "TEMP"):
        if os.environ.get(name):
            environment[name] = os.environ[name]
    return environment


def execute_local_monitored(
    *,
    envelope: dict[str, Any],
    attempt_id: str,
    factory_root: Path,
    stop_requested: Callable[[], bool] | None = None,
    timestamp_clock: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Run one commissioning command under measurable local limits.

    This profile controls exact argv, cwd, wall time and combined output size.
    It deliberately does not claim filesystem, memory, network or child-process
    isolation and is therefore never promotion eligible.
    """

    validate_envelope(envelope, factory_root=factory_root)
    cwd = _resolve_working_directory(factory_root, envelope["working_directory"])
    declared = envelope["allowed_command"]
    command = [sys.executable if token == "{python}" else token for token in declared]
    limits = envelope["resource_limits"]
    started_clock = time.monotonic()
    started_at = (timestamp_clock or (lambda: datetime.now(timezone.utc)))()
    if started_at.tzinfo is None:
        raise ContractError("executor timestamp clock must be timezone aware")
    termination_reason = "LAUNCH_ERROR"
    exit_code: int | None = None

    with tempfile.TemporaryDirectory(prefix="research-factory-envelope-") as temporary:
        stdout_path = Path(temporary) / "stdout.bin"
        stderr_path = Path(temporary) / "stderr.bin"
        try:
            with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
                process = subprocess.Popen(
                    command,
                    cwd=cwd,
                    env=_minimal_environment(),
                    stdin=subprocess.DEVNULL,
                    stdout=stdout,
                    stderr=stderr,
                    shell=False,
                )
                while process.poll() is None:
                    elapsed = time.monotonic() - started_clock
                    output_bytes = stdout_path.stat().st_size + stderr_path.stat().st_size
                    if stop_requested is not None and stop_requested():
                        termination_reason = "HUMAN_STOP"
                    elif elapsed >= limits["max_wall_seconds"]:
                        termination_reason = "WALL_TIME_LIMIT"
                    elif output_bytes > limits["max_output_bytes"]:
                        termination_reason = "OUTPUT_LIMIT"
                    else:
                        time.sleep(0.05)
                        continue
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=2)
                exit_code = process.returncode
                if termination_reason == "LAUNCH_ERROR":
                    termination_reason = "COMPLETED" if exit_code == 0 else "PROCESS_ERROR"
        except OSError:
            termination_reason = "LAUNCH_ERROR"

        wall_seconds = time.monotonic() - started_clock
        finished_at = started_at + timedelta(seconds=wall_seconds)
        if not stdout_path.exists():
            stdout_path.write_bytes(b"")
        if not stderr_path.exists():
            stderr_path.write_bytes(b"")
        output_bytes = stdout_path.stat().st_size + stderr_path.stat().st_size
        return build_receipt(
            attempt_id=attempt_id,
            envelope=envelope,
            started_at=utc_text(started_at),
            finished_at=utc_text(finished_at),
            exit_code=exit_code,
            termination_reason=termination_reason,
            wall_seconds=wall_seconds,
            output_bytes=output_bytes,
            stdout_sha256=sha256_file(stdout_path),
            stderr_sha256=sha256_file(stderr_path),
        )
