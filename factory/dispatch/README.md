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

Three built-in profiles make the current boundary visible:

| Profile | Mode | Enforced | Result |
| --- | --- | ---: | --- |
| `profile:no-execution-dry-run-v1` | `DRY_RUN_ONLY` | 18/18 | May issue a no-execution preflight ticket |
| `profile:frozen-local-monitored-v1` | `PROCESS_EXECUTION` | 4/18 | Rejected |
| `profile:container-commissioning-v1` | `PROCESS_EXECUTION` | 18/18 | May issue a **commissioning-only** ticket; the adapter performs another fail-closed host check before starting |

The dry-run profile is complete because it starts no process, tool, file,
network connection, model call or billable service. Its ticket proves only that
the admission machinery works.

The frozen local profile enforces human release, human stop, wall time and
combined output. It deliberately reports CPU, memory, GPU, storage, child
process, spend, tool, filesystem, network, hazard and complete-stop enforcement
as missing. Those source files are checked against the frozen software-lock
hashes before the profile can be inspected.

The container profile source-locks an auditable Docker adapter and request
schema. It accepts only a locally available, digest-pinned image and a
canonical exact-command manifest already allowlisted by the budget. It starts
Docker with a read-only root, no network, no GPU flag, dropped capabilities,
`no-new-privileges`, a non-root user, a PID limit, memory limit, CPU ulimit,
bounded tmpfs work directory, and read-only mounts for every declared input.
The runner itself captures stdout and stderr, applies wall/active/idle/output
stops, gives the human a stop-file control, and copies bounded output only to a
previously empty declared write location.

This is deliberately a **commissioning adapter**, not a claim that containers
are magic. An authorised ticket is necessary but not sufficient: an unavailable
Docker daemon, a missing local image, or an unsupported Docker flag causes a
fail-closed non-start. The daemon, kernel and host configuration remain part of
the local trusted computing base. A completed run has no scientific standing,
does not prove the identity of the person holding the release capability, and
cannot promote an output.

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

.\.venv\Scripts\python.exe enginectl.py dispatch-container-host
```

Tickets are canonical, self-hashed, bound to the exact budget and profile and
never overwritten in place. Even an authorised dry-run ticket still records
that human release is required and has no scientific or promotion standing.

## Container commissioning run

The adapter does not accept an arbitrary script, tag such as `python:latest`,
or an `sh -c` string. A human must prepare a hash-bound
`CONTAINER_DISPATCH_REQUEST` whose `image_ref`, `argv`, `budget_sha256`,
`ticket_sha256`, and empty declared `output_path` are all exact. The
command-manifest hash is canonical JSON for:

```json
{"argv":["python","-c","print('example')"],"image_ref":"registry/example@sha256:<64 lowercase hex characters>"}
```

That hash must already appear in the budget's
`allowed_tool_manifest_sha256`; the budget must permit exactly
`LOCAL_SUBPROCESS`, `DECLARED_INPUT_FILES`, and `DECLARED_OUTPUT_FILES`, with
`DENY_ALL` networking, zero GPU seconds, zero external-service spend, and one
bounded shift. The image must already exist in the local Docker image store;
the adapter passes `--pull never` and will not fetch it.

After generating and independently inspecting the budget, ticket and request,
the human with the release capability can run:

```powershell
.\.venv\Scripts\python.exe -m dispatch.run_container_adapter run `
  --budget state\container-budget.json `
  --ticket state\container-ticket.json `
  --request state\container-request.json `
  --stop-file state\container-stop.request `
  --receipt state\container-receipt.json
```

After checking the non-secret artifacts and host, the command prompts the human
once for the release capability without echoing it. Creating the stop file
while the process is running triggers a human stop. A
receipt and preserved output can be rechecked without trusting the runner:

```powershell
.\.venv\Scripts\python.exe -m dispatch.run_container_adapter verify `
  --budget state\container-budget.json `
  --ticket state\container-ticket.json `
  --request state\container-request.json `
  --receipt state\container-receipt.json
```

Do not put release capabilities into a repository, workflow, prompt log or
agent-accessible environment. The adapter compares the capability in memory to
its budget hash and never writes it to the receipt.

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
no-overwrite behaviour, the engine front door and the complete drill. It also
checks the container command plan and rejects manifest, network, path and
spend expansion. A local end-to-end commissioning test uses a preloaded
digest-pinned Python image only when explicitly enabled:

```powershell
$env:FACTORY_CONTAINER_E2E = '1'
.\.venv\Scripts\python.exe -m unittest `
  dispatch.tests.test_container_adapter.ContainerAdapterTests.test_digest_pinned_container_commissioning_run -v
```

That local test is engineering evidence for this adapter. It is not a research
run, external host attestation, independent reproduction, or scientific proof.
