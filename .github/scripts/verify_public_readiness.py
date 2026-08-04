from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
import re
import subprocess


ROOT = Path(__file__).resolve().parents[2]
REQUIRED_PATHS = {
    ".github/CODEOWNERS",
    ".github/ISSUE_TEMPLATE/config.yml",
    ".github/dependabot.yml",
    ".github/schemas/asset-provenance-v1.schema.json",
    ".github/scripts/verify_asset_provenance.py",
    ".github/scripts/verify_public_readiness.py",
    ".github/workflows/verify.yml",
    ".gitleaksignore",
    "ASSET_PROVENANCE.json",
    "CITATION.cff",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "CONTRIBUTOR_QUICKSTART.md",
    "GOVERNANCE.md",
    "LICENSE.md",
    "PUBLIC_LAUNCH_CHECKLIST.md",
    "README.md",
    "REUSE.toml",
    "SECURITY.md",
    "THIRD_PARTY_NOTICES.md",
    "candidate_artifacts/README.md",
    "factory/hangar/.openai/hosting.json",
    "factory/hangar/data/workbench-readiness.json",
}
ALLOWED_STAGES = {"CONTRACT_DRAFT", "COMMISSIONING_READY"}
GITLEAKS_BASELINE = {
    "fae90bbfaf42724f89f49d6a30b7de60b18bf4eb:factory/workbenches/"
    "wb001_lossless_compression/results/blind_demo/public_attestation.json:"
    "generic-api-key:5",
    "fae90bbfaf42724f89f49d6a30b7de60b18bf4eb:factory/workbenches/"
    "wb001_lossless_compression/results/blind_demo/job_token_v3.json:"
    "generic-api-key:4",
}
SECRET_SUFFIXES = {".key", ".p12", ".pem", ".pfx"}
SECRET_NAMES = {
    ".netrc",
    ".npmrc",
    ".pypirc",
    "credentials.json",
    "id_ed25519",
    "id_rsa",
    "service-account.json",
}


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def tracked_paths(root: Path) -> set[str]:
    output = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout
    return {
        item.decode("utf-8")
        for item in output.split(b"\0")
        if item
    }


def verify_required_files(tracked: set[str]) -> None:
    missing = sorted(REQUIRED_PATHS - tracked)
    if missing:
        raise ValueError(f"public-readiness files are missing or untracked: {missing}")


def verify_no_private_material(tracked: set[str]) -> None:
    violations: list[str] = []
    for value in sorted(tracked):
        path = PurePosixPath(value)
        lower_parts = [part.lower() for part in path.parts]
        name = path.name.lower()
        if (
            any(part in {"private", "secret", "secrets"} for part in lower_parts)
            or name == ".env"
            or (name.startswith(".env.") and name != ".env.example")
            or path.suffix.lower() in SECRET_SUFFIXES
            or name in SECRET_NAMES
        ):
            violations.append(value)
    if violations:
        raise ValueError(f"private or credential-shaped tracked paths: {violations}")


def verify_candidate_boundary(tracked: set[str]) -> None:
    candidate_paths = {
        path for path in tracked if path.startswith("candidate_artifacts/")
    }
    if candidate_paths != {"candidate_artifacts/README.md"}:
        raise ValueError(
            "candidate intake must stay closed; only candidate_artifacts/README.md "
            f"may be tracked, got {sorted(candidate_paths)}"
        )
    reproduction_forms = sorted(
        path
        for path in tracked
        if PurePosixPath(path).name.lower() in {"reproduction.yml", "reproduction.yaml"}
    )
    if reproduction_forms:
        raise ValueError(f"public reproduction intake is forbidden: {reproduction_forms}")


def verify_issue_configuration(root: Path) -> None:
    config = (root / ".github/ISSUE_TEMPLATE/config.yml").read_text(encoding="utf-8")
    if not re.search(r"(?m)^blank_issues_enabled:\s*false\s*$", config):
        raise ValueError("blank public issues must remain disabled")


