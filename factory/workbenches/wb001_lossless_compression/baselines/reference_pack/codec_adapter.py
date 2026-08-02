from __future__ import annotations

import argparse
import json
import lzma
import platform
import zlib
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
PROFILES_PATH = ROOT / "profiles.json"


def load_profiles() -> dict[str, dict[str, Any]]:
    document = json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
    if document.get("schema_version") != 1:
        raise ValueError("unsupported profiles schema")
    return document["profiles"]


def runtime_metadata(profile_id: str, profile: dict[str, Any]) -> dict[str, Any]:
    codec = profile["codec"]
    library: dict[str, Any]
    if codec == "zlib":
        library = {"package": "stdlib-zlib", "runtime": zlib.ZLIB_RUNTIME_VERSION}
    elif codec == "zstd":
        import zstandard

        library = {
            "package": "zstandard",
            "package_version": zstandard.__version__,
            "libzstd": ".".join(str(part) for part in zstandard.ZSTD_VERSION),
            "backend": zstandard.backend,
        }
    elif codec == "brotli":
        import brotli

        library = {"package": "Brotli", "package_version": brotli.__version__}
    elif codec == "xz":
        library = {"package": "stdlib-lzma", "container": "xz", "check": "crc64"}
    else:
        raise ValueError(f"unsupported codec: {codec}")
    return {
        "adapter": "wb001-reference-codec-adapter",
        "adapter_version": "1.0.0",
        "profile_id": profile_id,
        "parameters": profile,
        "library": library,
        "python": platform.python_version(),
        "deterministic": True,
        "protocol": "wb001-batch-v1",
    }


def compress_bytes(data: bytes, profile: dict[str, Any]) -> bytes:
    codec = profile["codec"]
    if codec == "zlib":
        return zlib.compress(data, level=int(profile["level"]))
    if codec == "zstd":
        import zstandard

        compressor = zstandard.ZstdCompressor(
            level=int(profile["level"]),
            write_checksum=bool(profile["checksum"]),
            write_content_size=bool(profile["content_size"]),
            write_dict_id=False,
            threads=int(profile["threads"]),
        )
        return compressor.compress(data)
    if codec == "brotli":
        import brotli

        return brotli.compress(
            data,
            mode=brotli.MODE_GENERIC,
            quality=int(profile["quality"]),
            lgwin=int(profile["lgwin"]),
        )
    if codec == "xz":
        preset = int(profile["preset"])
        if profile.get("extreme"):
            preset |= lzma.PRESET_EXTREME
        return lzma.compress(
            data,
            format=lzma.FORMAT_XZ,
            check=lzma.CHECK_CRC64,
            preset=preset,
        )
    raise ValueError(f"unsupported codec: {codec}")


def decompress_bytes(data: bytes, profile: dict[str, Any]) -> bytes:
    codec = profile["codec"]
    if codec == "zlib":
        return zlib.decompress(data)
    if codec == "zstd":
        import zstandard

        return zstandard.ZstdDecompressor().decompress(data)
    if codec == "brotli":
        import brotli

        return brotli.decompress(data)
    if codec == "xz":
        return lzma.decompress(data, format=lzma.FORMAT_XZ)
    raise ValueError(f"unsupported codec: {codec}")


def transform_file(operation: str, input_path: Path, output_path: Path, profile: dict[str, Any]) -> None:
    source = input_path.read_bytes()
    if operation == "compress":
        transformed = compress_bytes(source, profile)
    elif operation == "decompress":
        transformed = decompress_bytes(source, profile)
    else:
        raise ValueError(f"unsupported operation: {operation}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(transformed)


def run_batch(operation: str, job_path: Path, profile: dict[str, Any]) -> None:
    job = json.loads(job_path.read_text(encoding="utf-8"))
    expected = f"{operation}-batch"
    if job.get("schema_version") != 1 or job.get("operation") != expected:
        raise ValueError("batch job does not match the requested operation")
    items = job.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("batch job must contain at least one item")
    for item in items:
        transform_file(operation, Path(item["input"]), Path(item["output"]), profile)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("operation", choices=["metadata", "compress", "decompress", "compress-batch", "decompress-batch"])
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args()

    profiles = load_profiles()
    if args.profile not in profiles:
        raise SystemExit(f"unknown profile: {args.profile}")
    profile = profiles[args.profile]

    if args.operation == "metadata":
        if args.paths:
            raise SystemExit("metadata accepts no paths")
        print(json.dumps(runtime_metadata(args.profile, profile), sort_keys=True))
        return 0
    if args.operation in {"compress", "decompress"}:
        if len(args.paths) != 2:
            raise SystemExit(f"{args.operation} requires input and output paths")
        transform_file(args.operation, Path(args.paths[0]), Path(args.paths[1]), profile)
        return 0
    if len(args.paths) != 1:
        raise SystemExit(f"{args.operation} requires one job-manifest path")
    run_batch(args.operation.removesuffix("-batch"), Path(args.paths[0]), profile)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
