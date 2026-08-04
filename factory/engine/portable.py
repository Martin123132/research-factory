from __future__ import annotations

import json
import os
import platform
import shutil
import sys
import uuid
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError

from control_plane.common import (
    ContractError,
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
    utc_now,
    utc_text,
    validate_id,
    validate_sha256,
    write_json,
)

from . import ENGINE_VERSION
from .catalogue import StationCatalogue, contract_bytes


OPERATING_MODES = {"HANGAR_CONSTRUCTION", "SYNTHETIC_COMMISSIONING"}
EVIDENCE_KINDS = {
    "CONSTRUCTION",
    "CANDIDATE",
    "NEGATIVE_RESULT",
    "REPRODUCTION",
    "DISPUTE",
    "SHIFT_REPORT",
}
MAX_FILES = 10_000
MAX_TOTAL_BYTES = 512 * 1024 * 1024
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_PACKAGE_ENTRIES = 25_000


def _is_link_like(path: Path) -> bool:
    junction_check = getattr(path, "is_junction", None)
    return path.is_symlink() or bool(junction_check and junction_check())


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ContractError(f"non-finite JSON number is not allowed: {value}")


def _load_json_strict(path: Path) -> dict[str, Any]:
    try:
        if not path.is_file() or _is_link_like(path):
            raise ContractError(f"JSON input is not a regular file: {path}")
        if path.stat().st_size > MAX_JSON_BYTES:
            raise ContractError(f"JSON input exceeds the metadata size limit: {path}")
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_json_constant,
        )
    except ContractError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"could not load JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"expected a JSON object in {path}")
    return value


