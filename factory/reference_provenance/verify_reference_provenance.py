from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
REFERENCE_DIR = ROOT / "factory" / "reference_provenance"
MANIFEST = REFERENCE_DIR / "WB001-WB010.reference-provenance.2026-08-06.json"
MANIFESTS = (
    (MANIFEST, tuple(range(1, 11))),
    (
        REFERENCE_DIR / "WB011-WB020.reference-provenance.2026-08-06.json",
        tuple(range(11, 21)),
    ),
    (
        REFERENCE_DIR / "WB021-WB030.reference-provenance.2026-08-06.json",
        tuple(range(21, 31)),
    ),
    (
        REFERENCE_DIR / "WB031-WB040.reference-provenance.2026-08-06.json",
        tuple(range(31, 41)),
    ),
)
SCHEMA = ROOT / "factory" / "reference_provenance" / "reference-provenance-v1.schema.json"
CATALOGUE = ROOT / "research_factory_100_workbenches.json"
EXPECTED_CODES = [f"WB-{number:03d}" for number in range(1, 11)]
HTTPS_URL_RE = re.compile(r"^https://[^\s]+$")


def load_json_strict(path: Path) -> object:
    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        document: dict[str, object] = {}
        for key, value in pairs:
            if key in document:
                raise ValueError(f"duplicate JSON object key in {path}: {key!r}")
            document[key] = value
        return document

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_keys)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_schema(document: object, schema_path: Path) -> dict[str, object]:
    schema = load_json_strict(schema_path)
    if not isinstance(schema, dict):
        raise ValueError("reference-provenance schema must be a JSON object")
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    errors = sorted(
        validator.iter_errors(document),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        error = errors[0]
        location = "/".join(str(part) for part in error.absolute_path) or "$"
        raise ValueError(f"reference-provenance schema violation at {location}: {error.message}")
    if not isinstance(document, dict):
        raise ValueError("reference-provenance manifest must be a JSON object")
    return document


def canonical_rows(
    catalogue: object,
    expected_numbers: tuple[int, ...],
) -> list[dict[str, object]]:
    if not isinstance(catalogue, dict) or not isinstance(catalogue.get("workbenches"), list):
        raise ValueError("canonical catalogue must contain a workbenches array")

    by_id: dict[int, dict[str, object]] = {}
    for value in catalogue["workbenches"]:
        if not isinstance(value, dict) or not isinstance(value.get("id"), int):
            raise ValueError("every canonical catalogue row must have an integer id")
        row_id = value["id"]
        if row_id in by_id:
            raise ValueError(f"duplicate canonical catalogue id: {row_id}")
        by_id[row_id] = value

    missing = [number for number in expected_numbers if number not in by_id]
    if missing:
        raise ValueError(f"canonical catalogue is missing expected workbench ids: {missing}")
    return [by_id[number] for number in expected_numbers]


def catalogue_reference_urls(value: object) -> list[str]:
    """Expand the catalogue's canonical `url | url` notation without guessing."""

    if not isinstance(value, str):
        raise ValueError("catalogue reference_url must be a string")
    urls = value.split(" | ")
    if " | ".join(urls) != value or not urls or any(not HTTPS_URL_RE.fullmatch(url) for url in urls):
        raise ValueError(f"catalogue reference_url has invalid canonical HTTPS syntax: {value!r}")
    if len(set(urls)) != len(urls):
        raise ValueError(f"catalogue reference_url repeats an HTTPS component: {value!r}")
    return urls


def verify_retrieval(retrieval: object, station_code: str) -> None:
    if not isinstance(retrieval, dict):
        raise ValueError(f"{station_code} retrieval must be an object")

    outcome = retrieval.get("outcome")
    requested_url = retrieval.get("requested_url")
    final_url = retrieval.get("final_url")
    curl_exit = retrieval.get("curl_exit_code")
    http_status = retrieval.get("http_status")
    redirects = retrieval.get("redirect_count")
    content_type = retrieval.get("content_type")
    size = retrieval.get("response_size_bytes")
    response_hash = retrieval.get("response_sha256")
    error = retrieval.get("error")

    if outcome == "retrieved":
        if curl_exit != 0:
            raise ValueError(f"{station_code} retrieved response has non-zero curl exit")
        if not isinstance(http_status, int) or not 200 <= http_status <= 299:
            raise ValueError(f"{station_code} retrieved response is not HTTP 2xx")
        if not isinstance(final_url, str) or not final_url.startswith("https://"):
            raise ValueError(f"{station_code} retrieved response lacks a verified final URL")
        if not isinstance(content_type, str) or not content_type.strip():
            raise ValueError(f"{station_code} retrieved response lacks a content type")
        if not isinstance(size, int) or size < 1:
            raise ValueError(f"{station_code} retrieved response lacks a positive byte count")
        if not isinstance(response_hash, str) or len(response_hash) != 64:
            raise ValueError(f"{station_code} retrieved response lacks an exact-byte SHA-256")
        if error is not None:
            raise ValueError(f"{station_code} successful retrieval must not record an error")
        if redirects == 0 and final_url != requested_url:
            raise ValueError(
                f"{station_code} zero-redirect retrieval changed URL: {requested_url!r} -> {final_url!r}"
            )
    elif outcome == "failed":
        if not isinstance(curl_exit, int) or curl_exit == 0:
            raise ValueError(f"{station_code} failed retrieval must record a non-zero curl exit")
        if response_hash is not None or size is not None:
            raise ValueError(f"{station_code} failed retrieval must not claim unverified response bytes")
        if content_type is not None:
            raise ValueError(f"{station_code} failed retrieval must not claim a response content type")
        if not isinstance(error, str) or len(error.strip()) < 10:
            raise ValueError(f"{station_code} failed retrieval needs a useful error record")
    else:
        raise ValueError(f"{station_code} has unsupported retrieval outcome: {outcome!r}")


def verify(
    root: Path = ROOT,
    manifest_path: Path | None = None,
    schema_path: Path | None = None,
    catalogue_path: Path | None = None,
    expected_numbers: tuple[int, ...] | None = None,
) -> int:
    schema = schema_path or root / "factory" / "reference_provenance" / SCHEMA.name
    catalogue_file = catalogue_path or root / CATALOGUE.name

    if manifest_path is None:
        configured_codes: list[str] = []
        total = 0
        for configured_manifest, configured_numbers in MANIFESTS:
            manifest = root / "factory" / "reference_provenance" / configured_manifest.name
            codes = [f"WB-{number:03d}" for number in configured_numbers]
            if set(codes) & set(configured_codes):
                raise ValueError("configured reference-provenance batches overlap")
            configured_codes.extend(codes)
            total += verify(
                root=root,
                manifest_path=manifest,
                schema_path=schema,
                catalogue_path=catalogue_file,
                expected_numbers=configured_numbers,
            )
        return total

    manifest = manifest_path
    numbers = expected_numbers or tuple(range(1, 11))
    expected_codes = [f"WB-{number:03d}" for number in numbers]
    range_label = f"{expected_codes[0]} through {expected_codes[-1]}"

    document = validate_schema(load_json_strict(manifest), schema)
    catalogue = load_json_strict(catalogue_file)
    rows = canonical_rows(catalogue, numbers)

    actual_catalogue_hash = sha256(catalogue_file)
    if document.get("catalogue_sha256") != actual_catalogue_hash:
        raise ValueError(
            "catalogue SHA-256 differs from the exact canonical bytes: "
            f"expected {document.get('catalogue_sha256')}, got {actual_catalogue_hash}"
        )

    if document.get("scope") != expected_codes:
        raise ValueError(f"manifest scope must be exactly {range_label} in order")
    stations = document.get("stations")
    if not isinstance(stations, list):
        raise ValueError("manifest stations must be an array")
    codes = [station.get("workbench_code") for station in stations if isinstance(station, dict)]
    if codes != expected_codes:
        raise ValueError(f"manifest station IDs must be exactly {range_label} in order")

    manifest_date = str(document.get("manifest_id", ""))[-10:]
    expected_manifest_prefix = f"WB{numbers[0]:03d}-WB{numbers[-1]:03d}-"
    if not str(document.get("manifest_id", "")).startswith(expected_manifest_prefix):
        raise ValueError(f"manifest ID range must match {range_label}")
    if str(document.get("generated_at_utc", ""))[:10] != manifest_date:
        raise ValueError("manifest ID date and generated_at_utc date differ")

    for expected_number, station, row in zip(numbers, stations, rows, strict=True):
        if not isinstance(station, dict):
            raise ValueError("manifest station entries must be objects")
        code = f"WB-{expected_number:03d}"
        expected = {
            "catalogue_id": expected_number,
            "workbench_code": code,
            "catalogue_title": row.get("workbench"),
            "benchmark_label": row.get("benchmark"),
            "catalogue_reference_url": row.get("reference_url"),
        }
        for field, value in expected.items():
            if station.get(field) != value:
                raise ValueError(
                    f"{code} {field} diverges from the canonical catalogue: "
                    f"expected {value!r}, got {station.get(field)!r}"
                )

        retrievals = station.get("retrievals")
        if not isinstance(retrievals, list) or not retrievals:
            raise ValueError(f"{code} must contain at least one retrieval record")
        catalogue_retrievals = [
            retrieval
            for retrieval in retrievals
            if isinstance(retrieval, dict) and retrieval.get("role") == "catalogue-reference"
        ]
        expected_reference_urls = catalogue_reference_urls(row.get("reference_url"))
        actual_reference_urls = [retrieval.get("requested_url") for retrieval in catalogue_retrievals]
        if actual_reference_urls != expected_reference_urls:
            raise ValueError(
                f"{code} catalogue-reference retrieval URLs must exactly match the canonical "
                "catalogue components in order"
            )

        for retrieval in retrievals:
            verify_retrieval(retrieval, code)
            timestamp = retrieval.get("retrieved_at_utc") if isinstance(retrieval, dict) else None
            if not isinstance(timestamp, str) or timestamp[:10] != manifest_date:
                raise ValueError(f"{code} retrieval date differs from the dated manifest")

        upstream_terms = station.get("upstream_terms")
        terms_url = upstream_terms.get("terms_url") if isinstance(upstream_terms, dict) else None
        if terms_url is not None and not any(
            isinstance(retrieval, dict) and retrieval.get("requested_url") == terms_url
            for retrieval in retrievals
        ):
            raise ValueError(f"{code} upstream terms URL lacks a retrieval or failure record")

        catalogue_outcomes = [retrieval.get("outcome") for retrieval in catalogue_retrievals]
        assessment = station.get("reference_assessment")
        if "failed" in catalogue_outcomes and assessment != "retrieval-failed":
            raise ValueError(f"{code} incomplete catalogue retrieval is not marked retrieval-failed")
        if all(outcome == "retrieved" for outcome in catalogue_outcomes) and assessment == "retrieval-failed":
            raise ValueError(f"{code} complete catalogue retrieval is marked retrieval-failed")

    return len(stations)


def main() -> int:
    count = verify()
    final_station = MANIFESTS[-1][1][-1]
    print(
        f"Reference provenance verified for {count} catalogue stations "
        f"across {len(MANIFESTS)} dated manifests (WB-001 through WB-{final_station:03d})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
