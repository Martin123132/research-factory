# WB-013 trusted-local entry protocol

This is an executable construction gate for `DIGITAL_OPTIMIZATION_V1` with the
single allowlisted plugin `SYMMETRIC_TSP_V1`. It is not a universal optimisation
API and it does not claim full TSPLIB95 compatibility.

## Candidate interface

The trusted evaluator stages the locked instance and invokes the candidate
twice, without a shell:

```text
COMMAND solve INPUT.tsp OUTPUT.json --seed INTEGER
```

`OUTPUT.json` must contain exactly:

```json
{"tour": [1, 2, 3]}
```

The tour contains `DIMENSION` distinct one-based node IDs. Do not repeat the
first node at the end and do not report a score: candidate-reported lengths are
not evidence and extra fields are rejected.

## Implemented instance boundary

The entry parser accepts only:

- `TYPE: TSP`
- `EDGE_WEIGHT_TYPE: EXPLICIT`
- `EDGE_WEIGHT_FORMAT: FULL_MATRIX`
- a non-negative integer symmetric matrix with a zero diagonal

`EUC_2D`, `CEIL_2D`, `ATT`, `GEO`, triangular matrix encodings, ATSP, CVRP and
every other format fail closed. Each can be added only with its own conformance
fixtures against the official TSPLIB95 rules.

## Independent scoring

The evaluator rejects missing, duplicate and unknown nodes. It canonicalises
rotations and reversals of a symmetric cycle, sums every matrix edge including
the return edge, and compares two same-seed runs. Exact validity and arithmetic
have zero tolerance. Timing and peak RSS are advisory prototype observations.

## Trust and credit boundary

This runner executes only code that the local operator already trusts. Its
timeout, process-tree cleanup and output caps are not a sandbox; network and
filesystem isolation are not enforced. Every result is labelled entry-only,
zero scientific evidence, zero independent-reproduction credit, zero promotion
eligibility and not an official TSPLIB result.
