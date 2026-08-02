# WB-013 starter pack

Target: 45–60 minutes. This is a method-following gate, not a credential test
and not an attempt to discover a better route.

1. Read `PROTOCOL.md` and identify the supported TSPLIB subset.
2. Inspect the factory-owned 10-node matrix. Confirm that it is symmetric and
   that its diagonal is zero.
3. Run:

   ```powershell
   python factory/workbenches/wb013_travelling_salesperson_route_kernel/scripts/run_entry_gate.py --fixture --output work/wb013-entry-result.json
   ```

4. Inspect the result. Explain why the verifier, rather than the candidate,
   owns tour validity and route-length arithmetic.
5. Record `PASS`, `INVALID` or `UNRUNNABLE`. A careful failure report is valid
   construction work; this fixture creates no scientific credit.

The next, deliberately unresolved pack will acquire official TSPLIB instances,
freeze their raw hashes, implement each distance encoding through conformance
tests, and add a hidden generalisation suite. Until then, do not call this a
TSPLIB benchmark result.
