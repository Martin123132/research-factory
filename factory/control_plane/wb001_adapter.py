from __future__ import annotations

import tomllib
from decimal import Decimal
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from .common import (
    ContractError,
    canonical_json_bytes,
    load_json,
    sha256_bytes,
    sha256_file,
    validate_sha256,
)


ADVANCE_STATUSES = {"PUBLIC_SIZE_CANDIDATE", "FRONTIER_ADVANCE", "ELIGIBLE_FOR_REPRODUCTION"}


def _contract_row(round_document: dict[str, Any], name: str) -> dict[str, Any]:
    for row in round_document["frozen_contracts"]:
        if row["name"] == name:
            return row
    raise ContractError(f"round is missing frozen contract {name!r}")


def _logical_contract(round_document: dict[str, Any], name: str) -> str:
    value = _contract_row(round_document, name).get("logical_commitment_sha256")
    validate_sha256(value, field=f"{name}.logical_commitment_sha256")
    return value


def _frozen_path(
    factory_root: Path,
    round_document: dict[str, Any],
    name: str,
) -> tuple[Path, dict[str, Any]]:
    row = _contract_row(round_document, name)
    root = factory_root.resolve()
    path = (root / row["path"]).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ContractError(f"frozen contract {name!r} is outside the factory or missing")
    if sha256_file(path) != row["sha256"]:
        raise ContractError(f"frozen contract {name!r} has drifted")
    return path, row


def _verify_self_hash(document: dict[str, Any], field: str) -> None:
    expected = document.get(field)
    validate_sha256(expected, field=field)
    unsigned = {key: value for key, value in document.items() if key != field}
    if sha256_bytes(canonical_json_bytes(unsigned)) != expected:
        raise ContractError(f"{field} does not match the document contents")


def _verified_artifact_manifest(result: dict[str, Any]) -> dict[str, Any]:
    manifest = result.get("artifact_manifest")
    if not isinstance(manifest, dict):
        raise ContractError("evaluation result is missing its candidate artifact manifest")
    expected = result.get("candidate_artifact_sha256")
    validate_sha256(expected, field="candidate_artifact_sha256")
    if manifest.get("artifact_sha256") != expected:
        raise ContractError("candidate artifact manifest targets a different artifact")
    core = {key: value for key, value in manifest.items() if key != "artifact_sha256"}
    if sha256_bytes(canonical_json_bytes(core)) != expected:
        raise ContractError("candidate artifact manifest commitment is invalid")
    if not isinstance(manifest.get("submission"), dict):
        raise ContractError("candidate artifact manifest is missing its submission")
    validate_sha256(manifest.get("submission_sha256"), field="artifact_manifest.submission_sha256")
    if not isinstance(manifest.get("source_files"), list) or not manifest["source_files"]:
        raise ContractError("candidate artifact manifest is missing source files")
    return manifest


def verify_candidate_artifact_submission(
    submission_path: Path,
    *,
    result: dict[str, Any],
) -> tuple[Path, list[str]]:
    """Verify the exact metric-free source package rerunners will receive."""
    manifest = _verified_artifact_manifest(result)
    submission_path = submission_path.resolve()
    if submission_path.is_symlink() or not submission_path.is_file():
        raise ContractError("candidate submission must be a regular JSON file")
    submission = load_json(submission_path)
    if submission != manifest["submission"] or sha256_file(submission_path) != manifest["submission_sha256"]:
        raise ContractError("candidate submission does not match the result artifact manifest")
    declared_sources = submission.get("candidate", {}).get("source_files")
    rows = manifest["source_files"]
    if (
        not isinstance(declared_sources, list)
        or not all(isinstance(value, str) and value for value in declared_sources)
        or len(declared_sources) != len(set(declared_sources))
    ):
        raise ContractError("candidate submission has an invalid source file list")
    row_paths = [row.get("path") for row in rows if isinstance(row, dict)]
    if sorted(declared_sources) != sorted(row_paths):
        raise ContractError("candidate source declaration differs from the artifact manifest")
    base = submission_path.parent.resolve()
    for row in rows:
        path = (base / row["path"]).resolve()
        validate_sha256(row.get("sha256"), field=f"artifact_manifest.{row['path']}.sha256")
        if (
            not path.is_relative_to(base)
            or path.is_symlink()
            or not path.is_file()
            or not isinstance(row.get("bytes"), int)
            or row["bytes"] < 0
            or path.stat().st_size != row["bytes"]
            or sha256_file(path) != row["sha256"]
        ):
            raise ContractError(f"candidate source does not match the artifact manifest: {row['path']}")
    return base, [submission_path.relative_to(base).as_posix(), *declared_sources]


