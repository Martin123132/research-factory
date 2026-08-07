# Research Factory

Research Factory is a human–AI workshop for objective, reproducible research.
It turns large problems into bounded workbenches with explicit inputs, hard
gates, metrics, economic or physical guardrails, negative-result retention and
two-person independent reproduction.

The project is currently building the aircraft hangar, not claiming scientific
breakthroughs. Synthetic commissioning proves that the machinery works; it does
not count as evidence, independent reproduction or promotion.

The human and agent working conditions are governed by the
[`OPEN_FACTORY_CHARTER.md`](OPEN_FACTORY_CHARTER.md). Factory quality is measured
through non-compensating, evidence-bound gates in
[`FACTORY_QUALITY_STANDARD.md`](FACTORY_QUALITY_STANDARD.md), not by publication,
investment or breakthrough counts.

The source repository is intended to be public construction infrastructure.
That does not make the separately hosted Hangar public and does not open
scientific intake. Candidate artifacts, hidden answers, evaluator secrets and
private identity records remain outside Git.

## Current construction state

- 100 deterministic station kits
- 99 contract drafts
- 1 commissioning-ready legacy test article
- 2 adapter-bound stations
- 3 runnable entry gates
- 0 live-research stations
- 1 closed append-only shift-report contract with 4 valid operational outcomes
- 1 universal append-only correction contract with 5 typed standing changes
- 1 conflict-independent procedural appeal ledger with unanimous-or-diagnosis routing
- 1 universal dispatch-budget gate with 18 mandatory enforcement dimensions
- 1 public material-support disclosure ledger that cannot influence truth gates
- 1 machine-verifiable 28-control quality profile: `FOUNDATION_ONLY`, not certified

The first reusable families are exact public-corpus compression and symmetric
travelling-salesperson optimisation. Each adapter is deliberately narrow: a
TSP verifier cannot silently score vehicle routing, scheduling or another
distance convention.

## Repository map

- [`factory/workbench_standard/`](factory/workbench_standard/) — closed contract
  schema, adapter registry, deterministic kit generator and governance tests.
- [`factory/workbenches/`](factory/workbenches/) — fitted station work areas and
  known-answer commissioning fixtures.
- [`factory/station_kits/`](factory/station_kits/) — generated, content-addressed
  construction envelopes for all 100 stations.
- [`factory/control_plane/`](factory/control_plane/) — work orders, blind
  validation states, disputes and append-only evidence plumbing.
- [`factory/engine/`](factory/engine/) — provider-neutral catalogue discovery,
  clean-clone diagnostics, searchable retained negative results and portable
  construction evidence packaging; start with
  [`factory/ENGINE.md`](factory/ENGINE.md).
- [`factory/disclosures/`](factory/disclosures/) — public append-only records
  of material support and decision conflicts, structurally separated from
  measurement, replication and promotion.
- [`factory/release/`](factory/release/) — verified tracked-source and Git-history
  recovery packages; see [`OFFLINE_RECOVERY.md`](OFFLINE_RECOVERY.md).
- [`factory/shift_reports/`](factory/shift_reports/) — immutable operational
  memory for progress, no-gain, blocked and unrunnable shifts; zero scientific
  standing.
- [`factory/corrections/`](factory/corrections/) — universal hash-linked
  corrigenda, rights corrections, supersessions, invalidations and retractions;
  original bytes remain visible while current standing is derived.
- [`factory/dispatch/`](factory/dispatch/) — immutable agent budgets and
  fail-closed runner admission across time, compute, spend, tools, data, network,
  hazards and human stop authority.
- [`factory/reference_provenance/`](factory/reference_provenance/) — dated,
  hash-bound source and terms checks without committing upstream datasets.
- [`factory/quality/`](factory/quality/) — the versioned quality controls,
  evidence-bound assessment and fail-closed verifier.
- [`factory/hangar/`](factory/hangar/) — the construction and commissioning web
  interface.
- [`factory/commissioning/`](factory/commissioning/) — a complete zero-credit
  synthetic shift that forces a blind disagreement, diagnostic rerun and
  fail-closed dispute audit.
