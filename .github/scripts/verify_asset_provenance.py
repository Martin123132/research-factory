from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import subprocess

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "ASSET_PROVENANCE.json"
SCHEMA = ROOT / ".github" / "schemas" / "asset-provenance-v1.schema.json"
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
REGULAR_GIT_MODES = {"100644", "100755"}


def load_json_strict(path: Path) -> object:
    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        document: dict[str, object] = {}
        for key, value in pairs:
            if key in document:
                raise ValueError(f"duplicate JSON object key in {path}: {key!r}")
            document[key] = value
        return document

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_keys)


def tracked_media(root: Path) -> dict[str, str]:
    output = subprocess.run(
        ["git", "ls-files", "--stage", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout
    tracked: dict[str, str] = {}
    for record in output.split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        mode = metadata.split(b" ", 1)[0].decode("ascii")
        path = raw_path.decode("utf-8")
        if PurePosixPath(path).suffix.lower() in MEDIA_SUFFIXES:
            tracked[path] = mode
    return tracked


def safe_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"invalid asset path: {value!r}")
    path = PurePosixPath(value)
    windows_path = PureWindowsPath(value)
    if (
        path.is_absolute()
        or windows_path.is_absolute()
        or windows_path.drive
        or "." in path.parts
        or ".." in path.parts
        or path.as_posix() != value
    ):
        raise ValueError(f"unsafe asset path: {value!r}")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_document(document: object, schema_path: Path) -> dict[str, object]:
    schema = load_json_strict(schema_path)
    if not isinstance(schema, dict):
        raise ValueError("asset ledger schema must be a JSON object")
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    errors = sorted(
        validator.iter_errors(document),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        error = errors[0]
        location = "/".join(str(part) for part in error.absolute_path) or "$"
        raise ValueError(f"asset ledger schema violation at {location}: {error.message}")
    if not isinstance(document, dict):
        raise ValueError("asset ledger must be a JSON object")
    return document


def verify(
    root: Path = ROOT,
    ledger_path: Path | None = None,
    schema_path: Path | None = None,
    tracked_files: dict[str, str] | None = None,
) -> int:
    ledger = ledger_path or root / "ASSET_PROVENANCE.json"
    schema = schema_path or root / ".github" / "schemas" / "asset-provenance-v1.schema.json"
    document = validate_document(load_json_strict(ledger), schema)
    groups = document.get("assets")
    assert isinstance(groups, list)

    declared: set[str] = set()
    tracked = tracked_files if tracked_files is not None else tracked_media(root)
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
            mode = tracked.get(relative)
            if mode is not None and mode not in REGULAR_GIT_MODES:
                raise ValueError(f"asset has unsafe Git mode {mode}: {relative}")
            target = root / relative
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

    tracked_paths = set(tracked)
    missing = sorted(tracked_paths - declared)
    stale = sorted(declared - tracked_paths)
    if missing or stale:
        raise ValueError(f"asset ledger coverage differs: missing={missing}, stale={stale}")

    return len(declared)


def main() -> int:
    count = verify()

    print(f"Asset provenance verified for {count} tracked media files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
