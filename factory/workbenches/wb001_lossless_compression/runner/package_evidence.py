from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import canonical_json_bytes, sha256_bytes, sha256_file, write_json


def package_manifest(files: list[Path], *, root: Path) -> dict[str, Any]:
    root = root.resolve()
    entries: list[dict[str, Any]] = []
    for path in files:
        resolved = path.resolve()
        if not resolved.is_file():
            raise ValueError(f"evidence file does not exist: {path}")
        try:
            label = resolved.relative_to(root).as_posix()
        except ValueError:
            label = resolved.name
        entries.append(
            {
                "path": label,
                "bytes": resolved.stat().st_size,
                "sha256": sha256_file(resolved),
            }
        )
    entries.sort(key=lambda row: row["path"])
    unsigned = {
        "schema_version": 1,
        "evidence_type": "wb001_evidence_manifest",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "files": entries,
    }
    return {**unsigned, "package_sha256": sha256_bytes(canonical_json_bytes(unsigned))}


def main() -> int:
    parser = argparse.ArgumentParser(description="Hash a WB-001 evidence bundle")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--file", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = package_manifest(args.file, root=args.root)
    write_json(args.output, manifest)
    print(json.dumps({"output": str(args.output), "package_sha256": manifest["package_sha256"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

