"""Local construction shifts over existing, reviewed fixture packet adapters.

Not a work-order scheduler, identity service, sandbox or research state machine.
Closed shifts are immutable snapshots; portable packages are the handover unit.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import math
import os
from pathlib import Path
import re
import shutil
from typing import Any
import uuid

from control_plane.common import ContractError, canonical_json_bytes, sha256_bytes, sha256_file
from shift_reports.validate_shift_reports import canonical_report_hash, verify_reports
from .environments import LEGACY_PROFILE, RESEARCH_PROFILE, check_runtime, profiles
from .fixture_packets import FixturePacketController
from .portable import PortableEvidencePackage, _is_link_like, _load_json_strict

BOUNDARY = {
    "scientific_evidence": False, "counts_as_independent_reproduction": False,
    "eligible_for_promotion": False, "live_research_authorized": False,
    "proves_human_identity": False, "proves_process_isolation": False,
    "changes_governed_work_order": False,
}
OUTCOMES = ("PROGRESS", "NO_GAIN", "BLOCKED", "UNRUNNABLE")
MAX_HISTORY = 16
MAX_ENTRIES = 10000
MAX_BYTES = 64 * 1024 * 1024
SESSION_KEYS = {
    "format", "session_id", "work_order_id", "operator", "workbench", "started_at",
    "adapter_sha256", "contract_sha256", "environment", "previous_package_sha256",
    "boundary", "sha256",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def timestamp(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ContractError("shift timestamps must be UTC ending in Z")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError("invalid shift timestamp") from exc


def closed(value: dict, keys: set[str], label: str) -> None:
    if set(value) != keys:
        raise ContractError(f"{label} fields differ from the closed format")


def sealed(value: dict) -> dict:
    return {**value, "sha256": sha256_bytes(canonical_json_bytes(value))}


def verify_hash(value: dict) -> None:
    if value.get("sha256") != sealed({k: v for k, v in value.items() if k != "sha256"})["sha256"]:
        raise ContractError("shift record hash mismatch")


def safe_path(path: Path) -> Path:
    # Check before resolve(), including all parents (Windows junctions too).
    absolute = Path(os.path.abspath(path))
    for part in [absolute, *absolute.parents]:
        if _is_link_like(part):
            raise ContractError("shift paths cannot use symbolic links or junctions")
    return absolute


def write_new(path: Path, value: dict) -> None:
    with path.open("xb") as stream:
        stream.write(canonical_json_bytes(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())


def inventory(root: Path, *, omit_close: bool = False) -> list[dict]:
    files = []
    total = 0
    for count, path in enumerate(root.rglob("*"), 1):
        if count > MAX_ENTRIES:
            raise ContractError("shift exceeds entry limit")
        if _is_link_like(path):
            raise ContractError("shift contents cannot contain links or junctions")
        if not path.is_file():
            if not path.is_dir():
                raise ContractError("shift contains a non-regular entry")
            continue
        if path.stat().st_nlink != 1:
            raise ContractError("shift contents cannot contain hard links")
        relative = path.relative_to(root).as_posix()
        if omit_close and relative == "close.json":
            continue
        size = path.stat().st_size
        total += size
        if total > MAX_BYTES:
            raise ContractError("shift exceeds 64 MiB handover limit")
        files.append({"path": relative, "bytes": size, "sha256": sha256_file(path)})
    return sorted(files, key=lambda item: item["path"])


@contextmanager
def session_lock(root: Path):
    # OS-owned lock: released on exit/crash, unlike stale PID lock directories.
    # This coordinates cooperative commands on one local filesystem only.
    lock = safe_path(root / ".lock")
    if not lock.is_file() or lock.read_bytes() != b"0" or lock.stat().st_nlink != 1:
        raise ContractError("missing or invalid local shift lock")
    with lock.open("r+b") as stream:
        # Reserve a byte well beyond EOF: Windows rejects a read whose requested
        # buffer overlaps a lock, even if the read would end at EOF first.
        # Seeking/locking does not extend this one-byte file.
        stream.seek(1 << 30)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ContractError("shift is busy in another process; retry after it stops") from exc
        try:
            yield
        finally:
            stream.seek(1 << 30)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


class ShiftWorkflow:
    def __init__(self, factory_root: Path):
        self.factory_root = factory_root.resolve()
        self.portable = PortableEvidencePackage(self.factory_root)

    def tasks(self) -> dict:
        controller = FixturePacketController(self.factory_root)
        return {
            "tasks": [{**row, "required_environment": RESEARCH_PROFILE,
                       "actions": ["build", "verify", "rehearse"]} for row in controller.list()],
            "boundary": dict(BOUNDARY),
            "notice": "Available fixtures, not exclusive claims or live research jobs.",
        }

    def start(self, *, output: Path, operator: str, workbench: str | None = None,
              previous: Path | None = None) -> dict:
        if not re.fullmatch(r"demo:[A-Za-z0-9][A-Za-z0-9._:-]{0,149}", operator):
            raise ContractError("local fixture shifts require a demo: operator label, not identity proof")
        root = safe_path(output)
        if root.exists():
            raise ContractError("shift destination already exists; use a fresh directory")
        parent = None
        prior = None
        if previous is not None:
            previous = safe_path(previous)
            if root.is_relative_to(previous):
                raise ContractError("new shift must be outside its handover package")
            parent = self.verify_handover(previous)
            prior = parent["shift"]
            if prior["session"]["environment"]["environment_id"] != RESEARCH_PROFILE:
                raise ContractError("historical environment cannot be resumed; retain it and start a new task")
            if not parent["package"]["current_contract_match"] or not prior["current_adapter_match"]:
                raise ContractError("historical handover differs from current contract/adapter; review before starting new work")
            if prior["report_count"] >= MAX_HISTORY:
                raise ContractError("handover chain limit reached; retain this history and start a new local task")
            workbench = prior["session"]["workbench"]
        if not workbench:
            raise ContractError("start requires --workbench")
        controller = FixturePacketController(self.factory_root)
        adapter = controller._adapter(workbench)
        row = controller.catalogue.resolve(adapter.workbench_code)
        session = sealed({
            "format": "FACTORY_LOCAL_SHIFT_V1", "session_id": uuid.uuid4().hex,
            "work_order_id": prior["session"]["work_order_id"] if prior else "WO-" + uuid.uuid4().hex[:12].upper(),
            "operator": operator, "workbench": adapter.workbench_code, "started_at": now(),
            "adapter_sha256": adapter.adapter_sha256, "contract_sha256": row["contract_sha256"],
            "environment": check_runtime(self.factory_root, RESEARCH_PROFILE),
            "previous_package_sha256": parent["package"]["package_sha256"] if parent else None,
            "boundary": dict(BOUNDARY),
        })
        root.mkdir(parents=True, exist_ok=False)
        (root / ".lock").write_bytes(b"0")
        if previous is not None:
            shutil.copytree(previous, root / "previous")
            # Reject source changes during copying before committing the session.
            copied = self.verify_handover(root / "previous")
            if copied["package"]["package_sha256"] != session["previous_package_sha256"]:
                raise ContractError("handover changed while being copied")
        write_new(root / "session.json", session)
        return self.inspect(root)

    def inspect(self, root: Path, *, depth: int = 0) -> dict:
        if depth >= MAX_HISTORY:
            raise ContractError("handover history exceeds limit")
        root = safe_path(root)
        if not root.is_dir():
            raise ContractError("shift directory does not exist")
        inventory(root)
        top = {p.name for p in root.iterdir()}
        if not {".lock", "session.json"} <= top or top - {".lock", "session.json", "previous", "run", "close.json"}:
            raise ContractError("unexpected or missing shift contents")
        if (root / ".lock").read_bytes() != b"0":
            raise ContractError("invalid shift lock contents")
        session = _load_json_strict(root / "session.json")
        closed(session, SESSION_KEYS, "session")
        verify_hash(session)
        if session["format"] != "FACTORY_LOCAL_SHIFT_V1" or canonical_json_bytes(session["boundary"]) != canonical_json_bytes(BOUNDARY):
            raise ContractError("shift exceeds construction boundary")
        if not re.fullmatch(r"[0-9a-f]{32}", session["session_id"]) or not re.fullmatch(r"WO-[A-F0-9]{12}", session["work_order_id"]):
            raise ContractError("invalid local shift identity")
        if not re.fullmatch(r"demo:[A-Za-z0-9][A-Za-z0-9._:-]{0,149}", session["operator"]):
            raise ContractError("invalid demo operator")
        timestamp(session["started_at"])
        if not isinstance(session["environment"], dict) or session["environment"].get("environment_id") not in {LEGACY_PROFILE, RESEARCH_PROFILE}:
            raise ContractError("shift environment profile differs")
        _, registered = profiles(self.factory_root)
        recorded = session["environment"]
        profile = registered[recorded["environment_id"]]
        if recorded.get("lock_sha256") != profile["lock"]["sha256"] or recorded.get("manifest_sha256") != profile["manifest_sha256"]:
            raise ContractError("shift environment commitment differs")
        if type(session["environment"].get("matches")) is not bool:
            raise ContractError("invalid recorded environment match")
        for key in ("adapter_sha256", "contract_sha256"):
            if not isinstance(session[key], str) or not re.fullmatch(r"[0-9a-f]{64}", session[key]):
                raise ContractError("invalid locked work hash")
        row = self.portable.catalogue.resolve(session["workbench"])
        controller = FixturePacketController(self.factory_root)
        current = controller.adapters.get(session["workbench"])
        adapter_match = current is not None and current.adapter_sha256 == session["adapter_sha256"]
        reports = []
        if session["previous_package_sha256"] is not None:
            prior = self.verify_handover(root / "previous", depth=depth + 1)
            if prior["package"]["package_sha256"] != session["previous_package_sha256"]:
                raise ContractError("previous package commitment differs")
            previous_session = prior["shift"]["session"]
            if any(previous_session[k] != session[k] for k in ("work_order_id", "workbench", "contract_sha256", "adapter_sha256")):
                raise ContractError("resumed task identity or locked work changed")
            reports = prior["shift"]["reports"]
            if timestamp(session["started_at"]) < timestamp(reports[-1]["createdAt"]):
                raise ContractError("resumed shift predates prior clock-out")
        elif "previous" in top:
            raise ContractError("uncommitted prior handover")
        run_state = "NOT_RUN"
        run_error = None
        if "run" in top:
            if not (root / "run").is_dir() or {p.name for p in (root / "run").iterdir()} - {
                "intent.json", "result.json", "build.json", "verify.json", "rehearse.json", "packet", "rehearsal.json"
            }:
                raise ContractError("unexpected fixture run contents")
            intent = _load_json_strict(root / "run" / "intent.json")
            closed(intent, {"session_sha256", "started_at", "sha256"}, "run intent")
            verify_hash(intent)
            if intent["session_sha256"] != session["sha256"]:
                raise ContractError("run belongs to another shift")
            if timestamp(intent["started_at"]) < timestamp(session["started_at"]):
                raise ContractError("run predates clock-in")
            run_state = "INTERRUPTED_OR_RUNNING"
            if (root / "run" / "result.json").exists():
                result = _load_json_strict(root / "run" / "result.json")
                closed(result, {"intent_sha256", "status", "finished_at", "error", "steps", "sha256"}, "run result")
                verify_hash(result)
                if result["intent_sha256"] != intent["sha256"] or result["status"] not in {"PASSED", "UNRUNNABLE"}:
                    raise ContractError("invalid run result binding/status")
                steps = result["steps"]
                order = ["build", "verify", "rehearse"]
                if (not isinstance(steps, list) or steps != order[:len(steps)]
                        or (result["status"] == "PASSED" and (steps != order or result["error"] is not None))
                        or (result["status"] == "UNRUNNABLE" and (not isinstance(result["error"], str) or not result["error"]))):
                    raise ContractError("inconsistent fixture run steps/outcome")
                if timestamp(result["finished_at"]) < timestamp(intent["started_at"]):
                    raise ContractError("run finish predates start")
                for step in steps:
                    response = _load_json_strict(root / "run" / f"{step}.json")
                    if (not isinstance(response.get("adapter"), dict) or response.get("action") != step.upper()
                            or response.get("adapter", {}).get("adapter_sha256") != session["adapter_sha256"]):
                        raise ContractError("fixture response differs from locked adapter/action")
                run_state = result["status"]
                run_error = result["error"]
        if "close.json" in top:
            closing = _load_json_strict(root / "close.json")
            closed(closing, {"session_sha256", "run_state", "report", "files", "sha256"}, "clock-out")
            verify_hash(closing)
            if closing["session_sha256"] != session["sha256"] or closing["run_state"] != run_state:
                raise ContractError("clock-out binding differs")
            if closing["files"] != inventory(root, omit_close=True):
                raise ContractError("closed shift artifacts changed, missing or added")
            report = closing["report"]
            if not isinstance(report, dict):
                raise ContractError("clock-out report must be an object")
            if run_state in {"UNRUNNABLE", "INTERRUPTED_OR_RUNNING"} and report.get("outcomeClass") not in {"UNRUNNABLE", "BLOCKED"}:
                raise ContractError("clock-out disguises failed/interrupted execution")
            if (report["workOrderId"] != session["work_order_id"] or report["workbenchId"] != row["numeric_id"]
                    or report["reporter"] != {"actorUserId": session["operator"], "actorDisplay": session["operator"], "identityAssurance": "LOCAL_PREVIEW"}
                    or report["shift"]["startedAt"] != session["started_at"]
                    or report["mode"] != "HANGAR_CONSTRUCTION"
                    or report["workOrderSnapshot"] != {"status": "CLAIMED", "revision": 0}
                    or report["artifactReferences"]):
                raise ContractError("clock-out report differs from local shift")
            reports = [*reports, report]
            try:
                verify_reports(reports)
            except ValueError as exc:
                raise ContractError(str(exc)) from exc
            if (root / "run" / "result.json").exists() and timestamp(report["shift"]["endedAt"]) < timestamp(result["finished_at"]):
                raise ContractError("clock-out predates recorded completion")
        return {
            "session": session, "state": "CLOSED" if "close.json" in top else "OPEN",
            "run_state": run_state, "run_error": run_error, "reports": reports, "report_count": len(reports),
            "current_contract_match": row["contract_sha256"] == session["contract_sha256"],
            "current_adapter_match": adapter_match, "boundary": dict(BOUNDARY),
            "path": str(root),
        }

    def run(self, root: Path) -> dict:
        root = safe_path(root)
        with session_lock(root):
            view = self.inspect(root)
            if view["state"] != "OPEN" or view["run_state"] != "NOT_RUN":
                raise ContractError("shift already ran/closed; retain it and resume into a new directory")
            if not view["current_contract_match"] or not view["current_adapter_match"]:
                raise ContractError("locked work changed; review before running")
            session = view["session"]
            if session["environment"]["environment_id"] != RESEARCH_PROFILE:
                raise ContractError("historical environment cannot execute in the replacement")
            run = root / "run"
            run.mkdir()
            intent = sealed({"session_sha256": session["sha256"], "started_at": now()})
            write_new(run / "intent.json", intent)
            controller = FixturePacketController(self.factory_root)
            steps = []
            error = None
            try:
                for action in ("build", "verify", "rehearse"):
                    kwargs: dict[str, Any] = {"workbench": session["workbench"]}
                    if action == "build":
                        kwargs["output"] = run / "packet"
                    else:
                        kwargs["package"] = run / "packet"
                    if action == "rehearse":
                        kwargs.update(output=run / "rehearsal.json", operator_id=session["operator"])
                    value = controller.execute(action, **kwargs)
                    write_new(run / f"{action}.json", value)
                    steps.append(action)
            except (ValueError, ContractError, OSError) as exc:
                error = f"{type(exc).__name__}: {exc}"[:1500]
            write_new(run / "result.json", sealed({
                "intent_sha256": intent["sha256"], "status": "UNRUNNABLE" if error else "PASSED",
                "finished_at": now(), "error": error, "steps": steps,
            }))
            return self.inspect(root)

    def finish(self, root: Path, *, outcome: str, summary: str, next_lead: str,
               blocker: str | None = None, ended_at: str | None = None) -> dict:
        if outcome not in OUTCOMES or not all(isinstance(s, str) and 3 <= len(s.strip()) <= 500 for s in (summary, next_lead)):
            raise ContractError("choose a valid outcome and 3–500 character summary/next lead")
        if outcome in {"BLOCKED", "UNRUNNABLE"} and (not blocker or not 3 <= len(blocker.strip()) <= 500):
            raise ContractError("BLOCKED/UNRUNNABLE requires a 3–500 character blocker")
        if blocker and not 3 <= len(blocker.strip()) <= 500:
            raise ContractError("blocker must contain 3–500 characters")
        root = safe_path(root)
        with session_lock(root):
            view = self.inspect(root)
            if view["state"] != "OPEN":
                raise ContractError("shift already closed; clock-out is immutable")
            session = view["session"]
            created_at = now()
            end = ended_at or created_at
            elapsed = (timestamp(end) - timestamp(session["started_at"])).total_seconds()
            if elapsed < 0 or elapsed > 86400 or timestamp(end) > timestamp(created_at):
                raise ContractError("shift interval must be 0–24 hours; use --ended-at for an honestly recorded earlier finish")
            if view["run_state"] in {"UNRUNNABLE", "INTERRUPTED_OR_RUNNING"} and outcome not in {"UNRUNNABLE", "BLOCKED"}:
                raise ContractError("failed/interrupted execution must be retained as BLOCKED or UNRUNNABLE")
            if (root / "run" / "result.json").exists():
                result = _load_json_strict(root / "run" / "result.json")
                if timestamp(end) < timestamp(result["finished_at"]):
                    raise ContractError("clock-out cannot predate recorded run completion")
            reports = view["reports"]
            report = {
                "schemaVersion": 1, "reportId": "SR-" + uuid.uuid4().hex[:12].upper(),
                "workOrderId": session["work_order_id"], "reportSequence": len(reports) + 1,
                "previousReportSha256": reports[-1]["reportSha256"] if reports else None,
                "reportSha256": "", "workbenchId": int(session["workbench"][3:]),
                "mode": "HANGAR_CONSTRUCTION", "workOrderSnapshot": {"status": "CLAIMED", "revision": 0},
                "outcomeClass": outcome,
                "shift": {"startedAt": session["started_at"], "endedAt": end, "durationMinutes": math.ceil(elapsed / 60)},
                "attemptedWork": [{"approach": "Inspect or run the registered known-answer fixture.", "result": summary.strip(), "decision": "PAUSE"}],
                "observations": [summary.strip(), f"Recorded fixture execution state: {view['run_state']}. No scientific credit."],
                "artifactReferences": [],
                "blockers": [{"category": "OTHER", "description": blocker.strip(), "retryCondition": next_lead.strip()}] if blocker else [],
                "nextLeads": [{"lead": next_lead.strip(), "rationale": "Operator-proposed next step; not a scientific conclusion."}],
                "reporter": {"actorUserId": session["operator"], "actorDisplay": session["operator"], "identityAssurance": "LOCAL_PREVIEW"},
                "boundary": {"scope": "HANGAR_OPERATIONS_ONLY", "scientificEvidence": False,
                             "countsAsIndependentReproduction": False, "eligibleForPromotion": False,
                             "closesWorkOrder": False, "operationalRecordOnly": True},
                "createdAt": created_at,
            }
            report["reportSha256"] = canonical_report_hash(report)
            verify_reports([*reports, report])
            write_new(root / "close.json", sealed({
                "session_sha256": session["sha256"], "run_state": view["run_state"],
                "report": report, "files": inventory(root),
            }))
            return self.inspect(root)

    def export(self, root: Path, output: Path) -> dict:
        root, output = safe_path(root), safe_path(output)
        with session_lock(root):
            view = self.inspect(root)
            if view["state"] != "CLOSED":
                raise ContractError("clock out before exporting a handover")
            if not view["current_contract_match"] or not view["current_adapter_match"]:
                raise ContractError("cannot relabel historical work with a current contract")
            session = view["session"]
            result = self.portable.create(
                workbench=session["workbench"], attempt_id=f"shift:{session['session_id']}",
                operator_id=session["operator"], operating_mode="HANGAR_CONSTRUCTION", evidence_kind="SHIFT_REPORT",
                summary="Local construction shift handover; no scientific or independent reproduction standing.",
                commands=[f"enginectl.py shift export --session {root} --output {output}"],
                seeds=[], stochastic=False, source=root, output=output,
            )
            self.verify_handover(output)
            return result

    def verify_handover(self, package: Path, *, depth: int = 0) -> dict:
        package = safe_path(package)
        inventory(package)
        verification = self.portable.verify(package)
        if verification["evidence_kind"] != "SHIFT_REPORT" or verification["operating_mode"] != "HANGAR_CONSTRUCTION":
            raise ContractError("package is not a construction shift handover")
        shift = self.inspect(package / "evidence" / "files", depth=depth)
        envelope = _load_json_strict(package / "package.json")
        if (shift["state"] != "CLOSED" or verification["attempt_id"] != f"shift:{shift['session']['session_id']}"
                or verification["workbench_code"] != shift["session"]["workbench"]
                or envelope["accountable_human"]["operator_id"] != shift["session"]["operator"]
                or envelope["workbench"]["contract_sha256"] != shift["session"]["contract_sha256"]):
            raise ContractError("handover envelope differs from closed shift")
        return {"package": verification, "shift": shift}


def display(view: dict) -> str:
    if "tasks" in view:
        return "\n".join(["AVAILABLE CONSTRUCTION FIXTURES (not exclusive claims)", *[
            f"{task['workbench_code']}  {task['title']}" for task in view["tasks"]],
            f"Required execution environment: {RESEARCH_PROFILE}", "Start with: shift start --workbench WB-013 --operator demo:you --output <new-directory>"])
    if "shift" in view:
        return "HANDOVER VERIFIED\n" + display(view["shift"])
    if "session" not in view:
        return f"HANDOVER EXPORTED\n{view['path']}\nPackage SHA-256: {view['package_sha256']}\nScientific standing: NONE"
    session = view["session"]
    lines = [f"SHIFT {view['state']} | {session['workbench']} | {session['operator']}",
             f"Fixture: {view['run_state']}; retained reports: {view['report_count']}",
             f"Environment matched at clock-in: {session['environment']['matches']}",
             f"Current contract/adapter: {view['current_contract_match']}/{view['current_adapter_match']}"]
    if view["run_error"]:
        lines.append(f"Run error: {view['run_error']}")
    for name, mismatch in session["environment"].get("mismatches", {}).items():
        lines.append(f"Environment: {name} expected {mismatch['expected']}, observed {mismatch['observed']}")
    for report in view["reports"]:
        lines.extend([f"#{report['reportSequence']} {report['outcomeClass']}: {report['attemptedWork'][0]['result']}",
                      *[f"Blocker: {blocker['description']}" for blocker in report["blockers"]],
                      *[f"Next: {lead['lead']}" for lead in report["nextLeads"]]])
    lines.append("Scientific standing: NONE; demo labels do not prove different humans.")
    return "\n".join(lines)
