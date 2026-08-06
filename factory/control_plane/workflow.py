from __future__ import annotations

import copy
import secrets
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from .common import (
    ContractError,
    TransitionError,
    canonical_json_bytes,
    load_json,
    parse_utc,
    sha256_bytes,
    sha256_file,
    utc_now,
    utc_text,
    validate_id,
    validate_sha256,
)
from .evidence import EvidenceStore
from .ledger import EventLedger
from .sealed import SealedClaimStore, SealedRerunStore
from .envelope import (
    build_envelope,
    execute_local_monitored,
    load_envelope_policy,
    validate_envelope,
    validate_receipt,
)
from .attestation import verify_wb001_attestation, verify_wb001_job_token
from .wb001_adapter import (
    extract_result_observation,
    verify_candidate_artifact_submission,
    verify_comparison,
)


EVENT_TYPES = {
    "FACTORY_INITIALIZED",
    "OPERATOR_CHECKED_IN",
    "ROUND_OPENED",
    "ENTRY_GATE_COMPLETED",
    "WORK_CLAIMED",
    "WORK_ENVELOPE_ISSUED",
    "WORK_ENVELOPE_REVOKED",
    "ATTEMPT_STARTED",
    "ATTEMPT_STOP_REQUESTED",
    "ATTEMPT_EXECUTION_RECORDED",
    "ATTEMPT_TERMINATED",
    "RESULT_SUBMITTED",
    "NEGATIVE_RESULT_RECORDED",
    "RERUN_WORK_CLAIMED",
    "RERUN_SUBMITTED",
    "RERUN_GATE_RECORDED",
    "HOLDOUT_JOB_ISSUED",
    "HOLDOUT_ATTESTATION_RECORDED",
    "DISPUTE_ESCALATED",
    "ATTEMPT_ANNOTATED",
}

NEGATIVE_CLASSIFICATIONS = {
    "NO_GAIN",
    "HYPOTHESIS_REJECTED",
    "RESOURCE_LIMIT",
    "UNRUNNABLE",
    "BOUNDARY_FOUND",
    "DUPLICATE_DIRECTION",
}

BLIND_DISPUTE_CODES = {
    "ARTIFACT_UNAVAILABLE",
    "CONFLICT_DECLARED",
    "ENVIRONMENT_MISMATCH",
    "PROCEDURAL_CONCERN",
    "OTHER_SEALED",
}


def _empty_state() -> dict[str, Any]:
    return {
        "factory": None,
        "operators": {},
        "identity_index": {},
        "rounds": {},
        "entry_gates": {},
        "work_claims": {},
        "work_envelopes": {},
        "attempts": {},
        "rerun_claims": {},
        "annotations": [],
    }


def _identity_key(identity: dict[str, Any]) -> tuple[str, str]:
    return identity["provider"], identity["subject"]


def _round_work_units(round_document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["work_unit_id"]: row for row in round_document["work_units"]}


def replay(events: list[dict[str, Any]]) -> dict[str, Any]:
    state = _empty_state()
    for event in events:
        payload = event["payload"]
        kind = event["event_type"]
        if kind == "FACTORY_INITIALIZED":
            state["factory"] = {
                "factory_id": payload["factory_id"],
                "policy_version": payload["policy_version"],
                "initialized_at": event["recorded_at"],
            }
            admin = copy.deepcopy(payload["initial_administrator"])
            admin["checked_in_at"] = event["recorded_at"]
            state["operators"][admin["operator_id"]] = admin
            state["identity_index"][_identity_key(admin["identity"])] = admin["operator_id"]
        elif kind == "OPERATOR_CHECKED_IN":
            operator = copy.deepcopy(payload["operator"])
            operator["checked_in_at"] = event["recorded_at"]
            state["operators"][operator["operator_id"]] = operator
            state["identity_index"][_identity_key(operator["identity"])] = operator["operator_id"]
        elif kind == "ROUND_OPENED":
            document = copy.deepcopy(payload["round"])
            state["rounds"][document["round_id"]] = {
                "definition": document,
                "opened_at": event["recorded_at"],
                "opened_by": event["actor_id"],
            }
        elif kind == "ENTRY_GATE_COMPLETED":
            state["entry_gates"][f"{payload['round_id']}\0{event['actor_id']}"] = {
                **copy.deepcopy(payload),
                "operator_id": event["actor_id"],
                "completed_at": event["recorded_at"],
            }
        elif kind == "WORK_CLAIMED":
            for old_id in payload.get("supersedes_claim_ids", []):
                state["work_claims"][old_id]["superseded_by"] = payload["work_claim_id"]
            state["work_claims"][payload["work_claim_id"]] = {
                **copy.deepcopy(payload),
                "operator_id": event["actor_id"],
                "claimed_at": event["recorded_at"],
                "superseded_by": None,
            }
        elif kind == "WORK_ENVELOPE_ISSUED":
            envelope = copy.deepcopy(payload["envelope"])
            envelope["revoked_at"] = None
            envelope["revocation_reason"] = None
            state["work_envelopes"][envelope["envelope_id"]] = envelope
            state["work_claims"][envelope["work_claim_id"]]["envelope_id"] = envelope[
                "envelope_id"
            ]
        elif kind == "WORK_ENVELOPE_REVOKED":
            envelope = state["work_envelopes"][payload["envelope_id"]]
            envelope["revoked_at"] = event["recorded_at"]
            envelope["revocation_reason"] = payload["reason"]
        elif kind == "ATTEMPT_STARTED":
            claim = state["work_claims"][payload["work_claim_id"]]
            state["attempts"][payload["attempt_id"]] = {
                **copy.deepcopy(payload),
                "round_id": claim["round_id"],
                "work_unit_id": claim["work_unit_id"],
                "author_operator_id": event["actor_id"],
                "started_at": event["recorded_at"],
                "execution_receipt": None,
                "stop_request": None,
                "termination": None,
                "result": None,
                "rerun_claim_ids": [],
                "gate_history": [],
                "holdout_job": None,
                "holdout_attestation": None,
                "dispute": None,
            }
            claim["attempt_id"] = payload["attempt_id"]
        elif kind == "ATTEMPT_STOP_REQUESTED":
            state["attempts"][payload["attempt_id"]]["stop_request"] = {
                **copy.deepcopy(payload),
                "requested_at": event["recorded_at"],
                "requested_by": event["actor_id"],
            }
        elif kind == "ATTEMPT_EXECUTION_RECORDED":
            state["attempts"][payload["attempt_id"]]["execution_receipt"] = copy.deepcopy(
                payload["receipt"]
            )
        elif kind == "ATTEMPT_TERMINATED":
            state["attempts"][payload["attempt_id"]]["termination"] = {
                **copy.deepcopy(payload),
                "terminated_at": event["recorded_at"],
                "terminated_by": event["actor_id"],
            }
        elif kind in {"RESULT_SUBMITTED", "NEGATIVE_RESULT_RECORDED"}:
            state["attempts"][payload["attempt_id"]]["result"] = {
                **copy.deepcopy(payload),
                "event_type": kind,
                "submitted_at": event["recorded_at"],
                "submitted_by": event["actor_id"],
            }
        elif kind == "RERUN_WORK_CLAIMED":
            for old_id in payload.get("supersedes_claim_ids", []):
                state["rerun_claims"][old_id]["superseded_by"] = payload["rerun_claim_id"]
            rerun = {
                **copy.deepcopy(payload),
                "operator_id": event["actor_id"],
                "claimed_at": event["recorded_at"],
                "superseded_by": None,
                "commitment_sha256": None,
                "submitted_at": None,
            }
            state["rerun_claims"][payload["rerun_claim_id"]] = rerun
            state["attempts"][payload["attempt_id"]]["rerun_claim_ids"].append(
                payload["rerun_claim_id"]
            )
        elif kind == "RERUN_SUBMITTED":
            rerun = state["rerun_claims"][payload["rerun_claim_id"]]
            rerun.update(copy.deepcopy(payload))
            rerun["submitted_at"] = event["recorded_at"]
        elif kind == "RERUN_GATE_RECORDED":
            state["attempts"][payload["attempt_id"]]["gate_history"].append(
                {**copy.deepcopy(payload), "recorded_at": event["recorded_at"]}
            )
        elif kind == "HOLDOUT_JOB_ISSUED":
            state["attempts"][payload["attempt_id"]]["holdout_job"] = {
                **copy.deepcopy(payload),
                "recorded_at": event["recorded_at"],
                "event_sha256": event["event_sha256"],
            }
        elif kind == "HOLDOUT_ATTESTATION_RECORDED":
            state["attempts"][payload["attempt_id"]]["holdout_attestation"] = {
                **copy.deepcopy(payload),
                "recorded_at": event["recorded_at"],
            }
        elif kind == "DISPUTE_ESCALATED":
            state["attempts"][payload["attempt_id"]]["dispute"] = {
                **copy.deepcopy(payload),
                "escalated_at": event["recorded_at"],
                "escalated_by": event["actor_id"],
            }
        elif kind == "ATTEMPT_ANNOTATED":
            state["annotations"].append(
                {**copy.deepcopy(payload), "recorded_at": event["recorded_at"], "actor_id": event["actor_id"]}
            )
    return state


def _is_admin(state: dict[str, Any], operator_id: str) -> bool:
    operator = state["operators"].get(operator_id)
    return bool(operator and "administrator" in operator.get("roles", []))


def _require_operator(state: dict[str, Any], operator_id: str) -> dict[str, Any]:
    operator = state["operators"].get(operator_id)
    if not operator:
        raise TransitionError("operator must check in before performing this action")
    return operator


def _attempt_is_finished(attempt: dict[str, Any]) -> bool:
    return attempt["result"] is not None or attempt.get("termination") is not None


