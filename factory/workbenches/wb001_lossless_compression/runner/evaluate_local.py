from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

from common import (
    WORKBENCH_ROOT,
    ContractError,
    candidate_artifact_manifest,
    canonical_json_bytes,
    load_and_verify_corpus,
    load_submission,
    load_workbench_config,
    resolve_candidate_command,
    sha256_bytes,
    sha256_file,
    validate_operator_id,
    write_json,
)
from process_control import ProcessOutcome, run_process


RUNNER_VERSION = "0.2.0"


class CandidateExecutionError(RuntimeError):
    pass


class CandidateExecutor(Protocol):
    boundary: dict[str, Any]

    def run(self, operation: list[str]) -> ProcessOutcome:
        ...

    def close(self) -> None:
        ...


class LocalCandidateExecutor:
    def __init__(self, command: list[str], cwd: Path, config: dict[str, Any]) -> None:
        self.command = command
        self.cwd = cwd
        self.timeout_seconds = float(config["measurement"]["per_operation_timeout_seconds"])
        self.output_limit_bytes = int(config["measurement"]["stdout_stderr_limit_bytes"])
        self.boundary = {
            "mode": "trusted-local-process",
            "security_boundary": False,
            "timing_grade": config["measurement"]["local_timing_grade"],
        }

    def run(self, operation: list[str]) -> ProcessOutcome:
        outcome = run_process(
            [*self.command, *operation],
            cwd=self.cwd,
            timeout_seconds=self.timeout_seconds,
            output_limit_bytes=self.output_limit_bytes,
        )
        if outcome.timed_out:
            raise CandidateExecutionError(
                f"candidate timed out during {operation[0]} after {self.timeout_seconds:g}s"
            )
        if outcome.output_limit_exceeded:
            raise CandidateExecutionError(
                f"candidate exceeded the combined output limit during {operation[0]}"
            )
        if outcome.returncode != 0:
            raise CandidateExecutionError(
                f"candidate returned {outcome.returncode} during {operation[0]}: "
                f"{outcome.stderr[-4000:].strip()}"
            )
        return outcome

    def close(self) -> None:
        return None


ExecutorFactory = Callable[..., CandidateExecutor]


def build_local_executor(
    *,
    submission_path: Path,
    submission: dict[str, Any],
    artifact: dict[str, Any],
    corpus_root: Path,
    temp_root: Path,
    config: dict[str, Any],
) -> CandidateExecutor:
    del artifact, corpus_root, temp_root
    return LocalCandidateExecutor(
        resolve_candidate_command(submission),
        submission_path.parent,
        config,
    )


def economic_cost(
    config: dict[str, Any],
    *,
    compression_fraction: float,
    encode_ns: int,
    decode_ns: int,
    input_bytes: int,
) -> dict[str, float | str]:
    scenario = config["economic_scenario"]
    retained_input_bytes = float(scenario["retained_input_tb"]) * 1_000_000_000_000
    retained_input_gb = retained_input_bytes / 1_000_000_000
    compressed_gb = retained_input_gb * compression_fraction

    seconds_per_input_byte_encode = (encode_ns / 1_000_000_000) / input_bytes
    seconds_per_input_byte_decode = (decode_ns / 1_000_000_000) / input_bytes
    encode_core_hours = seconds_per_input_byte_encode * retained_input_bytes / 3600
    decode_core_hours = (
        seconds_per_input_byte_decode
        * retained_input_bytes
        * float(scenario["decode_reads_per_year"])
        / 3600
    )

    storage = compressed_gb * float(scenario["retention_months"]) * float(
        scenario["storage_gb_month_gbp"]
    )
    cpu = (encode_core_hours + decode_core_hours) * float(scenario["cpu_core_hour_gbp"])
    egress = compressed_gb * float(scenario["decode_reads_per_year"]) * float(
        scenario["egress_gb_gbp"]
    )
    return {
        "scenario": scenario["name"],
        "measurement_grade": "advisory-unless-pinned-central-runner",
        "storage_gbp": round(storage, 6),
        "cpu_gbp": round(cpu, 6),
        "egress_gbp": round(egress, 6),
        "total_gbp": round(storage + cpu + egress, 6),
    }


