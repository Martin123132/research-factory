# Research Factory

This directory contains versioned **workbenches**: bounded research problems with
external truth conditions, pinned baselines, reproducible runners, and explicit
promotion gates.

The first workbench is
[`WB-001: general-purpose lossless compression`](workbenches/wb001_lossless_compression/README.md).

The working factory control plane is in [`control_plane/`](control_plane/README.md).
The provider-neutral local engine front door is documented in
[`ENGINE.md`](ENGINE.md). It verifies and navigates the 100 stations without a
website or hosted account, and delegates governed lifecycle operations to the
same append-only control plane.
Universal public-artifact corrections and retractions are implemented in
[`corrections/`](corrections/README.md). They change derived standing through a
new hash-linked record while retaining the original artifact bytes.
Conflict-independent procedural appeals are implemented in
[`appeals/`](appeals/README.md). They exclude named involved identities from
the panel, require separate reviewer commitments and route a split to diagnosis
rather than a vote; they never change scientific standing automatically.
Material-support disclosures are implemented in
[`disclosures/`](disclosures/README.md). Funding, compute credits, provider
subsidies, donations and decision conflicts are public, append-only facts; they
cannot alter a measurement, scientific gate, validator requirement or promotion.
Provider-neutral agent admission is implemented in
[`dispatch/`](dispatch/README.md). Its immutable budget covers 18 enforcement
dimensions and rejects every process runner that cannot prove them all; the
frozen pilot remains unchanged and honestly rejected by this stricter gate.
The construction and commissioning dashboard is in
[`hangar/`](hangar/README.md). It maps all 100 stations, schedules hangar work,
registers non-promotion runner interfaces and keeps a separate append-only
operational history.
Workbench Contract v1, its generator and governance tests are in
[`workbench_standard/`](workbench_standard/). The generator creates one
deterministic construction envelope per catalogue entry under
[`station_kits/`](station_kits/) without inventing missing fixtures, verifiers,
runners or results.
Pilot Round 1 is frozen in
[`rounds/WB001-PILOT-001/round.json`](rounds/WB001-PILOT-001/round.json), with a
four-hour worker shift in
[`rounds/WB001-PILOT-001/STARTER_PACK.md`](rounds/WB001-PILOT-001/STARTER_PACK.md).

## Factory rule

A result is not promoted because it looks promising. It is promoted only when:

1. every correctness and safety gate passes;
2. the benchmark and baseline versions are frozen;
3. the candidate is a useful Pareto improvement after resource and economic
   costs are counted;
4. two other accountable humans independently rerun the locked artifact; and
5. the central evaluator confirms the result on sealed holdouts.

Reproducible failures are kept as typed evidence. `RERUN_CONFIRMED_NO_GAIN`,
`BOUNDARY_FOUND`, `UNRUNNABLE`, `INVALID`, and `DISPUTED` are different states.

The event ledger adds one stricter rule: independent rerun conclusions are
committed before either is revealed. A deterministic disagreement goes to human
review; a third diagnostic run cannot erase valid contrary evidence by vote.
The candidate source package is content-addressed separately from hidden
metrics, and the holdout evaluator cannot issue a valid job until replication
has passed.

## Operating modes

The factory keeps construction, commissioning and scientific evidence separate:

1. **Hangar construction** builds workbench templates, runners, measurement
   contracts, registries, identity, scheduling and review infrastructure. It
   does not claim progress on the research problems.
2. **Commissioning drills** use explicitly synthetic operators and results in
   temporary ledgers. They may exercise every gate, but can never enter a live
   workbench history or count as independent reproduction.
3. **Live research** uses real operators and real measurements. A single person
   may explore or retain negative work, but no candidate advances through the
   two-person gate until two genuinely separate accountable humans reproduce it.

The present phase is hangar construction plus commissioning. WB-001 is the
legacy instrumented test article. WB-002 and WB-013 are fitted through separate
closed-schema adapter families for exact compression and symmetric TSP. Both
remain contract drafts until their full official benchmark boundaries are
frozen. No station is authorized for live research.

