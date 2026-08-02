# WB-001 — General-purpose lossless compression

WB-001 asks whether a candidate can reduce stored bytes or resource cost while
reconstructing every input byte exactly. Version 0.2 evaluates candidates
against a fourteen-profile reference frontier rather than one selected
baseline.

## Hard gates

- every restored file must match its original SHA-256 hash;
- every declared corpus file must be processed;
- compressed size and compressed SHA-256 must repeat exactly;
- candidate source, submission, corpus, runtime image and results are hashed;
- timeouts, excessive output, excessive expansion and irregular output files
  fail the run; and
- advisory local timing can never create a promotion claim.

## Reference frontier

The pack contains zlib levels 1/6/9, Zstandard levels 1/3/9/19, Brotli
qualities 1/5/9/11 and XZ presets 0/6/9-extreme. Its dimensions are compressed
bytes, whole-corpus encode time, whole-corpus decode time and peak memory.

The local pack is deliberately marked `LOCAL_QUALIFICATION_ONLY`. Exact sizes
are evidence; timings are exploratory until measured as randomized paired runs
on a pinned promotion machine. For a non-promotion-grade pack, only a new exact
size extreme may pass the hidden gate, and it still awaits promotion-grade
timing and economics.

Build the public pack from the `factory` directory:

```powershell
.\.venv\Scripts\python.exe workbenches/wb001_lossless_compression/scripts/build_reference_pack.py
```

## Candidate contract

Start with `examples/zlib_level9`. A v0.2 candidate implements `metadata`,
`compress-batch` and `decompress-batch`; see `PROTOCOL.md`. The evaluator runs
one process per whole-corpus operation, so interpreter startup is paid once per
round rather than once per file.

The trusted public evaluator is:

```powershell
.\.venv\Scripts\python.exe workbenches/wb001_lossless_compression/runner/evaluate_local.py --submission <submission.json> --operator-id <operator-id> --output <result.json>
```

Do not run unknown submissions with that command.

## Isolated evaluator

`isolation/Dockerfile` builds a fixed Python runtime. The generated image lock
pins the resulting image ID, Dockerfile, dependency lock and security policy.
Each operation receives a fresh container with no network, a read-only root,
all Linux capabilities dropped, `no-new-privileges`, the built-in seccomp
profile, a non-root UID and CPU/RAM/PID/log limits. Candidate source and corpus
mounts are read-only; only a narrow temporary work mount is writable.

Build and test it with:

```powershell
.\.venv\Scripts\python.exe workbenches/wb001_lossless_compression/isolation/build_image.py
.\.venv\Scripts\python.exe workbenches/wb001_lossless_compression/scripts/qualify_isolation.py
```

Docker Desktop on WSL2 is a useful prototype containment boundary, but this
workbench does not label it promotion-grade. A public hostile-code service
should put the same container inside a disposable VM on a separate evaluator
host. See `SECURITY.md`.

## Blind holdout

The repository contains only `data/holdout_commitment.json` and the evaluator's
Ed25519 public key. Holdout files, detailed results, the signing key, the hidden
reference pack and the one-use ledger live under the ignored `factory/private/`
tree and are never mounted into candidate containers.

The evaluator issues a signed token bound to one operator, one candidate
artifact and one holdout commitment. After one run, the token is consumed. The
public response reveals only `PASS`, `NO_GAIN`, `INVALID` or `ESCALATE`, plus a
signature and a commitment to the private evidence.

```powershell
.\.venv\Scripts\python.exe workbenches/wb001_lossless_compression/runner/issue_job_token.py --submission <submission.json> --operator-id <authenticated-operator-id> --output <job-token.json>
.\.venv\Scripts\python.exe workbenches/wb001_lossless_compression/runner/blind_evaluate.py --submission <submission.json> --token <job-token.json> --output <attestation.json>
.\.venv\Scripts\python.exe workbenches/wb001_lossless_compression/runner/verify_attestation.py --attestation <attestation.json>
```

## Two other people

The implemented exact gate is correctly named an **independent rerun**: two
other human-owned accounts run the same locked artifact and reproduce its exact
compressed hashes. An independent reimplementation is stronger and belongs in
a separate reproduction lane. Local demo IDs test plumbing only; production
operator IDs must be injected by an authentication service.

Run the unit suite with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s workbenches/wb001_lossless_compression/tests -v
```
