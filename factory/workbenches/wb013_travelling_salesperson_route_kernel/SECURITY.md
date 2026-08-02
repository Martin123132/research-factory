# Security boundary

The entry evaluator launches a token-array command without a shell, stages only
declared regular source files, bounds captured process output and candidate JSON,
checks the input hash after each run, and kills the observed process tree on a
timeout.

It does **not** provide a security sandbox. The local process can access the
operator's network and filesystem with the operator's permissions. Therefore:

- run only source you have inspected and trust;
- never accept arbitrary public uploads through this runner;
- never describe its timing or memory observations as promotion-grade;
- use a disposable, networkless, read-only container before live evaluation;
- require external human identity and evaluator attestation before promotion.
