# Factory control plane

For a clean-clone front door, station discovery and portable construction
packages, start with [`../ENGINE.md`](../ENGINE.md) and `enginectl.py`. Its
governed lifecycle commands delegate here; there is no second state machine.
This directory and the legacy `factoryctl.py` wrapper remain pinned by Pilot
Round 1 and must stay reproducible for that historical round.

This is the working local control plane for the Research Factory. Its canonical
database is an append-only JSONL event ledger. Every event commits to the prior
event, so editing, deleting, reordering, or inserting history is detectable.
Materialized status views are rebuilt by replaying that ledger.

The database is still **editable in the scientific sense**: workers can append
new attempts, negative results, corrections, annotations, reruns, and dispute
findings. An old claim is never silently rewritten to make a new claim look
right.

## What is enforced

- A frozen round fails closed if a workbench, corpus, baseline pack, holdout
  commitment, evaluator image, dependency lock, acceptance rule, control-plane
  source file, schema, or evaluator source file drifts.
- Every worker completes a standard entry run before claiming research or rerun
  work.
- Work claims and rerun claims are exclusive, expiring leases.
- Every attempt requires a Work Order Envelope v2 issued by an administrator
  and released with a human-retained capability. The envelope freezes exact
  argv, working directory, interfaces, wall time, output, zero local monetary
  budget, stop conditions and the no-extension rule before execution.
- The local monitored runner writes an immutable receipt. Candidate submission
  fails closed without an in-envelope successful receipt; stopped and
  over-limit executions can be retained only as negative work or termination.
- The author cannot rerun their own result.
- Two rerunners must have different operator IDs and different provider/subject
  identity records from the author and one another, and each makes an explicit
  per-assignment conflict declaration.
- The candidate's `submission.json` and declared source files are verified
  against its result artifact manifest, copied into a metric-free public
  content-addressed package, and made exportable to rerunners.
- Independent reruns must come from the frozen isolated security boundary.
- Rerun conclusions are committed into evaluator-side storage. The public
  ledger contains only their salted commitments until both are locked.
- Rerun agreement is calculated from WB-001 result documents: locked artifact,
  the exact full frozen corpus manifest, hard gates, exact compressed bytes,
  and per-file compressed hashes. The control plane recalculates the
  public-size decision against the frozen 14-codec frontier.
  A validator cannot type `AGREES` and make it true.
- A deterministic disagreement is preserved for human review. A third run is
  diagnostic; it cannot erase valid contrary evidence by majority vote.
- A signed one-shot holdout job can be issued only after two agreeing reruns.
  Its verdict must bind the round, attempt and exact confirming gate event as
  well as the artifact, holdout, evaluator key, evaluator software and image.
- Plaintext annotations are blocked while a candidate remains blind.
- Negative and no-gain work remains searchable evidence.
- Command retries can use a stable `--request-id`; reuse for a different event
  is rejected.

## Trust boundary

The current `self-asserted-local` identity level proves distinct registered
provider/subject records, **not distinct biological humans**. A person who
controls the machine can also read its private state. Public operation requires
authenticated issuer/subject identities or passkeys and a separate evaluator
host with KMS-backed sealed storage. The scientific workflow is implemented;
production identity and secrecy are deliberately not overstated.

`LOCAL_MONITORED_V1` is also a commissioning boundary, not a security sandbox.
It enforces exact argv and working directory plus wall-time and combined-output
limits, but it does not independently isolate network, filesystem, memory or
child-process use. Its schemas set `promotion_eligible` to false. A live runner
must replace this profile with an independently attested isolation boundary;
the local receipt must never be relabelled as promotion-grade evidence.

The local entry receipt and public rerun result are hash-checked, but their
origin is not signed by a remote runner. A host owner could forge a new
self-consistent document. The public service must therefore execute or sign
each assigned run itself and bind it to the rerun lease nonce. This is why the
current round is labelled `technical-workflow-pilot-no-public-promotion` even
though its objective comparison logic is live.

Likewise, a hash chain is tamper-evident only if its head is anchored elsewhere.
Use `checkpoint` and commit or sign that checkpoint periodically.

## Use the bootstrapped local pilot

This workspace already has a three-event ignored local ledger: genesis, the
frozen WB-001 round, and the pilot administrator's entry gate. Check it with:

```powershell
.\.venv\Scripts\python.exe factoryctl.py verify-ledger
.\.venv\Scripts\python.exe factoryctl.py status --round WB001-PILOT-001
```

The initial head is recorded in
`rounds/WB001-PILOT-001/bootstrap_checkpoint.json`. It becomes an external
anchor only after that checkpoint is signed or copied into a separate
versioned system.

## Bootstrap a fresh ledger

Run commands from the `factory` directory:

```powershell
.\.venv\Scripts\python.exe factoryctl.py init `
  --admin-id local:pilot-admin `
  --provider local `
  --subject pilot-admin `
  --display-name "Pilot administrator"

.\.venv\Scripts\python.exe factoryctl.py open-round `
  --actor local:pilot-admin `
  --config rounds\WB001-PILOT-001\round.json
```

A worker then checks in and completes the reproducible entry run:

```powershell
.\.venv\Scripts\python.exe factoryctl.py check-in `
  --operator-id github:alice `
  --provider github `
  --subject 12345678 `
  --display-name "Alice"

.\.venv\Scripts\python.exe control_plane\scripts\run_entry_gate.py `
  --operator github:alice `
  --acknowledge-rules `
  --output state\alice-entry.json

