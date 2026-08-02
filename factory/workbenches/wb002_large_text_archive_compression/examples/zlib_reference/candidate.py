from __future__ import annotations

import argparse
import zlib
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["compress", "decompress"])
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    payload = args.source.read_bytes()
    output = zlib.compress(payload, level=6) if args.operation == "compress" else zlib.decompress(payload)
    args.destination.write_bytes(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
