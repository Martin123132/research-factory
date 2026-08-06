from __future__ import annotations

import json
import os
import uuid
from collections import Counter
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from urllib.parse import urlparse

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


GENESIS_PREVIOUS_HASH = "0" * 64
MAX_RECORD_BYTES = 1024 * 1024
TERMINAL_STANDINGS = {"SUPERSEDED", "INVALIDATED", "RETRACTED"}
ALL_STANDINGS = {"CURRENT_WITH_CORRECTION", *TERMINAL_STANDINGS}
ARTIFACT_CLASSES = {
    "CONTROL_PLANE_EVENT",
    "SHIFT_REPORT",
    "PORTABLE_EVIDENCE_PACKAGE",
    "STATION_CONTRACT",
    "CONTRIBUTION_LEDGER",
    "RIGHTS_AND_IP_RECORD",
    "QUALITY_ASSESSMENT",
    "CORRECTION_RECORD",
    "PUBLIC_ARTIFACT",
}
ACTION_STANDING = {
    "CORRIGENDUM": "CURRENT_WITH_CORRECTION",
    "RIGHTS_CORRECTION": "CURRENT_WITH_CORRECTION",
    "SUPERSESSION": "SUPERSEDED",
    "INVALIDATION": "INVALIDATED",
    "RETRACTION": "RETRACTED",
}
BOUNDARY = {
    "scope": "PUBLIC_ARTIFACT_STANDING_ONLY",
    "append_only": True,
    "original_bytes_preserved": True,
    "scientific_evidence": False,
    "counts_as_independent_reproduction": False,
    "eligible_for_promotion": False,
    "restores_terminal_standing": False,
}
DRAFT_KEYS = {
    "correction_id",
    "actor",
    "authority",
    "target",
    "action",
    "replacement",
    "reason",
    "public_summary",
}


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key!r}")
        value[key] = item
    return value


