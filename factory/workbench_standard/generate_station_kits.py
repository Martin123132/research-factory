from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
import tempfile
import unicodedata
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker

from commissioning import digital_compression, digital_optimization


GENERATOR_VERSION = "1.2.0"
CONTRACT_VERSION = "1.1.0"
STANDARD = "research-factory/workbench-contract/v1"
PINNED_CATALOGUE_SHA256 = "9b37a47c265e916cbf460f4dd0120b02b01fa800b104017b117ba2fc40644cd5"
GENERIC_STARTER = (
    "Reproduce the pinned baseline, pass the public verifier, then submit one "
    "sealed candidate against hidden holdouts."
)
NEGATIVE_TAXONOMY = [
    "NO_GAIN",
    "HYPOTHESIS_REJECTED",
    "RESOURCE_LIMIT",
    "UNRUNNABLE",
    "BOUNDARY_FOUND",
    "DUPLICATE_DIRECTION",
    "INVALID",
    "DISPUTED",
]
DISPUTE_OUTCOMES = [
    "REPRODUCED",
    "ORIGINAL_ERROR",
    "VALIDATOR_ERROR",
    "ENVIRONMENT_MISMATCH",
    "INCOMPLETE_METHOD",
    "UNSTABLE_BENCHMARK",
    "DISPUTED",
    "UNRUNNABLE",
]
PUBLIC_VERDICTS = ["PASS", "NO_GAIN", "INVALID", "ESCALATE"]
LANE_MAP = {
    "Digital": "DIGITAL",
    "Digital / device": "DIGITAL_DEVICE",
    "Simulation to lab": "SIMULATION_TO_LAB",
    "Lab / pilot": "LAB_PILOT",
    "Simulation to field": "SIMULATION_TO_FIELD",
    "Simulation to physical": "SIMULATION_TO_PHYSICAL",
    "Exact proof": "EXACT_PROOF",
}
TRACK_MAP = {
    "Practical improvement": "PRACTICAL_IMPROVEMENT",
    "Foundational exact proof": "FOUNDATIONAL_EXACT_PROOF",
}
SHARED_TEMPLATE_NAMES = [
    "submission-template.json",
    "negative-result-template.json",
    "dispute-template.json",
    "VALIDATOR_CHECKLIST.md",
    "NO_SCIENTIFIC_CREDIT.md",
]

STANDARD_ROOT = Path(__file__).resolve().parent
FACTORY_ROOT = STANDARD_ROOT.parent
REPOSITORY_ROOT = FACTORY_ROOT.parent
CATALOGUE_PATH = REPOSITORY_ROOT / "research_factory_100_workbenches.json"
HANGAR_CATALOGUE_PATH = FACTORY_ROOT / "hangar" / "data" / "workbenches.json"
SCHEMA_PATH = STANDARD_ROOT / "schema" / "workbench-contract-v1.schema.json"
TEMPLATES_ROOT = STANDARD_ROOT / "templates"
KITS_ROOT = FACTORY_ROOT / "station_kits"
HANGAR_DATA_PATH = FACTORY_ROOT / "hangar" / "data" / "workbench-contracts.json"
HANGAR_READINESS_PATH = FACTORY_ROOT / "hangar" / "data" / "workbench-readiness.json"
HANGAR_PUBLIC_SCHEMA_PATH = FACTORY_ROOT / "hangar" / "public" / SCHEMA_PATH.name
HANGAR_PUBLIC_BUNDLE_PATH = FACTORY_ROOT / "hangar" / "public" / "workbench-contracts-v1.json"
COMMISSIONING_ROOT = STANDARD_ROOT / "commissioning"
COMMISSIONING_INDEX_PATH = COMMISSIONING_ROOT / "index.json"
COMMISSIONING_INDEX_SCHEMA_PATH = COMMISSIONING_ROOT / "index.schema.json"
DIGITAL_COMPRESSION_SCHEMA_PATH = COMMISSIONING_ROOT / "digital-compression-override-v1.schema.json"
DIGITAL_OPTIMIZATION_SCHEMA_PATH = COMMISSIONING_ROOT / "digital-optimization-override-v1.schema.json"
GENERATOR_SOURCE_PATHS = [
    Path(__file__).resolve(),
    SCHEMA_PATH,
    COMMISSIONING_INDEX_PATH,
    COMMISSIONING_INDEX_SCHEMA_PATH,
    DIGITAL_COMPRESSION_SCHEMA_PATH,
    COMMISSIONING_ROOT / "digital_compression.py",
    COMMISSIONING_ROOT / "digital_compression_submission.schema.json",
    COMMISSIONING_ROOT / "digital_compression_result.schema.json",
    COMMISSIONING_ROOT / "runner" / "evaluate_trusted.py",
    COMMISSIONING_ROOT / "runner" / "process_control.py",
    DIGITAL_OPTIMIZATION_SCHEMA_PATH,
    COMMISSIONING_ROOT / "digital_optimization.py",
    COMMISSIONING_ROOT / "digital_optimization_submission.schema.json",
    COMMISSIONING_ROOT / "digital_optimization_result.schema.json",
    COMMISSIONING_ROOT / "runner" / "evaluate_optimization_trusted.py",
]
_SCHEMA_VALIDATOR: Draft202012Validator | None = None


