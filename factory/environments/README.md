# Versioned dependency environments

Dependency upgrades create successors; they never rewrite a research round's
dependency commitment or transfer its results.

| Profile | Use | Brotli | Cryptography |
| --- | --- | --- | --- |
| `wb001-pilot-001-v1` | Retained historical pilot; original `factory/requirements.lock` | 1.2.0 | 50.0.0 |
| `engine-v1` | Retained historical maintenance | 1.2.0 | 50.0.2 |
| `wb001-pilot-002-v1` | Current patched pilot and construction fixture execution | 1.2.1 | 50.0.0 |
| `engine-v2` | Current maintenance and discovery | 1.2.1 | 50.0.2 |

The original lock, both historical manifests, `WB001-PILOT-001`, its frozen
software, reference results, contracts and scientific gates remain unchanged.
Historical Brotli 1.2.0 has a known audit finding. These profiles remain
registered for historical verification; normal CI no longer installs or executes
them. Retaining their bytes is not security approval.

The successor `WB001-PILOT-002` binds its own versioned dependency lock and has
a distinct round hash. It reuses the existing contracts and reference material
for construction qualification only. No old attempts, benchmark status,
independent reproductions or promotion eligibility carry over. The required
independent reruns, signed holdout and isolated execution gates remain in force.
The original reference pack has not been regenerated or requalified.

## Install the replacement

From the repository root in PowerShell:

```powershell
python -m venv factory/state/environments/pilot-002/.venv
factory/state/environments/pilot-002/.venv/Scripts/python.exe -m pip install -r factory/environments/versions/wb001-pilot-002-v1/requirements.lock

python -m venv factory/state/environments/engine-v2/.venv
factory/state/environments/engine-v2/.venv/Scripts/python.exe -m pip install -r factory/environments/versions/engine-v2/requirements.lock

factory/state/environments/pilot-002/.venv/Scripts/python.exe factory/enginectl.py environment check --profile wb001-pilot-002-v1 --json
factory/state/environments/engine-v2/.venv/Scripts/python.exe factory/enginectl.py environment check --profile engine-v2 --json
```

On Linux/macOS use `bin/python` instead of `Scripts/python.exe`.
Generated environments and evidence are ignored local state.

Use the patched pilot interpreter for fixture packets, shifts and governed
commands through `enginectl.py`. These paths check every pinned package before
execution. Governed commands default to separate state under
`factory/state/WB001-PILOT-002/`; opening a round requires
`--config factory/rounds/WB001-PILOT-002/round.json`.
The entry-gate script must likewise receive that path with `--round`.
Historical ledgers remain inspectable, but the front door refuses mutations
against another round or the old default state locations. Historical shifts can
be inspected/exported; executing or resuming one requires a new task and directory.

The old `factoryctl.py` wrapper and direct frozen scripts remain unchanged.
They do not gain these new front-door guards. Their historical defaults must
not be used to run the replacement as the old pilot. Compatibility checks are
not an OS sandbox or protection against uncooperative concurrent writers.

## Validation and preserved history

CI installs and audits both active locks without advisory suppressions. It runs
the full factory regression suite in the patched pilot, maintenance CLI tests
in engine-v2, and complete shift/handover tests on Linux and Windows. Historical
control-plane test fixtures remain regression examples, not new scientific
evidence under the historical environment.

```powershell
python factory/environments/run_synthetic_drill.py --research-python factory/state/environments/pilot-002/.venv/Scripts/python.exe --engine-python factory/state/environments/engine-v2/.venv/Scripts/python.exe --output factory/state/environment-drill-002
```

This drill compares exact zlib/Brotli public round-trip and deterministic test
signature outputs across the two patched environments. Both must reject the
old profile. Hashed reports are written only to a fresh output directory.
The public fixture signing key is not an evaluator credential. The drill is
construction evidence, not a benchmark, independent reproduction or promotion.

The index hashes every manifest; manifests hash their locks and round bindings.
PR verification rejects edits/deletions of existing version files, frozen rounds
and the original requirements lock. Existing software commitments are checked
by the frozen contract validators. Python/platform and dependency versions are
recorded; wheel hashes, extra tools, OS images and hardware are not pinned by
this profile format.

## Future upgrades

Add a new version and index entry; retain previous entries and bytes. Update the
maintenance manifest selection and project pins together. A research dependency
change needs a new round identity and lock commitment, explicit runtime/CI
selection, separate state, transition tests and its own scientific qualification.
Retire unsafe automatic execution while retaining the historical record.
