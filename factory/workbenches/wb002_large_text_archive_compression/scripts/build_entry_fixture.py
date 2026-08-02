from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "entry_fixture.txt"


def build_payload() -> bytes:
    paragraphs: list[str] = []
    for article in range(512):
        title = f"<title>Commissioning article {article:04d}</title>"
        facts = " ".join(
            f"measurement-{index}={((article + 17) * (index + 11)) % 104729}"
            for index in range(24)
        )
        paragraphs.append(
            f"<page id=\"{article}\">{title}\n"
            f"A reproducible archive records inputs, exact commands, environment, and negative results. {facts}\n"
            f"Unicode check: geometry π; force F=ma; evidence before claims.\n</page>\n"
        )
    return "".join(paragraphs).encode("utf-8")


def main() -> int:
    payload = build_payload()
    OUTPUT.write_bytes(payload)
    print(f"{OUTPUT}: {len(payload)} bytes sha256={hashlib.sha256(payload).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
