from __future__ import annotations

import json
import os
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from control_plane.common import (
    ContractError,
    LedgerIntegrityError,
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
from control_plane.ledger import FileMutex
from corrections.ledger import _safe_public_locator, load_json_strict


GENESIS_PREVIOUS_HASH = "0" * 64
MAX_RECORD_BYTES = 1024 * 1024
CASE_KINDS = {"SCIENTIFIC_DISPUTE", "RIGHTS_AND_CREDIT", "SAFETY", "GOVERNANCE"}
OUTCOMES = {"UPHOLD_PROCEDURALLY", "DENY_PROCEDURALLY", "RETURN_FOR_DIAGNOSIS"}
OUTCOME_FOLLOW_UP = {
    "UPHOLD_PROCEDURALLY": "SEPARATE_CORRECTION_OR_REMEDY_RECORD_REQUIRED",
    "DENY_PROCEDURALLY": "NO_AUTOMATIC_STANDING_CHANGE",
    "RETURN_FOR_DIAGNOSIS": "FRESH_DIAGNOSTIC_RUN_REQUIRED",
}
BOUNDARY = {
    "scope": "PUBLIC_PROCEDURAL_APPEAL_ONLY",
    "append_only": True,
    "material_conflict_exclusion_enforced": True,
    "automatic_scientific_standing_change": False,
    "scientific_evidence": False,
    "counts_as_independent_reproduction": False,
    "eligible_for_promotion": False,
}
DRAFT_KEYS = {
    "appeal_id",
    "case",
    "panel",
    "findings",
    "outcome",
    "follow_up",
    "decision_public_summary",
}


def _appeal_target_key(record: dict[str, Any]) -> tuple[str, str, str]:
    target = record["case"]["target"]
    return target["artifact_class"], target["artifact_id"], target["artifact_sha256"]


def _validate_identity(identity: dict[str, Any], *, field: str) -> None:
    validate_id(identity["operator_id"], field=f"{field}.operator_id")


class AppealLedger:
    """Append and verify conflict-excluded procedural appeal decisions.

    The ledger evaluates only the declared record shape and conflict exclusions.
    An identity record is never proof that an identity represents a distinct human,
    that a reviewer is impartial, or that a reviewer has legal authority.
    """

    def __init__(self, path: Path, schema_path: Path | None = None) -> None:
        self.path = path.resolve()
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self.schema_path = (
            schema_path.resolve()
            if schema_path is not None
            else Path(__file__).resolve().with_name("appeal-record-v1.schema.json")
        )
        schema = load_json_strict(self.schema_path)
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as exc:  # pragma: no cover - jsonschema owns the exception types
            raise ContractError(f"appeal schema is invalid: {exc}") from exc
        self.validator = Draft202012Validator(schema)

    def _validate_schema(self, record: dict[str, Any]) -> None:
        errors = sorted(
            self.validator.iter_errors(record),
            key=lambda error: tuple(str(part) for part in error.absolute_path),
        )
        if errors:
            error = errors[0]
            location = "/".join(str(part) for part in error.absolute_path) or "$"
            raise ContractError(f"appeal schema violation at {location}: {error.message}")

    def _validate_record_contract(self, record: dict[str, Any]) -> None:
        self._validate_schema(record)
        validate_id(record["appeal_id"], field="appeal_id")
        parse_utc(record["recorded_at"], field="recorded_at")
        validate_sha256(record["previous_record_sha256"], field="previous_record_sha256")
        validate_sha256(record["record_sha256"], field="record_sha256")

        case = record["case"]
        validate_id(case["case_id"], field="case.case_id")
        if case["case_kind"] not in CASE_KINDS:
            raise ContractError(f"unknown appeal case kind: {case['case_kind']}")
        _validate_identity(case["requester"], field="case.requester")
        _safe_public_locator(case["target"], field="case.target.locator")
        validate_id(case["target"]["artifact_id"], field="case.target.artifact_id")
        validate_sha256(case["target"]["artifact_sha256"], field="case.target.artifact_sha256")
        for index, reference in enumerate(case["evidence_references"]):
            _safe_public_locator(reference, field=f"case.evidence_references[{index}].locator")
            validate_id(reference["artifact_id"], field=f"case.evidence_references[{index}].artifact_id")
            validate_sha256(
                reference["artifact_sha256"],
                field=f"case.evidence_references[{index}].artifact_sha256",
            )

        involved = set(case["materially_involved_identity_ids"])
        if len(involved) != len(case["materially_involved_identity_ids"]):
            raise ContractError("materially involved identity IDs must be distinct")
        for identity_id in involved:
            validate_id(identity_id, field="case.materially_involved_identity_ids")

        reviewers = record["panel"]["reviewers"]
        reviewer_ids = [row["operator_id"] for row in reviewers]
        reviewer_set = set(reviewer_ids)
        if len(reviewer_set) != len(reviewer_ids):
            raise ContractError("appeal panel reviewers must have distinct identity records")
        requester_id = case["requester"]["operator_id"]
        disallowed = involved | {requester_id}
        overlap = sorted(reviewer_set & disallowed)
        if overlap:
            raise ContractError(
                "materially involved requester, author, validator or reviewer cannot decide "
                f"this appeal: {', '.join(overlap)}"
            )
        for index, reviewer in enumerate(reviewers):
            _validate_identity(reviewer, field=f"panel.reviewers[{index}]")
            for digest in reviewer["conflict_evidence_sha256"]:
                validate_sha256(digest, field=f"panel.reviewers[{index}].conflict_evidence_sha256")

        findings = record["findings"]
        finding_ids = [row["reviewer_id"] for row in findings]
        if len(findings) != len(reviewers) or set(finding_ids) != reviewer_set:
            raise ContractError("appeal requires exactly one finding from every assigned reviewer")
        if len(set(finding_ids)) != len(finding_ids):
            raise ContractError("appeal cannot contain repeated reviewer findings")
        evidence_hashes = [row["evidence_sha256"] for row in findings]
        if len(set(evidence_hashes)) != len(evidence_hashes):
            raise ContractError("appeal reviewers must commit distinct evidence hashes")
        for finding in findings:
            validate_id(finding["reviewer_id"], field="finding.reviewer_id")
            validate_sha256(finding["evidence_sha256"], field="finding.evidence_sha256")

        conclusions = {finding["conclusion"] for finding in findings}
        if conclusions == {"UPHOLD_APPEAL"}:
            expected_outcome = "UPHOLD_PROCEDURALLY"
        elif conclusions == {"DENY_APPEAL"}:
            expected_outcome = "DENY_PROCEDURALLY"
        else:
            expected_outcome = "RETURN_FOR_DIAGNOSIS"
        if record["outcome"] != expected_outcome:
            raise ContractError(
                "appeal outcome must be unanimous or return to diagnosis; majority voting is forbidden"
            )
        if record["follow_up"] != OUTCOME_FOLLOW_UP[expected_outcome]:
            raise ContractError("appeal follow-up does not match the procedural outcome")
        if record["boundary"] != BOUNDARY:
            raise ContractError("appeal boundary differs from the construction-only contract")

        unsigned = {key: value for key, value in record.items() if key != "record_sha256"}
        actual_hash = sha256_bytes(canonical_json_bytes(unsigned))
        if record["record_sha256"] != actual_hash:
            raise LedgerIntegrityError(
                f"appeal record hash mismatch for {record['appeal_id']}: expected {actual_hash}"
            )

    def _read_unlocked(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise LedgerIntegrityError(f"could not read appeal ledger {self.path}: {exc}") from exc

        records: list[dict[str, Any]] = []
        previous_hash = GENESIS_PREVIOUS_HASH
        previous_time = None
        appeal_ids: set[str] = set()
        case_ids: set[str] = set()
        record_hashes: set[str] = set()
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                raise LedgerIntegrityError(f"blank appeal-ledger line at {line_number}")
            try:
                value = json.loads(
                    line,
                    object_pairs_hook=lambda pairs: _strict_object(pairs),
                    parse_constant=_reject_constant,
                )
            except (json.JSONDecodeError, ValueError) as exc:
                raise LedgerIntegrityError(
                    f"invalid strict JSON on appeal-ledger line {line_number}: {exc}"
                ) from exc
            if not isinstance(value, dict):
                raise LedgerIntegrityError(f"appeal-ledger line {line_number} is not an object")
            try:
                self._validate_record_contract(value)
            except (ContractError, LedgerIntegrityError) as exc:
                raise LedgerIntegrityError(
                    f"invalid appeal record on line {line_number}: {exc}"
                ) from exc
            if value["sequence"] != line_number:
                raise LedgerIntegrityError(f"non-contiguous appeal sequence on line {line_number}")
            if value["previous_record_sha256"] != previous_hash:
                raise LedgerIntegrityError(f"broken appeal hash chain on line {line_number}")
            if value["appeal_id"] in appeal_ids or value["record_sha256"] in record_hashes:
                raise LedgerIntegrityError(f"duplicate appeal ID or record hash on line {line_number}")
            case_id = value["case"]["case_id"]
            if case_id in case_ids:
                raise LedgerIntegrityError(f"duplicate appeal case ID on line {line_number}")
            recorded_time = parse_utc(value["recorded_at"], field="recorded_at")
            if previous_time is not None and recorded_time < previous_time:
                raise LedgerIntegrityError("appeal record time moved backwards")
            appeal_ids.add(value["appeal_id"])
            case_ids.add(case_id)
            record_hashes.add(value["record_sha256"])
            previous_hash = value["record_sha256"]
            previous_time = recorded_time
            records.append(value)
        return records

    def read(self) -> list[dict[str, Any]]:
        return self._read_unlocked()

    def append(self, draft: dict[str, Any], *, recorded_at: str | None = None) -> dict[str, Any]:
        if not isinstance(draft, dict) or not set(draft).issubset(DRAFT_KEYS):
            unsupported = sorted(set(draft) - DRAFT_KEYS) if isinstance(draft, dict) else []
            detail = f": {', '.join(unsupported)}" if unsupported else ""
            raise ContractError(f"appeal draft has unsupported fields{detail}")
        required = DRAFT_KEYS - {"appeal_id"}
        missing = sorted(required - set(draft))
        if missing:
            raise ContractError(f"appeal draft is missing fields: {', '.join(missing)}")
        appeal_id = draft.get("appeal_id") or f"appeal:{uuid.uuid4().hex}"
        validate_id(appeal_id, field="appeal_id")
        recorded_at = recorded_at or utc_text(utc_now())
        parse_utc(recorded_at, field="recorded_at")

        with FileMutex(self.lock_path):
            records = self._read_unlocked()
            if any(record["appeal_id"] == appeal_id for record in records):
                raise ContractError(f"appeal_id already exists: {appeal_id}")
            case_id = draft.get("case", {}).get("case_id") if isinstance(draft.get("case"), dict) else None
            if any(record["case"]["case_id"] == case_id for record in records):
                raise ContractError(f"case_id already exists: {case_id}")
            if records and parse_utc(recorded_at) < parse_utc(records[-1]["recorded_at"]):
                raise ContractError("appeal recorded_at cannot move backwards")

            unsigned = {
                "schema_version": 1,
                "sequence": len(records) + 1,
                "appeal_id": appeal_id,
                "recorded_at": recorded_at,
                "case": draft["case"],
                "panel": draft["panel"],
                "findings": draft["findings"],
                "outcome": draft["outcome"],
                "follow_up": draft["follow_up"],
                "decision_public_summary": draft["decision_public_summary"],
                "boundary": BOUNDARY,
                "previous_record_sha256": (
                    records[-1]["record_sha256"] if records else GENESIS_PREVIOUS_HASH
                ),
            }
            record = {
                **unsigned,
                "record_sha256": sha256_bytes(canonical_json_bytes(unsigned)),
            }
            self._validate_record_contract(record)
            line = canonical_json_bytes(record) + b"\n"
            if len(line) > MAX_RECORD_BYTES:
                raise ContractError("appeal record exceeds one megabyte; cite evidence by hash")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                written = os.write(descriptor, line)
                if written != len(line):
                    raise LedgerIntegrityError("short appeal-ledger write; manual recovery required")
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            return record

    def verify(self) -> dict[str, Any]:
        records = self.read()
        return {
            "valid": True,
            "records": len(records),
            "cases": len(records),
            "head_record_sha256": records[-1]["record_sha256"] if records else GENESIS_PREVIOUS_HASH,
            "ledger_sha256": sha256_file(self.path) if self.path.is_file() else sha256_bytes(b""),
            "outcomes": dict(sorted(Counter(row["outcome"] for row in records).items())),
            "ledger": str(self.path),
            "scientific_standing": "NONE",
            "eligible_for_promotion": False,
        }

    def history(
        self,
        *,
        target_sha256: str | None = None,
        case_kind: str | None = None,
        outcome: str | None = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        if target_sha256 is not None:
            validate_sha256(target_sha256, field="target_sha256")
        if case_kind is not None and case_kind not in CASE_KINDS:
            raise ContractError(f"unknown appeal case kind: {case_kind}")
        if outcome is not None and outcome not in OUTCOMES:
            raise ContractError(f"unknown appeal outcome: {outcome}")
        if limit < 1 or limit > 500:
            raise ContractError("appeal history limit must be between 1 and 500")
        records = self.read()
        filtered = [
            record
            for record in records
            if (target_sha256 is None or _appeal_target_key(record)[2] == target_sha256)
            and (case_kind is None or record["case"]["case_kind"] == case_kind)
            and (outcome is None or record["outcome"] == outcome)
        ]
        filtered.sort(key=lambda row: row["sequence"], reverse=True)
        return {
            "schema_version": 1,
            "ledger": self.verify(),
            "filters": {
                "target_sha256": target_sha256,
                "case_kind": case_kind,
                "outcome": outcome,
                "limit": limit,
            },
            "returned": min(len(filtered), limit),
            "total_matches": len(filtered),
            "records": filtered[:limit],
            "boundary": BOUNDARY,
        }

    def export_public_index(self, output: Path) -> dict[str, Any]:
        output = output.resolve()
        if output.exists():
            raise ContractError(f"appeal index destination already exists: {output}")
        index = self.history(limit=500)
        index["ledger"].pop("ledger", None)
        write_json(output, index)
        return index


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key!r}")
        value[key] = item
    return value
