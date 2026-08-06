from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess


MANIFEST_NAME = "offline-release-manifest-v1.json"
SOURCE_PREFIX = "research-factory/"


def run_git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def assert_clean(repository: Path) -> None:
    status = run_git(repository, "status", "--porcelain=v1", "--untracked-files=all")
    if status:
        raise ValueError(
            "offline releases require a clean checkout; commit, ignore or remove local changes first"
        )


def build_release(
    repository: Path,
    output_directory: Path,
    *,
    source_ref: str = "HEAD",
    require_clean: bool = True,
) -> Path:
    repository = repository.resolve()
    output_directory = output_directory.resolve()
    git_directory = (repository / ".git").resolve()

    if not (repository / ".git").exists():
        raise ValueError(f"not a Git checkout: {repository}")
    if output_directory == git_directory or output_directory.is_relative_to(git_directory):
        raise ValueError("offline release output must not be placed inside .git")
    if output_directory.exists():
        raise ValueError(f"offline release output already exists: {output_directory}")
    if require_clean:
        assert_clean(repository)

    source_commit = run_git(repository, "rev-parse", "--verify", f"{source_ref}^{{commit}}")
    short_commit = source_commit[:12]
    source_name = f"research-factory-source-{short_commit}.tar"
    history_name = f"research-factory-history-{short_commit}.bundle"
    source_path = output_directory / source_name
    history_path = output_directory / history_name

    output_directory.mkdir(parents=True)
    run_git(
        repository,
        "archive",
        "--format=tar",
        f"--prefix={SOURCE_PREFIX}",
        f"--output={source_path}",
        source_commit,
    )
    run_git(repository, "bundle", "create", str(history_path), source_ref, "--tags")

    artifacts = [
        {
            "path": source_name,
            "role": "tracked-source-snapshot",
            "size_bytes": source_path.stat().st_size,
            "sha256": sha256(source_path),
        },
        {
            "path": history_name,
            "role": "recoverable-git-history",
            "size_bytes": history_path.stat().st_size,
            "sha256": sha256(history_path),
        },
    ]
    manifest = {
        "schema_version": 1,
        "project": "Research Factory",
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_ref": source_ref,
        "source_commit": source_commit,
        "hash_algorithm": "SHA-256",
        "restore_root": SOURCE_PREFIX,
        "boundaries": {
            "tracked_files_only": True,
            "includes_gitignored_private_state": False,
            "includes_hosted_runtime_state": False,
            "scientific_evidence": False,
        },
        "artifacts": artifacts,
    }
    manifest_path = output_directory / MANIFEST_NAME
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a source, history and checksum package for offline Factory recovery."
    )
    parser.add_argument(
        "--repository",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Research Factory Git checkout (default: repository root).",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ref", default="HEAD", help="Git ref to archive and bundle.")
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Build from the committed ref even when unrelated local changes exist.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = build_release(
        args.repository,
        args.output,
        source_ref=args.ref,
        require_clean=not args.allow_dirty,
    )
    print(f"Offline release built: {manifest.parent}")
    print(f"Manifest: {manifest.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
