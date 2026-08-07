from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import tempfile

try:
    from .build_offline_release import MANIFEST_NAME, SOURCE_PREFIX
except ImportError:  # Direct script execution from factory/release.
    from build_offline_release import MANIFEST_NAME, SOURCE_PREFIX


TOP_LEVEL_KEYS = {
    "schema_version",
    "project",
    "generated_at_utc",
    "source_ref",
    "source_commit",
    "hash_algorithm",
    "restore_root",
    "boundaries",
    "artifacts",
}
BOUNDARY_KEYS = {
    "tracked_files_only",
    "includes_gitignored_private_state",
    "includes_hosted_runtime_state",
    "scientific_evidence",
}
ARTIFACT_KEYS = {"path", "role", "size_bytes", "sha256"}
EXPECTED_ROLES = {"tracked-source-snapshot", "recoverable-git-history"}


def load_json_strict(path: Path) -> object:
    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        document: dict[str, object] = {}
        for key, value in pairs:
            if key in document:
                raise ValueError(f"duplicate JSON object key in {path}: {key!r}")
            document[key] = value
        return document

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(command: list[str], *, cwd: Path | None = None) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def validate_manifest(document: object) -> tuple[str, list[dict[str, object]]]:
    if not isinstance(document, dict) or set(document) != TOP_LEVEL_KEYS:
        raise ValueError("offline release manifest has missing or unsupported top-level fields")
    if document["schema_version"] != 1 or document["project"] != "Research Factory":
        raise ValueError("offline release manifest identity is unsupported")
    if document["hash_algorithm"] != "SHA-256" or document["restore_root"] != SOURCE_PREFIX:
        raise ValueError("offline release hash or restore-root contract is unsupported")

    commit = document["source_commit"]
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("offline release source_commit must be a full lowercase Git object id")

    boundaries = document["boundaries"]
    expected_boundaries = {
        "tracked_files_only": True,
        "includes_gitignored_private_state": False,
        "includes_hosted_runtime_state": False,
        "scientific_evidence": False,
    }
    if not isinstance(boundaries, dict) or set(boundaries) != BOUNDARY_KEYS:
        raise ValueError("offline release boundaries are not closed")
    if boundaries != expected_boundaries:
        raise ValueError("offline release attempts to widen its evidence or private-state boundary")

    artifacts = document["artifacts"]
    if not isinstance(artifacts, list) or len(artifacts) != 2:
        raise ValueError("offline release must contain exactly two artifacts")
    roles: set[str] = set()
    paths: set[str] = set()
    for artifact in artifacts:
        if not isinstance(artifact, dict) or set(artifact) != ARTIFACT_KEYS:
            raise ValueError("offline release artifact record is not closed")
        path = artifact["path"]
        role = artifact["role"]
        if not isinstance(path, str) or PurePosixPath(path).name != path:
            raise ValueError("offline release artifact path must be one plain filename")
        if not isinstance(role, str) or role not in EXPECTED_ROLES:
            raise ValueError(f"unsupported offline release artifact role: {role!r}")
        if not isinstance(artifact["size_bytes"], int) or artifact["size_bytes"] < 1:
            raise ValueError("offline release artifact size must be positive")
        if not isinstance(artifact["sha256"], str) or not re.fullmatch(
            r"[0-9a-f]{64}", artifact["sha256"]
        ):
            raise ValueError("offline release artifact SHA-256 is invalid")
        roles.add(role)
        if path in paths:
            raise ValueError(f"duplicate offline release artifact path: {path}")
        paths.add(path)
    if roles != EXPECTED_ROLES:
        raise ValueError("offline release artifact roles are incomplete")
    return commit, artifacts


def verify_source_archive(path: Path, expected_commit: str) -> None:
    with path.open("rb") as stream:
        completed = subprocess.run(
            ["git", "get-tar-commit-id"],
            stdin=stream,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    archive_commit = completed.stdout.strip()
    if archive_commit != expected_commit:
        raise ValueError(
            f"source archive commit differs: expected {expected_commit}, got {archive_commit}"
        )

    required = {f"{SOURCE_PREFIX}README.md", f"{SOURCE_PREFIX}factory/ENGINE.md"}
    seen: set[str] = set()
    root_entry = SOURCE_PREFIX.rstrip("/")
    with tarfile.open(path, "r:") as archive:
        for member in archive.getmembers():
            name = PurePosixPath(member.name)
            inside_root = member.name == root_entry or member.name.startswith(SOURCE_PREFIX)
            if name.is_absolute() or ".." in name.parts or not inside_root:
                raise ValueError(f"unsafe source archive path: {member.name}")
            if member.issym() or member.islnk() or member.isdev():
                raise ValueError(f"unsupported source archive entry type: {member.name}")
            seen.add(member.name)
    missing = sorted(required - seen)
    if missing:
        raise ValueError(f"source archive lacks recovery-critical files: {missing}")


def verify_history_bundle(path: Path, expected_commit: str) -> None:
    with tempfile.TemporaryDirectory() as raw_directory:
        temporary = Path(raw_directory)
        verifier_repository = temporary / "verifier.git"
        recovered_repository = temporary / "recovered.git"
        run(["git", "init", "--quiet", str(verifier_repository)])
        run(["git", "bundle", "verify", str(path)], cwd=verifier_repository)
        run(["git", "clone", "--quiet", "--bare", str(path), str(recovered_repository)])
        run(
            [
                "git",
                f"--git-dir={recovered_repository}",
                "cat-file",
                "-e",
                f"{expected_commit}^{{commit}}",
            ]
        )


def verify_release(directory: Path) -> dict[str, object]:
    directory = directory.resolve()
    manifest_path = directory / MANIFEST_NAME
    if not manifest_path.is_file():
        raise ValueError(f"offline release manifest is missing: {manifest_path}")
    document = load_json_strict(manifest_path)
    commit, artifacts = validate_manifest(document)

    expected_files = {MANIFEST_NAME, *(str(value["path"]) for value in artifacts)}
    actual_files = {path.name for path in directory.iterdir() if path.is_file()}
    if actual_files != expected_files:
        raise ValueError(
            f"offline release file set differs: expected {sorted(expected_files)}, "
            f"got {sorted(actual_files)}"
        )

    by_role: dict[str, Path] = {}
    for artifact in artifacts:
        path = directory / str(artifact["path"])
        if path.stat().st_size != artifact["size_bytes"]:
            raise ValueError(f"offline release artifact size differs: {path.name}")
        actual_hash = sha256(path)
        if actual_hash != artifact["sha256"]:
            raise ValueError(f"offline release artifact SHA-256 differs: {path.name}")
        by_role[str(artifact["role"])] = path

    verify_source_archive(by_role["tracked-source-snapshot"], commit)
    verify_history_bundle(by_role["recoverable-git-history"], commit)
    assert isinstance(document, dict)
    return document


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify an offline Research Factory release before extraction or cloning."
    )
    parser.add_argument("release_directory", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    document = verify_release(args.release_directory)
    print(f"Offline release verified for commit {document['source_commit']}.")
    print("Tracked source archive and recoverable Git history are intact.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
