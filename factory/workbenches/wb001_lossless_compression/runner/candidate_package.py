from __future__ import annotations

import argparse
import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from baseline_frontier import verify_pack_hash
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError
from common import (
    WORKBENCH_ROOT,
    ContractError,
    candidate_artifact_manifest,
    canonical_json_bytes,
    evaluator_software_sha256,
    load_and_verify_corpus,
    load_json,
    load_submission,
    load_workbench_config,
    sha256_bytes,
    sha256_file,
    validate_operator_id,
    verify_commitment_hash,
    verify_decision_hash,
    verify_result_hash,
    write_json,
)
from evaluate_local import CandidateExecutionError, evaluate_submission


PACKAGE_TYPE = "wb001_candidate_package"
REFERENCE_SUBMISSION_ID = "wb001-example-zlib-level9-v1"
MAX_PACKAGE_FILES = 64
MAX_PACKAGE_BYTES = 4 * 1024 * 1024


def _utc_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        not value
        or value != path.as_posix()
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ContractError(f"candidate package path is not canonical: {value!r}")
    return path


def _record(root: Path, relative: str) -> dict[str, Any]:
    path = root / Path(*_safe_relative(relative).parts)
    if path.is_symlink() or not path.is_file():
        raise ContractError(f"candidate package file is not regular: {relative}")
    return {"path": relative, "bytes": path.stat().st_size, "sha256": sha256_file(path)}


def _payload_sha256(files: list[dict[str, Any]]) -> str:
    return sha256_bytes(canonical_json_bytes({"schema_version": 1, "files": sorted(files, key=lambda row: row["path"])}))


def _copy(source: Path, destination_root: Path, relative: str) -> None:
    destination = destination_root / Path(*_safe_relative(relative).parts)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def _validate_schema(name: str, document: dict[str, Any]) -> None:
    schema_path = WORKBENCH_ROOT / "schemas" / name
    try:
        schema = load_json(schema_path)
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(document)
    except (SchemaError, ValidationError) as exc:
        raise ContractError(f"{name} validation failed: {exc.message}") from exc


def _candidate_sources(submission_path: Path, submission: dict[str, Any]) -> list[tuple[Path, str]]:
    source_root = submission_path.resolve().parent
    paths = [(submission_path.resolve(), "artifact/submission.json")]
    for relative in submission["candidate"]["source_files"]:
        source = (source_root / relative).resolve()
        if not source.is_relative_to(source_root) or source.is_symlink() or not source.is_file():
            raise ContractError(f"candidate source is not a regular in-tree file: {relative}")
        paths.append((source, f"artifact/{relative}"))
    return paths


