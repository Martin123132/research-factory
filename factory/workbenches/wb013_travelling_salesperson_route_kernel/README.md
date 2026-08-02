# WB-013 — Travelling-salesperson route kernel

WB-013 is the first station bound to `DIGITAL_OPTIMIZATION_V1`. The adapter is a
closed family framework; this station enables only `SYMMETRIC_TSP_V1` and the
entry evaluator implements only TSPLIB's `EXPLICIT/FULL_MATRIX` representation.

## What works now

- factory-owned 10-node known-answer fixture;
- independently calculated Hamiltonian-cycle validity and exact route length;
- rotation/reversal canonicalisation for symmetric tours;
- same-seed double execution;
- locked submission/result schemas and trusted-local process controls;
- structured, but not price-frozen, practical routing accounting.

## What does not work yet

- official TSPLIB assets are not bundled or factory-hashed;
- coordinate and compressed-matrix distance conventions are not implemented;
- no hidden generalisation suite or frozen scientific comparator exists;
- compute, energy and economic inputs are not frozen;
- the runner is not isolated, promotion-grade or centrally blind;
- no result here is scientific evidence or an official optimum claim.

The station therefore remains `ADAPTER_BOUND / CONTRACT_DRAFT` with scientific
standing `NONE`. Passing the entry gate proves only that the local workflow and
the operator's method discipline work as specified.

## Primary references

- [TSPLIB95 specification](https://comopt.ifi.uni-heidelberg.de/software/TSPLIB95/tsp95.pdf)
- [TSPLIB FAQ](https://comopt.ifi.uni-heidelberg.de/software/TSPLIB95/TSPFAQ.html)
- [Symmetric TSP optimum table](https://comopt.ifi.uni-heidelberg.de/software/TSPLIB95/STSP.html)
- [Concorde TSP solver](https://math.uwaterloo.ca/tsp/concorde/)
