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
SUBMISSION_SCHEMA = LANE_ROOT / "digital_optimization_submission.schema.json"
RESULT_SCHEMA = LANE_ROOT / "digital_optimization_result.schema.json"
MAX_CANDIDATE_RESULT_BYTES = 1_048_576


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
    if not path.is_file() or path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
        raise EvaluationError(f"{label} must be a regular non-symlink file")


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


def parse_explicit_symmetric_tsp(path: Path) -> tuple[dict[str, str], list[list[int]]]:
    """Parse only the deliberately narrow TSPLIB EXPLICIT/FULL_MATRIX subset."""

    require_regular(path, "TSP instance")
    headers: dict[str, str] = {}
    weight_tokens: list[str] = []
    in_weights = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if not in_weights:
            if line == "EDGE_WEIGHT_SECTION":
                in_weights = True
                continue
            key, separator, value = line.partition(":")
            if not separator:
                parts = line.split(maxsplit=1)
                if len(parts) != 2:
                    raise EvaluationError(f"malformed TSPLIB header line: {line[:80]}")
                key, value = parts
            key = key.strip().upper()
            value = value.strip()
            if key in headers:
                raise EvaluationError(f"duplicate TSPLIB header: {key}")
            headers[key] = value
        elif line == "EOF":
            break
        else:
            weight_tokens.extend(line.split())
    if not in_weights:
        raise EvaluationError("EDGE_WEIGHT_SECTION is missing")
    required = {
        "NAME": None,
        "TYPE": "TSP",
        "DIMENSION": None,
        "EDGE_WEIGHT_TYPE": "EXPLICIT",
        "EDGE_WEIGHT_FORMAT": "FULL_MATRIX",
    }
    for key, expected in required.items():
        if key not in headers:
            raise EvaluationError(f"required TSPLIB header is missing: {key}")
        if expected is not None and headers[key].upper() != expected:
            raise EvaluationError(f"unsupported {key}: {headers[key]}")
    try:
        dimension = int(headers["DIMENSION"])
    except ValueError as error:
        raise EvaluationError("DIMENSION must be an integer") from error
    if dimension < 3 or dimension > 10_000:
        raise EvaluationError("DIMENSION is outside the evaluator boundary")
    if len(weight_tokens) != dimension * dimension:
        raise EvaluationError("FULL_MATRIX token count does not match DIMENSION")
    try:
        weights = [int(token) for token in weight_tokens]
    except ValueError as error:
        raise EvaluationError("FULL_MATRIX weights must be integers") from error
    if any(weight < 0 for weight in weights):
        raise EvaluationError("negative edge weights are unsupported")
    matrix = [weights[index:index + dimension] for index in range(0, len(weights), dimension)]
    for row in range(dimension):
        if matrix[row][row] != 0:
            raise EvaluationError("symmetric TSP diagonal weights must be zero")
        for column in range(row + 1, dimension):
            if matrix[row][column] != matrix[column][row]:
                raise EvaluationError("SYMMETRIC_TSP_V1 rejects asymmetric matrices")
    return headers, matrix


def canonical_tour(raw_tour: Any, dimension: int) -> list[int]:
    if not isinstance(raw_tour, list) or len(raw_tour) != dimension:
        raise EvaluationError("tour must contain DIMENSION nodes without a repeated closing node")
    if any(isinstance(node, bool) or not isinstance(node, int) for node in raw_tour):
        raise EvaluationError("tour nodes must be integers")
    if set(raw_tour) != set(range(1, dimension + 1)):
        raise EvaluationError("tour must contain every node exactly once and no unknown node")
    minimum_index = raw_tour.index(min(raw_tour))
    forward = raw_tour[minimum_index:] + raw_tour[:minimum_index]
    reverse = [forward[0], *reversed(forward[1:])]
    return min(forward, reverse)


def route_length(tour: list[int], matrix: list[list[int]]) -> int:
    return sum(matrix[tour[index] - 1][tour[(index + 1) % len(tour)] - 1] for index in range(len(tour)))


def load_candidate_tour(path: Path, dimension: int) -> list[int]:
    require_regular(path, "candidate result")
    if path.stat().st_size > MAX_CANDIDATE_RESULT_BYTES:
        raise EvaluationError("candidate result exceeds the evaluator size limit")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EvaluationError("candidate result must be UTF-8 JSON") from error
    if not isinstance(document, dict) or set(document) != {"tour"}:
        raise EvaluationError("candidate result must contain exactly one field: tour")
    return canonical_tour(document["tour"], dimension)