def _load_inputs(
    submission_path: Path, result_path: Path, comparison_path: Path
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    config = load_workbench_config()
    submission = load_submission(submission_path, config)
    result = load_json(result_path)
    comparison = load_json(comparison_path)
    verify_result_hash(result)
    verify_decision_hash(comparison)
    artifact = candidate_artifact_manifest(submission_path, submission)
    if result.get("candidate_artifact_sha256") != artifact["artifact_sha256"]:
        raise ContractError("recorded result does not bind the supplied candidate artifact")
    if result.get("artifact_manifest") != artifact:
        raise ContractError("recorded result artifact manifest does not match the supplied candidate")
    if comparison.get("candidate_artifact_sha256") != artifact["artifact_sha256"]:
        raise ContractError("frontier comparison does not bind the supplied candidate artifact")
    if comparison.get("candidate_result_sha256") != result["result_sha256"]:
        raise ContractError("frontier comparison does not bind the supplied result")
    expected_workbench = {"id": config["workbench"]["id"], "version": config["workbench"]["version"]}
    if result.get("workbench") != expected_workbench or comparison.get("workbench") != expected_workbench:
        raise ContractError("recorded evidence targets a different workbench")
    manifest, _ = load_and_verify_corpus(WORKBENCH_ROOT / config["corpus"]["public_manifest"])
    if result.get("corpus", {}).get("corpus_sha256") != manifest["corpus_sha256"]:
        raise ContractError("recorded result does not bind the public corpus commitment")
    if comparison.get("corpus_sha256") != manifest["corpus_sha256"]:
        raise ContractError("frontier comparison does not bind the public corpus commitment")
    baseline_pack = load_json(WORKBENCH_ROOT / "results" / "reference_pack" / "baseline_pack.json")
    verify_pack_hash(baseline_pack)
    if comparison.get("baseline_pack_sha256") != baseline_pack["pack_sha256"]:
        raise ContractError("frontier comparison does not bind the frozen baseline pack")
    return config, submission, result, comparison, artifact


def _handoff(
    *, artifact_sha256: str, result_sha256: str, comparison_sha256: str,
    corpus_sha256: str, pre_handoff_payload_sha256: str, holdout: dict[str, Any]
) -> dict[str, Any]:
    unsigned = {
        "schema_version": 1,
        "handoff_type": "wb001_sealed_evaluator_handoff",
        "candidate_payload_sha256": pre_handoff_payload_sha256,
        "candidate_artifact_sha256": artifact_sha256,
        "recorded_public_result_sha256": result_sha256,
        "frontier_comparison_sha256": comparison_sha256,
        "public_corpus_sha256": corpus_sha256,
        "sealed_holdout": {
            "commitment_sha256": holdout["commitment_sha256"],
            "corpus_sha256": holdout["corpus_sha256"],
            "evaluator_key_id": holdout["evaluator_key_id"],
            "contains_holdout_data": False,
        },
        "admission": {
            "state": "BLOCKED_AWAITING_TWO_OTHER_HUMAN_RERUNS",
            "may_contact_evaluator": False,
            "missing_preconditions": [
                "TWO_OTHER_ACCOUNTABLE_HUMANS_RERUN_THE_SAME_LOCKED_ARTIFACT",
                "EACH_RERUN_USES_THE_REQUIRED_ISOLATED_EVALUATOR_BOUNDARY",
                "RERUN_GATE_CONFIRMS_EXACT_COMPRESSED_HASHES",
                "AUTHENTICATED_EVALUATOR_ISSUES_A_ONE_USE_TOKEN",
            ],
            "service_status": "CONTRACT_ONLY_NO_PUBLIC_EVALUATOR_SERVICE_IS_CLAIMED",
        },
        "agent_boundary": {
            "agent_may_read_this_contract": True,
            "agent_must_not_receive_a_future_one_use_token": True,
            "human_authorizes_any_future_evaluator_submission": True,
        },
        "scientific_standing": {
            "scientific_evidence": False,
            "counts_as_independent_reproduction": False,
            "eligible_for_promotion": False,
        },
    }
    return {**unsigned, "handoff_sha256": sha256_bytes(canonical_json_bytes(unsigned))}


def _start_here() -> str:
    return (
        "# WB-001 candidate package — commissioning only\n\n"
        "This packet locks one candidate source tree, one recorded public result, one frontier decision and the public commitments needed to inspect them. It is not a scientific result, an independent rerun, or permission to execute an unknown candidate locally.\n\n"
        "## Verify without execution\n\n"
        "From a clean Factory checkout, run:\n\n"
        "```powershell\n"
        ".\\.venv\\Scripts\\python.exe workbenches/wb001_lossless_compression/runner/candidate_package.py verify <PACKAGE_DIRECTORY>\n"
        "```\n\n"
        "Verification checks every copied byte, the candidate artifact commitment, recorded-result and frontier-decision hashes, the public corpus commitment, and the sealed-evaluator handoff. It does not open a holdout or run code.\n\n"
        "## Reference-fixture rehearsal only\n\n"
        "The optional `rehearse` command is deliberately limited to the checked-in zlib-level-9 reference fixture and a `demo:` identity. It proves a fresh checkout can rerun the known-safe test fixture. The receipt is commissioning only: it cannot satisfy either other-person rerun, obtain a holdout token, or support promotion.\n\n"
        "A real submitted candidate must use the isolated evaluator and two-other-human rerun gate. `handoff.json` records that blocked state without pretending an evaluator service exists.\n"
    )


def build_candidate_package(
    *, submission_path: Path, result_path: Path, comparison_path: Path, output: Path
) -> dict[str, Any]:
    output = output.resolve()
    if output.exists():
        raise ContractError("candidate package destination already exists")
    submission_path, result_path, comparison_path = (
        submission_path.resolve(), result_path.resolve(), comparison_path.resolve()
    )
    config, submission, result, comparison, artifact = _load_inputs(
        submission_path, result_path, comparison_path
    )
    public_manifest_path = WORKBENCH_ROOT / config["corpus"]["public_manifest"]
    holdout_path = WORKBENCH_ROOT / "data" / "holdout_commitment.json"
    public_key_path = WORKBENCH_ROOT / config["blind_evaluator"]["public_key"]
    evaluator_lock_path = WORKBENCH_ROOT / "isolation" / "evaluator_software.lock.json"
    workbench_path = WORKBENCH_ROOT / "workbench.toml"
    baseline_pack_path = WORKBENCH_ROOT / "results" / "reference_pack" / "baseline_pack.json"
    holdout = load_json(holdout_path)
    verify_commitment_hash(holdout)
    temporary = output.parent / f".{output.name}.{uuid.uuid4().hex}.tmp"
    try:
        sources = _candidate_sources(submission_path, submission)
        sources.extend([
            (result_path, "evidence/recorded-public-result.json"),
            (comparison_path, "evidence/frontier-comparison.json"),
            (baseline_pack_path, "evidence/frozen-baseline-pack.json"),
            (public_manifest_path, "contracts/public-corpus-manifest.json"),
            (holdout_path, "contracts/holdout-commitment.json"),
            (public_key_path, "contracts/evaluator-public-key.json"),
            (evaluator_lock_path, "contracts/evaluator-software.lock.json"),
            (workbench_path, "contracts/workbench.toml"),
        ])
        for source, relative in sources:
            _copy(source, temporary, relative)
        copied_paths = [relative for _, relative in sources]
        initial_records = [_record(temporary, relative) for relative in copied_paths]
        handoff = _handoff(
            artifact_sha256=artifact["artifact_sha256"],
            result_sha256=result["result_sha256"],
            comparison_sha256=comparison["decision_sha256"],
            corpus_sha256=result["corpus"]["corpus_sha256"],
            pre_handoff_payload_sha256=_payload_sha256(initial_records),
            holdout=holdout,
        )
        _validate_schema("evaluator-handoff-v1.schema.json", handoff)
        write_json(temporary / "handoff.json", handoff)
        (temporary / "START_HERE.md").write_text(_start_here(), encoding="utf-8")
        payload_files = initial_records + [_record(temporary, "handoff.json"), _record(temporary, "START_HERE.md")]
        payload_files.sort(key=lambda row: row["path"])
        total = sum(row["bytes"] for row in payload_files)
        if len(payload_files) > MAX_PACKAGE_FILES or total > MAX_PACKAGE_BYTES:
            raise ContractError("candidate package exceeds commissioning package limits")
        payload_sha256 = _payload_sha256(payload_files)
        unsigned = {
            "schema_version": 1,
            "package_type": PACKAGE_TYPE,
            "generated_at": _utc_text(),
            "workbench": {"id": config["workbench"]["id"], "version": config["workbench"]["version"]},
            "candidate": {
                "submission_id": submission["submission_id"],
                "candidate_artifact_sha256": artifact["artifact_sha256"],
                "artifact_manifest": artifact,
                "execution_class": "REFERENCE_FIXTURE_TRUSTED_LOCAL_ONLY" if submission["submission_id"] == REFERENCE_SUBMISSION_ID else "UNTRUSTED_CANDIDATE_ISOLATED_EVALUATOR_REQUIRED",
            },
            "recorded_public_evidence": {
                "result_sha256": result["result_sha256"],
                "frontier_comparison_sha256": comparison["decision_sha256"],
                "baseline_pack_sha256": comparison["baseline_pack_sha256"],
                "frontier_status": comparison["status"],
                "public_corpus_sha256": result["corpus"]["corpus_sha256"],
                "timing_is_advisory": result["execution_boundary"].get("timing_grade") == "advisory",
            },
            "evaluator": {
                "software_sha256": evaluator_software_sha256(),
                "software_lock_path": "contracts/evaluator-software.lock.json",
                "production_rerun_command": "evaluate_isolated.py",
                "local_execution_warning": "DO_NOT_RUN_UNKNOWN_SUBMISSIONS_WITH_EVALUATE_LOCAL",
            },
            "sealed_evaluator_handoff": {
                "path": "handoff.json", "handoff_sha256": handoff["handoff_sha256"],
                "state": handoff["admission"]["state"],
            },
            "payload": {
                "files": payload_files, "payload_sha256": payload_sha256,
                "file_count": len(payload_files), "total_bytes": total,
            },
            "construction_boundary": {
                "operating_mode": "SYNTHETIC_COMMISSIONING", "scientific_evidence": False,
                "counts_as_independent_reproduction": False, "eligible_for_promotion": False,
                "live_research_authorized": False,
            },
        }
        package = {**unsigned, "package_sha256": sha256_bytes(canonical_json_bytes(unsigned))}
        _validate_schema("candidate-package-v1.schema.json", package)
        write_json(temporary / "package.json", package)
        verification = verify_candidate_package(temporary)
        if verification["package_sha256"] != package["package_sha256"]:
            raise ContractError("candidate package failed creation-time verification")
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary.replace(output)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return {
        "created": True, "path": str(output), "package_sha256": package["package_sha256"],
        "candidate_artifact_sha256": artifact["artifact_sha256"],
        "handoff_state": handoff["admission"]["state"], **package["construction_boundary"],
    }


def verify_candidate_package(package_root: Path) -> dict[str, Any]:
    root = package_root.resolve()
    if root.is_symlink() or not root.is_dir() or any(path.is_symlink() for path in root.rglob("*")):
        raise ContractError("candidate package must be a regular directory without symbolic links")
    expected_top = {"artifact", "contracts", "evidence", "handoff.json", "START_HERE.md", "package.json"}
    if {path.name for path in root.iterdir()} != expected_top:
        raise ContractError("candidate package has missing or unexpected top-level entries")
    package = load_json(root / "package.json")
    if package.get("schema_version") != 1 or package.get("package_type") != PACKAGE_TYPE:
        raise ContractError("candidate package header is invalid")
    _validate_schema("candidate-package-v1.schema.json", package)
    unsigned = {key: value for key, value in package.items() if key != "package_sha256"}
    if package.get("package_sha256") != sha256_bytes(canonical_json_bytes(unsigned)):
        raise ContractError("candidate package self-hash does not match")
    boundary = package.get("construction_boundary")
    if not isinstance(boundary, dict) or any(boundary.get(key) is not False for key in ("scientific_evidence", "counts_as_independent_reproduction", "eligible_for_promotion", "live_research_authorized")):
        raise ContractError("candidate package exceeds the commissioning boundary")
    payload = package.get("payload")
    if not isinstance(payload, dict) or not isinstance(payload.get("files"), list):
        raise ContractError("candidate package payload manifest is missing")
    files = payload["files"]
    if not files or len(files) > MAX_PACKAGE_FILES:
        raise ContractError("candidate package payload file count is invalid")
    seen: set[str] = set()
    total = 0
    for row in files:
        if not isinstance(row, dict) or set(row) != {"path", "bytes", "sha256"}:
            raise ContractError("candidate package payload entry is invalid")
        relative = row["path"]
        _safe_relative(relative)
        if relative in seen:
            raise ContractError("candidate package payload contains a duplicate path")
        seen.add(relative)
        if _record(root, relative) != row:
            raise ContractError(f"candidate package payload file does not match: {relative}")
        total += row["bytes"]
    actual_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.relative_to(root).as_posix() != "package.json"
    }
    if (
        actual_files != seen
        or payload.get("file_count") != len(files)
        or payload.get("total_bytes") != total
        or total > MAX_PACKAGE_BYTES
    ):
        raise ContractError("candidate package payload inventory does not match")
    if payload.get("payload_sha256") != _payload_sha256(files):
        raise ContractError("candidate package payload hash does not match")
    expected_directories = {"artifact", "contracts", "evidence"}
    for relative in seen:
        parent = PurePosixPath(relative).parent
        while parent != PurePosixPath("."):
            expected_directories.add(parent.as_posix())
            parent = parent.parent
    actual_directories = {
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_dir()
    }
    if actual_directories != expected_directories:
        raise ContractError("candidate package contains missing or unexpected directories")
    config = load_workbench_config()
    if package.get("workbench") != {"id": config["workbench"]["id"], "version": config["workbench"]["version"]}:
        raise ContractError("candidate package targets a different workbench")
    submission_path = root / "artifact" / "submission.json"
    submission = load_submission(submission_path, config)
    artifact = candidate_artifact_manifest(submission_path, submission)
    candidate = package.get("candidate")
    expected_execution_class = (
        "REFERENCE_FIXTURE_TRUSTED_LOCAL_ONLY"
        if submission["submission_id"] == REFERENCE_SUBMISSION_ID
        else "UNTRUSTED_CANDIDATE_ISOLATED_EVALUATOR_REQUIRED"
    )
    if (
        not isinstance(candidate, dict)
        or candidate.get("submission_id") != submission["submission_id"]
        or candidate.get("artifact_manifest") != artifact
        or candidate.get("candidate_artifact_sha256") != artifact["artifact_sha256"]
        or candidate.get("execution_class") != expected_execution_class
    ):
        raise ContractError("candidate package artifact does not match its source")
    result = load_json(root / "evidence" / "recorded-public-result.json")
    comparison = load_json(root / "evidence" / "frontier-comparison.json")
    verify_result_hash(result)
    verify_decision_hash(comparison)
    if result.get("candidate_artifact_sha256") != artifact["artifact_sha256"] or comparison.get("candidate_artifact_sha256") != artifact["artifact_sha256"] or comparison.get("candidate_result_sha256") != result["result_sha256"]:
        raise ContractError("recorded public evidence does not bind packaged candidate")
    baseline_pack = load_json(root / "evidence" / "frozen-baseline-pack.json")
    verify_pack_hash(baseline_pack)
    if comparison.get("baseline_pack_sha256") != baseline_pack["pack_sha256"]:
        raise ContractError("frontier comparison does not bind packaged baseline pack")
    manifest, _ = load_and_verify_corpus(WORKBENCH_ROOT / config["corpus"]["public_manifest"])
    embedded_manifest_path = root / "contracts" / "public-corpus-manifest.json"
    if (
        sha256_file(embedded_manifest_path)
        != sha256_file(WORKBENCH_ROOT / config["corpus"]["public_manifest"])
        or load_json(embedded_manifest_path) != manifest
        or result.get("corpus", {}).get("corpus_sha256") != manifest["corpus_sha256"]
    ):
        raise ContractError("candidate package public corpus commitment does not match clean checkout")
    embedded_workbench = root / "contracts" / "workbench.toml"
    if sha256_file(embedded_workbench) != sha256_file(WORKBENCH_ROOT / "workbench.toml"):
        raise ContractError("candidate package workbench contract does not match clean checkout")
    embedded_lock = root / "contracts" / "evaluator-software.lock.json"
    evaluator = package.get("evaluator")
    if (
        not isinstance(evaluator, dict)
        or evaluator.get("software_lock_path") != "contracts/evaluator-software.lock.json"
        or evaluator.get("production_rerun_command") != "evaluate_isolated.py"
        or evaluator.get("local_execution_warning") != "DO_NOT_RUN_UNKNOWN_SUBMISSIONS_WITH_EVALUATE_LOCAL"
        or sha256_file(embedded_lock)
        != sha256_file(WORKBENCH_ROOT / "isolation" / "evaluator_software.lock.json")
        or evaluator.get("software_sha256") != load_json(embedded_lock).get("software_sha256")
        or evaluator.get("software_sha256") != evaluator_software_sha256()
    ):
        raise ContractError("candidate package evaluator software does not match clean checkout")
    holdout_path = root / "contracts" / "holdout-commitment.json"
    holdout = load_json(holdout_path)
    verify_commitment_hash(holdout)
    public_key = load_json(root / "contracts" / "evaluator-public-key.json")
    if (
        sha256_file(holdout_path) != sha256_file(WORKBENCH_ROOT / "data" / "holdout_commitment.json")
        or sha256_file(root / "contracts" / "evaluator-public-key.json")
        != sha256_file(WORKBENCH_ROOT / "data" / "evaluator_public_key.json")
        or public_key.get("key_id") != holdout.get("evaluator_key_id")
    ):
        raise ContractError("candidate package evaluator commitments do not match clean checkout")
    handoff = load_json(root / "handoff.json")
    _validate_schema("evaluator-handoff-v1.schema.json", handoff)
    handoff_unsigned = {key: value for key, value in handoff.items() if key != "handoff_sha256"}
    non_handoff_files = [row for row in files if row["path"] not in {"handoff.json", "START_HERE.md"}]
    if handoff.get("handoff_sha256") != sha256_bytes(canonical_json_bytes(handoff_unsigned)) or handoff.get("candidate_payload_sha256") != _payload_sha256(non_handoff_files):
        raise ContractError("sealed evaluator handoff does not bind the candidate payload")
    if handoff.get("candidate_artifact_sha256") != artifact["artifact_sha256"] or handoff.get("sealed_holdout", {}).get("commitment_sha256") != holdout["commitment_sha256"]:
        raise ContractError("sealed evaluator handoff does not bind package evidence")
    admission = handoff.get("admission")
    expected_preconditions = {
        "TWO_OTHER_ACCOUNTABLE_HUMANS_RERUN_THE_SAME_LOCKED_ARTIFACT",
        "EACH_RERUN_USES_THE_REQUIRED_ISOLATED_EVALUATOR_BOUNDARY",
        "RERUN_GATE_CONFIRMS_EXACT_COMPRESSED_HASHES",
        "AUTHENTICATED_EVALUATOR_ISSUES_A_ONE_USE_TOKEN",
    }
    standing = handoff.get("scientific_standing")
    if (
        not isinstance(admission, dict)
        or admission.get("state") != "BLOCKED_AWAITING_TWO_OTHER_HUMAN_RERUNS"
        or admission.get("may_contact_evaluator") is not False
        or set(admission.get("missing_preconditions", [])) != expected_preconditions
        or admission.get("service_status") != "CONTRACT_ONLY_NO_PUBLIC_EVALUATOR_SERVICE_IS_CLAIMED"
        or not isinstance(standing, dict)
        or any(standing.get(key) is not False for key in ("scientific_evidence", "counts_as_independent_reproduction", "eligible_for_promotion"))
    ):
        raise ContractError("sealed evaluator handoff incorrectly grants evaluator access")
    return {
        "valid": True, "path": str(root), "package_sha256": package["package_sha256"],
        "candidate_artifact_sha256": artifact["artifact_sha256"], "payload_sha256": payload["payload_sha256"],
        "handoff_state": admission["state"], "scientific_evidence": False,
        "counts_as_independent_reproduction": False, "eligible_for_promotion": False,
    }


