from __future__ import annotations

import copy
from typing import Any


ADAPTER_ID = "DIGITAL_OPTIMIZATION_V1"
ADAPTER_VERSION = "1.0.0"
PROBLEM_PLUGIN = "SYMMETRIC_TSP_V1"


def _metric(
    metric_id: str,
    label: str,
    unit: str,
    direction: str,
    aggregation: str,
    baseline_binding: str | None,
    measurement_grade: str,
    decision_threshold: float | str | None,
    *,
    required: bool = True,
) -> dict[str, Any]:
    return {
        "metric_id": metric_id,
        "label": label,
        "unit": unit,
        "direction": direction,
        "aggregation": aggregation,
        "baseline_binding": baseline_binding,
        "measurement_grade": measurement_grade,
        "decision_threshold": decision_threshold,
        "required": required,
    }


def _criterion(
    criterion_id: str,
    statement: str,
    comparison: str,
    metric_id: str | None,
    threshold: float | str | None,
    unit: str | None,
    *,
    executable: bool,
    verifier_path: str,
    verifier_sha256: str,
) -> dict[str, Any]:
    return {
        "criterion_id": criterion_id,
        "statement": statement,
        "comparison": comparison,
        "metric_id": metric_id,
        "threshold": threshold,
        "unit": unit,
        "machine_check": "EXECUTABLE" if executable else "NOT_IMPLEMENTED",
        "verifier_path_or_protocol": verifier_path if executable else None,
        "verifier_sha256": verifier_sha256 if executable else None,
        "failure_behavior": "FAIL_CLOSED",
        "score_may_override_failure": False,
    }


