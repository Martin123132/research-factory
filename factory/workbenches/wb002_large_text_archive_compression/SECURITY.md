# WB-002 execution boundary

The entry evaluator stages declared source files, caps stdout/stderr, times out
the process tree, bounds archive size and verifies regular output files. It
still runs with the local user's filesystem and network authority.

- Run only code you wrote or reviewed and trust.
- Do not accept arbitrary public candidate code.
- Entry results are not promotion-grade evidence.
- The hidden claimed score and signing material must never enter a candidate
  process.
- Live work requires a digest-pinned, networkless, read-only container inside a
  disposable evaluator host with production identity and signed attestations.
