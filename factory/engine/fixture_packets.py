from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from control_plane.common import ControlPlaneError

from .catalogue import StationCatalogue


MAX_ADAPTER_OUTPUT_BYTES = 1_048_576
ADAPTER_TIMEOUT_SECONDS = 180


@dataclass(frozen=True)
class FixturePacketAdapter:
    workbench_code: str
    title: str
    packet_kind: str
    script_relative_path: str
    rehearsal_scope: str
    handoff_state: str
    live_research_authorized: bool = False


ADAPTERS: tuple[FixturePacketAdapter, ...] = (
    FixturePacketAdapter(
        workbench_code="WB-001",
        title="General-purpose lossless compression",
        packet_kind="CANDIDATE_PACKAGE_COMMISSIONING",
        script_relative_path="workbenches/wb001_lossless_compression/runner/candidate_package.py",
        rehearsal_scope="Known-safe zlib level-9 fixture only; demo identity only.",
        handoff_state="BLOCKED_AWAITING_TWO_OTHER_HUMAN_RERUNS",
    ),
    FixturePacketAdapter(
        workbench_code="WB-013",
        title="Travelling-salesperson route kernel",
        packet_kind="ENTRY_FIXTURE_CONSTRUCTION",
        script_relative_path="workbenches/wb013_travelling_salesperson_route_kernel/scripts/entry_package.py",
        rehearsal_scope="Known-safe 10-node Held-Karp fixture only; demo identity only.",
        handoff_state="NOT_ELIGIBLE_ENTRY_ONLY",
    ),
)
ADAPTER_BY_CODE = {adapter.workbench_code: adapter for adapter in ADAPTERS}


class FixturePacketController:
    """Run only allowlisted Factory fixture packet adapters.

    This is deliberately a dispatcher, not a general process runner. Callers
    cannot select a script, add command tokens, or turn a fixture rehearsal
    into arbitrary candidate execution.
    """

    def __init__(self, factory_root: Path) -> None:
        self.factory_root = factory_root.resolve()
        self.catalogue = StationCatalogue(self.factory_root)

    def list(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for adapter in ADAPTERS:
            registry = self.catalogue.resolve(adapter.workbench_code)
            _, contract = self.catalogue.verified_contract(registry)
            rows.append(
                {
                    "workbench_code": adapter.workbench_code,
                    "title": adapter.title,
                    "packet_kind": adapter.packet_kind,
                    "rehearsal_scope": adapter.rehearsal_scope,
                    "handoff_state": adapter.handoff_state,
                    "readiness_stage": registry["readiness_stage"],
                    "scientific_standing": contract["readiness"]["scientific_standing"],
                    "live_research_authorized": adapter.live_research_authorized,
                }
            )
        return rows

    def _adapter(self, workbench: str) -> FixturePacketAdapter:
        normalized = workbench.upper()
        adapter = ADAPTER_BY_CODE.get(normalized)
        if adapter is None:
            available = ", ".join(sorted(ADAPTER_BY_CODE))
            raise ControlPlaneError(
                f"no allowlisted fixture packet adapter for {workbench!r}; available: {available}"
            )
        registry = self.catalogue.resolve(adapter.workbench_code)
        self.catalogue.verified_contract(registry)
        script = self.factory_root / Path(*adapter.script_relative_path.split("/"))
        if not script.is_file() or script.is_symlink():
            raise ControlPlaneError(f"fixture packet adapter is missing or unsafe: {script}")
        return adapter

    def _command(
        self,
        adapter: FixturePacketAdapter,
        action: str,
        *,
        output: Path | None = None,
        package: Path | None = None,
        operator_id: str | None = None,
    ) -> list[str]:
        script = self.factory_root / Path(*adapter.script_relative_path.split("/"))
        command = [sys.executable, str(script), action]
        if action == "build":
            if output is None:
                raise ControlPlaneError("fixture packet build requires an output directory")
            if adapter.workbench_code == "WB-001":
                root = self.factory_root / "workbenches" / "wb001_lossless_compression"
                command.extend(
                    [
                        "--submission",
                        str(root / "examples" / "zlib_level9" / "submission.json"),
                        "--result",
                        str(root / "results" / "qualification_v0_2" / "candidate_result.json"),
                        "--comparison",
                        str(root / "results" / "qualification_v0_2" / "frontier_comparison.json"),
                        "--output",
                        str(output),
                    ]
                )
            else:
                command.extend(["--output", str(output)])
            return command
        if action == "verify":
            if package is None:
                raise ControlPlaneError("fixture packet verification requires a package directory")
            return [*command, str(package)]
        if action == "rehearse":
            if package is None or output is None or operator_id is None:
                raise ControlPlaneError("fixture packet rehearsal requires package, operator and output")
            return [*command, str(package), "--operator-id", operator_id, "--output", str(output)]
        raise ControlPlaneError(f"unsupported fixture packet action: {action}")

    def _run(self, adapter: FixturePacketAdapter, command: list[str]) -> dict[str, Any]:
        try:
            completed = subprocess.run(
                command,
                cwd=self.factory_root,
                text=True,
                encoding="utf-8",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=ADAPTER_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ControlPlaneError(f"fixture packet adapter could not complete: {exc}") from exc
        if len(completed.stdout.encode("utf-8")) > MAX_ADAPTER_OUTPUT_BYTES:
            raise ControlPlaneError("fixture packet adapter exceeded its output limit")
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}"
            raise ControlPlaneError(f"fixture packet adapter failed: {detail[:800]}")
        try:
            value = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ControlPlaneError("fixture packet adapter did not return one JSON object") from exc
        if not isinstance(value, dict):
            raise ControlPlaneError("fixture packet adapter returned a non-object result")
        return value

    def execute(
        self,
        action: str,
        *,
        workbench: str,
        output: Path | None = None,
        package: Path | None = None,
        operator_id: str | None = None,
    ) -> dict[str, Any]:
        adapter = self._adapter(workbench)
        if action == "rehearse" and (operator_id is None or not operator_id.lower().startswith("demo:")):
            raise ControlPlaneError("fixture packet rehearsal only accepts a demo: operator identity")
        command = self._command(
            adapter,
            action,
            output=output.resolve() if output is not None else None,
            package=package.resolve() if package is not None else None,
            operator_id=operator_id,
        )
        result = self._run(adapter, command)
        boundary = {
            "scientific_evidence": False,
            "counts_as_independent_reproduction": False,
            "eligible_for_promotion": False,
            "live_research_authorized": False,
        }
        return {
            "schema_version": 1,
            "operation_type": "RESEARCH_FACTORY_FIXTURE_PACKET",
            "action": action.upper(),
            "adapter": {
                "workbench_code": adapter.workbench_code,
                "packet_kind": adapter.packet_kind,
                "rehearsal_scope": adapter.rehearsal_scope,
                "handoff_state": adapter.handoff_state,
            },
            "result": result,
            "construction_boundary": boundary,
        }
