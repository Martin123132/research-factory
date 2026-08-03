from __future__ import annotations

import argparse
import re
import subprocess


SIGN_OFF = re.compile(
    r"^Signed-off-by:\s+\S.*\s+<[^<>\s]+@[^<>\s]+>\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Require a DCO Signed-off-by trailer on every pull-request commit."
    )
    parser.add_argument("--base", required=True, help="Pull-request base commit SHA")
    parser.add_argument("--head", required=True, help="Pull-request head commit SHA")
    args = parser.parse_args()

    commits = [
        value
        for value in git("rev-list", "--reverse", "--no-merges", f"{args.base}..{args.head}").splitlines()
        if value
    ]
    if not commits:
        raise SystemExit("No non-merge pull-request commits were found.")

    missing: list[str] = []
    for commit in commits:
        message = git("show", "-s", "--format=%B", commit)
        if not SIGN_OFF.search(message):
            subject = git("show", "-s", "--format=%s", commit).strip()
            missing.append(f"{commit[:12]} {subject}")

    if missing:
        print("DCO sign-off is missing from:")
        for row in missing:
            print(f"- {row}")
        print("Add your trailer with `git commit -s` and update the pull request.")
        return 1

    print(f"DCO sign-off verified for {len(commits)} pull-request commit(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