.\.venv\Scripts\python.exe factoryctl.py complete-entry-gate `
  --operator github:alice `
  --round WB001-PILOT-001 `
  --evidence state\alice-entry.json
```

The `github` values are labels in this local prototype; they become trustworthy
only when a server obtains them from GitHub authentication rather than CLI text.

## Work cycle

```powershell
# See the nine open work units.
.\.venv\Scripts\python.exe factoryctl.py status --round WB001-PILOT-001

# Claim one unit. Save the returned work_claim_id.
.\.venv\Scripts\python.exe factoryctl.py claim-work `
  --operator github:alice `
  --round WB001-PILOT-001 `
  --work-unit wu:selector-features

# Start its attempt.
.\.venv\Scripts\python.exe factoryctl.py issue-work-envelope `
  --actor local:pilot-admin `
  --work-claim WORK_CLAIM_ID `
  --policy control_plane\examples\wb001-synthetic-envelope-policy.json

.\.venv\Scripts\python.exe factoryctl.py start-attempt `
  --operator github:alice `
  --work-claim WORK_CLAIM_ID `
  --envelope ENVELOPE_ID

# Commission the dispatch and record its non-promotion receipt.
.\.venv\Scripts\python.exe factoryctl.py execute-attempt `
  --operator github:alice `
  --attempt ATTEMPT_ID

# Submit a candidate and its metric-free source package.
.\.venv\Scripts\python.exe factoryctl.py submit-result `
  --operator github:alice `
  --attempt ATTEMPT_ID `
  --evidence PATH_TO_WB001_RESULT_JSON `
  --comparison PATH_TO_FRONTIER_COMPARISON_JSON `
  --artifact-submission PATH_TO_SUBMISSION_JSON `
  --artifact-sha256 64_HEX_DIGEST `
  --summary "Deterministic block classifier and selection method."
```

Both envelope commands prompt for the same human-retained capability with input
hidden. Passing `--release-capability` is available for automated commissioning
tests, but exposes the value to shell history and should not be normal human use.

If the idea did not work, retain it with `record-negative-result` instead. Its
hypothesis, failure classification, reason code, and evidence hash become part
of the searchable history.

## Blind rerun cycle

The rerunner generates and saves a random capability before claiming. Supplying
the same capability and `--request-id` safely recovers an interrupted claim.
Neither the capability nor the worker's conclusion enters the public ledger.
The response identifies the metric-free artifact package to export.

```powershell
.\.venv\Scripts\python.exe factoryctl.py claim-rerun `
  --operator github:bob `
  --attempt ATTEMPT_ID `
  --capability SAVED_RANDOM_SECRET_AT_LEAST_32_CHARACTERS `
  --declare-independent

.\.venv\Scripts\python.exe factoryctl.py export-artifact `
  --package-sha256 ARTIFACT_PACKAGE_SHA256 `
  --output state\reruns\ATTEMPT_ID

.\.venv\Scripts\python.exe factoryctl.py submit-rerun `
  --operator github:bob `
  --rerun-claim RERUN_CLAIM_ID `
  --capability ONE_TIME_CAPABILITY `
  --evidence PATH_TO_WB001_RERUN_RESULT_JSON
```

The evaluator derives agreement; the rerunner does not declare it. After two
people commit, an administrator runs `evaluate-reruns`. It appends a coarse
state such as `RERUN_CONFIRMED_AWAITING_HOLDOUT`,
`TIEBREAK_DIAGNOSTIC_REQUIRED`, or `DISPUTED_REVIEW_REQUIRED`, without exposing
which validator submitted which conclusion.

After agreement, the evaluator signs a one-shot job token containing the round
hash, attempt ID and confirming rerun-gate event hash. Record it with
`record-holdout-job`; only then may its verdict be joined with
`record-holdout-attestation`. Even a valid `PASS` remains
`HOLDOUT_PASS_AWAITING_PROMOTION_GRADE_MEASUREMENT` in this local pilot; it does
not enter the trusted repository until the frozen promotion-grade runner and
economic gates also pass.

## Run the complete disagreement drill

[`../commissioning/README.md`](../commissioning/README.md) documents a disposable
zero-credit shift that exercises this machinery from entry gate through bounded
execution, two blind reruns, a deliberate split, diagnostic third run, dispute,
post-blind diagnosis and public-ledger audit. It is a test of the factory, not a
compression result and not a substitute for two other human operators.

## Files

- `ledger.py`: canonical event-chain storage and OS writer lock.
- `workflow.py`: replayable state machine and transition invariants.
- `evidence.py`: content-addressed immutable evidence copies.
- `envelope.py`: v2 policy/envelope/receipt validation and the local monitored
  commissioning runner.
- `audit.py`: metric-free public-ledger blindness and identity-separation audit.
- `sealed.py`: local evaluator-side rerun conclusion commitments.
- `attestation.py`: Ed25519 holdout-attestation verification and binding.
- `wb001_adapter.py`: objective result/comparison checks and exact rerun
  fingerprint derivation.
- `software.lock.json`: frozen hashes of the acceptance state machine, schemas,
  entry script, and pilot instructions.
- `cli.py`: `factoryctl` commands.
- `tests/`: adversarial workflow tests.

The default live state is under `factory/state/` and is intentionally ignored.
No evaluator private keys or sealed holdout files are read by this control
plane.
