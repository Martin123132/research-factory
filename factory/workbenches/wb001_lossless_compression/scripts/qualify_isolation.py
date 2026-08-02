from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


WORKBENCH_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKBENCH_ROOT / "runner"))

from common import write_json  # noqa: E402
from evaluate_isolated import DockerExecutorFactory  # noqa: E402
from evaluate_local import evaluate_submission  # noqa: E402


def remaining_containers() -> list[str]:
    completed = subprocess.run(
        [
            "docker",
            "ps",
            "--all",
            "--quiet",
            "--filter",
            "label=research-factory.workbench=WB-001",
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    return [line for line in completed.stdout.splitlines() if line.strip()]


def main() -> int:
    policy = WORKBENCH_ROOT / "isolation" / "docker_policy.toml"
    lock = WORKBENCH_ROOT / "isolation" / "image.lock.json"
    factory = DockerExecutorFactory(policy, lock)
    output_root = WORKBENCH_ROOT / "results" / "isolation_qualification"
    output_root.mkdir(parents=True, exist_ok=True)

    probe = evaluate_submission(
        WORKBENCH_ROOT / "tests" / "fixtures" / "isolation_probe_submission.json",
        "demo:isolation-probe",
        executor_factory=factory,
    )
    write_json(output_root / "probe.result.json", probe)
    metadata = probe["candidate"]["metadata"]
    required = {
        "network_blocked": True,
        "root_write_blocked": True,
        "docker_socket_absent": True,
        "host_canary_absent": True,
        "corpus_absent_during_metadata": True,
        "numeric_uid": 65532,
        "cap_eff": "0000000000000000",
        "no_new_privs": "1",
        "seccomp": "2",
    }
    mismatches = {
        key: {"expected": expected, "actual": metadata.get(key)}
        for key, expected in required.items()
        if metadata.get(key) != expected
    }
    if not probe["hard_gate_pass"] or mismatches:
        raise SystemExit(f"isolation probe failed: {json.dumps(mismatches, sort_keys=True)}")

    log_bomb = evaluate_submission(
        WORKBENCH_ROOT / "tests" / "fixtures" / "log_bomb_submission.json",
        "demo:log-bomb",
        executor_factory=factory,
    )
    write_json(output_root / "log-bomb.result.json", log_bomb)
    if log_bomb["hard_gate_pass"]:
        raise SystemExit("log bomb unexpectedly passed")
    if "log limit" not in json.dumps(log_bomb["failures"]).lower():
        raise SystemExit("log bomb failed for the wrong reason")

    leftovers = remaining_containers()
    if leftovers:
        raise SystemExit(f"factory containers were not cleaned up: {leftovers}")
    summary = {
        "probe_hard_gate_pass": probe["hard_gate_pass"],
        "policy_checks": required,
        "log_bomb_rejected": True,
        "leftover_containers": 0,
        "boundary": probe["execution_boundary"],
    }
    write_json(output_root / "summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
