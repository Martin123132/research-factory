"""Versioned dependency profiles; not a sandbox or scientific qualification."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import re
import stat
import sys
from pathlib import Path, PurePosixPath
from typing import Any


LEGACY_PROFILE = "wb001-pilot-001-v1"
PIN = re.compile(r"([A-Za-z0-9][A-Za-z0-9._-]*)==([A-Za-z0-9][A-Za-z0-9.!+_-]*)")
BOUNDARY = {
    "scientific_evidence": False,
    "counts_as_independent_reproduction": False,
    "eligible_for_promotion": False,
    "live_research_authorized": False,
    "proves_os_or_process_isolation": False,
}


class EnvironmentProfileError(ValueError):
    pass


def _closed(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise EnvironmentProfileError(f"{label}: fields differ from the closed format")
    return value


def _safe_file(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or "\\" in relative or ":" in relative:
        raise EnvironmentProfileError("unsafe environment path")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or pure.as_posix() != relative or any(p in {".", ".."} for p in pure.parts) or not pure.parts:
        raise EnvironmentProfileError("unsafe environment path")
    root = root.resolve()
    path = root
    for part in pure.parts:
        path = path / part
        try:
            info = path.lstat()
        except OSError as exc:
            raise EnvironmentProfileError(f"missing environment path: {relative}") from exc
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
            raise EnvironmentProfileError("environment paths cannot use links or junctions")
    if not path.is_file() or not path.resolve().is_relative_to(root):
        raise EnvironmentProfileError("environment path must be a file within the factory")
    return path


def _load(path: Path) -> dict[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise EnvironmentProfileError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    if path.stat().st_size > 131072:
        raise EnvironmentProfileError("environment JSON exceeds size limit")
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise EnvironmentProfileError(f"invalid environment JSON: {path.name}") from exc
    if not isinstance(value, dict):
        raise EnvironmentProfileError("environment JSON must be an object")
    return value


def _hashed_file(root: Path, record: dict[str, Any]) -> Path:
    path = _safe_file(root, record["path"])
    if not isinstance(record["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", record["sha256"]):
        raise EnvironmentProfileError("invalid environment SHA-256")
    if hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
        raise EnvironmentProfileError(f"environment hash mismatch: {record['path']}")
    return path


def _pins(path: Path) -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = PIN.fullmatch(line)
        if not match:
            raise EnvironmentProfileError("environment locks require exact package==version pins")
        name = re.sub(r"[-_.]+", "-", match[1]).lower()
        if name in pins:
            raise EnvironmentProfileError(f"duplicate environment dependency: {name}")
        pins[name] = match[2]
    if not pins:
        raise EnvironmentProfileError("environment lock cannot be empty")
    return pins


def profiles(root: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    index = _closed(_load(_safe_file(root, "environments/index.json")), {"schema_version", "current_engine", "profiles"}, "environment index")
    if type(index["schema_version"]) is not int or index["schema_version"] != 1:
        raise EnvironmentProfileError("unsupported environment index version")
    if not isinstance(index["profiles"], list) or not 1 <= len(index["profiles"]) <= 100:
        raise EnvironmentProfileError("invalid environment profile count")
    loaded = {}
    for entry in index["profiles"]:
        _closed(entry, {"environment_id", "path", "sha256"}, "environment entry")
        identity = entry["environment_id"]
        if not isinstance(identity, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", identity) or identity in loaded:
            raise EnvironmentProfileError("duplicate or invalid environment ID")
        if entry["path"] != f"environments/versions/{identity}/manifest.json":
            raise EnvironmentProfileError("environment ID and versioned path disagree")
        value = _closed(_load(_hashed_file(root, entry)), {"schema_version", "environment_id", "role", "python_minimum", "lock", "round_binding"}, "environment manifest")
        if type(value["schema_version"]) is not int or value["schema_version"] != 1 or value["environment_id"] != identity:
            raise EnvironmentProfileError("environment identity/version mismatch")
        minimum = value["python_minimum"]
        if not isinstance(minimum, list) or len(minimum) != 2 or any(type(n) is not int or n < 0 for n in minimum) or minimum < [3, 11]:
            raise EnvironmentProfileError("invalid Python minimum")
        _closed(value["lock"], {"path", "sha256"}, "dependency lock")
        pins = _pins(_hashed_file(root, value["lock"]))
        if value["role"] == "ENGINE_MAINTENANCE":
            if value["round_binding"] is not None or value["lock"]["path"] != f"environments/versions/{identity}/requirements.lock":
                raise EnvironmentProfileError("maintenance profiles need their own lock and no round binding")
        elif value["role"] == "FROZEN_ROUND":
            binding = _closed(value["round_binding"], {"round_id", "path", "sha256"}, "round binding")
            round_doc = _load(_hashed_file(root, binding))
            if round_doc.get("round_id") != binding["round_id"]:
                raise EnvironmentProfileError("frozen round identity mismatch")
            locks = [r for r in round_doc.get("frozen_contracts", []) if r.get("name") == "factory_dependency_lock"]
            if len(locks) != 1 or any(locks[0].get(k) != value["lock"][k] for k in ("path", "sha256")):
                raise EnvironmentProfileError("environment is not the round's frozen dependency lock")
        else:
            raise EnvironmentProfileError("unknown environment role")
        loaded[identity] = {**value, "manifest_sha256": entry["sha256"], "pins": pins}
    if not isinstance(index["current_engine"], str) or loaded.get(index["current_engine"], {}).get("role") != "ENGINE_MAINTENANCE":
        raise EnvironmentProfileError("current engine must select a maintenance profile")
    legacy = loaded.get(LEGACY_PROFILE, {})
    if legacy.get("role") != "FROZEN_ROUND" or legacy.get("round_binding", {}).get("round_id") != "WB001-PILOT-001":
        raise EnvironmentProfileError("the legacy pilot profile must remain registered")
    return index, loaded


def inspect_profiles(root: Path) -> dict[str, Any]:
    index, loaded = profiles(root)
    return {"current_engine": index["current_engine"], "profiles": list(loaded.values()), "boundary": dict(BOUNDARY)}


def check_runtime(root: Path, identity: str) -> dict[str, Any]:
    _, loaded = profiles(root)
    if identity not in loaded:
        raise EnvironmentProfileError(f"unregistered environment: {identity}")
    profile = loaded[identity]
    actual = {}
    for name in profile["pins"]:
        try:
            actual[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            actual[name] = None
    mismatches = {name: {"expected": version, "observed": actual[name]} for name, version in profile["pins"].items() if actual[name] != version}
    python_ok = tuple(sys.version_info[:2]) >= tuple(profile["python_minimum"])
    return {
        "environment_id": identity,
        "manifest_sha256": profile["manifest_sha256"],
        "lock_sha256": profile["lock"]["sha256"],
        "matches": not mismatches and python_ok,
        "mismatches": mismatches,
        "python_compatible": python_ok,
        "runtime": {"python": platform.python_version(), "implementation": platform.python_implementation(), "platform": platform.platform(), "dependencies": actual},
        "additional_packages_not_checked": True,
        "boundary": dict(BOUNDARY),
    }


def require_runtime(root: Path, identity: str) -> dict[str, Any]:
    report = check_runtime(root, identity)
    if not report["matches"]:
        raise EnvironmentProfileError(f"environment {identity} does not match this interpreter; activate its pinned environment first. Mismatches: {report['mismatches']}; Python compatible: {report['python_compatible']}")
    return report


def rehearse(root: Path, identity: str) -> dict[str, Any]:
    report = require_runtime(root, identity)
    import zlib
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    # Public known-answer construction fixture, never a production signing key.
    payload = b"Research Factory synthetic environment fixture\n" * 32
    key = Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"public environment fixture key, not a credential").digest())
    compressed = zlib.compress(payload, level=9)
    if zlib.decompress(compressed) != payload:
        raise EnvironmentProfileError("synthetic fixture failed exact round-trip")
    signature = key.sign(payload)
    key.public_key().verify(signature, payload)
    report["fixture"] = {
        "fixture_id": "environment-smoke-v1",
        "input_sha256": hashlib.sha256(payload).hexdigest(),
        "compressed_sha256": hashlib.sha256(compressed).hexdigest(),
        "signature_sha256": hashlib.sha256(signature).hexdigest(),
        "round_trip_exact": True,
        "signature_verified": True,
    }
    report["runtime"]["zlib"] = zlib.ZLIB_RUNTIME_VERSION
    report["report_sha256"] = hashlib.sha256(json.dumps(report, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return report