class ContractError(ValueError):
    pass


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    value = canonicalize_value(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonicalize_value(value: Any) -> Any:
    """Normalize JSON values so Python and JavaScript hash the same document."""
    if isinstance(value, dict):
        return {key: canonicalize_value(child) for key, child in value.items()}
    if isinstance(value, list):
        return [canonicalize_value(child) for child in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def pretty_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def generator_source_digest() -> str:
    records = []
    for path in GENERATOR_SOURCE_PATHS:
        if not path.is_file() or path.is_symlink():
            raise ContractError(f"generator source is missing or unsafe: {path}")
        records.append(
            {
                "path": path.relative_to(REPOSITORY_ROOT).as_posix(),
                "sha256": sha256_bytes(path.read_bytes()),
            }
        )
    return sha256_bytes(canonical_bytes(records))


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    if not slug:
        raise ContractError(f"cannot make slug from {value!r}")
    return slug[:80].rstrip("-")


def workbench_code(numeric_id: int) -> str:
    return f"WB-{numeric_id:03d}"


def split_references(value: str) -> list[str]:
    refs = [part.strip() for part in value.split("|") if part.strip()]
    if not refs or any(not ref.startswith("https://") for ref in refs):
        raise ContractError(f"references must be non-empty HTTPS URLs: {value!r}")
    return refs


def assert_safe_relative(path_text: str, *, label: str) -> None:
    if not path_text:
        raise ContractError(f"{label} is empty")
    path = Path(path_text)
    if path.is_absolute() or re.match(r"^[A-Za-z]:", path_text):
        raise ContractError(f"{label} must be relative: {path_text}")
    if "\\" in path_text or any(part in {"", ".", ".."} for part in path_text.split("/")):
        raise ContractError(f"{label} is not a canonical relative path: {path_text}")


def resolve_governed_path(path_text: str) -> Path:
    """Resolve legacy factory-relative locks and repository-relative v1.1 locks."""
    return REPOSITORY_ROOT / path_text if path_text.startswith("factory/") else FACTORY_ROOT / path_text


def load_catalogue() -> dict[str, Any]:
    primary_bytes = CATALOGUE_PATH.read_bytes()
    copy_bytes = HANGAR_CATALOGUE_PATH.read_bytes()
    actual = sha256_bytes(primary_bytes)
    if actual != PINNED_CATALOGUE_SHA256:
        raise ContractError(f"catalogue digest changed: expected {PINNED_CATALOGUE_SHA256}, got {actual}")
    if primary_bytes != copy_bytes:
        raise ContractError("Hangar catalogue is not byte-identical to the canonical catalogue")
    catalogue = json.loads(primary_bytes.decode("utf-8"))
    rows = catalogue.get("workbenches")
    if catalogue.get("version") != 1 or not isinstance(rows, list) or len(rows) != 100:
        raise ContractError("catalogue must be version 1 with exactly 100 workbenches")
    required = {
        "id",
        "category",
        "short_category",
        "evidence_lane",
        "workbench",
        "hard_gate_and_score",
        "economic_or_physical_guardrail",
        "benchmark",
        "reference_url",
        "starter_pack",
        "track",
    }
    for expected_id, row in enumerate(rows, start=1):
        if row.get("id") != expected_id:
            raise ContractError(f"catalogue ID {expected_id} is missing or out of order")
        missing = sorted(required - set(row))
        if missing:
            raise ContractError(f"{workbench_code(expected_id)} missing fields: {missing}")
        if row["evidence_lane"] not in LANE_MAP or row["track"] not in TRACK_MAP:
            raise ContractError(f"{workbench_code(expected_id)} uses an unsupported lane or track")
        for field in required - {"id"}:
            if not isinstance(row[field], str) or not row[field].strip():
                raise ContractError(f"{workbench_code(expected_id)} has an empty {field}")
    return catalogue


def base_governance() -> dict[str, Any]:
    return {
        "reproduction": {
            "required_independent_human_validators": 2,
            "author_may_validate": False,
            "distinct_people_required": True,
            "validator_conflict_declaration_required": True,
            "identity_assurance": "NOT_IMPLEMENTED",
            "result_visibility": "COMMIT_BEFORE_REVEAL",
            "pass_rule": "TWO_INDEPENDENT_PASSES",
            "split_rule": "DIAGNOSTIC_THEN_HUMAN_REVIEW",
            "majority_vote_resolves_deterministic_dispute": False,
            "tolerance_binding": "STATION_MEASUREMENT_CONTRACT",
        },
        "negative_results": {
            "retained": True,
            "searchable": True,
            "append_only": True,
            "taxonomy": NEGATIVE_TAXONOMY,
        },
        "blind_evaluation": {
            "required_before_live": True,
            "hidden_claim_withheld": True,
            "human_authorization_required": True,
            "evaluator_status": "NOT_IMPLEMENTED",
            "public_verdicts": PUBLIC_VERDICTS,
            "detailed_results_private_until_reveal": True,
        },
        "disputes": {
            "failed_reproduction_is_not_automatic_falsification": True,
            "third_run_role": "DIAGNOSTIC_ONLY",
            "deterministic_disagreement_policy": "HUMAN_REVIEW_REQUIRED",
            "majority_vote_can_promote": False,
            "outcomes": DISPUTE_OUTCOMES,
        },
    }


def draft_criterion(row: dict[str, Any], *, exact_proof: bool) -> dict[str, Any]:
    return {
        "criterion_id": "formal-proof-valid" if exact_proof else "station-hard-gate",
        "statement": row["hard_gate_and_score"],
        "comparison": "FORMAL_PROOF" if exact_proof else "STATION_DEFINED",
        "metric_id": "proof_valid" if exact_proof else None,
        "threshold": "TRUE" if exact_proof else None,
        "unit": "boolean" if exact_proof else None,
        "machine_check": "NOT_IMPLEMENTED",
        "verifier_path_or_protocol": None,
        "verifier_sha256": None,
        "failure_behavior": "FAIL_CLOSED",
        "score_may_override_failure": False,
    }


def proof_metric() -> dict[str, Any]:
    return {
        "metric_id": "proof_valid",
        "label": "Proof satisfies the official universal statement",
        "unit": "boolean",
        "direction": "EXACT",
        "aggregation": "CERTIFICATE",
        "baseline_binding": "official problem statement",
        "measurement_grade": "NOT_IMPLEMENTED",
        "decision_threshold": "TRUE",
        "required": True,
    }


def empty_stochastic_protocol() -> dict[str, Any]:
    return {
        "required": False,
        "repetitions": None,
        "seed_policy": None,
        "aggregation": None,
        "confidence_rule": None,
        "permitted_runner_class": None,
    }


def draft_measurement(row: dict[str, Any], *, exact_proof: bool) -> dict[str, Any]:
    if exact_proof:
        tolerance = {
            "policy": "FORMAL_PROOF",
            "logical_tolerance": 0,
            "reproduction_rules": [
                "Logical validity has zero tolerance.",
                "Finite numerical evidence cannot substitute for a universal proof.",
                "The Factory cannot claim official prize acceptance.",
            ],
            "reproduction_equivalence": [
                {
                    "rule_id": "proof-validity",
                    "metric_id": "proof_valid",
                    "mode": "FORMAL",
                    "value": "VALID",
                    "unit": "boolean",
                    "zero_reference_policy": "NOT_APPLICABLE",
                }
            ],
            "improvement_thresholds": [],
            "safety_limits": [],
            "stochastic_protocol": empty_stochastic_protocol(),
        }
        metrics = [proof_metric()]
        hidden_policy = "NOT_APPLICABLE"
        accounting = {
            "required": False,
            "applicability": "NOT_APPLICABLE",
            "structured": False,
            "scenario_path": None,
            "scenario_version": None,
            "formula": None,
            "system_boundary": None,
            "included_costs": [],
            "comparator": None,
            "decision_threshold": None,
        }
    else:
        tolerance = {
            "policy": "STATION_DEFINED",
            "logical_tolerance": None,
            "reproduction_rules": [
                "The station must define task-specific equivalence before commissioning.",
                "Correctness, improvement and safety thresholds must remain separate.",
            ],
            "reproduction_equivalence": [],
            "improvement_thresholds": [],
            "safety_limits": [],
            "stochastic_protocol": empty_stochastic_protocol(),
        }
        metrics = []
        hidden_policy = "TO_BE_DEFINED"
        accounting = {
            "required": True,
            "applicability": "REQUIRED",
            "structured": False,
            "scenario_path": None,
            "scenario_version": None,
            "formula": None,
            "system_boundary": None,
            "included_costs": [],
            "comparator": None,
            "decision_threshold": None,
        }
    return {
        "criteria": [draft_criterion(row, exact_proof=exact_proof)],
        "metrics": metrics,
        "tolerance": tolerance,
        "public_inputs": {
            "status": "NOT_APPLICABLE" if exact_proof else "UNFROZEN",
            "manifest_path": None,
            "content_commitment_sha256": None,
        },
        "hidden_inputs": {"policy": hidden_policy, "commitment_path": None},
        "baseline": {
            "status": "NOT_APPLICABLE" if exact_proof else "UNFROZEN",
            "definition_path": None,
            "result_path": None,
        },
        "compute_budget": {
            "status": "UNDEFINED",
            "wall_time_seconds": None,
            "cpu_cores": None,
            "memory_bytes": None,
            "energy_measurement_required": False,
        },
        "economic_or_physical_accounting": accounting,
    }


def default_facets(*, exact_proof: bool, lane_specific_starter: bool) -> dict[str, bool]:
    return {
        "objective_truth_brief": True,
        "hard_gate_brief": True,
        "reference_benchmark": True,
        "utility_guardrail": True,
        "lane_specific_starter_pack": lane_specific_starter,
        "structured_predicate": False,
        "independent_verifier": False,
        "structured_metrics": exact_proof,
        "declared_tolerances": exact_proof,
        "frozen_public_inputs": False,
        "pinned_baseline": False,
        "executable_entry_gate": False,
        "runner_protocol": False,
        "isolation_policy": False,
        "blind_evaluator": False,
        "dispute_policy": True,
        "negative_result_policy": True,
        "production_identity": False,
        "promotion_grade_runner": False,
        "live_authorization": False,
    }


def unresolved_for_draft(*, exact_proof: bool, generic_starter: bool) -> list[str]:
    unresolved = [
        "STRUCTURED_PREDICATE_MISSING",
        "INDEPENDENT_VERIFIER_MISSING",
        "ENTRY_GATE_NOT_EXECUTABLE",
        "RUNNER_NOT_IMPLEMENTED",
        "ISOLATION_NOT_IMPLEMENTED",
        "BLIND_EVALUATOR_NOT_IMPLEMENTED",
        "PRODUCTION_IDENTITY_NOT_IMPLEMENTED",
        "PROMOTION_RUNNER_NOT_IMPLEMENTED",
        "LIVE_AUTHORIZATION_NOT_IMPLEMENTED",
    ]
    if exact_proof:
        unresolved.extend(["OFFICIAL_PROBLEM_STATEMENT_NOT_FROZEN", "OFFICIAL_ACCEPTANCE_EXTERNAL"])
    else:
        unresolved.extend(
            [
                "STRUCTURED_METRICS_MISSING",
                "TOLERANCES_UNDECLARED",
                "PUBLIC_INPUTS_UNFROZEN",
                "BASELINE_UNFROZEN",
                "ECONOMIC_ACCOUNTING_UNSTRUCTURED",
            ]
        )
    if generic_starter:
        unresolved.append("STARTER_PACK_IS_GENERIC")
    return sorted(unresolved)


def build_draft_contract(
    catalogue: dict[str, Any], row: dict[str, Any], catalogue_sha256: str, generator_sha256: str
) -> dict[str, Any]:
    numeric_id = row["id"]
    code = workbench_code(numeric_id)
    exact_proof = row["evidence_lane"] == "Exact proof"
    generic_starter = row["starter_pack"] == GENERIC_STARTER
    lane_specific_starter = not generic_starter
    governance = base_governance()
    contract: dict[str, Any] = {
        "standard": STANDARD,
        "contract_version": CONTRACT_VERSION,
        "workbench": {
            "code": code,
            "numeric_id": numeric_id,
            "slug": slugify(row["workbench"]),
            "title": row["workbench"],
            "category": row["category"],
            "short_category": row["short_category"],
            "evidence_lane": LANE_MAP[row["evidence_lane"]],
            "track": TRACK_MAP[row["track"]],
        },
        "source": {
            "catalogue_version": catalogue["version"],
            "catalogue_generated_at": catalogue["generated_at"],
            "catalogue_sha256": catalogue_sha256,
            "entry_sha256": sha256_bytes(canonical_bytes(row)),
            "benchmark_name": row["benchmark"],
            "reference_urls": split_references(row["reference_url"]),
            "factory_path": row.get("factory_path"),
            "active_round_path": row.get("active_round"),
            "implementation_contract_version": row.get("contract_version"),
        },
        "commissioning": {
            "profile_status": "CATALOGUE_ONLY",
            "adapter_id": None,
            "adapter_version": None,
            "dossier_path": None,
            "dossier_sha256": None,
        },
        "problem": {
            "objective": row["workbench"],
            "truth_condition": row["hard_gate_and_score"],
            "hard_gate_statement": row["hard_gate_and_score"],
            "utility_guardrail": row["economic_or_physical_guardrail"],
            "structured_predicate": {
                "status": "BRIEF_ONLY",
                "subject_or_input_population": None,
                "required_output": None,
                "verifier_status": "NOT_DEFINED",
                "verifier_path_or_protocol": None,
                "verifier_sha256": None,
                "pass_rule": None,
                "candidate_claim_is_authoritative": False,
                "failure_behavior": "FAIL_CLOSED",
            },
        },
        "measurement": draft_measurement(row, exact_proof=exact_proof),
        "starter_pack": {
            "entry_gate_required": True,
            "credential_neutral": True,
            "target_duration_minutes": 240 if exact_proof else None,
            "brief": row["starter_pack"],
            "fixture_status": "BRIEF_ONLY",
            "command": None,
            "expected_outputs": [],
        },
        "runner": {
            "protocol_status": "NOT_DEFINED",
            "protocol_path": None,
            "isolation_status": "NOT_DEFINED",
            "isolation_policy_path": None,
            "network_policy": "NOT_DEFINED",
            "trusted_code_only": True,
            "arbitrary_public_code_allowed": False,
            "promotion_grade": False,
        },
        "submission": {
            "template_path": "submission-template.json",
            "required_sections": [
                "human_owner",
                "hypothesis",
                "method",
                "artifact",
                "environment",
                "commands",
                "public_evidence",
                "hard_gates",
                "measurements",
                "economic_or_physical_accounting",
            ],
            "artifact_lock_required": True,
            "environment_manifest_required": True,
            "exact_commands_required": True,
            "seeds_required_when_stochastic": True,
        },
        "reproduction": governance["reproduction"],
        "negative_results": governance["negative_results"],
        "blind_evaluation": governance["blind_evaluation"],
        "disputes": governance["disputes"],
        "readiness": {
            "current_stage": "CONTRACT_DRAFT",
            "live_research_enabled": False,
            "scientific_standing": "NONE",
            "promotion_claims_allowed": False,
            "facets": default_facets(
                exact_proof=exact_proof, lane_specific_starter=lane_specific_starter
            ),
            "unresolved": unresolved_for_draft(
                exact_proof=exact_proof, generic_starter=generic_starter
            ),
        },
        "provenance": {
            "generator_version": GENERATOR_VERSION,
            "generator_sha256": generator_sha256,
            "generated_from": "research_factory_100_workbenches.json",
            "source_entry_sha256": sha256_bytes(canonical_bytes(row)),
            "referenced_assets": [],
            "shared_templates": SHARED_TEMPLATE_NAMES,
        },
    }
    return contract


def round_asset_locks(round_doc: dict[str, Any]) -> list[dict[str, Any]]:
    locks: list[dict[str, Any]] = []
    for asset in round_doc["frozen_contracts"]:
        path_text = asset["path"]
        assert_safe_relative(path_text, label=f"frozen asset {asset['name']}")
        path = FACTORY_ROOT / path_text
        if not path.is_file() or path.is_symlink():
            raise ContractError(f"frozen asset is missing or a symlink: {path_text}")
        actual = sha256_bytes(path.read_bytes())
        if actual != asset["sha256"]:
            raise ContractError(f"frozen asset hash mismatch: {path_text}")
        locks.append(
            {
                "name": asset["name"],
                "path": path_text,
                "sha256": actual,
                "logical_commitment_sha256": asset.get("logical_commitment_sha256"),
            }
        )
    for name, path_text in [
        ("pilot_round", "rounds/WB001-PILOT-001/round.json"),
        ("four_hour_starter_pack", "rounds/WB001-PILOT-001/STARTER_PACK.md"),
    ]:
        path = FACTORY_ROOT / path_text
        locks.append(
            {
                "name": name,
                "path": path_text,
                "sha256": sha256_bytes(path.read_bytes()),
                "logical_commitment_sha256": None,
            }
        )
    return locks


def instrument_wb001(contract: dict[str, Any]) -> dict[str, Any]:
    contract = copy.deepcopy(contract)
    wb_path = "factory/workbenches/wb001_lossless_compression"
    runner_path = f"{wb_path}/runner/evaluate_isolated.py"
    runner_sha256 = sha256_bytes((REPOSITORY_ROOT / runner_path).read_bytes())
    protocol_path = f"{wb_path}/PROTOCOL.md"
    contract["commissioning"] = {
        "profile_status": "LEGACY_INSTRUMENTED",
        "adapter_id": None,
        "adapter_version": None,
        "dossier_path": None,
        "dossier_sha256": None,
    }
    contract["problem"]["structured_predicate"] = {
        "status": "DEFINED",
        "subject_or_input_population": "Every file named by the frozen public corpus or sealed holdout commitment",
        "required_output": "A deterministic compressor and deployable decoder that reconstruct every input byte",
        "verifier_status": "EXECUTABLE",
        "verifier_path_or_protocol": runner_path,
        "verifier_sha256": runner_sha256,
        "pass_rule": "All exact round-trip, determinism, expansion, resource and frozen-frontier gates pass",
        "candidate_claim_is_authoritative": False,
        "failure_behavior": "FAIL_CLOSED",
    }
    contract["measurement"] = {
        "criteria": [
            {
                "criterion_id": "exact-round-trip",
                "statement": "Every decoded public and hidden file must equal the original byte-for-byte.",
                "comparison": "EXACT",
                "metric_id": "round_trip_fraction",
                "threshold": 1.0,
                "unit": "fraction",
                "machine_check": "EXECUTABLE",
                "verifier_path_or_protocol": runner_path,
                "verifier_sha256": runner_sha256,
                "failure_behavior": "FAIL_CLOSED",
                "score_may_override_failure": False,
            },
            {
                "criterion_id": "deterministic-stream",
                "statement": "Three repeated encodes must produce byte-identical compressed stream hashes.",
                "comparison": "EXACT",
                "metric_id": "determinism_fraction",
                "threshold": 1.0,
                "unit": "fraction",
                "machine_check": "EXECUTABLE",
                "verifier_path_or_protocol": runner_path,
                "verifier_sha256": runner_sha256,
                "failure_behavior": "FAIL_CLOSED",
                "score_may_override_failure": False,
            },
        ],
        "metrics": [
            {
                "metric_id": "round_trip_fraction",
                "label": "Files reconstructed exactly",
                "unit": "fraction",
                "direction": "EXACT",
                "aggregation": "EXACT",
                "baseline_binding": None,
                "measurement_grade": "REPRODUCTION",
                "decision_threshold": 1.0,
                "required": True,
            },
            {
                "metric_id": "determinism_fraction",
                "label": "Repeated streams with the expected hash",
                "unit": "fraction",
                "direction": "EXACT",
                "aggregation": "EXACT",
                "baseline_binding": None,
                "measurement_grade": "REPRODUCTION",
                "decision_threshold": 1.0,
                "required": True,
            },
            {
                "metric_id": "total_compressed_bytes",
                "label": "Total compressed bytes including decode requirements",
                "unit": "bytes",
                "direction": "MINIMIZE",
                "aggregation": "SUM",
                "baseline_binding": "frozen 14-codec reference frontier",
                "measurement_grade": "REPRODUCTION",
                "decision_threshold": 0.001,
                "required": True,
            },
            {
                "metric_id": "encode_wall_ns",
                "label": "Paired whole-corpus encode wall time",
                "unit": "nanoseconds",
                "direction": "MINIMIZE",
                "aggregation": "MEDIAN",
                "baseline_binding": "frozen 14-codec reference frontier",
                "measurement_grade": "ADVISORY",
                "decision_threshold": 0.05,
                "required": True,
            },
            {
                "metric_id": "decode_wall_ns",
                "label": "Paired whole-corpus decode wall time",
                "unit": "nanoseconds",
                "direction": "MINIMIZE",
                "aggregation": "MEDIAN",
                "baseline_binding": "frozen 14-codec reference frontier",
                "measurement_grade": "ADVISORY",
                "decision_threshold": 0.05,
                "required": True,
            },
            {
                "metric_id": "peak_rss_bytes",
                "label": "Peak resident memory",
                "unit": "bytes",
                "direction": "MINIMIZE",
                "aggregation": "MAX",
                "baseline_binding": "frozen 14-codec reference frontier",
                "measurement_grade": "ADVISORY",
                "decision_threshold": None,
                "required": True,
            },
            {
                "metric_id": "annualized_scenario_cost_gbp",
                "label": "Annualized frozen-scenario cost",
                "unit": "GBP/year",
                "direction": "MINIMIZE",
                "aggregation": "SUM",
                "baseline_binding": "best eligible frontier point for archive-and-retrieval-v1",
                "measurement_grade": "ADVISORY",
                "decision_threshold": 0.001,
                "required": True,
            },
        ],
        "tolerance": {
            "policy": "MIXED",
            "logical_tolerance": 0,
            "reproduction_rules": [
                "Decoded bytes and deterministic stream hashes require exact equality.",
                "Size uses exact byte counts; timing uses randomized paired promotion runs.",
                "Equivalence, improvement and safety thresholds are evaluated separately.",
            ],
            "reproduction_equivalence": [
                {
                    "rule_id": "exact-round-trip",
                    "metric_id": "round_trip_fraction",
                    "mode": "EXACT",
                    "value": 1.0,
                    "unit": "fraction",
                    "zero_reference_policy": "NOT_APPLICABLE",
                },
                {
                    "rule_id": "exact-determinism",
                    "metric_id": "determinism_fraction",
                    "mode": "EXACT",
                    "value": 1.0,
                    "unit": "fraction",
                    "zero_reference_policy": "NOT_APPLICABLE",
                },
                {
                    "rule_id": "exact-size",
                    "metric_id": "total_compressed_bytes",
                    "mode": "EXACT",
                    "value": 0,
                    "unit": "bytes difference",
                    "zero_reference_policy": "REQUIRE_EXACT_ZERO",
                },
            ],
            "improvement_thresholds": [
                {
                    "rule_id": "minimum-size-gain",
                    "metric_id": "total_compressed_bytes",
                    "mode": "RELATIVE",
                    "value": 0.001,
                    "unit": "fraction",
                    "zero_reference_policy": "USE_ABSOLUTE_RULE",
                },
                {
                    "rule_id": "minimum-timing-gain",
                    "metric_id": "encode_wall_ns",
                    "mode": "RELATIVE",
                    "value": 0.05,
                    "unit": "fraction",
                    "zero_reference_policy": "USE_ABSOLUTE_RULE",
                },
                {
                    "rule_id": "minimum-cost-gain",
                    "metric_id": "annualized_scenario_cost_gbp",
                    "mode": "RELATIVE",
                    "value": 0.001,
                    "unit": "fraction",
                    "zero_reference_policy": "USE_ABSOLUTE_RULE",
                },
            ],
            "safety_limits": [
                {
                    "rule_id": "maximum-encode-slowdown",
                    "metric_id": "encode_wall_ns",
                    "mode": "RELATIVE",
                    "value": 0.25,
                    "unit": "fraction",
                    "zero_reference_policy": "USE_ABSOLUTE_RULE",
                },
                {
                    "rule_id": "maximum-decode-slowdown",
                    "metric_id": "decode_wall_ns",
                    "mode": "RELATIVE",
                    "value": 0.10,
                    "unit": "fraction",
                    "zero_reference_policy": "USE_ABSOLUTE_RULE",
                },
            ],
            "stochastic_protocol": {
                "required": True,
                "repetitions": 7,
                "seed_policy": "Log the randomized paired baseline/candidate schedule seed",
                "aggregation": "Paired whole-corpus median ratios",
                "confidence_rule": "The confidence interval must exclude no improvement for a timing claim",
                "permitted_runner_class": "Pinned central hardware class for promotion; local timing is advisory",
            },
        },
        "public_inputs": {
            "status": "FROZEN",
            "manifest_path": f"{wb_path}/data/public_manifest.json",
            "content_commitment_sha256": "7e87977d8f79843d4e383590c0bc7d7058d773cf558007de66d258e9b01bb30f",
        },
        "hidden_inputs": {
            "policy": "REQUIRED",
            "commitment_path": f"{wb_path}/data/holdout_commitment.json",
        },
        "baseline": {
            "status": "FROZEN",
            "definition_path": f"{wb_path}/baselines/reference_pack/baseline_pack.toml",
            "result_path": f"{wb_path}/results/reference_pack/baseline_pack.json",
        },
        "compute_budget": {
            "status": "DECLARED",
            "wall_time_seconds": 30,
            "cpu_cores": 1,
            "memory_bytes": 536870912,
            "energy_measurement_required": False,
        },
        "economic_or_physical_accounting": {
            "required": True,
            "applicability": "REQUIRED",
            "structured": True,
            "scenario_path": f"{wb_path}/workbench.toml",
            "scenario_version": "archive-and-retrieval-v1",
            "formula": "storage + encode CPU + annual decode CPU + egress + decoder deployment cost",
            "system_boundary": "100 TB retained for 12 months with four full decode reads per year",
            "included_costs": ["storage", "encode CPU", "decode CPU", "egress", "decoder deployment"],
            "comparator": "best eligible pinned frontier point under the same scenario",
            "decision_threshold": 0.001,
        },
    }
    contract["starter_pack"] = {
        "entry_gate_required": True,
        "credential_neutral": True,
        "target_duration_minutes": 240,
        "brief": "Run the locked entry gate, reproduce the reference floor, then package one four-hour shift or a useful negative result.",
        "fixture_status": "KNOWN_ANSWER_READY",
        "command": "python control_plane/scripts/run_entry_gate.py --operator YOUR_OPERATOR_ID --acknowledge-rules --output state/YOUR_OPERATOR_ID-entry.json",
        "expected_outputs": ["entry-gate evidence JSON", "exact public reference result", "immutable shift evidence bundle"],
    }
    contract["runner"] = {
        "protocol_status": "IMPLEMENTED",
        "protocol_path": protocol_path,
        "isolation_status": "PROTOTYPE",
        "isolation_policy_path": f"{wb_path}/isolation/docker_policy.toml",
        "network_policy": "NONE",
        "trusted_code_only": True,
        "arbitrary_public_code_allowed": False,
        "promotion_grade": False,
    }
    contract["reproduction"]["identity_assurance"] = "SELF_ASSERTED_LOCAL"
    contract["blind_evaluation"]["evaluator_status"] = "LOCAL_COMMISSIONING_ONLY"
    facets = {key: True for key in contract["readiness"]["facets"]}
    facets.update(
        {
            "production_identity": False,
            "promotion_grade_runner": False,
            "live_authorization": False,
        }
    )
    contract["readiness"] = {
        "current_stage": "COMMISSIONING_READY",
        "live_research_enabled": False,
        "scientific_standing": "NONE",
        "promotion_claims_allowed": False,
        "facets": facets,
        "unresolved": [
            "CENTRAL_BLIND_EVALUATOR_NOT_DEPLOYED",
            "ECONOMIC_DECISION_ENFORCEMENT_GAP",
            "LIVE_AUTHORIZATION_NOT_IMPLEMENTED",
            "PRODUCTION_IDENTITY_NOT_IMPLEMENTED",
            "PROMOTION_RUNNER_NOT_IMPLEMENTED",
            "TIMING_PROTOCOL_ADVISORY",
        ],
    }
    round_doc = json.loads((FACTORY_ROOT / "rounds" / "WB001-PILOT-001" / "round.json").read_text(encoding="utf-8"))
    contract["provenance"]["referenced_assets"] = round_asset_locks(round_doc)
    return contract


def _load_schema_validator(path: Path) -> Draft202012Validator:
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _schema_errors(validator: Draft202012Validator, document: dict[str, Any], label: str) -> None:
    errors = sorted(validator.iter_errors(document), key=lambda item: list(item.absolute_path))
    if errors:
        details = "; ".join(
            f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
            for error in errors[:8]
        )
        raise ContractError(f"{label} schema error: {details}")


def load_commissioning_registrations() -> list[dict[str, Any]]:
    index = json.loads(COMMISSIONING_INDEX_PATH.read_text(encoding="utf-8"))
    _schema_errors(_load_schema_validator(COMMISSIONING_INDEX_SCHEMA_PATH), index, "commissioning index")
    unsigned = {key: value for key, value in index.items() if key != "index_sha256"}
    if index["index_sha256"] != sha256_bytes(canonical_bytes(unsigned)):
        raise ContractError("commissioning index self-hash mismatch")
    registrations = index["registrations"]
    codes = [registration["workbench_code"] for registration in registrations]
    paths = [registration["override_path"] for registration in registrations]
    if len(codes) != len(set(codes)) or len(paths) != len(set(paths)):
        raise ContractError("commissioning index has duplicate station codes or override paths")
    return registrations


def load_adapter_override(
    registration: dict[str, Any],
    draft: dict[str, Any],
    *,
    adapter_id: str,
    schema_path: Path,
    allowed_category: str,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    if registration["adapter"] != adapter_id:
        raise ContractError(f"unsupported commissioning adapter: {registration['adapter']}")
    if draft["workbench"]["category"] != allowed_category or draft["workbench"]["evidence_lane"] != "DIGITAL":
        raise ContractError(f"{draft['workbench']['code']}: {adapter_id} lane mismatch")
    override_path_text = registration["override_path"]
    assert_safe_relative(override_path_text, label="commissioning override")
    override_path = REPOSITORY_ROOT / override_path_text
    if not override_path.is_file() or override_path.is_symlink():
        raise ContractError(f"commissioning override is missing or unsafe: {override_path_text}")
    override_payload = override_path.read_bytes()
    if sha256_bytes(override_payload) != registration["override_sha256"]:
        raise ContractError(f"commissioning override hash mismatch: {override_path_text}")
    override = json.loads(override_payload.decode("utf-8"))
    _schema_errors(_load_schema_validator(schema_path), override, override_path_text)
    if override["workbench_code"] != registration["workbench_code"] or override["workbench_code"] != draft["workbench"]["code"]:
        raise ContractError("commissioning override station identity mismatch")
    if override["catalogue_entry_sha256"] != draft["source"]["entry_sha256"]:
        raise ContractError(f"{override['workbench_code']}: commissioning override catalogue digest is stale")
    asset_by_role: dict[str, dict[str, Any]] = {
        "commissioning_override": {
            "name": "commissioning_override",
            "path": override_path_text,
            "sha256": registration["override_sha256"],
            "logical_commitment_sha256": None,
        }
    }
    seen_paths = {override_path_text}
    for declared in override["assets"]:
        role = declared["role"]
        path_text = declared["path"]
        if role in asset_by_role:
            raise ContractError(f"{override['workbench_code']}: duplicate asset role {role}")
        if path_text in seen_paths:
            raise ContractError(f"{override['workbench_code']}: duplicate asset path {path_text}")
        assert_safe_relative(path_text, label=f"{override['workbench_code']} asset {role}")
        if {part.lower() for part in path_text.split('/')} & {"private", "state"}:
            raise ContractError(f"{override['workbench_code']}: forbidden private/state asset path")
        asset_path = REPOSITORY_ROOT / path_text
        if not asset_path.is_file() or asset_path.is_symlink():
            raise ContractError(f"{override['workbench_code']}: missing or unsafe asset {path_text}")
        actual = sha256_bytes(asset_path.read_bytes())
        if actual != declared["sha256"]:
            raise ContractError(f"{override['workbench_code']}: asset hash mismatch {path_text}")
        asset_by_role[role] = {
            "name": role,
            "path": path_text,
            "sha256": actual,
            "logical_commitment_sha256": None,
        }
        seen_paths.add(path_text)
    required_roles = {
        "commissioning_override", "truth_verifier", "runner_implementation", "submission_schema",
        "result_schema", "public_input_manifest", "entry_baseline_definition", "entry_baseline_result",
        "economic_scenario", "runner_protocol", "isolation_policy", "starter_pack_instructions",
        "entry_fixture", "entry_gate_script",
    }
    missing = sorted(required_roles - set(asset_by_role))
    if missing:
        raise ContractError(f"{override['workbench_code']}: missing commissioning asset roles: {missing}")
    role_path_bindings = {
        "public_input_manifest": "public_input_manifest",
        "economic_scenario": "economic_scenario",
        "runner_protocol": "runner_protocol",
        "isolation_policy": "isolation_policy",
    }
    for role, path_key in role_path_bindings.items():
        if asset_by_role[role]["path"] != override["paths"][path_key]:
            raise ContractError(f"{override['workbench_code']}: {role} path is not bound to its asset")
    return override, asset_by_role


def load_commissioning_override(
    registration: dict[str, Any], draft: dict[str, Any]
) -> tuple[
    dict[str, Any],
    dict[str, dict[str, Any]],
    Any,
]:
    adapter = registration["adapter"]
    if adapter == digital_compression.ADAPTER_ID:
        override, assets = load_adapter_override(
            registration,
            draft,
            adapter_id=digital_compression.ADAPTER_ID,
            schema_path=DIGITAL_COMPRESSION_SCHEMA_PATH,
            allowed_category="Compression & storage",
        )
        return override, assets, digital_compression.hydrate_contract
    if adapter == digital_optimization.ADAPTER_ID:
        override, assets = load_adapter_override(
            registration,
            draft,
            adapter_id=digital_optimization.ADAPTER_ID,
            schema_path=DIGITAL_OPTIMIZATION_SCHEMA_PATH,
            allowed_category="Routing & logistics",
        )
        return override, assets, digital_optimization.hydrate_contract
    raise ContractError(f"unsupported commissioning adapter: {adapter}")


def build_contracts() -> list[dict[str, Any]]:
    catalogue = load_catalogue()
    catalogue_sha256 = sha256_bytes(CATALOGUE_PATH.read_bytes())
    generator_sha256 = generator_source_digest()
    contracts = [
        build_draft_contract(catalogue, row, catalogue_sha256, generator_sha256)
        for row in catalogue["workbenches"]
    ]
    contracts[0] = instrument_wb001(contracts[0])
    by_code = {contract["workbench"]["code"]: index for index, contract in enumerate(contracts)}
    for registration in load_commissioning_registrations():
        code = registration["workbench_code"]
        if code not in by_code:
            raise ContractError(f"commissioning index names an unknown station: {code}")
        index = by_code[code]
        if contracts[index]["commissioning"]["profile_status"] != "CATALOGUE_ONLY":
            raise ContractError(f"{code}: station already has a commissioning implementation")
        override, assets, hydrate = load_commissioning_override(registration, contracts[index])
        contracts[index] = hydrate(contracts[index], override, assets)
    for contract in contracts:
        validate_contract(contract)
    return contracts


def validate_schema_document(contract: dict[str, Any]) -> None:
    global _SCHEMA_VALIDATOR
    if _SCHEMA_VALIDATOR is None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        _SCHEMA_VALIDATOR = Draft202012Validator(schema, format_checker=FormatChecker())
    validator = _SCHEMA_VALIDATOR
    errors = sorted(validator.iter_errors(contract), key=lambda item: list(item.absolute_path))
    if errors:
        details = "; ".join(
            f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
            for error in errors[:8]
        )
        raise ContractError(f"{contract.get('workbench', {}).get('code', 'contract')} schema error: {details}")


def iter_path_fields(value: Any, trail: tuple[str, ...] = ()) -> Iterable[tuple[str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            new_trail = (*trail, key)
            if child is not None and isinstance(child, str) and (key.endswith("_path") or key == "path"):
                yield "/".join(new_trail), child
            yield from iter_path_fields(child, new_trail)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_path_fields(child, (*trail, str(index)))


def validate_contract(contract: dict[str, Any], *, require_stage: str | None = None) -> None:
    validate_schema_document(contract)
    code = contract["workbench"]["code"]
    if code != workbench_code(contract["workbench"]["numeric_id"]):
        raise ContractError(f"{code}: code and numeric ID disagree")
    if contract["source"]["entry_sha256"] != contract["provenance"]["source_entry_sha256"]:
        raise ContractError(f"{code}: source entry digests disagree")
    commissioning = contract["commissioning"]
    profile = commissioning["profile_status"]
    adapter_fields = [
        commissioning["adapter_id"], commissioning["adapter_version"],
        commissioning["dossier_path"], commissioning["dossier_sha256"],
    ]
    if profile in {"CATALOGUE_ONLY", "LEGACY_INSTRUMENTED"} and any(value is not None for value in adapter_fields):
        raise ContractError(f"{code}: non-adapter profile carries adapter fields")
    if profile == "ADAPTER_BOUND" and any(value is None for value in adapter_fields):
        raise ContractError(f"{code}: adapter-bound profile lacks identity or dossier commitment")
    for label, path_text in iter_path_fields(contract):
        assert_safe_relative(path_text, label=f"{code} {label}")
        lowered_parts = {part.lower() for part in path_text.split("/")}
        if lowered_parts & {"private", "state"}:
            raise ContractError(f"{code}: governed contract references forbidden private/state path")
    asset_by_name: dict[str, dict[str, Any]] = {}
    for asset in contract["provenance"]["referenced_assets"]:
        if asset["name"] in asset_by_name:
            raise ContractError(f"{code}: duplicate referenced asset role {asset['name']}")
        asset_path = resolve_governed_path(asset["path"])
        if not asset_path.is_file() or asset_path.is_symlink():
            raise ContractError(f"{code}: referenced asset is missing or unsafe: {asset['path']}")
        if sha256_bytes(asset_path.read_bytes()) != asset["sha256"]:
            raise ContractError(f"{code}: referenced asset hash mismatch: {asset['path']}")
        asset_by_name[asset["name"]] = asset
    if profile == "ADAPTER_BOUND":
        dossier = asset_by_name.get("commissioning_override")
        if not dossier or dossier["path"] != commissioning["dossier_path"] or dossier["sha256"] != commissioning["dossier_sha256"]:
            raise ContractError(f"{code}: adapter dossier is not bound to a locked asset")
        operational_bindings = {
            "public_input_manifest": contract["measurement"]["public_inputs"]["manifest_path"],
            "economic_scenario": contract["measurement"]["economic_or_physical_accounting"]["scenario_path"],
            "runner_protocol": contract["runner"]["protocol_path"],
            "isolation_policy": contract["runner"]["isolation_policy_path"],
            "starter_pack_instructions": next(
                (asset["path"] for asset in contract["provenance"]["referenced_assets"] if asset["name"] == "starter_pack_instructions"),
                None,
            ),
        }
        for role, path_text in operational_bindings.items():
            if role not in asset_by_name or asset_by_name[role]["path"] != path_text:
                raise ContractError(f"{code}: operational path is not locked by asset role {role}")
    predicate = contract["problem"]["structured_predicate"]
    if predicate["status"] == "DEFINED":
        required_values = [
            predicate["subject_or_input_population"],
            predicate["required_output"],
            predicate["verifier_path_or_protocol"],
            predicate["verifier_sha256"],
            predicate["pass_rule"],
        ]
        if any(value is None for value in required_values) or predicate["verifier_status"] == "NOT_DEFINED":
            raise ContractError(f"{code}: a defined truth predicate needs an independent verifier and pass rule")
        verifier_path = str(predicate["verifier_path_or_protocol"])
        if verifier_path.startswith(("candidate/", "submission/")):
            raise ContractError(f"{code}: the candidate cannot control the truth verifier")
        verifier_file = REPOSITORY_ROOT / verifier_path
        if not verifier_file.is_file() or verifier_file.is_symlink():
            raise ContractError(f"{code}: truth verifier is missing or unsafe")
        if sha256_bytes(verifier_file.read_bytes()) != predicate["verifier_sha256"]:
            raise ContractError(f"{code}: truth verifier hash mismatch")
    for criterion in contract["measurement"]["criteria"]:
        if criterion["failure_behavior"] != "FAIL_CLOSED" or criterion["score_may_override_failure"]:
            raise ContractError(f"{code}: hard gates must fail closed and cannot be overridden by score")
        if criterion["machine_check"] in {"EXECUTABLE", "FORMAL"}:
            if not criterion["verifier_path_or_protocol"] or not criterion["verifier_sha256"]:
                raise ContractError(f"{code}: executable/formal hard gate lacks a locked verifier")
            verifier_file = REPOSITORY_ROOT / criterion["verifier_path_or_protocol"]
            if not verifier_file.is_file() or verifier_file.is_symlink():
                raise ContractError(f"{code}: hard-gate verifier is missing or unsafe")
            if sha256_bytes(verifier_file.read_bytes()) != criterion["verifier_sha256"]:
                raise ContractError(f"{code}: hard-gate verifier hash mismatch")
    if contract["workbench"]["evidence_lane"] == "EXACT_PROOF":
        tolerance = contract["measurement"]["tolerance"]
        if tolerance["policy"] != "FORMAL_PROOF" or tolerance["logical_tolerance"] != 0:
            raise ContractError(f"{code}: exact proof work requires zero logical tolerance")
    starter = contract["starter_pack"]
    if starter["brief"] == GENERIC_STARTER and starter["fixture_status"] != "BRIEF_ONLY":
        raise ContractError(f"{code}: a generic starter sentence cannot be marked runnable")
    if starter["fixture_status"] == "KNOWN_ANSWER_READY" and (
        not starter["command"] or not starter["expected_outputs"]
    ):
        raise ContractError(f"{code}: runnable starter pack lacks a command or expected outputs")
    stochastic = contract["measurement"]["tolerance"]["stochastic_protocol"]
    if stochastic["required"] and any(
        stochastic[field] is None
        for field in ["repetitions", "seed_policy", "aggregation", "confidence_rule", "permitted_runner_class"]
    ):
        raise ContractError(f"{code}: stochastic measurement lacks repetitions, seeds, aggregation or confidence rules")
    tolerance = contract["measurement"]["tolerance"]
    equivalence_rules = {
        canonical_bytes(rule) for rule in tolerance["reproduction_equivalence"]
    }
    improvement_rules = {
        canonical_bytes(rule) for rule in tolerance["improvement_thresholds"]
    }
    if equivalence_rules & improvement_rules:
        raise ContractError(f"{code}: reproduction equivalence cannot be reused as an improvement threshold")
    for family in ["reproduction_equivalence", "improvement_thresholds", "safety_limits"]:
        for rule in tolerance[family]:
            if rule["mode"] == "RELATIVE" and rule["zero_reference_policy"] != "USE_ABSOLUTE_RULE":
                raise ContractError(f"{code}: relative threshold lacks an explicit zero-reference fallback")
    accounting = contract["measurement"]["economic_or_physical_accounting"]
    if accounting["required"] and accounting["structured"]:
        required_accounting = [
            accounting["scenario_path"],
            accounting["scenario_version"],
            accounting["formula"],
            accounting["system_boundary"],
            accounting["comparator"],
            accounting["decision_threshold"],
        ]
        if any(value is None for value in required_accounting) or not accounting["included_costs"]:
            raise ContractError(f"{code}: structured economic/physical gate is incomplete")
    runner = contract["runner"]
    if runner["arbitrary_public_code_allowed"] and (
        runner["isolation_status"] != "PROMOTION_GRADE"
        or runner["network_policy"] != "NONE"
        or runner["trusted_code_only"]
    ):
        raise ContractError(f"{code}: arbitrary public code lacks a promotion-grade isolated boundary")
    stage = contract["readiness"]["current_stage"]
    stage_order = {"CATALOGUED": 0, "CONTRACT_DRAFT": 1, "COMMISSIONING_READY": 2, "LIVE_READY": 3}
    if require_stage and stage_order[stage] < stage_order[require_stage]:
        raise ContractError(f"{code}: stage {stage} is below required {require_stage}")
    if stage in {"COMMISSIONING_READY", "LIVE_READY"}:
        required_facets = {
            "objective_truth_brief",
            "hard_gate_brief",
            "reference_benchmark",
            "utility_guardrail",
            "lane_specific_starter_pack",
            "structured_predicate",
            "independent_verifier",
            "structured_metrics",
            "declared_tolerances",
            "frozen_public_inputs",
            "pinned_baseline",
            "executable_entry_gate",
            "runner_protocol",
            "isolation_policy",
            "blind_evaluator",
            "dispute_policy",
            "negative_result_policy",
        }
        missing = sorted(name for name in required_facets if not contract["readiness"]["facets"][name])
        if missing:
            raise ContractError(f"{code}: commissioning facets missing: {missing}")
    reproduction = contract["reproduction"]
    if (
        reproduction["required_independent_human_validators"] != 2
        or reproduction["author_may_validate"]
        or not reproduction["distinct_people_required"]
        or reproduction["majority_vote_resolves_deterministic_dispute"]
    ):
        raise ContractError(f"{code}: invalid independent-reproduction policy")
    if contract["readiness"]["scientific_standing"] != "NONE" or contract["readiness"]["promotion_claims_allowed"]:
        raise ContractError(f"{code}: construction contracts cannot claim scientific standing")


def render_template(name: str, code: str) -> bytes:
    text = (TEMPLATES_ROOT / name).read_text(encoding="utf-8").replace("${WORKBENCH_CODE}", code)
    return text.replace("\r\n", "\n").encode("utf-8")


def starter_pack_bytes(contract: dict[str, Any]) -> bytes:
    code = contract["workbench"]["code"]
    starter_asset = next(
        (
            asset
            for asset in contract["provenance"]["referenced_assets"]
            if asset["name"] == "starter_pack_instructions"
        ),
        None,
    )
    if starter_asset is not None:
        source_path = REPOSITORY_ROOT / starter_asset["path"]
        payload = source_path.read_bytes()
        if sha256_bytes(payload) != starter_asset["sha256"]:
            raise ContractError(f"{code}: starter-pack asset hash mismatch")
        return payload
    if code == "WB-001":
        return (FACTORY_ROOT / "rounds" / "WB001-PILOT-001" / "STARTER_PACK.md").read_bytes()
    starter = contract["starter_pack"]
    status_note = (
        "This is a lane-specific four-hour entry brief, but its fixture and verifier are not yet commissioned."
        if starter["target_duration_minutes"] == 240
        else "This catalogue sentence is only a generic design placeholder; it is not a runnable exercise."
    )
    text = f"""# {code} starter-pack envelope

## Catalogue brief

{starter['brief']}

## Current status

`{starter['fixture_status']}` — {status_note}

Do not accept a submission until prerequisites, licensed acquisition steps, frozen fixture hashes, a safe command, expected public output, a verifier, an output schema and the negative-result path are all present.

Passing a future pack will prove method-following only. It will not be evidence for the open problem and will not count as an independent reproduction.
"""
    return text.encode("utf-8")


def start_here_bytes(contract: dict[str, Any], contract_sha256: str) -> bytes:
    code = contract["workbench"]["code"]
    unresolved = "\n".join(f"- `{item}`" for item in contract["readiness"]["unresolved"])
    text = f"""# {code} — {contract['workbench']['title']}

Stage: `{contract['readiness']['current_stage']}`  
Contract SHA-256: `{contract_sha256}`

This is a generated construction kit. It records the station's measurable brief, governance and missing commissioning gates without fabricating a benchmark, verifier, runner or result.

## Unresolved before live work

{unresolved}

## Fixed factory rules

- Exactly two other human owners must reproduce a locked claim.
- Neither the author nor one person using two accounts may validate it.
- Conclusions commit before reveal; deterministic disagreement is reviewed, never majority-voted into truth.
- Failed and negative work remains searchable.
- This kit, synthetic demonstrations and Hangar activity carry no scientific or promotion credit.
"""
    return text.encode("utf-8")


def runner_trust_bytes(contract: dict[str, Any]) -> bytes:
    runner = contract["runner"]
    text = f"""# Runner trust declaration — {contract['workbench']['code']}

- Protocol: `{runner['protocol_status']}`
- Isolation: `{runner['isolation_status']}`
- Network policy: `{runner['network_policy']}`
- Trusted code only: `{str(runner['trusted_code_only']).lower()}`
- Arbitrary public code allowed: `{str(runner['arbitrary_public_code_allowed']).lower()}`
- Promotion grade: `{str(runner['promotion_grade']).lower()}`

No generated kit grants execution authority. A prototype runner must not execute arbitrary public submissions, and a local result cannot be represented as promotion-grade evidence.
"""
    return text.encode("utf-8")


def verification_bytes(contract: dict[str, Any]) -> bytes:
    predicate = contract["problem"]["structured_predicate"]
    verifier = predicate["verifier_path_or_protocol"] or "NOT DEFINED"
    text = f"""# Verification boundary — {contract['workbench']['code']}

- Truth predicate status: `{predicate['status']}`
- Verifier status: `{predicate['verifier_status']}`
- Verifier or protocol: `{verifier}`
- Candidate's own claim is authoritative: `false`
- Verifier failure behavior: `FAIL_CLOSED`

The catalogue prose is a useful target, but prose alone is not an executable truth predicate. If the verifier is not defined, this station remains a contract draft.
"""
    return text.encode("utf-8")


def public_input_bytes(contract: dict[str, Any]) -> tuple[str, bytes]:
    public_inputs = contract["measurement"]["public_inputs"]
    if public_inputs["manifest_path"] is not None:
        source_path = REPOSITORY_ROOT / str(public_inputs["manifest_path"])
        if not source_path.is_file() or source_path.is_symlink():
            raise ContractError(f"missing public manifest: {source_path}")
        return "public-input-manifest.json", source_path.read_bytes()
    text = f"""# Public inputs are not frozen — {contract['workbench']['code']}

Status: `{public_inputs['status']}`

No dataset, theorem fixture or benchmark payload has been generated. Commissioning must resolve acquisition and licensing, freeze the exact input population, record content hashes and provide a public verifier before live submissions are accepted.
"""
    return "PUBLIC_INPUTS_NOT_FROZEN.md", text.encode("utf-8")


def public_input_notice_bytes(contract: dict[str, Any]) -> bytes:
    public_inputs = contract["measurement"]["public_inputs"]
    text = f"""# Public inputs are not frozen — {contract['workbench']['code']}

Status: `{public_inputs['status']}`

The included manifest records published identifiers and the current acquisition boundary. It is not a frozen content commitment. Commissioning must acquire the exact payload, verify published checksums, record a factory-derived SHA-256 and resolve licensing before live submissions are accepted.
"""
    return text.encode("utf-8")


def make_self_hashed(document: dict[str, Any], field: str) -> dict[str, Any]:
    result = copy.deepcopy(document)
    result[field] = sha256_bytes(canonical_bytes(result))
    return result


def build_kit_files(contract: dict[str, Any]) -> tuple[dict[str, bytes], dict[str, Any]]:
    code = contract["workbench"]["code"]
    contract_payload = pretty_bytes(contract)
    contract_sha256 = sha256_bytes(canonical_bytes(contract))
    files: dict[str, bytes] = {
        "contract.json": contract_payload,
        f"schemas/{SCHEMA_PATH.name}": SCHEMA_PATH.read_bytes(),
        "START_HERE.md": start_here_bytes(contract, contract_sha256),
        "STARTER_PACK.md": starter_pack_bytes(contract),
        "RUNNER_TRUST.md": runner_trust_bytes(contract),
        "VERIFICATION.md": verification_bytes(contract),
    }
    for template_name in SHARED_TEMPLATE_NAMES:
        files[template_name] = render_template(template_name, code)
    public_name, public_payload = public_input_bytes(contract)
    files[public_name] = public_payload
    if (
        contract["measurement"]["public_inputs"]["status"] == "UNFROZEN"
        and contract["measurement"]["public_inputs"]["manifest_path"] is not None
    ):
        files["PUBLIC_INPUTS_NOT_FROZEN.md"] = public_input_notice_bytes(contract)
    for path_text in files:
        assert_safe_relative(path_text, label=f"{code} kit file")
    manifest_files = [
        {"path": path_text, "bytes": len(payload), "sha256": sha256_bytes(payload)}
        for path_text, payload in sorted(files.items())
    ]
    manifest = make_self_hashed(
        {
            "schema_version": 1,
            "manifest_type": "RESEARCH_FACTORY_STATION_KIT",
            "generator_version": GENERATOR_VERSION,
            "generator_sha256": contract["provenance"]["generator_sha256"],
            "workbench_code": code,
            "contract_sha256": contract_sha256,
            "source_entry_sha256": contract["source"]["entry_sha256"],
            "readiness_stage": contract["readiness"]["current_stage"],
            "files": manifest_files,
            "construction_boundary": {
                "scientific_evidence": False,
                "counts_as_independent_reproduction": False,
                "eligible_for_promotion": False,
            },
        },
        "kit_sha256",
    )
    validate_kit_manifest(files, manifest)
    files["kit-manifest.json"] = pretty_bytes(manifest)
    return files, manifest


def validate_kit_manifest(files: dict[str, bytes], manifest: dict[str, Any]) -> None:
    code = manifest.get("workbench_code", "station kit")
    without_hash = {key: value for key, value in manifest.items() if key != "kit_sha256"}
    if manifest.get("kit_sha256") != sha256_bytes(canonical_bytes(without_hash)):
        raise ContractError(f"{code}: kit manifest self-hash mismatch")
    declared = {entry["path"]: entry for entry in manifest.get("files", [])}
    if set(declared) != set(files):
        raise ContractError(f"{code}: kit manifest has missing or extra files")
    casefolded: set[str] = set()
    for path_text, payload in files.items():
        assert_safe_relative(path_text, label=f"{code} kit file")
        folded = path_text.casefold()
        if folded in casefolded:
            raise ContractError(f"{code}: kit has a case-colliding path")
        casefolded.add(folded)
        entry = declared[path_text]
        if entry["bytes"] != len(payload) or entry["sha256"] != sha256_bytes(payload):
            raise ContractError(f"{code}: kit file size or hash mismatch for {path_text}")
    boundary = manifest.get("construction_boundary", {})
    if any(
        boundary.get(key) is not False
        for key in ["scientific_evidence", "counts_as_independent_reproduction", "eligible_for_promotion"]
    ):
        raise ContractError(f"{code}: construction kit claims scientific credit")


def build_outputs() -> tuple[list[dict[str, Any]], dict[Path, bytes], dict[str, Any]]:
    contracts = build_contracts()
    expected: dict[Path, bytes] = {}
    kit_records: list[dict[str, Any]] = []
    for contract in contracts:
        code = contract["workbench"]["code"]
        files, manifest = build_kit_files(contract)
        kit_root = KITS_ROOT / code
        for relative, payload in files.items():
            expected[kit_root / relative] = payload
        kit_records.append(
            {
                "workbench_code": code,
                "numeric_id": contract["workbench"]["numeric_id"],
                "slug": contract["workbench"]["slug"],
                "title": contract["workbench"]["title"],
                "contract_version": contract["contract_version"],
                "commissioning_profile": contract["commissioning"]["profile_status"],
                "adapter_id": contract["commissioning"]["adapter_id"],
                "adapter_version": contract["commissioning"]["adapter_version"],
                "evidence_lane": contract["workbench"]["evidence_lane"],
                "kit_path": f"factory/station_kits/{code}",
                "contract_path": f"factory/station_kits/{code}/contract.json",
                "contract_sha256": manifest["contract_sha256"],
                "kit_sha256": manifest["kit_sha256"],
                "readiness_stage": contract["readiness"]["current_stage"],
                "starter_pack_status": contract["starter_pack"]["fixture_status"],
                "unresolved_count": len(contract["readiness"]["unresolved"]),
                "unresolved": contract["readiness"]["unresolved"],
                "facets": contract["readiness"]["facets"],
                "scientific_evidence": False,
                "counts_as_independent_reproduction": False,
                "eligible_for_promotion": False,
            }
        )
    global_manifest = make_self_hashed(
        {
            "schema_version": 1,
            "manifest_type": "RESEARCH_FACTORY_STATION_KITS",
            "generator_version": GENERATOR_VERSION,
            "generator_sha256": contracts[0]["provenance"]["generator_sha256"],
            "catalogue_sha256": PINNED_CATALOGUE_SHA256,
            "standard": STANDARD,
            "stations": kit_records,
        },
        "manifest_sha256",
    )
    expected[KITS_ROOT / "manifest.json"] = pretty_bytes(global_manifest)
    counts = {
        stage: sum(1 for contract in contracts if contract["readiness"]["current_stage"] == stage)
        for stage in ["CONTRACT_DRAFT", "COMMISSIONING_READY", "LIVE_READY"]
    }
    site_summary = make_self_hashed(
        {
            "schema_version": 1,
            "standard": STANDARD,
            "generator_sha256": contracts[0]["provenance"]["generator_sha256"],
            "catalogue_sha256": PINNED_CATALOGUE_SHA256,
            "station_kits_manifest_sha256": global_manifest["manifest_sha256"],
            "counts": {
                "total": len(contracts),
                "contract_draft": counts["CONTRACT_DRAFT"],
                "commissioning_ready": counts["COMMISSIONING_READY"],
                "live_ready": counts["LIVE_READY"],
                "runnable_entry_gate": sum(
                    1 for contract in contracts if contract["starter_pack"]["fixture_status"] == "KNOWN_ANSWER_READY"
                ),
                "live_research_enabled": sum(
                    1 for contract in contracts if contract["readiness"]["live_research_enabled"]
                ),
                "adapter_bound": sum(
                    1 for contract in contracts if contract["commissioning"]["profile_status"] == "ADAPTER_BOUND"
                ),
                "legacy_instrumented": sum(
                    1 for contract in contracts if contract["commissioning"]["profile_status"] == "LEGACY_INSTRUMENTED"
                ),
                "catalogue_only": sum(
                    1 for contract in contracts if contract["commissioning"]["profile_status"] == "CATALOGUE_ONLY"
                ),
            },
            "stations": kit_records,
        },
        "summary_sha256",
    )
    expected[HANGAR_DATA_PATH] = pretty_bytes(site_summary)
    readiness_snapshot = make_self_hashed(
        {
            "schema_version": 1,
            "standard": STANDARD,
            "catalogue_sha256": PINNED_CATALOGUE_SHA256,
            "stations": [
                {
                    "numeric_id": record["numeric_id"],
                    "workbench_code": record["workbench_code"],
                    "readiness_stage": record["readiness_stage"],
                }
                for record in kit_records
            ],
        },
        "readiness_sha256",
    )
    expected[HANGAR_READINESS_PATH] = pretty_bytes(readiness_snapshot)
    expected[HANGAR_PUBLIC_SCHEMA_PATH] = SCHEMA_PATH.read_bytes()
    public_bundle = make_self_hashed(
        {
            "schema_version": 1,
            "standard": STANDARD,
            "generator_sha256": contracts[0]["provenance"]["generator_sha256"],
            "catalogue_sha256": PINNED_CATALOGUE_SHA256,
            "contracts": contracts,
        },
        "bundle_sha256",
    )
    expected[HANGAR_PUBLIC_BUNDLE_PATH] = pretty_bytes(public_bundle)
    return contracts, expected, site_summary


def output_root_for(path: Path) -> Path:
    if path.is_relative_to(KITS_ROOT):
        return KITS_ROOT
    if path.is_relative_to(FACTORY_ROOT / "hangar"):
        return FACTORY_ROOT / "hangar"
    raise ContractError(f"refusing to manage unexpected output path: {path}")


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.is_symlink():
        raise ContractError(f"refusing to replace symlink: {path}")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def detect_extra_kit_files(expected: dict[Path, bytes]) -> list[Path]:
    if not KITS_ROOT.exists():
        return []
    expected_kit_paths = {path.resolve() for path in expected if path.is_relative_to(KITS_ROOT)}
    extras: list[Path] = []
    for path in KITS_ROOT.rglob("*"):
        if path.is_symlink():
            extras.append(path)
        elif path.is_file() and path.resolve() not in expected_kit_paths:
            extras.append(path)
    return sorted(extras)


def verify_expected_outputs(expected: dict[Path, bytes]) -> list[str]:
    errors: list[str] = []
    for path, payload in sorted(expected.items(), key=lambda item: str(item[0])):
        if not path.is_file() or path.is_symlink():
            errors.append(f"missing or unsafe: {path}")
        elif path.read_bytes() != payload:
            errors.append(f"content drift: {path}")
    for path in detect_extra_kit_files(expected):
        errors.append(f"undeclared kit file: {path}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic Research Factory station kits")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="write deterministic generated outputs")
    mode.add_argument("--check", action="store_true", help="verify generated outputs without changing files")
    mode.add_argument("--explain", metavar="WB-NNN", help="print one derived station contract summary")
    parser.add_argument(
        "--require-stage",
        choices=["CATALOGUED", "CONTRACT_DRAFT", "COMMISSIONING_READY", "LIVE_READY"],
        help="fail unless every station has reached at least this stage",
    )
    parser.add_argument(
        "--require-station",
        action="append",
        default=[],
        metavar="WB-NNN=STAGE",
        help="fail unless one named station has reached at least the stated stage",
    )
    parser.add_argument(
        "--require-profile",
        action="append",
        default=[],
        metavar="WB-NNN=PROFILE",
        help="fail unless one named station has the stated commissioning profile",
    )
    args = parser.parse_args()
    contracts, expected, site_summary = build_outputs()
    by_code = {contract["workbench"]["code"]: contract for contract in contracts}
    if args.require_stage:
        for contract in contracts:
            validate_contract(contract, require_stage=args.require_stage)
    for requirement in args.require_station:
        try:
            code, stage = requirement.split("=", 1)
            contract = by_code[code]
        except (ValueError, KeyError) as error:
            raise ContractError(f"invalid station-stage requirement: {requirement}") from error
        if stage not in {"CATALOGUED", "CONTRACT_DRAFT", "COMMISSIONING_READY", "LIVE_READY"}:
            raise ContractError(f"invalid station stage: {stage}")
        validate_contract(contract, require_stage=stage)
    for requirement in args.require_profile:
        try:
            code, profile = requirement.split("=", 1)
            contract = by_code[code]
        except (ValueError, KeyError) as error:
            raise ContractError(f"invalid station-profile requirement: {requirement}") from error
        if contract["commissioning"]["profile_status"] != profile:
            raise ContractError(
                f"{code}: expected commissioning profile {profile}, got {contract['commissioning']['profile_status']}"
            )
    if args.explain:
        if args.explain not in by_code:
            raise ContractError(f"unknown station: {args.explain}")
        contract = by_code[args.explain]
        print(
            json.dumps(
                {
                    "workbench": contract["workbench"],
                    "commissioning": contract["commissioning"],
                    "readiness": contract["readiness"],
                    "starter_pack": contract["starter_pack"],
                    "locked_assets": contract["provenance"]["referenced_assets"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.write:
        extras = detect_extra_kit_files(expected)
        if extras:
            raise ContractError(
                "refusing to overwrite a kit tree with undeclared files: " + ", ".join(str(path) for path in extras[:8])
            )
        for path, payload in sorted(expected.items(), key=lambda item: str(item[0])):
            output_root_for(path)
            atomic_write(path, payload)
        action = "written"
    else:
        errors = verify_expected_outputs(expected)
        if errors:
            raise ContractError("generated output check failed:\n" + "\n".join(errors[:20]))
        action = "verified"
    print(
        json.dumps(
            {
                "action": action,
                "stations": len(contracts),
                "counts": site_summary["counts"],
                "catalogue_sha256": PINNED_CATALOGUE_SHA256,
                "summary_sha256": site_summary["summary_sha256"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractError as error:
        print(f"station-kit error: {error}", file=sys.stderr)
        raise SystemExit(1)
