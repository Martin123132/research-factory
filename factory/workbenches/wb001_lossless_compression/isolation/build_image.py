from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path


ISOLATION_ROOT = Path(__file__).resolve().parent
WORKBENCH_ROOT = ISOLATION_ROOT.parent
sys.path.insert(0, str(WORKBENCH_ROOT / "runner"))

from common import canonical_json_bytes, sha256_bytes, sha256_file, write_json  # noqa: E402


def docker_json(*arguments: str) -> dict:
    completed = subprocess.run(
        ["docker", *arguments],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "Docker command failed")
    return json.loads(completed.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and lock the WB-001 candidate runtime image")
    parser.add_argument("--output", type=Path, default=ISOLATION_ROOT / "image.lock.json")
    parser.add_argument("--no-pull", action="store_true")
    args = parser.parse_args()

    with (ISOLATION_ROOT / "docker_policy.toml").open("rb") as handle:
        policy = tomllib.load(handle)
    image_tag = policy["image_tag"]

    try:
        docker_version = docker_json("version", "--format", "{{json .}}")
    except (OSError, subprocess.TimeoutExpired, RuntimeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Docker daemon is unavailable: {exc}") from exc

    command = ["docker", "build"]
    if not args.no_pull:
        command.append("--pull")
    command.extend(["--tag", image_tag, str(ISOLATION_ROOT)])
    completed = subprocess.run(command, check=False)
    if completed.returncode != 0:
        raise SystemExit(f"Docker image build failed with code {completed.returncode}")

    image = docker_json("image", "inspect", image_tag)[0]
    info = docker_json("info", "--format", "{{json .}}")
    unsigned = {
        "schema_version": 1,
        "lock_type": "wb001_docker_image",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "image_tag": image_tag,
        "image_id": image["Id"],
        "repo_digests": image.get("RepoDigests") or [],
        "platform": {
            "os": image.get("Os"),
            "architecture": image.get("Architecture"),
        },
        "docker": {
            "client_version": docker_version.get("Client", {}).get("Version"),
            "server_version": docker_version.get("Server", {}).get("Version"),
            "operating_system": info.get("OperatingSystem"),
            "os_type": info.get("OSType"),
            "architecture": info.get("Architecture"),
            "security_options": info.get("SecurityOptions", []),
        },
        "dockerfile_sha256": sha256_file(ISOLATION_ROOT / "Dockerfile"),
        "requirements_sha256": sha256_file(ISOLATION_ROOT / "requirements.docker.lock"),
        "policy_sha256": sha256_file(ISOLATION_ROOT / "docker_policy.toml"),
        "promotion_grade": bool(policy["promotion_grade"]),
        "boundary_note": policy["boundary_note"],
    }
    lock = {**unsigned, "image_lock_sha256": sha256_bytes(canonical_json_bytes(unsigned))}
    write_json(args.output, lock)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "image_id": lock["image_id"],
                "promotion_grade": lock["promotion_grade"],
                "image_lock_sha256": lock["image_lock_sha256"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
