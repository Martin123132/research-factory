# Local-first factory engine

The repository is the durable factory. The Hangar website is an optional view
over it, not a runtime dependency. A clean clone can inspect all 100 stations,
verify their contracts, create hash-bound work packages and operate the existing
append-only workflow without a hosted site, GitHub API, OpenAI account or any
other model provider.

## Engine shape

```text
100-station catalogue + generated contracts
                    |
                    v
          enginectl / factoryctl
             |             |
             v             v
  portable work package   governed event ledger
  (construction only)     (claims, attempts, reruns, disputes)
             |             |
             +------ optional adapters ------+
                    GitHub / Hangar / CI
```

There is one governed state machine. The engine front door delegates lifecycle
commands to `control_plane`; it does not maintain a competing database. GitHub
is useful for distributing source, issues and reviews, but a pull request is not
a scientific result and GitHub is not the scientific system of record.

Dispatch now fails closed through Work Order Envelope v2. Before an attempt can
start, an administrator binds its exact local command, working directory,
interfaces, wall-time/output/cost limits and stop rules to the work claim; the
human then releases it with a capability kept out of the public ledger. The
commissioning executor records a receipt, and only a successful in-envelope
receipt can enter candidate reruns. `LOCAL_MONITORED_V1` is deliberately marked
non-promotion because it does not yet isolate network, filesystem or memory.

## Start from a clean clone

From the repository root on Windows PowerShell:

```powershell
python -m venv factory\.venv
factory\.venv\Scripts\python.exe -m pip install -r factory\requirements.lock
factory\.venv\Scripts\python.exe factory\enginectl.py doctor
factory\.venv\Scripts\python.exe factory\enginectl.py quality
factory\.venv\Scripts\python.exe factory\enginectl.py list --entry-ready
factory\.venv\Scripts\python.exe factory\enginectl.py inspect WB-013
```

On Linux or macOS, replace `factory\.venv\Scripts\python.exe` with
`factory/.venv/bin/python` and use `/` in paths.

`doctor` verifies the source catalogue commitment, root station manifest, all
100 contract commitments, their closed JSON Schema and every generated kit file.
It also reports the operating boundary: currently 100 stations, three runnable
entry gates and zero stations authorised for live research.

These discovery commands do not create local state. To verify a ledger as part
of the same diagnostic, pass it explicitly:

```powershell
factory\.venv\Scripts\python.exe factory\enginectl.py doctor `
  --ledger factory\state\pilot_events.jsonl
```

## Inspect Factory quality

`quality` verifies the 28-control Open Factory profile, its exact standard,
every cited evidence hash, derived outcome counts, current station readiness and
certification prerequisites:

```powershell
factory\.venv\Scripts\python.exe factory\enginectl.py quality
factory\.venv\Scripts\python.exe factory\enginectl.py quality --json
```

The current result is `FOUNDATION_ONLY`: 19 controls meet their declared
minimum, seven remain partial and two are blocked. Operational, scientific and
independent-audit certification remain false. Passing the command verifies that
this self-assessment is internally honest; it does not certify the Factory.

## Search retained negative results

Failed hypotheses, measured boundaries, no-gain results and unrunnable paths
are useful factory output. Search their public metadata without opening private
evidence or changing the append-only ledger:

```powershell
factory\.venv\Scripts\python.exe factory\enginectl.py negative-results `
  --ledger factory\state\pilot_events.jsonl `
  --query "small block header" `
  --classification HYPOTHESIS_REJECTED
```

Exact filters are also available for `--round`, `--work-unit` and
`--reason-code`; use `--json` for machine-readable output. Query words are
case-insensitive and all must occur somewhere in the public attempt ID, round,
work unit, author, classification, reason, hypothesis or summary. Results are
newest first and expose content hashes rather than private evidence contents.
The command verifies the ledger hash chain before searching it and performs no
writes.

## Correct public artifacts without erasing history

`correction-append` writes a universal correction record to a separate public
hash chain. Its target is an immutable artifact ID and SHA-256, not a mutable
database row. Corrigenda, rights corrections and supersessions must name
different replacement bytes. Invalidations and retractions cannot carry a
replacement, and terminal standing cannot be restored in v1.

```powershell
factory\.venv\Scripts\python.exe factory\enginectl.py correction-append `
  --ledger factory\state\public\corrections.jsonl `
  --draft factory\corrections\correction-draft.example.json

factory\.venv\Scripts\python.exe factory\enginectl.py correction-verify `
  --ledger factory\state\public\corrections.jsonl

factory\.venv\Scripts\python.exe factory\enginectl.py correction-history `
  --ledger factory\state\public\corrections.jsonl
```

The history view reports the standing recorded at every step and the current
standing derived from the whole verified chain. Original bytes are never
rewritten. Identity and authority fields are accountable assertions, not proof
that an actor is independent or legally entitled to act. Correction records
carry zero scientific standing and cannot promote an artifact.

## Portable construction packages

The portable package command copies a local evidence file or directory into a
closed bundle. It records exact commands, seeds, a bounded environment record,
the current station contract and schema, a per-file manifest and top-level
SHA-256 commitments.

```powershell
factory\.venv\Scripts\python.exe factory\enginectl.py package `
  --workbench WB-013 `
  --attempt attempt:alice-first-fixture `
  --operator human:alice `
  --summary "Ran the published known-answer TSP fixture." `
  --command "python factory/workbenches/wb013_travelling_salesperson_route_kernel/scripts/run_entry_gate.py --fixture --output work/result.json" `
  --source work `
  --output packages\alice-first-fixture

factory\.venv\Scripts\python.exe factory\enginectl.py verify `
  packages\alice-first-fixture
```

Package verification does not trust filenames or the author's claim. It rejects
changed bytes, missing or extra files, symbolic links, path escapes, duplicate
JSON keys, schema drift and broken commitments. It separately reports whether
the embedded contract matches the repository's current station commitment; a
structurally valid historical bundle with `current_contract_match: false` must
not be treated as current work.

Packaging is not redaction. Review the selected files and command strings before
sharing a bundle; never package credentials, hidden evaluator inputs, private
identity records or confidential invention details.

Portable packages deliberately carry `scientific_evidence: false`,
`counts_as_independent_reproduction: false` and `eligible_for_promotion: false`.
They are useful shift hand-offs and construction records. They cannot bypass
station readiness, human independence, blind commitment, the two-rerun gate or
the central evaluator. Once a station is genuinely live, its scientific artifact
must enter through a versioned round and the governed lifecycle described in
[`control_plane/README.md`](control_plane/README.md).

## Governed lifecycle compatibility

Installing the project in editable mode exposes the combined command:

```powershell
Push-Location factory
.\.venv\Scripts\python.exe -m pip install --no-deps --editable .
.\.venv\Scripts\factoryctl.exe doctor
.\.venv\Scripts\factoryctl.exe status --round WB001-PILOT-001
Pop-Location
```

The version-pinned `factory/factoryctl.py` wrapper and the files under
`control_plane/` remain byte-for-byte compatible with frozen Pilot Round 1.
`enginectl.py` is the new clean-clone front door: local commands are handled by
the engine facade and all established lifecycle commands are passed to that same
frozen control plane.

## What survives loss of hosted services

If the current paid site is cancelled, the public repository, station contracts,
entry fixtures, CLI, local ledgers, evidence stores and test suite continue to
work. Only that hosted visual interface disappears. A future website can be
rebuilt from repository data or attached as another read-only adapter without
changing the evidence rules.
