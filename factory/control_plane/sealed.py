from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .common import ContractError, canonical_json_bytes, load_json, sha256_bytes


class SealedRerunStore:
    """Evaluator-side rerun conclusions, kept out of the public event ledger.

    This is a structural separation for the local pilot, not a security boundary
    against somebody who controls the host.  Production uses a separate service
    and KMS-backed storage.
    """

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _path(self, rerun_claim_id: str) -> Path:
        key = sha256_bytes(rerun_claim_id.encode("utf-8"))
        return self.root / f"{key}.json"

    def commit(self, record: dict[str, Any]) -> str:
        if "salt" not in record or not isinstance(record["salt"], str):
            raise ContractError("sealed rerun records require a salt")
        commitment = sha256_bytes(canonical_json_bytes(record))
        document = {**record, "commitment_sha256": commitment}
        path = self._path(record["rerun_claim_id"])
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("x", encoding="utf-8") as handle:
                json.dump(document, handle, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        except FileExistsError as exc:
            existing = load_json(path)
            existing_commitment = existing.pop("commitment_sha256", None)
            if existing_commitment != sha256_bytes(canonical_json_bytes(existing)):
                raise ContractError("existing sealed rerun has an invalid commitment") from exc
            old_semantic = {key: value for key, value in existing.items() if key != "salt"}
            new_semantic = {key: value for key, value in record.items() if key != "salt"}
            if old_semantic != new_semantic:
                raise ContractError("a different sealed rerun already exists for this claim") from exc
            return existing_commitment
        return commitment

    def reveal(self, rerun_claim_id: str, expected_commitment: str) -> dict[str, Any]:
        path = self._path(rerun_claim_id)
        document = load_json(path)
        commitment = document.pop("commitment_sha256", None)
        actual = sha256_bytes(canonical_json_bytes(document))
        if commitment != actual or commitment != expected_commitment:
            raise ContractError("sealed rerun commitment does not match the public ledger")
        return document


class SealedClaimStore:
    """Original exact observations kept hidden from blind rerunners."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _path(self, attempt_id: str) -> Path:
        return self.root / f"{sha256_bytes(attempt_id.encode('utf-8'))}.json"

    def commit(self, record: dict[str, Any]) -> str:
        if "salt" not in record:
            raise ContractError("sealed claim records require a salt")
        commitment = sha256_bytes(canonical_json_bytes(record))
        document = {**record, "commitment_sha256": commitment}
        path = self._path(record["attempt_id"])
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("x", encoding="utf-8") as handle:
                json.dump(document, handle, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        except FileExistsError as exc:
            existing = load_json(path)
            existing_commitment = existing.pop("commitment_sha256", None)
            if existing_commitment != sha256_bytes(canonical_json_bytes(existing)):
                raise ContractError("existing sealed observation has an invalid commitment") from exc
            old_semantic = {key: value for key, value in existing.items() if key != "salt"}
            new_semantic = {key: value for key, value in record.items() if key != "salt"}
            if old_semantic != new_semantic:
                raise ContractError("a different sealed observation exists for this attempt") from exc
            return existing_commitment
        return commitment

    def reveal(self, attempt_id: str, expected_commitment: str) -> dict[str, Any]:
        document = load_json(self._path(attempt_id))
        commitment = document.pop("commitment_sha256", None)
        if commitment != sha256_bytes(canonical_json_bytes(document)) or commitment != expected_commitment:
            raise ContractError("sealed claim observation does not match the public commitment")
        return document
