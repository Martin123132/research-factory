from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from control_plane import cli as governed_cli
from control_plane.common import ControlPlaneError
from control_plane.workflow import NEGATIVE_CLASSIFICATIONS
from corrections.ledger import (
    ALL_STANDINGS,
    ARTIFACT_CLASSES,
    CorrectionLedger,
    load_json_strict as load_correction_draft,
)
from quality.verify_quality import verify as verify_factory_quality

from .catalogue import PROFILES, STAGES, StationCatalogue, doctor
from .negative_results import search_ledger
from .portable import EVIDENCE_KINDS, OPERATING_MODES, PortableEvidencePackage


FACTORY_ROOT = Path(__file__).resolve().parents[1]
LOCAL_COMMANDS = {
    "doctor",
    "quality",
    "list",
    "inspect",
    "package",
    "verify",
    "negative-results",
    "correction-append",
    "correction-verify",
    "correction-history",
    "correction-export",
}
GLOBAL_VALUE_OPTIONS = {
    "--factory-root",
    "--ledger",
    "--evidence-root",
    "--artifact-root",
    "--private-root",
}


def _json(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def _selected_command(argv: list[str]) -> str | None:
    """Return the first command token while skipping global option values."""

    skip_value = False
    for token in argv:
        if skip_value:
            skip_value = False
            continue
        if token in GLOBAL_VALUE_OPTIONS:
            skip_value = True
            continue
        if any(token.startswith(f"{option}=") for option in GLOBAL_VALUE_OPTIONS):
            continue
        if token.startswith("-"):
            continue
        return token
    return None


def _print_help() -> None:
    print(
        """Research Factory local-first engine

usage: factoryctl [GLOBAL OPTIONS] COMMAND [COMMAND OPTIONS]

Explore and verify the factory (no account, website, network, or AI provider required):
  doctor                 verify the engine, 100-station registry, and station kits
  quality                verify the evidence-bound Open Factory quality profile
  list                   discover workbenches and filter by readiness
  inspect                read one station's objective, gates, and current limits
  package                make a portable, hash-bound construction evidence bundle
  verify                 verify a portable evidence bundle without trusting its author
  negative-results       search retained failed and no-gain experiments read-only
  correction-append      append one closed correction or retraction record
  correction-verify      verify the universal correction ledger and current standings
  correction-history     search original and current artifact standing read-only
  correction-export      export a read-only public correction index for adapters

Governed append-only lifecycle:
  init, check-in, open-round, complete-entry-gate, claim-work,
  issue-work-envelope, start-attempt, execute-attempt, request-stop,
  terminate-attempt, submit-result, record-negative-result, claim-rerun, submit-rerun,
  evaluate-reruns, record-holdout-job, record-holdout-attestation,
  escalate-dispute, annotate-attempt, status, verify-ledger, audit-blindness, export-artifact,
  checkpoint

Run `factoryctl COMMAND --help` for command options. The governed commands retain
their existing ledger and evidence-store behaviour; this front door does not create
a second workflow or make portable packages scientific evidence.
"""
    )


def build_local_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="factoryctl",
        description="Provider-neutral discovery and portable evidence tools",
    )
    parser.add_argument(
        "--factory-root",
        type=Path,
        default=FACTORY_ROOT,
        help="factory directory containing station_kits and workbench_standard",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    doctor_parser = sub.add_parser("doctor", help="verify a clean clone and its catalogue")
    doctor_parser.add_argument(
        "--ledger",
        type=Path,
        help="optionally verify an existing append-only ledger",
    )
    doctor_parser.add_argument("--json", action="store_true")

    quality_parser = sub.add_parser(
        "quality",
        help="verify the non-compensating Open Factory quality profile",
    )
    quality_parser.add_argument("--json", action="store_true")

    list_parser = sub.add_parser("list", help="list the verified 100-station catalogue")
    list_parser.add_argument("--stage", type=str.upper, choices=sorted(STAGES))
    list_parser.add_argument("--profile", type=str.upper, choices=sorted(PROFILES))
    list_parser.add_argument("--lane")
    list_parser.add_argument(
        "--entry-ready",
        action="store_true",
        help="show only stations with a runnable known-answer entry gate",
    )
    list_parser.add_argument("--json", action="store_true")

    inspect_parser = sub.add_parser("inspect", help="inspect one verified station contract")
    inspect_parser.add_argument("workbench", help="number, WB code, or station slug")
    inspect_parser.add_argument("--json", action="store_true")

    package_parser = sub.add_parser(
        "package",
        help="package local construction evidence with hashes and an embedded contract",
    )
    package_parser.add_argument("--workbench", required=True)
    package_parser.add_argument("--attempt", required=True)
    package_parser.add_argument("--operator", required=True)
    package_parser.add_argument(
        "--mode",
        type=str.upper,
        choices=sorted(OPERATING_MODES),
        default="HANGAR_CONSTRUCTION",
    )
    package_parser.add_argument(
        "--kind",
        type=str.upper,
        choices=sorted(EVIDENCE_KINDS),
        default="CONSTRUCTION",
    )
    package_parser.add_argument("--summary", required=True)
    package_parser.add_argument(
        "--command",
        action="append",
        required=True,
        dest="commands",
        help="exact command used; repeat for multiple commands",
    )
    package_parser.add_argument(
        "--seed",
        action="append",
        default=[],
        dest="seeds",
        help="recorded random seed; repeat for multiple seeds",
    )
    package_parser.add_argument("--stochastic", action="store_true")
    package_parser.add_argument("--source", type=Path, required=True)
    package_parser.add_argument("--output", type=Path, required=True)
    package_parser.add_argument("--json", action="store_true")

    verify_parser = sub.add_parser("verify", help="verify a portable evidence package")
    verify_parser.add_argument("package", type=Path)
    verify_parser.add_argument("--json", action="store_true")

    negative_parser = sub.add_parser(
        "negative-results",
        help="search the public index of retained failed and no-gain experiments",
    )
    negative_parser.add_argument(
        "--ledger",
        type=Path,
        required=True,
        help="append-only governed ledger to verify and search",
    )
    negative_parser.add_argument("--query", help="case-insensitive words matched across public fields")
    negative_parser.add_argument("--round", dest="round_id")
    negative_parser.add_argument("--work-unit", dest="work_unit_id")
    negative_parser.add_argument(
        "--classification",
        type=str.upper,
        choices=sorted(NEGATIVE_CLASSIFICATIONS),
    )
    negative_parser.add_argument("--reason-code")
    negative_parser.add_argument("--limit", type=int, default=50)
    negative_parser.add_argument("--json", action="store_true")

    correction_append = sub.add_parser(
        "correction-append",
        help="append a hash-linked public-artifact correction or retraction",
    )
    correction_append.add_argument("--ledger", type=Path, required=True)
    correction_append.add_argument("--draft", type=Path, required=True)
    correction_append.add_argument("--json", action="store_true")

    correction_verify = sub.add_parser(
        "correction-verify",
        help="verify an append-only correction ledger and derive current standings",
    )
    correction_verify.add_argument("--ledger", type=Path, required=True)
    correction_verify.add_argument("--json", action="store_true")

    correction_history = sub.add_parser(
        "correction-history",
        help="search correction history without changing the ledger",
    )
    correction_history.add_argument("--ledger", type=Path, required=True)
    correction_history.add_argument("--target-sha256")
    correction_history.add_argument(
        "--artifact-class",
        type=str.upper,
        choices=sorted(ARTIFACT_CLASSES),
    )
    correction_history.add_argument(
        "--standing",
        type=str.upper,
        choices=sorted(ALL_STANDINGS),
    )
    correction_history.add_argument("--limit", type=int, default=200)
    correction_history.add_argument("--json", action="store_true")

    correction_export = sub.add_parser(
        "correction-export",
        help="export a verified public correction index for read-only adapters",
    )
    correction_export.add_argument("--ledger", type=Path, required=True)
    correction_export.add_argument("--output", type=Path, required=True)
    correction_export.add_argument("--json", action="store_true")
    return parser


def _human_doctor(value: dict[str, Any]) -> str:
    catalogue = value["catalogue"]
    providers = value["provider_dependencies"]
    return "\n".join(
        [
            "ENGINE READY" if value["engine_ready"] else "ENGINE NOT READY",
            (
                f"Catalogue: {catalogue['stations']} verified stations; "
                f"{catalogue['runnable_entry_gates']} runnable entry gates; "
                f"{catalogue['live_ready']} live-research stations"
            ),
            f"Ledger: {value['ledger']['status']}",
            (
                "External dependencies: "
                f"network={providers['network_required']}, "
                f"GitHub={providers['github_required']}, "
                f"OpenAI={providers['openai_required']}, "
                f"website={providers['website_required']}"
            ),
            f"Scope: {value['operating_scope']} (not live scientific intake)",
        ]
    )


def _human_list(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No workbenches match those filters."
    lines = [f"{len(rows)} verified workbench(es)"]
    for row in rows:
        lines.append(
            f"{row['workbench_code']}  {row['readiness_stage']:<19} "
            f"{row['evidence_lane']:<11} {row['title']}"
        )
    return "\n".join(lines)


def _human_quality(value: dict[str, Any]) -> str:
    summary = value["summary"]
    certifications = value["certifications"]
    profile_note = (
        "not a certification"
        if value["profile"] == "FOUNDATION_ONLY"
        else "certified profile"
    )
    return "\n".join(
        [
            "FACTORY QUALITY PROFILE VERIFIED",
            f"Profile: {value['profile']} ({profile_note})",
            (
                f"Controls: {summary['controls']} total; {summary['meets']} meet; "
                f"{summary['partial']} partial; {summary['blocked']} blocked"
            ),
            (
                "Certifications: "
                f"operational={str(certifications['operationally_conformant']).lower()}, "
                f"scientific={str(certifications['scientifically_demonstrated']).lower()}, "
                f"independent-audit={str(certifications['independently_audited']).lower()}"
            ),
            (
                "Operating facts: "
                f"{value['operating_facts']['live_research_stations']} live stations; "
                f"{value['operating_facts']['independent_human_validators_onboarded']} "
                "independent validators onboarded"
            ),
            f"Boundary: {value['scope_boundary']}",
        ]
    )


def _human_inspect(value: dict[str, Any]) -> str:
    row = value["registry"]
    contract = value["contract"]
    problem = contract["problem"]
    starter = contract["starter_pack"]
    unresolved = contract["readiness"]["unresolved"]
    lines = [
        f"{row['workbench_code']} - {row['title']}",
        (
            f"Stage: {row['readiness_stage']} | profile: "
            f"{row['commissioning_profile']} | lane: {row['evidence_lane']}"
        ),
        f"Safe scope now: {value['safe_scope']}",
        f"Live research allowed: {str(value['live_research_allowed']).lower()}",
        f"Objective: {problem['objective']}",
        f"Hard gate: {problem['hard_gate_statement']}",
        f"Starter gate: {starter['fixture_status']}",
        f"Starter command: {starter['command']}",
        f"Unresolved before live use ({len(unresolved)}):",
    ]
    lines.extend(f"  - {item}" for item in unresolved)
    lines.append(f"Contract: {value['paths']['contract']}")
    return "\n".join(lines)


def _human_package(value: dict[str, Any], *, verified: bool) -> str:
    verb = "STRUCTURE VERIFIED" if verified else "CREATED AND VERIFIED"
    lines = [
        f"PORTABLE PACKAGE {verb}",
        f"Path: {value['path']}",
        f"Workbench: {value['workbench_code']}",
        f"Package SHA-256: {value['package_sha256']}",
        f"Evidence SHA-256: {value['evidence_sha256']}",
        "Scientific standing: NONE",
        "Promotion eligibility: false",
    ]
    if verified:
        lines.insert(3, f"Current contract match: {str(value['current_contract_match']).lower()}")
    return "\n".join(lines)


def _human_negative_results(value: dict[str, Any]) -> str:
    if not value["results"]:
        return "No retained negative results matched."
    lines = [
        f"{value['returned']} of {value['total_matches']} retained negative result(s)"
    ]
    for row in value["results"]:
        lines.extend(
            [
                "",
                f"{row['attempt_id']}  {row['classification']}  {row['reason_code']}",
                f"Round: {row['round_id']} | work unit: {row['work_unit_id']}",
                f"Hypothesis: {row['hypothesis']}",
                f"Finding: {row['public_summary']}",
                f"Evidence: sha256:{row['evidence_package_sha256']}",
            ]
        )
    return "\n".join(lines)


def _human_correction_record(value: dict[str, Any]) -> str:
    target = value["target"]
    return "\n".join(
        [
            "CORRECTION APPENDED",
            f"Record: {value['correction_id']} (sequence {value['sequence']})",
            f"Target: {target['artifact_class']} / {target['artifact_id']}",
            f"Standing: {value['standing_before']} -> {value['standing_after']}",
            f"Record SHA-256: {value['record_sha256']}",
            "Original bytes preserved: true",
            "Scientific standing: NONE",
        ]
    )


def _human_correction_verification(value: dict[str, Any]) -> str:
    standings = ", ".join(
        f"{name}={count}" for name, count in value["current_standings"].items()
    ) or "none"
    return "\n".join(
        [
            "CORRECTION LEDGER VERIFIED",
            f"Records: {value['records']} across {value['targets']} target(s)",
            f"Current standings: {standings}",
            f"Head SHA-256: {value['head_record_sha256']}",
            "Scientific standing: NONE",
        ]
    )


def _human_correction_history(value: dict[str, Any]) -> str:
    if not value["records"]:
        return "No correction records matched."
    lines = [f"{value['returned']} of {value['total_matches']} correction record(s)"]
    for record in value["records"]:
        lines.extend(
            [
                "",
                f"#{record['sequence']} {record['correction_id']}  {record['action']}",
                (
                    f"Target: {record['target']['artifact_class']} / "
                    f"{record['target']['artifact_id']}"
                ),
                (
                    f"Recorded: {record['standing_before']} -> {record['standing_after']} | "
                    f"current: {record['current_standing']}"
                ),
                f"Reason: {record['reason']['code']} - {record['public_summary']}",
            ]
        )
    return "\n".join(lines)


def run_local(args: argparse.Namespace) -> int:
    factory_root = args.factory_root.resolve()
    if args.command == "doctor":
        value = doctor(factory_root, ledger=args.ledger)
        print(_human_doctor(value) if not args.json else json.dumps(value, indent=2))
        return 0

    if args.command == "quality":
        value = verify_factory_quality(factory_root.parent)
        _json(value) if args.json else print(_human_quality(value))
        return 0

    if args.command == "list":
        catalogue = StationCatalogue(factory_root)
        value = catalogue.list(
            stage=args.stage,
            profile=args.profile,
            lane=args.lane,
            entry_ready=args.entry_ready,
        )
        _json(value) if args.json else print(_human_list(value))
        return 0
    if args.command == "inspect":
        catalogue = StationCatalogue(factory_root)
        value = catalogue.inspect(args.workbench)
        _json(value) if args.json else print(_human_inspect(value))
        return 0

    if args.command == "negative-results":
        value = search_ledger(
            args.ledger,
            query=args.query,
            round_id=args.round_id,
            work_unit_id=args.work_unit_id,
            classification=args.classification,
            reason_code=args.reason_code,
            limit=args.limit,
        )
        _json(value) if args.json else print(_human_negative_results(value))
        return 0

    if args.command == "correction-append":
        ledger = CorrectionLedger(args.ledger)
        value = ledger.append(load_correction_draft(args.draft))
        _json(value) if args.json else print(_human_correction_record(value))
        return 0
    if args.command == "correction-verify":
        value = CorrectionLedger(args.ledger).verify()
        _json(value) if args.json else print(_human_correction_verification(value))
        return 0
    if args.command == "correction-history":
        value = CorrectionLedger(args.ledger).history(
            target_sha256=args.target_sha256,
            artifact_class=args.artifact_class,
            standing=args.standing,
            limit=args.limit,
        )
        _json(value) if args.json else print(_human_correction_history(value))
        return 0
    if args.command == "correction-export":
        value = CorrectionLedger(args.ledger).export_public_index(args.output)
        if args.json:
            _json(value)
        else:
            print(
                "CORRECTION INDEX EXPORTED\n"
                f"Path: {args.output.resolve()}\n"
                f"Records: {value['returned']}\n"
                "Scientific standing: NONE"
            )
        return 0

    portable = PortableEvidencePackage(factory_root)
    if args.command == "package":
        value = portable.create(
            workbench=args.workbench,
            attempt_id=args.attempt,
            operator_id=args.operator,
            operating_mode=args.mode,
            evidence_kind=args.kind,
            summary=args.summary,
            commands=args.commands,
            seeds=args.seeds,
            stochastic=args.stochastic,
            source=args.source,
            output=args.output,
        )
        _json(value) if args.json else print(_human_package(value, verified=False))
        return 0
    if args.command == "verify":
        value = portable.verify(args.package)
        _json(value) if args.json else print(_human_package(value, verified=True))
        return 0
    raise AssertionError(f"unhandled local command {args.command}")


def main(argv: list[str] | None = None) -> int:
    actual = list(sys.argv[1:] if argv is None else argv)
    command = _selected_command(actual)
    if command is None and (not actual or any(item in {"-h", "--help"} for item in actual)):
        _print_help()
        return 0
    if command not in LOCAL_COMMANDS:
        return governed_cli.main(actual)
    parser = build_local_parser()
    args = parser.parse_args(actual)
    try:
        return run_local(args)
    except ControlPlaneError as exc:
        print(f"factoryctl: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
