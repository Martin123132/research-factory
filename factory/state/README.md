# Local factory state

`factoryctl` places the live JSONL ledger, lock file, private content-addressed
evidence, metric-free public candidate packages, entry-run outputs, and
evaluator-side sealed rerun conclusions here. Those files are ignored because
the tree contains unrevealed results and operator data. Rerunners receive only
packages under `public/artifacts`, never the private evidence store.

Back up the ledger and private state together. Periodically run `factoryctl
checkpoint` and anchor that checkpoint in a separate signed or versioned
location. Never place evaluator private keys or the sealed holdout in this
directory.
