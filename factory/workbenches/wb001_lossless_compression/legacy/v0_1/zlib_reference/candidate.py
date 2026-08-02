from __future__ import annotations

import argparse
import json
import zlib
from pathlib import Path


LEVEL = 6


def metadata() -> dict[str, object]:
    return {
        "codec": "zlib",
        "level": LEVEL,
        "wrapper": "zlib",
        "implementation": zlib.ZLIB_VERSION,
        "deterministic": True,
        "role": "pinned-reference-baseline",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="operation", required=True)
    subparsers.add_parser("metadata")
    for operation in ("compress", "decompress"):
        command = subparsers.add_parser(operation)
        command.add_argument("input", type=Path)
        command.add_argument("output", type=Path)
    args = parser.parse_args()

    if args.operation == "metadata":
        print(json.dumps(metadata(), sort_keys=True))
        return 0

    data = args.input.read_bytes()
    output = zlib.compress(data, LEVEL) if args.operation == "compress" else zlib.decompress(data)
    args.output.write_bytes(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