def _attempt_gate_status(attempt: dict[str, Any], round_document: dict[str, Any]) -> str:
    if attempt["dispute"] is not None:
        return "DISPUTED_REVIEW_REQUIRED"
    if attempt.get("termination") is not None:
        return "TERMINATED_RETAINED"
    if attempt.get("stop_request") is not None and attempt.get("execution_receipt") is None:
        return "STOP_REQUESTED"
    if attempt.get("execution_receipt") is not None and attempt["result"] is None:
        if attempt["execution_receipt"]["within_envelope"]:
            return "EXECUTION_RECORDED_AWAITING_RESULT"
        return "EXECUTION_OUTSIDE_ENVELOPE_REQUIRES_RETENTION"
    if attempt["result"] is None:
        return "IN_PROGRESS"
    if attempt["result"]["event_type"] == "NEGATIVE_RESULT_RECORDED":
        return "NEGATIVE_RESULT_RETAINED"
    if attempt.get("holdout_job") is not None and attempt.get("holdout_attestation") is None:
        return "HOLDOUT_JOB_ISSUED_AWAITING_VERDICT"
    if attempt.get("holdout_attestation") is not None:
        return {
            "PASS": "HOLDOUT_PASS_AWAITING_PROMOTION_GRADE_MEASUREMENT",
            "NO_GAIN": "RETAINED_NO_GAIN",
            "INVALID": "INVALID_RETAINED",
            "ESCALATE": "EVALUATOR_REVIEW_REQUIRED",
        }[attempt["holdout_attestation"]["verdict"]]
    if attempt["gate_history"]:
        return attempt["gate_history"][-1]["status"]
    committed = sum(
        1
        for claim_id in attempt["rerun_claim_ids"]
        if attempt.get("_rerun_claims", {}).get(claim_id, {}).get("commitment_sha256")
    )
    required = int(round_document["required_independent_reruns"])
    return "READY_FOR_RERUN_GATE" if committed >= required else "AWAITING_RERUNS"


SOFTWARE_LOCK_NAMES = {"control_plane_software_lock", "evaluator_software_lock"}


def _software_lock_drift(contract: dict[str, Any], factory_root: Path) -> list[dict[str, str]]:
    drift: list[dict[str, str]] = []
    lock_path = (factory_root / contract["path"]).resolve()
    try:
        lock = load_json(lock_path)
    except ContractError:
        return [{"name": contract["name"], "expected": contract["sha256"], "actual": "INVALID_LOCK"}]
    files = lock.get("files")
    if lock.get("schema_version") != 1 or not isinstance(files, list) or not files:
        return [{"name": contract["name"], "expected": "VALID_SOFTWARE_LOCK", "actual": "MALFORMED"}]
    core = {key: value for key, value in lock.items() if key != "software_sha256"}
    actual_logical = sha256_bytes(canonical_json_bytes(core))
    expected_logical = contract.get("logical_commitment_sha256")
    if lock.get("software_sha256") != actual_logical or expected_logical != actual_logical:
        drift.append(
            {
                "name": contract["name"],
                "expected": str(expected_logical),
                "actual": actual_logical,
            }
        )
    seen: set[str] = set()
    root = factory_root.resolve()
    for row in files:
        relative = row.get("path") if isinstance(row, dict) else None
        expected = row.get("sha256") if isinstance(row, dict) else None
        if not isinstance(relative, str) or relative in seen:
            drift.append({"name": f"{contract['name']}:entry", "expected": "UNIQUE_PATH", "actual": "INVALID"})
            continue
        seen.add(relative)
        target = (root / relative).resolve()
        if not target.is_relative_to(root):
            actual = "ESCAPES_FACTORY_ROOT"
        else:
            actual = sha256_file(target) if target.is_file() else "MISSING"
        if actual != expected:
            drift.append({"name": f"{contract['name']}:{relative}", "expected": str(expected), "actual": actual})
    return drift


def _validate_round_document(document: dict[str, Any], factory_root: Path) -> None:
    try:
        Draft202012Validator(
            load_json(Path(__file__).resolve().parent / "schemas" / "round.schema.json")
        ).validate(document)
    except ValidationError as exc:
        raise ContractError(f"round document does not satisfy its JSON schema: {exc.message}") from exc
    required_fields = {
        "schema_version",
        "round_id",
        "title",
        "status",
        "workbench",
        "identity_assurance",
        "promotion_scope",
        "worker_timebox_hours",
        "default_claim_lease_hours",
        "required_independent_reruns",
        "max_diagnostic_reruns",
        "disagreement_policy",
        "evaluator_software_sha256",
        "promotion_grade_execution_required",
        "frozen_contracts",
        "lanes",
        "work_units",
        "negative_result_taxonomy",
        "round_sha256",
    }
    missing = sorted(required_fields - set(document))
    if missing:
        raise ContractError(f"round document is missing fields: {', '.join(missing)}")
    if document["schema_version"] != 1:
        raise ContractError("round.schema_version must equal 1")
    validate_id(document["round_id"], field="round_id")
    if document["required_independent_reruns"] != 2:
        raise ContractError("this pilot requires exactly two independent reruns")
    if document["max_diagnostic_reruns"] != 1:
        raise ContractError("this pilot permits one diagnostic third rerun")
    if document["disagreement_policy"] != "human_review_no_majority_promotion":
        raise ContractError("deterministic disagreements must go to human review")
    validate_sha256(document["evaluator_software_sha256"], field="evaluator_software_sha256")
    if document["promotion_grade_execution_required"] is not True:
        raise ContractError("the pilot must require promotion-grade execution before promotion")
    if not isinstance(document["worker_timebox_hours"], int) or document["worker_timebox_hours"] < 1:
        raise ContractError("worker_timebox_hours must be a positive integer")
    if not isinstance(document["default_claim_lease_hours"], int) or document["default_claim_lease_hours"] < 1:
        raise ContractError("default_claim_lease_hours must be a positive integer")

    unsigned = {key: value for key, value in document.items() if key != "round_sha256"}
    expected_round_hash = sha256_bytes(canonical_json_bytes(unsigned))
    if document["round_sha256"] != expected_round_hash:
        raise ContractError("round_sha256 does not match the round document")

    lanes = document["lanes"]
    units = document["work_units"]
    if not isinstance(lanes, list) or not lanes or not isinstance(units, list) or not units:
        raise ContractError("round lanes and work_units must be non-empty arrays")
    lane_ids = [row.get("lane_id") for row in lanes if isinstance(row, dict)]
    unit_ids = [row.get("work_unit_id") for row in units if isinstance(row, dict)]
    if len(lane_ids) != len(lanes) or len(set(lane_ids)) != len(lane_ids):
        raise ContractError("lane IDs must be present and unique")
    if len(unit_ids) != len(units) or len(set(unit_ids)) != len(unit_ids):
        raise ContractError("work-unit IDs must be present and unique")
    for lane_id in lane_ids:
        validate_id(lane_id, field="lane_id")
    for unit in units:
        validate_id(unit["work_unit_id"], field="work_unit_id")
        if unit.get("lane_id") not in lane_ids:
            raise ContractError("every work unit must refer to a declared lane")

    contracts = document["frozen_contracts"]
    if not isinstance(contracts, list) or not contracts:
        raise ContractError("frozen_contracts must be a non-empty array")
    names: set[str] = set()
    for contract in contracts:
        if not isinstance(contract, dict) or set(contract) < {"name", "path", "sha256"}:
            raise ContractError("each frozen contract requires name, path, and sha256")
        if contract["name"] in names:
            raise ContractError("frozen contract names must be unique")
        names.add(contract["name"])
        validate_sha256(contract["sha256"], field=f"frozen_contracts.{contract['name']}.sha256")
        relative = Path(contract["path"])
        if relative.is_absolute():
            raise ContractError("frozen contract paths must be relative to the factory root")
        target = (factory_root / relative).resolve()
        if not target.is_relative_to(factory_root.resolve()):
            raise ContractError("frozen contract path escapes the factory root")
        if not target.is_file() or sha256_file(target) != contract["sha256"]:
            raise ContractError(f"frozen contract does not match: {contract['name']}")
    if document["workbench"].get("id") == "WB-001":
        missing_locks = SOFTWARE_LOCK_NAMES - names
        if missing_locks:
            raise ContractError(f"WB-001 round is missing software locks: {sorted(missing_locks)}")
        contracts_by_name = {row["name"]: row for row in contracts}
        for name in SOFTWARE_LOCK_NAMES:
            problems = _software_lock_drift(contracts_by_name[name], factory_root)
            if problems:
                raise ContractError(f"frozen software lock does not match: {problems[0]['name']}")
        if document["evaluator_software_sha256"] != contracts_by_name[
            "evaluator_software_lock"
        ].get("logical_commitment_sha256"):
            raise ContractError("evaluator_software_sha256 does not match the frozen evaluator lock")


def _round_drift(round_document: dict[str, Any], factory_root: Path) -> list[dict[str, str]]:
    drift: list[dict[str, str]] = []
    for contract in round_document["frozen_contracts"]:
        target = (factory_root / contract["path"]).resolve()
        actual = sha256_file(target) if target.is_file() else "MISSING"
        if actual != contract["sha256"]:
            drift.append({"name": contract["name"], "expected": contract["sha256"], "actual": actual})
        elif contract["name"] in SOFTWARE_LOCK_NAMES:
            drift.extend(_software_lock_drift(contract, factory_root))
    return drift


