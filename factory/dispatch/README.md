# Universal dispatch-budget gate

This directory defines the provider-neutral admission contract that every new
Factory agent runner must satisfy before it can receive process-execution
authority. It complements the frozen Pilot Round 1 work-order envelope; it does
not rewrite or weaken that software lock.

The gate binds one accountable human and one immutable work order to ceilings
for:

- wall, active and idle time, plus shift count;
- CPU, memory, GPU, storage, output and process count;
- money and named billable services;
- interfaces and exact tool-manifest hashes;
- readable and writable repository paths;
- network denial or an explicit domain allowlist;
- hazard classification and a hash-bound human risk review; and
- all 18 fixed stop conditions.

The agent cannot add tools, broaden paths, increase spending, extend its shift,
self-release or change its evidence class. Any continuation requires a new
budget and a new human-retained release capability.

The accountable-human block also records its identity assurance and the fixed
warning `IDENTITY_RECORD_IS_NOT_PROOF_OF_A_DISTINCT_HUMAN`. A budget names who
holds authority; it does not manufacture identity or independence evidence.

## Admission profiles

Two built-in profiles make the current boundary visible:

| Profile | Mode | Enforced | Result |
| --- | --- | ---: | --- |
| `profile:no-execution-dry-run-v1` | `DRY_RUN_ONLY` | 18/18 | May issue a no-execution preflight ticket |
| `profile:frozen-local-monitored-v1` | `PROCESS_EXECUTION` | 4/18 | Rejected |

The dry-run profile is complete because it starts no process, tool, file,
network connection, model call or billable service. Its ticket proves only that
the admission machinery works.

The frozen local profile enforces human release, human stop, wall time and
combined output. It deliberately reports CPU, memory, GPU, storage, child
process, spend, tool, filesystem, network, hazard and complete-stop enforcement
as missing. Those source files are checked against the frozen software-lock
hashes before the profile can be inspected.

There is therefore **no process-execution profile authorised by this module**.
Adding one requires an auditable adapter that enforces every dimension; editing
a JSON file or claiming that a runner is isolated cannot create authority.

## Engine commands

From `factory/`:

```powershell
.\.venv\Scripts\python.exe enginectl.py dispatch-profiles

.\.venv\Scripts\python.exe enginectl.py dispatch-budget-verify `
  --budget dispatch\dispatch-budget.example.json

.\.venv\Scripts\python.exe enginectl.py dispatch-preflight `
  --budget dispatch\dispatch-budget.example.json `
  --profile profile:no-execution-dry-run-v1 `
  --output state\dispatch-dry-run-ticket.json `
  --require-authorized

.\.venv\Scripts\python.exe enginectl.py dispatch-ticket-verify `
  --budget dispatch\dispatch-budget.example.json `
  --ticket state\dispatch-dry-run-ticket.json
```

Tickets are canonical, self-hashed, bound to the exact budget and profile and
never overwritten in place. Even an authorised dry-run ticket still records
that human release is required and has no scientific or promotion standing.

## Synthetic commissioning

Run the known-answer gate drill into a fresh ignored directory:

```powershell
.\.venv\Scripts\python.exe -m dispatch.run_synthetic_drill `
  --output state\dispatch-budget-synthetic-001

.\.venv\Scripts\python.exe -m dispatch.verify_synthetic_drill `
  state\dispatch-budget-synthetic-001
```

The drill issues one no-execution ticket and one explicit rejection for the
partial local runner. It verifies both artifacts and proves that no process was
started. It is synthetic commissioning, not agent work or scientific evidence.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover `
  -s dispatch\tests -p "test_*.py" -v
```

The suite covers self-hashes, duplicate keys, protected paths, self-expansion,
expired windows, execution-mode mismatches, source drift, ticket tampering,
no-overwrite behaviour, the engine front door and the complete drill.