def extract_result_observation(
    result_path: Path,
    *,
    factory_root: Path,
    expected_operator_id: str,
    expected_artifact_sha256: str,
    round_document: dict[str, Any],
    allow_failed_hard_gate: bool = False,
    require_secure_boundary: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    result = load_json(result_path)
    result_schema_path = (
        factory_root
        / "workbenches"
        / "wb001_lossless_compression"
        / "schemas"
        / "result.schema.json"
    )
    try:
        Draft202012Validator(load_json(result_schema_path)).validate(result)
    except ValidationError as exc:
        raise ContractError(f"WB-001 result does not satisfy its schema: {exc.message}") from exc
    _verify_self_hash(result, "result_sha256")
    if result.get("schema_version") != 2 or result.get("result_type") != "wb001_evaluation":
        raise ContractError("rerun evidence must be a WB-001 v0.2 evaluation result")
    if result.get("runner_version") != "0.2.0":
        raise ContractError("evaluation result uses the wrong WB-001 runner version")
    validate_sha256(result.get("runtime_fingerprint_sha256"), field="runtime_fingerprint_sha256")
    if not isinstance(result.get("execution_boundary"), dict):
        raise ContractError("evaluation result is missing its execution boundary")
    if require_secure_boundary and result["execution_boundary"].get("security_boundary") is not True:
        raise ContractError("independent reruns must use the frozen isolated security boundary")
    expected_workbench = {
        "id": round_document["workbench"]["id"],
        "version": round_document["workbench"]["version"],
    }
    if result.get("workbench") != expected_workbench:
        raise ContractError("evaluation result targets the wrong workbench epoch")
    if result.get("operator_id") != expected_operator_id:
        raise ContractError("evaluation result operator does not match the assigned operator")
    if result.get("candidate_artifact_sha256") != expected_artifact_sha256:
        raise ContractError("evaluation result targets the wrong candidate artifact")
    _verified_artifact_manifest(result)
    manifest_path, manifest_contract = _frozen_path(
        factory_root, round_document, "public_corpus_manifest"
    )
    manifest = load_json(manifest_path)
    manifest_files = manifest.get("files")
    if manifest.get("schema_version") != 1 or not isinstance(manifest_files, list) or not manifest_files:
        raise ContractError("frozen public corpus manifest is malformed")
    manifest_core = {
        "schema_version": manifest.get("schema_version"),
        "profile": manifest.get("profile"),
        "root": manifest.get("root"),
        "files": manifest_files,
    }
    expected_corpus_sha256 = _logical_contract(round_document, "public_corpus_manifest")
    if (
        manifest.get("corpus_sha256") != expected_corpus_sha256
        or sha256_bytes(canonical_json_bytes(manifest_core)) != expected_corpus_sha256
    ):
        raise ContractError("frozen public corpus logical commitment is invalid")
    corpus = result.get("corpus")
    if (
        not isinstance(corpus, dict)
        or corpus.get("profile") != manifest.get("profile")
        or corpus.get("manifest_sha256") != manifest_contract["sha256"]
        or corpus.get("corpus_sha256") != expected_corpus_sha256
        or corpus.get("files") != len(manifest_files)
    ):
        raise ContractError("evaluation result targets the wrong public corpus")

    hard_gate_pass = result.get("hard_gate_pass") is True
    if not hard_gate_pass and not allow_failed_hard_gate:
        raise ContractError("candidate result failed the exact hard gate")
    files = result.get("files")
    aggregate = result.get("aggregate")
    if not isinstance(files, list) or not files or not isinstance(aggregate, dict):
        raise ContractError("evaluation result is missing file or aggregate measurements")
    required_file_fields = {
        "path",
        "original_bytes",
        "original_sha256",
        "compressed_bytes",
        "compressed_sha256",
        "deterministic",
        "round_trip_pass",
    }
    normalized_files: list[dict[str, Any]] = []
    paths: set[str] = set()
    for row in files:
        if not isinstance(row, dict) or not required_file_fields <= set(row):
            raise ContractError("evaluation result has an incomplete file measurement")
        if not isinstance(row["path"], str) or row["path"] in paths:
            raise ContractError("evaluation result file paths must be unique strings")
        paths.add(row["path"])
        for field in ("original_sha256", "compressed_sha256"):
            validate_sha256(row[field], field=f"files.{row['path']}.{field}")
        for field in ("original_bytes", "compressed_bytes"):
            if not isinstance(row[field], int) or row[field] < 0:
                raise ContractError(f"files.{row['path']}.{field} must be a nonnegative integer")
        if hard_gate_pass and (row["deterministic"] is not True or row["round_trip_pass"] is not True):
            raise ContractError("hard-gate-passing result contains a failed file gate")
        normalized_files.append(
            {
                "path": row["path"],
                "original_bytes": row["original_bytes"],
                "original_sha256": row["original_sha256"],
                "compressed_bytes": row["compressed_bytes"],
                "compressed_sha256": row["compressed_sha256"],
                "deterministic": row["deterministic"],
                "round_trip_pass": row["round_trip_pass"],
            }
        )
    normalized_files.sort(key=lambda row: row["path"])
    expected_originals: dict[str, tuple[int, str]] = {}
    for row in manifest_files:
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            raise ContractError("frozen public corpus contains an invalid file entry")
        validate_sha256(row.get("sha256"), field=f"manifest.{row.get('path')}.sha256")
        if not isinstance(row.get("bytes"), int) or row["bytes"] < 0:
            raise ContractError("frozen public corpus contains an invalid file size")
        if row["path"] in expected_originals:
            raise ContractError("frozen public corpus paths must be unique")
        expected_originals[row["path"]] = (row["bytes"], row["sha256"])
    actual_originals = {
        row["path"]: (row["original_bytes"], row["original_sha256"])
        for row in normalized_files
    }
    if actual_originals != expected_originals:
        raise ContractError(
            "evaluation result must contain the exact frozen public file set, sizes, and input hashes"
        )
    if aggregate.get("files") != len(normalized_files):
        raise ContractError("aggregate file count does not match file measurements")
    if aggregate.get("total_input_bytes") != sum(row["original_bytes"] for row in normalized_files):
        raise ContractError("aggregate input bytes do not match file measurements")
    if aggregate.get("total_compressed_bytes") != sum(row["compressed_bytes"] for row in normalized_files):
        raise ContractError("aggregate compressed bytes do not match file measurements")

    fingerprint_core = {
        "workbench": expected_workbench,
        "candidate_artifact_sha256": expected_artifact_sha256,
        "corpus_sha256": corpus["corpus_sha256"],
        "corpus_manifest_sha256": corpus["manifest_sha256"],
        "hard_gate_pass": hard_gate_pass,
        "files": normalized_files,
        "total_input_bytes": aggregate["total_input_bytes"],
        "total_compressed_bytes": aggregate["total_compressed_bytes"],
    }
    observation = {
        "schema_version": 1,
        "observation_type": "wb001_exact_result_observation",
        "result_sha256": result["result_sha256"],
        "candidate_artifact_sha256": expected_artifact_sha256,
        "corpus_sha256": corpus["corpus_sha256"],
        "corpus_manifest_sha256": corpus["manifest_sha256"],
        "hard_gate_pass": hard_gate_pass,
        "exact_output_fingerprint_sha256": sha256_bytes(canonical_json_bytes(fingerprint_core)),
    }
    return result, observation


def verify_comparison(
    comparison_path: Path,
    *,
    factory_root: Path,
    result: dict[str, Any],
    result_kind: str,
    round_document: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    comparison = load_json(comparison_path)
    _verify_self_hash(comparison, "decision_sha256")
    if comparison.get("schema_version") != 2 or comparison.get("decision_type") != "wb001_frontier_comparison":
        raise ContractError("candidate comparison must be a WB-001 v0.2 frontier decision")
    bindings = {
        "workbench": result["workbench"],
        "candidate_result_sha256": result["result_sha256"],
        "candidate_artifact_sha256": result["candidate_artifact_sha256"],
        "corpus_sha256": result["corpus"]["corpus_sha256"],
        "baseline_pack_sha256": _logical_contract(round_document, "reference_frontier_pack"),
    }
    for field, expected in bindings.items():
        if comparison.get(field) != expected:
            raise ContractError(f"frontier comparison has the wrong {field} binding")

    pack_path, _ = _frozen_path(factory_root, round_document, "reference_frontier_pack")
    pack = load_json(pack_path)
    _verify_self_hash(pack, "pack_sha256")
    if (
        pack.get("pack_sha256") != bindings["baseline_pack_sha256"]
        or pack.get("workbench") != result["workbench"]
        or pack.get("corpus_sha256") != result["corpus"]["corpus_sha256"]
        or pack.get("corpus_manifest_sha256") != result["corpus"]["manifest_sha256"]
    ):
        raise ContractError("frozen frontier pack is not bound to this workbench and corpus")
    if pack.get("promotable") is not False:
        raise ContractError("this local pilot only accepts its frozen non-promotable frontier pack")
    entries = pack.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ContractError("frozen frontier pack has no baseline entries")
    try:
        best_size = min(int(row["metrics"]["total_compressed_bytes"]) for row in entries)
        candidate_size = int(result["aggregate"]["total_compressed_bytes"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ContractError("frontier size metrics are incomplete") from exc

    config_path, _ = _frozen_path(factory_root, round_document, "workbench_contract")
    try:
        with config_path.open("rb") as handle:
            config = tomllib.load(handle)
        minimum_gain = Decimal(str(config["promotion"]["minimum_size_improvement_fraction"]))
    except (OSError, tomllib.TOMLDecodeError, KeyError, ValueError) as exc:
        raise ContractError("could not read the frozen size-improvement threshold") from exc
    if minimum_gain < 0 or minimum_gain >= 1:
        raise ContractError("frozen size-improvement threshold must be in [0, 1)")
    expected_status = (
        "PUBLIC_SIZE_CANDIDATE"
        if Decimal(candidate_size) <= Decimal(best_size) * (Decimal(1) - minimum_gain)
        else "VALID_NO_CONFIRMED_GAIN"
    )
    candidate_metrics = comparison.get("candidate_metrics")
    if (
        not isinstance(candidate_metrics, dict)
        or candidate_metrics.get("total_compressed_bytes") != candidate_size
    ):
        raise ContractError("frontier comparison metrics do not match the exact candidate result")
    if comparison.get("status") != expected_status:
        raise ContractError(
            f"frontier comparison status is wrong; evaluator derived {expected_status!r}"
        )
    if comparison.get("eligible_for_promotion") is not False:
        raise ContractError("a local public-size candidate is not yet promotion eligible")
    if result_kind != "CANDIDATE" or expected_status != "PUBLIC_SIZE_CANDIDATE":
        raise ContractError(
            f"result does not advance the frozen exact-size frontier (derived {expected_status})"
        )
    return comparison, {
        "comparison_status": comparison["status"],
        "comparison_decision_sha256": comparison["decision_sha256"],
        "baseline_pack_sha256": comparison["baseline_pack_sha256"],
        "comparison_recomputed_by_control_plane": True,
    }
