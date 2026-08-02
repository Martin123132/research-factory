from __future__ import annotations

import argparse
import json
import os
import socket
import zlib
from pathlib import Path


def status_field(name: str) -> str | None:
    try:
        for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{name}:"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return None


def blocked_network() -> bool:
    try:
        socket.setdefaulttimeout(0.25)
        socket.getaddrinfo("example.com", 443)
        return False
    except OSError:
        return True


def blocked_root_write() -> bool:
    try:
        Path("/factory-escape-probe").write_bytes(b"escape")
        return False
    except OSError:
        return True


def metadata() -> dict[str, object]:
    return {
        "codec": "isolation-probe-zlib",
        "protocol": "wb001-batch-v1",
        "deterministic": True,
        "network_blocked": blocked_network(),
        "root_write_blocked": blocked_root_write(),
        "docker_socket_absent": not Path("/var/run/docker.sock").exists(),
        "host_canary_absent": not Path("/host-secret-canary").exists(),
        "corpus_absent_during_metadata": not Path("/corpus").exists(),
        "numeric_uid": os.getuid(),
        "cap_eff": status_field("CapEff"),
        "no_new_privs": status_field("NoNewPrivs"),
        "seccomp": status_field("Seccomp"),
    }


def transform(operation: str, source: Path, destination: Path) -> None:
    data = source.read_bytes()
    output = zlib.compress(data, 6) if operation == "compress" else zlib.decompress(data)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(output)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation")
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args()
    if args.operation == "metadata":
        print(json.dumps(metadata(), sort_keys=True))
        return 0
    if args.operation not in {"compress-batch", "decompress-batch"} or len(args.paths) != 1:
        raise SystemExit("probe supports only WB-001 batch operations")
    operation = args.operation.removesuffix("-batch")
    job = json.loads(Path(args.paths[0]).read_text(encoding="utf-8"))
    for item in job["items"]:
        transform(operation, Path(item["input"]), Path(item["output"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
