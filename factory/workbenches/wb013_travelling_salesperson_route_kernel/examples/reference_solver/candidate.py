from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_matrix(path: Path) -> list[list[int]]:
    headers: dict[str, str] = {}
    tokens: list[str] = []
    in_weights = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line == "EDGE_WEIGHT_SECTION":
            in_weights = True
            continue
        if in_weights:
            if line == "EOF":
                break
            tokens.extend(line.split())
            continue
        key, separator, value = line.partition(":")
        if separator:
            headers[key.strip().upper()] = value.strip()
    dimension = int(headers["DIMENSION"])
    weights = [int(token) for token in tokens]
    return [weights[index:index + dimension] for index in range(0, len(weights), dimension)]


def exact_held_karp(matrix: list[list[int]]) -> list[int]:
    """Return one exact tour for the deliberately tiny entry fixture."""

    dimension = len(matrix)
    states: dict[tuple[int, int], tuple[int, tuple[int, ...]]] = {}
    for node in range(1, dimension):
        states[(1 << (node - 1), node)] = (matrix[0][node], (node,))
    full_mask = (1 << (dimension - 1)) - 1
    for mask in range(1, full_mask + 1):
        for last in range(1, dimension):
            last_bit = 1 << (last - 1)
            if not mask & last_bit or mask == last_bit:
                continue
            previous_mask = mask ^ last_bit
            options = []
            for previous in range(1, dimension):
                previous_state = states.get((previous_mask, previous))
                if previous_state is not None:
                    options.append(
                        (
                            previous_state[0] + matrix[previous][last],
                            (*previous_state[1], last),
                        )
                    )
            states[(mask, last)] = min(options)
    _, path = min(
        (cost + matrix[last][0], path)
        for (mask, last), (cost, path) in states.items()
        if mask == full_mask
    )
    return [0, *path]


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic WB-013 reference candidate")
    parser.add_argument("mode", choices=["solve"])
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()
    matrix = load_matrix(args.input)
    tour = exact_held_karp(matrix)
    args.output.write_text(json.dumps({"tour": [node + 1 for node in tour]}) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
