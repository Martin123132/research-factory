from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from control_plane.common import (
    ContractError,
    canonical_json_bytes,
    parse_utc,
    sha256_bytes,
    sha256_file,
    utc_now,
    utc_text,
    validate_id,
    validate_sha256,
    write_json,
)
from corrections.ledger import load_json_strict
from release.build_offline_release import MANIFEST_NAME
from release.verify_offline_release import verify_release


REPORT_NAME = "key-person-recovery-report.json"
PUBLIC_DIRECTORY = "public"
SCOPE = "RECOVERY_DRILL_NOT_SCIENTIFIC_EVIDENCE"
BRANCH = "recovered-maintainer"
BOUNDARY = {
    "scientific_evidence": False,
    "promotion_changed": False,
    "quality_control_changed": False,
    "independent_maintainers_proven": False,
    "resilience_04_satisfied": False,
}
DECLARED_CONDITIONS = {
    "founder_present": False,
    "operator_independence": "SELF_ASSERTED_NOT_PROVEN",
    "operator_identity_proven": False,
    "resilience_04_qualification": False,
}
REPORT_KEYS = {
    "schema_version",
    "recovery_id",
    "recorded_at",
    "scope",
    "operator",
    "declared_conditions",
    "offline_release",
    "recovered_clone",
    "administration",
    "boundary",
    "report_sha256",
}


def _schema_path() -> Path:
    return Path(__file__).resolve().with_name("key-person-recovery-v1.schema.json")


def _validator() -> Draft202012Validator:
    schema = load_json_strict(_schema_path())
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:  # pragma: no cover - repository authoring fault
        raise ContractError(f"key-person recovery schema is invalid: {exc}") from exc
    return Draft202012Validator(schema)


