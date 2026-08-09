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
stops, gives the human a stop-file control, and writes receipts only to a
previously empty declared location. A request must explicitly select either a
best-effort temporary-work copy or a durable stdout-artifact channel.

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
`ticket_sha256`, `output_protocol`, and empty declared `output_path` are all exact. The
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

`WORKDIR_COPY_V1` asks the adapter to copy the bounded temporary `/work`
directory after the command exits. That is useful only where the Docker host
preserves that temporary filesystem after exit; it is not durable on every
host. `STDOUT_ARTIFACT_V1` is the portable durable channel. Its exact command
must write exactly one line of the form
`FACTORY_STDOUT_ARTIFACT_V1:<base64 bytes>`. The adapter validates the framing,
decodes at most the budgeted work-output ceiling, writes `stdout-artifact.bin`,
then replaces the raw encoded stdout with a small hash-and-byte-count capture
marker. Any extra stdout text, invalid base64, empty packet or over-limit
artifact fails closed. The selected protocol is part of the allowlisted
command-manifest hash and receipt.

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

## Portable container commissioning drill

The adapter's regular interface expects a prepared budget, ticket and request.
For a new operator or Docker host, the Factory also supplies one fixed,
known-answer commissioning fixture. It has three deliberate stages: prepare an
inspectable package; authorise its one bounded run with the same retained human
capability; then verify the preserved result later without Docker.

The package is a local engineering check only. It does **not** establish that
two distinct people reproduced anything, that a person’s identity is proven,
or that a workbench result has scientific or promotion standing. Docker's
daemon, kernel and host configuration remain trusted computing bases.

The default fixture uses a locally available digest-pinned Python image. It
uses `--pull never`: first obtain the exact image through your ordinary local
Docker workflow, inspect its digest, and never replace the digest in a prepared
package. The fixture itself has no network access and emits the known answer
`container-commissioned` through the hash-bound stdout-artifact protocol. The
adapter writes that packet as a durable local `stdout-artifact.bin`, so the
commissioning check exercises a preserved artifact path even when Docker drops
its temporary filesystem after the container exits.

From `factory/`, prepare a fresh ignored state directory. The prompt hashes the
capability but never saves it:

```powershell
.\.venv\Scripts\python.exe -m dispatch.run_container_commissioning_drill prepare `
  --output state\container-commissioning-001

.\.venv\Scripts\python.exe -m dispatch.verify_container_commissioning_drill `
  state\container-commissioning-001 --prepared
```

Before the next command, inspect `public/budget.json`, `public/ticket.json` and
`public/request.json`. In particular, check the immutable image digest, exact
argument list, zero-cost/no-network limits, declared output path and the
`false` scientific, independent-reproduction and promotion boundary fields.
The prepared ticket expires after 30 minutes; discard the state directory and
prepare a new package if it expires or a run fails. A partial directory is
intentionally never overwritten or reused.

The human holding the same capability can then start exactly that prepared
fixture. A `human-stop.request` file created in the output directory during the
run stops it. The run command prompts again rather than reading a secret back
from the package:

```powershell
.\.venv\Scripts\python.exe -m dispatch.run_container_commissioning_drill run `
  --output state\container-commissioning-001

.\.venv\Scripts\python.exe -m dispatch.verify_container_commissioning_drill `
  state\container-commissioning-001
```

The completed public package contains the original three artifacts, a
hash-bound receipt, a closed commissioning report and `runner-output/`. The
verification command recomputes every binding and the known answer without
starting a container. It therefore permits a later inspector to check the
artifact bytes, while honestly remaining local synthetic commissioning.

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

The portable drill has ordinary no-Docker contract tests and one opt-in local
end-to-end check:

```powershell
$env:FACTORY_CONTAINER_E2E = '1'
.\.venv\Scripts\python.exe -m unittest `
  dispatch.tests.test_container_commissioning.ContainerCommissioningTests.test_prepared_package_runs_and_verifies_on_a_local_docker_host -v
```
