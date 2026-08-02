# Validator onboarding

This is the entry route for a human who wants to operate an independent
Research Factory rerun. It tests whether a person and their agent can follow a
locked method and retain auditable evidence. It does not test credentials, and
passing it does not create scientific credit.

The current repository is a technical-workflow pilot. No station is authorised
for public scientific promotion yet.

## Who may validate

A validator must:

- be a different human from the claim author and the other required validator;
- operate their own GitHub identity and environment;
- disclose shared employment, collaboration, funding or other material conflicts;
- avoid the author's result, the other validator's result and every hidden answer
  until their own evidence commitment is locked;
- accept that `INVALID`, `UNRUNNABLE`, `NO_GAIN` and disagreement are useful
  outcomes when recorded accurately.

Degrees, job titles and institutional affiliation are not entry requirements.
One person using two accounts is one person and cannot fill two validator slots.

## First-day qualification

### 1. Clone and verify the construction snapshot

From the repository root on Windows PowerShell:

```powershell
python -m venv factory\.venv
factory\.venv\Scripts\python.exe -m pip install -r factory\requirements.lock
factory\.venv\Scripts\python.exe factory\workbench_standard\generate_station_kits.py --check

Push-Location factory
.\.venv\Scripts\python.exe -m unittest discover -s control_plane\tests -p "test_*.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s workbenches\wb001_lossless_compression\tests -p "test_*.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s workbench_standard\tests -p "test_*.py" -v
Pop-Location
```

The expected construction check is 100 deterministic station kits followed by
75 passing Python tests. A platform-specific failure is recorded as
`UNRUNNABLE`; it is not papered over with a claimed pass.

On Linux or macOS, use `factory/.venv/bin/python` and the corresponding POSIX
paths. The evidence requirements are identical across operating systems.

### 2. Complete the WB-001 entry run

The entry run verifies frozen hashes and schemas, then exercises exact
round-trip and deterministic reference behaviour:

```powershell
Push-Location factory
.\.venv\Scripts\python.exe control_plane\scripts\run_entry_gate.py `
  --operator github:YOUR_GITHUB_HANDLE `
  --acknowledge-rules `
  --output state\YOUR_GITHUB_HANDLE-entry.json
Pop-Location
```

The receipt remains local because `factory/state/` is ignored. Post only its
SHA-256, bounded environment description and pass/fail state in a validator
check-in issue. Never post credentials, machine secrets, hidden inputs or
absolute paths containing personal information.

### 3. Reproduce the synthetic test article

The first two pilot validators will rerun a known-answer commissioning artifact
under separate human ownership. This validates assignment, isolation, evidence
commitment, reveal and dispute plumbing. It carries zero scientific credit and
cannot promote a research claim.

The pilot succeeds only if both people can independently:

1. receive the same metric-free, content-addressed artifact;
2. bind their own environment and runner to it;
3. commit evidence before seeing any expected conclusion;
4. produce a result that the evaluator can compare mechanically;
5. preserve any mismatch instead of editing it away.

## Per-assignment workflow

1. The human validator accepts one rerun lease and declares independence.
2. The Factory supplies the locked contract, input commitments, candidate
   artifact and command without the author's result.
3. The validator runs every hard gate inside the required isolation boundary.
4. The validator commits the result and evidence hashes before reveal.
5. Only after both validators commit may the evaluator return a bounded state.
6. Agreement advances to the next gate. A deterministic mismatch opens a
   dispute; a third run may diagnose but cannot outvote contrary evidence.

GitHub review approval is source-code review. It is never a substitute for this
scientific reproduction workflow.

## Foundational and Clay-style stations

No Clay Mathematics station is live. When a foundational station is
commissioned, its entry route may include a published Colab exercise designed
to take roughly four hours. The exercise will use visible inputs and a
machine-checkable receipt while keeping its answer sheet outside the agent's
environment.

That gate measures willingness to complete the standard method, not whether the
entrant already knows the solution. It remains open to people without formal
mathematics credentials. Exact proof claims will additionally require the
station's formal proof assistant, dependency locks and zero-tolerance proof
checker before entering independent review.

## Stop and escalate when

- the artifact, contract or input hash differs;
- the isolation boundary cannot be reproduced;
- an instruction exposes an expected result before commitment;
- the author asks for tuning help during an independent rerun;
- identities or conflicts are not genuinely independent;
- two valid deterministic runs disagree.

Do not decide who is right from reputation. Record the first material
divergence and move the claim to structured review.
