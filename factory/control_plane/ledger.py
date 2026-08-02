from __future__ import annotations

import json
import os
import time
import uuid
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, Callable

from .common import (
    ContractError,
    LedgerIntegrityError,
    canonical_json_bytes,
    parse_utc,
    sha256_bytes,
    utc_now,
    utc_text,
    validate_id,
    validate_sha256,
)


GENESIS_PREVIOUS_HASH = "0" * 64
MAX_EVENT_BYTES = 1024 * 1024
EVENT_KEYS = {
    "schema_version",
    "sequence",
    "event_id",
    "request_id",
    "event_type",
    "recorded_at",
    "actor_id",
    "payload",
    "previous_event_sha256",
    "event_sha256",
}


class FileMutex(AbstractContextManager["FileMutex"]):
    """Small cross-platform advisory lock for one local ledger writer."""

    def __init__(self, path: Path, timeout_seconds: float = 10.0) -> None:
        self.path = path
        self.timeout_seconds = timeout_seconds
        self.handle: Any | None = None

    def __enter__(self) -> "FileMutex":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+b")
        self.handle.seek(0, os.SEEK_END)
        if self.handle.tell() == 0:
            self.handle.write(b"\0")
            self.handle.flush()

        deadline = time.monotonic() + self.timeout_seconds
        while True:
            try:
                self.handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except OSError as exc:
                if time.monotonic() >= deadline:
                    self.handle.close()
                    self.handle = None
                    raise LedgerIntegrityError(f"timed out acquiring ledger lock {self.path}") from exc
                time.sleep(0.05)

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self.handle is None:
            return
        try:
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None


TransitionValidator = Callable[[list[dict[str, Any]], str, str, dict[str, Any], str], None]


class EventLedger:
    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        events: list[dict[str, Any]] = []
        previous = GENESIS_PREVIOUS_HASH
        event_ids: set[str] = set()
        request_ids: set[str] = set()
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise LedgerIntegrityError(f"could not read ledger {self.path}: {exc}") from exc

        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                raise LedgerIntegrityError(f"blank ledger line at {line_number}")
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise LedgerIntegrityError(f"invalid JSON on ledger line {line_number}") from exc
            if not isinstance(event, dict) or set(event) != EVENT_KEYS:
                raise LedgerIntegrityError(f"ledger line {line_number} has an invalid event shape")
            if event.get("schema_version") != 1:
                raise LedgerIntegrityError(f"unsupported event schema on ledger line {line_number}")
            if event.get("sequence") != line_number:
                raise LedgerIntegrityError(f"non-contiguous sequence on ledger line {line_number}")
            if not isinstance(event.get("payload"), dict):
                raise LedgerIntegrityError(f"event payload is not an object on line {line_number}")
            try:
                validate_id(event["event_id"], field="event_id")
                validate_id(event["request_id"], field="request_id")
                validate_id(event["event_type"], field="event_type")
                validate_id(event["actor_id"], field="actor_id")
                parse_utc(event["recorded_at"], field="recorded_at")
                validate_sha256(event["previous_event_sha256"], field="previous_event_sha256")
                validate_sha256(event["event_sha256"], field="event_sha256")
            except ContractError as exc:
                raise LedgerIntegrityError(f"invalid contract on ledger line {line_number}: {exc}") from exc
            if event["event_id"] in event_ids or event["request_id"] in request_ids:
                raise LedgerIntegrityError(f"duplicate event or request ID on line {line_number}")
            if event["previous_event_sha256"] != previous:
                raise LedgerIntegrityError(f"broken hash chain on ledger line {line_number}")
            unsigned = {key: value for key, value in event.items() if key != "event_sha256"}
            actual_hash = sha256_bytes(canonical_json_bytes(unsigned))
            if event["event_sha256"] != actual_hash:
                raise LedgerIntegrityError(f"event hash mismatch on ledger line {line_number}")
            event_ids.add(event["event_id"])
            request_ids.add(event["request_id"])
            previous = actual_hash
            events.append(event)
        return events

    def append(
        self,
        event_type: str,
        actor_id: str,
        payload: dict[str, Any],
        *,
        validator: TransitionValidator,
        request_id: str | None = None,
        recorded_at: str | None = None,
    ) -> dict[str, Any]:
        validate_id(event_type, field="event_type")
        validate_id(actor_id, field="actor_id")
        if not isinstance(payload, dict):
            raise ContractError("event payload must be an object")
        request_id = request_id or f"request:{uuid.uuid4().hex}"
        validate_id(request_id, field="request_id")
        recorded_at = recorded_at or utc_text(utc_now())
        parse_utc(recorded_at, field="recorded_at")

        with FileMutex(self.lock_path):
            events = self.read()
            for existing in events:
                if existing["request_id"] != request_id:
                    continue
                if (
                    existing["event_type"] == event_type
                    and existing["actor_id"] == actor_id
                    and existing["payload"] == payload
                ):
                    return existing
                raise ContractError("request_id was already used for a different event")

            validator(events, event_type, actor_id, payload, recorded_at)
            unsigned = {
                "schema_version": 1,
                "sequence": len(events) + 1,
                "event_id": f"event:{uuid.uuid4().hex}",
                "request_id": request_id,
                "event_type": event_type,
                "recorded_at": recorded_at,
                "actor_id": actor_id,
                "payload": payload,
                "previous_event_sha256": (
                    events[-1]["event_sha256"] if events else GENESIS_PREVIOUS_HASH
                ),
            }
            event = {
                **unsigned,
                "event_sha256": sha256_bytes(canonical_json_bytes(unsigned)),
            }
            self.path.parent.mkdir(parents=True, exist_ok=True)
            line = canonical_json_bytes(event) + b"\n"
            if len(line) > MAX_EVENT_BYTES:
                raise ContractError("event exceeds the one-megabyte ledger limit; store evidence by hash")
            descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                written = os.write(descriptor, line)
                if written != len(line):
                    raise LedgerIntegrityError("short ledger write; manual recovery is required")
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            return event

    def verify(self) -> dict[str, Any]:
        events = self.read()
        return {
            "valid": True,
            "events": len(events),
            "head_event_sha256": events[-1]["event_sha256"] if events else GENESIS_PREVIOUS_HASH,
            "ledger": str(self.path),
        }
