from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError

from control_plane.common import (
    ContractError,
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
    validate_sha256,
)


CODE_RE = re.compile(r"^WB-(\d{3})$")
SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
STAGES = {"CATALOGUED", "CONTRACT_DRAFT", "COMMISSIONING_READY", "LIVE_READY"}
PROFILES = {"CATALOGUE_ONLY", "ADAPTER_BOUND", "LEGACY_INSTRUMENTED"}
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_KIT_ENTRIES = 10_000
ROOT_MANIFEST_KEYS = {
    "catalogue_sha256",
    "generator_sha256",
    "generator_version",
    "manifest_sha256",
    "manifest_type",
    "schema_version",
    "standard",
    "stations",
}
STATION_ROW_KEYS = {
    "adapter_id",
    "adapter_version",
    "commissioning_profile",
    "contract_path",
    "contract_sha256",
    "contract_version",
    "counts_as_independent_reproduction",
    "eligible_for_promotion",
    "evidence_lane",
    "facets",
    "kit_path",
    "kit_sha256",
    "numeric_id",
    "readiness_stage",
    "scientific_evidence",
    "slug",
    "starter_pack_status",
    "title",
    "unresolved",
    "unresolved_count",
    "workbench_code",
}
KIT_MANIFEST_KEYS = {
    "construction_boundary",
    "contract_sha256",
    "files",
    "generator_sha256",
    "generator_version",
    "kit_sha256",
    "manifest_type",
    "readiness_stage",
    "schema_version",
    "source_entry_sha256",
    "workbench_code",
}


def _is_link_like(path: Path) -> bool:
    junction_check = getattr(path, "is_junction", None)
    return path.is_symlink() or bool(junction_check and junction_check())


