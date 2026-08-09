from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError


WORKBENCH_ROOT = Path(__file__).resolve().parents[1]
FACTORY_ROOT = WORKBENCH_ROOT.parents[1]
REPOSITORY_ROOT = FACTORY_ROOT.parent
STANDARD_ROOT = FACTORY_ROOT / "workbench_standard" / "commissioning"
REFERENCE_SUBMISSION_ID = "factory-reference-held-karp-v1"
PACKAGE_TYPE = "wb013_entry_fixture_package"
MAX_PACKAGE_FILES = 48
MAX_PACKAGE_BYTES = 4 * 1024 * 1024


class ContractError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    import hashlib

    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_json(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"could not read JSON document {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise ContractError(f"expected a JSON object in {path}")
    return document


def _validate_schema(name: str, document: dict[str, Any]) -> None:
    try:
        schema = load_json(WORKBENCH_ROOT / "schemas" / name)
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(document)
    except (SchemaError, ValidationError) as exc:
        raise ContractError(f"{name} validation failed: {exc.message}") from exc


def _safe_relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        not value
        or value != path.as_posix()
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ContractError(f"entry package path is not canonical: {value!r}")
    return path


def _record(root: Path, relative: str) -> dict[str, Any]:
    path = root / Path(*_safe_relative(relative).parts)
    if path.is_symlink() or not path.is_file():
        raise ContractError(f"entry package file is not regular: {relative}")
    return {"path": relative, "bytes": path.stat().st_size, "sha256": sha256_file(path)}


def _payload_sha256(files: list[dict[str, Any]]) -> str:
    return sha256_bytes(canonical_bytes({"schema_version": 1, "files": sorted(files, key=lambda row: row["path"])}))


def _copy(source: Path, destination_root: Path, relative: str) -> None:
    if source.is_symlink() or not source.is_file():
        raise ContractError(f"entry package source is not a regular file: {source}")
    destination = destination_root / Path(*_safe_relative(relative).parts)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def _source_manifest(submission_path: Path, submission: dict[str, Any]) -> list[dict[str, Any]]:
    source_root = submission_path.resolve().parent
    manifest: list[dict[str, Any]] = []
    for relative in submission["source_files"]:
        source = (source_root / relative).resolve()
        if not source.is_relative_to(source_root) or source.is_symlink() or not source.is_file():
            raise ContractError(f"candidate source is not a regular in-tree file: {relative}")
        manifest.append({"path": relative, "bytes": source.stat().st_size, "sha256": sha256_file(source)})
    return manifest


def _source_package_sha256(manifest: list[dict[str, Any]]) -> str:
    return sha256_bytes(canonical_bytes(sorted(manifest, key=lambda row: row["path"])))


def _load_submission(path: Path) -> dict[str, Any]:
    submission = load_json(path)
    schema_path = STANDARD_ROOT / "digital_optimization_submission.schema.json"
    try:
        Draft202012Validator(load_json(schema_path)).validate(submission)
    except ValidationError as exc:
        raise ContractError(f"submission schema validation failed: {exc.message}") from exc
    if submission["workbench_code"] != "WB-013":
        raise ContractError("submission targets a different workbench")
    return submission


def _verify_result_hash(result: dict[str, Any]) -> None:
    expected = result.get("result_sha256")
    unsigned = {key: value for key, value in result.items() if key != "result_sha256"}
    if expected != sha256_bytes(canonical_bytes(unsigned)):
        raise ContractError("entry result hash does not match")


def _stable_evidence(result: dict[str, Any]) -> dict[str, Any]:
    return {key: result[key] for key in ("input", "instance", "artifact", "hard_gates", "metrics")}


def _commissioning_assets() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    commissioning_path = WORKBENCH_ROOT / "commissioning.json"
    commissioning = load_json(commissioning_path)
    override_schema = STANDARD_ROOT / "digital-optimization-override-v1.schema.json"
    try:
        Draft202012Validator(load_json(override_schema)).validate(commissioning)
    except ValidationError as exc:
        raise ContractError(f"commissioning contract validation failed: {exc.message}") from exc
    if commissioning["workbench_code"] != "WB-013":
        raise ContractError("commissioning contract targets a different workbench")
    snapshot = [{
        "role": "commissioning_contract",
        "source_path": "factory/workbenches/wb013_travelling_salesperson_route_kernel/commissioning.json",
        "package_path": "locked/commissioning_contract/commissioning.json",
        "sha256": sha256_file(commissioning_path),
    }]
    roles: set[str] = set()
    for declared in commissioning["assets"]:
        role = declared["role"]
        source_path = declared["path"]
        source = REPOSITORY_ROOT / Path(*_safe_relative(source_path).parts)
        if role in roles or not source.is_file() or source.is_symlink():
            raise ContractError(f"invalid locked commissioning asset: {role}")
        actual = sha256_file(source)
        if actual != declared["sha256"]:
            raise ContractError(f"commissioning asset hash mismatch: {source_path}")
        snapshot.append(
            {
                "role": role,
                "source_path": source_path,
                "package_path": f"locked/{role}/{source.name}",
                "sha256": actual,
            }
        )
        roles.add(role)
    return commissioning, snapshot


def _handoff(*, artifact_sha256: str, fixture_sha256: str, payload_sha256: str) -> dict[str, Any]:
    unsigned = {
        "schema_version": 1,
        "handoff_type": "wb013_entry_fixture_evaluator_handoff",
        "candidate_payload_sha256": payload_sha256,
        "candidate_artifact_sha256": artifact_sha256,
        "entry_fixture_sha256": fixture_sha256,
        "admission": {
            "state": "NOT_ELIGIBLE_ENTRY_ONLY",
            "may_contact_evaluator": False,
            "missing_preconditions": [
                "OFFICIAL_TSPLIB_INPUTS_ACQUIRED_AND_HASHED",
                "SUPPORTED_TSPLIB_DISTANCE_CONFORMANCE_COMPLETED",
                "FROZEN_OFFICIAL_COMPARATOR_AND_OPTIMUM_CERTIFICATE_PROTOCOL",
                "PROMOTION_GRADE_ISOLATED_RUNNER_AND_BUDGET",
                "TWO_OTHER_ACCOUNTABLE_HUMANS_RERUN_THE_LOCKED_ARTIFACT",
                "CENTRAL_BLIND_EVALUATOR_DEPLOYED",
            ],
            "service_status": "CONTRACT_ONLY_NO_EVALUATOR_SERVICE_IS_CLAIMED",
        },
        "agent_boundary": {
            "agent_may_read_this_contract": True,
            "agent_must_not_receive_a_future_evaluator_token": True,
            "human_authorizes_any_future_evaluator_submission": True,
        },
        "scientific_standing": {
            "scientific_evidence": False,
            "counts_as_independent_reproduction": False,
            "eligible_for_promotion": False,
            "official_tsplib_score": False,
        },
    }
    return {**unsigned, "handoff_sha256": sha256_bytes(canonical_bytes(unsigned))}


def _start_here() -> str:
    return (
        "# WB-013 entry-fixture packet — construction only\n\n"
        "This packet locks the factory-owned 10-node `EXPLICIT/FULL_MATRIX` TSP fixture, its known-answer reference candidate, the trusted-local evaluator assets and the current limitations. It is not a TSPLIB benchmark, an optimum claim, an independent reproduction, or permission to run an unknown solver locally.\n\n"
        "## Verify without execution\n\n"
        "```powershell\n"
        ".\\.venv\\Scripts\\python.exe workbenches/wb013_travelling_salesperson_route_kernel/scripts/entry_package.py verify <PACKAGE_DIRECTORY>\n"
        "```\n\n"
        "Verification requires a checkout whose locked entry assets still match and does not run candidate code.\n\n"
        "## Reference-fixture rehearsal only\n\n"
        "`rehearse` accepts only the checked-in reference Held–Karp fixture and a `demo:` identity. It compares the stable known-answer evidence while deliberately ignoring advisory timing and memory observations. Its receipt has zero scientific, replication, promotion and official-TSPLIB credit.\n\n"
        "The sealed-evaluator handoff is `NOT_ELIGIBLE_ENTRY_ONLY`. It remains blocked even if one or two people run this fixture: official inputs, distance conformance, a promotion boundary and an evaluator service do not exist yet.\n"
    )


def build_entry_package(*, output: Path) -> dict[str, Any]:
    output = output.resolve()
    if output.exists():
        raise ContractError("entry package destination already exists")
    submission_path = WORKBENCH_ROOT / "examples" / "reference_solver" / "submission.json"
    submission = _load_submission(submission_path)
    if submission["submission_id"] != REFERENCE_SUBMISSION_ID:
        raise ContractError("entry package is restricted to the known-safe reference submission")
    manifest = _source_manifest(submission_path, submission)
    artifact_sha256 = _source_package_sha256(manifest)
    expected = load_json(WORKBENCH_ROOT / "baselines" / "entry_expected.json")
    reference = load_json(WORKBENCH_ROOT / "baselines" / "entry_reference.json")
    fixture_path = WORKBENCH_ROOT / "data" / "entry_fixture.tsp"
    if expected["stable_evidence"]["artifact"]["source_package_sha256"] != artifact_sha256:
        raise ContractError("reference expected evidence does not bind the reference candidate source")
    if expected["stable_evidence"]["input"]["sha256"] != sha256_file(fixture_path):
        raise ContractError("reference expected evidence does not bind the entry fixture")
    commissioning, assets = _commissioning_assets()
    temporary = output.parent / f".{output.name}.{uuid.uuid4().hex}.tmp"
    try:
        sources: list[tuple[Path, str]] = [(submission_path, "candidate/submission.json")]
        sources.extend(
            ((submission_path.parent / row["path"], f"candidate/{row['path']}") for row in manifest)
        )
        sources.extend([
            (fixture_path, "fixture/entry_fixture.tsp"),
            (WORKBENCH_ROOT / "baselines" / "entry_expected.json", "evidence/entry_expected.json"),
            (WORKBENCH_ROOT / "baselines" / "entry_reference.json", "evidence/entry_reference.json"),
        ])
        for asset in assets:
            source = REPOSITORY_ROOT / Path(*_safe_relative(asset["source_path"]).parts)
            sources.append((source, asset["package_path"]))
        for source, relative in sources:
            _copy(source, temporary, relative)
        initial_records = [_record(temporary, relative) for _, relative in sources]
        handoff = _handoff(
            artifact_sha256=artifact_sha256,
            fixture_sha256=sha256_file(fixture_path),
            payload_sha256=_payload_sha256(initial_records),
        )
        _validate_schema("evaluator-handoff-v1.schema.json", handoff)
        write_json(temporary / "handoff.json", handoff)
        (temporary / "START_HERE.md").write_text(_start_here(), encoding="utf-8")
        payload_files = initial_records + [_record(temporary, "handoff.json"), _record(temporary, "START_HERE.md")]
        payload_files.sort(key=lambda row: row["path"])
        total = sum(row["bytes"] for row in payload_files)
        if len(payload_files) > MAX_PACKAGE_FILES or total > MAX_PACKAGE_BYTES:
            raise ContractError("entry package exceeds construction package limits")
        unsigned = {
            "schema_version": 1,
            "package_type": PACKAGE_TYPE,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "workbench": {"code": "WB-013", "implementation_version": commissioning["implementation_version"]},
            "candidate": {
                "submission_id": submission["submission_id"],
                "source_manifest": manifest,
                "source_package_sha256": artifact_sha256,
                "execution_class": "REFERENCE_FIXTURE_TRUSTED_LOCAL_ONLY",
            },
            "entry_fixture": {
                "fixture_sha256": sha256_file(fixture_path),
                "reference_length": reference["reference_length"],
                "scope": "ENTRY_GATE_ONLY",
            },
            "locked_assets": assets,
            "sealed_evaluator_handoff": {
                "path": "handoff.json", "handoff_sha256": handoff["handoff_sha256"],
                "state": handoff["admission"]["state"],
            },
            "payload": {
                "files": payload_files, "payload_sha256": _payload_sha256(payload_files),
                "file_count": len(payload_files), "total_bytes": total,
            },
            "construction_boundary": {
                "operating_mode": "HANGAR_CONSTRUCTION", "scientific_evidence": False,
                "counts_as_independent_reproduction": False, "eligible_for_promotion": False,
                "official_tsplib_score": False, "live_research_authorized": False,
            },
        }
        package = {**unsigned, "package_sha256": sha256_bytes(canonical_bytes(unsigned))}
        _validate_schema("entry-package-v1.schema.json", package)
        write_json(temporary / "package.json", package)
        verification = verify_entry_package(temporary)
        if verification["package_sha256"] != package["package_sha256"]:
            raise ContractError("entry package failed creation-time verification")
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary.replace(output)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return {
        "created": True, "path": str(output), "package_sha256": package["package_sha256"],
        "candidate_artifact_sha256": artifact_sha256, "handoff_state": handoff["admission"]["state"],
        **package["construction_boundary"],
    }


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def _expected_directories(files: list[dict[str, Any]]) -> set[str]:
    expected = {"candidate", "fixture", "evidence", "locked"}
    for row in files:
        parent = PurePosixPath(row["path"]).parent
        while parent != PurePosixPath("."):
            expected.add(parent.as_posix())
            parent = parent.parent
    return expected


def verify_entry_package(package_root: Path) -> dict[str, Any]:
    root = package_root.resolve()
    if root.is_symlink() or not root.is_dir() or any(path.is_symlink() for path in root.rglob("*")):
        raise ContractError("entry package must be a regular directory without symbolic links")
    expected_top = {"candidate", "fixture", "evidence", "locked", "handoff.json", "START_HERE.md", "package.json"}
    if {path.name for path in root.iterdir()} != expected_top:
        raise ContractError("entry package has missing or unexpected top-level entries")
    package = load_json(root / "package.json")
    if package.get("schema_version") != 1 or package.get("package_type") != PACKAGE_TYPE:
        raise ContractError("entry package header is invalid")
    _validate_schema("entry-package-v1.schema.json", package)
    unsigned = {key: value for key, value in package.items() if key != "package_sha256"}
    if package.get("package_sha256") != sha256_bytes(canonical_bytes(unsigned)):
        raise ContractError("entry package self-hash does not match")
    boundary = package["construction_boundary"]
    if any(boundary.get(key) is not False for key in ("scientific_evidence", "counts_as_independent_reproduction", "eligible_for_promotion", "official_tsplib_score", "live_research_authorized")):
        raise ContractError("entry package exceeds the construction boundary")
    payload = package["payload"]
    files = payload["files"]
    if not files or len(files) > MAX_PACKAGE_FILES:
        raise ContractError("entry package payload file count is invalid")
    seen: set[str] = set()
    total = 0
    for row in files:
        if not isinstance(row, dict) or set(row) != {"path", "bytes", "sha256"}:
            raise ContractError("entry package payload entry is invalid")
        relative = row["path"]
        _safe_relative(relative)
        if relative in seen or _record(root, relative) != row:
            raise ContractError(f"entry package payload file does not match: {relative}")
        seen.add(relative)
        total += row["bytes"]
    actual_files = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file() and path.relative_to(root).as_posix() != "package.json"}
    actual_directories = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_dir()}
    if actual_files != seen or actual_directories != _expected_directories(files) or payload["file_count"] != len(files) or payload["total_bytes"] != total or total > MAX_PACKAGE_BYTES:
        raise ContractError("entry package payload inventory does not match")
    if payload["payload_sha256"] != _payload_sha256(files):
        raise ContractError("entry package payload hash does not match")

    submission_path = root / "candidate" / "submission.json"
    submission = _load_submission(submission_path)
    manifest = _source_manifest(submission_path, submission)
    candidate = package["candidate"]
    artifact_sha256 = _source_package_sha256(manifest)
    if (
        submission["submission_id"] != REFERENCE_SUBMISSION_ID
        or candidate["submission_id"] != submission["submission_id"]
        or candidate["source_manifest"] != manifest
        or candidate["source_package_sha256"] != artifact_sha256
        or candidate["execution_class"] != "REFERENCE_FIXTURE_TRUSTED_LOCAL_ONLY"
    ):
        raise ContractError("entry package candidate does not match its source")
    expected = load_json(root / "evidence" / "entry_expected.json")
    reference = load_json(root / "evidence" / "entry_reference.json")
    fixture = root / "fixture" / "entry_fixture.tsp"
    if (
        sha256_file(fixture) != package["entry_fixture"]["fixture_sha256"]
        or expected["stable_evidence"]["artifact"]["source_package_sha256"] != artifact_sha256
        or expected["stable_evidence"]["input"]["sha256"] != sha256_file(fixture)
        or reference["reference_length"] != package["entry_fixture"]["reference_length"]
        or package["entry_fixture"]["scope"] != "ENTRY_GATE_ONLY"
    ):
        raise ContractError("entry package known-answer evidence does not match")
    commissioning, current_assets = _commissioning_assets()
    if package["workbench"] != {"code": "WB-013", "implementation_version": commissioning["implementation_version"]}:
        raise ContractError("entry package targets a different workbench")
    locked_assets = package["locked_assets"]
    if locked_assets != current_assets:
        raise ContractError("entry package locked assets do not match clean checkout")
    for asset in locked_assets:
        if _record(root, asset["package_path"])["sha256"] != asset["sha256"]:
            raise ContractError(f"entry package locked asset changed: {asset['role']}")
    handoff = load_json(root / "handoff.json")
    _validate_schema("evaluator-handoff-v1.schema.json", handoff)
    handoff_unsigned = {key: value for key, value in handoff.items() if key != "handoff_sha256"}
    non_handoff_files = [row for row in files if row["path"] not in {"handoff.json", "START_HERE.md"}]
    if (
        handoff["handoff_sha256"] != sha256_bytes(canonical_bytes(handoff_unsigned))
        or handoff["candidate_payload_sha256"] != _payload_sha256(non_handoff_files)
        or handoff["candidate_artifact_sha256"] != artifact_sha256
        or handoff["entry_fixture_sha256"] != sha256_file(fixture)
        or handoff["admission"]["may_contact_evaluator"] is not False
    ):
        raise ContractError("entry package evaluator handoff does not match")
    return {
        "valid": True, "path": str(root), "package_sha256": package["package_sha256"],
        "candidate_artifact_sha256": artifact_sha256, "handoff_state": handoff["admission"]["state"],
        "scientific_evidence": False, "counts_as_independent_reproduction": False,
        "eligible_for_promotion": False, "official_tsplib_score": False,
    }


