# Append-only shift reports

A shift report preserves what a person-and-agent team attempted during one
bounded work period. It is an operational memory record, not a scientific
result. `PROGRESS`, `NO_GAIN`, `BLOCKED` and `UNRUNNABLE` are all valid outcomes.

The closed
[`shift-report-v1.schema.json`](shift-report-v1.schema.json) contract records:

- the work-order snapshot to which the report attaches;
- attempted approaches and their local decisions;
- observations, blockers and useful next leads;
- public, hash-bound provenance links to artifacts; and
- an explicit zero-standing boundary.

Every report is immutable. Reports for one work order receive a monotonically
increasing sequence and commit to the previous report's SHA-256 digest. The
Hangar stores them in a table protected against `UPDATE` and `DELETE`. Filing a
report does not change the work-order status, revision or completion time.

## Validate the examples

From `factory/`:

```powershell
python shift_reports/validate_shift_reports.py shift_reports/examples
python -m unittest discover -s shift_reports/tests -p "test_*.py" -v
```

The four examples form one synthetic chain and cover every outcome class. Their
artifact reference points to a tracked synthetic fixture by path and hash; it
does not embed artifact bytes, evaluator material or a hidden answer.

## What this does not authorize

A shift report cannot:

- close or advance a work order;
- become scientific evidence;
- count as an independent reproduction;
- create a validator verdict;
- reveal a hidden answer; or
- make anything eligible for promotion.

Those capabilities require separate contracts and remain unavailable through
this interface.
