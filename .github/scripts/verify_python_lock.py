"""Require CI's Python lock to match the project's exact direct pins."""

from __future__ import annotations

import re
import argparse
import subprocess
import sys
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
    relative = project.get("tool", {}).get("research-factory", {}).get("python-lock", "requirements.lock")
    if not isinstance(relative, str) or not re.fullmatch(r"requirements\.lock|environments/versions/[a-z][a-z0-9-]{0,63}/requirements\.lock", relative):
        raise ValueError("unsupported Python lock path")
    lock_path = factory_root / relative
    if lock_path.is_symlink() or not lock_path.resolve().is_relative_to(factory_root.resolve()):
        raise ValueError("Python lock path escapes the factory")
    locked = parse_pins(lock_path.read_text(encoding="utf-8").splitlines(), relative)
    mismatches = [
        f"{name}: project={version}, lock={locked.get(name, 'MISSING')}"
        for name, version in direct.items()
        if locked.get(name) != version
    ]
    if mismatches:
        raise ValueError("Python dependency pins differ: " + "; ".join(mismatches))
    return len(direct)


def verify_append_only(base: str, head: str) -> None:
    if not all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in (base, head)):
        raise ValueError("history verification requires full commit SHAs")
    changes = subprocess.check_output(
        ["git", "diff", "--name-status", "--no-renames", base, head, "--", "factory/environments/versions"],
        cwd=FACTORY_ROOT.parent, text=True, encoding="utf-8",
    )
    for line in changes.splitlines():
        if line.split("\t", 1)[0] != "A":
            raise ValueError(f"versioned environments are append-only; add a successor: {line}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base")
    parser.add_argument("--head")
    args = parser.parse_args()
    try:
        count = verify()
        sys.path.insert(0, str(FACTORY_ROOT))
        from engine.environments import profiles
        index, loaded = profiles(FACTORY_ROOT)
        project = tomllib.loads((FACTORY_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        if project["tool"]["research-factory"]["python-lock"] != loaded[index["current_engine"]]["lock"]["path"]:
            raise ValueError("project and current engine environment disagree")
        if bool(args.base) != bool(args.head):
            raise ValueError("--base and --head must be supplied together")
        if args.base:
            verify_append_only(args.base, args.head)
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        print(f"Python lock verification failed: {error}")
        return 1
    print(f"Python lock matches all {count} direct dependency pins.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
