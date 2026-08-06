from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
QUALITY_DIR = ROOT / "factory" / "quality"
STANDARD = QUALITY_DIR / "factory-quality-standard-v1.json"
STANDARD_SCHEMA = QUALITY_DIR / "factory-quality-standard-v1.schema.json"
ASSESSMENT = QUALITY_DIR / "current-assessment.json"
ASSESSMENT_SCHEMA = QUALITY_DIR / "factory-quality-assessment-v1.schema.json"
HANGAR_SUMMARY = ROOT / "factory" / "hangar" / "data" / "factory-quality-summary.json"
READINESS = ROOT / "factory" / "hangar" / "data" / "workbench-readiness.json"


def load_json_strict(path: Path) -> object:
    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        value: dict[str, object] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate JSON object key in {path}: {key!r}")
            value[key] = item
        return value

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate(document: object, schema_path: Path, *, label: str) -> dict[str, Any]:
    schema = load_json_strict(schema_path)
    if not isinstance(schema, dict):
        raise ValueError(f"{label} schema must be an object")
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    errors = sorted(
        validator.iter_errors(document),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        error = errors[0]
        location = "/".join(str(part) for part in error.absolute_path) or "$"
        raise ValueError(f"{label} schema violation at {location}: {error.message}")
    if not isinstance(document, dict):
        raise ValueError(f"{label} must be an object")
    return document


def _safe_file(root: Path, relative: object) -> Path:
    if not isinstance(relative, str):
        raise ValueError("quality evidence path must be a string")
    pure = PurePosixPath(relative)
    if (
        pure.is_absolute()
        or not pure.parts
        or any(part in {"", ".", ".."} for part in pure.parts)
        or pure.as_posix() != relative
    ):
        raise ValueError(f"unsafe or noncanonical quality evidence path: {relative!r}")
    resolved_root = root.resolve()
    path = (root / Path(*pure.parts)).resolve()
    if path == resolved_root or resolved_root not in path.parents:
        raise ValueError(f"quality evidence escapes the repository: {relative!r}")
    if not path.is_file() or stat.S_ISLNK(path.lstat().st_mode):
        raise ValueError(f"quality evidence is missing or link-like: {relative!r}")
    return path


def _flatten_controls(standard: dict[str, Any]) -> list[dict[str, Any]]:
    domains = standard["domains"]
    domain_ids: set[str] = set()
    control_ids: set[str] = set()
    controls: list[dict[str, Any]] = []
    for domain in domains:
        domain_id = domain["domain_id"]
        if domain_id in domain_ids:
            raise ValueError(f"duplicate quality domain: {domain_id}")
        domain_ids.add(domain_id)
        for control in domain["controls"]:
            control_id = control["control_id"]
            if control_id in control_ids:
                raise ValueError(f"duplicate quality control: {control_id}")
            if not control_id.startswith(f"{domain_id}-"):
                raise ValueError(f"quality control is filed under the wrong domain: {control_id}")
            control_ids.add(control_id)
            controls.append(control)
    if len(controls) != 28:
        raise ValueError(f"quality standard must contain exactly 28 controls, got {len(controls)}")
    return controls


def _readiness_facts(root: Path) -> tuple[int, int]:
    readiness = load_json_strict(root / READINESS.relative_to(ROOT))
    if not isinstance(readiness, dict) or not isinstance(readiness.get("stations"), list):
        raise ValueError("workbench readiness is not a station array")
    stations = readiness["stations"]
    return len(stations), sum(
        isinstance(row, dict) and row.get("readiness_stage") == "LIVE_READY"
        for row in stations
    )


def verify(
    root: Path = ROOT,
    *,
    standard_path: Path | None = None,
    assessment_path: Path | None = None,
    require_hangar_summary: bool = True,
) -> dict[str, Any]:
    standard_file = standard_path or root / STANDARD.relative_to(ROOT)
    assessment_file = assessment_path or root / ASSESSMENT.relative_to(ROOT)
    standard = validate(
        load_json_strict(standard_file),
        root / STANDARD_SCHEMA.relative_to(ROOT),
        label="quality standard",
    )
    assessment = validate(
        load_json_strict(assessment_file),
        root / ASSESSMENT_SCHEMA.relative_to(ROOT),
        label="quality assessment",
    )
    controls = _flatten_controls(standard)
    standard_hash = sha256_file(standard_file)
    if assessment["standard_sha256"] != standard_hash:
        raise ValueError("quality assessment standard SHA-256 does not match exact standard bytes")

    expected_ids = [control["control_id"] for control in controls]
    results = assessment["results"]
    actual_ids = [result["control_id"] for result in results]
    if actual_ids != expected_ids:
        raise ValueError("quality assessment controls must exactly match standard order")

    levels = {name: index for index, name in enumerate(standard["evidence_levels"])}
    for control, result in zip(controls, results, strict=True):
        control_id = control["control_id"]
        for field in ("critical", "minimum_evidence_level"):
            if result[field] != control[field]:
                raise ValueError(f"{control_id} assessment {field} differs from the standard")

        outcome = result["outcome"]
        evidence_level = result["evidence_level"]
        evidence = result["evidence"]
        limitation = result["limitation"]
        if outcome == "MEETS":
            if levels[evidence_level] < levels[control["minimum_evidence_level"]]:
                raise ValueError(f"{control_id} claims MEETS below its minimum evidence level")
            if not evidence or limitation is not None:
                raise ValueError(f"{control_id} MEETS must have evidence and no limitation")
        elif outcome == "PARTIAL":
            if evidence_level == "NONE" or not evidence or not isinstance(limitation, str):
                raise ValueError(f"{control_id} PARTIAL must have evidence and a limitation")
        elif not isinstance(limitation, str):
            raise ValueError(f"{control_id} BLOCKED must state its limitation")

        evidence_paths: set[str] = set()
        for item in evidence:
            relative = item["path"]
            if relative in evidence_paths:
                raise ValueError(f"{control_id} repeats an evidence path: {relative}")
            evidence_paths.add(relative)
            path = _safe_file(root, relative)
            if sha256_file(path) != item["sha256"]:
                raise ValueError(f"{control_id} evidence SHA-256 differs: {relative}")

    counts = Counter(result["outcome"] for result in results)
    expected_summary = {
        "controls": len(results),
        "meets": counts["MEETS"],
        "partial": counts["PARTIAL"],
        "blocked": counts["BLOCKED"],
    }
    if assessment["summary"] != expected_summary:
        raise ValueError("quality assessment summary is not derived from its control outcomes")

    domain_summaries: list[dict[str, Any]] = []
    result_index = 0
    for domain in standard["domains"]:
        domain_results = results[result_index : result_index + len(domain["controls"])]
        result_index += len(domain_results)
        domain_counts = Counter(result["outcome"] for result in domain_results)
        domain_summaries.append(
            {
                "domain_id": domain["domain_id"],
                "title": domain["title"],
                "meets": domain_counts["MEETS"],
                "partial": domain_counts["PARTIAL"],
                "blocked": domain_counts["BLOCKED"],
            }
        )

    station_count, live_count = _readiness_facts(root)
    facts = assessment["operating_facts"]
    if facts["catalogue_stations"] != station_count or facts["live_research_stations"] != live_count:
        raise ValueError("quality operating facts differ from public station readiness")

    profile = assessment["profile"]
    certifications = assessment["certifications"]
    incomplete = counts["PARTIAL"] > 0 or counts["BLOCKED"] > 0
    if incomplete and profile != "FOUNDATION_ONLY":
        raise ValueError("an incomplete quality profile cannot claim certification")
    if profile == "FOUNDATION_ONLY" and any(certifications.values()):
        raise ValueError("FOUNDATION_ONLY must keep every certification false")
    if certifications["scientifically_demonstrated"] and (
        not certifications["operationally_conformant"]
        or live_count < 1
        or facts["independent_human_validators_onboarded"] < 2
        or facts["observed_live_two_person_reproductions"] < 1
    ):
        raise ValueError("scientific certification lacks live two-human operating evidence")
    if certifications["independently_audited"] and (
        not certifications["scientifically_demonstrated"]
        or facts["independent_quality_audits"] < 1
        or results[-1]["control_id"] != "GOVERNANCE-04"
        or results[-1]["outcome"] != "MEETS"
        or results[-1]["evidence_level"] != "INDEPENDENTLY_AUDITED"
    ):
        raise ValueError("independent audit certification lacks an audited complete profile")

    result = {
        "schema_version": 1,
        "diagnostic_type": "RESEARCH_FACTORY_QUALITY_PROFILE",
        "valid": True,
        "standard_version": standard["standard_version"],
        "standard_sha256": standard_hash,
        "assessment_id": assessment["assessment_id"],
        "baseline_revision": assessment["subject"]["baseline_revision"],
        "profile": profile,
        "certifications": certifications,
        "summary": expected_summary,
        "domains": domain_summaries,
        "operating_facts": facts,
        "scope_boundary": assessment["scope_boundary"],
    }
    if require_hangar_summary:
        summary_file = root / HANGAR_SUMMARY.relative_to(ROOT)
        if load_json_strict(summary_file) != result:
            raise ValueError("Hangar quality summary differs from the verified assessment")
    return result


def main() -> int:
    value = verify()
    summary = value["summary"]
    print(
        "Factory quality profile verified: "
        f"{summary['controls']} controls, {summary['meets']} meet, "
        f"{summary['partial']} partial, {summary['blocked']} blocked; "
        f"profile {value['profile']}; operational/scientific/audit certification false."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
