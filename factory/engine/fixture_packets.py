from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from control_plane.common import ContractError, canonical_json_bytes, sha256_bytes, sha256_file

from .catalogue import StationCatalogue, _is_link_like, _load_json_strict, _safe_repository_path


REGISTRY_RELATIVE_PATH = "factory/fixture_packets/registry.json"
REGISTRY_SCHEMA_RELATIVE_PATH = "factory/fixture_packets/fixture-packet-adapter-index-v1.schema.json"
ADAPTER_SCHEMA_RELATIVE_PATH = "factory/fixture_packets/fixture-packet-adapter-v1.schema.json"
ADAPTERS_RELATIVE_DIRECTORY = "factory/fixture_packets/adapters"


@dataclass(frozen=True)
class FixturePacketAdapter:
    adapter_id: str
    adapter_sha256: str
    workbench_code: str
    title: str
    packet_kind: str
    runner: dict[str, Any]
    rehearsal_scope: str
    handoff_state: str
    construction_boundary: dict[str, bool]


class FixturePacketController:
    """Run hash-locked, registry-declared fixture packet adapters only.

    This is deliberately a fixed command grammar, not a general process runner.
    A reviewed adapter may choose its checked-in script and its hash-locked build
    inputs, but callers cannot select a script, add command tokens, or execute
    an arbitrary candidate.
    """

    def __init__(self, factory_root: Path) -> None:
        self.factory_root = factory_root.resolve()
        self.repository_root = self.factory_root.parent
        self.catalogue = StationCatalogue(self.factory_root)
        self.registry_document: dict[str, Any] = {}
        self.adapters = self._load_adapters()

    def _validator(self, relative_path: str, *, label: str) -> Draft202012Validator:
        schema_path = _safe_repository_path(
            self.repository_root, relative_path, field=f"{label} schema path"
        )
        schema = _load_json_strict(schema_path)
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as exc:
            raise ContractError(f"{label} schema is invalid: {exc.message}") from exc
        return Draft202012Validator(schema)

    def _validate_document(
        self,
        validator: Draft202012Validator,
        document: dict[str, Any],
        *,
        label: str,
    ) -> None:
        try:
            validator.validate(document)
        except ValidationError as exc:
            raise ContractError(f"{label} schema failure: {exc.message}") from exc

    def _locked_regular_file(self, relative_path: str, expected_sha256: str, *, field: str) -> Path:
        path = _safe_repository_path(self.repository_root, relative_path, field=field)
        if not path.is_file() or _is_link_like(path):
            raise ContractError(f"{field} is missing or not a regular file: {relative_path}")
        if sha256_file(path) != expected_sha256:
            raise ContractError(f"{field} SHA-256 differs: {relative_path}")
        return path

    def _validate_runner_assets(
        self,
        adapter: dict[str, Any],
        *,
        registry: dict[str, Any],
    ) -> None:
        runner = adapter["runner"]
        workbench_code = adapter["workbench_code"]
        workbench_prefix = f"wb{int(workbench_code[3:]):03d}_"
        workbenches_root = self.factory_root / "workbenches"
        workbench_root = workbenches_root / next(
            (
                path.name
                for path in workbenches_root.iterdir()
                if path.is_dir() and path.name.startswith(workbench_prefix)
            ),
            "",
        )
        if not workbench_root.is_dir() or _is_link_like(workbench_root):
            raise ContractError(f"{workbench_code}: workbench directory is missing or unsafe")

        script = self._locked_regular_file(
            runner["script_path"], runner["script_sha256"], field=f"{workbench_code}.runner.script"
        )
        if script.suffix != ".py" or not script.is_relative_to(workbench_root):
            raise ContractError(f"{workbench_code}: runner script is outside its workbench")

        options: set[str] = set()
        paths: set[str] = set()
        for item in runner["build"]["inputs"]:
            option = item["option"]
            if option in options:
                raise ContractError(f"{workbench_code}: repeated build input option: {option}")
            if item["path"] in paths:
                raise ContractError(f"{workbench_code}: repeated build input path: {item['path']}")
            options.add(option)
            paths.add(item["path"])
            input_path = self._locked_regular_file(
                item["path"], item["sha256"], field=f"{workbench_code}.runner.build_input"
            )
            if not input_path.is_relative_to(workbench_root):
                raise ContractError(f"{workbench_code}: build input is outside its workbench")

        _, contract = self.catalogue.verified_contract(registry)
        if contract["readiness"]["scientific_standing"] != "NONE":
            raise ContractError(f"{workbench_code}: packet adapter requires construction standing NONE")

    def _load_adapters(self) -> dict[str, FixturePacketAdapter]:
        registry_validator = self._validator(REGISTRY_SCHEMA_RELATIVE_PATH, label="fixture packet registry")
        adapter_validator = self._validator(ADAPTER_SCHEMA_RELATIVE_PATH, label="fixture packet adapter")
        registry_path = _safe_repository_path(
            self.repository_root, REGISTRY_RELATIVE_PATH, field="fixture packet registry path"
        )
        registry_document = _load_json_strict(registry_path)
        self._validate_document(registry_validator, registry_document, label="fixture packet registry")
        unsigned_registry = {
            key: value for key, value in registry_document.items() if key != "registry_sha256"
        }
        if sha256_bytes(canonical_json_bytes(unsigned_registry)) != registry_document["registry_sha256"]:
            raise ContractError("fixture packet registry self-hash does not match")
        self.registry_document = registry_document

        adapters_root = _safe_repository_path(
            self.repository_root, ADAPTERS_RELATIVE_DIRECTORY, field="fixture packet adapter directory"
        )
        if not adapters_root.is_dir() or _is_link_like(adapters_root):
            raise ContractError("fixture packet adapter directory is missing or unsafe")

        adapters: dict[str, FixturePacketAdapter] = {}
        paths: set[str] = set()
        for registration in registry_document["registrations"]:
            workbench_code = registration["workbench_code"]
            adapter_path_text = registration["adapter_path"]
            if workbench_code in adapters:
                raise ContractError(f"fixture packet registry repeats workbench: {workbench_code}")
            if adapter_path_text in paths:
                raise ContractError(f"fixture packet registry repeats adapter path: {adapter_path_text}")
            paths.add(adapter_path_text)

            adapter_path = self._locked_regular_file(
                adapter_path_text,
                registration["adapter_file_sha256"],
                field=f"{workbench_code}.adapter_file",
            )
            if not adapter_path.is_relative_to(adapters_root):
                raise ContractError(f"{workbench_code}: adapter path is outside the adapter directory")
            document = _load_json_strict(adapter_path)
            self._validate_document(adapter_validator, document, label=f"{workbench_code} fixture packet adapter")
            unsigned_adapter = {
                key: value for key, value in document.items() if key != "adapter_sha256"
            }
            if sha256_bytes(canonical_json_bytes(unsigned_adapter)) != document["adapter_sha256"]:
                raise ContractError(f"{workbench_code}: adapter self-hash does not match")
            if document["workbench_code"] != workbench_code:
                raise ContractError(f"{workbench_code}: registry and adapter workbench identity differ")

            catalogue_row = self.catalogue.resolve(workbench_code)
            self._validate_runner_assets(document, registry=catalogue_row)
            adapters[workbench_code] = FixturePacketAdapter(
                adapter_id=document["adapter_id"],
                adapter_sha256=document["adapter_sha256"],
                workbench_code=workbench_code,
                title=catalogue_row["title"],
                packet_kind=document["packet_kind"],
                runner=document["runner"],
                rehearsal_scope=document["rehearsal_scope"],
                handoff_state=document["handoff_state"],
                construction_boundary=document["construction_boundary"],
            )
        return adapters

    def list(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for workbench_code in sorted(self.adapters):
            adapter = self.adapters[workbench_code]
            registry = self.catalogue.resolve(workbench_code)
            _, contract = self.catalogue.verified_contract(registry)
            rows.append(
                {
                    "adapter_id": adapter.adapter_id,
                    "workbench_code": adapter.workbench_code,
                    "title": adapter.title,
                    "packet_kind": adapter.packet_kind,
                    "rehearsal_scope": adapter.rehearsal_scope,
                    "handoff_state": adapter.handoff_state,
                    "readiness_stage": registry["readiness_stage"],
                    "scientific_standing": contract["readiness"]["scientific_standing"],
                    "live_research_authorized": False,
                }
            )
        return rows

    def validate_draft(self, adapter_path: Path) -> dict[str, Any]:
        """Validate a prospective adapter without registering or running it."""

        document = _load_json_strict(adapter_path)
        adapter_validator = self._validator(
            ADAPTER_SCHEMA_RELATIVE_PATH, label="fixture packet adapter"
        )
        self._validate_document(adapter_validator, document, label="fixture packet adapter draft")
        unsigned_adapter = {
            key: value for key, value in document.items() if key != "adapter_sha256"
        }
        if sha256_bytes(canonical_json_bytes(unsigned_adapter)) != document["adapter_sha256"]:
            raise ContractError("fixture packet draft adapter self-hash does not match")

        catalogue_row = self.catalogue.resolve(document["workbench_code"])
        self._validate_runner_assets(document, registry=catalogue_row)
        registered = self.adapters.get(document["workbench_code"])
        exact_adapter_registered = (
            registered is not None
            and registered.adapter_id == document["adapter_id"]
            and registered.adapter_sha256 == document["adapter_sha256"]
        )
        return {
            "schema_version": 1,
            "diagnostic_type": "RESEARCH_FACTORY_FIXTURE_PACKET_DRAFT_CHECK",
            "valid": True,
            "adapter": {
                "adapter_id": document["adapter_id"],
                "adapter_sha256": document["adapter_sha256"],
                "workbench_code": document["workbench_code"],
                "packet_kind": document["packet_kind"],
                "rehearsal_scope": document["rehearsal_scope"],
                "handoff_state": document["handoff_state"],
            },
            "registry_status": {
                "workbench_has_registered_adapter": registered is not None,
                "exact_adapter_registered": exact_adapter_registered,
                "registration_changed": False,
            },
            "runner_execution": {
                "executed": False,
                "reason": "draft-check validates metadata and hash locks only",
            },
            "construction_boundary": document["construction_boundary"],
        }

    def plan_registration(self, adapter_path: Path) -> dict[str, Any]:
        """Produce a read-only registry addition plan for one validated draft."""

        draft = self.validate_draft(adapter_path)
        adapter = draft["adapter"]
        adapters_root = _safe_repository_path(
            self.repository_root,
            ADAPTERS_RELATIVE_DIRECTORY,
            field="fixture packet adapter directory",
        )
        source = adapter_path.resolve()
        if not source.is_relative_to(adapters_root) or source.suffix != ".json":
            raise ContractError(
                "registration planning requires an adapter JSON file under factory/fixture_packets/adapters"
            )
        adapter_relative_path = source.relative_to(self.repository_root).as_posix()
        registrations = [dict(row) for row in self.registry_document["registrations"]]
        if any(row["workbench_code"] == adapter["workbench_code"] for row in registrations):
            raise ContractError(
                f"{adapter['workbench_code']} already has a registered fixture packet adapter; "
                "replacement requires a separate reviewed change"
            )
        if any(row["adapter_path"] == adapter_relative_path for row in registrations):
            raise ContractError("adapter path is already registered")
        if any(item.adapter_id == adapter["adapter_id"] for item in self.adapters.values()):
            raise ContractError(f"adapter ID is already registered: {adapter['adapter_id']}")

        proposed_registration = {
            "workbench_code": adapter["workbench_code"],
            "adapter_path": adapter_relative_path,
            "adapter_file_sha256": sha256_file(source),
        }
        proposed_registrations = sorted(
            [*registrations, proposed_registration], key=lambda row: row["workbench_code"]
        )
        unsigned_registry = {
            "schema_version": self.registry_document["schema_version"],
            "registrations": proposed_registrations,
        }
        proposed_registry_sha256 = sha256_bytes(canonical_json_bytes(unsigned_registry))
        return {
            "schema_version": 1,
            "diagnostic_type": "RESEARCH_FACTORY_FIXTURE_PACKET_REGISTRATION_PLAN",
            "valid": True,
            "adapter": adapter,
            "registration_plan": {
                "operation": "ADD_AFTER_HUMAN_REVIEW",
                "registry_path": REGISTRY_RELATIVE_PATH,
                "registry_mutated": False,
                "proposed_registration": proposed_registration,
                "proposed_registry_sha256": proposed_registry_sha256,
            },
            "runner_execution": draft["runner_execution"],
            "construction_boundary": draft["construction_boundary"],
        }

    def _adapter(self, workbench: str) -> FixturePacketAdapter:
        try:
            workbench_code = self.catalogue.resolve(workbench)["workbench_code"]
        except ContractError as exc:
            raise ContractError(f"no allowlisted fixture packet adapter for {workbench!r}") from exc
        adapter = self.adapters.get(workbench_code)
        if adapter is None:
            available = ", ".join(sorted(self.adapters))
            raise ContractError(
                f"no allowlisted fixture packet adapter for {workbench!r}; available: {available}"
            )
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
        runner = adapter.runner
        script = _safe_repository_path(
            self.repository_root, runner["script_path"], field=f"{adapter.workbench_code}.runner.script"
        )
        command = [sys.executable, str(script)]
        if action == "build":
            if output is None:
                raise ContractError("fixture packet build requires an output directory")
            command.append(runner["build"]["verb"])
            for item in runner["build"]["inputs"]:
                input_path = _safe_repository_path(
                    self.repository_root,
                    item["path"],
                    field=f"{adapter.workbench_code}.runner.build_input",
                )
                command.extend([item["option"], str(input_path)])
            command.extend([runner["build"]["output_option"], str(output)])
            return command
        if action == "verify":
            if package is None:
                raise ContractError("fixture packet verification requires a package directory")
            return [*command, runner["verify"]["verb"], str(package)]
        if action == "rehearse":
            if package is None or output is None or operator_id is None:
                raise ContractError("fixture packet rehearsal requires package, operator and output")
            rehearsal = runner["rehearse"]
            return [
                *command,
                rehearsal["verb"],
                str(package),
                rehearsal["operator_option"],
                operator_id,
                rehearsal["output_option"],
                str(output),
            ]
        raise ContractError(f"unsupported fixture packet action: {action}")

    def _run(self, adapter: FixturePacketAdapter, command: list[str]) -> dict[str, Any]:
        try:
            completed = subprocess.run(
                command,
                cwd=self.factory_root,
                text=True,
                encoding="utf-8",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=adapter.runner["maximum_runtime_seconds"],
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ContractError(f"fixture packet adapter could not complete: {exc}") from exc
        if len(completed.stdout.encode("utf-8")) > adapter.runner["maximum_stdout_bytes"]:
            raise ContractError("fixture packet adapter exceeded its output limit")
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}"
            raise ContractError(f"fixture packet adapter failed: {detail[:800]}")
        try:
            value = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ContractError("fixture packet adapter did not return one JSON object") from exc
        if not isinstance(value, dict):
            raise ContractError("fixture packet adapter returned a non-object result")
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
        operator_prefix = "demo:"
        if action == "rehearse" and (
            operator_id is None or not operator_id.lower().startswith(operator_prefix)
        ):
            raise ContractError("fixture packet rehearsal only accepts a demo: operator identity")
        command = self._command(
            adapter,
            action,
            output=output.resolve() if output is not None else None,
            package=package.resolve() if package is not None else None,
            operator_id=operator_id,
        )
        result = self._run(adapter, command)
        return {
            "schema_version": 1,
            "operation_type": "RESEARCH_FACTORY_FIXTURE_PACKET",
            "action": action.upper(),
            "adapter": {
                "adapter_id": adapter.adapter_id,
                "adapter_sha256": adapter.adapter_sha256,
                "workbench_code": adapter.workbench_code,
                "packet_kind": adapter.packet_kind,
                "rehearsal_scope": adapter.rehearsal_scope,
                "handoff_state": adapter.handoff_state,
            },
            "result": result,
            "construction_boundary": adapter.construction_boundary,
        }
