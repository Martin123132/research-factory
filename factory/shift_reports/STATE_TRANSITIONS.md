# Shift-report attachment and state transitions

Shift reports are append-only children of a work order. They are permitted only
while the reporting operator owns an order in `CLAIMED`, `IN_PROGRESS` or
`BLOCKED` state.

```text
work order rN, active
        |
        +-- file report 1 (previous = null)
        |       work order remains rN
        |
        +-- file report 2 (previous = SHA-256(report 1))
        |       work order remains rN
        |
        +-- ordinary command changes work order to rN+1
        |
        +-- file report 3 (previous = SHA-256(report 2))
                report snapshots rN+1; it does not cause rN+1
```

The report sequence and hash link provide ordering without rewriting an earlier
record. Database uniqueness prevents two records occupying the same position.
Database triggers reject updates and deletes. A correction is therefore a new
report that refers to the earlier record in its text; the earlier bytes stay in
the chain.

Outcome classes do not imply work-order transitions:

| Outcome | Meaning inside a shift report | Work-order effect |
| --- | --- | --- |
| `PROGRESS` | A bounded direction advanced | None |
| `NO_GAIN` | A valid attempt produced no worthwhile gain | None |
| `BLOCKED` | Work could not continue under recorded conditions | None |
| `UNRUNNABLE` | The attempted procedure could not be executed | None |

Moving an order to `BLOCKED`, requesting review or completing it still requires
the existing explicit work-order command and its revision check. A report cannot
smuggle in any of those transitions.