def evaluate(
    submission_path: Path,
    input_path: Path,
    *,
    reference_length: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    submission_path = submission_path.resolve()
    input_path = input_path.resolve()
    require_regular(submission_path, "submission")
    require_regular(input_path, "input")
    if reference_length < 0:
        raise EvaluationError("reference length must be non-negative")
    submission = load_validated(submission_path, SUBMISSION_SCHEMA)
    headers, matrix = parse_explicit_symmetric_tsp(input_path)
    dimension = len(matrix)
    source_root = submission_path.parent.resolve()
    source_paths: list[Path] = []
    for relative in submission["source_files"]:
        source = (source_root / relative).resolve()
        if not source.is_relative_to(source_root):
            raise EvaluationError(f"source path escapes the submission directory: {relative}")
        require_regular(source, f"source {relative}")
        source_paths.append(source)
    source_manifest = [
        {"path": relative, "bytes": path.stat().st_size, "sha256": sha256_bytes(path.read_bytes())}
        for relative, path in zip(submission["source_files"], source_paths, strict=True)
    ]
    source_package_bytes = sum(item["bytes"] for item in source_manifest)
    source_package_sha256 = sha256_bytes(canonical_bytes(source_manifest))

    with tempfile.TemporaryDirectory(prefix="rf-opt-entry-") as temporary_name:
        temporary = Path(temporary_name)
        candidate_root = temporary / "candidate"
        candidate_root.mkdir()
        for relative, source in zip(submission["source_files"], source_paths, strict=True):
            destination = candidate_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        staged_input = temporary / "instance.tsp"
        shutil.copyfile(input_path, staged_input)
        locked_input_hash = sha256_bytes(staged_input.read_bytes())
        result_a = temporary / "tour-a.json"
        result_b = temporary / "tour-b.json"
        base = resolve_command(submission["command"])
        clean_environment = {"PATH": os.environ.get("PATH", ""), "PYTHONHASHSEED": "0"}

        outcomes: list[ProcessOutcome] = []
        for label, output in (("first solve", result_a), ("second solve", result_b)):
            outcome = run_process(
                [*base, "solve", str(staged_input), str(output), "--seed", str(submission["seed"])],
                cwd=candidate_root,
                timeout_seconds=timeout_seconds,
                output_limit_bytes=65_536,
                environment=clean_environment,
            )
            require_success(outcome, label)
            if sha256_bytes(staged_input.read_bytes()) != locked_input_hash:
                raise EvaluationError("candidate modified the staged instance")
            outcomes.append(outcome)

        tour_a = load_candidate_tour(result_a, dimension)
        tour_b = load_candidate_tour(result_b, dimension)
        length_a = route_length(tour_a, matrix)
        length_b = route_length(tour_b, matrix)
        if tour_a != tour_b or length_a != length_b:
            raise EvaluationError("same-seed canonical tour or route length is not deterministic")
        if length_a < reference_length:
            raise EvaluationError("candidate beat the entry reference; the locked known answer must be audited")
        gap = 0 if reference_length == 0 and length_a == 0 else (
            float("inf") if reference_length == 0 else (length_a - reference_length) / reference_length
        )
        if gap == float("inf"):
            raise EvaluationError("a zero reference cannot score a positive route")
        result: dict[str, Any] = {
            "schema_version": 1,
            "result_type": "DIGITAL_OPTIMIZATION_ENTRY_RESULT",
            "workbench_code": submission["workbench_code"],
            "submission_id": submission["submission_id"],
            "input": file_record(staged_input),
            "instance": {
                "name": headers["NAME"],
                "problem_plugin": submission["problem_plugin"],
                "dimension": dimension,
                "edge_weight_type": headers["EDGE_WEIGHT_TYPE"],
                "edge_weight_format": headers["EDGE_WEIGHT_FORMAT"],
                "reference_length": reference_length,
            },
            "artifact": {
                "source_package_bytes": source_package_bytes,
                "source_package_sha256": source_package_sha256,
                "tour": tour_a,
                "tour_sha256": sha256_bytes(canonical_bytes(tour_a)),
            },
            "hard_gates": {
                "candidate_processes_pass": True,
                "supported_instance": True,
                "tour_valid": True,
                "exact_length_accounting": True,
                "same_seed_determinism": True,
            },
            "metrics": {
                "supported_instance": True,
                "tour_valid": True,
                "route_length": length_a,
                "length_accounting_difference": 0,
                "determinism_fraction": 1,
                "optimality_gap_fraction": gap,
            },
            "advisory": {
                "first_solve_elapsed_ns": outcomes[0].elapsed_ns,
                "second_solve_elapsed_ns": outcomes[1].elapsed_ns,
                "peak_rss_bytes": max(outcome.peak_rss_bytes for outcome in outcomes),
            },
            "credit_boundary": {
                "scope": "ENTRY_GATE_ONLY",
                "scientific_evidence": False,
                "counts_as_independent_reproduction": False,
                "eligible_for_promotion": False,
                "official_tsplib_score": False,
                "optimum_claim_verified": False,
            },
        }
        result["result_sha256"] = sha256_bytes(canonical_bytes(result))
        Draft202012Validator(json.loads(RESULT_SCHEMA.read_text(encoding="utf-8"))).validate(result)
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Trusted-local symmetric TSP entry evaluator")
    parser.add_argument("--submission", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--reference-length", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--i-understand-this-runs-trusted-local-code", action="store_true")
    args = parser.parse_args()
    if not args.i_understand_this_runs_trusted_local_code:
        raise EvaluationError("explicit trusted-local-code acknowledgement is required")
    result = evaluate(
        args.submission,
        args.input,
        reference_length=args.reference_length,
        timeout_seconds=args.timeout_seconds,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"PASS entry-only result: {result['result_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
