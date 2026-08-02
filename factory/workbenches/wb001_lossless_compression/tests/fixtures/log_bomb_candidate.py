from __future__ import annotations

import sys


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "metadata":
        while True:
            sys.stdout.write("x" * 8192)
            sys.stdout.flush()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
