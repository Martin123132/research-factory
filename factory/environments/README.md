# Versioned dependency environments

Factory maintenance and frozen research rounds have different lifetimes.
Updating the engine must not rewrite a round's dependency commitment.

| Profile | Purpose | Dependency lock | Cryptography |
| --- | --- | --- | --- |
| `wb001-pilot-001-v1` | Existing frozen pilot and fixture adapters | `factory/requirements.lock` (unchanged) | 50.0.0 |
| `engine-v1` | Current engine maintenance | `factory/environments/versions/engine-v1/requirements.lock` | 50.0.2 |

`index.json` commits to each versioned manifest. Each manifest commits to its
exact dependency-lock bytes. A frozen profile also commits to the unchanged
round document and must match that round's existing dependency-lock entry.
The project manifest selects the maintenance lock explicitly. CI rejects edits
or deletions of existing files under `versions/`; upgrades add a new version.

## Set up separate interpreters

From the repository root in PowerShell:

```powershell
python -m venv factory/state/environments/pilot/.venv
factory/state/environments/pilot/.venv/Scripts/python.exe -m pip install -r factory/requirements.lock

python -m venv factory/state/environments/engine-v1/.venv
factory/state/environments/engine-v1/.venv/Scripts/python.exe -m pip install -r factory/environments/versions/engine-v1/requirements.lock

factory/state/environments/engine-v1/.venv/Scripts/python.exe factory/enginectl.py environment list --json
factory/state/environments/engine-v1/.venv/Scripts/python.exe factory/enginectl.py environment check --profile engine-v1 --json
factory/state/environments/pilot/.venv/Scripts/python.exe factory/enginectl.py environment check --profile wb001-pilot-001-v1 --json
```

On Linux/macOS use `bin/python` instead of `Scripts/python.exe`.
The environments and generated evidence are ignored local state. No command
installs anything automatically or downloads a model.

Use the maintenance interpreter for discovery, packaging and other engine-local
construction commands. Use the frozen interpreter for governed pilot lifecycle
commands and execution of existing fixture adapters. The engine front door
checks every locked package version before delegating or spawning those paths.
A mismatch exits nonzero with the expected/observed versions. It never silently
selects another interpreter or falls back to a different profile.

The old `factoryctl.py` wrapper and direct frozen scripts remain byte-for-byte
unchanged for compatibility. They do not acquire the new front-door guard:
run them only in the declared frozen environment. This is a compatibility
check, not an operating-system security boundary. To install an editable CLI
inside the frozen environment, use `pip install --no-deps --editable factory`;
ordinary dependency-resolving installation uses the newer maintenance pins.

## Small synthetic transition drill

```powershell
python factory/environments/run_synthetic_drill.py --legacy-python factory/state/environments/pilot/.venv/Scripts/python.exe --engine-python factory/state/environments/engine-v1/.venv/Scripts/python.exe --output factory/state/environment-drill-001
```

This runs a tiny public compression round-trip and deterministic test signature
under both interpreters. It compares their exact fixture output hashes and
confirms that the new interpreter fails the old-profile check. It retains
separate hashed reports, the negative check and a summary. Existing output
directories are refused rather than overwritten. CI repeats this drill on Linux
and also runs the original full factory tests in the frozen environment.

The fixture signing material is deliberately public and must never be used as
an evaluator key. Passing this drill is not scientific evidence, benchmark
requalification, a performance claim, independent reproduction or promotion.
It proves only the recorded dependency checks and this one fixture comparison.
Interpreter, platform and zlib versions are recorded; operating-system images,
package-wheel hashes, extra installed tools and hardware are not pinned or
attested by this first dependency-profile format. The original pilot's separate
software, image, corpus and promotion checks remain in force.

## Future upgrades

1. Add a successor under `versions/<new-id>/`, including a new lock and manifest.
   Never modify an existing version or the legacy `factory/requirements.lock`.
2. Add the manifest hash to the index; retain existing entries. For maintenance,
   update `current_engine` and `tool.research-factory.python-lock` together.
3. Update CI to install and check the selected maintenance profile. Keep the
   original frozen-environment job and run the relevant transition fixtures.
4. A changed scientific environment needs a separately identified successor
   round and its own qualification. No profile registration or successful
   construction drill transfers scientific status from the old round.

Dependency hashes identify bytes; they do not establish package safety. Both
environments are audited separately. If a frozen dependency becomes unsafe,
retain its historical record but do not treat reproducibility as permission to
run it unsafely; prepare an explicit successor and reassess execution risk.