def _safe_relative(value: str, *, field: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise ContractError(f"{field} must be a non-empty relative path")
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    if (
        value != posix.as_posix()
        or "\\" in value
        or posix.is_absolute()
        or windows.is_absolute()
        or windows.drive
        or any(part in {"", ".", ".."} for part in posix.parts)
    ):
        raise ContractError(f"{field} is not a canonical relative path")
    return posix


def _inventory(source: Path) -> tuple[Path, list[dict[str, Any]]]:
    source = source.resolve()
    if _is_link_like(source):
        raise ContractError("evidence source must not be a symbolic link or junction")
    if source.is_file():
        base = source.parent
        paths = [source]
    elif source.is_dir():
        paths = []
        for path in source.rglob("*"):
            if _is_link_like(path):
                raise ContractError(
                    "evidence directories must not contain symbolic links or junctions"
                )
            if path.is_file():
                paths.append(path)
                if len(paths) > MAX_FILES:
                    raise ContractError("evidence package exceeds the file-count limit")
        paths.sort()
        base = source
    else:
        raise ContractError(f"evidence source does not exist: {source}")
    if not paths:
        raise ContractError("evidence package must contain at least one regular file")
    if len(paths) > MAX_FILES:
        raise ContractError("evidence package exceeds the file-count limit")
    files: list[dict[str, Any]] = []
    total = 0
    for path in paths:
        relative = path.relative_to(base).as_posix()
        _safe_relative(relative, field="evidence file path")
        size = path.stat().st_size
        total += size
        if total > MAX_TOTAL_BYTES:
            raise ContractError("evidence package exceeds the total-byte limit")
        files.append({"path": relative, "bytes": size, "sha256": sha256_file(path)})
    return base, files


def _environment() -> dict[str, Any]:
    executable = Path(sys.executable)
    if not executable.is_file():
        raise ContractError("Python executable cannot be hashed")
    return {
        "python": {
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
            "executable_sha256": sha256_file(executable),
        },
        "platform": {
            "system": platform.system() or "UNKNOWN",
            "release": platform.release() or "UNKNOWN",
            "machine": platform.machine() or "UNKNOWN",
        },
    }


class PortableEvidencePackage:
    """Create and verify provider-neutral, explicitly non-scientific packages."""

    def __init__(self, factory_root: Path) -> None:
        self.factory_root = factory_root.resolve()
        self.catalogue = StationCatalogue(self.factory_root)
        self.schema_path = (
            Path(__file__).resolve().parent
            / "schemas"
            / "portable-evidence-package-v1.schema.json"
        )
        self.schema = _load_json_strict(self.schema_path)
        try:
            Draft202012Validator.check_schema(self.schema)
        except SchemaError as exc:
            raise ContractError(f"portable package schema is invalid: {exc.message}") from exc
        self.validator = Draft202012Validator(self.schema, format_checker=FormatChecker())

    def _validate(self, document: dict[str, Any]) -> None:
        try:
            self.validator.validate(document)
        except ValidationError as exc:
            raise ContractError(f"portable package schema failure: {exc.message}") from exc

    def create(
        self,
        *,
        workbench: str,
        attempt_id: str,
        operator_id: str,
        operating_mode: str,
        evidence_kind: str,
        summary: str,
        commands: list[str],
        seeds: list[str],
        stochastic: bool,
        source: Path,
        output: Path,
    ) -> dict[str, Any]:
        validate_id(attempt_id, field="attempt_id")
        validate_id(operator_id, field="operator_id")
        operating_mode = operating_mode.upper()
        evidence_kind = evidence_kind.upper()
        if operating_mode not in OPERATING_MODES:
            raise ContractError("portable packages cannot authorize live research")
        if evidence_kind not in EVIDENCE_KINDS:
            raise ContractError(f"unknown evidence kind: {evidence_kind}")
        if not isinstance(summary, str) or len(summary.strip()) < 8:
            raise ContractError("method summary must contain at least eight characters")
        if not commands or not all(
            isinstance(value, str) and value.strip() for value in commands
        ):
            raise ContractError("at least one exact command is required")
        if len(seeds) != len(set(seeds)) or not all(
            isinstance(value, str) and value.strip() for value in seeds
        ):
            raise ContractError("seeds must be unique non-empty strings")
        if stochastic and not seeds:
            raise ContractError("stochastic packages must record at least one seed")

        inspection = self.catalogue.inspect(workbench)
        row = inspection["registry"]
        if (
            operating_mode == "SYNTHETIC_COMMISSIONING"
            and row["readiness_stage"] != "COMMISSIONING_READY"
        ):
            raise ContractError(
                f"{row['workbench_code']} is not commissioning-ready; package it as construction"
            )

        if _is_link_like(source):
            raise ContractError("evidence source must not be a symbolic link or junction")
        source = source.resolve()
        output = output.resolve()
        if output.exists():
            raise ContractError("portable package destination already exists")
        if source.is_dir() and output.is_relative_to(source):
            raise ContractError("portable package destination must be outside its evidence source")
        base, files = _inventory(source)
        evidence_core = {
            "schema_version": 1,
            "manifest_type": "RESEARCH_FACTORY_EVIDENCE_FILES",
            "files": files,
            "file_count": len(files),
            "total_bytes": sum(item["bytes"] for item in files),
        }
        evidence_manifest = {
            **evidence_core,
            "evidence_sha256": sha256_bytes(canonical_json_bytes(evidence_core)),
        }

        contract_path = self.catalogue.repository_root / Path(row["contract_path"])
        contract_schema_path = self.catalogue.contract_schema_path
        contract_file_sha256 = sha256_file(contract_path)
        contract_schema_sha256 = sha256_file(contract_schema_path)
        unsigned = {
            "schema_version": 1,
            "package_type": "RESEARCH_FACTORY_PORTABLE_EVIDENCE",
            "generated_at": utc_text(utc_now()),
            "operating_mode": operating_mode,
            "evidence_kind": evidence_kind,
            "workbench": {
                "code": row["workbench_code"],
                "title": row["title"],
                "contract_sha256": row["contract_sha256"],
                "contract_file_sha256": contract_file_sha256,
                "contract_path": "contract/contract.json",
                "contract_schema_sha256": contract_schema_sha256,
                "contract_schema_path": "contract/schema.json",
            },
            "attempt_id": attempt_id,
            "accountable_human": {
                "operator_id": operator_id,
                "identity_assurance": "SELF_ASSERTED_LOCAL",
                "identity_warning": "NOT_PROOF_OF_DISTINCT_HUMAN",
            },
            "method": {
                "summary": summary.strip(),
                "exact_commands": commands,
                "stochastic": stochastic,
                "seeds": seeds,
            },
            "environment": _environment(),
            "evidence": {
                "evidence_sha256": evidence_manifest["evidence_sha256"],
                "manifest_path": "evidence/manifest.json",
                "files_path": "evidence/files",
                "file_count": evidence_manifest["file_count"],
                "total_bytes": evidence_manifest["total_bytes"],
            },
            "provenance": {
                "engine_version": ENGINE_VERSION,
                "catalogue_sha256": self.catalogue.manifest["catalogue_sha256"],
                "station_manifest_sha256": self.catalogue.manifest["manifest_sha256"],
            },
            "construction_boundary": {
                "scientific_evidence": False,
                "counts_as_independent_reproduction": False,
                "eligible_for_promotion": False,
                "live_research_authorized": False,
            },
        }
        package_document = {
            **unsigned,
            "package_sha256": sha256_bytes(canonical_json_bytes(unsigned)),
        }
        self._validate(package_document)

        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.parent / f".{output.name}.{uuid.uuid4().hex}.tmp"
        try:
            (temporary / "contract").mkdir(parents=True)
            (temporary / "evidence" / "files").mkdir(parents=True)
            shutil.copyfile(contract_path, temporary / "contract" / "contract.json")
            shutil.copyfile(contract_schema_path, temporary / "contract" / "schema.json")
            for item in files:
                relative = _safe_relative(item["path"], field="evidence file path")
                source_path = base / Path(*relative.parts)
                target = temporary / "evidence" / "files" / Path(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source_path, target)
                if target.stat().st_size != item["bytes"] or sha256_file(target) != item["sha256"]:
                    raise ContractError("evidence changed while the package was created")
            write_json(temporary / "evidence" / "manifest.json", evidence_manifest)
            write_json(temporary / "package.json", package_document)
            verification = self.verify(temporary)
            if (
                verification["package_sha256"] != package_document["package_sha256"]
                or verification["evidence_sha256"] != evidence_manifest["evidence_sha256"]
            ):
                raise ContractError("portable package failed its creation-time verification")
            os.replace(temporary, output)
        except Exception:
            if temporary.exists():
                shutil.rmtree(temporary)
            raise
        return {
            "created": True,
            "path": str(output),
            "package_sha256": package_document["package_sha256"],
            "evidence_sha256": evidence_manifest["evidence_sha256"],
            "workbench_code": row["workbench_code"],
            "operating_mode": operating_mode,
            "scientific_evidence": False,
            "counts_as_independent_reproduction": False,
            "eligible_for_promotion": False,
        }

    def verify(self, package: Path) -> dict[str, Any]:
        if _is_link_like(package):
            raise ContractError("portable package must not be a symbolic link or junction")
        root = package.resolve()
        if not root.is_dir() or _is_link_like(root):
            raise ContractError("portable package must be a regular directory")
        entry_count = 0
        for path in root.rglob("*"):
            entry_count += 1
            if entry_count > MAX_PACKAGE_ENTRIES:
                raise ContractError("portable package exceeds the entry-count limit")
            if _is_link_like(path):
                raise ContractError("portable package must not contain symbolic links or junctions")
        top_level = {path.name for path in root.iterdir()}
        if top_level != {"package.json", "contract", "evidence"}:
            raise ContractError("portable package contains missing or unexpected top-level entries")
        if not (root / "package.json").is_file():
            raise ContractError("portable package envelope is missing")
        if not (root / "contract").is_dir() or not (root / "evidence").is_dir():
            raise ContractError("portable package contract or evidence directory is missing")
        contract_entries = {path.name for path in (root / "contract").iterdir()}
        if contract_entries != {"contract.json", "schema.json"}:
            raise ContractError("portable package contract snapshot is incomplete")
        evidence_entries = {path.name for path in (root / "evidence").iterdir()}
        if evidence_entries != {"manifest.json", "files"}:
            raise ContractError("portable package evidence directory is incomplete")

        document = _load_json_strict(root / "package.json")
        self._validate(document)
        expected_package_sha256 = document["package_sha256"]
        unsigned = {key: value for key, value in document.items() if key != "package_sha256"}
        if sha256_bytes(canonical_json_bytes(unsigned)) != expected_package_sha256:
            raise ContractError("portable package self-hash does not match")

        workbench = document["workbench"]
        contract_path = root / workbench["contract_path"]
        contract_schema_path = root / workbench["contract_schema_path"]
        if not contract_path.is_file() or not contract_schema_path.is_file():
            raise ContractError("embedded contract or contract schema is missing")
        if sha256_file(contract_path) != workbench["contract_file_sha256"]:
            raise ContractError("embedded contract bytes do not match the package")
        if sha256_file(contract_schema_path) != workbench["contract_schema_sha256"]:
            raise ContractError("embedded contract schema bytes do not match the package")
        contract = _load_json_strict(contract_path)
        contract_schema = _load_json_strict(contract_schema_path)
        try:
            Draft202012Validator.check_schema(contract_schema)
            Draft202012Validator(
                contract_schema,
                format_checker=FormatChecker(),
            ).validate(contract)
        except (SchemaError, ValidationError) as exc:
            raise ContractError(f"embedded workbench contract is invalid: {exc.message}") from exc
        if sha256_bytes(contract_bytes(contract)) != workbench["contract_sha256"]:
            raise ContractError("embedded workbench contract commitment does not match")
        if (
            contract.get("workbench", {}).get("code") != workbench["code"]
            or contract.get("workbench", {}).get("title") != workbench["title"]
        ):
            raise ContractError("embedded workbench identity does not match the package")
        if document["provenance"]["catalogue_sha256"] != contract["source"][
            "catalogue_sha256"
        ]:
            raise ContractError("package catalogue commitment differs from its contract")
        if (
            contract["readiness"]["live_research_enabled"] is not False
            or contract["readiness"]["scientific_standing"] != "NONE"
            or contract["readiness"]["promotion_claims_allowed"] is not False
        ):
            raise ContractError("portable package contract exceeds construction scope")
        if (
            document["operating_mode"] == "SYNTHETIC_COMMISSIONING"
            and contract["readiness"]["current_stage"] != "COMMISSIONING_READY"
        ):
            raise ContractError("package claims commissioning for an unready contract")

        evidence_manifest = _load_json_strict(root / document["evidence"]["manifest_path"])
        required_manifest_keys = {
            "schema_version",
            "manifest_type",
            "files",
            "file_count",
            "total_bytes",
            "evidence_sha256",
        }
        if set(evidence_manifest) != required_manifest_keys:
            raise ContractError("evidence manifest has missing or unexpected fields")
        if (
            evidence_manifest["schema_version"] != 1
            or evidence_manifest["manifest_type"] != "RESEARCH_FACTORY_EVIDENCE_FILES"
            or not isinstance(evidence_manifest["files"], list)
            or not evidence_manifest["files"]
        ):
            raise ContractError("evidence manifest header is invalid")
        evidence_core = {
            key: value for key, value in evidence_manifest.items() if key != "evidence_sha256"
        }
        evidence_sha256 = sha256_bytes(canonical_json_bytes(evidence_core))
        if (
            evidence_manifest["evidence_sha256"] != evidence_sha256
            or document["evidence"]["evidence_sha256"] != evidence_sha256
        ):
            raise ContractError("evidence manifest commitment does not match")
        files_root = root / document["evidence"]["files_path"]
        if not files_root.is_dir():
            raise ContractError("evidence files directory is missing")
        expected_paths: set[str] = set()
        computed_total = 0
        for item in evidence_manifest["files"]:
            if not isinstance(item, dict) or set(item) != {"path", "bytes", "sha256"}:
                raise ContractError("evidence manifest contains an invalid file row")
            relative = _safe_relative(item["path"], field="evidence file path")
            if item["path"] in expected_paths:
                raise ContractError("evidence manifest contains a duplicate path")
            expected_paths.add(item["path"])
            if type(item["bytes"]) is not int or item["bytes"] < 0:
                raise ContractError("evidence file size must be a nonnegative integer")
            validate_sha256(item["sha256"], field=f"{item['path']}.sha256")
            path = files_root / Path(*relative.parts)
            if (
                not path.is_file()
                or _is_link_like(path)
                or path.stat().st_size != item["bytes"]
                or sha256_file(path) != item["sha256"]
            ):
                raise ContractError(f"evidence file does not match: {item['path']}")
            computed_total += item["bytes"]
        actual_paths = {
            path.relative_to(files_root).as_posix()
            for path in files_root.rglob("*")
            if path.is_file()
        }
        if actual_paths != expected_paths:
            raise ContractError("evidence file set differs from its manifest")
        if (
            type(evidence_manifest["file_count"]) is not int
            or type(evidence_manifest["total_bytes"]) is not int
            or evidence_manifest["file_count"] != len(expected_paths)
            or evidence_manifest["total_bytes"] != computed_total
            or document["evidence"]["file_count"] != len(expected_paths)
            or document["evidence"]["total_bytes"] != computed_total
        ):
            raise ContractError("evidence counts do not match the file inventory")

        expected_directories = {"contract", "evidence", "evidence/files"}
        for relative_text in expected_paths:
            relative = PurePosixPath("evidence/files") / PurePosixPath(relative_text)
            expected_directories.update(parent.as_posix() for parent in relative.parents[:-1])
        actual_directories = {
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_dir()
        }
        if actual_directories != expected_directories:
            raise ContractError("portable package contains missing or unexpected directories")

        current = self.catalogue.resolve(workbench["code"])
        try:
            self.catalogue.verified_contract(current)
        except ContractError:
            current_contract_match = False
        else:
            current_contract_match = current["contract_sha256"] == workbench["contract_sha256"]
        return {
            "valid": True,
            "path": str(root),
            "package_sha256": expected_package_sha256,
            "evidence_sha256": evidence_sha256,
            "workbench_code": workbench["code"],
            "attempt_id": document["attempt_id"],
            "operating_mode": document["operating_mode"],
            "evidence_kind": document["evidence_kind"],
            "files": len(expected_paths),
            "total_bytes": computed_total,
            "current_contract_match": current_contract_match,
            "scientific_evidence": False,
            "counts_as_independent_reproduction": False,
            "eligible_for_promotion": False,
        }
