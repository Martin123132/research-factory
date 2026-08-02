from __future__ import annotations

import copy
from typing import Any


ADAPTER_ID = "DIGITAL_COMPRESSION_V1"
ADAPTER_VERSION = "1.0.0"


def _metric(
    metric_id: str,
    label: str,
    unit: str,
    direction: str,
    aggregation: str,
    baseline_binding: str | None,
    measurement_grade: str,
    decision_threshold: float | str | None,
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
        "required": True,
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
    """Apply the closed fixed-public-corpus exact-compression adapter.

    Governance, readiness and scientific authority are derived here. They are
    deliberately absent from the station override.
    """

    contract = copy.deepcopy(draft)
    benchmark = override["official_benchmark"]
    starter = override["entry_gate"]
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
        "verifier_status": "MANUAL_PROTOCOL",
        "verifier_path_or_protocol": protocol["path"],
        "verifier_sha256": protocol["sha256"],
        "pass_rule": override["truth"]["pass_rule"],
        "candidate_claim_is_authoritative": False,
        "failure_behavior": "FAIL_CLOSED",
    }

    exact_round_trip = _criterion(
        "exact-round-trip",
        "The restored input must be byte-identical; any mismatch invalidates the run.",
        "EXACT",
        "round_trip_fraction",
        1.0,
        "fraction",
        executable=True,
        verifier_path=verifier["path"],
        verifier_sha256=verifier["sha256"],
    )
    deterministic_archive = _criterion(
        "deterministic-archive",
        "Two identical encodes must produce byte-identical archive hashes.",
        "EXACT",
        "determinism_fraction",
        1.0,
        "fraction",
        executable=True,
        verifier_path=verifier["path"],
        verifier_sha256=verifier["sha256"],
    )
    official_corpus = _criterion(
        "official-corpus-identity",
        f"The official input must be {benchmark['input_bytes']} bytes and match the published MD5 and SHA-1 commitments.",
        "EXACT",
        "official_corpus_identity",
        "TRUE",
        "boolean",
        executable=False,
        verifier_path=verifier["path"],
        verifier_sha256=verifier["sha256"],
    )
    self_contained = _criterion(
        "self-contained-package",
        "The counted package must use no undeclared network, installation, dictionary, GPU or outside file.",
        "EXACT",
        "self_contained",
        "TRUE",
        "boolean",
        executable=False,
        verifier_path=verifier["path"],
        verifier_sha256=verifier["sha256"],
    )
    size_accounting = _criterion(
        "official-size-accounting",
        "Every required program, archive and command-option byte must be counted under one permitted Hutter formula.",
        "EXACT",
        "official_counted_size_bytes",
        f"LESS_THAN_{benchmark['official_record_bytes']}",
        "bytes",
        executable=False,
        verifier_path=verifier["path"],
        verifier_sha256=verifier["sha256"],
    )
    resource_gate = _criterion(
        "official-resource-limits",
        "Each required executable must independently satisfy the official CPU, RAM and temporary-disk ceilings.",
        "MAXIMUM",
        "resource_limits_pass",
        "TRUE",
        "boolean",
        executable=False,
        verifier_path=verifier["path"],
        verifier_sha256=verifier["sha256"],
    )

    contract["measurement"] = {
        "criteria": [
            exact_round_trip,
            deterministic_archive,
            official_corpus,
            self_contained,
            size_accounting,
            resource_gate,
        ],
        "metrics": [
            _metric("round_trip_fraction", "Inputs restored exactly", "fraction", "EXACT", "EXACT", None, "REPRODUCTION", 1.0),
            _metric("determinism_fraction", "Repeated archive hashes equal", "fraction", "EXACT", "EXACT", None, "REPRODUCTION", 1.0),
            _metric("official_corpus_identity", "Official corpus commitments pass", "boolean", "EXACT", "EXACT", "published enwik9 commitments", "NOT_IMPLEMENTED", "TRUE"),
            _metric("self_contained", "Package is self-contained", "boolean", "EXACT", "EXACT", "official Hutter rules", "NOT_IMPLEMENTED", "TRUE"),
            _metric("official_counted_size_bytes", "Official counted package size", "bytes", "MINIMIZE", "SUM", f"official Hutter record observed {benchmark['record_observed_on']}", "ADVISORY", benchmark["official_record_bytes"]),
            _metric("resource_limits_pass", "Official resource ceilings pass", "boolean", "EXACT", "EXACT", "official Hutter rules", "NOT_IMPLEMENTED", "TRUE"),
            _metric("practical_tco_gbp", "Frozen practical archive total cost", "GBP", "MINIMIZE", "SUM", economics["comparator"], "ADVISORY", economics["decision_threshold"]),
        ],
        "tolerance": {
            "policy": "MIXED",
            "logical_tolerance": 0,
            "reproduction_rules": [
                "Restored bytes, corpus commitments, package bytes and deterministic archive hashes use zero tolerance.",
                "Official Hutter score and practical archive utility are separate result scopes.",
                "Blind validation hides the claimed score, not the deliberately public corpus.",
            ],
            "reproduction_equivalence": [
                {"rule_id": "exact-restoration", "metric_id": "round_trip_fraction", "mode": "EXACT", "value": 1.0, "unit": "fraction", "zero_reference_policy": "NOT_APPLICABLE"},
                {"rule_id": "exact-determinism", "metric_id": "determinism_fraction", "mode": "EXACT", "value": 1.0, "unit": "fraction", "zero_reference_policy": "NOT_APPLICABLE"},
                {"rule_id": "exact-counted-size", "metric_id": "official_counted_size_bytes", "mode": "EXACT", "value": 0, "unit": "bytes difference", "zero_reference_policy": "REQUIRE_EXACT_ZERO"},
            ],
            "improvement_thresholds": [
                {"rule_id": "official-record-improvement", "metric_id": "official_counted_size_bytes", "mode": "ABSOLUTE", "value": benchmark["official_record_bytes"] - 1, "unit": "maximum bytes", "zero_reference_policy": "NOT_APPLICABLE"},
                {"rule_id": "official-one-percent-floor", "metric_id": "official_counted_size_bytes", "mode": "ABSOLUTE", "value": benchmark["one_percent_maximum_bytes"], "unit": "maximum bytes", "zero_reference_policy": "NOT_APPLICABLE"},
                {"rule_id": "minimum-practical-tco-gain", "metric_id": "practical_tco_gbp", "mode": "RELATIVE", "value": economics["decision_threshold"], "unit": "fraction", "zero_reference_policy": "USE_ABSOLUTE_RULE"},
            ],
            "safety_limits": [],
            "stochastic_protocol": {
                "required": False,
                "repetitions": None,
                "seed_policy": None,
                "aggregation": None,
                "confidence_rule": None,
                "permitted_runner_class": None,
            },
        },
        "public_inputs": {
            "status": "UNFROZEN",
            "manifest_path": paths["public_input_manifest"],
            "content_commitment_sha256": None,
        },
        "hidden_inputs": {"policy": "NOT_APPLICABLE", "commitment_path": None},
        "baseline": {"status": "UNFROZEN", "definition_path": None, "result_path": None},
        "compute_budget": {
            "status": "UNDEFINED",
            "wall_time_seconds": None,
            "cpu_cores": 1,
            "memory_bytes": 10_000_000_000,
            "energy_measurement_required": False,
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
