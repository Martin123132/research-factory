from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import Any

from .common import ContractError, canonical_json_bytes, load_json, sha256_bytes, sha256_file, write_json


class EvidenceStore:
    """Content-addressed immutable copies of submitted evidence bundles."""

    def __init__(
        self,
        root: Path,
        *,
        max_files: int = 10_000,
        max_total_bytes: int = 512 * 1024 * 1024,
    ) -> None:
        self.root = root.resolve()
        self.max_files = max_files
        self.max_total_bytes = max_total_bytes

    def _inventory(self, source: Path) -> tuple[Path, list[dict[str, Any]]]:
        source = source.resolve()
        if source.is_symlink():
            raise ContractError("evidence source must not be a symbolic link")
        if source.is_file():
            base = source.parent
            paths = [source]
        elif source.is_dir():
            base = source
            paths = sorted(path for path in source.rglob("*") if path.is_file())
            if any(path.is_symlink() for path in source.rglob("*")):
                raise ContractError("evidence bundles must not contain symbolic links")
        else:
            raise ContractError(f"evidence path does not exist: {source}")
        if not paths:
            raise ContractError("evidence bundle must contain at least one regular file")
        if len(paths) > self.max_files:
            raise ContractError("evidence bundle exceeds the file-count limit")

        files: list[dict[str, Any]] = []
        total = 0
        for path in paths:
            relative = path.relative_to(base).as_posix()
            size = path.stat().st_size
            total += size
            if total > self.max_total_bytes:
                raise ContractError("evidence bundle exceeds the total-byte limit")
            files.append({"path": relative, "bytes": size, "sha256": sha256_file(path)})
        return base, files

    def _verify_stored(self, destination: Path, manifest: dict[str, Any]) -> None:
        files_root = destination / "files"
        expected_paths = {row["path"] for row in manifest["files"]}
        if not files_root.is_dir() or (destination / "manifest.json").is_symlink():
            raise ContractError("stored evidence package is structurally invalid")
        actual_paths: set[str] = set()
        for path in files_root.rglob("*"):
            if path.is_symlink():
                raise ContractError("stored evidence package contains a symbolic link")
            if path.is_file():
                actual_paths.add(path.relative_to(files_root).as_posix())
        if actual_paths != expected_paths:
            raise ContractError("stored evidence package file set does not match its manifest")
        for row in manifest["files"]:
            path = files_root / Path(row["path"])
            if (
                not path.is_file()
                or path.stat().st_size != row["bytes"]
                or sha256_file(path) != row["sha256"]
            ):
                raise ContractError("stored evidence blob does not match its manifest")

    def _store(self, base: Path, files: list[dict[str, Any]]) -> dict[str, Any]:
        core = {
            "schema_version": 1,
            "evidence_type": "content_addressed_bundle",
            "files": files,
            "total_bytes": sum(row["bytes"] for row in files),
        }
        package_sha256 = sha256_bytes(canonical_json_bytes(core))
        manifest = {**core, "package_sha256": package_sha256}
        destination = self.root / "sha256" / package_sha256
        manifest_path = destination / "manifest.json"
        if destination.exists():
            existing = load_json(manifest_path)
            if existing != manifest:
                raise ContractError("existing evidence directory does not match its content address")
            self._verify_stored(destination, existing)
            return {**manifest, "stored_at": str(destination)}

        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.parent / f".{package_sha256}.{uuid.uuid4().hex}.tmp"
        (temporary / "files").mkdir(parents=True)
        try:
            for row in files:
                source_path = base / Path(row["path"])
                target = temporary / "files" / Path(row["path"])
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source_path, target)
                if target.stat().st_size != row["bytes"] or sha256_file(target) != row["sha256"]:
                    raise ContractError("evidence changed while it was being ingested")
                try:
                    os.chmod(target, 0o444)
                except OSError:
                    pass
            write_json(temporary / "manifest.json", manifest)
            try:
                os.replace(temporary, destination)
            except FileExistsError:
                shutil.rmtree(temporary)
        except Exception:
            if temporary.exists():
                shutil.rmtree(temporary)
            raise
        return {**manifest, "stored_at": str(destination)}

    def ingest(self, source: Path) -> dict[str, Any]:
        base, files = self._inventory(source)
        return self._store(base, files)

    def ingest_declared(self, base: Path, relative_paths: list[str]) -> dict[str, Any]:
        """Ingest only an explicitly declared, relative file set."""
        base = base.resolve()
        if not base.is_dir() or base.is_symlink():
            raise ContractError("declared evidence base must be a regular directory")
        if not relative_paths or len(relative_paths) != len(set(relative_paths)):
            raise ContractError("declared evidence paths must be non-empty and unique")
        if len(relative_paths) > self.max_files:
            raise ContractError("declared evidence exceeds the file-count limit")
        files: list[dict[str, Any]] = []
        total = 0
        for relative in sorted(relative_paths):
            if not isinstance(relative, str) or not relative:
                raise ContractError("declared evidence path must be a non-empty string")
            path = (base / relative).resolve()
            if not path.is_relative_to(base) or path.is_symlink() or not path.is_file():
                raise ContractError(f"declared evidence path escapes, is linked, or is missing: {relative}")
            normalized = path.relative_to(base).as_posix()
            if normalized != Path(relative).as_posix():
                raise ContractError(f"declared evidence path is not canonical: {relative}")
            size = path.stat().st_size
            total += size
            if total > self.max_total_bytes:
                raise ContractError("declared evidence exceeds the total-byte limit")
            files.append({"path": normalized, "bytes": size, "sha256": sha256_file(path)})
        return self._store(base, files)

    def export(self, package_sha256: str, output: Path) -> dict[str, Any]:
        """Materialize one verified package without overwriting an existing path."""
        if len(package_sha256) != 64 or any(char not in "0123456789abcdef" for char in package_sha256):
            raise ContractError("package_sha256 must be 64 lowercase hexadecimal characters")
        destination = self.root / "sha256" / package_sha256
        manifest = load_json(destination / "manifest.json")
        if manifest.get("package_sha256") != package_sha256:
            raise ContractError("artifact package address does not match its manifest")
        self._verify_stored(destination, manifest)
        output = output.resolve()
        if output.exists():
            raise ContractError("artifact export destination already exists")
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(destination / "files", output)
        return {**manifest, "exported_to": str(output)}