def _normalize_contract_value(value: Any) -> Any:
    """Mirror Workbench Contract v1's cross-language number normalisation."""

    if isinstance(value, dict):
        return {key: _normalize_contract_value(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_normalize_contract_value(child) for child in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def contract_bytes(value: Any) -> bytes:
    return json.dumps(
        _normalize_contract_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
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
            object_pairs_hook=_strict_json_object,
            parse_constant=_reject_json_constant,
        )
    except ContractError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"could not load JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"expected a JSON object in {path}")
    return value


def _safe_repository_path(root: Path, value: str, *, field: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ContractError(f"{field} must be a non-empty repository-relative path")
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
        raise ContractError(f"{field} is not a canonical repository-relative path")
    resolved = (root / Path(*posix.parts)).resolve()
    if not resolved.is_relative_to(root):
        raise ContractError(f"{field} escapes the repository")
    return resolved


class StationCatalogue:
    """Verified view of the generated 100-station registry."""

    def __init__(self, factory_root: Path) -> None:
        self.factory_root = factory_root.resolve()
        self.repository_root = self.factory_root.parent
        self.manifest_path = self.factory_root / "station_kits" / "manifest.json"
        self.contract_schema_path = (
            self.factory_root
            / "workbench_standard"
            / "schema"
            / "workbench-contract-v1.schema.json"
        )
        self.manifest = _load_json_strict(self.manifest_path)
        self.contract_schema = _load_json_strict(self.contract_schema_path)
        try:
            Draft202012Validator.check_schema(self.contract_schema)
        except SchemaError as exc:
            raise ContractError(f"workbench contract schema is invalid: {exc.message}") from exc
        self._validator = Draft202012Validator(
            self.contract_schema,
            format_checker=FormatChecker(),
        )
        self._rows = self._validate_manifest()

    def _validate_manifest(self) -> dict[str, dict[str, Any]]:
        manifest = self.manifest
        if set(manifest) != ROOT_MANIFEST_KEYS:
            raise ContractError("station registry has missing or unexpected fields")
        if manifest.get("schema_version") != 1:
            raise ContractError("station registry uses an unsupported schema version")
        if manifest.get("manifest_type") != "RESEARCH_FACTORY_STATION_KITS":
            raise ContractError("station registry has the wrong manifest type")
        if manifest.get("standard") != "research-factory/workbench-contract/v1":
            raise ContractError("station registry has the wrong contract standard")
        if not isinstance(manifest.get("generator_version"), str) or not SEMVER_RE.fullmatch(
            manifest["generator_version"]
        ):
            raise ContractError("station registry generator_version is invalid")
        validate_sha256(manifest.get("generator_sha256"), field="generator_sha256")
        validate_sha256(manifest.get("manifest_sha256"), field="manifest_sha256")
        unsigned = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
        if sha256_bytes(canonical_json_bytes(unsigned)) != manifest["manifest_sha256"]:
            raise ContractError("station registry self-hash does not match")

        catalogue_path = self.repository_root / "research_factory_100_workbenches.json"
        validate_sha256(manifest.get("catalogue_sha256"), field="catalogue_sha256")
        if (
            not catalogue_path.is_file()
            or sha256_file(catalogue_path) != manifest["catalogue_sha256"]
        ):
            raise ContractError("station registry does not bind the current source catalogue")

        stations = manifest.get("stations")
        if not isinstance(stations, list) or len(stations) != 100:
            raise ContractError("station registry must contain exactly 100 stations")
        rows: dict[str, dict[str, Any]] = {}
        slugs: set[str] = set()
        for expected_number, row in enumerate(stations, start=1):
            if not isinstance(row, dict):
                raise ContractError("station registry entries must be objects")
            if set(row) != STATION_ROW_KEYS:
                raise ContractError("station registry row has missing or unexpected fields")
            code = row.get("workbench_code")
            expected_code = f"WB-{expected_number:03d}"
            if (
                code != expected_code
                or type(row.get("numeric_id")) is not int
                or row["numeric_id"] != expected_number
            ):
                raise ContractError(
                    f"station registry must be contiguous; expected {expected_code}"
                )
            slug = row.get("slug")
            if not isinstance(slug, str) or not slug or slug in slugs:
                raise ContractError(f"{code}: station slug is missing or duplicated")
            slugs.add(slug)
            if row.get("readiness_stage") not in STAGES:
                raise ContractError(f"{code}: unknown readiness stage")
            if row.get("commissioning_profile") not in PROFILES:
                raise ContractError(f"{code}: unknown commissioning profile")
            if not isinstance(row.get("contract_version"), str) or not SEMVER_RE.fullmatch(
                row["contract_version"]
            ):
                raise ContractError(f"{code}: invalid workbench contract version")
            if row.get("kit_path") != f"factory/station_kits/{code}" or row.get(
                "contract_path"
            ) != f"factory/station_kits/{code}/contract.json":
                raise ContractError(f"{code}: station paths are not canonical")
            if any(
                row.get(field) is not False
                for field in (
                    "scientific_evidence",
                    "counts_as_independent_reproduction",
                    "eligible_for_promotion",
                )
            ):
                raise ContractError(
                    f"{code}: generated station registry exceeds construction scope"
                )
            validate_sha256(row.get("contract_sha256"), field=f"{code}.contract_sha256")
            validate_sha256(row.get("kit_sha256"), field=f"{code}.kit_sha256")
            rows[code] = row
        return rows

    @staticmethod
    def normalize_identifier(value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ContractError("workbench identifier is required")
        text = value.strip()
        upper = text.upper()
        if upper.isdigit():
            number = int(upper)
            if 1 <= number <= 100:
                return f"WB-{number:03d}"
        compact = upper.replace("-", "")
        if compact.startswith("WB") and compact[2:].isdigit():
            number = int(compact[2:])
            if 1 <= number <= 100:
                return f"WB-{number:03d}"
        if CODE_RE.fullmatch(upper):
            return upper
        return text.lower()

    def resolve(self, identifier: str) -> dict[str, Any]:
        normalized = self.normalize_identifier(identifier)
        if normalized in self._rows:
            return self._rows[normalized]
        for row in self._rows.values():
            if row["slug"] == normalized:
                return row
        raise ContractError(f"unknown workbench: {identifier}")

    def _contract_path(self, row: dict[str, Any]) -> Path:
        path = _safe_repository_path(
            self.repository_root,
            row["contract_path"],
            field=f"{row['workbench_code']}.contract_path",
        )
        if not path.is_file() or _is_link_like(path):
            raise ContractError(f"{row['workbench_code']}: generated contract is missing")
        return path

    def verified_contract(self, row: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
        path = self._contract_path(row)
        contract = _load_json_strict(path)
        try:
            self._validator.validate(contract)
        except ValidationError as exc:
            raise ContractError(
                f"{row['workbench_code']}: contract schema failure: {exc.message}"
            ) from exc
        actual = sha256_bytes(contract_bytes(contract))
        if actual != row["contract_sha256"]:
            raise ContractError(f"{row['workbench_code']}: contract commitment does not match")
        workbench = contract.get("workbench", {})
        if (
            workbench.get("code") != row["workbench_code"]
            or workbench.get("numeric_id") != row["numeric_id"]
            or workbench.get("slug") != row["slug"]
            or workbench.get("title") != row["title"]
        ):
            raise ContractError(f"{row['workbench_code']}: registry and contract identity differ")
        expected_bindings = {
            "contract_version": contract["contract_version"],
            "commissioning_profile": contract["commissioning"]["profile_status"],
            "adapter_id": contract["commissioning"]["adapter_id"],
            "adapter_version": contract["commissioning"]["adapter_version"],
            "evidence_lane": workbench["evidence_lane"],
            "readiness_stage": contract["readiness"]["current_stage"],
            "starter_pack_status": contract["starter_pack"]["fixture_status"],
            "unresolved": contract["readiness"]["unresolved"],
            "unresolved_count": len(contract["readiness"]["unresolved"]),
            "facets": contract["readiness"]["facets"],
        }
        for field, expected in expected_bindings.items():
            if row[field] != expected:
                raise ContractError(
                    f"{row['workbench_code']}: registry field {field} differs from its contract"
                )
        if (
            contract["readiness"]["live_research_enabled"] is not False
            or contract["readiness"]["scientific_standing"] != "NONE"
            or contract["readiness"]["promotion_claims_allowed"] is not False
        ):
            raise ContractError(
                f"{row['workbench_code']}: current station contract exceeds construction scope"
            )
        return path, contract

    def list(
        self,
        *,
        stage: str | None = None,
        profile: str | None = None,
        lane: str | None = None,
        entry_ready: bool = False,
    ) -> list[dict[str, Any]]:
        if stage is not None:
            stage = stage.upper()
            if stage not in STAGES:
                raise ContractError(f"unknown readiness stage: {stage}")
        if profile is not None:
            profile = profile.upper()
            if profile not in PROFILES:
                raise ContractError(f"unknown commissioning profile: {profile}")
        lane_upper = lane.upper() if lane else None
        selected: list[dict[str, Any]] = []
        for row in self._rows.values():
            self.verified_contract(row)
            if stage and row["readiness_stage"] != stage:
                continue
            if profile and row["commissioning_profile"] != profile:
                continue
            if lane_upper and str(row["evidence_lane"]).upper() != lane_upper:
                continue
            if entry_ready and row["starter_pack_status"] != "KNOWN_ANSWER_READY":
                continue
            selected.append(
                {
                    "workbench_code": row["workbench_code"],
                    "title": row["title"],
                    "slug": row["slug"],
                    "evidence_lane": row["evidence_lane"],
                    "commissioning_profile": row["commissioning_profile"],
                    "readiness_stage": row["readiness_stage"],
                    "starter_pack_status": row["starter_pack_status"],
                    "unresolved_count": row["unresolved_count"],
                    "contract_sha256": row["contract_sha256"],
                }
            )
        return selected

    def inspect(self, identifier: str) -> dict[str, Any]:
        row = self.resolve(identifier)
        contract_path, contract = self.verified_contract(row)
        self._verify_kit(row)
        kit_path = _safe_repository_path(
            self.repository_root,
            row["kit_path"],
            field=f"{row['workbench_code']}.kit_path",
        )
        return {
            "schema_version": 1,
            "inspection_type": "RESEARCH_FACTORY_WORKBENCH",
            "registry": row,
            "contract": contract,
            "paths": {
                "kit": kit_path.relative_to(self.repository_root).as_posix(),
                "contract": contract_path.relative_to(self.repository_root).as_posix(),
                "start_here": (kit_path / "START_HERE.md")
                .relative_to(self.repository_root)
                .as_posix(),
                "starter_pack": (kit_path / "STARTER_PACK.md")
                .relative_to(self.repository_root)
                .as_posix(),
            },
            "safe_scope": (
                "SYNTHETIC_COMMISSIONING"
                if row["readiness_stage"] == "COMMISSIONING_READY"
                else "HANGAR_CONSTRUCTION"
            ),
            "live_research_allowed": contract["readiness"]["live_research_enabled"],
        }

    def _verify_kit(self, row: dict[str, Any]) -> None:
        kit_path = _safe_repository_path(
            self.repository_root,
            row["kit_path"],
            field=f"{row['workbench_code']}.kit_path",
        )
        manifest_path = kit_path / "kit-manifest.json"
        if not manifest_path.is_file() or _is_link_like(manifest_path):
            raise ContractError(f"{row['workbench_code']}: kit manifest is missing")
        kit_manifest = _load_json_strict(manifest_path)
        if set(kit_manifest) != KIT_MANIFEST_KEYS:
            raise ContractError(f"{row['workbench_code']}: kit manifest fields are invalid")
        validate_sha256(kit_manifest.get("kit_sha256"), field="kit_sha256")
        unsigned = {key: value for key, value in kit_manifest.items() if key != "kit_sha256"}
        if sha256_bytes(canonical_json_bytes(unsigned)) != kit_manifest["kit_sha256"]:
            raise ContractError(f"{row['workbench_code']}: kit self-hash does not match")
        if (
            kit_manifest.get("workbench_code") != row["workbench_code"]
            or kit_manifest.get("contract_sha256") != row["contract_sha256"]
            or kit_manifest.get("kit_sha256") != row["kit_sha256"]
            or kit_manifest.get("readiness_stage") != row["readiness_stage"]
            or kit_manifest.get("generator_version") != self.manifest["generator_version"]
            or kit_manifest.get("generator_sha256") != self.manifest["generator_sha256"]
        ):
            raise ContractError(f"{row['workbench_code']}: root and kit manifests differ")
        if kit_manifest.get("construction_boundary") != {
            "scientific_evidence": False,
            "counts_as_independent_reproduction": False,
            "eligible_for_promotion": False,
        }:
            raise ContractError(f"{row['workbench_code']}: kit exceeds construction scope")
        files = kit_manifest.get("files")
        if not isinstance(files, list) or not files:
            raise ContractError(f"{row['workbench_code']}: kit file inventory is empty")
        expected: set[str] = set()
        for item in files:
            if not isinstance(item, dict):
                raise ContractError(f"{row['workbench_code']}: invalid kit file row")
            if set(item) != {"path", "bytes", "sha256"}:
                raise ContractError(f"{row['workbench_code']}: invalid kit file fields")
            relative = item.get("path")
            path = _safe_repository_path(kit_path, relative, field="kit file path")
            normalized = path.relative_to(kit_path).as_posix()
            if normalized != relative or normalized in expected:
                raise ContractError(f"{row['workbench_code']}: duplicate or noncanonical kit path")
            expected.add(normalized)
            validate_sha256(item.get("sha256"), field=f"{row['workbench_code']}.{relative}.sha256")
            if type(item.get("bytes")) is not int or item["bytes"] < 0:
                raise ContractError(f"{row['workbench_code']}: invalid kit file size")
            if (
                not path.is_file()
                or _is_link_like(path)
                or path.stat().st_size != item.get("bytes")
                or sha256_file(path) != item["sha256"]
            ):
                raise ContractError(f"{row['workbench_code']}: kit file drift: {relative}")
        actual: set[str] = set()
        entry_count = 0
        for path in kit_path.rglob("*"):
            entry_count += 1
            if entry_count > MAX_KIT_ENTRIES:
                raise ContractError(f"{row['workbench_code']}: kit exceeds the entry limit")
            if _is_link_like(path):
                raise ContractError(
                    f"{row['workbench_code']}: kit contains a symbolic link or junction"
                )
            if path.is_file() and path != manifest_path:
                actual.add(path.relative_to(kit_path).as_posix())
        if actual != expected:
            raise ContractError(f"{row['workbench_code']}: kit file set differs from its manifest")

    def verify(self, *, full: bool = True) -> dict[str, Any]:
        for row in self._rows.values():
            self.verified_contract(row)
            if full:
                self._verify_kit(row)
        stages = Counter(row["readiness_stage"] for row in self._rows.values())
        profiles = Counter(row["commissioning_profile"] for row in self._rows.values())
        entry_ready = sum(
            row["starter_pack_status"] == "KNOWN_ANSWER_READY"
            for row in self._rows.values()
        )
        return {
            "valid": True,
            "stations": len(self._rows),
            "catalogue_sha256": self.manifest["catalogue_sha256"],
            "manifest_sha256": self.manifest["manifest_sha256"],
            "readiness_stages": dict(sorted(stages.items())),
            "commissioning_profiles": dict(sorted(profiles.items())),
            "runnable_entry_gates": entry_ready,
            "live_ready": stages.get("LIVE_READY", 0),
        }


def doctor(factory_root: Path, *, ledger: Path | None = None) -> dict[str, Any]:
    catalogue = StationCatalogue(factory_root)
    catalogue_result = catalogue.verify(full=True)
    ledger_result: dict[str, Any]
    if ledger is None:
        ledger_result = {
            "status": "NOT_INITIALIZED",
            "canonical_state_required_for_discovery": False,
        }
    else:
        if not ledger.is_file() or _is_link_like(ledger):
            raise ContractError(f"ledger does not exist or is not a file: {ledger}")
        from control_plane.ledger import EventLedger

        ledger_result = {"status": "VALID", **EventLedger(ledger).verify()}
    python_compatible = sys.version_info >= (3, 11)
    return {
        "schema_version": 1,
        "diagnostic_type": "RESEARCH_FACTORY_ENGINE_DOCTOR",
        "engine_ready": python_compatible,
        "operating_scope": "CONSTRUCTION_AND_SYNTHETIC_COMMISSIONING",
        "live_research_ready": catalogue_result["live_ready"] > 0,
        "python": {
            "version": ".".join(str(part) for part in sys.version_info[:3]),
            "minimum": "3.11",
            "compatible": python_compatible,
        },
        "catalogue": catalogue_result,
        "ledger": ledger_result,
        "provider_dependencies": {
            "network_required": False,
            "github_required": False,
            "openai_required": False,
            "website_required": False,
        },
        "warnings": [
            "No station is authorised for live research."
            if catalogue_result["live_ready"] == 0
            else "Only stations explicitly marked LIVE_READY may accept live work.",
            "Self-asserted local identities do not prove distinct biological humans.",
        ],
    }
