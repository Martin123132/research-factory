# WB-002 four-hour entry pack

`ENTRY_GATE_ONLY — ZERO SCIENTIFIC CREDIT`

This exercise is credential-neutral. Passing means you followed a reproducible
procedure carefully; it does not mean that you improved `enwik9`, reproduced a
scientific claim or earned promotion credit. A valid `NO_GAIN` is acceptable.

## Part A — local known-answer preflight

From the repository root:

```powershell
python factory/workbenches/wb002_large_text_archive_compression/scripts/run_entry_gate.py --fixture --output work/wb002-fixture-result.json
```

The script must report `PASS`, exact restoration and a deterministic archive.
It compares only stable hashes, sizes and accounting fields; wall time and peak
memory remain advisory.

## Part B — official `enwik8` method gate

Budget the remainder of the four-hour shift for acquisition, verification,
execution, evidence packaging and one bounded alternative. Do not deliberately
waste time if the work finishes early.

1. Read the Hutter rules and corpus page linked in `data/corpus_manifest.json`.
2. Acquire `enwik8.zip` from the canonical source and extract `enwik8` yourself.
3. Verify the extracted file before running anything:

```powershell
python factory/workbenches/wb002_large_text_archive_compression/scripts/verify_corpus.py --corpus enwik8 --input C:/path/to/enwik8
```

4. Run the same locked entry candidate:

```powershell
python factory/workbenches/wb002_large_text_archive_compression/scripts/run_entry_gate.py --enwik8 C:/path/to/enwik8 --output work/wb002-enwik8-result.json
```

5. Repeat the run and confirm exact input hash, archive hash and entry-only
   counted bytes. Record all commands and the environment.
6. Run one bounded alternative setting or record why it was not useful.
7. Commit your conclusion and result-package hash before requesting reveal.

## Required evidence

- corpus byte count, published MD5 and SHA-1, plus labelled factory-derived SHA-256;
- candidate source list and content-addressed source package;
- exact commands and environment;
- two entry result JSON files with matching stable evidence;
- a short `PASS`, `NO_GAIN`, `INVALID` or `UNRUNNABLE` conclusion;
- if negative, what region was explored, the decisive boundary and conditions
  for revisiting it.

The runner is a process-control prototype for trusted local code. It is not a
security sandbox and must not execute arbitrary public submissions.