def hydrate_contract(
    draft: dict[str, Any],
    override: dict[str, Any],
    asset_by_role: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Fit the closed symmetric-TSP plugin to a catalogue draft.

    DIGITAL_OPTIMIZATION_V1 is a family boundary, not a universal optimiser.
    This first version accepts only the SYMMETRIC_TSP_V1 plugin and derives
    governance/readiness here so a station dossier cannot promote itself.
    """

    if override["problem_plugin"] != PROBLEM_PLUGIN:
        raise ValueError(f"unsupported optimisation plugin: {override['problem_plugin']}")

    contract = copy.deepcopy(draft)
    benchmark = override["official_benchmark"]
    starter = override["entry_gate"]
    scoring = override["scoring"]
    economics = override["practical_accounting"]
    paths = override["paths"]
    verifier = asset_by_role["truth_verifier"]
    protocol = asset_by_role["runner_protocol"]

    contract["source"]["factory_path"] = override["implementation_root"]
    contract["source"]["implementation_contract_version"] = override["implementation_version"]
    contract["commissioning"] = {
        "profile_status": "ADAPTER_BOUND",
        "adapter_id": ADAPTER_ID,
        "adapter_version": ADAPTER_VERSION,
        "dossier_path": asset_by_role["commissioning_override"]["path"],
        "dossier_sha256": asset_by_role["commissioning_override"]["sha256"],
    }
    contract["problem"]["structured_predicate"] = {
        "status": "DEFINED",
        "subject_or_input_population": override["truth"]["subject_or_input_population"],
        "required_output": override["truth"]["required_output"],
        "verifier_status": "EXECUTABLE",
        "verifier_path_or_protocol": verifier["path"],
        "verifier_sha256": verifier["sha256"],
        "pass_rule": override["truth"]["pass_rule"],
        "candidate_claim_is_authoritative": False,
        "failure_behavior": "FAIL_CLOSED",
    }

    executable = [
        _criterion(
            "supported-instance",
            "The input must be a symmetric TSP instance in the implemented EXPLICIT/FULL_MATRIX subset.",
            "EXACT", "supported_instance", "TRUE", "boolean", executable=True,
            verifier_path=verifier["path"], verifier_sha256=verifier["sha256"],
        ),
        _criterion(
            "hamiltonian-cycle",
            "The submitted tour must visit every numbered node exactly once and close back to its start.",
            "EXACT", "tour_valid", "TRUE", "boolean", executable=True,
            verifier_path=verifier["path"], verifier_sha256=verifier["sha256"],
        ),
        _criterion(
            "exact-length-accounting",
            "The trusted verifier must independently sum every matrix edge including the closing edge with zero tolerance.",
            "EXACT", "length_accounting_difference", 0, "integer cost units", executable=True,
            verifier_path=verifier["path"], verifier_sha256=verifier["sha256"],
        ),
        _criterion(
            "same-seed-determinism",
            "Two runs with the same seed must return the same canonical cycle and route length.",
            "EXACT", "determinism_fraction", 1.0, "fraction", executable=True,
            verifier_path=verifier["path"], verifier_sha256=verifier["sha256"],
        ),
    ]
    external = [
        _criterion(
            "official-input-identity",
            "Each official TSPLIB instance must be source-pinned and interpreted under its declared distance convention.",
            "EXACT", "official_input_identity", "TRUE", "boolean", executable=False,
            verifier_path=verifier["path"], verifier_sha256=verifier["sha256"],
        ),
        _criterion(
            "promotion-resource-boundary",
            "Runtime, memory and energy comparisons must use a frozen promotion-grade runner class.",
            "MAXIMUM", "resource_budget_pass", "TRUE", "boolean", executable=False,
            verifier_path=verifier["path"], verifier_sha256=verifier["sha256"],
        ),
    ]

    contract["measurement"] = {
        "criteria": [*executable, *external],
        "metrics": [
            _metric("supported_instance", "Implemented instance subset accepted", "boolean", "EXACT", "EXACT", benchmark["suite_id"], "REPRODUCTION", "TRUE"),
            _metric("tour_valid", "Hamiltonian cycle is valid", "boolean", "EXACT", "EXACT", "independent verifier", "REPRODUCTION", "TRUE"),
            _metric("route_length", "Independently calculated closed-tour length", "integer cost units", "MINIMIZE", "EXACT", "same frozen instance and distance convention", "REPRODUCTION", None),
            _metric("length_accounting_difference", "Difference between repeated trusted length calculations", "integer cost units", "EXACT", "EXACT", "independent verifier", "REPRODUCTION", 0),
            _metric("determinism_fraction", "Equivalent same-seed canonical cycles", "fraction", "EXACT", "EXACT", "two trusted-local entry runs", "REPRODUCTION", 1.0),
            _metric("optimality_gap_fraction", "Gap to a frozen proven optimum or comparator", "fraction", "MINIMIZE", "MEDIAN", "official optimum or frozen baseline", "ADVISORY", scoring["minimum_improvement_fraction"]),
            _metric("solve_elapsed_ns", "Candidate solve elapsed time", "nanoseconds", "MINIMIZE", "MEDIAN", "frozen runner class", "ADVISORY", None, required=False),
            _metric("peak_rss_bytes", "Peak candidate process-tree memory", "bytes", "MINIMIZE", "MAX", "frozen runner class", "ADVISORY", None, required=False),
            _metric("practical_annual_cost_gbp", "Frozen practical routing annual cost", "GBP/year", "MINIMIZE", "SUM", economics["comparator"], "ADVISORY", economics["decision_threshold"]),
        ],
        "tolerance": {
            "policy": "MIXED",
            "logical_tolerance": 0,
            "reproduction_rules": [
                "Instance identity, node coverage and route-length arithmetic use zero tolerance.",
                "Equivalent rotations and reversals of a symmetric cycle are canonicalised before comparison.",
                "A claimed stochastic improvement requires the declared multi-seed protocol; one lucky run is not evidence.",
                "Blind validation withholds the claimed score, not deliberately public TSPLIB instances.",
            ],
            "reproduction_equivalence": [
                {"rule_id": "valid-tour", "metric_id": "tour_valid", "mode": "EXACT", "value": "TRUE", "unit": "boolean", "zero_reference_policy": "NOT_APPLICABLE"},
                {"rule_id": "exact-route-length-accounting", "metric_id": "length_accounting_difference", "mode": "EXACT", "value": 0, "unit": "integer cost units", "zero_reference_policy": "REQUIRE_EXACT_ZERO"},
                {"rule_id": "same-seed-cycle", "metric_id": "determinism_fraction", "mode": "EXACT", "value": 1.0, "unit": "fraction", "zero_reference_policy": "NOT_APPLICABLE"},
            ],
            "improvement_thresholds": [
                {"rule_id": "minimum-route-improvement", "metric_id": "route_length", "mode": "RELATIVE", "value": scoring["minimum_improvement_fraction"], "unit": "fraction below frozen comparator", "zero_reference_policy": "USE_ABSOLUTE_RULE"},
                {"rule_id": "minimum-practical-gain", "metric_id": "practical_annual_cost_gbp", "mode": "RELATIVE", "value": economics["decision_threshold"], "unit": "fraction below frozen comparator", "zero_reference_policy": "USE_ABSOLUTE_RULE"},
            ],
            "safety_limits": [],
            "stochastic_protocol": {
                "required": True,
                "repetitions": scoring["stochastic_repetitions"],
                "seed_policy": scoring["seed_policy"],
                "aggregation": "median route length; report p95 elapsed time and maximum memory",
                "confidence_rule": scoring["confidence_rule"],
                "permitted_runner_class": "promotion-grade runner not yet implemented",
            },
        },
        "public_inputs": {
            "status": "UNFROZEN",
            "manifest_path": paths["public_input_manifest"],
            "content_commitment_sha256": None,
        },
        "hidden_inputs": {"policy": "REQUIRED", "commitment_path": None},
        "baseline": {
            "status": "UNFROZEN",
            "definition_path": asset_by_role["entry_baseline_definition"]["path"],
            "result_path": asset_by_role["entry_baseline_result"]["path"],
        },
        "compute_budget": {
            "status": "UNDEFINED",
            "wall_time_seconds": None,
            "cpu_cores": None,
            "memory_bytes": None,
            "energy_measurement_required": True,
        },
        "economic_or_physical_accounting": {
            "required": True,
            "applicability": "REQUIRED",
            "structured": True,
            "scenario_path": paths["economic_scenario"],
            "scenario_version": economics["scenario_version"],
            "formula": economics["formula"],
            "system_boundary": economics["system_boundary"],
            "included_costs": economics["included_costs"],
            "comparator": economics["comparator"],
            "decision_threshold": economics["decision_threshold"],
        },
    }
    contract["starter_pack"] = {
        "entry_gate_required": True,
        "credential_neutral": True,
        "target_duration_minutes": starter["target_duration_minutes"],
        "brief": starter["brief"],
        "fixture_status": "KNOWN_ANSWER_READY",
        "command": starter["command"],
        "expected_outputs": starter["expected_outputs"],
    }
    contract["runner"] = {
        "protocol_status": "IMPLEMENTED",
        "protocol_path": paths["runner_protocol"],
        "isolation_status": "NOT_DEFINED",
        "isolation_policy_path": paths["isolation_policy"],
        "network_policy": "NOT_DEFINED",
        "trusted_code_only": True,
        "arbitrary_public_code_allowed": False,
        "promotion_grade": False,
    }
    contract["reproduction"]["identity_assurance"] = "SELF_ASSERTED_LOCAL"
    contract["blind_evaluation"]["evaluator_status"] = "LOCAL_COMMISSIONING_ONLY"

    facets = dict(contract["readiness"]["facets"])
    facets.update(
        {
            "lane_specific_starter_pack": True,
            "structured_predicate": True,
            "independent_verifier": True,
            "structured_metrics": True,
            "declared_tolerances": True,
            "frozen_public_inputs": False,
            "pinned_baseline": False,
            "executable_entry_gate": True,
            "runner_protocol": True,
            "isolation_policy": True,
            "blind_evaluator": True,
            "production_identity": False,
            "promotion_grade_runner": False,
            "live_authorization": False,
        }
    )
    contract["readiness"] = {
        "current_stage": "CONTRACT_DRAFT",
        "live_research_enabled": False,
        "scientific_standing": "NONE",
        "promotion_claims_allowed": False,
        "facets": facets,
        "unresolved": sorted(override["external_limitations"]),
    }
    contract["provenance"]["referenced_assets"] = [
        asset_by_role[role] for role in sorted(asset_by_role)
    ]
    return contract
