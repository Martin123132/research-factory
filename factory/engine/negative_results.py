from __future__ import annotations

from pathlib import Path
from typing import Any

from control_plane.common import ContractError
from control_plane.ledger import EventLedger
from control_plane.workflow import replay


SEARCHABLE_FIELDS = (
    "attempt_id",
    "round_id",
    "work_unit_id",
    "author_operator_id",
    "classification",
    "reason_code",
    "hypothesis",
    "public_summary",
)


def _row_for_attempt(attempt: dict[str, Any]) -> dict[str, Any] | None:
    result = attempt.get("result")
    if not isinstance(result, dict) or result.get("event_type") != "NEGATIVE_RESULT_RECORDED":
        return None
    return {
        "attempt_id": attempt["attempt_id"],
        "round_id": attempt["round_id"],
        "work_unit_id": attempt["work_unit_id"],
        "author_operator_id": attempt["author_operator_id"],
        "classification": result["classification"],
        "reason_code": result["reason_code"],
        "hypothesis": result["hypothesis"],
        "public_summary": result["public_summary"],
        "submitted_at": result["submitted_at"],
        "candidate_artifact_sha256": result["candidate_artifact_sha256"],
        "evidence_package_sha256": result["evidence_package_sha256"],
        "details_sealed": result["details_sealed"],
    }


def search_rows(
    rows: list[dict[str, Any]],
    *,
    query: str | None = None,
    round_id: str | None = None,
    work_unit_id: str | None = None,
    classification: str | None = None,
    reason_code: str | None = None,
    limit: int = 50,
) -> tuple[list[dict[str, Any]], int]:
    """Filter public negative-result records and return newest records first."""

    if limit < 1 or limit > 500:
        raise ContractError("negative-result search limit must be between 1 and 500")
    terms = [term.casefold() for term in (query or "").split() if term.strip()]
    filtered: list[dict[str, Any]] = []
    for row in rows:
        if round_id is not None and row["round_id"] != round_id:
            continue
        if work_unit_id is not None and row["work_unit_id"] != work_unit_id:
            continue
        if classification is not None and row["classification"] != classification:
            continue
        if reason_code is not None and row["reason_code"].casefold() != reason_code.casefold():
            continue
        haystack = "\n".join(str(row[field]) for field in SEARCHABLE_FIELDS).casefold()
        if any(term not in haystack for term in terms):
            continue
        filtered.append(row)

    filtered.sort(key=lambda row: (row["submitted_at"], row["attempt_id"]), reverse=True)
    return filtered[:limit], len(filtered)


def search_ledger(
    ledger_path: Path,
    *,
    query: str | None = None,
    round_id: str | None = None,
    work_unit_id: str | None = None,
    classification: str | None = None,
    reason_code: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Build a read-only search result from a verified governed ledger."""

    ledger_path = ledger_path.resolve()
    if not ledger_path.is_file():
        raise ContractError(f"ledger does not exist: {ledger_path}")
    events = EventLedger(ledger_path).read()
    if not events:
        raise ContractError("ledger contains no events")
    ledger = {
        "valid": True,
        "events": len(events),
        "head_event_sha256": events[-1]["event_sha256"],
        "ledger": str(ledger_path),
    }
    rows = [
        row
        for attempt in replay(events)["attempts"].values()
        if (row := _row_for_attempt(attempt)) is not None
    ]
    results, total_matches = search_rows(
        rows,
        query=query,
        round_id=round_id,
        work_unit_id=work_unit_id,
        classification=classification,
        reason_code=reason_code,
        limit=limit,
    )
    return {
        "schema_version": 1,
        "ledger": ledger,
        "filters": {
            "query": query,
            "round_id": round_id,
            "work_unit_id": work_unit_id,
            "classification": classification,
            "reason_code": reason_code,
            "limit": limit,
        },
        "total_matches": total_matches,
        "returned": len(results),
        "results": results,
    }
