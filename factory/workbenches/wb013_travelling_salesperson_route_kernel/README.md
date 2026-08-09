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

## Entry-fixture packet and clean-checkout rehearsal

`scripts/entry_package.py` packages the factory-owned 10-node known-answer
fixture, reference solver, exact expected evidence, and all currently locked
trusted-local evaluator assets. It is construction infrastructure: it cannot
make a TSPLIB benchmark claim, an optimum claim, a replication claim or a
promotion claim.

Build and verify it from the `factory` directory:

```powershell
.\.venv\Scripts\python.exe workbenches/wb013_travelling_salesperson_route_kernel/scripts/entry_package.py build `
  --output state/wb013-entry-fixture-package

.\.venv\Scripts\python.exe workbenches/wb013_travelling_salesperson_route_kernel/scripts/entry_package.py verify `
  state/wb013-entry-fixture-package
```

The optional rehearsal runs only the checked-in Held–Karp reference source with
a `demo:` identity. It compares the stable exact evidence and deliberately
ignores advisory timing and memory. It will not run any alternate candidate:

```powershell
.\.venv\Scripts\python.exe workbenches/wb013_travelling_salesperson_route_kernel/scripts/entry_package.py rehearse `
  state/wb013-entry-fixture-package `
  --operator-id demo:wb013-clean-clone `
  --output state/wb013-entry-fixture-rehearsal.json
```

`handoff.json` is intentionally `NOT_ELIGIBLE_ENTRY_ONLY`. The packet cannot
become eligible merely through more local reruns: official inputs, distance
conformance, a promotion-grade isolated runner and a deployed blind evaluator
remain separate prerequisites.

## Primary references

- [TSPLIB95 specification](https://comopt.ifi.uni-heidelberg.de/software/TSPLIB95/tsp95.pdf)
- [TSPLIB FAQ](https://comopt.ifi.uni-heidelberg.de/software/TSPLIB95/TSPFAQ.html)
- [Symmetric TSP optimum table](https://comopt.ifi.uni-heidelberg.de/software/TSPLIB95/STSP.html)
- [Concorde TSP solver](https://math.uwaterloo.ca/tsp/concorde/)
