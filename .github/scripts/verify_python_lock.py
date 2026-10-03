"""Require CI's Python lock to match the project's exact direct pins."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path


FACTORY_ROOT = Path(__file__).resolve().parents[2] / "factory"
PIN = re.compile(r"([A-Za-z0-9][A-Za-z0-9._-]*)==([A-Za-z0-9][A-Za-z0-9.!+_-]*)")


def parse_pins(lines: list[str], source: str) -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in lines:
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        match = PIN.fullmatch(value)
        if match is None:
            raise ValueError(f"{source}: expected an exact name==version pin: {value!r}")
        name = re.sub(r"[-_.]+", "-", match[1]).lower()
        if name in pins:
            raise ValueError(f"{source}: duplicate pin for {name}")
        pins[name] = match[2]
    return pins


def verify(factory_root: Path = FACTORY_ROOT) -> int:
    project = tomllib.loads((factory_root / "pyproject.toml").read_text(encoding="utf-8"))
    direct = parse_pins(project["project"]["dependencies"], "pyproject.toml")
    if not direct:
        raise ValueError("pyproject.toml: direct dependency pins must not be empty")
    locked = parse_pins(
        (factory_root / "requirements.lock").read_text(encoding="utf-8").splitlines(),
        "requirements.lock",
    )
    mismatches = [
        f"{name}: project={version}, lock={locked.get(name, 'MISSING')}"
        for name, version in direct.items()
        if locked.get(name) != version
    ]
    if mismatches:
        raise ValueError("Python dependency pins differ: " + "; ".join(mismatches))
    return len(direct)


def main() -> int:
    try:
        count = verify()
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Python lock verification failed: {error}")
        return 1
    print(f"Python lock matches all {count} direct dependency pins.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
