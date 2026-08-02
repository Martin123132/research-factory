from __future__ import annotations

import argparse
import dataclasses
import json
import re
import shutil
import subprocess
import threading
import time
import tomllib
import uuid
from pathlib import Path
from typing import Any

from common import (
    WORKBENCH_ROOT,
    ContractError,
    canonical_json_bytes,
    load_json,
    sha256_bytes,
    sha256_file,
    write_json,
)
from evaluate_local import CandidateExecutionError, CandidateExecutor, evaluate_submission
from process_control import ProcessOutcome, run_process


MEMORY_RE = re.compile(r"^\s*([0-9.]+)\s*([KMGTP]?i?B)\s*$", re.IGNORECASE)


def verify_image_lock(lock: dict[str, Any], policy_path: Path) -> None:
    expected = lock.get("image_lock_sha256")
    unsigned = {key: value for key, value in lock.items() if key != "image_lock_sha256"}
    if expected != sha256_bytes(canonical_json_bytes(unsigned)):
        raise ContractError("Docker image lock hash does not match its contents")
    isolation_root = policy_path.resolve().parent
    checks = {
        "policy_sha256": policy_path,
        "dockerfile_sha256": isolation_root / "Dockerfile",
        "requirements_sha256": isolation_root / "requirements.docker.lock",
    }
    for field, path in checks.items():
        if lock.get(field) != sha256_file(path):
            raise ContractError(f"Docker image lock no longer matches {path.name}")


