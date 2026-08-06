# Construction contributor quickstart

You do not need a degree, paid legal advice or a scientific breakthrough to
help build the Research Factory. The first public lane is deliberately limited
to constructing and testing the workshop itself.

## 1. Pick a bounded construction task

Choose an open issue labelled `hangar-construction` or propose one with the
`Construction task` issue form. A valid task names:

- one station or `FACTORY-WIDE`;
- exact deliverable paths;
- a definition of done;
- commands that another person can run; and
- known blockers and third-party inputs.

Do not use a public issue for a confidential invention, hidden evaluator answer
or live scientific result.

## 2. Clone and branch

```powershell
git clone https://github.com/Martin123132/research-factory.git
cd research-factory
git switch -c your-name/bounded-task
```

Read the task's named files before editing. Do not alter generated station kits
directly; change their governed source and regenerate them.

## 3. Install the locked construction tools

The common checks require Python 3.11 or newer, Node.js 22.13 or newer and Git.
Create an isolated Python environment so project tools do not change your
system Python. Some Linux distributions package virtual-environment support
separately (for example, `python3-venv`).

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r factory/requirements.lock
python -m pip install reuse==6.2.0
cd factory/hangar
npm.cmd ci
cd ../..
```

Linux or macOS:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r factory/requirements.lock
python -m pip install reuse==6.2.0
cd factory/hangar
npm ci
cd ../..
```

## 4. Keep the boundary visible

Public newcomer work is one of:

- `HANGAR_CONSTRUCTION` — documentation, schemas, fixtures, tests, interfaces
  or non-promotion tooling; or
- `SYNTHETIC_COMMISSIONING` — a known-answer drill carrying zero scientific
  standing.

It is not `LIVE_RESEARCH`, a scientific reproduction or a promotion claim.

## 5. Run the declared checks

The issue defines its targeted commands. Common checks are:

```text
# Licence and provenance classification
reuse lint

# Contract or station-kit work
python factory/workbench_standard/generate_station_kits.py --check
python -m unittest discover -s factory/workbench_standard/tests -p "test_*.py" -v

# Local engine and portable evidence work
python factory/enginectl.py doctor
python -m unittest discover -s factory/engine/tests -t factory -p "test_*.py" -v

# Hangar work
cd factory/hangar
# Windows PowerShell
npm.cmd run typecheck
npm.cmd run lint
npm.cmd test

# Linux or macOS
npm run typecheck
npm run lint
npm test
```

If a task is unrunnable in your environment, record the exact command and
failure. Do not invent a passing result.

## 6. Commit without assigning ownership

```powershell
git add -- path/to/the/files-you-changed
git commit -s -m "Describe the bounded construction change"
```

The `-s` adds a `Signed-off-by` line under the Developer Certificate of Origin.
You keep your copyright. Your contribution is made available under the standard
licence assigned to its path in `REUSE.toml`.

## 7. Open a pull request

Link the construction issue and complete the rights, provenance and verification
sections. A merged construction pull request means the workshop improved. It
does not mean a research problem was solved, reproduced or promoted.

## When to stop before posting

Stop before opening an issue or pull request if the material is confidential,
you do not know whether you may share it, or patent protection might still be
wanted. Metadata and hashes can also disclose an idea. Private questions can be
worked through without uploading the protected material.
