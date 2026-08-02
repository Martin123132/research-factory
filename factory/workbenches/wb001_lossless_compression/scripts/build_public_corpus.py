from __future__ import annotations

import argparse
import json
import random
import struct
import sys
from pathlib import Path


WORKBENCH_ROOT = Path(__file__).resolve().parents[1]
RUNNER_ROOT = WORKBENCH_ROOT / "runner"
sys.path.insert(0, str(RUNNER_ROOT))

from common import canonical_json_bytes, sha256_bytes, sha256_file, write_json  # noqa: E402


PROFILE = "synthetic-public-v1"


def _english_like() -> bytes:
    subjects = ["sensor", "router", "archive", "bearing", "worker", "dataset", "module", "valve"]
    verbs = ["records", "checks", "measures", "repeats", "compresses", "validates", "updates"]
    objects = ["the result", "every byte", "a frozen input", "the cost vector", "the evidence log"]
    lines = []
    for index in range(18_000):
        lines.append(
            f"{index:06d}: the {subjects[index % len(subjects)]} "
            f"{verbs[(index // 3) % len(verbs)]} {objects[(index // 7) % len(objects)]}.\n"
        )
    return "".join(lines).encode("utf-8")


def _json_events() -> bytes:
    records = []
    states = ["queued", "running", "checked", "reproduced", "archived"]
    for index in range(12_000):
        records.append(
            json.dumps(
                {
                    "event_id": index,
                    "workbench": f"WB-{1 + index % 12:03d}",
                    "state": states[index % len(states)],
                    "worker": f"agent-{index % 64:02d}",
                    "score": round(((index * 2654435761) % 10000) / 100, 2),
                    "valid": index % 17 != 0,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    return ("\n".join(records) + "\n").encode("utf-8")


def _source_like() -> bytes:
    fragments = [
        "def verify(payload: bytes) -> bool:\n",
        "    digest = sha256(payload).hexdigest()\n",
        "    return digest == EXPECTED\n\n",
        "class EvidenceBundle:\n",
        "    def __init__(self, rows):\n",
        "        self.rows = tuple(rows)\n\n",
    ]
    return "".join(fragments[index % len(fragments)] for index in range(30_000)).encode("utf-8")


def _numeric_series() -> bytes:
    output = bytearray()
    value = 100_000
    for index in range(180_000):
        value += ((index * 17) % 11) - 5
        output.extend(struct.pack("<i", value))
    return bytes(output)


def _sparse_binary() -> bytes:
    output = bytearray(768 * 1024)
    for offset in range(0, len(output), 4096):
        marker = struct.pack("<II", offset, (offset * 31) & 0xFFFFFFFF)
        output[offset : offset + len(marker)] = marker
    return bytes(output)


def _incompressible() -> bytes:
    generator = random.Random(20260801)
    return bytes(generator.getrandbits(8) for _ in range(384 * 1024))


def corpus_payloads() -> list[tuple[str, str, bytes]]:
    english = _english_like()
    events = _json_events()
    numeric = _numeric_series()
    sparse = _sparse_binary()
    random_bytes = _incompressible()
    source = _source_like()
    mixed = b"".join(
        [
            english[:180_000],
            events[:180_000],
            numeric[:180_000],
            sparse[:180_000],
            random_bytes[:180_000],
        ]
    )
    return [
        ("english_like.txt", "generated-text", english),
        ("events.ndjson", "structured-records", events),
        ("source_like.py.txt", "source-like-text", source),
        ("numeric_series.i32le", "integer-array", numeric),
        ("sparse_blocks.bin", "sparse-binary", sparse),
        ("incompressible.bin", "incompressible", random_bytes),
        ("mixed_blocks.bin", "mixed", mixed),
    ]


def build_corpus(output_root: Path, manifest_path: Path) -> dict[str, object]:
    output_root.mkdir(parents=True, exist_ok=True)
    entries = []
    for name, data_class, payload in corpus_payloads():
        path = output_root / name
        path.write_bytes(payload)
        entries.append(
            {
                "path": name,
                "class": data_class,
                "bytes": len(payload),
                "sha256": sha256_file(path),
            }
        )
    core = {
        "schema_version": 1,
        "profile": PROFILE,
        "root": output_root.name,
        "files": entries,
    }
    manifest = {**core, "corpus_sha256": sha256_bytes(canonical_json_bytes(core))}
    write_json(manifest_path, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the deterministic WB-001 public corpus")
    parser.add_argument("--output-root", type=Path, default=WORKBENCH_ROOT / "data" / "public")
    parser.add_argument("--manifest", type=Path, default=WORKBENCH_ROOT / "data" / "public_manifest.json")
    args = parser.parse_args()
    manifest = build_corpus(args.output_root, args.manifest)
    print(
        json.dumps(
            {
                "manifest": str(args.manifest),
                "files": len(manifest["files"]),
                "bytes": sum(row["bytes"] for row in manifest["files"]),
                "corpus_sha256": manifest["corpus_sha256"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

