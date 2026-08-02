from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .common import ControlPlaneError, canonical_json_bytes, sha256_bytes, utc_now, utc_text, write_json
from .workflow import ControlPlane, NEGATIVE_CLASSIFICATIONS


FACTORY_ROOT = Path(__file__).resolve().parents[1]


def _add_request_id(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--request-id", help="stable idempotency key for a retried command")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="factoryctl",
        description="Append-only Research Factory work and reproduction control plane",
    )
    parser.add_argument(
        "--ledger",
        type=Path,
        default=FACTORY_ROOT / "state" / "pilot_events.jsonl",
        help="canonical JSONL event ledger",
    )
    parser.add_argument(
        "--evidence-root",
        type=Path,
        default=FACTORY_ROOT / "state" / "private" / "evidence",
        help="private content-addressed evidence store",
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=FACTORY_ROOT / "state" / "public" / "artifacts",
        help="public content-addressed candidate packages for rerunners",
    )
    parser.add_argument(
        "--private-root",
        type=Path,
        default=FACTORY_ROOT / "state" / "private" / "rerun_results",
        help="evaluator-side sealed rerun conclusions",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="create the genesis event and local pilot administrator")
    init.add_argument("--factory-id", default="research-factory-local")
    init.add_argument("--admin-id", required=True)
    init.add_argument("--provider", required=True)
    init.add_argument("--subject", required=True)
    init.add_argument("--display-name", required=True)
    _add_request_id(init)

    check_in = sub.add_parser("check-in", help="register one human-owned operator identity")
    check_in.add_argument("--operator-id", required=True)
    check_in.add_argument("--provider", required=True)
    check_in.add_argument("--subject", required=True)
    check_in.add_argument("--display-name", required=True)
    _add_request_id(check_in)

    open_round = sub.add_parser("open-round", help="freeze and open a versioned round document")
    open_round.add_argument("--actor", required=True)
    open_round.add_argument("--config", type=Path, required=True)
    _add_request_id(open_round)

    entry = sub.add_parser(
        "complete-entry-gate",
        help="record the standard readiness run required before work or rerun claims",
    )
    entry.add_argument("--operator", required=True)
    entry.add_argument("--round", required=True, dest="round_id")
    entry.add_argument("--evidence", type=Path, required=True)
    _add_request_id(entry)

    claim = sub.add_parser("claim-work", help="lease one open work unit")
    claim.add_argument("--operator", required=True)
    claim.add_argument("--round", required=True, dest="round_id")
    claim.add_argument("--work-unit", required=True)
    _add_request_id(claim)

    start = sub.add_parser("start-attempt", help="start an immutable attempt under a work claim")
    start.add_argument("--operator", required=True)
    start.add_argument("--work-claim", required=True)
    start.add_argument("--attempt-id")
    _add_request_id(start)

    result = sub.add_parser("submit-result", help="seal a candidate result and open it for reruns")
    result.add_argument("--operator", required=True)
    result.add_argument("--attempt", required=True)
    result.add_argument("--evidence", type=Path, required=True)
    result.add_argument("--comparison", type=Path, required=True)
    result.add_argument(
        "--artifact-submission",
        type=Path,
        required=True,
        help="submission.json whose declared source files form the metric-free rerun package",
    )
    result.add_argument("--artifact-sha256", required=True)
    result.add_argument(
        "--kind",
        choices=["CANDIDATE"],
        default="CANDIDATE",
    )
    result.add_argument("--summary", required=True, help="public summary without hidden metrics")
    _add_request_id(result)

    negative = sub.add_parser(
        "record-negative-result",
        help="retain a failed hypothesis, boundary, no-gain result, or unrunnable path",
    )
    negative.add_argument("--operator", required=True)
    negative.add_argument("--attempt", required=True)
    negative.add_argument("--evidence", type=Path, required=True)
    negative.add_argument("--artifact-sha256", required=True)
    negative.add_argument("--classification", choices=sorted(NEGATIVE_CLASSIFICATIONS), required=True)
    negative.add_argument("--reason-code", required=True)
    negative.add_argument("--hypothesis", required=True)
    negative.add_argument("--summary", required=True)
    _add_request_id(negative)

    rerun_claim = sub.add_parser("claim-rerun", help="lease one blind rerun slot")
    rerun_claim.add_argument("--operator", required=True)
    rerun_claim.add_argument("--attempt", required=True)
    rerun_claim.add_argument(
        "--capability",
        required=True,
        help="client-generated random secret (32+ characters); save it for retries and submission",
    )
    rerun_claim.add_argument(
        "--declare-independent",
        action="store_true",
        help="declare no authorship, identity, collaboration, or result-sharing conflict for this assignment",
    )
    _add_request_id(rerun_claim)

    rerun_submit = sub.add_parser(
        "submit-rerun",
        help="commit a rerun without revealing its conclusion to the other worker",
    )
    rerun_submit.add_argument("--operator", required=True)
    rerun_submit.add_argument("--rerun-claim", required=True)
    rerun_submit.add_argument("--capability", required=True)
    rerun_submit.add_argument("--evidence", type=Path, required=True)
    _add_request_id(rerun_submit)

    evaluate = sub.add_parser(
        "evaluate-reruns",
        help="reveal committed reruns to the evaluator and append only a coarse gate",
    )
    evaluate.add_argument("--actor", required=True)
    evaluate.add_argument("--attempt", required=True)
    _add_request_id(evaluate)

    holdout_job = sub.add_parser(
        "record-holdout-job",
        help="verify and record a signed post-rerun one-shot holdout job token",
    )
    holdout_job.add_argument("--actor", required=True)
    holdout_job.add_argument("--attempt", required=True)
    holdout_job.add_argument("--token", type=Path, required=True)
    _add_request_id(holdout_job)

    holdout = sub.add_parser(
        "record-holdout-attestation",
        help="verify and join a signed blind holdout verdict after the two-person gate",
    )
    holdout.add_argument("--actor", required=True)
    holdout.add_argument("--attempt", required=True)
    holdout.add_argument("--attestation", type=Path, required=True)
    _add_request_id(holdout)

    escalate = sub.add_parser("escalate-dispute", help="preserve and escalate conflicting evidence")
    escalate.add_argument("--actor", required=True)
    escalate.add_argument("--attempt", required=True)
    escalate.add_argument("--reason", required=True)
    _add_request_id(escalate)

    annotate = sub.add_parser("annotate-attempt", help="append a correction, note, or divergence finding")
    annotate.add_argument("--actor", required=True)
    annotate.add_argument("--attempt", required=True)
    annotate.add_argument("--note", required=True)
    annotate.add_argument("--evidence", type=Path)
    _add_request_id(annotate)

    status = sub.add_parser("status", help="show the rebuildable materialized factory view")
    status.add_argument("--round", dest="round_id")
    status.add_argument("--json", action="store_true")

    sub.add_parser("verify-ledger", help="verify every sequence and hash-chain link")

    export = sub.add_parser("export-artifact", help="export a verified metric-free candidate package")
    export.add_argument("--package-sha256", required=True)
    export.add_argument("--output", type=Path, required=True)

    checkpoint = sub.add_parser("checkpoint", help="write the current ledger head for external anchoring")
    checkpoint.add_argument("--output", type=Path, required=True)
    checkpoint.add_argument("--label", default="manual-checkpoint")
    return parser