def rehearse_entry_fixture(*, package_root: Path, operator_id: str, output: Path) -> dict[str, Any]:
    if not operator_id.lower().startswith("demo:"):
        raise ContractError("entry-fixture rehearsal only accepts a demo: operator identity")
    verified = verify_entry_package(package_root)
    root = package_root.resolve()
    package = load_json(root / "package.json")
    reference_submission = WORKBENCH_ROOT / "examples" / "reference_solver" / "submission.json"
    checked_in_manifest = _source_manifest(reference_submission, _load_submission(reference_submission))
    if package["candidate"]["source_manifest"] != checked_in_manifest:
        raise ContractError("entry-fixture rehearsal will not execute a changed candidate source")
    with tempfile.TemporaryDirectory(prefix="wb013-package-rehearsal-") as temporary:
        entry_result = Path(temporary) / "entry-result.json"
        completed = subprocess.run(
            [sys.executable, str(WORKBENCH_ROOT / "scripts" / "run_entry_gate.py"), "--fixture", "--output", str(entry_result)],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if completed.returncode != 0:
            raise ContractError(f"reference entry fixture failed: {completed.stderr.strip()[:400]}")
        result = load_json(entry_result)
    _verify_result_hash(result)
    expected = load_json(root / "evidence" / "entry_expected.json")
    if _stable_evidence(result) != expected["stable_evidence"]:
        raise ContractError("reference entry fixture differs from locked stable evidence")
    if output.exists():
        raise ContractError("entry-fixture rehearsal receipt destination already exists")
    comparisons = {
        "source_package_sha256": result["artifact"]["source_package_sha256"] == verified["candidate_artifact_sha256"],
        "fixture_sha256": result["input"]["sha256"] == package["entry_fixture"]["fixture_sha256"],
        "stable_known_answer": True,
    }
    unsigned = {
        "schema_version": 1, "receipt_type": "wb013_entry_fixture_rehearsal",
        "generated_at": datetime.now(timezone.utc).isoformat(), "operator_id": operator_id,
        "candidate_package_sha256": verified["package_sha256"],
        "candidate_artifact_sha256": verified["candidate_artifact_sha256"],
        "entry_result_sha256": result["result_sha256"], "exact_comparisons": comparisons,
        "advisory_timing_compared": False,
        "construction_boundary": {
            "scientific_evidence": False, "counts_as_independent_reproduction": False,
            "eligible_for_promotion": False, "official_tsplib_score": False,
            "reason": "single-operator known-safe entry-fixture construction rehearsal",
        },
    }
    receipt = {**unsigned, "receipt_sha256": sha256_bytes(canonical_bytes(unsigned))}
    write_json(output, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description="Build, verify, or rehearse a closed WB-013 entry-fixture packet")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="build the known-answer entry packet without running code")
    build.add_argument("--output", type=Path, required=True)
    verify = sub.add_parser("verify", help="verify a packet without running code")
    verify.add_argument("package", type=Path)
    rehearse = sub.add_parser("rehearse", help="rerun only the known-safe reference entry fixture")
    rehearse.add_argument("package", type=Path)
    rehearse.add_argument("--operator-id", required=True)
    rehearse.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "build":
            result = build_entry_package(output=args.output)
        elif args.command == "verify":
            result = verify_entry_package(args.package)
        else:
            result = rehearse_entry_fixture(package_root=args.package, operator_id=args.operator_id, output=args.output)
    except (ContractError, subprocess.TimeoutExpired) as exc:
        raise SystemExit(f"WB-013 entry package failed: {exc}") from exc
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
