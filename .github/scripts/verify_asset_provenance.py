from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess


ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "ASSET_PROVENANCE.json"
MEDIA_SUFFIXES = {
    ".gif",
    ".jpeg",
    ".jpg",
    ".mp3",
    ".mp4",
    ".otf",
    ".png",
    ".svg",
    ".ttf",
    ".vtt",
    ".wav",
    ".webp",
    ".woff",
    ".woff2",
}
ALLOWED_LICENSES = {"CC-BY-4.0", "OFL-1.1"}


def tracked_media() -> set[str]:
    output = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    return {
        path
        for path in output.decode("utf-8").split("\0")
        if path and PurePosixPath(path).suffix.lower() in MEDIA_SUFFIXES
    }


def safe_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"invalid asset path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe asset path: {value!r}")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    document = json.loads(LEDGER.read_text(encoding="utf-8"))
    if document.get("schema_version") != 1 or document.get("hash_algorithm") != "SHA-256":
        raise ValueError("asset ledger version or hash algorithm is not supported")
    groups = document.get("assets")
    if not isinstance(groups, list) or not groups:
        raise ValueError("asset ledger needs at least one asset group")

    declared: set[str] = set()
    for group in groups:
        if not isinstance(group, dict):
            raise ValueError("asset groups must be JSON objects")
        if not isinstance(group.get("origin"), str) or len(group["origin"].strip()) < 10:
            raise ValueError("every asset group needs a useful origin")
        if group.get("licence") not in ALLOWED_LICENSES:
            raise ValueError(f"unsupported asset licence: {group.get('licence')!r}")
        paths = [safe_path(value) for value in group.get("paths", [])]
        hashes = group.get("sha256")
        if not paths or len(paths) != len(set(paths)) or not isinstance(hashes, dict):
            raise ValueError("asset paths must be a non-empty unique list with a hash map")
        if set(paths) != set(hashes):
            raise ValueError("asset path and SHA-256 keys differ")

        for relative in paths:
            if relative in declared:
                raise ValueError(f"asset is declared more than once: {relative}")
            declared.add(relative)
            target = ROOT / relative
            if not target.is_file() or target.is_symlink():
                raise ValueError(f"asset is missing, linked or not a file: {relative}")
            expected = hashes[relative]
            if not isinstance(expected, str) or len(expected) != 64:
                raise ValueError(f"asset hash is malformed: {relative}")
            actual = sha256(target)
            if actual != expected:
                raise ValueError(
                    f"asset hash mismatch for {relative}: expected {expected}, got {actual}"
                )

    tracked = tracked_media()
    missing = sorted(tracked - declared)
    stale = sorted(declared - tracked)
    if missing or stale:
        raise ValueError(f"asset ledger coverage differs: missing={missing}, stale={stale}")

    print(f"Asset provenance verified for {len(declared)} tracked media files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
