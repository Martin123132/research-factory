from __future__ import annotations

import hashlib
import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Any


WORKBENCH_ROOT = Path(__file__).resolve().parents[1]
OPERATOR_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@-]{2,127}$")


class ContractError(ValueError):
    """Raised when an artifact does not satisfy the workbench contract."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"Could not read JSON contract {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"Expected a JSON object in {path}")
    return value


def load_workbench_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or WORKBENCH_ROOT / "workbench.toml"
    try:
        with config_path.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ContractError(f"Could not read workbench config {config_path}: {exc}") from exc


def validate_operator_id(operator_id: str, *, allow_demo: bool = True) -> None:
    if not OPERATOR_ID_RE.fullmatch(operator_id):
        raise ContractError(
            "operator_id must be 3-128 characters using letters, numbers, '.', '_', ':', '@', or '-'"
        )
    if not allow_demo and operator_id.lower().startswith("demo:"):
        raise ContractError("demo operator IDs cannot satisfy an independence gate")


def _require_dict(parent: dict[str, Any], key: str, context: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise ContractError(f"{context}.{key} must be an object")
    return value


def load_submission(path: Path, config: dict[str, Any]) -> dict[str, Any]:
    submission = load_json(path)
    if submission.get("schema_version") != 1:
        raise ContractError("submission.schema_version must equal 1")

    for key in ("submission_id", "workbench", "candidate", "method"):
        if key not in submission:
            raise ContractError(f"submission is missing required field {key!r}")

    workbench = _require_dict(submission, "workbench", "submission")
    expected = config["workbench"]
    if workbench.get("id") != expected["id"]:
        raise ContractError("submission targets the wrong workbench ID")
    if workbench.get("version") != expected["version"]:
        raise ContractError("submission targets the wrong workbench version")

    candidate = _require_dict(submission, "candidate", "submission")
    command = candidate.get("command")
    source_files = candidate.get("source_files")
    if not isinstance(command, list) or not command or not all(isinstance(x, str) and x for x in command):
        raise ContractError("submission.candidate.command must be a non-empty string array")
    if not isinstance(source_files, list) or not source_files or not all(
        isinstance(x, str) and x for x in source_files
    ):
        raise ContractError("submission.candidate.source_files must be a non-empty string array")
    if candidate.get("deterministic") is not True:
        raise ContractError("WB-001 v0.2 requires candidate.deterministic=true")
    if candidate.get("protocol") != config["measurement"]["protocol"]:
        raise ContractError(
            f"submission.candidate.protocol must equal {config['measurement']['protocol']!r}"
        )

    return submission


def candidate_artifact_manifest(
    submission_path: Path,
    submission: dict[str, Any],
) -> dict[str, Any]:
    root = submission_path.resolve().parent
    source_hashes: list[dict[str, Any]] = []
    for relative in submission["candidate"]["source_files"]:
        source_path = (root / relative).resolve()
        if not source_path.is_relative_to(root):
            raise ContractError(f"candidate source escapes its submission directory: {relative}")
        if source_path.is_symlink():
            raise ContractError(f"candidate source must not be a symbolic link: {relative}")
        if not source_path.is_file():
            raise ContractError(f"candidate source file does not exist: {relative}")
        source_hashes.append(
            {
                "path": source_path.relative_to(root).as_posix(),
                "bytes": source_path.stat().st_size,
                "sha256": sha256_file(source_path),
            }
        )

    core = {
        "submission": submission,
        "submission_sha256": sha256_file(submission_path),
        "source_files": sorted(source_hashes, key=lambda row: row["path"]),
    }
    return {**core, "artifact_sha256": sha256_bytes(canonical_json_bytes(core))}


def resolve_candidate_command(submission: dict[str, Any]) -> list[str]:
    command = list(submission["candidate"]["command"])
    return [sys.executable if token == "{python}" else token for token in command]


def load_and_verify_corpus(manifest_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = load_json(manifest_path)
    if manifest.get("schema_version") != 1:
        raise ContractError("corpus manifest schema_version must equal 1")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise ContractError("corpus manifest must contain at least one file")

    expected_commitment = manifest.get("corpus_sha256")
    commitment_payload = {
        "schema_version": manifest.get("schema_version"),
        "profile": manifest.get("profile"),
        "root": manifest.get("root"),
        "files": files,
    }
    actual_commitment = sha256_bytes(canonical_json_bytes(commitment_payload))
    if expected_commitment != actual_commitment:
        raise ContractError("corpus manifest commitment does not match its contents")

    corpus_root = (manifest_path.parent / manifest.get("root", "public")).resolve()
    verified: list[dict[str, Any]] = []
    for entry in files:
        if not isinstance(entry, dict):
            raise ContractError("corpus manifest file entries must be objects")
        relative = entry.get("path")
        if not isinstance(relative, str):
            raise ContractError("corpus file path must be a string")
        path = (corpus_root / relative).resolve()
        if not path.is_relative_to(corpus_root):
            raise ContractError(f"corpus path escapes the corpus root: {relative}")
        if not path.is_file():
            raise ContractError(f"corpus file is missing: {relative}")
        if path.stat().st_size != entry.get("bytes"):
            raise ContractError(f"corpus file size differs from manifest: {relative}")
        if sha256_file(path) != entry.get("sha256"):
            raise ContractError(f"corpus file hash differs from manifest: {relative}")
        verified.append({**entry, "absolute_path": path})

    return manifest, verified


def verify_result_hash(result: dict[str, Any]) -> None:
    expected = result.get("result_sha256")
    unsigned = {key: value for key, value in result.items() if key != "result_sha256"}
    actual = sha256_bytes(canonical_json_bytes(unsigned))
    if expected != actual:
        raise ContractError("result_sha256 does not match the result contents")


def verify_decision_hash(decision: dict[str, Any]) -> None:
    expected = decision.get("decision_sha256")
    unsigned = {key: value for key, value in decision.items() if key != "decision_sha256"}
    actual = sha256_bytes(canonical_json_bytes(unsigned))
    if expected != actual:
        raise ContractError("decision_sha256 does not match the decision contents")


def verify_commitment_hash(commitment: dict[str, Any]) -> None:
    expected = commitment.get("commitment_sha256")
    unsigned = {key: value for key, value in commitment.items() if key != "commitment_sha256"}
    if expected != sha256_bytes(canonical_json_bytes(unsigned)):
        raise ContractError("holdout commitment hash does not match its contents")


def evaluator_software_sha256() -> str:
    lock = load_json(WORKBENCH_ROOT / "isolation" / "evaluator_software.lock.json")
    declared = lock.get("files")
    if lock.get("lock_type") != "wb001_evaluator" or not isinstance(declared, list):
        raise ContractError("evaluator software lock is malformed")
    prefix = "workbenches/wb001_lossless_compression/"
    files = []
    for row in declared:
        relative = row.get("path")
        if not isinstance(relative, str) or not relative.startswith(prefix):
            raise ContractError("evaluator software lock contains an invalid path")
        local_relative = relative[len(prefix) :]
        files.append({"path": relative, "sha256": sha256_file(WORKBENCH_ROOT / local_relative)})
    core = {"schema_version": 1, "lock_type": "wb001_evaluator", "files": files}
    return sha256_bytes(canonical_json_bytes(core))
