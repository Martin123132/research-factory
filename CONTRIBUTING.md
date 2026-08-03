# Contributing

Contributions are welcome from people at every level of formal education. The
standard is whether someone else can run the locked work and obtain the declared
result—not the contributor's title.

## Choose the correct scope

Every contribution should identify one scope:

- `HANGAR_CONSTRUCTION` — schemas, fixtures, runners, interfaces or governance;
- `EXPLORATION` — a hypothesis or bounded search direction;
- `NEGATIVE_RESULT` — a reproducible no-gain, boundary or failed hypothesis;
- `REPRODUCTION` — an independent rerun owned by someone other than the author;
- `DISPUTE` — evidence that two apparently equivalent procedures diverge.

Construction changes carry zero scientific credit. Do not relabel them as a
result because their tests pass.

## First-time validators

Start with [`VALIDATOR_ONBOARDING.md`](VALIDATOR_ONBOARDING.md) and open a
`Pilot validator check-in` issue. Qualification proves that your independently
owned environment can follow the locked workflow; it does not count as one of
the two reproductions for a scientific claim.

## Pull-request requirements

1. Name the workbench code and scope.
2. Lock every input, source artifact, environment and expected output that the
   station contract requires.
3. Keep candidate claims separate from verifier calculations.
4. Record seeds and repetitions for stochastic work.
5. State the practical or economic comparison, including adverse trade-offs.
6. Retain useful failed work and classify it accurately.
7. Never include hidden holdouts, answer sheets, credentials or personal data.
8. Complete the accountable-human and rights/IP declarations without treating
   schema validity as proof of ownership.
9. Record material sources, collaborators, institutional interests and AI use.
10. Do not upload confidential or patent-sensitive material. If patent
    protection may matter, stop before the issue or pull request and follow
    [`PATENTS_AND_PUBLIC_DISCLOSURE.md`](PATENTS_AND_PUBLIC_DISCLOSURE.md).
11. Complete the contribution ledger with roles, artifact references and credit
    boundaries; do not turn validation or infrastructure work into solver credit.

For a scientific claim, code review may merge construction support while the
claim remains unpromoted. Two independent reproductions are recorded separately.

Read [`IP_POLICY.md`](IP_POLICY.md),
[`CONTRIBUTOR_TERMS.md`](CONTRIBUTOR_TERMS.md) and
[`LICENSING.md`](LICENSING.md) before contributing protected material. The
licensing framework is not active yet, so external substantive work must not be
merged on an assumed or implied licence.

## Local verification

Run before opening a pull request:

```powershell
python factory/workbench_standard/generate_station_kits.py --check
Push-Location factory
python -m unittest discover -s control_plane/tests -p "test_*.py" -v
python -m unittest discover -s workbenches/wb001_lossless_compression/tests -p "test_*.py" -v
python -m unittest discover -s workbench_standard/tests -p "test_*.py" -v
Pop-Location
cd factory/hangar
npm ci
npm run typecheck
npm run lint
npm test
```

If a check cannot run, record `UNRUNNABLE` with the environment and exact
failure. Do not replace missing evidence with an assertion that it probably
works.
