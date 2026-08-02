from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from process_control import ProcessOutcome, run_process


LANE_ROOT = Path(__file__).resolve().parents[1]
SUBMISSION_SCHEMA = LANE_ROOT / "digital_compression_submission.schema.json"
RESULT_SCHEMA = LANE_ROOT / "digital_compression_result.schema.json"


class EvaluationError(RuntimeError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def file_record(path: Path) -> dict[str, Any]:
    return {"name": path.name, "bytes": path.stat().st_size, "sha256": sha256_bytes(path.read_bytes())}


def load_validated(path: Path, schema_path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(document), key=lambda item: list(item.path))
    if errors:
        raise EvaluationError("; ".join(error.message for error in errors[:5]))
    return document


def require_regular(path: Path, label: str) -> None:
    if not path.is_file() or path.is_symlink():
        raise EvaluationError(f"{label} must be a regular non-symlink file")
    mode = path.stat().st_mode
    if not stat.S_ISREG(mode):
        raise EvaluationError(f"{label} is not a regular file")


def require_success(outcome: ProcessOutcome, label: str) -> None:
    if outcome.timed_out:
        raise EvaluationError(f"{label} timed out")
    if outcome.output_limit_exceeded:
        raise EvaluationError(f"{label} exceeded the output limit")
    if outcome.returncode != 0:
        detail = outcome.stderr.strip() or outcome.stdout.strip() or f"exit {outcome.returncode}"
        raise EvaluationError(f"{label} failed: {detail[:400]}")


def resolve_command(tokens: list[str]) -> list[str]:
    return [sys.executable if token == "{python}" else token for token in tokens]


def evaluate(submission_path: Path, input_path: Path, *, timeout_seconds: int) -> dict[str, Any]:
    submission_path = submission_path.resolve()
    input_path = input_path.resolve()
    require_regular(submission_path, "submission")
    require_regular(input_path, "input")
    submission = load_validated(submission_path, SUBMISSION_SCHEMA)
    source_root = submission_path.parent
    source_paths: list[Path] = []
    for relative in submission["source_files"]:
        source = (source_root / relative).resolve()
        if not source.is_relative_to(source_root.resolve()):
            raise EvaluationError(f"source path escapes the submission directory: {relative}")
        require_regular(source, f"source {relative}")
        source_paths.append(source)

    source_manifest = [
        {"path": relative, "bytes": path.stat().st_size, "sha256": sha256_bytes(path.read_bytes())}
        for relative, path in zip(submission["source_files"], source_paths, strict=True)
    ]
    source_package_bytes = sum(item["bytes"] for item in source_manifest)
    source_package_sha256 = sha256_bytes(canonical_bytes(source_manifest))
    compress_options = submission["packaging"]["compress_options"]
    decompress_options = submission["packaging"]["decompress_options"]
    option_bytes = len(" ".join([*compress_options, *decompress_options]).encode("utf-8"))

    with tempfile.TemporaryDirectory(prefix="rf-dc-entry-") as temporary_name:
        temporary = Path(temporary_name)
        candidate_root = temporary / "candidate"
        candidate_root.mkdir()
        for relative, source in zip(submission["source_files"], source_paths, strict=True):
            destination = candidate_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        staged_input = temporary / "input.bin"
        shutil.copyfile(input_path, staged_input)
        archive_a = temporary / "archive-a.bin"
        archive_b = temporary / "archive-b.bin"
        restored = temporary / "restored.bin"
        base = resolve_command(submission["command"])
        clean_environment = {"PATH": os.environ.get("PATH", ""), "PYTHONHASHSEED": "0"}
        first = run_process(
            [*base, "compress", str(staged_input), str(archive_a), *compress_options],
            cwd=candidate_root, timeout_seconds=timeout_seconds, output_limit_bytes=65_536,
            environment=clean_environment,
        )
        require_success(first, "first compression")
        require_regular(archive_a, "first archive")
        maximum_archive_bytes = max(10_000_000, staged_input.stat().st_size * 3)
        if archive_a.stat().st_size > maximum_archive_bytes:
            raise EvaluationError("archive exceeds the entry evaluator output limit")
        second = run_process(
            [*base, "compress", str(staged_input), str(archive_b), *compress_options],
            cwd=candidate_root, timeout_seconds=timeout_seconds, output_limit_bytes=65_536,
            environment=clean_environment,
        )
        require_success(second, "second compression")
        require_regular(archive_b, "second archive")
        decode = run_process(
            [*base, "decompress", str(archive_a), str(restored), *decompress_options],
            cwd=candidate_root, timeout_seconds=timeout_seconds, output_limit_bytes=65_536,
            environment=clean_environment,
        )
        require_success(decode, "decompression")
        require_regular(restored, "restored output")
        archive_hash = sha256_bytes(archive_a.read_bytes())
        deterministic = archive_hash == sha256_bytes(archive_b.read_bytes())
        exact = sha256_bytes(staged_input.read_bytes()) == sha256_bytes(restored.read_bytes())
        if not deterministic or not exact:
            raise EvaluationError("exact restoration or deterministic archive gate failed")
        archive_bytes = archive_a.stat().st_size
        counted_size = source_package_bytes + archive_bytes + option_bytes
        result: dict[str, Any] = {
            "schema_version": 1,
            "result_type": "DIGITAL_COMPRESSION_ENTRY_RESULT",
            "workbench_code": submission["workbench_code"],
            "submission_id": submission["submission_id"],
            "input": file_record(staged_input),
            "artifact": {
                "source_package_bytes": source_package_bytes,
                "source_package_sha256": source_package_sha256,
                "archive_bytes": archive_bytes,
                "archive_sha256": archive_hash,
                "option_bytes": option_bytes,
                "entry_counted_size_bytes": counted_size,
            },
            "hard_gates": {"candidate_processes_pass": True, "exact_round_trip": exact, "deterministic_archive": deterministic},
            "metrics": {"round_trip_fraction": 1, "determinism_fraction": 1, "entry_counted_size_bytes": counted_size},
            "advisory": {
                "compress_elapsed_ns": first.elapsed_ns,
                "decompress_elapsed_ns": decode.elapsed_ns,
                "peak_rss_bytes": max(first.peak_rss_bytes, second.peak_rss_bytes, decode.peak_rss_bytes),
            },
            "credit_boundary": {
                "scope": "ENTRY_GATE_ONLY", "scientific_evidence": False,
                "counts_as_independent_reproduction": False, "eligible_for_promotion": False,
                "official_hutter_score": False,
            },
        }
        result["result_sha256"] = sha256_bytes(canonical_bytes(result))
        schema = json.loads(RESULT_SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(result)
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Trusted-local exact compression entry evaluator")
    parser.add_argument("--submission", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--i-understand-this-runs-trusted-local-code", action="store_true")
    args = parser.parse_args()
    if not args.i_understand_this_runs_trusted_local_code:
        raise EvaluationError("explicit trusted-local-code acknowledgement is required")
    result = evaluate(args.submission, args.input, timeout_seconds=args.timeout_seconds)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"PASS entry-only result: {result['result_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
