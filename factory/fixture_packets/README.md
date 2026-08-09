# Fixture packet adapter contract

This directory is the Factory control-plane registry for known-safe fixture
packet adapters. Adding a workbench here does not enable live research,
arbitrary candidate execution, independent reproduction or promotion.

## What an adapter permits

Every registered adapter exposes exactly three fixed actions:

- `build` — copies only the hash-locked, checked-in construction inputs into a
  packet;
- `verify` — checks a supplied packet without executing an unknown candidate;
  and
- `rehearse` — runs the named known-safe fixture with a `demo:` identity only.

The engine constructs the command shape itself. Manifests cannot add a shell,
interpreter, command-line token, candidate path or input at invocation time.
The adapter’s runner and every build input are SHA-256 locked. The registry also
locks each adapter file by its exact bytes.

## Add a future adapter

1. Start from [`adapter-template.json`](adapter-template.json).
2. Implement the fixed `build`, `verify` and `rehearse` command interface in a
   reviewed workbench-local script. The script must reject anything outside its
   known-safe fixture.
3. Lock the script and build-input SHA-256 values. Calculate
   `adapter_sha256` from canonical JSON with that field omitted.
4. Run `python factory/enginectl.py packet draft-check --adapter path/to/adapter.json`.
   It validates the schema, self-hash, runner and input locks without executing
   the runner or changing the registry.
5. Put the completed document under `adapters/`, add its exact file SHA-256 to
   `registry.json`, then calculate `registry_sha256` the same way.
6. Add a test that demonstrates the complete build → verify → rehearsal path
   and proves every construction-boundary field remains `false`.
7. Run `python factory/enginectl.py packet list` and the Factory checks before
   review.

This is a controlled source-integration route, not an automatic trust system.
Review of the runner and its fixture remains mandatory: a schema and hash can
prove that declared bytes have not drifted, but cannot prove that newly reviewed
code is harmless or scientifically valid.
