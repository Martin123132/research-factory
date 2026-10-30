# An engine-only construction shift

Choose a reviewed fixture, clock in, optionally run it, clock out, export a
handover and resume it under another local operator label. No hosted Hangar,
Node.js, GitHub API, model provider or paid subscription is needed. Installation
of Python dependencies needs package access or a local cache; the shift commands
themselves do not call online services.

This first version offers **WB-001 compression and WB-013 TSP fixtures only**.
It is a construction rehearsal, not breakthrough search or an arbitrary agent
executor. It creates no exclusive task claim and changes no governed work order,
research round, validator assignment or Hangar database.

## First shift (Windows)

From the repository root, use the patched successor fixture environment described in
[`../environments/README.md`](../environments/README.md). The maintenance
environment can inspect/report/package, but cannot execute the research fixtures.
Nothing silently installs packages or switches interpreters.

```powershell
$shiftPython = 'factory/state/environments/pilot-002/.venv/Scripts/python.exe'
& $shiftPython factory/enginectl.py shift tasks
& $shiftPython factory/enginectl.py shift start --workbench WB-013 --operator demo:alice --output factory/state/alice-shift-001
& $shiftPython factory/enginectl.py shift inspect --session factory/state/alice-shift-001
& $shiftPython factory/enginectl.py shift run --session factory/state/alice-shift-001 --acknowledge-fixture-only
& $shiftPython factory/enginectl.py shift finish --session factory/state/alice-shift-001 --outcome PROGRESS --summary 'The fixed TSP fixture completed its build, verify and rehearsal.' --next-lead 'Repeat the journey on another clean checkout.'
& $shiftPython factory/enginectl.py shift export --session factory/state/alice-shift-001 --output factory/state/alice-handover-001
```

`start` records the adapter/contract commitments and environment check without
executing anything. `run` executes the existing fixed build → verify → rehearse
grammar. Each step retains its 180-second timeout. This is trusted local
fixture execution, **not process isolation or universal dispatch authorisation**.
It does not invoke the separate container runner or permit other agent commands.
Ctrl+C interrupts the run; inspect the retained files and clock out instead of
restarting that directory.

On Linux/macOS, use the same arguments with
`factory/state/environments/pilot-002/.venv/bin/python` in place of `& $shiftPython`.
All actions support `--json`. CI tests Windows and Linux; macOS compatibility is
not claimed as observed verification.

## Honest clock-out, including failures

The four existing outcomes are `PROGRESS`, `NO_GAIN`, `BLOCKED`, `UNRUNNABLE`.
A summary and next lead are required. Blocked/unrunnable work requires a reason:

```powershell
& $shiftPython factory/enginectl.py shift finish --session factory/state/alice-shift-001 --outcome UNRUNNABLE --summary 'The fixture could not start under this interpreter.' --blocker 'The environment does not match the frozen profile.' --next-lead 'Activate the frozen environment and start a new shift.'
```

Use that **instead of** the successful clock-out above. A failed or interrupted
execution cannot be relabelled as a passing shift. `run` returns nonzero for an
unrunnable fixture and retains its bounded error and completed steps. `inspect`
is read-only; an unfinished attempt is `INTERRUPTED_OR_RUNNING`.

An OS-owned lock prevents another cooperating command from closing/exporting a
shift while its runner is active. The OS releases it after a crash. This is not
a distributed lease or a defence against someone editing their own files.
A no-execution shift may record useful inspection or a no-gain outcome; it
explicitly remains `NOT_RUN`. Next leads are proposals, not verified conclusions.

The existing report schema permits intervals up to 24 hours. When filing late,
use `--ended-at 2026-10-21T15:00:00Z` with the **actual recorded finish** within
that interval. Never fabricate a duration. The finish cannot predate recorded
run completion. Times and operator labels are assertions, not attestations.

## Handover and resume

Copy the **whole handover directory** through your chosen channel. Review it
before sharing: packaging is not redaction of private paths, confidential text
or secrets. No command uploads anything. On the recipient's checkout:

```powershell
& $shiftPython factory/enginectl.py shift verify --package factory/state/alice-handover-001
& $shiftPython factory/enginectl.py shift resume --package factory/state/alice-handover-001 --operator demo:bob --output factory/state/bob-shift-001
& $shiftPython factory/enginectl.py shift inspect --session factory/state/bob-shift-001
```

The new operator sees earlier reports and next leads before choosing whether to
run the fixture or do more inspection. Resume creates a fresh directory, copies
the verified package and links the next report to its predecessor. It never
executes imported command strings, retries partial output, or changes old
reports. Changing demo labels **does not prove two distinct humans participated**.

Clock-out reuses `shift-report-v1.schema.json` and its verifier. Its existing
`HANGAR_OPERATIONS_ONLY` boundary names non-scientific operations, not a website
dependency. The local `WO-...` snapshot (`CLAIMED`, revision 0) is an isolated
construction context, not a claim against a real Hangar/governed order.
Clock-out ends only the local shift and never closes a work order.

`close.json` contains the report and an inventory committing to retained
session/fixture artifacts. Reports do not mislabel ignored local files as
repository artifact references: the inventory and portable manifest commit
those bytes instead. Export uses the existing `HANGAR_CONSTRUCTION / SHIFT_REPORT`
package route. `shift verify` checks both the outer package and the contained
shift/history.

The existing portable format preserves files, not empty directories. A failed
fixture's empty folders may be absent from a copied package; its retained files,
error record and report remain committed and are never replaced with a pass.

## Limits and recovery

- Reviewed, registered fixtures only: no caller-supplied candidate, script,
  shell command, dataset or model API.
- One run and immutable clock-out per directory. Resume into a fresh directory;
  failed/no-gain outcomes remain in history.
- Maximum 16 shifts per history, 10,000 entries and 64 MiB. Retain an exhausted
  history and start a separately identified task; do not erase it.
- Tampering, missing/extra files, duplicate keys, links, junctions and hard links
  fail closed. Historical contract/adapter changes cannot silently become
  current work.
- Hashes detect changes relative to retained commitments; they are not signatures
  or proof that an owner has not rewritten their whole local record.
- A fixture crash preserves partial output for an `UNRUNNABLE` clock-out.
  Malformed/partial metadata itself fails closed: preserve it for diagnosis
  rather than editing it into an apparently valid record.
- Use a local filesystem, not a network share with uncertain lock semantics.
- No live intake, independent reproduction, answer reveal or promotion is
  enabled. Frozen pilot files and scientific gates are unchanged.

## Verification

```powershell
& $shiftPython -m unittest discover -s factory/engine/tests -t factory -p test_shifts.py -v
```

Tests exercise both real fixture adapters, copied handovers, chained reports,
all outcomes, interruption, duplicate operations, concurrent writers, tampering
and CLI errors. The CI matrix uses frozen dependencies on Windows and Linux,
without starting a website or calling a model provider.
