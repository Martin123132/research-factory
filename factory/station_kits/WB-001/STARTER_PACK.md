# WB-001 Pilot Round 1 starter pack

This pack turns one four-hour block into either a reproducible candidate or a
useful map of a dead end. Both outcomes count as factory work.

## Before the clock starts

You need Python 3.11 or newer, the pinned dependencies in
`factory/requirements.lock`, and enough disk for the public corpus and evidence.
Docker is optional for the author's private exploration. It is mandatory for
every independent rerun and for the sealed holdout evaluator; both use the
frozen isolation policy and image lock. Never execute another person's
submitted code with the trusted local runner.

The mandatory entry run checks all frozen hashes and schemas, then runs the
reference codec through exact round-trip and determinism gates. Its purpose is
to show that the person and agent can follow the standard method before
occupying a work or rerun slot.

```powershell
.\.venv\Scripts\python.exe control_plane\scripts\run_entry_gate.py `
  --operator YOUR_OPERATOR_ID `
  --acknowledge-rules `
  --output state\YOUR_OPERATOR_ID-entry.json
```

For a future Clay or proof workbench, the same gate can point at a four-hour
Colab proof-checking exercise. It remains open to anyone; entry depends on
following the method, not holding a credential.

## Four-hour shift

### 00:00-00:30 - clock in and reproduce the floor

- Check in and record the entry-gate evidence.
- Read the selected work unit, protocol and hard rules.
- Re-run or inspect the reference result for the relevant corpus classes.
- State one falsifiable hypothesis before changing code.

### 00:30-01:00 - freeze the experiment

- Record the candidate source and dependency hashes.
- Define success, no gain, boundary found, invalid and unrunnable.
- Count headers, dictionaries, model data, decoder libraries, memory, latency,
  CPU and deployment complexity.
- Choose the smallest experiment capable of killing the idea quickly.

### 01:00-03:15 - explore

- Let the agent search only within the claimed work unit.
- Run exact decompression and determinism checks before trusting any metric.
- Keep seeds, commands, environment, failures and the first divergent step.
- Do not query or infer against the sealed holdout.
- Do not discard a sound negative result because it is not exciting.

### 03:15-04:00 - package the shift

Produce one immutable evidence bundle containing:

- hypothesis and method;
- source and artifact hashes;
- environment and dependency versions;
- public corpus and baseline commitments;
- commands, seeds, logs, failures and exact correctness results;
- compressed bytes plus encoder, decoder, memory and economic measurements;
- the frozen frontier decision bound to that exact result;
- per-corpus-class changes, not only one aggregate;
- why it worked, failed or found a boundary;
- the next unexplored branch, if one exists.

Then use `submit-result` or `record-negative-result`. Do not replace the original
attempt; append a permitted annotation after blindness ends or create a new
attempt. The work unit reopens as `OPEN_WITH_HISTORY` so later shifts can avoid
repeating the same search.

## Candidate gate

A candidate enters independent reruns only when:

- every frozen public file round-trips byte-for-byte;
- repeated runs produce identical compressed hashes;
- the exact corpus file set, source artifact and environment are locked;
- the control plane independently recalculates an advance over the frozen
  14-codec frontier;
- every decode requirement and economic cost is counted;
- the metric-free `submission.json` and declared source files form a verified,
  content-addressed rerun package;
- no forbidden holdout information was used.

Two other human owners then declare assignment independence and rerun that
package inside the frozen isolated boundary. Their conclusions remain sealed
until both commit. A valid deterministic mismatch cannot be voted away. One
procedurally invalid run may be replaced once.

The holdout job is not issued until two reruns agree. Its signed one-shot token
binds the round, attempt, artifact and exact confirming gate event. A result
obtained before replication cannot be attached afterward.

## Negative-result gate

A failed try is valuable when it identifies what was tested and prevents
repeated waste. Record the hypothesis, explored region, failure or boundary
criterion, enough evidence to separate a dead end from broken tooling, and what
would need to change before revisiting it.

Use one frozen classification: `NO_GAIN`, `HYPOTHESIS_REJECTED`,
`RESOURCE_LIMIT`, `UNRUNNABLE`, `BOUNDARY_FOUND`, or `DUPLICATE_DIRECTION`.

## Non-negotiable rules

- No one confirms their own work.
- One person cannot occupy two rerun identities.
- Credentials do not alter the evidence gate.
- A deterministic disagreement cannot be voted away.
- Hidden answers stay with the evaluator.
- Exact metrics and free text stay sealed while reruns are blind.
- Corrections append history; they do not rewrite it.
- A reproducible failed idea is completed work, not rubbish.
