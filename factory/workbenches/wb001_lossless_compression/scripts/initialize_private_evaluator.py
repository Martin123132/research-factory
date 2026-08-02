from __future__ import annotations

import argparse
import base64
import json
import os
import random
import secrets
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


WORKBENCH_ROOT = Path(__file__).resolve().parents[1]
FACTORY_ROOT = WORKBENCH_ROOT.parents[1]
sys.path.insert(0, str(WORKBENCH_ROOT / "runner"))

from common import canonical_json_bytes, sha256_bytes, sha256_file, write_json  # noqa: E402
from signing import key_id  # noqa: E402


WORDS = (
    "factory evidence method boundary signal archive packet orbit thermal control "
    "vector model storage retrieval checksum independent validator experiment"
).split()


def generate_files(root: Path) -> list[dict[str, object]]:
    seed = int.from_bytes(secrets.token_bytes(32), "big")
    rng = random.Random(seed)
    payloads: list[tuple[str, str, bytes]] = []

    text = "\n".join(
        " ".join(rng.choice(WORDS) for _ in range(rng.randint(8, 22)))
        for _ in range(28000)
    ).encode("utf-8")
    payloads.append(("sealed_notes.txt", "natural-language", text))

    events = bytearray()
    for index in range(18000):
        row = {
            "event": index,
            "machine": f"M-{rng.randrange(20):02d}",
            "state": rng.choice(["idle", "run", "inspect", "fault"]),
            "value": round(rng.gauss(50, 7), 5),
            "nonce": secrets.token_hex(5),
        }
        events.extend(json.dumps(row, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        events.extend(b"\n")
    payloads.append(("sealed_events.ndjson", "structured-records", bytes(events)))

    value = rng.randrange(-100000, 100000)
    telemetry = bytearray()
    for _ in range(180000):
        value += rng.randrange(-12, 13)
        telemetry.extend(struct.pack("<q", value))
    payloads.append(("sealed_telemetry.i64le", "numeric-series", bytes(telemetry)))

    mixed = bytearray()
    for index in range(1024):
        if index % 5 == 0:
            mixed.extend(secrets.token_bytes(1024))
        elif index % 5 == 1:
            mixed.extend(bytes([rng.randrange(256)]) * 1024)
        else:
            pattern = secrets.token_bytes(32)
            mixed.extend(pattern * 32)
    payloads.append(("sealed_mixed.bin", "mixed-binary", bytes(mixed)))
    payloads.append(("sealed_noise.bin", "incompressible", secrets.token_bytes(768 * 1024)))

    entries: list[dict[str, object]] = []
    for name, data_class, payload in payloads:
        path = root / name
        path.write_bytes(payload)
        entries.append(
            {
                "path": name,
                "class": data_class,
                "bytes": len(payload),
                "sha256": sha256_bytes(payload),
            }
        )
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the private WB-001 evaluator state once")
    parser.add_argument("--private-root", type=Path, default=FACTORY_ROOT / "private" / "wb001")
    parser.add_argument(
        "--commitment-output",
        type=Path,
        default=WORKBENCH_ROOT / "data" / "holdout_commitment.json",
    )
    parser.add_argument(
        "--public-key-output",
        type=Path,
        default=WORKBENCH_ROOT / "data" / "evaluator_public_key.json",
    )
    args = parser.parse_args()

    private_root = args.private_root.resolve()
    if private_root.exists() or args.commitment_output.exists() or args.public_key_output.exists():
        raise SystemExit("refusing to replace existing evaluator state or public commitments")
    corpus_root = private_root / "holdout"
    corpus_root.mkdir(parents=True)
    entries = generate_files(corpus_root)
    core = {
        "schema_version": 1,
        "profile": "sealed-mixed-corpus-v1",
        "root": "holdout",
        "files": entries,
    }
    manifest = {**core, "corpus_sha256": sha256_bytes(canonical_json_bytes(core))}
    manifest_path = private_root / "holdout_manifest.json"
    write_json(manifest_path, manifest)

    private_key = Ed25519PrivateKey.generate()
    private_path = private_root / "evaluator_private_key.pem"
    private_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    try:
        os.chmod(private_path, 0o600)
    except OSError:
        pass
    public_key = private_key.public_key()
    raw_public = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    public_document = {
        "schema_version": 1,
        "algorithm": "Ed25519",
        "key_id": key_id(public_key),
        "public_key_base64": base64.b64encode(raw_public).decode("ascii"),
    }
    write_json(args.public_key_output, public_document)

    generated_at = datetime.now(timezone.utc).isoformat()
    commitment_core = {
        "schema_version": 1,
        "commitment_type": "wb001_sealed_holdout",
        "profile": manifest["profile"],
        "committed_at": generated_at,
        "corpus_sha256": manifest["corpus_sha256"],
        "manifest_sha256": sha256_file(manifest_path),
        "files": len(entries),
        "total_bytes": sum(int(entry["bytes"]) for entry in entries),
        "evaluator_key_id": public_document["key_id"],
    }
    commitment = {
        **commitment_core,
        "commitment_sha256": sha256_bytes(canonical_json_bytes(commitment_core)),
    }
    write_json(args.commitment_output, commitment)
    write_json(
        private_root / "private_state.json",
        {
            "schema_version": 1,
            "created_at": generated_at,
            "holdout_manifest": str(manifest_path),
            "holdout_commitment_sha256": commitment["commitment_sha256"],
            "evaluator_key_id": public_document["key_id"],
            "warning": "Private evaluator state. Never mount this directory into a candidate container.",
        },
    )
    print(
        json.dumps(
            {
                "private_root": str(private_root),
                "public_commitment": str(args.commitment_output),
                "public_key": str(args.public_key_output),
                "files": commitment["files"],
                "total_bytes": commitment["total_bytes"],
                "commitment_sha256": commitment["commitment_sha256"],
                "evaluator_key_id": public_document["key_id"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
