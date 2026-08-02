# Corpus boundary

`scripts/build_public_corpus.py` deterministically creates the small public
qualification corpus in `data/public/` and writes `data/public_manifest.json`.
Generated corpus files are ignored by Git; the generator and manifest define
the public dataset.

The public corpus is deliberately synthetic and redistributable. It exercises
repetitive text, structured records, source-like text, numerical arrays, sparse
binary data, mixed blocks, and incompressible bytes.

`holdout_commitment.json` commits to the current sealed corpus without exposing
its files or private manifest. `evaluator_public_key.json` verifies signed job
tokens and verdicts. The matching corpus, manifest, reference results and
signing key live only under the ignored `factory/private/` evaluator tree and
are never mounted into a candidate container. External scale-up can use the
Silesia Corpus under its own published terms and hashes.
