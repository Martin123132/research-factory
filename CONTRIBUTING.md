# Contributing

Contributions are welcome from people at every level of formal education. The
standard is whether someone else can run the locked work and obtain the declared
result—not the contributor's title.

For a first construction contribution, use
[`CONTRIBUTOR_QUICKSTART.md`](CONTRIBUTOR_QUICKSTART.md).
Participation also requires following
[`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md). Your working rights, including
bounded work, provider choice, pause or exit, retained attribution and
non-retaliation, are stated in
[`OPEN_FACTORY_CHARTER.md`](OPEN_FACTORY_CHARTER.md).

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
12. For dispatched agent work, state the accountable human, allowed interfaces,
    compute or material ceiling and stop condition; an agent may not expand its
    own authority or scientific standing.

For a scientific claim, code review may merge construction support while the
claim remains unpromoted. Two independent reproductions are recorded separately.

Read [`IP_POLICY.md`](IP_POLICY.md),
[`CONTRIBUTOR_TERMS.md`](CONTRIBUTOR_TERMS.md) and
[`LICENSING.md`](LICENSING.md) before contributing protected material. The
path-scoped licensing framework is active for construction work. Commits must
carry a `Signed-off-by` trailer (`git commit -s`). Candidate scientific
artifacts remain outside this route and never inherit the licence of a nearby
Factory file.

Every new tracked file must be classified by [`REUSE.toml`](REUSE.toml) or
valid file-local SPDX information. Run `reuse lint` before submitting when the
REUSE tool is available; CI performs the authoritative check.

## Local verification

Use the narrowest relevant check while developing:

- documentation, issue forms or provenance: `reuse lint`;
- station contracts or generated kits: the generator check and workbench
  standard tests;
- control-plane changes: the control-plane tests;
- Charter or quality changes: the quality verifier and quality tests;
- Hangar changes: typecheck, lint and Hangar tests.

The full pull-request gate remains:

```powershell
python -m pip install -r factory/requirements.lock
python -m pip install reuse==6.2.0
reuse lint
python -m unittest discover -s .github/scripts/tests -p "test_*.py" -v
python .github/scripts/verify_asset_provenance.py
python .github/scripts/verify_public_readiness.py
python factory/quality/verify_quality.py
python -m unittest discover -s factory/quality/tests -p "test_*.py" -v
python factory/workbench_standard/generate_station_kits.py --check
Push-Location factory
python shift_reports/validate_shift_reports.py shift_reports/examples
python -m unittest discover -s shift_reports/tests -p "test_*.py" -v
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

When citing the infrastructure, identify the exact artifact and contributors
used rather than treating the repository as the author of a scientific result.
[`CITATION.cff`](CITATION.cff) provides repository-level metadata.

If a check cannot run, record `UNRUNNABLE` with the environment and exact
failure. Do not replace missing evidence with an assertion that it probably
works.
