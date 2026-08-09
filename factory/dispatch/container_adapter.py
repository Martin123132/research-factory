"""Fail-closed, commissioning-only Docker adapter for dispatch budgets.

This adapter is deliberately narrower than a general container launcher.  It
accepts an already-authorised immutable ticket, a digest-pinned image and a
canonical exact-command manifest; it never accepts a shell string, a floating
image tag, network access, a GPU, or a request to promote output.  A host that
cannot apply the required Docker flags is rejected before the workload starts.

Container isolation is a useful enforcement mechanism, not proof of scientific
correctness, independent reproduction, human identity, or safe execution on an
untrusted Docker daemon.  Those boundaries remain outside this adapter.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Callable, Sequence

from jsonschema import Draft202012Validator

from control_plane.common import (
    ContractError,
    canonical_json_bytes,
    parse_utc,
    sha256_bytes,
    utc_text,
    validate_id,
)

from .gate import PROFILE_CONTAINER, DispatchBudgetGate, load_json_strict


SCHEMAS = Path(__file__).resolve().parent
DOCKER_BINARY = "docker"
POLL_SECONDS = 0.1
SUPPORTED_HAZARDS = {"NONE", "UNTRUSTED_SOFTWARE"}
REQUIRED_INTERFACES = {
    "LOCAL_SUBPROCESS",
    "DECLARED_INPUT_FILES",
    "DECLARED_OUTPUT_FILES",
}
OUTPUT_PROTOCOL_WORKDIR_COPY = "WORKDIR_COPY_V1"
OUTPUT_PROTOCOL_STDOUT_ARTIFACT = "STDOUT_ARTIFACT_V1"
STDOUT_ARTIFACT_PREFIX = b"FACTORY_STDOUT_ARTIFACT_V1:"
STDOUT_ARTIFACT_FILENAME = "stdout-artifact.bin"
RECEIPT_KEYS = {
    "schema_version",
    "receipt_type",
    "receipt_id",
    "created_at",
    "request_sha256",
    "budget_sha256",
    "ticket_sha256",
    "container_name",
    "started",
    "exit_code",
    "stop_conditions_triggered",
    "output_bytes",
    "work_bytes",
    "log_bytes",
    "output_protocol",
    "artifact_bytes",
    "artifact_sha256",
    "output_path",
    "output_sha256",
    "scientific_standing",
    "promotion_eligible",
    "limitations",
    "receipt_sha256",
}


def _write_json_exclusive(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
    except FileExistsError as exc:
        raise ContractError(f"container receipt destination already exists: {path}") from exc


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key!r}")
        value[key] = item
    return value


def _load_schema() -> Draft202012Validator:
    path = SCHEMAS / "container-run-request-v1.schema.json"
    try:
        schema = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
        Draft202012Validator.check_schema(schema)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ContractError(f"container request schema cannot be loaded: {exc}") from exc
    return Draft202012Validator(schema)


REQUEST_VALIDATOR = _load_schema()


def _validate_schema(value: dict[str, Any]) -> None:
    errors = sorted(
        REQUEST_VALIDATOR.iter_errors(value),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        error = errors[0]
        location = "/".join(str(part) for part in error.absolute_path) or "$"
        raise ContractError(f"container dispatch request schema violation at {location}: {error.message}")


def _verify_self_hash(document: dict[str, Any], field: str) -> None:
    expected = document.get(field)
    unsigned = {key: value for key, value in document.items() if key != field}
    actual = sha256_bytes(canonical_json_bytes(unsigned))
    if expected != actual:
        raise ContractError(f"{field} does not match the canonical document")


def _safe_repository_path(value: str, *, field: str) -> PurePosixPath:
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
    sensitive = {"private", "secret", "secrets", "credential", "credentials", "hidden", "holdout", "holdouts", "key", "keys"}
    if any(part.casefold() in sensitive or part.casefold().startswith(".env") for part in path.parts):
        raise ContractError(f"{field} cannot grant protected or hidden material")
    return path


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _path_is_within_any(path: PurePosixPath, roots: list[str]) -> bool:
    return any(path == PurePosixPath(root) or PurePosixPath(root) in path.parents for root in roots)


def _directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for item in path.rglob("*"):
        if item.is_symlink():
            raise ContractError(f"container output contains a symbolic link: {item.name}")
        if item.is_file():
            total += item.stat().st_size
    return total


def _file_size(path: Path) -> int:
    return path.stat().st_size if path.exists() else 0


def _tree_sha256(path: Path) -> str:
    """Hash a closed output tree with its relative paths and file bytes."""

    rows: list[dict[str, Any]] = []
    for item in sorted(path.rglob("*"), key=lambda value: value.as_posix()):
        if item.is_symlink():
            raise ContractError(f"container output contains a symbolic link: {item.name}")
        if item.is_file():
            relative = item.relative_to(path).as_posix()
            rows.append({"path": relative, "sha256": sha256_bytes(item.read_bytes()), "bytes": item.stat().st_size})
    return sha256_bytes(canonical_json_bytes(rows))


def _command_manifest(
    image_ref: str,
    argv: Sequence[str],
    output_protocol: str,
) -> dict[str, Any]:
    return {
        "image_ref": image_ref,
        "argv": list(argv),
        "output_protocol": output_protocol,
    }


def _work_output_limit(budget: dict[str, Any]) -> int:
    return min(
        budget["compute_budget"]["max_storage_bytes"],
        budget["compute_budget"]["max_output_bytes"] // 2,
    )


def _stdout_artifact_raw_limit(artifact_limit: int) -> int:
    """Bound one ASCII base64 packet plus its fixed prefix and newline."""

    return len(STDOUT_ARTIFACT_PREFIX) + 4 * ((artifact_limit + 2) // 3) + 1


def _decode_stdout_artifact(stdout: bytes, *, artifact_limit: int) -> bytes:
    if not stdout.startswith(STDOUT_ARTIFACT_PREFIX) or not stdout.endswith(b"\n"):
        raise ContractError("stdout artifact must be one framed FACTORY_STDOUT_ARTIFACT_V1 packet")
    encoded = stdout[len(STDOUT_ARTIFACT_PREFIX) : -1]
    if not encoded or b"\n" in encoded or b"\r" in encoded:
        raise ContractError("stdout artifact packet must contain one non-empty base64 line")
    try:
        artifact = base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise ContractError("stdout artifact packet is not valid base64") from exc
    if not artifact or len(artifact) > artifact_limit:
        raise ContractError("stdout artifact exceeds its immutable bounded artifact ceiling")
    return artifact


def _capture_stdout_artifact(
    stdout_path: Path,
    destination: Path,
    *,
    artifact_limit: int,
) -> tuple[int, str]:
    artifact = _decode_stdout_artifact(stdout_path.read_bytes(), artifact_limit=artifact_limit)
    artifact_path = destination / STDOUT_ARTIFACT_FILENAME
    with artifact_path.open("xb") as handle:
        handle.write(artifact)
    artifact_sha256 = sha256_bytes(artifact)
    stdout_path.write_bytes(
        f"FACTORY_STDOUT_ARTIFACT_V1_CAPTURED sha256:{artifact_sha256} bytes:{len(artifact)}\n".encode(
            "ascii"
        )
    )
    return len(artifact), artifact_sha256


def validate_request(
    request: dict[str, Any],
    *,
    budget: dict[str, Any],
    ticket: dict[str, Any],
    factory_root: Path,
    output_must_be_new: bool = True,
) -> dict[str, Any]:
    """Validate the request against immutable gate artifacts and local paths."""

    _validate_schema(request)
    _verify_self_hash(request, "request_sha256")
    validate_id(request["request_id"], field="request_id")
    if request["budget_sha256"] != budget["budget_sha256"]:
        raise ContractError("container request is bound to a different budget")
    if request["ticket_sha256"] != ticket["ticket_sha256"]:
        raise ContractError("container request is bound to a different ticket")
    if ticket["profile"]["profile_id"] != PROFILE_CONTAINER or not ticket["authorized"]:
        raise ContractError("container adapter requires an authorised container-profile ticket")
    if ticket["authorization_scope"] != "PROCESS_EXECUTION":
        raise ContractError("container adapter ticket has no process-execution scope")
    if budget["requested_execution_mode"] != "PROCESS_EXECUTION":
        raise ContractError("container adapter requires a process-execution budget")

    interfaces = set(budget["interface_budget"]["allowed_interfaces"])
    if interfaces != REQUIRED_INTERFACES:
        raise ContractError("container adapter accepts only the three declared local container interfaces")
    if budget["interface_budget"]["shell_policy"] != "EXACT_COMMAND_ONLY":
        raise ContractError("container adapter requires EXACT_COMMAND_ONLY")
    if not budget["interface_budget"]["allowed_tool_manifest_sha256"]:
        raise ContractError("container adapter requires an allowlisted exact-command manifest")
    manifest_hash = sha256_bytes(
        canonical_json_bytes(
            _command_manifest(request["image_ref"], request["argv"], request["output_protocol"])
        )
    )
    if manifest_hash not in budget["interface_budget"]["allowed_tool_manifest_sha256"]:
        raise ContractError("container exact-command manifest is not allowlisted by the budget")

    if budget["data_budget"]["network_policy"] != "DENY_ALL" or budget["data_budget"]["allowed_domains"]:
        raise ContractError("container adapter supports only DENY_ALL network budgets")
    if budget["financial_budget"]["max_minor_units"] != 0:
        raise ContractError("container adapter supports only zero-cost external-service budgets")
    if budget["financial_budget"]["allowed_billable_services"]:
        raise ContractError("container adapter cannot allow billable services")
    if budget["compute_budget"]["max_gpu_seconds"] != 0:
        raise ContractError("container adapter provides no GPU execution")
    for field in (
        "max_cpu_seconds",
        "max_memory_bytes",
        "max_storage_bytes",
        "max_output_bytes",
        "max_processes",
    ):
        if budget["compute_budget"][field] < 1:
            raise ContractError(f"container adapter requires a positive {field}")
    for field in ("max_wall_seconds", "max_active_seconds", "max_idle_seconds"):
        if budget["time_budget"][field] < 1:
            raise ContractError(f"container adapter requires a positive {field}")
    if budget["hazard_budget"]["classification"] not in SUPPORTED_HAZARDS:
        raise ContractError("container adapter supports only NONE or UNTRUSTED_SOFTWARE hazards")
    if budget["hazard_budget"]["classification"] == "UNTRUSTED_SOFTWARE" and not budget["hazard_budget"]["human_review_required"]:
        raise ContractError("UNTRUSTED_SOFTWARE requires the budget's hash-bound human review")
    if budget["time_budget"]["max_shift_count"] != 1:
        raise ContractError("container adapter executes exactly one bounded shift")
    if request["output_protocol"] not in {
        OUTPUT_PROTOCOL_WORKDIR_COPY,
        OUTPUT_PROTOCOL_STDOUT_ARTIFACT,
    }:
        raise ContractError("container adapter received an unknown output protocol")

    output = _safe_repository_path(request["output_path"], field="output_path")
    write_paths = budget["data_budget"]["write_paths"]
    if not _path_is_within_any(output, write_paths):
        raise ContractError("container output_path is outside the immutable write allowlist")
    root = factory_root.resolve()
    destination = (root / output).resolve()
    if not _is_within(destination, root):
        raise ContractError("container output_path escaped the factory root")
    if output_must_be_new and destination.exists():
        raise ContractError("container output_path must not already exist")
    for read_path in budget["data_budget"]["read_paths"]:
        source = (root / _safe_repository_path(read_path, field="read_path")).resolve()
        if not source.is_dir() and not source.is_file():
            raise ContractError(f"declared container input does not exist: {read_path}")
        if not _is_within(source, root):
            raise ContractError(f"declared container input escaped the factory root: {read_path}")
    return request


def build_docker_command(
    request: dict[str, Any],
    *,
    budget: dict[str, Any],
    factory_root: Path,
    container_name: str,
) -> list[str]:
    """Build the exact no-network, no-GPU, read-only Docker invocation.

    Work and captured output share a bounded tmpfs.  Its ceiling is conservatively
    lower than both the storage and total-output ceilings, reserving the remaining
    output allowance for stdout/stderr captured by this parent process.
    """

    output_limit = budget["compute_budget"]["max_output_bytes"]
    storage_limit = budget["compute_budget"]["max_storage_bytes"]
    if output_limit < 2 or storage_limit < 1:
        raise ContractError("container adapter requires at least two output bytes and one storage byte")
    work_limit = min(storage_limit, output_limit // 2)
    root = factory_root.resolve()
    command = [
        DOCKER_BINARY,
        "run",
        "--name",
        container_name,
        "--pull",
        "never",
        "--read-only",
        "--network",
        "none",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--pids-limit",
        str(budget["compute_budget"]["max_processes"]),
        "--memory",
        str(budget["compute_budget"]["max_memory_bytes"]),
        "--ulimit",
        f"cpu={budget['compute_budget']['max_cpu_seconds']}",
        "--tmpfs",
        f"/work:rw,noexec,nosuid,uid=65534,gid=65534,size={work_limit}",
        "--workdir",
        "/work",
        "--user",
        "65534:65534",
    ]
    for index, relative in enumerate(budget["data_budget"]["read_paths"]):
        source = (root / relative).resolve()
        command.extend(["--mount", f"type=bind,src={source},dst=/inputs/{index},readonly"])
    command.extend([request["image_ref"], *request["argv"]])
    return command


def inspect_host(*, docker: str = DOCKER_BINARY) -> dict[str, Any]:
    """Check only prerequisites that can be checked without creating a container."""

    executable = shutil.which(docker)
    if executable is None:
        return {
            "ready": False,
            "reason": "DOCKER_NOT_FOUND",
            "limitations": ["Docker is unavailable; no workload can start."],
        }
    try:
        completed = subprocess.run(
            [docker, "version", "--format", "{{.Server.Version}}"],
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "ready": False,
            "reason": "DOCKER_DAEMON_UNAVAILABLE",
            "limitations": [f"Docker could not be queried: {exc}"],
        }
    if completed.returncode != 0 or not completed.stdout.strip():
        return {
            "ready": False,
            "reason": "DOCKER_DAEMON_UNAVAILABLE",
            "limitations": ["Docker did not expose a usable local server version."],
        }
    return {
        "ready": True,
        "reason": "READY",
        "server_version": completed.stdout.strip(),
        "limitations": [
            "This verifies only Docker availability; a run still fails closed if its digest-pinned image or required flags are unavailable.",
            "A Docker daemon is part of the trusted computing base and is not independently attested by this adapter.",
        ],
    }


def _terminate_container(container_name: str) -> None:
    subprocess.run(
        [DOCKER_BINARY, "kill", container_name],
        text=True,
        encoding="utf-8",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=15,
        check=False,
    )


def _remove_container(container_name: str) -> None:
    subprocess.run(
        [DOCKER_BINARY, "rm", "-f", container_name],
        text=True,
        encoding="utf-8",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=15,
        check=False,
    )


def _copy_container_work(container_name: str, destination: Path) -> None:
    completed = subprocess.run(
        [DOCKER_BINARY, "cp", f"{container_name}:/work/.", str(destination)],
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        raise ContractError("container output could not be copied into the declared output path")


def run_container(
    request: dict[str, Any],
    *,
    budget: dict[str, Any],
    ticket: dict[str, Any],
    factory_root: Path,
    release_capability: str,
    stop_file: Path,
    receipt_output: Path,
    now: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Run one exact command, or fail before start, and write a closed receipt.

    The release value is deliberately consumed in memory only.  A matching hash
    shows that the retained capability was supplied; it cannot prove who supplied
    it, so the receipt never upgrades the identity or scientific boundary.
    """

    root = factory_root.resolve()
    gate = DispatchBudgetGate(root)
    gate.validate_budget(budget)
    gate.validate_ticket(ticket, budget=budget)
    validate_request(request, budget=budget, ticket=ticket, factory_root=root)
    if sha256_bytes(release_capability.encode("utf-8")) != ticket["release_capability_sha256"]:
        raise ContractError("human release capability was withheld or does not match the ticket")
    if stop_file.exists():
        raise ContractError("human stop was requested before the container could start")
    host = inspect_host()
    if not host["ready"]:
        raise ContractError(f"container host is not ready: {host['reason']}")

    created = utc_text(datetime.now(timezone.utc))
    active_at = parse_utc(ticket["created_at"], field="ticket.created_at")
    expires_at = parse_utc(budget["time_budget"]["expires_at"], field="expires_at")
    if parse_utc(created, field="created_at") >= expires_at or active_at >= expires_at:
        raise ContractError("container ticket is outside its immutable budget window")

    receipt_output = receipt_output.resolve()
    if receipt_output.exists():
        raise ContractError(f"container receipt destination already exists: {receipt_output}")
    destination = (root / request["output_path"]).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise ContractError("container output_path became occupied before launch")

    container_name = f"factory-{uuid.uuid4().hex}"
    command = build_docker_command(
        request, budget=budget, factory_root=root, container_name=container_name
    )
    work_limit = _work_output_limit(budget)
    log_limit = (
        _stdout_artifact_raw_limit(work_limit)
        if request["output_protocol"] == OUTPUT_PROTOCOL_STDOUT_ARTIFACT
        else budget["compute_budget"]["max_output_bytes"] - work_limit
    )
    stop_reasons: list[str] = []
    started = False
    exit_code: int | None = None
    logs_directory = Path(tempfile.mkdtemp(prefix="factory-container-logs-"))
    stdout_path = logs_directory / "stdout.log"
    stderr_path = logs_directory / "stderr.log"
    began = now()
    try:
        with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
            process = subprocess.Popen(command, stdout=stdout, stderr=stderr, shell=False)
            started = True
            last_log_bytes = 0
            last_activity = began
            while process.poll() is None:
                elapsed = now() - began
                log_bytes = _file_size(stdout_path) + _file_size(stderr_path)
                if log_bytes != last_log_bytes:
                    last_log_bytes = log_bytes
                    last_activity = now()
                if stop_file.exists():
                    stop_reasons.append("HUMAN_STOP_REQUESTED")
                elif elapsed >= budget["time_budget"]["max_wall_seconds"]:
                    stop_reasons.append("WALL_TIME_LIMIT_REACHED")
                elif elapsed >= budget["time_budget"]["max_active_seconds"]:
                    stop_reasons.append("ACTIVE_TIME_LIMIT_REACHED")
                elif now() - last_activity >= budget["time_budget"]["max_idle_seconds"]:
                    stop_reasons.append("IDLE_TIME_LIMIT_REACHED")
                elif log_bytes > log_limit:
                    stop_reasons.append("OUTPUT_LIMIT_REACHED")
                if stop_reasons:
                    _terminate_container(container_name)
                    break
                sleeper(POLL_SECONDS)
            exit_code = process.wait(timeout=20)
        if not stop_reasons:
            stop_reasons.append("PROCESS_EXITED")
        if _file_size(stdout_path) + _file_size(stderr_path) > log_limit:
            raise ContractError("container raw output exceeded the immutable output ceiling")

        destination.mkdir()
        artifact_bytes: int | None = None
        artifact_sha256: str | None = None
        if request["output_protocol"] == OUTPUT_PROTOCOL_WORKDIR_COPY:
            _copy_container_work(container_name, destination)
        else:
            artifact_bytes, artifact_sha256 = _capture_stdout_artifact(
                stdout_path,
                destination,
                artifact_limit=work_limit,
            )
        work_bytes = _directory_size(destination)
        log_bytes = _file_size(stdout_path) + _file_size(stderr_path)
        output_bytes = work_bytes + log_bytes
        if work_bytes > work_limit:
            raise ContractError("container work output exceeded the bounded tmpfs allocation")
        if output_bytes > budget["compute_budget"]["max_output_bytes"]:
            raise ContractError("container output exceeded the immutable output ceiling")
        shutil.copy2(stdout_path, destination / "stdout.log")
        shutil.copy2(stderr_path, destination / "stderr.log")
        output_sha256 = _tree_sha256(destination)
        receipt_unsigned = {
            "schema_version": 1,
            "receipt_type": "CONTAINER_DISPATCH_RECEIPT",
            "receipt_id": f"container-receipt:{uuid.uuid4().hex}",
            "created_at": utc_text(datetime.now(timezone.utc)),
            "request_sha256": request["request_sha256"],
            "budget_sha256": budget["budget_sha256"],
            "ticket_sha256": ticket["ticket_sha256"],
            "container_name": container_name,
            "started": started,
            "exit_code": exit_code,
            "stop_conditions_triggered": stop_reasons,
            "output_bytes": output_bytes,
            "work_bytes": work_bytes,
            "log_bytes": log_bytes,
            "output_protocol": request["output_protocol"],
            "artifact_bytes": artifact_bytes,
            "artifact_sha256": artifact_sha256,
            "output_path": request["output_path"],
            "output_sha256": output_sha256,
            "scientific_standing": "NONE_CONTAINER_COMMISSIONING_ONLY",
            "promotion_eligible": False,
            "limitations": [
                "A successful command is not scientific evidence or independent reproduction.",
                "The retained release capability does not prove the identity or independence of its holder.",
                "Docker daemon, kernel and host configuration remain trusted computing-base assumptions.",
            ],
        }
        receipt = {**receipt_unsigned, "receipt_sha256": sha256_bytes(canonical_json_bytes(receipt_unsigned))}
        if set(receipt) != RECEIPT_KEYS:
            raise ContractError("container receipt implementation has an invalid closed shape")
        _write_json_exclusive(receipt_output, receipt)
        return receipt
    except (OSError, subprocess.SubprocessError) as exc:
        if started:
            _terminate_container(container_name)
        raise ContractError(f"container execution failed closed: {exc}") from exc
    finally:
        _remove_container(container_name)
        shutil.rmtree(logs_directory, ignore_errors=True)


