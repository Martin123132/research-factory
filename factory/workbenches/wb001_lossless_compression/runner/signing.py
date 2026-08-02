from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from common import ContractError, canonical_json_bytes, sha256_bytes


def key_id(public_key: Ed25519PublicKey) -> str:
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return f"ed25519:{sha256_bytes(raw)}"


def load_private_key(path: Path) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ContractError("evaluator private key is not Ed25519")
    return key


def load_public_key_document(document: dict[str, Any]) -> Ed25519PublicKey:
    if document.get("algorithm") != "Ed25519":
        raise ContractError("unsupported evaluator signing algorithm")
    try:
        raw = base64.b64decode(document["public_key_base64"], validate=True)
        public_key = Ed25519PublicKey.from_public_bytes(raw)
    except (KeyError, ValueError) as exc:
        raise ContractError("invalid evaluator public key document") from exc
    if key_id(public_key) != document.get("key_id"):
        raise ContractError("evaluator public key ID does not match the key")
    return public_key


def sign_document(unsigned: dict[str, Any], private_key: Ed25519PrivateKey) -> dict[str, Any]:
    signature = private_key.sign(canonical_json_bytes(unsigned))
    return {**unsigned, "signature_base64": base64.b64encode(signature).decode("ascii")}


def verify_signed_document(document: dict[str, Any], public_key: Ed25519PublicKey) -> None:
    signature_text = document.get("signature_base64")
    if not isinstance(signature_text, str):
        raise ContractError("signed document has no signature")
    unsigned = {key: value for key, value in document.items() if key != "signature_base64"}
    try:
        signature = base64.b64decode(signature_text, validate=True)
        public_key.verify(signature, canonical_json_bytes(unsigned))
    except (ValueError, InvalidSignature) as exc:
        raise ContractError("signed document failed Ed25519 verification") from exc