def coefficient_of_variation(samples: list[int]) -> float:
    if len(samples) < 2 or statistics.mean(samples) == 0:
        return 0.0
    return statistics.stdev(samples) / statistics.mean(samples)


def require_regular_bounded_file(path: Path, maximum_bytes: int) -> None:
    if path.is_symlink() or not path.is_file():
        raise CandidateExecutionError(f"candidate output is not one regular file: {path.name}")
    stat = path.stat()
    if stat.st_nlink != 1:
        raise CandidateExecutionError(f"candidate output has multiple hard links: {path.name}")
    if stat.st_size > maximum_bytes:
        raise CandidateExecutionError(f"candidate output exceeded its size limit: {path.name}")


def write_batch_job(
    path: Path,
    operation: str,
    pairs: list[tuple[Path, Path]],
) -> None:
    write_json(
        path,
        {
            "schema_version": 1,
            "operation": operation,
            "items": [
                {"input": str(source.resolve()), "output": str(destination.resolve())}
                for source, destination in pairs
            ],
        },
    )


def evaluate_submission(
    submission_path: Path,
    operator_id: str,
    *,
    manifest_path: Path | None = None,
    config_path: Path | None = None,
    executor_factory: ExecutorFactory | None = None,
) -> dict[str, Any]:
    validate_operator_id(operator_id)
    config = load_workbench_config(config_path)
    manifest_path = (manifest_path or WORKBENCH_ROOT / config["corpus"]["public_manifest"]).resolve()
    submission_path = submission_path.resolve()
    submission = load_submission(submission_path, config)
    artifact = candidate_artifact_manifest(submission_path, submission)
    corpus_manifest, corpus_files = load_and_verify_corpus(manifest_path)
    corpus_root = (manifest_path.parent / corpus_manifest["root"]).resolve()

    timeout = float(config["measurement"]["per_operation_timeout_seconds"])
    timing_runs = int(config["measurement"]["timing_runs"])
    warmup_runs = int(config["measurement"]["warmup_runs"])
    determinism_runs = int(config["correctness"]["determinism_runs"])
    repeats = max(timing_runs, determinism_runs)
    max_expansion = float(config["correctness"]["max_output_expansion_ratio"])
    factory = executor_factory or build_local_executor

    failures: list[dict[str, str]] = []
    measured_rounds: list[dict[str, Any]] = []
    candidate_metadata: dict[str, Any] = {}
    boundary: dict[str, Any] = {}

    with tempfile.TemporaryDirectory(prefix="wb001-") as temporary:
        temp_root = Path(temporary).resolve()
        work_root = temp_root / "work"
        work_root.mkdir()
        executor = factory(
            submission_path=submission_path,
            submission=submission,
            artifact=artifact,
            corpus_root=corpus_root,
            temp_root=temp_root,
            config=config,
        )
        boundary = executor.boundary
        try:
            metadata_outcome = executor.run(["metadata"])
            try:
                parsed_metadata = json.loads(metadata_outcome.stdout)
            except json.JSONDecodeError as exc:
                raise ContractError("candidate metadata command did not return one JSON object") from exc
            if not isinstance(parsed_metadata, dict):
                raise ContractError("candidate metadata must be a JSON object")
            candidate_metadata = parsed_metadata
            if parsed_metadata.get("protocol") != config["measurement"]["protocol"]:
                raise ContractError("candidate metadata reported the wrong batch protocol")

            total_rounds = warmup_runs + repeats
            for round_index in range(total_rounds):
                round_root = work_root / f"round-{round_index:03d}"
                compressed_root = round_root / "compressed"
                restored_root = round_root / "restored"
                compressed_root.mkdir(parents=True)
                restored_root.mkdir(parents=True)
                compressed_paths = [compressed_root / f"{index:05d}.bin" for index in range(len(corpus_files))]
                restored_paths = [restored_root / f"{index:05d}.out" for index in range(len(corpus_files))]

                compress_job = round_root / "compress-job.json"
                write_batch_job(
                    compress_job,
                    "compress-batch",
                    [
                        (entry["absolute_path"], compressed_paths[index])
                        for index, entry in enumerate(corpus_files)
                    ],
                )
                encode_outcome = executor.run(["compress-batch", str(compress_job)])

                sizes: list[int] = []
                compressed_hashes: list[str] = []
                for index, entry in enumerate(corpus_files):
                    maximum = max(int(entry["bytes"] * max_expansion), int(entry["bytes"]) + 1024)
                    require_regular_bounded_file(compressed_paths[index], maximum)
                    sizes.append(compressed_paths[index].stat().st_size)
                    compressed_hashes.append(sha256_file(compressed_paths[index]))

                decompress_job = round_root / "decompress-job.json"
                write_batch_job(
                    decompress_job,
                    "decompress-batch",
                    [
                        (compressed_paths[index], restored_paths[index])
                        for index in range(len(corpus_files))
                    ],
                )
                decode_outcome = executor.run(["decompress-batch", str(decompress_job)])
                for index, entry in enumerate(corpus_files):
                    require_regular_bounded_file(restored_paths[index], int(entry["bytes"]))
                    if sha256_file(restored_paths[index]) != entry["sha256"]:
                        raise CandidateExecutionError(
                            f"round trip changed input bytes for {entry['path']}"
                        )

                if round_index >= warmup_runs:
                    measured_rounds.append(
                        {
                            "compressed_sizes": sizes,
                            "compressed_hashes": compressed_hashes,
                            "encode_wall_ns": encode_outcome.elapsed_ns,
                            "decode_wall_ns": decode_outcome.elapsed_ns,
                            "encode_peak_rss_bytes": encode_outcome.peak_rss_bytes,
                            "decode_peak_rss_bytes": decode_outcome.peak_rss_bytes,
                        }
                    )
        except (CandidateExecutionError, ContractError, OSError, ValueError) as exc:
            failures.append({"path": "*batch*", "error": str(exc)})
        finally:
            executor.close()

    final_manifest, _ = load_and_verify_corpus(manifest_path)
    if final_manifest["corpus_sha256"] != corpus_manifest["corpus_sha256"]:
        raise ContractError("corpus commitment changed during evaluation")

    file_results: list[dict[str, Any]] = []
    if not failures and len(measured_rounds) == repeats:
        for index, entry in enumerate(corpus_files):
            hashes = [round_result["compressed_hashes"][index] for round_result in measured_rounds]
            sizes = [round_result["compressed_sizes"][index] for round_result in measured_rounds]
            deterministic = len(set(hashes[:determinism_runs])) == 1 and len(
                set(sizes[:determinism_runs])
            ) == 1
            if not deterministic:
                failures.append({"path": entry["path"], "error": "compressed output was not deterministic"})
                continue
            file_results.append(
                {
                    "path": entry["path"],
                    "class": entry["class"],
                    "original_bytes": entry["bytes"],
                    "original_sha256": entry["sha256"],
                    "compressed_bytes": sizes[0],
                    "compressed_sha256": hashes[0],
                    "compression_fraction": sizes[0] / entry["bytes"],
                    "space_saving_fraction": 1 - (sizes[0] / entry["bytes"]),
                    "deterministic": True,
                    "round_trip_pass": True,
                }
            )

    hard_gate_pass = not failures and len(file_results) == len(corpus_files)
    aggregate: dict[str, Any] | None = None
    if hard_gate_pass:
        total_input = sum(row["original_bytes"] for row in file_results)
        total_compressed = sum(row["compressed_bytes"] for row in file_results)
        encode_samples = [row["encode_wall_ns"] for row in measured_rounds[:timing_runs]]
        decode_samples = [row["decode_wall_ns"] for row in measured_rounds[:timing_runs]]
        encode_ns = int(statistics.median(encode_samples))
        decode_ns = int(statistics.median(decode_samples))
        peak_rss = max(
            max(row["encode_peak_rss_bytes"], row["decode_peak_rss_bytes"])
            for row in measured_rounds[:timing_runs]
        )
        compression_fraction = total_compressed / total_input
        aggregate = {
            "files": len(file_results),
            "total_input_bytes": total_input,
            "total_compressed_bytes": total_compressed,
            "compression_fraction": compression_fraction,
            "space_saving_fraction": 1 - compression_fraction,
            "encode_wall_ns": encode_ns,
            "decode_wall_ns": decode_ns,
            "encode_samples_ns": encode_samples,
            "decode_samples_ns": decode_samples,
            "encode_coefficient_of_variation": coefficient_of_variation(encode_samples),
            "decode_coefficient_of_variation": coefficient_of_variation(decode_samples),
            "peak_rss_bytes": peak_rss,
            "encode_throughput_bytes_per_second": total_input / (encode_ns / 1_000_000_000),
            "decode_throughput_bytes_per_second": total_input / (decode_ns / 1_000_000_000),
            "economic_scenario": economic_cost(
                config,
                compression_fraction=compression_fraction,
                encode_ns=encode_ns,
                decode_ns=decode_ns,
                input_bytes=total_input,
            ),
        }

    executable = Path(sys.executable).resolve()
    environment = {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "python_executable_sha256": sha256_file(executable),
        "processor_count": os.cpu_count(),
    }
    runtime_core = {
        "environment": environment,
        "execution_boundary": boundary,
        "candidate_metadata": candidate_metadata,
    }
    runtime_fingerprint = sha256_bytes(canonical_json_bytes(runtime_core))

    unsigned_result: dict[str, Any] = {
        "schema_version": 2,
        "result_type": "wb001_evaluation",
        "runner_version": RUNNER_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workbench": {"id": config["workbench"]["id"], "version": config["workbench"]["version"]},
        "operator_id": operator_id,
        "submission_id": submission["submission_id"],
        "candidate": {
            "name": submission["candidate"]["name"],
            "version": submission["candidate"]["version"],
            "metadata": candidate_metadata,
        },
        "candidate_artifact_sha256": artifact["artifact_sha256"],
        "artifact_manifest": artifact,
        "corpus": {
            "profile": corpus_manifest["profile"],
            "manifest_sha256": sha256_file(manifest_path),
            "corpus_sha256": corpus_manifest["corpus_sha256"],
            "files": len(corpus_files),
        },
        "environment": environment,
        "execution_boundary": boundary,
        "runtime_fingerprint_sha256": runtime_fingerprint,
        "measurement_contract": {
            "protocol": config["measurement"]["protocol"],
            "scope": "whole-corpus process per operation",
            "warmup_runs": warmup_runs,
            "timing_runs": timing_runs,
            "determinism_runs": determinism_runs,
            "timeout_seconds": timeout,
        },
        "hard_gate_pass": hard_gate_pass,
        "failures": failures,
        "files": file_results,
        "aggregate": aggregate,
    }
    return {**unsigned_result, "result_sha256": sha256_bytes(canonical_json_bytes(unsigned_result))}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate one trusted local WB-001 batch submission")
    parser.add_argument("--submission", type=Path, required=True)
    parser.add_argument("--operator-id", required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = evaluate_submission(
            args.submission,
            args.operator_id,
            manifest_path=args.manifest,
            config_path=args.config,
        )
        write_json(args.output, result)
    except (ContractError, CandidateExecutionError) as exc:
        raise SystemExit(f"WB-001 evaluation failed: {exc}") from exc
    print(
        json.dumps(
            {
                "output": str(args.output),
                "hard_gate_pass": result["hard_gate_pass"],
                "result_sha256": result["result_sha256"],
            },
            indent=2,
        )
    )
    return 0 if result["hard_gate_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