- [`research_factory_100_workbenches.json`](research_factory_100_workbenches.json)
  — canonical 100-problem catalogue.

- [`factory/appeals/`](factory/appeals/) — public hash-linked procedural appeal
  decisions that reject named conflicts, never vote a split away and cannot
  alter scientific standing automatically.

## Verify the factory

```powershell
python -m pip install -r factory/requirements.lock
python -m pip install reuse==6.2.0
reuse lint
python -m unittest discover -s .github/scripts/tests -p "test_*.py" -v
python .github/scripts/verify_asset_provenance.py
python .github/scripts/verify_public_readiness.py
python factory/shift_reports/validate_shift_reports.py factory/shift_reports/examples
python -m unittest discover -s factory/shift_reports/tests -p "test_*.py" -v
python -m unittest discover -s factory/corrections/tests -t factory -p "test_*.py" -v
python -m unittest discover -s factory/appeals/tests -t factory -p "test_*.py" -v
python -m unittest discover -s factory/dispatch/tests -t factory -p "test_*.py" -v
python factory/reference_provenance/verify_reference_provenance.py
python -m unittest discover -s factory/reference_provenance/tests -p "test_*.py" -v
python factory/quality/verify_quality.py
python -m unittest discover -s factory/quality/tests -p "test_*.py" -v
python factory/workbench_standard/generate_station_kits.py --check
python factory/enginectl.py doctor
python factory/enginectl.py quality
python -m unittest discover -s factory/engine/tests -t factory -p "test_*.py" -v
python -m unittest discover -s factory/release/tests -p "test_*.py" -v
python -m unittest discover -s factory/control_plane/tests -t factory -p "test_*.py" -v
python -m unittest discover -s factory/workbenches/wb001_lossless_compression/tests -p "test_*.py" -v
python -m unittest discover -s factory/workbench_standard/tests -p "test_*.py" -v
cd factory/hangar
npm ci
npm run typecheck
npm run lint
npm test
```

## Evidence boundary

An accepted pull request is not automatically an accepted scientific result.
Scientific promotion additionally requires two reproductions owned by two
different humans, commitment before reveal, the station-specific tolerance
contract and every hard gate. The author cannot validate their own work.

Hidden holdouts, answer sheets, evaluator secrets and private identity records
are intentionally excluded from this repository. See
[`VALIDATOR_ONBOARDING.md`](VALIDATOR_ONBOARDING.md),
[`GOVERNANCE.md`](GOVERNANCE.md), [`CONTRIBUTING.md`](CONTRIBUTING.md) and
[`SECURITY.md`](SECURITY.md). Worker rights and bounded agent authority are
defined in [`OPEN_FACTORY_CHARTER.md`](OPEN_FACTORY_CHARTER.md).

Community participation is governed by
[`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md). The publication boundary and manual
post-publication checks are recorded in
[`PUBLIC_LAUNCH_CHECKLIST.md`](PUBLIC_LAUNCH_CHECKLIST.md).

## Rights and licensing status

The Factory does not take ownership of contributor work. Rights, scientific
credit, inventorship and prizes are separate records. This repository has
active path-scoped standard licences and deliberately has no repository-wide
blanket licence. Construction contributions are open under the file
classification in [`REUSE.toml`](REUSE.toml); candidate scientific artifacts
remain per-artifact or metadata-only and their deposit route is closed. Start
with [`IP_POLICY.md`](IP_POLICY.md),
[`LICENSING.md`](LICENSING.md) and
[`PATENTS_AND_PUBLIC_DISCLOSURE.md`](PATENTS_AND_PUBLIC_DISCLOSURE.md) before
submitting protected or potentially patentable material.

New construction contributors can begin with
[`CONTRIBUTOR_QUICKSTART.md`](CONTRIBUTOR_QUICKSTART.md). Nothing merged through
that route counts as scientific evidence or independent reproduction.

The private Hangar deployment is available to authorised project members at
[Research Factory Hangar 01](https://research-factory-hangar-01.clear-seed-4435.chatgpt.site).