def _fingerprint(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"path": row["path"], "compressed_bytes": row["compressed_bytes"], "compressed_sha256": row["compressed_sha256"]} for row in result["files"]]


def rehearse_clean_clone(*, package_root: Path, operator_id: str, output: Path) -> dict[str, Any]:
    validate_operator_id(operator_id)
    if not operator_id.lower().startswith("demo:"):
        raise ContractError("clean-clone rehearsal only accepts a demo: operator identity")
    verified = verify_candidate_package(package_root)
    root = package_root.resolve()
    package = load_json(root / "package.json")
    if package["candidate"]["execution_class"] != "REFERENCE_FIXTURE_TRUSTED_LOCAL_ONLY" or package["candidate"]["submission_id"] != REFERENCE_SUBMISSION_ID:
        raise ContractError("clean-clone rehearsal will not execute an untrusted candidate package")
    if package["evaluator"]["software_sha256"] != evaluator_software_sha256():
        raise ContractError("clean checkout evaluator software does not match the package")
    try:
        rerun = evaluate_submission(root / "artifact" / "submission.json", operator_id)
    except CandidateExecutionError as exc:
        raise ContractError(f"clean-clone rehearsal reference fixture failed: {exc}") from exc
    recorded = load_json(root / "evidence" / "recorded-public-result.json")
    comparisons = {
        "candidate_artifact_sha256": rerun.get("candidate_artifact_sha256") == recorded.get("candidate_artifact_sha256"),
        "public_corpus_sha256": rerun.get("corpus", {}).get("corpus_sha256") == recorded.get("corpus", {}).get("corpus_sha256"),
        "compressed_fingerprint": rerun.get("hard_gate_pass") and _fingerprint(rerun) == _fingerprint(recorded),
    }
    if not all(comparisons.values()):
        raise ContractError("clean-clone rehearsal differs from recorded deterministic evidence")
    if output.exists():
        raise ContractError("clean-clone rehearsal receipt destination already exists")
    unsigned = {
        "schema_version": 1, "receipt_type": "wb001_clean_clone_rehearsal",
        "generated_at": _utc_text(), "rehearsal_type": "WB001_CLEAN_CLONE_REFERENCE_FIXTURE_REHEARSAL",
        "operator_id": operator_id, "candidate_package_sha256": verified["package_sha256"],
        "candidate_artifact_sha256": rerun["candidate_artifact_sha256"],
        "recorded_result_sha256": recorded["result_sha256"], "rerun_result_sha256": rerun["result_sha256"],
        "exact_comparisons": comparisons, "timings_compared": False,
        "construction_boundary": {
            "scientific_evidence": False, "counts_as_independent_reproduction": False,
            "eligible_for_promotion": False,
            "reason": "single-operator known-safe reference-fixture commissioning rehearsal",
        },
    }
    receipt = {**unsigned, "receipt_sha256": sha256_bytes(canonical_json_bytes(unsigned))}
    write_json(output, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description="Build, verify, or commission a portable WB-001 candidate package")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="build a closed package without executing code")
    build.add_argument("--submission", type=Path, required=True)
    build.add_argument("--result", type=Path, required=True)
    build.add_argument("--comparison", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    verify = sub.add_parser("verify", help="verify a package without executing code")
    verify.add_argument("package", type=Path)
    rehearse = sub.add_parser("rehearse", help="rerun only the known-safe zlib reference fixture")
    rehearse.add_argument("package", type=Path)
    rehearse.add_argument("--operator-id", required=True)
    rehearse.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "build":
            result = build_candidate_package(submission_path=args.submission, result_path=args.result, comparison_path=args.comparison, output=args.output)
        elif args.command == "verify":
            result = verify_candidate_package(args.package)
        else:
            result = rehearse_clean_clone(package_root=args.package, operator_id=args.operator_id, output=args.output)
    except ContractError as exc:
        raise SystemExit(f"WB-001 candidate package failed: {exc}") from exc
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
