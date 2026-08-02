from __future__ import annotations

import argparse
import json
import zlib
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="operation", required=True)
    subparsers.add_parser("metadata")
    for operation in ("compress", "decompress"):
        command = subparsers.add_parser(operation)
        command.add_argument("input", type=Path)
        command.add_argument("output", type=Path)
    for operation in ("compress-batch", "decompress-batch"):
        command = subparsers.add_parser(operation)
        command.add_argument("job", type=Path)
    args = parser.parse_args()
    if args.operation == "metadata":
        print(json.dumps({"codec": "deliberately-broken", "deterministic": True, "protocol": "wb001-batch-v1"}))
        return 0

    def transform(operation: str, input_path: Path, output_path: Path) -> None:
        if operation == "compress":
            output = zlib.compress(input_path.read_bytes(), 6)
        else:
            decoded = bytearray(zlib.decompress(input_path.read_bytes()))
            if decoded:
                decoded[0] ^= 1
            output = bytes(decoded)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(output)

    if args.operation in {"compress", "decompress"}:
        transform(args.operation, args.input, args.output)
        return 0
    job = json.loads(args.job.read_text(encoding="utf-8"))
    operation = args.operation.removesuffix("-batch")
    for item in job["items"]:
        transform(operation, Path(item["input"]), Path(item["output"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
