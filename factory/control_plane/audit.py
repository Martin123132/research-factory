from __future__ import annotations

from typing import Any

from .workflow import _identity_key, replay


FORBIDDEN_CONCLUSION_KEYS = {
    "conclusion",
    "individual_conclusion",
    "agreement",
}
FORBIDDEN_METRIC_KEYS = {
    "candidate_metrics",
    "candidate_total_compressed_bytes",
    "total_compressed_bytes",
    "exact_output_fingerprint_sha256",
    "salt",
}


def _walk_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            keys.add(str(key))
            keys.update(_walk_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(_walk_keys(child))
    return keys


def audit_public_ledger_blindness(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Audit public structure without opening either evaluator-side sealed store."""

    state = replay(events)
    keys = _walk_keys(events)
    violations: list[str] = []
    conclusion_leaks = sorted(keys & FORBIDDEN_CONCLUSION_KEYS)
    metric_leaks = sorted(keys & FORBIDDEN_METRIC_KEYS)
    if conclusion_leaks:
        violations.append(f"plaintext conclusion keys in public ledger: {conclusion_leaks}")
    if metric_leaks:
        violations.append(f"plaintext metric or salt keys in public ledger: {metric_leaks}")

    identities_valid = True
    for attempt in state["attempts"].values():
        author = state["operators"][attempt["author_operator_id"]]
        seen = {_identity_key(author["identity"])}
        for claim_id in attempt["rerun_claim_ids"]:
            rerun = state["rerun_claims"][claim_id]
            rerunner = state["operators"][rerun["operator_id"]]
            identity = _identity_key(rerunner["identity"])
            if identity in seen:
                identities_valid = False
                violations.append(
                    f"attempt {attempt['attempt_id']} reuses an author or rerunner identity record"
                )
            seen.add(identity)

    contradictions_safe = True
    for attempt in state["attempts"].values():
        statuses = [gate["status"] for gate in attempt["gate_history"]]
        if "TIEBREAK_DIAGNOSTIC_REQUIRED" in statuses:
            later = statuses[statuses.index("TIEBREAK_DIAGNOSTIC_REQUIRED") + 1 :]
            if any(status == "RERUN_CONFIRMED_AWAITING_HOLDOUT" for status in later):
                contradictions_safe = False
                violations.append(
                    f"attempt {attempt['attempt_id']} promoted after a deterministic contradiction"
                )

    commitments = sum(
        1 for rerun in state["rerun_claims"].values() if rerun.get("commitment_sha256")
    )
    checks = {
        "no_plaintext_conclusions": not conclusion_leaks,
        "no_plaintext_metrics": not metric_leaks,
        "distinct_identity_records": identities_valid,
        "contradictions_cannot_majority_promote": contradictions_safe,
    }
    return {
        "schema_version": 1,
        "audit_type": "PUBLIC_LEDGER_BLINDNESS",
        "valid": all(checks.values()),
        "events_scanned": len(events),
        "candidate_attempts": sum(
            1
            for attempt in state["attempts"].values()
            if attempt.get("result")
            and attempt["result"]["event_type"] == "RESULT_SUBMITTED"
        ),
        "sealed_rerun_commitments": commitments,
        "checks": checks,
        "violations": violations,
    }