def load_json_strict(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ContractError(f"could not load strict JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"expected a JSON object in {path}")
    return value


def _safe_public_locator(reference: dict[str, Any], *, field: str) -> None:
    locator = reference["locator"]
    if reference["locator_kind"] == "PUBLIC_URL":
        parsed = urlparse(locator)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise ContractError(f"{field} must be a credential-free HTTPS URL")
        return

    path = PurePosixPath(locator)
    windows = PureWindowsPath(locator)
    if (
        not locator
        or "\\" in locator
        or path.is_absolute()
        or windows.is_absolute()
        or windows.drive
        or "." in path.parts
        or ".." in path.parts
        or path.as_posix() != locator
    ):
        raise ContractError(f"{field} must be a safe repository-relative path")
    sensitive = {
        "private",
        "secret",
        "secrets",
        "credential",
        "credentials",
        "hidden",
        "holdout",
        "holdouts",
        "key",
        "keys",
    }
    if any(part.casefold() in sensitive or part.casefold().startswith(".env") for part in path.parts):
        raise ContractError(f"{field} cannot identify protected or hidden material")


def _target_key(record: dict[str, Any]) -> tuple[str, str, str]:
    target = record["target"]
    return target["artifact_class"], target["artifact_id"], target["artifact_sha256"]


class CorrectionLedger:
    """Append and verify universal public-artifact standing corrections."""

    def __init__(self, path: Path, schema_path: Path | None = None) -> None:
        self.path = path.resolve()
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self.schema_path = (
            schema_path.resolve()
            if schema_path is not None
            else Path(__file__).resolve().with_name("correction-record-v1.schema.json")
        )
        schema = load_json_strict(self.schema_path)
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as exc:  # pragma: no cover - jsonschema owns the exception types
            raise ContractError(f"correction schema is invalid: {exc}") from exc
        self.validator = Draft202012Validator(schema)

    def _validate_schema(self, record: dict[str, Any]) -> None:
        errors = sorted(
            self.validator.iter_errors(record),
            key=lambda error: tuple(str(part) for part in error.absolute_path),
        )
        if errors:
            error = errors[0]
            location = "/".join(str(part) for part in error.absolute_path) or "$"
            raise ContractError(f"correction schema violation at {location}: {error.message}")

    def _validate_record_contract(self, record: dict[str, Any]) -> None:
        self._validate_schema(record)
        validate_id(record["correction_id"], field="correction_id")
        parse_utc(record["recorded_at"], field="recorded_at")
        validate_sha256(record["previous_record_sha256"], field="previous_record_sha256")
        validate_sha256(record["record_sha256"], field="record_sha256")

        references = [record["target"], *record["reason"]["evidence_references"]]
        if record["replacement"] is not None:
            references.append(record["replacement"])
        for index, reference in enumerate(references):
            validate_id(reference["artifact_id"], field=f"artifact_reference[{index}].artifact_id")
            validate_sha256(
                reference["artifact_sha256"],
                field=f"artifact_reference[{index}].artifact_sha256",
            )
            _safe_public_locator(reference, field=f"artifact_reference[{index}].locator")

        replacement = record["replacement"]
        if replacement is not None and replacement["artifact_sha256"] == record["target"]["artifact_sha256"]:
            raise ContractError("replacement bytes must differ from the corrected target bytes")
        if ACTION_STANDING[record["action"]] != record["standing_after"]:
            raise ContractError("correction action does not match standing_after")
        if record["boundary"] != BOUNDARY:
            raise ContractError("correction boundary differs from the construction-only contract")

        unsigned = {key: value for key, value in record.items() if key != "record_sha256"}
        actual_hash = sha256_bytes(canonical_json_bytes(unsigned))
        if record["record_sha256"] != actual_hash:
            raise LedgerIntegrityError(
                f"record hash mismatch for {record['correction_id']}: expected {actual_hash}"
            )

    def _read_unlocked(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise LedgerIntegrityError(f"could not read correction ledger {self.path}: {exc}") from exc

        records: list[dict[str, Any]] = []
        previous_hash = GENESIS_PREVIOUS_HASH
        previous_time = None
        record_ids: set[str] = set()
        record_hashes: set[str] = set()
        artifact_hashes: dict[tuple[str, str], str] = {}
        standings: dict[tuple[str, str, str], str] = {}

        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                raise LedgerIntegrityError(f"blank correction-ledger line at {line_number}")
            try:
                record = json.loads(
                    line,
                    object_pairs_hook=_strict_object,
                    parse_constant=_reject_constant,
                )
            except (json.JSONDecodeError, ValueError) as exc:
                raise LedgerIntegrityError(
                    f"invalid strict JSON on correction-ledger line {line_number}: {exc}"
                ) from exc
            if not isinstance(record, dict):
                raise LedgerIntegrityError(
                    f"correction-ledger line {line_number} is not an object"
                )
            try:
                self._validate_record_contract(record)
            except (ContractError, LedgerIntegrityError) as exc:
                raise LedgerIntegrityError(
                    f"invalid correction record on line {line_number}: {exc}"
                ) from exc
            if record["sequence"] != line_number:
                raise LedgerIntegrityError(
                    f"non-contiguous correction sequence on line {line_number}"
                )
            if record["previous_record_sha256"] != previous_hash:
                raise LedgerIntegrityError(
                    f"broken correction hash chain on line {line_number}"
                )
            if record["correction_id"] in record_ids or record["record_sha256"] in record_hashes:
                raise LedgerIntegrityError(
                    f"duplicate correction ID or record hash on line {line_number}"
                )

            recorded_time = parse_utc(record["recorded_at"], field="recorded_at")
            if previous_time is not None and recorded_time < previous_time:
                raise LedgerIntegrityError("correction record time moved backwards")

            target = record["target"]
            identity = (target["artifact_class"], target["artifact_id"])
            known_hash = artifact_hashes.setdefault(identity, target["artifact_sha256"])
            if known_hash != target["artifact_sha256"]:
                raise LedgerIntegrityError(
                    f"artifact identity {identity[1]} was rebound to different original bytes"
                )
            target_key = _target_key(record)
            expected_before = standings.get(target_key, "CURRENT")
            if expected_before in TERMINAL_STANDINGS:
                raise LedgerIntegrityError(
                    f"terminal artifact standing {expected_before} cannot be changed"
                )
            if record["standing_before"] != expected_before:
                raise LedgerIntegrityError(
                    f"standing_before mismatch for {target['artifact_id']}: "
                    f"expected {expected_before}, got {record['standing_before']}"
                )
            standings[target_key] = record["standing_after"]

            record_ids.add(record["correction_id"])
            record_hashes.add(record["record_sha256"])
            previous_hash = record["record_sha256"]
            previous_time = recorded_time
            records.append(record)
        return records

    def read(self) -> list[dict[str, Any]]:
        return self._read_unlocked()

    def append(
        self,
        draft: dict[str, Any],
        *,
        recorded_at: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(draft, dict) or not set(draft).issubset(DRAFT_KEYS):
            unsupported = sorted(set(draft) - DRAFT_KEYS) if isinstance(draft, dict) else []
            detail = f": {', '.join(unsupported)}" if unsupported else ""
            raise ContractError(f"correction draft has unsupported fields{detail}")
        required = DRAFT_KEYS - {"correction_id"}
        missing = sorted(required - set(draft))
        if missing:
            raise ContractError(f"correction draft is missing fields: {', '.join(missing)}")
        correction_id = draft.get("correction_id") or f"correction:{uuid.uuid4().hex}"
        validate_id(correction_id, field="correction_id")
        recorded_at = recorded_at or utc_text(utc_now())
        parse_utc(recorded_at, field="recorded_at")

        with FileMutex(self.lock_path):
            records = self._read_unlocked()
            if any(record["correction_id"] == correction_id for record in records):
                raise ContractError(f"correction_id already exists: {correction_id}")
            target = draft["target"]
            if not isinstance(target, dict):
                raise ContractError("correction target must be an object")
            identity = (target.get("artifact_class"), target.get("artifact_id"))
            rebound = [
                record
                for record in records
                if (
                    record["target"]["artifact_class"],
                    record["target"]["artifact_id"],
                )
                == identity
                and record["target"]["artifact_sha256"] != target.get("artifact_sha256")
            ]
            if rebound:
                raise ContractError("artifact identity cannot be rebound to different original bytes")
            if records and parse_utc(recorded_at) < parse_utc(records[-1]["recorded_at"]):
                raise ContractError("correction recorded_at cannot move backwards")
            matching = [record for record in records if _target_key(record) == (
                target.get("artifact_class"),
                target.get("artifact_id"),
                target.get("artifact_sha256"),
            )]
            standing_before = matching[-1]["standing_after"] if matching else "CURRENT"
            if standing_before in TERMINAL_STANDINGS:
                raise ContractError(
                    f"artifact already has terminal standing {standing_before}; v1 cannot restore it"
                )
            action = draft["action"]
            if action not in ACTION_STANDING:
                raise ContractError(f"unknown correction action: {action!r}")

            unsigned = {
                "schema_version": 1,
                "sequence": len(records) + 1,
                "correction_id": correction_id,
                "recorded_at": recorded_at,
                "actor": draft["actor"],
                "authority": draft["authority"],
                "target": target,
                "action": action,
                "standing_before": standing_before,
                "standing_after": ACTION_STANDING[action],
                "replacement": draft["replacement"],
                "reason": draft["reason"],
                "public_summary": draft["public_summary"],
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
                raise ContractError("correction record exceeds one megabyte; cite evidence by hash")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                written = os.write(descriptor, line)
                if written != len(line):
                    raise LedgerIntegrityError("short correction-ledger write; manual recovery required")
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            return record

    def verify(self) -> dict[str, Any]:
        records = self.read()
        standings: dict[tuple[str, str, str], str] = {}
        for record in records:
            standings[_target_key(record)] = record["standing_after"]
        return {
            "valid": True,
            "records": len(records),
            "targets": len(standings),
            "head_record_sha256": (
                records[-1]["record_sha256"] if records else GENESIS_PREVIOUS_HASH
            ),
            "ledger_sha256": sha256_file(self.path) if self.path.is_file() else sha256_bytes(b""),
            "actions": dict(sorted(Counter(record["action"] for record in records).items())),
            "current_standings": dict(sorted(Counter(standings.values()).items())),
            "ledger": str(self.path),
            "scientific_standing": "NONE",
            "eligible_for_promotion": False,
        }

    def history(
        self,
        *,
        target_sha256: str | None = None,
        artifact_class: str | None = None,
        standing: str | None = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        if target_sha256 is not None:
            validate_sha256(target_sha256, field="target_sha256")
        if artifact_class is not None and artifact_class not in ARTIFACT_CLASSES:
            raise ContractError(f"unknown artifact class: {artifact_class}")
        if standing is not None and standing not in ALL_STANDINGS:
            raise ContractError(f"unknown current standing: {standing}")
        if limit < 1 or limit > 500:
            raise ContractError("correction history limit must be between 1 and 500")
        records = self.read()
        current: dict[tuple[str, str, str], str] = {}
        for record in records:
            current[_target_key(record)] = record["standing_after"]
        filtered = []
        for record in records:
            if target_sha256 is not None and record["target"]["artifact_sha256"] != target_sha256:
                continue
            if artifact_class is not None and record["target"]["artifact_class"] != artifact_class:
                continue
            if standing is not None and current[_target_key(record)] != standing:
                continue
            filtered.append(
                {
                    **record,
                    "current_standing": current[_target_key(record)],
                }
            )
        filtered.sort(key=lambda row: row["sequence"], reverse=True)
        return {
            "schema_version": 1,
            "ledger": self.verify(),
            "filters": {
                "target_sha256": target_sha256,
                "artifact_class": artifact_class,
                "standing": standing,
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
            raise ContractError(f"correction index destination already exists: {output}")
        index = self.history(limit=500)
        index["ledger"].pop("ledger", None)
        write_json(output, index)
        return index
