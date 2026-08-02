from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .common import ContractError, canonical_json_bytes, load_json, parse_utc, sha256_bytes


def _contract(round_document: dict[str, Any], name: str) -> dict[str, Any]:
    for row in round_document["frozen_contracts"]:
        if row["name"] == name:
            return row
    raise ContractError(f"round is missing frozen contract {name!r}")


def _public_key(round_document: dict[str, Any], factory_root: Path) -> tuple[Ed25519PublicKey, str]:
    key_contract = _contract(round_document, "evaluator_public_key")
    key_document = load_json(factory_root / key_contract["path"])
    if key_document.get("algorithm") != "Ed25519":
        raise ContractError("unsupported evaluator key algorithm")
    try:
        raw_key = base64.b64decode(key_document["public_key_base64"], validate=True)
        public_key = Ed25519PublicKey.from_public_bytes(raw_key)
    except (KeyError, ValueError) as exc:
        raise ContractError("invalid evaluator public-key encoding") from exc
    key_id = f"ed25519:{sha256_bytes(public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))}"
    if key_id != key_document.get("key_id"):
        raise ContractError("evaluator public-key ID does not match its key")
    return public_key, key_id


def _verify_signature(document: dict[str, Any], public_key: Ed25519PublicKey, *, label: str) -> None:
    try:
        signature = base64.b64decode(document["signature_base64"], validate=True)
    except (KeyError, ValueError) as exc:
        raise ContractError(f"invalid {label} signature encoding") from exc
    unsigned = {key: value for key, value in document.items() if key != "signature_base64"}
    try:
        public_key.verify(signature, canonical_json_bytes(unsigned))
    except InvalidSignature as exc:
        raise ContractError(f"{label} signature is invalid") from exc


def verify_wb001_job_token(
    token: dict[str, Any],
    *,
    round_document: dict[str, Any],
    factory_root: Path,
    candidate_artifact_sha256: str,
    operator_id: str,
    attempt_id: str,
    gate_event_sha256: str,
    gate_recorded_at: str,
    now: str,
) -> dict[str, Any]:
    public_key, key_id = _public_key(round_document, factory_root)
    _verify_signature(token, public_key, label="holdout job token")
    if token.get("token_type") != "wb001_blind_job" or token.get("maximum_uses") != 1:
        raise ContractError("unexpected holdout job token contract")
    expected = {
        "operator_id": operator_id,
        "round_id": round_document["round_id"],
        "round_sha256": round_document["round_sha256"],
        "attempt_id": attempt_id,
        "rerun_gate_event_sha256": gate_event_sha256,
        "workbench": {
            "id": round_document["workbench"]["id"],
            "version": round_document["workbench"]["version"],
        },
        "candidate_artifact_sha256": candidate_artifact_sha256,
        "holdout_commitment_sha256": _contract(
            round_document, "sealed_holdout_commitment"
        ).get("logical_commitment_sha256"),
        "evaluator_key_id": key_id,
    }
    for field, value in expected.items():
        if token.get(field) != value:
            raise ContractError(f"holdout job token has the wrong {field} binding")
    issued_at = parse_utc(token.get("issued_at"), field="token.issued_at")
    expires_at = parse_utc(token.get("expires_at"), field="token.expires_at")
    if issued_at < parse_utc(gate_recorded_at) or expires_at <= issued_at:
        raise ContractError("holdout job token was not issued after the rerun gate")
    current = parse_utc(now)
    if issued_at > current or expires_at <= current:
        raise ContractError("holdout job token is not yet valid or has expired")
    token_id = token.get("token_id")
    if not isinstance(token_id, str) or not token_id:
        raise ContractError("holdout job token is missing token_id")
    return {
        "token_id": token_id,
        "token_sha256": sha256_bytes(canonical_json_bytes(token)),
        "issued_at": token["issued_at"],
        "expires_at": token["expires_at"],
        "candidate_artifact_sha256": candidate_artifact_sha256,
        "rerun_gate_event_sha256": gate_event_sha256,
        "evaluator_key_id": key_id,
    }


def verify_wb001_attestation(
    attestation: dict[str, Any],
    *,
    round_document: dict[str, Any],
    factory_root: Path,
    candidate_artifact_sha256: str,
    attempt_id: str,
    holdout_job: dict[str, Any],
) -> dict[str, Any]:
    public_key, key_id = _public_key(round_document, factory_root)
    _verify_signature(attestation, public_key, label="holdout attestation")

    verdict = attestation.get("verdict")
    if attestation.get("attestation_type") != "wb001_blind_verdict":
        raise ContractError("unexpected holdout attestation type")
    if verdict not in {"PASS", "NO_GAIN", "INVALID", "ESCALATE"}:
        raise ContractError("unexpected holdout verdict")
    if attestation.get("candidate_artifact_sha256") != candidate_artifact_sha256:
        raise ContractError("holdout attestation targets a different candidate artifact")
    if attestation.get("workbench") != {
        "id": round_document["workbench"]["id"],
        "version": round_document["workbench"]["version"],
    }:
        raise ContractError("holdout attestation targets a different workbench epoch")
    if attestation.get("holdout_commitment_sha256") != _contract(
        round_document, "sealed_holdout_commitment"
    ).get("logical_commitment_sha256"):
        raise ContractError("holdout attestation targets a different sealed corpus")
    if attestation.get("image_lock_sha256") != _contract(
        round_document, "evaluator_image_lock"
    ).get("logical_commitment_sha256"):
        raise ContractError("holdout attestation targets a different evaluator image")
    if attestation.get("evaluator_software_sha256") != round_document["evaluator_software_sha256"]:
        raise ContractError("holdout attestation targets a different evaluator software epoch")
    if attestation.get("evaluator_key_id") != key_id:
        raise ContractError("holdout attestation targets a different evaluator key")
    causality_bindings = {
        "token_id": holdout_job["token_id"],
        "round_id": round_document["round_id"],
        "round_sha256": round_document["round_sha256"],
        "attempt_id": attempt_id,
        "rerun_gate_event_sha256": holdout_job["rerun_gate_event_sha256"],
    }
    for field, expected in causality_bindings.items():
        if attestation.get(field) != expected:
            raise ContractError(f"holdout attestation has the wrong {field} causality binding")
    if parse_utc(attestation.get("generated_at"), field="attestation.generated_at") < parse_utc(
        holdout_job["issued_at"], field="holdout_job.issued_at"
    ):
        raise ContractError("holdout attestation predates its issued job")
    if attestation.get("details_sealed") is not True:
        raise ContractError("blind attestation must keep detailed results sealed")
    return {
        "verdict": verdict,
        "run_id": attestation.get("run_id"),
        "token_id": attestation.get("token_id"),
        "rerun_gate_event_sha256": attestation["rerun_gate_event_sha256"],
        "candidate_artifact_sha256": candidate_artifact_sha256,
        "holdout_commitment_sha256": attestation["holdout_commitment_sha256"],
        "evaluator_software_sha256": attestation["evaluator_software_sha256"],
        "image_lock_sha256": attestation["image_lock_sha256"],
        "evaluator_key_id": key_id,
    }