def load_policy(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            policy = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ContractError(f"could not load Docker policy: {exc}") from exc
    if policy.get("schema_version") != 1:
        raise ContractError("unsupported Docker policy schema")
    return policy


def memory_bytes(value: str) -> int:
    match = MEMORY_RE.match(value)
    if not match:
        return 0
    amount = float(match.group(1))
    unit = match.group(2).lower()
    powers = {"b": 0, "kb": 1, "kib": 1, "mb": 2, "mib": 2, "gb": 3, "gib": 3, "tb": 4, "tib": 4}
    return int(amount * (1024 ** powers.get(unit, 0)))


def docker_mount(source: Path, target: str, *, read_only: bool) -> str:
    value = f"type=bind,source={source.resolve()},target={target}"
    return f"{value},readonly" if read_only else value


def build_docker_command(
    *,
    policy: dict[str, Any],
    image_id: str,
    container_name: str,
    session_label: str,
    candidate_root: Path,
    corpus_root: Path,
    work_root: Path,
    candidate_command: list[str],
    include_data_mounts: bool,
) -> list[str]:
    limits = policy["limits"]
    mounts = policy["mounts"]
    command = [
        "docker",
        "run",
        "--rm",
        "--pull",
        "never",
        "--name",
        container_name,
        "--label",
        f"research-factory.session={session_label}",
        "--label",
        "research-factory.workbench=WB-001",
        "--network",
        policy["network"],
        "--read-only",
        "--cap-drop",
        policy["cap_drop"],
        "--security-opt",
        f"no-new-privileges={str(policy['no_new_privileges']).lower()}",
        "--security-opt",
        f"seccomp={policy['seccomp']}",
        "--user",
        policy["candidate_user"],
        "--pids-limit",
        str(limits["pids"]),
        "--memory",
        limits["memory"],
        "--memory-swap",
        limits["memory_swap"],
        "--cpus",
        str(limits["cpus"]),
        "--ulimit",
        f"core={limits['core_ulimit']}",
        "--ulimit",
        f"nofile={limits['nofile_ulimit']}",
        "--ulimit",
        f"nproc={limits['nproc_ulimit']}",
        "--ipc",
        policy["ipc"],
        "--cgroupns",
        policy["cgroup_namespace"],
        "--hostname",
        policy["hostname"],
        "--tmpfs",
        limits["tmpfs"],
        "--stop-timeout",
        str(limits["stop_timeout_seconds"]),
        "--env",
        "HOME=/tmp",
        "--env",
        "TMPDIR=/tmp",
        "--env",
        "PYTHONDONTWRITEBYTECODE=1",
        "--mount",
        docker_mount(candidate_root, mounts["candidate"], read_only=True),
        "--workdir",
        mounts["candidate"],
    ]
    if include_data_mounts:
        command.extend(
            [
                "--mount",
                docker_mount(corpus_root, mounts["corpus"], read_only=True),
                "--mount",
                docker_mount(work_root, mounts["work"], read_only=False),
            ]
        )
    command.extend([image_id, *candidate_command])
    return command


class DockerCandidateExecutor:
    def __init__(
        self,
        *,
        submission_path: Path,
        submission: dict[str, Any],
        artifact: dict[str, Any],
        corpus_root: Path,
        temp_root: Path,
        config: dict[str, Any],
        policy_path: Path,
        lock_path: Path,
    ) -> None:
        self.policy_path = policy_path.resolve()
        self.policy = load_policy(self.policy_path)
        self.lock = load_json(lock_path.resolve())
        verify_image_lock(self.lock, self.policy_path)
        self.image_id = self.lock["image_id"]
        self.corpus_root = corpus_root.resolve()
        self.work_root = (temp_root / "work").resolve()
        self.work_root.mkdir(exist_ok=True)
        self.candidate_root = (temp_root / "candidate").resolve()
        self.candidate_root.mkdir()
        self.timeout_seconds = float(config["measurement"]["per_operation_timeout_seconds"])
        self.output_limit_bytes = min(
            int(config["measurement"]["stdout_stderr_limit_bytes"]),
            int(self.policy["limits"]["stdout_stderr_bytes"]),
        )
        self.session_label = uuid.uuid4().hex
        self.active_names: set[str] = set()

        source_root = submission_path.parent.resolve()
        manifest_rows = {row["path"]: row for row in artifact["source_files"]}
        for relative, expected in manifest_rows.items():
            source = (source_root / relative).resolve()
            destination = (self.candidate_root / relative).resolve()
            if not destination.is_relative_to(self.candidate_root):
                raise ContractError(f"staged candidate path escapes its root: {relative}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            if destination.is_symlink() or sha256_file(destination) != expected["sha256"]:
                raise ContractError(f"candidate changed while being staged: {relative}")

        raw_command = submission["candidate"]["command"]
        self.candidate_command = ["python" if token == "{python}" else token for token in raw_command]
        self._verify_daemon_image()
        self.boundary = {
            "mode": "docker-desktop-linux",
            "security_boundary": True,
            "promotion_grade": bool(self.lock["promotion_grade"]),
            "timing_grade": "container-startup-included-correctness-only",
            "image_id": self.image_id,
            "image_lock_sha256": self.lock["image_lock_sha256"],
            "policy_id": self.policy["policy_id"],
            "policy_sha256": self.lock["policy_sha256"],
            "network": self.policy["network"],
            "read_only_root": bool(self.policy["read_only_root"]),
            "boundary_note": self.lock["boundary_note"],
        }

    def _verify_daemon_image(self) -> None:
        try:
            completed = subprocess.run(
                ["docker", "image", "inspect", self.image_id, "--format", "{{.Id}}"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ContractError(f"Docker daemon is unavailable: {exc}") from exc
        if completed.returncode != 0 or completed.stdout.strip() != self.image_id:
            raise ContractError("locked Docker image is not present in the active daemon")

    def _container_path(self, host_path: Path, *, output: bool) -> str:
        resolved = host_path.resolve()
        if resolved.is_relative_to(self.work_root):
            relative = resolved.relative_to(self.work_root).as_posix()
            return f"{self.policy['mounts']['work']}/{relative}"
        if not output and resolved.is_relative_to(self.corpus_root):
            relative = resolved.relative_to(self.corpus_root).as_posix()
            return f"{self.policy['mounts']['corpus']}/{relative}"
        raise ContractError(f"batch path is outside its permitted mount: {host_path}")

    def _rewrite_job(self, host_job_path: Path) -> str:
        job = load_json(host_job_path)
        rewritten = {
            "schema_version": job["schema_version"],
            "operation": job["operation"],
            "items": [
                {
                    "input": self._container_path(Path(item["input"]), output=False),
                    "output": self._container_path(Path(item["output"]), output=True),
                }
                for item in job["items"]
            ],
        }
        destination = self.work_root / f"container-job-{uuid.uuid4().hex}.json"
        write_json(destination, rewritten)
        return f"{self.policy['mounts']['work']}/{destination.relative_to(self.work_root).as_posix()}"

    def _monitor_memory(self, container_name: str, stop: threading.Event, peak: list[int]) -> None:
        while not stop.wait(0.05):
            try:
                completed = subprocess.run(
                    ["docker", "stats", "--no-stream", "--format", "{{json .}}", container_name],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    check=False,
                )
                if completed.returncode != 0 or not completed.stdout.strip():
                    continue
                row = json.loads(completed.stdout)
                used = row.get("MemUsage", "").split("/", 1)[0].strip()
                peak[0] = max(peak[0], memory_bytes(used))
            except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
                continue

    def _cleanup(self, container_name: str) -> None:
        subprocess.run(
            ["docker", "rm", "--force", "--volumes", container_name],
            capture_output=True,
            timeout=10,
            check=False,
        )
        self.active_names.discard(container_name)

    def run(self, operation: list[str]) -> ProcessOutcome:
        if operation[0] == "metadata":
            mapped = operation
            include_data = False
        elif operation[0] in {"compress-batch", "decompress-batch"} and len(operation) == 2:
            mapped = [operation[0], self._rewrite_job(Path(operation[1]))]
            include_data = True
        else:
            raise ContractError(f"isolated runner rejects unsupported operation: {operation[0]}")

        name = f"wb001-{self.session_label[:12]}-{uuid.uuid4().hex[:8]}"
        self.active_names.add(name)
        command = build_docker_command(
            policy=self.policy,
            image_id=self.image_id,
            container_name=name,
            session_label=self.session_label,
            candidate_root=self.candidate_root,
            corpus_root=self.corpus_root,
            work_root=self.work_root,
            candidate_command=[*self.candidate_command, *mapped],
            include_data_mounts=include_data,
        )
        stop = threading.Event()
        peak = [0]
        monitor = threading.Thread(target=self._monitor_memory, args=(name, stop, peak), daemon=True)
        monitor.start()
        try:
            outcome = run_process(
                command,
                cwd=WORKBENCH_ROOT,
                timeout_seconds=self.timeout_seconds,
                output_limit_bytes=self.output_limit_bytes,
            )
        finally:
            stop.set()
            monitor.join(timeout=3)
            self._cleanup(name)
        outcome = dataclasses.replace(outcome, peak_rss_bytes=peak[0])
        if outcome.timed_out:
            raise CandidateExecutionError(
                f"isolated candidate timed out during {operation[0]} after {self.timeout_seconds:g}s"
            )
        if outcome.output_limit_exceeded:
            raise CandidateExecutionError(
                f"isolated candidate exceeded its log limit during {operation[0]}"
            )
        if outcome.returncode != 0:
            raise CandidateExecutionError(
                f"isolated candidate returned {outcome.returncode} during {operation[0]}: "
                f"{outcome.stderr[-4000:].strip()}"
            )
        return outcome

    def close(self) -> None:
        for name in list(self.active_names):
            self._cleanup(name)


class DockerExecutorFactory:
    def __init__(self, policy_path: Path, lock_path: Path) -> None:
        self.policy_path = policy_path
        self.lock_path = lock_path

    def __call__(self, **kwargs: Any) -> CandidateExecutor:
        return DockerCandidateExecutor(
            **kwargs,
            policy_path=self.policy_path,
            lock_path=self.lock_path,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate WB-001 in the locked Docker boundary")
    parser.add_argument("--submission", type=Path, required=True)
    parser.add_argument("--operator-id", required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument(
        "--policy",
        type=Path,
        default=WORKBENCH_ROOT / "isolation" / "docker_policy.toml",
    )
    parser.add_argument(
        "--image-lock",
        type=Path,
        default=WORKBENCH_ROOT / "isolation" / "image.lock.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = evaluate_submission(
            args.submission,
            args.operator_id,
            manifest_path=args.manifest,
            config_path=args.config,
            executor_factory=DockerExecutorFactory(args.policy, args.image_lock),
        )
        write_json(args.output, result)
    except (ContractError, CandidateExecutionError) as exc:
        raise SystemExit(f"WB-001 isolated evaluation failed: {exc}") from exc
    print(
        json.dumps(
            {
                "output": str(args.output),
                "hard_gate_pass": result["hard_gate_pass"],
                "boundary": result["execution_boundary"],
                "result_sha256": result["result_sha256"],
            },
            indent=2,
        )
    )
    return 0 if result["hard_gate_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
