from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "corpus_manifest.json"


def digest(path: Path, algorithm: str) -> str:
    hasher = hashlib.new(algorithm)
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a canonical WB-002 corpus")
    parser.add_argument("--corpus", required=True, choices=["enwik8", "enwik9"])
    parser.add_argument("--input", required=True, type=Path)
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    expected = next(item for item in manifest["corpora"] if item["id"] == args.corpus)
    if args.input.stat().st_size != expected["extracted_bytes"]:
        raise SystemExit("FAIL byte count does not match the published corpus commitment")
    md5 = digest(args.input, "md5")
    sha1 = digest(args.input, "sha1")
    if md5 != expected["official_md5"] or sha1 != expected["official_sha1"]:
        raise SystemExit("FAIL MD5 or SHA-1 does not match the published corpus commitment")
    print(json.dumps({"corpus": args.corpus, "bytes": args.input.stat().st_size, "official_md5": md5, "official_sha1": sha1, "factory_derived_sha256": digest(args.input, "sha256")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