## Workbench Contract v1

The catalogue says what each station is trying to measure. Contract v1 records
whether the station can actually measure it. Every contract uses a closed JSON
Schema and keeps objective truth, hard gates, metrics, task-specific tolerances,
economic or physical accounting, the starter gate, runner trust, blind
evaluation, disputes and negative-result retention as separate governed fields.

Current generated state:

- 100 deterministic station kits;
- 99 honest `CONTRACT_DRAFT` envelopes;
- one `COMMISSIONING_READY` envelope for WB-001;
- three runnable entry gates, including the entry-only WB-002 and WB-013 fixtures;
- two `ADAPTER_BOUND` stations and 97 catalogue-only stations;
- zero `LIVE_READY` stations and zero live-research authorization.

Generate, verify and run the governance tests from the repository root:

```powershell
python factory\workbench_standard\generate_station_kits.py --write
python factory\workbench_standard\generate_station_kits.py --check
python factory\workbench_standard\generate_station_kits.py --explain WB-002
python factory\workbench_standard\generate_station_kits.py --check --require-profile WB-002=ADAPTER_BOUND
python factory\workbench_standard\generate_station_kits.py --explain WB-013
python factory\workbench_standard\generate_station_kits.py --check --require-profile WB-013=ADAPTER_BOUND
python -m unittest discover -s factory\workbench_standard\tests -p "test_*.py" -v
python factory\enginectl.py doctor
python -m unittest discover -s factory\engine\tests -t factory -p "test_*.py" -v
```

Commission the complete blind-disagreement route without making a scientific
claim:

```powershell
python factory\commissioning\run_synthetic_shift.py `
  --output factory\state\commissioning\wb001-synthetic-dispute-001
```

The normalized report distinguishes separate local identity records from
separate humans and proves that a diagnostic majority cannot erase a valid
contradiction. See
[`commissioning/README.md`](commissioning/README.md).

Commission the separate append-only correction route without changing any
scientific standing:

```powershell
Push-Location factory
.\.venv\Scripts\python.exe -m corrections.run_synthetic_drill `
  --output state\correction-synthetic-001
Pop-Location
```

The drill preserves a deliberately false original fixture, appends a
corrigendum, appends a retraction and independently re-derives the final
`RETRACTED` standing from the complete record chain.

Commission the universal dispatch-budget gate without starting a process:

```powershell
Push-Location factory
.\.venv\Scripts\python.exe -m dispatch.run_synthetic_drill `
  --output state\dispatch-budget-synthetic-001
Pop-Location
```

The drill authorises one zero-resource no-execution preflight, then proves that
the frozen local process runner is rejected for its 14 missing enforcement
dimensions. It grants no execution, scientific or promotion authority.

Commission the conflict-independent appeal route without making a scientific
claim:

```powershell
Push-Location factory
.\.venv\Scripts\python.exe -m appeals.run_synthetic_drill `
  --output state\appeal-synthetic-001
Pop-Location
```

The drill rejects a named author placed on the review panel, records a split
between two otherwise excluded reviewer identities and verifies that the split
returns to diagnosis instead of being voted away.

Commission a public material-support disclosure without making a scientific
claim:

```powershell
Push-Location factory
.\.venv\Scripts\python.exe -m disclosures.run_synthetic_drill `
  --output state\support-disclosure-synthetic-001
Pop-Location
```

The drill declares and ends a fictional compute credit, checks the append-only
hash chain and confirms that it confers no scientific standing or promotion.

`--require-stage COMMISSIONING_READY` is intentionally fail-closed: it rejects
the present 99 drafts rather than pretending a catalogue brief is runnable.

## Current scope

The trusted local runner is not a security boundary. WB-001 v0.2 also includes
a locked Docker prototype with read-only inputs, no network and bounded
resources. The local container boundary is intentionally marked
non-promotion-grade; the production boundary remains a disposable VM or
separate evaluator host.