def _human_status(snapshot: dict[str, Any]) -> str:
    lines = [
        f"Ledger: {snapshot['ledger']['events']} events; head {snapshot['ledger']['head_event_sha256']}",
        f"Operators: {snapshot['operators']} ({snapshot['identity_assurance']})",
    ]
    for round_row in snapshot["rounds"]:
        counts: dict[str, int] = {}
        for unit in round_row["work_units"]:
            counts[unit["status"]] = counts.get(unit["status"], 0) + 1
        rendered = ", ".join(f"{key.lower()}={value}" for key, value in sorted(counts.items()))
        lines.append(
            f"{round_row['round_id']}: contracts={round_row['contract_status']}; {rendered}"
        )
    for attempt in snapshot["attempts"]:
        lines.append(
            f"{attempt['attempt_id']}: {attempt['status']} "
            f"(rerun commitments={attempt['rerun_commitments']})"
        )
    if snapshot["negative_results"]:
        lines.append(f"Retained negative results: {len(snapshot['negative_results'])}")
    lines.append(snapshot["identity_warning"])
    return "\n".join(lines)


def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def run(args: argparse.Namespace) -> int:
    plane = ControlPlane(
        args.ledger,
        factory_root=FACTORY_ROOT,
        evidence_root=args.evidence_root,
        artifact_root=args.artifact_root,
        private_root=args.private_root,
    )
    command = args.command
    if command == "init":
        value = plane.initialize(
            factory_id=args.factory_id,
            admin_id=args.admin_id,
            provider=args.provider,
            subject=args.subject,
            display_name=args.display_name,
            request_id=args.request_id,
        )
    elif command == "check-in":
        value = plane.check_in(
            operator_id=args.operator_id,
            provider=args.provider,
            subject=args.subject,
            display_name=args.display_name,
            request_id=args.request_id,
        )
    elif command == "open-round":
        value = plane.open_round(actor_id=args.actor, round_path=args.config, request_id=args.request_id)
    elif command == "complete-entry-gate":
        value = plane.complete_entry_gate(
            operator_id=args.operator,
            round_id=args.round_id,
            evidence_path=args.evidence,
            request_id=args.request_id,
        )
    elif command == "claim-work":
        value = plane.claim_work(
            operator_id=args.operator,
            round_id=args.round_id,
            work_unit_id=args.work_unit,
            request_id=args.request_id,
        )
    elif command == "start-attempt":
        value = plane.start_attempt(
            operator_id=args.operator,
            work_claim_id=args.work_claim,
            attempt_id=args.attempt_id,
            request_id=args.request_id,
        )
    elif command == "submit-result":
        value = plane.submit_result(
            operator_id=args.operator,
            attempt_id=args.attempt,
            evidence_path=args.evidence,
            comparison_path=args.comparison,
            candidate_submission_path=args.artifact_submission,
            candidate_artifact_sha256=args.artifact_sha256,
            result_kind=args.kind,
            public_summary=args.summary,
            request_id=args.request_id,
        )
    elif command == "record-negative-result":
        value = plane.record_negative(
            operator_id=args.operator,
            attempt_id=args.attempt,
            evidence_path=args.evidence,
            candidate_artifact_sha256=args.artifact_sha256,
            classification=args.classification,
            reason_code=args.reason_code,
            hypothesis=args.hypothesis,
            public_summary=args.summary,
            request_id=args.request_id,
        )
    elif command == "claim-rerun":
        value = plane.claim_rerun(
            operator_id=args.operator,
            attempt_id=args.attempt,
            capability=args.capability,
            conflict_declaration=args.declare_independent,
            request_id=args.request_id,
        )
    elif command == "submit-rerun":
        value = plane.submit_rerun(
            operator_id=args.operator,
            rerun_claim_id=args.rerun_claim,
            capability=args.capability,
            evidence_path=args.evidence,
            request_id=args.request_id,
        )
    elif command == "evaluate-reruns":
        value = plane.evaluate_reruns(
            actor_id=args.actor,
            attempt_id=args.attempt,
            request_id=args.request_id,
        )
    elif command == "record-holdout-job":
        value = plane.record_holdout_job(
            actor_id=args.actor,
            attempt_id=args.attempt,
            token_path=args.token,
            request_id=args.request_id,
        )
    elif command == "record-holdout-attestation":
        value = plane.record_holdout_attestation(
            actor_id=args.actor,
            attempt_id=args.attempt,
            attestation_path=args.attestation,
            request_id=args.request_id,
        )
    elif command == "escalate-dispute":
        value = plane.escalate_dispute(
            actor_id=args.actor,
            attempt_id=args.attempt,
            reason=args.reason,
            request_id=args.request_id,
        )
    elif command == "annotate-attempt":
        value = plane.annotate_attempt(
            actor_id=args.actor,
            attempt_id=args.attempt,
            note=args.note,
            evidence_path=args.evidence,
            request_id=args.request_id,
        )
    elif command == "status":
        value = plane.snapshot(round_id=args.round_id)
        if not args.json:
            print(_human_status(value))
            return 0
    elif command == "verify-ledger":
        value = plane.ledger.verify()
    elif command == "export-artifact":
        value = plane.artifacts.export(args.package_sha256, args.output)
    elif command == "checkpoint":
        verified = plane.ledger.verify()
        state = plane.state()
        unsigned = {
            "schema_version": 1,
            "checkpoint_type": "research_factory_ledger_head",
            "label": args.label,
            "generated_at": utc_text(utc_now()),
            "factory_id": state["factory"]["factory_id"] if state["factory"] else None,
            "ledger_name": args.ledger.name,
            "events": verified["events"],
            "head_event_sha256": verified["head_event_sha256"],
        }
        value = {
            **unsigned,
            "checkpoint_sha256": sha256_bytes(canonical_json_bytes(unsigned)),
        }
        write_json(args.output, value)
        value = {**value, "checkpoint": str(args.output.resolve())}
    else:
        raise AssertionError(f"unhandled command {command}")
    _print(value)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except ControlPlaneError as exc:
        print(f"factoryctl: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