class ControlPlane:
    def __init__(
        self,
        ledger_path: Path,
        *,
        factory_root: Path,
        evidence_root: Path | None = None,
        artifact_root: Path | None = None,
        private_root: Path | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.factory_root = factory_root.resolve()
        self.ledger = EventLedger(ledger_path)
        state_root = ledger_path.resolve().parent
        self.evidence = EvidenceStore(evidence_root or state_root / "private" / "evidence")
        self.artifacts = EvidenceStore(artifact_root or state_root / "public" / "artifacts")
        rerun_root = (private_root or state_root / "private" / "rerun_results").resolve()
        self.sealed_reruns = SealedRerunStore(rerun_root)
        self.sealed_claims = SealedClaimStore(rerun_root.parent / "claim_observations")
        self.clock = clock

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            raise ContractError("control-plane clock must be timezone aware")
        return value

    def events(self) -> list[dict[str, Any]]:
        return self.ledger.read()

    def _find_retry(
        self,
        *,
        request_id: str | None,
        event_type: str,
        actor_id: str,
        payload_fields: dict[str, Any],
    ) -> dict[str, Any] | None:
        if request_id is None:
            return None
        for event in self.events():
            if event["request_id"] != request_id:
                continue
            if event["event_type"] != event_type or event["actor_id"] != actor_id:
                raise ContractError("request_id was already used for a different command or actor")
            for field, expected in payload_fields.items():
                if event["payload"].get(field) != expected:
                    raise ContractError("request_id was already used with different command arguments")
            return event
        return None

    def state(self) -> dict[str, Any]:
        state = replay(self.events())
        for attempt in state["attempts"].values():
            attempt["_rerun_claims"] = state["rerun_claims"]
        return state

    def _emit(
        self,
        event_type: str,
        actor_id: str,
        payload: dict[str, Any],
        *,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        recorded_at = utc_text(self._now())
        return self.ledger.append(
            event_type,
            actor_id,
            payload,
            validator=self._validate_transition,
            request_id=request_id,
            recorded_at=recorded_at,
        )

    def _validate_transition(
        self,
        events: list[dict[str, Any]],
        event_type: str,
        actor_id: str,
        payload: dict[str, Any],
        recorded_at: str,
    ) -> None:
        if event_type not in EVENT_TYPES:
            raise TransitionError(f"unsupported event type: {event_type}")
        state = replay(events)
        now = parse_utc(recorded_at)

        if event_type == "FACTORY_INITIALIZED":
            if events or state["factory"] is not None or actor_id != "system:bootstrap":
                raise TransitionError("FACTORY_INITIALIZED must be the genesis event")
            validate_id(payload.get("factory_id"), field="factory_id")
            admin = payload.get("initial_administrator")
            if not isinstance(admin, dict):
                raise ContractError("initial_administrator must be an object")
            self._validate_operator_document(admin, administrator=True)
            return

        if state["factory"] is None:
            raise TransitionError("initialize the factory before appending workflow events")

        if event_type == "OPERATOR_CHECKED_IN":
            operator = payload.get("operator")
            if not isinstance(operator, dict):
                raise ContractError("operator must be an object")
            self._validate_operator_document(operator, administrator=False)
            if actor_id != operator["operator_id"]:
                raise TransitionError("a local check-in must be performed by that operator ID")
            if operator["operator_id"] in state["operators"]:
                raise TransitionError("operator_id is already checked in")
            if _identity_key(operator["identity"]) in state["identity_index"]:
                raise TransitionError("this provider/subject identity is already checked in")
            return

        actor = _require_operator(state, actor_id)

        if event_type == "ROUND_OPENED":
            if not _is_admin(state, actor_id):
                raise TransitionError("only an administrator can open a round")
            document = payload.get("round")
            if not isinstance(document, dict):
                raise ContractError("round must be an object")
            _validate_round_document(document, self.factory_root)
            if document["round_id"] in state["rounds"]:
                raise TransitionError("round_id already exists; corrections require a successor round")
            return

        if event_type == "ENTRY_GATE_COMPLETED":
            validate_id(payload.get("round_id"), field="round_id")
            round_state = state["rounds"].get(payload["round_id"])
            if not round_state:
                raise TransitionError("round does not exist")
            key = f"{payload['round_id']}\0{actor_id}"
            if key in state["entry_gates"]:
                raise TransitionError("operator has already completed this round's entry gate")
            if _round_drift(round_state["definition"], self.factory_root):
                raise TransitionError("round contracts have drifted")
            if payload.get("round_sha256") != round_state["definition"]["round_sha256"]:
                raise ContractError("entry gate targets a different round contract")
            for field in ("entry_evidence_sha256", "evidence_package_sha256"):
                validate_sha256(payload.get(field), field=field)
            if payload.get("all_checks_passed") is not True:
                raise ContractError("entry gate requires all checks to pass")
            return

        attempt_id = payload.get("attempt_id")
        round_id = payload.get("round_id")
        if event_type == "WORK_CLAIMED":
            validate_id(payload.get("work_claim_id"), field="work_claim_id")
            validate_id(round_id, field="round_id")
            validate_id(payload.get("work_unit_id"), field="work_unit_id")
            if payload["work_claim_id"] in state["work_claims"]:
                raise TransitionError("work_claim_id already exists")
            round_state = state["rounds"].get(round_id)
            if not round_state:
                raise TransitionError("round does not exist")
            if f"{round_id}\0{actor_id}" not in state["entry_gates"]:
                raise TransitionError("operator must complete the round entry gate before claiming work")
            if _round_drift(round_state["definition"], self.factory_root):
                raise TransitionError("round contracts have drifted; open a successor round")
            if payload["work_unit_id"] not in _round_work_units(round_state["definition"]):
                raise TransitionError("work unit does not exist in this round")
            expires = parse_utc(payload.get("expires_at"), field="expires_at")
            maximum = now + timedelta(hours=round_state["definition"]["default_claim_lease_hours"])
            if expires <= now or expires > maximum:
                raise TransitionError("work lease expiry must be within the round's frozen lease duration")
            related = [
                row for row in state["work_claims"].values()
                if row["round_id"] == round_id and row["work_unit_id"] == payload["work_unit_id"]
            ]
            for row in related:
                if row.get("attempt_id") and _attempt_is_finished(
                    state["attempts"][row["attempt_id"]]
                ):
                    continue
                if row.get("superseded_by") is None and parse_utc(row["expires_at"]) > now:
                    raise TransitionError("work unit already has an active claim")
            expected_superseded = sorted(
                row["work_claim_id"] for row in related
                if not (
                    row.get("attempt_id")
                    and _attempt_is_finished(state["attempts"][row["attempt_id"]])
                )
                if row.get("superseded_by") is None and parse_utc(row["expires_at"]) <= now
            )
            if sorted(payload.get("supersedes_claim_ids", [])) != expected_superseded:
                raise TransitionError("expired work-claim supersession set is incorrect")
            return

        if event_type == "WORK_ENVELOPE_ISSUED":
            if not _is_admin(state, actor_id):
                raise TransitionError("only an administrator can issue a work envelope")
            envelope = payload.get("envelope")
            if not isinstance(envelope, dict):
                raise ContractError("envelope must be an object")
            validate_envelope(envelope, factory_root=self.factory_root)
            if envelope["envelope_id"] in state["work_envelopes"]:
                raise TransitionError("envelope_id already exists")
            claim = state["work_claims"].get(envelope["work_claim_id"])
            if not claim:
                raise TransitionError("work envelope requires an existing work claim")
            if claim.get("envelope_id"):
                raise TransitionError("work claim already has an immutable envelope")
            if claim.get("attempt_id"):
                raise TransitionError("work envelope must be issued before the attempt starts")
            if claim.get("superseded_by") is not None or parse_utc(claim["expires_at"]) <= now:
                raise TransitionError("work envelope cannot bind an expired or superseded claim")
            round_document = state["rounds"][claim["round_id"]]["definition"]
            expected = {
                "factory_id": state["factory"]["factory_id"],
                "round_id": claim["round_id"],
                "round_sha256": round_document["round_sha256"],
                "work_unit_id": claim["work_unit_id"],
                "operator_id": claim["operator_id"],
                "issued_by": actor_id,
            }
            for field, value in expected.items():
                if envelope.get(field) != value:
                    raise TransitionError(f"work envelope is not bound to the claim field {field}")
            issued_at = parse_utc(envelope["issued_at"])
            if issued_at > now or now - issued_at > timedelta(seconds=1):
                raise TransitionError("work envelope issued_at must match its ledger event time")
            if parse_utc(envelope["expires_at"]) > parse_utc(claim["expires_at"]):
                raise TransitionError("work envelope cannot outlive its work claim")
            return

        if event_type == "WORK_ENVELOPE_REVOKED":
            if not _is_admin(state, actor_id):
                raise TransitionError("only an administrator can revoke a work envelope")
            validate_id(payload.get("envelope_id"), field="envelope_id")
            envelope = state["work_envelopes"].get(payload["envelope_id"])
            if not envelope:
                raise TransitionError("work envelope does not exist")
            if envelope.get("revoked_at") is not None:
                raise TransitionError("work envelope is already revoked")
            claim = state["work_claims"][envelope["work_claim_id"]]
            if claim.get("attempt_id"):
                raise TransitionError("an envelope cannot be revoked after its attempt starts; request stop")
            if not isinstance(payload.get("reason"), str) or not payload["reason"].strip():
                raise ContractError("work-envelope revocation requires a reason")
            return

        if event_type == "ATTEMPT_STARTED":
            validate_id(attempt_id, field="attempt_id")
            claim_id = payload.get("work_claim_id")
            validate_id(claim_id, field="work_claim_id")
            if attempt_id in state["attempts"]:
                raise TransitionError("attempt_id already exists")
            claim = state["work_claims"].get(claim_id)
            if not claim or claim["operator_id"] != actor_id:
                raise TransitionError("attempt must be started by the current work-claim owner")
            if claim.get("superseded_by") is not None or parse_utc(claim["expires_at"]) <= now:
                raise TransitionError("work claim is expired or superseded")
            if claim.get("attempt_id"):
                raise TransitionError("work claim already has an attempt")
            envelope_id = payload.get("envelope_id")
            validate_id(envelope_id, field="envelope_id")
            envelope = state["work_envelopes"].get(envelope_id)
            if not envelope or envelope["work_claim_id"] != claim_id:
                raise TransitionError("attempt requires the work claim's issued envelope")
            if envelope.get("revoked_at") is not None or parse_utc(envelope["expires_at"]) <= now:
                raise TransitionError("work envelope is revoked or expired")
            if payload.get("envelope_sha256") != envelope["envelope_sha256"]:
                raise TransitionError("attempt targets a different work-envelope commitment")
            return

        if event_type == "ATTEMPT_STOP_REQUESTED":
            validate_id(attempt_id, field="attempt_id")
            attempt = state["attempts"].get(attempt_id)
            if not attempt:
                raise TransitionError("attempt does not exist")
            if actor_id not in {attempt["author_operator_id"]} and not _is_admin(state, actor_id):
                raise TransitionError("only the worker or an administrator can stop an attempt")
            if attempt["result"] is not None or attempt.get("termination") is not None:
                raise TransitionError("completed or terminated attempts cannot receive a stop request")
            if attempt.get("stop_request") is not None:
                raise TransitionError("attempt already has an immutable stop request")
            if not isinstance(payload.get("reason"), str) or not payload["reason"].strip():
                raise ContractError("attempt stop requires a reason")
            return

        if event_type == "ATTEMPT_EXECUTION_RECORDED":
            validate_id(attempt_id, field="attempt_id")
            attempt = state["attempts"].get(attempt_id)
            if not attempt or attempt["author_operator_id"] != actor_id:
                raise TransitionError("only the attempt author can record its monitored execution")
            if attempt.get("execution_receipt") is not None:
                raise TransitionError("attempt already has an immutable execution receipt")
            if attempt["result"] is not None or attempt.get("termination") is not None:
                raise TransitionError("completed or terminated attempts cannot record execution")
            receipt = payload.get("receipt")
            if not isinstance(receipt, dict):
                raise ContractError("attempt execution requires a receipt object")
            envelope = state["work_envelopes"][attempt["envelope_id"]]
            validate_receipt(
                receipt,
                envelope=envelope,
                attempt_id=attempt_id,
                factory_root=self.factory_root,
            )
            if parse_utc(receipt["started_at"]) < parse_utc(attempt["started_at"]):
                raise TransitionError("execution receipt predates the attempt")
            return

        if event_type == "ATTEMPT_TERMINATED":
            validate_id(attempt_id, field="attempt_id")
            attempt = state["attempts"].get(attempt_id)
            if not attempt:
                raise TransitionError("attempt does not exist")
            if actor_id not in {attempt["author_operator_id"]} and not _is_admin(state, actor_id):
                raise TransitionError("only the worker or an administrator can terminate an attempt")
            if attempt["result"] is not None or attempt.get("termination") is not None:
                raise TransitionError("attempt is already completed or terminated")
            receipt = attempt.get("execution_receipt")
            if receipt is None:
                raise TransitionError("termination requires an immutable execution receipt")
            if payload.get("receipt_sha256") != receipt["receipt_sha256"]:
                raise TransitionError("termination targets a different execution receipt")
            if receipt["within_envelope"] and attempt.get("stop_request") is None:
                raise TransitionError("a successful in-envelope execution should submit a result or negative")
            if not isinstance(payload.get("reason"), str) or not payload["reason"].strip():
                raise ContractError("attempt termination requires a reason")
            return

        if event_type in {"RESULT_SUBMITTED", "NEGATIVE_RESULT_RECORDED"}:
            validate_id(attempt_id, field="attempt_id")
            attempt = state["attempts"].get(attempt_id)
            if not attempt or attempt["author_operator_id"] != actor_id:
                raise TransitionError("only the attempt author can submit its result")
            if attempt["result"] is not None:
                raise TransitionError("attempt already has an immutable result")
            claim = state["work_claims"][attempt["work_claim_id"]]
            if claim.get("superseded_by") is not None:
                raise TransitionError("a superseded work claim cannot submit a result")
            if parse_utc(claim["expires_at"]) <= now:
                raise TransitionError("the work claim expired before its result was submitted")
            if attempt.get("stop_request") is not None or attempt.get("termination") is not None:
                raise TransitionError("a stopped or terminated attempt cannot submit scientific work")
            receipt = attempt.get("execution_receipt")
            if receipt is None:
                raise TransitionError("scientific work requires an immutable monitored execution receipt")
            validate_sha256(payload.get("evidence_package_sha256"), field="evidence_package_sha256")
            validate_sha256(payload.get("candidate_artifact_sha256"), field="candidate_artifact_sha256")
            if event_type == "RESULT_SUBMITTED":
                if not receipt["within_envelope"]:
                    raise TransitionError("out-of-envelope work cannot enter candidate reruns")
                if payload.get("result_kind") != "CANDIDATE":
                    raise ContractError("result_kind must be CANDIDATE; boundaries belong in retained negatives")
                for field in (
                    "claim_result_sha256",
                    "claim_observation_commitment_sha256",
                    "comparison_decision_sha256",
                    "comparison_package_sha256",
                    "baseline_pack_sha256",
                    "method_summary_sha256",
                    "candidate_artifact_package_sha256",
                ):
                    validate_sha256(payload.get(field), field=field)
                if not isinstance(payload.get("comparison_status"), str):
                    raise ContractError("candidate result requires a frontier comparison status")
            else:
                if payload.get("classification") not in NEGATIVE_CLASSIFICATIONS:
                    raise ContractError("unknown negative-result classification")
                if not receipt["within_envelope"] and payload.get("classification") not in {
                    "RESOURCE_LIMIT",
                    "UNRUNNABLE",
                }:
                    raise TransitionError(
                        "out-of-envelope work must be retained as RESOURCE_LIMIT or UNRUNNABLE"
                    )
                if not isinstance(payload.get("hypothesis"), str) or not payload["hypothesis"].strip():
                    raise ContractError("negative results require the tested hypothesis")
                if not isinstance(payload.get("reason_code"), str) or not payload["reason_code"].strip():
                    raise ContractError("negative results require a reason_code")
            return

        if event_type == "RERUN_WORK_CLAIMED":
            validate_id(attempt_id, field="attempt_id")
            validate_id(payload.get("rerun_claim_id"), field="rerun_claim_id")
            validate_sha256(payload.get("capability_sha256"), field="capability_sha256")
            if payload.get("conflict_declaration") is not True:
                raise TransitionError("rerunner must explicitly declare assignment independence")
            attempt = state["attempts"].get(attempt_id)
            if not attempt or attempt["result"] is None:
                raise TransitionError("rerun work requires a submitted original result")
            if attempt["result"]["event_type"] != "RESULT_SUBMITTED":
                raise TransitionError("this pilot rerun gate accepts structured candidate results only")
            if actor_id == attempt["author_operator_id"]:
                raise TransitionError("the author cannot validate their own work")
            author_identity = _identity_key(state["operators"][attempt["author_operator_id"]]["identity"])
            if _identity_key(actor["identity"]) == author_identity:
                raise TransitionError("author and rerunner resolve to the same identity subject")
            for claim_id in attempt["rerun_claim_ids"]:
                prior = state["rerun_claims"][claim_id]
                if prior["operator_id"] == actor_id:
                    raise TransitionError("one operator cannot occupy multiple rerun attempts")
                prior_identity = _identity_key(state["operators"][prior["operator_id"]]["identity"])
                if prior_identity == _identity_key(actor["identity"]):
                    raise TransitionError("one identity subject cannot occupy multiple rerun attempts")

            round_document = state["rounds"][attempt["round_id"]]["definition"]
            if f"{attempt['round_id']}\0{actor_id}" not in state["entry_gates"]:
                raise TransitionError("operator must complete the round entry gate before claiming a rerun")
            if _round_drift(round_document, self.factory_root):
                raise TransitionError("round contracts have drifted; no new reruns may begin")
            status = _attempt_gate_status(attempt, round_document)
            permitted = {"AWAITING_RERUNS", "TIEBREAK_DIAGNOSTIC_REQUIRED", "REPLACEMENT_RERUN_REQUIRED"}
            if status not in permitted:
                raise TransitionError(f"attempt does not accept another rerun in state {status}")
            allowed_total = round_document["required_independent_reruns"]
            if status in {"TIEBREAK_DIAGNOSTIC_REQUIRED", "REPLACEMENT_RERUN_REQUIRED"}:
                allowed_total += round_document["max_diagnostic_reruns"]
            committed = [
                state["rerun_claims"][claim_id]
                for claim_id in attempt["rerun_claim_ids"]
                if state["rerun_claims"][claim_id].get("commitment_sha256")
            ]
            active = [
                state["rerun_claims"][claim_id]
                for claim_id in attempt["rerun_claim_ids"]
                if not state["rerun_claims"][claim_id].get("commitment_sha256")
                and state["rerun_claims"][claim_id].get("superseded_by") is None
                and parse_utc(state["rerun_claims"][claim_id]["expires_at"]) > now
            ]
            if len(committed) + len(active) >= allowed_total:
                raise TransitionError("all currently permitted rerun slots are occupied")
            expires = parse_utc(payload.get("expires_at"), field="expires_at")
            if expires <= now or expires > now + timedelta(hours=round_document["default_claim_lease_hours"]):
                raise TransitionError("rerun lease expiry exceeds the frozen lease duration")
            expected_superseded = sorted(
                claim_id for claim_id in attempt["rerun_claim_ids"]
                if not state["rerun_claims"][claim_id].get("commitment_sha256")
                and state["rerun_claims"][claim_id].get("superseded_by") is None
                and parse_utc(state["rerun_claims"][claim_id]["expires_at"]) <= now
            )
            if sorted(payload.get("supersedes_claim_ids", [])) != expected_superseded:
                raise TransitionError("expired rerun-claim supersession set is incorrect")
            return

        if event_type == "RERUN_SUBMITTED":
            claim_id = payload.get("rerun_claim_id")
            validate_id(claim_id, field="rerun_claim_id")
            rerun = state["rerun_claims"].get(claim_id)
            if not rerun or rerun["operator_id"] != actor_id:
                raise TransitionError("rerun must be submitted by its assigned operator")
            if rerun.get("superseded_by") is not None or parse_utc(rerun["expires_at"]) <= now:
                raise TransitionError("rerun claim is expired or superseded")
            if rerun.get("commitment_sha256"):
                raise TransitionError("rerun claim has already been committed")
            if payload.get("attempt_id") != rerun["attempt_id"]:
                raise TransitionError("rerun submission targets the wrong attempt")
            for field in ("commitment_sha256", "evidence_package_sha256"):
                validate_sha256(payload.get(field), field=field)
            return

        if event_type == "RERUN_GATE_RECORDED":
            if not _is_admin(state, actor_id):
                raise TransitionError("only the evaluator administrator can record a rerun gate")
            validate_id(attempt_id, field="attempt_id")
            attempt = state["attempts"].get(attempt_id)
            if not attempt or attempt["result"] is None:
                raise TransitionError("gate requires a submitted original result")
            commitment_ids = payload.get("rerun_claim_ids")
            if not isinstance(commitment_ids, list) or len(commitment_ids) < 2:
                raise ContractError("rerun gate requires at least two committed rerun claims")
            if len(set(commitment_ids)) != len(commitment_ids):
                raise ContractError("rerun gate claim IDs must be unique")
            for claim_id in commitment_ids:
                claim = state["rerun_claims"].get(claim_id)
                if not claim or claim["attempt_id"] != attempt_id or not claim.get("commitment_sha256"):
                    raise TransitionError("rerun gate refers to an uncommitted or unrelated claim")
            prior_ids = {
                claim_id
                for gate in attempt["gate_history"]
                for claim_id in gate["rerun_claim_ids"]
            }
            if set(commitment_ids) <= prior_ids:
                raise TransitionError("rerun commitments have already been evaluated")
            allowed = {
                "RERUN_CONFIRMED_AWAITING_HOLDOUT",
                "NEGATIVE_RESULT_CONFIRMED",
                "TIEBREAK_DIAGNOSTIC_REQUIRED",
                "REPLACEMENT_RERUN_REQUIRED",
                "DISPUTED_REVIEW_REQUIRED",
            }
            if payload.get("status") not in allowed:
                raise ContractError("invalid rerun gate status")
            validate_sha256(payload.get("gate_evidence_sha256"), field="gate_evidence_sha256")
            return

        if event_type == "HOLDOUT_JOB_ISSUED":
            if not _is_admin(state, actor_id):
                raise TransitionError("only the evaluator administrator can issue a holdout job")
            validate_id(attempt_id, field="attempt_id")
            attempt = state["attempts"].get(attempt_id)
            if not attempt or attempt["result"] is None:
                raise TransitionError("holdout job requires a submitted candidate")
            if attempt.get("holdout_job") is not None:
                raise TransitionError("attempt already has an immutable holdout job")
            round_document = state["rounds"][attempt["round_id"]]["definition"]
            attempt_for_status = copy.copy(attempt)
            attempt_for_status["_rerun_claims"] = state["rerun_claims"]
            if _attempt_gate_status(attempt_for_status, round_document) != "RERUN_CONFIRMED_AWAITING_HOLDOUT":
                raise TransitionError("a holdout job can be issued only after two agreeing reruns")
            matching_gates = [
                event for event in events
                if event["event_type"] == "RERUN_GATE_RECORDED"
                and event["payload"].get("attempt_id") == attempt_id
                and event["payload"].get("status") == "RERUN_CONFIRMED_AWAITING_HOLDOUT"
            ]
            if not matching_gates or payload.get("rerun_gate_event_sha256") != matching_gates[-1]["event_sha256"]:
                raise TransitionError("holdout job is not bound to the confirming rerun-gate event")
            for field in (
                "token_sha256",
                "token_package_sha256",
                "candidate_artifact_sha256",
                "rerun_gate_event_sha256",
            ):
                validate_sha256(payload.get(field), field=field)
            validate_id(payload.get("token_id"), field="token_id")
            if payload["candidate_artifact_sha256"] != attempt["result"]["candidate_artifact_sha256"]:
                raise TransitionError("holdout job targets a different candidate artifact")
            issued_at = parse_utc(payload.get("issued_at"), field="issued_at")
            expires_at = parse_utc(payload.get("expires_at"), field="expires_at")
            if (
                issued_at < parse_utc(matching_gates[-1]["recorded_at"])
                or issued_at > now
                or expires_at <= now
            ):
                raise TransitionError("holdout job timing is invalid or already expired")
            for other_attempt in state["attempts"].values():
                other = other_attempt.get("holdout_job")
                if other and other.get("token_id") == payload["token_id"]:
                    raise TransitionError("holdout job token is already joined to another attempt")
            return

        if event_type == "HOLDOUT_ATTESTATION_RECORDED":
            if not _is_admin(state, actor_id):
                raise TransitionError("only the evaluator administrator can record a holdout attestation")
            validate_id(attempt_id, field="attempt_id")
            attempt = state["attempts"].get(attempt_id)
            if not attempt or attempt["result"] is None:
                raise TransitionError("holdout attestation requires a submitted candidate")
            round_document = state["rounds"][attempt["round_id"]]["definition"]
            attempt_for_status = copy.copy(attempt)
            attempt_for_status["_rerun_claims"] = state["rerun_claims"]
            if _attempt_gate_status(attempt_for_status, round_document) != "HOLDOUT_JOB_ISSUED_AWAITING_VERDICT":
                raise TransitionError("a post-rerun signed holdout job is required before its verdict")
            if attempt.get("holdout_attestation") is not None:
                raise TransitionError("attempt already has an immutable holdout attestation")
            for other_attempt in state["attempts"].values():
                other = other_attempt.get("holdout_attestation")
                if other and (
                    other.get("token_id") == payload.get("token_id")
                    or other.get("run_id") == payload.get("run_id")
                ):
                    raise TransitionError("holdout token or run has already been joined to another attempt")
            if _round_drift(round_document, self.factory_root):
                raise TransitionError("round contracts have drifted; attestation cannot be joined")
            if payload.get("verdict") not in {"PASS", "NO_GAIN", "INVALID", "ESCALATE"}:
                raise ContractError("invalid holdout verdict")
            validate_id(payload.get("token_id"), field="token_id")
            validate_id(payload.get("run_id"), field="run_id")
            for field in (
                "attestation_package_sha256",
                "candidate_artifact_sha256",
                "holdout_commitment_sha256",
                "evaluator_software_sha256",
                "image_lock_sha256",
            ):
                validate_sha256(payload.get(field), field=field)
            if payload["candidate_artifact_sha256"] != attempt["result"]["candidate_artifact_sha256"]:
                raise TransitionError("attestation is not bound to this attempt's artifact")
            if (
                payload.get("token_id") != attempt["holdout_job"]["token_id"]
                or payload.get("rerun_gate_event_sha256")
                != attempt["holdout_job"]["rerun_gate_event_sha256"]
            ):
                raise TransitionError("attestation is not bound to this attempt's issued holdout job")
            return

        if event_type == "DISPUTE_ESCALATED":
            validate_id(attempt_id, field="attempt_id")
            attempt = state["attempts"].get(attempt_id)
            if not attempt:
                raise TransitionError("attempt does not exist")
            if actor_id != attempt["author_operator_id"] and not _is_admin(state, actor_id):
                raise TransitionError("only the author or an administrator can escalate this attempt")
            if attempt["dispute"] is not None:
                raise TransitionError("attempt is already escalated")
            if not attempt["gate_history"] and not any(
                state["rerun_claims"][claim_id].get("commitment_sha256")
                for claim_id in attempt["rerun_claim_ids"]
            ):
                raise TransitionError("a dispute needs at least one committed rerun or gate decision")
            if not isinstance(payload.get("reason"), str) or not payload["reason"].strip():
                raise ContractError("dispute escalation requires a reason")
            if payload["reason"] not in BLIND_DISPUTE_CODES:
                raise ContractError("blind disputes must use a predefined coarse reason code")
            return

        if event_type == "ATTEMPT_ANNOTATED":
            validate_id(attempt_id, field="attempt_id")
            if attempt_id not in state["attempts"]:
                raise TransitionError("attempt does not exist")
            attempt = state["attempts"][attempt_id]
            round_document = state["rounds"][attempt["round_id"]]["definition"]
            attempt_for_status = copy.copy(attempt)
            attempt_for_status["_rerun_claims"] = state["rerun_claims"]
            blind_states = {
                "AWAITING_RERUNS",
                "READY_FOR_RERUN_GATE",
                "TIEBREAK_DIAGNOSTIC_REQUIRED",
                "REPLACEMENT_RERUN_REQUIRED",
                "RERUN_CONFIRMED_AWAITING_HOLDOUT",
            }
            if _attempt_gate_status(attempt_for_status, round_document) in blind_states:
                raise TransitionError("plaintext annotations are deferred while the attempt is blind")
            if not isinstance(payload.get("note"), str) or not payload["note"].strip():
                raise ContractError("annotation note must not be empty")
            if payload.get("evidence_package_sha256") is not None:
                validate_sha256(payload["evidence_package_sha256"], field="evidence_package_sha256")
            return

        raise TransitionError(f"unhandled event type: {event_type}")

    @staticmethod
    def _validate_operator_document(operator: dict[str, Any], *, administrator: bool) -> None:
        validate_id(operator.get("operator_id"), field="operator_id")
        identity = operator.get("identity")
        if not isinstance(identity, dict):
            raise ContractError("operator identity must be an object")
        for field in ("provider", "subject"):
            if (
                not isinstance(identity.get(field), str)
                or not identity[field].strip()
                or len(identity[field]) > 256
            ):
                raise ContractError(f"identity.{field} must not be empty")
        if operator.get("identity_assurance") not in {"self-asserted-local", "authenticated-external"}:
            raise ContractError("unknown identity assurance level")
        roles = operator.get("roles")
        expected = {"operator", "administrator"} if administrator else {"operator"}
        if not isinstance(roles, list) or set(roles) != expected:
            raise ContractError(f"operator roles must equal {sorted(expected)}")
        if not isinstance(operator.get("conflict_declaration"), bool) or not operator["conflict_declaration"]:
            raise ContractError("operator must accept the conflict-of-interest declaration")

    def initialize(
        self,
        *,
        factory_id: str,
        admin_id: str,
        provider: str,
        subject: str,
        display_name: str,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "factory_id": factory_id,
            "policy_version": "research-factory-control-v1",
            "initial_administrator": {
                "operator_id": admin_id,
                "display_name": display_name,
                "identity": {"provider": provider, "subject": subject},
                "identity_assurance": "self-asserted-local",
                "roles": ["administrator", "operator"],
                "conflict_declaration": True,
            },
        }
        return self._emit("FACTORY_INITIALIZED", "system:bootstrap", payload, request_id=request_id)

    def check_in(
        self,
        *,
        operator_id: str,
        provider: str,
        subject: str,
        display_name: str,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "operator": {
                "operator_id": operator_id,
                "display_name": display_name,
                "identity": {"provider": provider, "subject": subject},
                "identity_assurance": "self-asserted-local",
                "roles": ["operator"],
                "conflict_declaration": True,
            }
        }
        return self._emit("OPERATOR_CHECKED_IN", operator_id, payload, request_id=request_id)

    def open_round(self, *, actor_id: str, round_path: Path, request_id: str | None = None) -> dict[str, Any]:
        document = load_json(round_path)
        return self._emit("ROUND_OPENED", actor_id, {"round": document}, request_id=request_id)

    def complete_entry_gate(
        self,
        *,
        operator_id: str,
        round_id: str,
        evidence_path: Path,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        state = self.state()
        round_state = state["rounds"].get(round_id)
        if not round_state:
            raise TransitionError("round does not exist")
        evidence = load_json(evidence_path)
        try:
            Draft202012Validator(
                load_json(Path(__file__).resolve().parent / "schemas" / "entry-gate.schema.json")
            ).validate(evidence)
        except ValidationError as exc:
            raise ContractError(f"entry evidence does not satisfy its JSON schema: {exc.message}") from exc
        expected_fields = {
            "schema_version": 1,
            "evidence_type": "worker_entry_gate",
            "round_id": round_id,
            "round_sha256": round_state["definition"]["round_sha256"],
            "operator_id": operator_id,
        }
        for field, expected in expected_fields.items():
            if evidence.get(field) != expected:
                raise ContractError(f"entry evidence field {field!r} does not match")
        checks = evidence.get("checks")
        required_checks = {
            "frozen_contracts_match",
            "schemas_validate",
            "reference_round_trip_exact",
            "reference_output_deterministic",
            "rules_acknowledged",
        }
        if not isinstance(checks, dict) or set(checks) != required_checks or not all(checks.values()):
            raise ContractError("entry evidence must contain every required passing check")
        expected_hash = evidence.get("entry_evidence_sha256")
        unsigned = {key: value for key, value in evidence.items() if key != "entry_evidence_sha256"}
        actual_hash = sha256_bytes(canonical_json_bytes(unsigned))
        if expected_hash != actual_hash:
            raise ContractError("entry_evidence_sha256 does not match the evidence document")
        bundle = self.evidence.ingest(evidence_path)
        payload = {
            "round_id": round_id,
            "round_sha256": evidence["round_sha256"],
            "entry_evidence_sha256": actual_hash,
            "evidence_package_sha256": bundle["package_sha256"],
            "all_checks_passed": True,
        }
        return self._emit("ENTRY_GATE_COMPLETED", operator_id, payload, request_id=request_id)

    def claim_work(
        self,
        *,
        operator_id: str,
        round_id: str,
        work_unit_id: str,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        retry = self._find_retry(
            request_id=request_id,
            event_type="WORK_CLAIMED",
            actor_id=operator_id,
            payload_fields={"round_id": round_id, "work_unit_id": work_unit_id},
        )
        if retry is not None:
            return retry
        state = self.state()
        round_state = state["rounds"].get(round_id)
        if not round_state:
            raise TransitionError("round does not exist")
        now = self._now()
        related = [
            row for row in state["work_claims"].values()
            if row["round_id"] == round_id and row["work_unit_id"] == work_unit_id
        ]
        superseded = sorted(
            row["work_claim_id"] for row in related
            if row.get("superseded_by") is None
            and not (
                row.get("attempt_id")
                and _attempt_is_finished(state["attempts"][row["attempt_id"]])
            )
            and parse_utc(row["expires_at"]) <= now
        )
        payload = {
            "work_claim_id": f"work-claim:{uuid.uuid4().hex}",
            "round_id": round_id,
            "work_unit_id": work_unit_id,
            "expires_at": utc_text(now + timedelta(hours=round_state["definition"]["default_claim_lease_hours"])),
            "supersedes_claim_ids": superseded,
        }
        return self._emit("WORK_CLAIMED", operator_id, payload, request_id=request_id)

    def start_attempt(
        self,
        *,
        operator_id: str,
        work_claim_id: str,
        envelope_id: str,
        release_capability: str,
        attempt_id: str | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(release_capability, str) or len(release_capability) < 32:
            raise ContractError("envelope release capability must be a saved secret of at least 32 characters")
        state = self.state()
        envelope = state["work_envelopes"].get(envelope_id)
        if not envelope or envelope["work_claim_id"] != work_claim_id:
            raise TransitionError("attempt requires the work claim's issued envelope")
        if envelope["release_capability_sha256"] != sha256_bytes(
            release_capability.encode("utf-8")
        ):
            raise TransitionError("envelope release capability is invalid")
        retry_fields: dict[str, Any] = {
            "work_claim_id": work_claim_id,
            "envelope_id": envelope_id,
            "envelope_sha256": envelope["envelope_sha256"],
        }
        if attempt_id is not None:
            retry_fields["attempt_id"] = attempt_id
        retry = self._find_retry(
            request_id=request_id,
            event_type="ATTEMPT_STARTED",
            actor_id=operator_id,
            payload_fields=retry_fields,
        )
        if retry is not None:
            return retry
        payload = {
            "attempt_id": attempt_id or f"attempt:{uuid.uuid4().hex}",
            "work_claim_id": work_claim_id,
            "envelope_id": envelope_id,
            "envelope_sha256": envelope["envelope_sha256"],
        }
        return self._emit("ATTEMPT_STARTED", operator_id, payload, request_id=request_id)

    def issue_work_envelope(
        self,
        *,
        actor_id: str,
        work_claim_id: str,
        policy_path: Path,
        release_capability: str,
        envelope_id: str | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(release_capability, str) or len(release_capability) < 32:
            raise ContractError("envelope release capability must be a saved secret of at least 32 characters")
        policy = load_envelope_policy(policy_path, factory_root=self.factory_root)
        state = self.state()
        claim = state["work_claims"].get(work_claim_id)
        if not claim:
            raise TransitionError("work claim does not exist")
        round_document = state["rounds"][claim["round_id"]]["definition"]
        now_text = utc_text(self._now())
        requested_id = envelope_id or f"envelope:{uuid.uuid4().hex}"
        retry = self._find_retry(
            request_id=request_id,
            event_type="WORK_ENVELOPE_ISSUED",
            actor_id=actor_id,
            payload_fields={},
        )
        if retry is not None:
            existing = retry["payload"]["envelope"]
            if (
                existing["work_claim_id"] != work_claim_id
                or existing["policy_sha256"] != policy["policy_sha256"]
                or existing["release_capability_sha256"]
                != sha256_bytes(release_capability.encode("utf-8"))
            ):
                raise ContractError("request_id retry supplied different work-envelope arguments")
            return {"event": retry, "release_capability_retained_by_human": True}
        envelope = build_envelope(
            envelope_id=requested_id,
            policy=policy,
            factory_id=state["factory"]["factory_id"],
            round_id=claim["round_id"],
            round_sha256=round_document["round_sha256"],
            work_unit_id=claim["work_unit_id"],
            work_claim_id=work_claim_id,
            operator_id=claim["operator_id"],
            issued_by=actor_id,
            issued_at=now_text,
            expires_at=claim["expires_at"],
            release_capability_sha256=sha256_bytes(release_capability.encode("utf-8")),
        )
        event = self._emit(
            "WORK_ENVELOPE_ISSUED",
            actor_id,
            {"envelope": envelope},
            request_id=request_id,
        )
        return {"event": event, "release_capability_retained_by_human": True}

    def revoke_work_envelope(
        self,
        *,
        actor_id: str,
        envelope_id: str,
        reason: str,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        return self._emit(
            "WORK_ENVELOPE_REVOKED",
            actor_id,
            {"envelope_id": envelope_id, "reason": reason},
            request_id=request_id,
        )

    def request_attempt_stop(
        self,
        *,
        actor_id: str,
        attempt_id: str,
        reason: str,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        return self._emit(
            "ATTEMPT_STOP_REQUESTED",
            actor_id,
            {"attempt_id": attempt_id, "reason": reason},
            request_id=request_id,
        )

    def record_attempt_receipt(
        self,
        *,
        operator_id: str,
        attempt_id: str,
        receipt: dict[str, Any],
        request_id: str | None = None,
    ) -> dict[str, Any]:
        return self._emit(
            "ATTEMPT_EXECUTION_RECORDED",
            operator_id,
            {"attempt_id": attempt_id, "receipt": receipt},
            request_id=request_id,
        )

    def execute_attempt(
        self,
        *,
        operator_id: str,
        attempt_id: str,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        state = self.state()
        attempt = state["attempts"].get(attempt_id)
        if not attempt or attempt["author_operator_id"] != operator_id:
            raise TransitionError("only the attempt author can run its envelope")
        if attempt.get("execution_receipt") is not None:
            raise TransitionError("attempt already has an immutable execution receipt")
        if attempt["result"] is not None or attempt.get("termination") is not None:
            raise TransitionError("completed or terminated attempts cannot execute")
        if attempt.get("stop_request") is not None:
            raise TransitionError("a stopped attempt cannot launch its command")
        envelope = state["work_envelopes"][attempt["envelope_id"]]
        if (
            envelope.get("revoked_at") is not None
            or parse_utc(envelope["expires_at"]) <= self._now()
        ):
            raise TransitionError("work envelope is revoked or expired")

        def stopped() -> bool:
            current = self.state()["attempts"].get(attempt_id)
            return bool(current and current.get("stop_request"))

        receipt = execute_local_monitored(
            envelope=envelope,
            attempt_id=attempt_id,
            factory_root=self.factory_root,
            stop_requested=stopped,
            timestamp_clock=self._now,
        )
        event = self.record_attempt_receipt(
            operator_id=operator_id,
            attempt_id=attempt_id,
            receipt=receipt,
            request_id=request_id,
        )
        return {
            "event": event,
            "within_envelope": receipt["within_envelope"],
            "termination_reason": receipt["termination_reason"],
            "promotion_eligible": False,
        }

    def terminate_attempt(
        self,
        *,
        actor_id: str,
        attempt_id: str,
        reason: str,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        state = self.state()
        attempt = state["attempts"].get(attempt_id)
        if not attempt or attempt.get("execution_receipt") is None:
            raise TransitionError("attempt termination requires a recorded execution receipt")
        return self._emit(
            "ATTEMPT_TERMINATED",
            actor_id,
            {
                "attempt_id": attempt_id,
                "receipt_sha256": attempt["execution_receipt"]["receipt_sha256"],
                "reason": reason,
            },
            request_id=request_id,
        )

    def submit_result(
        self,
        *,
        operator_id: str,
        attempt_id: str,
        evidence_path: Path,
        comparison_path: Path,
        candidate_submission_path: Path,
        candidate_artifact_sha256: str,
        result_kind: str,
        public_summary: str,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(public_summary, str) or not public_summary.strip() or len(public_summary) > 2048:
            raise ContractError("method summary must contain 1-2048 characters")
        state = self.state()
        attempt = state["attempts"].get(attempt_id)
        if not attempt:
            raise TransitionError("attempt does not exist")
        round_document = state["rounds"][attempt["round_id"]]["definition"]
        result, observation = extract_result_observation(
            evidence_path,
            factory_root=self.factory_root,
            expected_operator_id=operator_id,
            expected_artifact_sha256=candidate_artifact_sha256,
            round_document=round_document,
        )
        comparison, comparison_binding = verify_comparison(
            comparison_path,
            factory_root=self.factory_root,
            result=result,
            result_kind=result_kind,
            round_document=round_document,
        )
        artifact_base, artifact_paths = verify_candidate_artifact_submission(
            candidate_submission_path,
            result=result,
        )
        bundle = self.evidence.ingest(evidence_path)
        comparison_bundle = self.evidence.ingest(comparison_path)
        artifact_bundle = self.artifacts.ingest_declared(artifact_base, artifact_paths)
        retry = self._find_retry(
            request_id=request_id,
            event_type="RESULT_SUBMITTED",
            actor_id=operator_id,
            payload_fields={
                "attempt_id": attempt_id,
                "result_kind": result_kind,
                "candidate_artifact_sha256": candidate_artifact_sha256,
                "evidence_package_sha256": bundle["package_sha256"],
                "comparison_package_sha256": comparison_bundle["package_sha256"],
                "candidate_artifact_package_sha256": artifact_bundle["package_sha256"],
                "method_summary_sha256": sha256_bytes(public_summary.encode("utf-8")),
            },
        )
        if retry is not None:
            return retry
        claim_record = {
            "schema_version": 1,
            "attempt_id": attempt_id,
            "operator_id": operator_id,
            "observation": observation,
            "comparison_decision_sha256": comparison["decision_sha256"],
            "method_summary": public_summary,
            "salt": secrets.token_hex(32),
        }
        claim_commitment = self.sealed_claims.commit(claim_record)
        payload = {
            "attempt_id": attempt_id,
            "result_kind": result_kind,
            "candidate_artifact_sha256": candidate_artifact_sha256,
            "evidence_package_sha256": bundle["package_sha256"],
            "comparison_package_sha256": comparison_bundle["package_sha256"],
            "candidate_artifact_package_sha256": artifact_bundle["package_sha256"],
            "claim_result_sha256": result["result_sha256"],
            "claim_observation_commitment_sha256": claim_commitment,
            **comparison_binding,
            "method_summary_sha256": sha256_bytes(public_summary.encode("utf-8")),
            "details_sealed": True,
        }
        return self._emit("RESULT_SUBMITTED", operator_id, payload, request_id=request_id)

    def record_negative(
        self,
        *,
        operator_id: str,
        attempt_id: str,
        evidence_path: Path,
        candidate_artifact_sha256: str,
        classification: str,
        reason_code: str,
        hypothesis: str,
        public_summary: str,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(public_summary, str) or not public_summary.strip() or len(public_summary) > 2048:
            raise ContractError("negative-result summary must contain 1-2048 characters")
        bundle = self.evidence.ingest(evidence_path)
        payload = {
            "attempt_id": attempt_id,
            "classification": classification,
            "reason_code": reason_code,
            "hypothesis": hypothesis,
            "candidate_artifact_sha256": candidate_artifact_sha256,
            "evidence_package_sha256": bundle["package_sha256"],
            "public_summary": public_summary,
            "details_sealed": True,
        }
        return self._emit("NEGATIVE_RESULT_RECORDED", operator_id, payload, request_id=request_id)

    def claim_rerun(
        self,
        *,
        operator_id: str,
        attempt_id: str,
        capability: str,
        conflict_declaration: bool,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(capability, str) or len(capability) < 32:
            raise ContractError("rerun capability must be a saved random secret of at least 32 characters")
        if conflict_declaration is not True:
            raise TransitionError("rerunner must declare no conflict for this assignment")
        retry = self._find_retry(
            request_id=request_id,
            event_type="RERUN_WORK_CLAIMED",
            actor_id=operator_id,
            payload_fields={"attempt_id": attempt_id},
        )
        if retry is not None:
            if retry["payload"]["capability_sha256"] != sha256_bytes(capability.encode("utf-8")):
                raise ContractError("request_id retry supplied a different rerun capability")
            state = self.state()
            attempt = state["attempts"][attempt_id]
            return {
                "event": retry,
                "lease_capability": capability,
                "candidate_artifact_sha256": attempt["result"]["candidate_artifact_sha256"],
                "candidate_artifact_package_sha256": attempt["result"][
                    "candidate_artifact_package_sha256"
                ],
                "note": "Idempotent retry recovered the same client-retained capability and artifact binding.",
            }
        state = self.state()
        attempt = state["attempts"].get(attempt_id)
        if not attempt:
            raise TransitionError("attempt does not exist")
        round_document = state["rounds"][attempt["round_id"]]["definition"]
        now = self._now()
        superseded = sorted(
            claim_id for claim_id in attempt["rerun_claim_ids"]
            if not state["rerun_claims"][claim_id].get("commitment_sha256")
            and state["rerun_claims"][claim_id].get("superseded_by") is None
            and parse_utc(state["rerun_claims"][claim_id]["expires_at"]) <= now
        )
        payload = {
            "rerun_claim_id": f"rerun-claim:{uuid.uuid4().hex}",
            "attempt_id": attempt_id,
            "expires_at": utc_text(now + timedelta(hours=round_document["default_claim_lease_hours"])),
            "capability_sha256": sha256_bytes(capability.encode("utf-8")),
            "conflict_declaration": True,
            "supersedes_claim_ids": superseded,
        }
        event = self._emit("RERUN_WORK_CLAIMED", operator_id, payload, request_id=request_id)
        return {
            "event": event,
            "lease_capability": capability,
            "candidate_artifact_sha256": attempt["result"]["candidate_artifact_sha256"],
            "candidate_artifact_package_sha256": attempt["result"][
                "candidate_artifact_package_sha256"
            ],
        }

    def submit_rerun(
        self,
        *,
        operator_id: str,
        rerun_claim_id: str,
        capability: str,
        evidence_path: Path,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        state = self.state()
        claim = state["rerun_claims"].get(rerun_claim_id)
        if not claim:
            raise TransitionError("rerun claim does not exist")
        if claim["operator_id"] != operator_id:
            raise TransitionError("rerun claim belongs to a different operator")
        if sha256_bytes(capability.encode("utf-8")) != claim["capability_sha256"]:
            raise TransitionError("rerun lease capability is incorrect")
        attempt = state["attempts"][claim["attempt_id"]]
        round_document = state["rounds"][attempt["round_id"]]["definition"]
        _, observation = extract_result_observation(
            evidence_path,
            factory_root=self.factory_root,
            expected_operator_id=operator_id,
            expected_artifact_sha256=attempt["result"]["candidate_artifact_sha256"],
            round_document=round_document,
            allow_failed_hard_gate=True,
            require_secure_boundary=True,
        )
        bundle = self.evidence.ingest(evidence_path)
        retry = self._find_retry(
            request_id=request_id,
            event_type="RERUN_SUBMITTED",
            actor_id=operator_id,
            payload_fields={
                "rerun_claim_id": rerun_claim_id,
                "attempt_id": claim["attempt_id"],
                "evidence_package_sha256": bundle["package_sha256"],
            },
        )
        if retry is not None:
            sealed = self.sealed_reruns.reveal(rerun_claim_id, retry["payload"]["commitment_sha256"])
            if sealed["observation"] != observation:
                raise ContractError("request_id was already used with a different rerun observation")
            return retry
        if claim.get("superseded_by") is not None or parse_utc(claim["expires_at"]) <= self._now():
            raise TransitionError("rerun claim is expired or superseded")
        sealed_record = {
            "schema_version": 1,
            "rerun_claim_id": rerun_claim_id,
            "attempt_id": claim["attempt_id"],
            "operator_id": operator_id,
            "observation": observation,
            "evidence_package_sha256": bundle["package_sha256"],
            "salt": secrets.token_hex(32),
        }
        commitment = self.sealed_reruns.commit(sealed_record)
        payload = {
            "rerun_claim_id": rerun_claim_id,
            "attempt_id": claim["attempt_id"],
            "commitment_sha256": commitment,
            "evidence_package_sha256": bundle["package_sha256"],
            "conclusion_sealed": True,
        }
        return self._emit("RERUN_SUBMITTED", operator_id, payload, request_id=request_id)

    def evaluate_reruns(
        self,
        *,
        actor_id: str,
        attempt_id: str,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        retry = self._find_retry(
            request_id=request_id,
            event_type="RERUN_GATE_RECORDED",
            actor_id=actor_id,
            payload_fields={"attempt_id": attempt_id},
        )
        if retry is not None:
            return retry
        state = self.state()
        _require_operator(state, actor_id)
        if not _is_admin(state, actor_id):
            raise TransitionError("only the evaluator administrator can evaluate sealed reruns")
        attempt = state["attempts"].get(attempt_id)
        if not attempt:
            raise TransitionError("attempt does not exist")
        committed = [
            state["rerun_claims"][claim_id]
            for claim_id in attempt["rerun_claim_ids"]
            if state["rerun_claims"][claim_id].get("commitment_sha256")
        ]
        prior_ids = {
            claim_id
            for gate in attempt["gate_history"]
            for claim_id in gate["rerun_claim_ids"]
        }
        if len(committed) < 2 or set(row["rerun_claim_id"] for row in committed) <= prior_ids:
            raise TransitionError("no new complete rerun set is ready for evaluation")
        records = [
            self.sealed_reruns.reveal(row["rerun_claim_id"], row["commitment_sha256"])
            for row in committed
        ]
        claim_record = self.sealed_claims.reveal(
            attempt_id,
            attempt["result"]["claim_observation_commitment_sha256"],
        )
        original_observation = claim_record["observation"]
        conclusions = []
        for record in records:
            observation = record["observation"]
            if observation["hard_gate_pass"] is not True:
                conclusions.append("INVALID")
            elif (
                observation["candidate_artifact_sha256"] == original_observation["candidate_artifact_sha256"]
                and observation["corpus_sha256"] == original_observation["corpus_sha256"]
                and observation["exact_output_fingerprint_sha256"]
                == original_observation["exact_output_fingerprint_sha256"]
            ):
                conclusions.append("AGREES")
            else:
                conclusions.append("DISAGREES")
        agrees = conclusions.count("AGREES")
        disagrees = conclusions.count("DISAGREES")
        incomplete = conclusions.count("UNRUNNABLE") + conclusions.count("INVALID")
        if len(records) == 2:
            if agrees == 2:
                status = "RERUN_CONFIRMED_AWAITING_HOLDOUT"
            elif agrees == 1 and disagrees == 1:
                status = "TIEBREAK_DIAGNOSTIC_REQUIRED"
            elif incomplete:
                status = "REPLACEMENT_RERUN_REQUIRED"
            else:
                status = "DISPUTED_REVIEW_REQUIRED"
        else:
            # A procedurally invalid run can be replaced once. A valid
            # deterministic mismatch remains contrary evidence and cannot be
            # outvoted by the diagnostic third run.
            valid_conclusions = [value for value in conclusions if value != "INVALID"]
            status = (
                "RERUN_CONFIRMED_AWAITING_HOLDOUT"
                if len(valid_conclusions) >= 2 and set(valid_conclusions) == {"AGREES"}
                else "DISPUTED_REVIEW_REQUIRED"
            )

        gate_core = {
            "schema_version": 1,
            "attempt_id": attempt_id,
            "rerun_commitments": sorted(row["commitment_sha256"] for row in committed),
            "conclusion_counts": {
                "agrees": agrees,
                "disagrees": disagrees,
                "incomplete": incomplete,
            },
        }
        payload = {
            "attempt_id": attempt_id,
            "rerun_claim_ids": [row["rerun_claim_id"] for row in committed],
            "status": status,
            "gate_evidence_sha256": sha256_bytes(canonical_json_bytes(gate_core)),
            "individual_conclusions_sealed": True,
        }
        return self._emit("RERUN_GATE_RECORDED", actor_id, payload, request_id=request_id)

    def record_holdout_job(
        self,
        *,
        actor_id: str,
        attempt_id: str,
        token_path: Path,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        state = self.state()
        _require_operator(state, actor_id)
        if not _is_admin(state, actor_id):
            raise TransitionError("only the evaluator administrator can issue a holdout job")
        attempt = state["attempts"].get(attempt_id)
        if not attempt or attempt["result"] is None:
            raise TransitionError("attempt does not have a submitted result")
        gate_events = [
            event for event in self.events()
            if event["event_type"] == "RERUN_GATE_RECORDED"
            and event["payload"].get("attempt_id") == attempt_id
            and event["payload"].get("status") == "RERUN_CONFIRMED_AWAITING_HOLDOUT"
        ]
        if not gate_events:
            raise TransitionError("two agreeing reruns must be recorded before holdout job issuance")
        gate_event = gate_events[-1]
        round_document = state["rounds"][attempt["round_id"]]["definition"]
        token = load_json(token_path)
        verified = verify_wb001_job_token(
            token,
            round_document=round_document,
            factory_root=self.factory_root,
            candidate_artifact_sha256=attempt["result"]["candidate_artifact_sha256"],
            operator_id=attempt["author_operator_id"],
            attempt_id=attempt_id,
            gate_event_sha256=gate_event["event_sha256"],
            gate_recorded_at=gate_event["recorded_at"],
            now=utc_text(self._now()),
        )
        bundle = self.evidence.ingest(token_path)
        payload = {
            "attempt_id": attempt_id,
            **verified,
            "token_package_sha256": bundle["package_sha256"],
            "signature_verified": True,
        }
        return self._emit("HOLDOUT_JOB_ISSUED", actor_id, payload, request_id=request_id)

    def record_holdout_attestation(
        self,
        *,
        actor_id: str,
        attempt_id: str,
        attestation_path: Path,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        state = self.state()
        attempt = state["attempts"].get(attempt_id)
        if not attempt or attempt["result"] is None:
            raise TransitionError("attempt does not have a submitted result")
        if attempt.get("holdout_job") is None:
            raise TransitionError("attempt has no post-rerun signed holdout job")
        round_document = state["rounds"][attempt["round_id"]]["definition"]
        attestation = load_json(attestation_path)
        verified = verify_wb001_attestation(
            attestation,
            round_document=round_document,
            factory_root=self.factory_root,
            candidate_artifact_sha256=attempt["result"]["candidate_artifact_sha256"],
            attempt_id=attempt_id,
            holdout_job=attempt["holdout_job"],
        )
        bundle = self.evidence.ingest(attestation_path)
        payload = {
            "attempt_id": attempt_id,
            **verified,
            "attestation_package_sha256": bundle["package_sha256"],
            "signature_verified": True,
            "details_sealed": True,
            "promotion_grade_execution_still_required": True,
        }
        return self._emit("HOLDOUT_ATTESTATION_RECORDED", actor_id, payload, request_id=request_id)

    def escalate_dispute(
        self,
        *,
        actor_id: str,
        attempt_id: str,
        reason: str,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        return self._emit(
            "DISPUTE_ESCALATED",
            actor_id,
            {"attempt_id": attempt_id, "reason": reason},
            request_id=request_id,
        )

    def annotate_attempt(
        self,
        *,
        actor_id: str,
        attempt_id: str,
        note: str,
        evidence_path: Path | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"attempt_id": attempt_id, "note": note}
        if evidence_path is not None:
            payload["evidence_package_sha256"] = self.evidence.ingest(evidence_path)["package_sha256"]
        return self._emit("ATTEMPT_ANNOTATED", actor_id, payload, request_id=request_id)

    def snapshot(self, *, round_id: str | None = None) -> dict[str, Any]:
        events = self.events()
        state = replay(events)
        now = self._now()
        rounds: list[dict[str, Any]] = []
        for current_id, round_state in state["rounds"].items():
            if round_id is not None and current_id != round_id:
                continue
            document = round_state["definition"]
            drift = _round_drift(document, self.factory_root)
            units: list[dict[str, Any]] = []
            for unit_id, unit in _round_work_units(document).items():
                claims = [
                    row for row in state["work_claims"].values()
                    if row["round_id"] == current_id and row["work_unit_id"] == unit_id
                ]
                completed_attempts = [
                    state["attempts"][row["attempt_id"]]
                    for row in claims
                    if row.get("attempt_id")
                    and (
                        state["attempts"][row["attempt_id"]]["result"] is not None
                        or state["attempts"][row["attempt_id"]].get("termination") is not None
                    )
                ]
                completed_attempt = completed_attempts[-1] if completed_attempts else None
                active = next(
                    (
                        row for row in reversed(claims)
                        if row.get("superseded_by") is None
                        and not (
                            row.get("attempt_id")
                            and (
                                state["attempts"][row["attempt_id"]]["result"] is not None
                                or state["attempts"][row["attempt_id"]].get("termination") is not None
                            )
                        )
                        and parse_utc(row["expires_at"]) > now
                    ),
                    None,
                )
                status = "CLAIMED" if active else "OPEN_WITH_HISTORY" if completed_attempt else "OPEN"
                units.append(
                    {
                        "work_unit_id": unit_id,
                        "lane_id": unit["lane_id"],
                        "title": unit["title"],
                        "status": status,
                        "operator_id": active["operator_id"] if active else None,
                        "attempt_id": completed_attempt["attempt_id"] if completed_attempt else None,
                        "completed_attempts": len(completed_attempts),
                    }
                )
            rounds.append(
                {
                    "round_id": current_id,
                    "title": document["title"],
                    "round_sha256": document["round_sha256"],
                    "contract_status": "MATCH" if not drift else "DRIFTED",
                    "contract_drift": drift,
                    "work_units": units,
                }
            )

        attempts: list[dict[str, Any]] = []
        for attempt in state["attempts"].values():
            if round_id is not None and attempt["round_id"] != round_id:
                continue
            round_document = state["rounds"][attempt["round_id"]]["definition"]
            attempt_for_status = copy.copy(attempt)
            attempt_for_status["_rerun_claims"] = state["rerun_claims"]
            attempts.append(
                {
                    "attempt_id": attempt["attempt_id"],
                    "round_id": attempt["round_id"],
                    "work_unit_id": attempt["work_unit_id"],
                    "author_operator_id": attempt["author_operator_id"],
                    "envelope_id": attempt["envelope_id"],
                    "enforcement_profile": state["work_envelopes"][attempt["envelope_id"]][
                        "enforcement_profile"
                    ],
                    "execution_receipt_sha256": (
                        attempt["execution_receipt"]["receipt_sha256"]
                        if attempt.get("execution_receipt")
                        else None
                    ),
                    "within_envelope": (
                        attempt["execution_receipt"]["within_envelope"]
                        if attempt.get("execution_receipt")
                        else None
                    ),
                    "stop_requested": attempt.get("stop_request") is not None,
                    "result_type": attempt["result"]["event_type"] if attempt["result"] else None,
                    "status": _attempt_gate_status(attempt_for_status, round_document),
                    "rerun_commitments": sum(
                        1
                        for claim_id in attempt["rerun_claim_ids"]
                        if state["rerun_claims"][claim_id].get("commitment_sha256")
                    ),
                    "annotations": sum(1 for row in state["annotations"] if row["attempt_id"] == attempt["attempt_id"]),
                }
            )

        negative_results = [
            {
                "attempt_id": attempt["attempt_id"],
                "classification": attempt["result"]["classification"],
                "reason_code": attempt["result"]["reason_code"],
                "hypothesis": attempt["result"]["hypothesis"],
                "evidence_package_sha256": attempt["result"]["evidence_package_sha256"],
            }
            for attempt in state["attempts"].values()
            if attempt["result"] and attempt["result"]["event_type"] == "NEGATIVE_RESULT_RECORDED"
            and (round_id is None or attempt["round_id"] == round_id)
        ]
        return {
            "schema_version": 1,
            "generated_at": utc_text(now),
            "ledger": self.ledger.verify(),
            "factory": state["factory"],
            "identity_assurance": "self-asserted-local",
            "identity_warning": "Distinct provider/subject records are enforced, but this local pilot does not prove distinct humans.",
            "operators": len(state["operators"]),
            "entry_gates_completed": len(state["entry_gates"]),
            "work_envelopes_issued": len(state["work_envelopes"]),
            "rounds": rounds,
            "attempts": attempts,
            "negative_results": negative_results,
        }

    def audit_blindness(self) -> dict[str, Any]:
        from .audit import audit_public_ledger_blindness

        return audit_public_ledger_blindness(self.events())
