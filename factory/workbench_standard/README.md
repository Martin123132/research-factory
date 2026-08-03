# Workbench Contract v1

This directory turns the 100-station catalogue into deterministic construction
kits. It does not turn a brief into a result and it never assigns scientific,
reproduction or promotion credit.

## Contents

- `schema/workbench-contract-v1.schema.json` — closed Draft 2020-12 contract.
- `schema/rights-and-ip-v1.schema.json` — closed contributor declaration
  vocabulary that cannot claim Factory legal clearance.
- `schema/contribution-ledger-v1.schema.json` — role, credit and external-prize
  provenance without automatic authorship or inventorship claims.
- `generate_station_kits.py` — fail-closed generator and semantic validator.
- `commissioning/` — self-hashed adapter registry, closed override schemas and
  named transformations that cannot set governance or readiness.
- `templates/` — submission, negative-result, dispute and validator templates.
- `tests/test_station_kits.py` — adversarial governance and determinism tests.

Generated outputs live in `factory/station_kits/WB-NNN/`. Each kit contains the
contract and schema snapshot, a closed file manifest, entry-pack status,
verification boundary, runner trust declaration and the shared evidence
templates. Missing scientific infrastructure is represented by an unresolved
gate, never a plausible placeholder.

## Commands

```powershell
python factory\workbench_standard\generate_station_kits.py --write
python factory\workbench_standard\generate_station_kits.py --check
python factory\workbench_standard\generate_station_kits.py --explain WB-002
python factory\workbench_standard\generate_station_kits.py --check --require-profile WB-002=ADAPTER_BOUND
python factory\workbench_standard\generate_station_kits.py --explain WB-013
python factory\workbench_standard\generate_station_kits.py --check --require-profile WB-013=ADAPTER_BOUND
python -m unittest discover -s factory\workbench_standard\tests -p "test_*.py" -v
```

To prove that incomplete stations cannot silently pass a stricter build gate:

```powershell
python factory\workbench_standard\generate_station_kits.py --check --require-stage COMMISSIONING_READY
```

That command currently fails on the 99 drafts, as intended. WB-001 is commissioning
ready but still has no live-research or promotion authority.

WB-002 demonstrates progressive construction without stage inflation: its
`DIGITAL_COMPRESSION_V1` dossier, runner protocol, exact known-answer fixture,
starter instructions and evidence schemas are locked, so the generated profile
is `ADAPTER_BOUND`. Its station stage stays `CONTRACT_DRAFT` because `enwik9`
has not been acquired and content-addressed, the mutable official record has not
been frozen into an authority snapshot, and the full official package/resource
scorer is not implemented.

WB-013 is the second adapter-bound station and the first fitted optimisation
station. `DIGITAL_OPTIMIZATION_V1` enables only `SYMMETRIC_TSP_V1`; its local
entry gate handles an exact `EXPLICIT/FULL_MATRIX` fixture. Official TSPLIB
assets, other distance encodings, hidden generalisation inputs, economic prices
and promotion-grade execution remain explicit blockers.