def verify_readiness(root: Path) -> None:
    document = load_json(root / "factory/hangar/data/workbench-readiness.json")
    if not isinstance(document, dict) or not isinstance(document.get("stations"), list):
        raise ValueError("workbench readiness must contain a stations array")
    stations = document["stations"]
    if len(stations) != 100:
        raise ValueError(f"expected 100 stations, got {len(stations)}")
    actual_ids: set[int] = set()
    for station in stations:
        if not isinstance(station, dict):
            raise ValueError("each readiness station must be an object")
        numeric_id = station.get("numeric_id")
        code = station.get("workbench_code")
        stage = station.get("readiness_stage")
        if not isinstance(numeric_id, int) or numeric_id < 1 or numeric_id > 100:
            raise ValueError(f"invalid readiness numeric_id: {numeric_id!r}")
        if code != f"WB-{numeric_id:03d}":
            raise ValueError(f"readiness code/id mismatch: {code!r}, {numeric_id!r}")
        if stage not in ALLOWED_STAGES:
            raise ValueError(f"public repository contains a live/unknown stage: {stage!r}")
        actual_ids.add(numeric_id)
    if actual_ids != set(range(1, 101)):
        raise ValueError("readiness stations must cover each numeric id from 1 through 100")


def verify_hosting_metadata(root: Path) -> None:
    document = load_json(root / "factory/hangar/.openai/hosting.json")
    if not isinstance(document, dict):
        raise ValueError("hosting metadata must be an object")
    unknown = sorted(set(document) - {"project_id", "d1", "r2"})
    if unknown:
        raise ValueError(f"hosting metadata contains unexpected keys: {unknown}")
    if not isinstance(document.get("project_id"), str):
        raise ValueError("hosting project_id must be a public identifier string")
    if document.get("d1") != "DB" or document.get("r2") is not None:
        raise ValueError("hosting metadata must request only the DB binding")


def verify_asset_schema_pointer(root: Path) -> None:
    document = load_json(root / "ASSET_PROVENANCE.json")
    expected = ".github/schemas/asset-provenance-v1.schema.json"
    if not isinstance(document, dict) or document.get("$schema") != expected:
        raise ValueError("asset ledger must point to its tracked closed schema")


def verify_workflow_permissions(root: Path) -> None:
    workflow = (root / ".github/workflows/verify.yml").read_text(encoding="utf-8")
    if not re.search(r"(?m)^permissions:\s*\n\s+contents:\s*read\s*$", workflow):
        raise ValueError("verification workflow must retain top-level contents: read")
    if re.search(r"(?m)^\s+[a-z-]+:\s*write\s*$", workflow):
        raise ValueError("verification workflow must not request write permissions")


def verify_gitleaks_baseline(root: Path) -> None:
    lines = {
        line.strip()
        for line in (root / ".gitleaksignore").read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    if lines != GITLEAKS_BASELINE:
        raise ValueError("Gitleaks baseline must contain only the two reviewed fixture fingerprints")
    fingerprint = re.compile(r"^[0-9a-f]{40}:.+:[a-z0-9-]+:[1-9][0-9]*$")
    if any(not fingerprint.fullmatch(line) for line in lines):
        raise ValueError("Gitleaks baseline entries must be exact fingerprints")


def verify(root: Path = ROOT) -> int:
    tracked = tracked_paths(root)
    verify_required_files(tracked)
    verify_no_private_material(tracked)
    verify_candidate_boundary(tracked)
    verify_issue_configuration(root)
    verify_readiness(root)
    verify_hosting_metadata(root)
    verify_asset_schema_pointer(root)
    verify_workflow_permissions(root)
    verify_gitleaks_baseline(root)
    return len(tracked)


def main() -> int:
    count = verify()
    print(f"Public-readiness boundary verified across {count} tracked paths.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
