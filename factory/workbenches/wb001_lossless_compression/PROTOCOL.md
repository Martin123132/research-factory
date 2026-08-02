# WB-001 v0.2 protocol

## Candidate executable

`submission.json` declares a command array. The evaluator appends one of:

```text
<command> metadata
<command> compress-batch <job-manifest.json>
<command> decompress-batch <job-manifest.json>
```

`metadata` prints one JSON object containing `protocol:
"wb001-batch-v1"`. A batch job contains input/output path pairs. Diagnostics go
to standard error. A candidate must not depend on a network, hostname, clock,
user directory or undeclared source file.

The batch boundary is language-neutral. Python is used by the prototype
adapters, not required by the scientific contract.

## Measurement

One encode sample is one process handling the complete corpus. One decode
sample is another process restoring the complete corpus. The evaluator records
the median, every timing sample, coefficient of variation and peak RSS. Exact
bytes are portable under a pinned codec/runtime; timing is accepted only from a
predeclared promotion-grade execution class.

## Blind boundary

The public holdout commitment is published before submissions. Candidate
containers receive the holdout corpus but never receive baseline measurements,
tolerances, signing keys, detailed decisions or the private evidence store.
Networking is disabled and detailed output stays on the trusted host.

A signed one-shot token binds the candidate artifact, operator and holdout
commitment. A signed verdict commits to the private evidence without revealing
its measurements. Token reuse, source mutation, commitment mutation and
signature mutation are failures.

## Evidence states

- `INVALID`: a hard correctness or contract gate failed.
- `VALID_NO_CONFIRMED_GAIN`: correct, but advisory resource measurements cannot
  establish an advance.
- `PUBLIC_SIZE_CANDIDATE`: exact bytes beat the entire public/hidden pack by the
  predeclared threshold; promotion timing remains outstanding.
- `VALID_DOMINATED`: a promotion-grade reference point dominates the candidate.
- `VALID_NONDOMINATED_NO_GAIN`: joins a promotion-grade trade-space without
  crossing a threshold.
- `FRONTIER_ADVANCE`: advances a promotion-grade reference frontier.
- `RERUN_CONFIRMED_NO_GAIN`: two other humans reproduced the locked result.
- `RERUN_CONFIRMED_ADVANCE_AWAITING_HIDDEN_HOLDOUT`: two other humans confirmed
  an advancing locked artifact before hidden evaluation.
- `DISPUTED` or `ESCALATE`: evidence diverged or evaluator infrastructure needs
  inspection.

Failed and non-improving attempts remain searchable evidence.
