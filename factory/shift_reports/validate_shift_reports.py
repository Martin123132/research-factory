from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Iterable

from jsonschema import Draft202012Validator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = Path(__file__).resolve().with_name("shift-report-v1.schema.json")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json_strict(path: Path) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key in {path}: {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicates,
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not load JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return value


def load_validator(schema_path: Path = SCHEMA_PATH) -> Draft202012Validator:
    schema = load_json_strict(schema_path)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def canonical_report_hash(report: dict[str, Any]) -> str:
    unsigned = {key: value for key, value in report.items() if key != "reportSha256"}
    return sha256_bytes(canonical_json_bytes(unsigned))


def safe_repository_path(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"invalid repository artifact path: {value!r}")
    path = PurePosixPath(value)
    windows = PureWindowsPath(value)
    if (
        path.is_absolute()
        or windows.is_absolute()
        or windows.drive
        or "." in path.parts
        or ".." in path.parts
        or path.as_posix() != value
    ):
        raise ValueError(f"unsafe repository artifact path: {value!r}")
    sensitive = {
        "private",
        "secret",
        "secrets",
        "credential",
        "credentials",
        "key",
        "keys",
        "hidden",
        "hidden-answer",
        "hidden-answers",
        "holdout",
        "holdouts",
    }
    if any(part.casefold() in sensitive or part.casefold().startswith(".env") for part in path.parts):
        raise ValueError(f"repository artifact path is not public provenance: {value!r}")
    return path


def verify_report(
    report: dict[str, Any],
    *,
    validator: Draft202012Validator,
    repository_root: Path = REPOSITORY_ROOT,
) -> None:
    errors = sorted(
        validator.iter_errors(report),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        error = errors[0]
        location = "/".join(str(part) for part in error.absolute_path) or "$"
        raise ValueError(f"shift-report schema violation at {location}: {error.message}")

    expected_hash = canonical_report_hash(report)
    if report["reportSha256"] != expected_hash:
        raise ValueError(
            f"reportSha256 mismatch for {report['reportId']}: "
            f"expected {expected_hash}, got {report['reportSha256']}"
        )

    started_at = datetime.fromisoformat(report["shift"]["startedAt"].replace("Z", "+00:00"))
    ended_at = datetime.fromisoformat(report["shift"]["endedAt"].replace("Z", "+00:00"))
    created_at = datetime.fromisoformat(report["createdAt"].replace("Z", "+00:00"))
    elapsed_seconds = (ended_at - started_at).total_seconds()
    if elapsed_seconds < 0 or elapsed_seconds > 24 * 60 * 60:
        raise ValueError(f"invalid shift interval for {report['reportId']}")
    expected_minutes = math.ceil(elapsed_seconds / 60)
    if report["shift"]["durationMinutes"] != expected_minutes:
        raise ValueError(
            f"durationMinutes mismatch for {report['reportId']}: "
            f"expected {expected_minutes}, got {report['shift']['durationMinutes']}"
        )
    if ended_at > created_at:
        raise ValueError(f"createdAt precedes the shift end for {report['reportId']}")

    for reference in report["artifactReferences"]:
        if reference["kind"] != "REPOSITORY_PATH":
            continue
        relative = safe_repository_path(reference["locator"])
        target = repository_root.joinpath(*relative.parts)
        try:
            target.relative_to(repository_root)
        except ValueError as exc:
            raise ValueError(f"artifact path escapes the repository: {relative}") from exc
        if not target.is_file():
            raise ValueError(f"referenced repository artifact is missing: {relative}")
        actual_hash = sha256_file(target)
        if reference["sha256"] != actual_hash:
            raise ValueError(
                f"artifact SHA-256 mismatch for {relative}: "
                f"expected {reference['sha256']}, got {actual_hash}"
            )


def verify_reports(
    reports: Iterable[dict[str, Any]],
    *,
    validator: Draft202012Validator | None = None,
    repository_root: Path = REPOSITORY_ROOT,
) -> int:
    schema_validator = validator or load_validator()
    documents = list(reports)
    if not documents:
        raise ValueError("at least one shift report is required")
    report_ids: set[str] = set()
    report_hashes: set[str] = set()
    chains: dict[str, list[dict[str, Any]]] = {}

    for report in documents:
        verify_report(report, validator=schema_validator, repository_root=repository_root)
        report_id = report["reportId"]
        report_hash = report["reportSha256"]
        if report_id in report_ids:
            raise ValueError(f"duplicate reportId: {report_id}")
        if report_hash in report_hashes:
            raise ValueError(f"duplicate reportSha256: {report_hash}")
        report_ids.add(report_id)
        report_hashes.add(report_hash)
        chains.setdefault(report["workOrderId"], []).append(report)

    for work_order_id, chain in chains.items():
        chain.sort(key=lambda report: report["reportSequence"])
        previous_hash: str | None = None
        previous_revision = -1
        previous_created_at: datetime | None = None
        expected_workbench = chain[0]["workbenchId"]
        expected_mode = chain[0]["mode"]
        for expected_sequence, report in enumerate(chain, start=1):
            if report["reportSequence"] != expected_sequence:
                raise ValueError(
                    f"non-contiguous report sequence for {work_order_id}: "
                    f"expected {expected_sequence}, got {report['reportSequence']}"
                )
            if report["previousReportSha256"] != previous_hash:
                raise ValueError(
                    f"previous-report hash mismatch for {report['reportId']}: "
                    f"expected {previous_hash}, got {report['previousReportSha256']}"
                )
            if report["workbenchId"] != expected_workbench or report["mode"] != expected_mode:
                raise ValueError(f"work-order identity drift in report chain for {work_order_id}")
            revision = report["workOrderSnapshot"]["revision"]
            if revision < previous_revision:
                raise ValueError(f"work-order revision moved backwards for {work_order_id}")
            created_at = datetime.fromisoformat(report["createdAt"].replace("Z", "+00:00"))
            if previous_created_at is not None and created_at < previous_created_at:
                raise ValueError(f"report creation time moved backwards for {work_order_id}")
            previous_hash = report["reportSha256"]
            previous_revision = revision
            previous_created_at = created_at

    return len(documents)


def collect_paths(values: list[str]) -> list[Path]:
    paths: list[Path] = []
    for raw in values:
        candidate = Path(raw)
        if candidate.is_dir():
            paths.extend(sorted(candidate.glob("*.json")))
        else:
            paths.append(candidate)
    if not paths:
        raise ValueError("no shift-report JSON files were selected")
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate append-only Factory shift reports")
    parser.add_argument("paths", nargs="+", help="Report JSON files or directories")
    args = parser.parse_args()
    selected = collect_paths(args.paths)
    reports = [load_json_strict(path) for path in selected]
    count = verify_reports(reports)
    print(f"Verified {count} append-only shift reports across a valid hash chain.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