def _validate_report(report: dict[str, Any]) -> None:
    errors = sorted(
        _validator().iter_errors(report),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        error = errors[0]
        location = "/".join(str(part) for part in error.absolute_path) or "$"
        raise ContractError(f"key-person recovery report schema violation at {location}: {error.message}")
    if set(report) != REPORT_KEYS:
        raise ContractError("key-person recovery report has an invalid closed shape")
    validate_id(report["recovery_id"], field="recovery_id")
    parse_utc(report["recorded_at"], field="recorded_at")
    validate_id(report["operator"]["operator_id"], field="operator.operator_id")
    for field in ("manifest_sha256", "source_archive_sha256", "history_bundle_sha256"):
        validate_sha256(report["offline_release"][field], field=f"offline_release.{field}")
    source_commit = report["offline_release"]["source_commit"]
    if report["recovered_clone"]["head_commit"] != source_commit:
        raise ContractError("recovered clone does not point to the released source commit")
    if report["declared_conditions"] != DECLARED_CONDITIONS:
        raise ContractError("key-person recovery report attempts to overstate human independence")
    if report["boundary"] != BOUNDARY:
        raise ContractError("key-person recovery report attempts to alter its no-credit boundary")
    unsigned = {key: value for key, value in report.items() if key != "report_sha256"}
    if sha256_bytes(canonical_json_bytes(unsigned)) != report["report_sha256"]:
        raise ContractError("key-person recovery report self-hash does not match")


def _run_git(*arguments: str, cwd: Path | None = None) -> str:
    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ContractError(f"key-person recovery Git operation failed: {' '.join(arguments)}") from exc
    return completed.stdout.strip()


def _artifact_hashes(release_directory: Path, manifest: dict[str, Any]) -> tuple[str, str]:
    by_role = {artifact["role"]: artifact for artifact in manifest["artifacts"]}
    source = by_role.get("tracked-source-snapshot")
    history = by_role.get("recoverable-git-history")
    if not isinstance(source, dict) or not isinstance(history, dict):
        raise ContractError("verified release does not contain both recovery artifacts")
    source_path = release_directory / str(source["path"])
    history_path = release_directory / str(history["path"])
    return sha256_file(source_path), sha256_file(history_path)


def _recover_clone(release_directory: Path, manifest: dict[str, Any], workspace: Path) -> dict[str, Any]:
    history = next(
        artifact
        for artifact in manifest["artifacts"]
        if artifact["role"] == "recoverable-git-history"
    )
    history_path = release_directory / str(history["path"])
    recovered = workspace / "recovered-history"
    _run_git("clone", "--quiet", str(history_path), str(recovered))
    _run_git("switch", "--quiet", "-c", BRANCH, cwd=recovered)
    _run_git("remote", "remove", "origin", cwd=recovered)
    _run_git("fsck", "--no-dangling", cwd=recovered)
    head_commit = _run_git("rev-parse", "HEAD", cwd=recovered)
    if head_commit != manifest["source_commit"]:
        raise ContractError("recovered local branch points to the wrong source commit")
    if _run_git("branch", "--show-current", cwd=recovered) != BRANCH:
        raise ContractError("recovered local branch was not created")
    if _run_git("remote", cwd=recovered):
        raise ContractError("recovered local clone retained a configured remote")
    if _run_git("status", "--porcelain=v1", cwd=recovered):
        raise ContractError("recovered local clone is not clean")
    return {
        "branch": BRANCH,
        "head_commit": head_commit,
        "git_fsck_passed": True,
        "origin_configured": False,
        "working_tree_clean": True,
    }


def _release_manifest(release_directory: Path) -> dict[str, Any]:
    verified = verify_release(release_directory)
    if not isinstance(verified, dict):  # pragma: no cover - enforced by verifier
        raise ContractError("offline release verifier returned an invalid manifest")
    return verified


def _operator(operator_id: str, display_name: str, identity_assurance: str) -> dict[str, str]:
    validate_id(operator_id, field="operator_id")
    if not display_name or len(display_name) > 160:
        raise ContractError("operator display name must be between 1 and 160 characters")
    if identity_assurance not in {"SELF_ASSERTED_LOCAL", "PLATFORM_VERIFIED", "EXTERNALLY_ATTESTED"}:
        raise ContractError("operator identity assurance is unsupported")
    return {
        "operator_id": operator_id,
        "display_name": display_name,
        "identity_assurance": identity_assurance,
        "identity_warning": "IDENTITY_RECORD_IS_NOT_PROOF_OF_AUTHORITY",
    }


def run_key_person_recovery_drill(
    release_directory: Path,
    output: Path,
    *,
    operator_id: str,
    display_name: str,
    identity_assurance: str = "SELF_ASSERTED_LOCAL",
    recovery_id: str | None = None,
    recorded_at: str | None = None,
) -> dict[str, Any]:
    release_directory = release_directory.resolve()
    output = output.resolve()
    if output.exists():
        raise ContractError(f"key-person recovery output already exists: {output}")
    operator = _operator(operator_id, display_name, identity_assurance)
    recovery_id = recovery_id or f"recovery:{uuid.uuid4().hex}"
    validate_id(recovery_id, field="recovery_id")
    recorded_at = recorded_at or utc_text(utc_now())
    parse_utc(recorded_at, field="recorded_at")
    manifest = _release_manifest(release_directory)
    source_hash, history_hash = _artifact_hashes(release_directory, manifest)

    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    workspace = Path(tempfile.mkdtemp(prefix="key-person-recovery-work-"))
    try:
        recovered_clone = _recover_clone(release_directory, manifest, workspace)
        unsigned = {
            "schema_version": 1,
            "recovery_id": recovery_id,
            "recorded_at": recorded_at,
            "scope": SCOPE,
            "operator": operator,
            "declared_conditions": DECLARED_CONDITIONS,
            "offline_release": {
                "manifest_sha256": sha256_file(release_directory / MANIFEST_NAME),
                "source_commit": manifest["source_commit"],
                "source_archive_sha256": source_hash,
                "history_bundle_sha256": history_hash,
            },
            "recovered_clone": recovered_clone,
            "administration": {
                "action": "RECOVERED_LOCAL_BRANCH_CREATED",
                "upstream_write": False,
                "hosted_credentials_required": False,
                "scientific_authority_changed": False,
            },
            "boundary": BOUNDARY,
        }
        report = {**unsigned, "report_sha256": sha256_bytes(canonical_json_bytes(unsigned))}
        _validate_report(report)
        public = staging / PUBLIC_DIRECTORY
        public.mkdir()
        write_json(public / REPORT_NAME, report)
        if {path.name for path in public.iterdir()} != {REPORT_NAME}:
            raise ContractError("key-person recovery drill wrote an unexpected public file")
        os.replace(staging, output)
        return report
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def verify_key_person_recovery_drill(release_directory: Path, output: Path) -> dict[str, Any]:
    release_directory = release_directory.resolve()
    output = output.resolve()
    public = output / PUBLIC_DIRECTORY
    if not public.is_dir() or {path.name for path in public.iterdir()} != {REPORT_NAME}:
        raise ContractError("key-person recovery drill has missing or unexpected public files")
    report = load_json_strict(public / REPORT_NAME)
    if not isinstance(report, dict):  # pragma: no cover - strict loader uses objects here
        raise ContractError("key-person recovery report is not an object")
    _validate_report(report)
    manifest = _release_manifest(release_directory)
    source_hash, history_hash = _artifact_hashes(release_directory, manifest)
    if report["offline_release"] != {
        "manifest_sha256": sha256_file(release_directory / MANIFEST_NAME),
        "source_commit": manifest["source_commit"],
        "source_archive_sha256": source_hash,
        "history_bundle_sha256": history_hash,
    }:
        raise ContractError("key-person recovery report does not bind this verified release")
    workspace = Path(tempfile.mkdtemp(prefix="key-person-recovery-verify-"))
    try:
        clone = _recover_clone(release_directory, manifest, workspace)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
    if report["recovered_clone"] != clone:
        raise ContractError("key-person recovery report does not match a fresh recovered clone")
    return {
        "valid": True,
        "recovery_id": report["recovery_id"],
        "source_commit": manifest["source_commit"],
        "scientific_evidence": False,
        "resilience_04_satisfied": False,
        "operator_identity_proven": False,
    }
