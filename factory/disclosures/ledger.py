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
from corrections.ledger import load_json_strict


GENESIS = "0" * 64
MAX_RECORD_BYTES = 1024 * 1024
ACTIONS = {"DECLARE", "AMEND", "END"}
STATUSES = {"UNDECLARED", "ACTIVE", "ENDED"}
SUPPORT_KINDS = {
    "FINANCIAL_SUPPORT",
    "COMPUTE_CREDIT",
    "TOOL_OR_PROVIDER_SUBSIDY",
    "DATA_OR_MATERIAL_DONATION",
    "EMPLOYMENT_OR_INSTITUTIONAL_INTEREST",
    "GOVERNANCE_INTEREST",
    "OTHER_MATERIAL_INTEREST",
}
BOUNDARY = {
    "scope": "PUBLIC_MATERIAL_SUPPORT_DISCLOSURE_ONLY",
    "append_only": True,
    "scientific_gates_changed": False,
    "measurement_changed": False,
    "promotion_changed": False,
    "validator_independence_proven": False,
    "legal_clearance_proven": False,
}
DRAFT_KEYS = {"event_id", "disclosure_id", "action", "scope", "declarant", "disclosure", "public_summary"}


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


class SupportDisclosureLedger:
    """Append-only public material-support declarations and later changes."""

    def __init__(self, path: Path, schema_path: Path | None = None) -> None:
        self.path = path.resolve()
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self.schema_path = schema_path.resolve() if schema_path else Path(__file__).resolve().with_name("support-disclosure-v1.schema.json")
        schema = load_json_strict(self.schema_path)
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as exc:  # pragma: no cover
            raise ContractError(f"support-disclosure schema is invalid: {exc}") from exc
        self.validator = Draft202012Validator(schema)

    def _validate_schema(self, record: dict[str, Any]) -> None:
        errors = sorted(self.validator.iter_errors(record), key=lambda error: tuple(str(part) for part in error.absolute_path))
        if errors:
            error = errors[0]
            location = "/".join(str(part) for part in error.absolute_path) or "$"
            raise ContractError(f"support-disclosure schema violation at {location}: {error.message}")

    def _validate_record(self, record: dict[str, Any]) -> None:
        self._validate_schema(record)
        for field in ("event_id", "disclosure_id"):
            validate_id(record[field], field=field)
        parse_utc(record["recorded_at"], field="recorded_at")
        validate_sha256(record["previous_record_sha256"], field="previous_record_sha256")
        validate_sha256(record["previous_disclosure_event_sha256"], field="previous_disclosure_event_sha256")
        validate_sha256(record["record_sha256"], field="record_sha256")
        validate_id(record["scope"]["scope_id"], field="scope.scope_id")
        validate_id(record["declarant"]["operator_id"], field="declarant.operator_id")
        if record["action"] not in ACTIONS or record["status_before"] not in STATUSES or record["status_after"] not in STATUSES:
            raise ContractError("support-disclosure action or status is unknown")
        if record["boundary"] != BOUNDARY:
            raise ContractError("support disclosure attempts to alter its non-influence boundary")
        unsigned = {key: value for key, value in record.items() if key != "record_sha256"}
        expected = sha256_bytes(canonical_json_bytes(unsigned))
        if record["record_sha256"] != expected:
            raise LedgerIntegrityError(f"support-disclosure hash mismatch for {record['event_id']}: expected {expected}")

    def _read_unlocked(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise LedgerIntegrityError(f"could not read support-disclosure ledger {self.path}: {exc}") from exc
        records: list[dict[str, Any]] = []
        previous_hash = GENESIS
        previous_time = None
        event_ids: set[str] = set()
        per_disclosure: dict[str, dict[str, Any]] = {}
        for sequence, line in enumerate(lines, start=1):
            if not line.strip():
                raise LedgerIntegrityError(f"blank support-disclosure line at {sequence}")
            try:
                record = json.loads(line, object_pairs_hook=_strict_object, parse_constant=_reject_constant)
            except (json.JSONDecodeError, ValueError) as exc:
                raise LedgerIntegrityError(f"invalid strict JSON on support-disclosure line {sequence}: {exc}") from exc
            if not isinstance(record, dict):
                raise LedgerIntegrityError(f"support-disclosure line {sequence} is not an object")
            try:
                self._validate_record(record)
            except (ContractError, LedgerIntegrityError) as exc:
                raise LedgerIntegrityError(f"invalid support-disclosure record on line {sequence}: {exc}") from exc
            if record["sequence"] != sequence or record["previous_record_sha256"] != previous_hash:
                raise LedgerIntegrityError(f"broken support-disclosure sequence or hash chain on line {sequence}")
            if record["event_id"] in event_ids:
                raise LedgerIntegrityError(f"duplicate support-disclosure event ID on line {sequence}")
            recorded_time = parse_utc(record["recorded_at"], field="recorded_at")
            if previous_time is not None and recorded_time < previous_time:
                raise LedgerIntegrityError("support-disclosure record time moved backwards")
            prior = per_disclosure.get(record["disclosure_id"])
            expected_before = "UNDECLARED" if prior is None else prior["status_after"]
            expected_previous = GENESIS if prior is None else prior["record_sha256"]
            if record["status_before"] != expected_before or record["previous_disclosure_event_sha256"] != expected_previous:
                raise LedgerIntegrityError(f"disclosure state chain is broken for {record['disclosure_id']}")
            if prior is None and record["action"] != "DECLARE":
                raise LedgerIntegrityError("a support disclosure must start with DECLARE")
            if prior is not None and prior["status_after"] == "ENDED":
                raise LedgerIntegrityError("an ended support disclosure cannot be silently restored")
            if prior is not None and record["action"] == "DECLARE":
                raise LedgerIntegrityError("a declared support disclosure cannot be declared twice")
            event_ids.add(record["event_id"])
            per_disclosure[record["disclosure_id"]] = record
            previous_hash = record["record_sha256"]
            previous_time = recorded_time
            records.append(record)
        return records

    def read(self) -> list[dict[str, Any]]:
        return self._read_unlocked()

    def append(self, draft: dict[str, Any], *, recorded_at: str | None = None) -> dict[str, Any]:
        if not isinstance(draft, dict) or not set(draft).issubset(DRAFT_KEYS):
            unsupported = sorted(set(draft) - DRAFT_KEYS) if isinstance(draft, dict) else []
            raise ContractError(f"support-disclosure draft has unsupported fields: {', '.join(unsupported)}")
        required = DRAFT_KEYS - {"event_id"}
        missing = sorted(required - set(draft))
        if missing:
            raise ContractError(f"support-disclosure draft is missing fields: {', '.join(missing)}")
        event_id = draft.get("event_id") or f"support-event:{uuid.uuid4().hex}"
        validate_id(event_id, field="event_id")
        recorded_at = recorded_at or utc_text(utc_now())
        parse_utc(recorded_at, field="recorded_at")
        with FileMutex(self.lock_path):
            records = self._read_unlocked()
            if any(record["event_id"] == event_id for record in records):
                raise ContractError(f"support-disclosure event_id already exists: {event_id}")
            previous = next((record for record in reversed(records) if record["disclosure_id"] == draft["disclosure_id"]), None)
            if records and parse_utc(recorded_at) < parse_utc(records[-1]["recorded_at"]):
                raise ContractError("support-disclosure recorded_at cannot move backwards")
            if previous is not None and previous["status_after"] == "ENDED":
                raise ContractError("an ended support disclosure cannot be restored in v1")
            action = draft["action"]
            if action not in ACTIONS:
                raise ContractError(f"unknown support-disclosure action: {action}")
            if previous is None and action != "DECLARE":
                raise ContractError("a new support disclosure must use DECLARE")
            if previous is not None and action == "DECLARE":
                raise ContractError("an existing support disclosure cannot use DECLARE")
            if (
                previous is not None
                and action == "AMEND"
                and canonical_json_bytes(draft["disclosure"])
                == canonical_json_bytes(previous["disclosure"])
            ):
                raise ContractError("a support-disclosure AMEND must change the public disclosure")
            status_before = "UNDECLARED" if previous is None else "ACTIVE"
            status_after = "ENDED" if action == "END" else "ACTIVE"
            unsigned = {
                "schema_version": 1,
                "sequence": len(records) + 1,
                "event_id": event_id,
                "recorded_at": recorded_at,
                "disclosure_id": draft["disclosure_id"],
                "action": action,
                "status_before": status_before,
                "status_after": status_after,
                "scope": draft["scope"],
                "declarant": draft["declarant"],
                "disclosure": draft["disclosure"],
                "public_summary": draft["public_summary"],
                "boundary": BOUNDARY,
                "previous_record_sha256": records[-1]["record_sha256"] if records else GENESIS,
                "previous_disclosure_event_sha256": previous["record_sha256"] if previous else GENESIS,
            }
            record = {**unsigned, "record_sha256": sha256_bytes(canonical_json_bytes(unsigned))}
            self._validate_record(record)
            line = canonical_json_bytes(record) + b"\n"
            if len(line) > MAX_RECORD_BYTES:
                raise ContractError("support-disclosure record exceeds one megabyte")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                if os.write(descriptor, line) != len(line):
                    raise LedgerIntegrityError("short support-disclosure ledger write; manual recovery required")
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            return record

    def verify(self) -> dict[str, Any]:
        records = self.read()
        current = {record["disclosure_id"]: record["status_after"] for record in records}
        return {
            "valid": True,
            "records": len(records),
            "disclosures": len(current),
            "active_disclosures": sum(status == "ACTIVE" for status in current.values()),
            "head_record_sha256": records[-1]["record_sha256"] if records else GENESIS,
            "ledger_sha256": sha256_file(self.path) if self.path.is_file() else sha256_bytes(b""),
            "actions": dict(sorted(Counter(record["action"] for record in records).items())),
            "scientific_standing": "NONE",
            "eligible_for_promotion": False,
        }

    def history(self, *, scope_id: str | None = None, support_kind: str | None = None, limit: int = 200) -> dict[str, Any]:
        if scope_id is not None:
            validate_id(scope_id, field="scope_id")
        if support_kind is not None and support_kind not in SUPPORT_KINDS:
            raise ContractError(f"unknown material-support kind: {support_kind}")
        if limit < 1 or limit > 500:
            raise ContractError("support-disclosure history limit must be between 1 and 500")
        records = self.read()
        filtered = [record for record in records if (scope_id is None or record["scope"]["scope_id"] == scope_id) and (support_kind is None or record["disclosure"]["support_kind"] == support_kind)]
        filtered.sort(key=lambda record: record["sequence"], reverse=True)
        return {"schema_version": 1, "ledger": self.verify(), "filters": {"scope_id": scope_id, "support_kind": support_kind, "limit": limit}, "returned": min(len(filtered), limit), "total_matches": len(filtered), "records": filtered[:limit], "boundary": BOUNDARY}

    def export_public_index(self, output: Path) -> dict[str, Any]:
        output = output.resolve()
        if output.exists():
            raise ContractError(f"support-disclosure index destination already exists: {output}")
        value = self.history(limit=500)
        value["ledger"].pop("ledger", None)
        write_json(output, value)
        return value