def verify_receipt(
    receipt: dict[str, Any],
    *,
    request: dict[str, Any],
    budget: dict[str, Any],
    ticket: dict[str, Any],
    factory_root: Path,
) -> dict[str, Any]:
    """Verify the preserved local outputs without trusting the receipt author."""

    if set(receipt) != RECEIPT_KEYS:
        raise ContractError("container receipt has an invalid closed shape")
    _verify_self_hash(receipt, "receipt_sha256")
    if receipt["receipt_type"] != "CONTAINER_DISPATCH_RECEIPT" or receipt["schema_version"] != 1:
        raise ContractError("container receipt has the wrong type or version")
    validate_request(
        request,
        budget=budget,
        ticket=ticket,
        factory_root=factory_root,
        output_must_be_new=False,
    )
    expected = {
        "request_sha256": request["request_sha256"],
        "budget_sha256": budget["budget_sha256"],
        "ticket_sha256": ticket["ticket_sha256"],
        "output_path": request["output_path"],
        "output_protocol": request["output_protocol"],
    }
    for field, value in expected.items():
        if receipt[field] != value:
            raise ContractError(f"container receipt differs from its input at {field}")
    if receipt["scientific_standing"] != "NONE_CONTAINER_COMMISSIONING_ONLY":
        raise ContractError("container receipt claims scientific standing")
    if receipt["promotion_eligible"] is not False:
        raise ContractError("container receipt claims promotion eligibility")
    output = (factory_root.resolve() / receipt["output_path"]).resolve()
    if not output.is_dir():
        raise ContractError("container receipt output directory is missing")
    work_bytes = _directory_size(output)
    if work_bytes != receipt["output_bytes"]:
        raise ContractError("container receipt output byte count no longer matches")
    if _tree_sha256(output) != receipt["output_sha256"]:
        raise ContractError("container receipt output hash no longer matches")
    if receipt["work_bytes"] + receipt["log_bytes"] != receipt["output_bytes"]:
        raise ContractError("container receipt output accounting is inconsistent")
    if receipt["output_bytes"] > budget["compute_budget"]["max_output_bytes"]:
        raise ContractError("container receipt exceeds its immutable output ceiling")
    if receipt["output_protocol"] == OUTPUT_PROTOCOL_STDOUT_ARTIFACT:
        artifact = output / STDOUT_ARTIFACT_FILENAME
        if not artifact.is_file() or artifact.stat().st_size != receipt["artifact_bytes"]:
            raise ContractError("container stdout artifact is missing or has the wrong byte count")
        if sha256_bytes(artifact.read_bytes()) != receipt["artifact_sha256"]:
            raise ContractError("container stdout artifact hash no longer matches")
    elif receipt["artifact_bytes"] is not None or receipt["artifact_sha256"] is not None:
        raise ContractError("workdir-copy receipt cannot claim a stdout artifact")
    return {
        "valid": True,
        "receipt_sha256": receipt["receipt_sha256"],
        "output_sha256": receipt["output_sha256"],
        "scientific_standing": "NONE_CONTAINER_COMMISSIONING_ONLY",
        "promotion_eligible": False,
    }


def load_request(path: Path) -> dict[str, Any]:
    return load_json_strict(path)
