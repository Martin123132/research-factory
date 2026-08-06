# Catalogue reference provenance

These dated manifests record whether the Research Factory could retrieve and
identify each workbench's catalogue reference without copying its benchmark
data into Git. They are construction evidence, not scientific evidence and not
a claim that public access grants redistribution rights.

Each ten-station batch records:

- the exact canonical catalogue fields and catalogue-file commitment;
- requested and final HTTPS URLs, redirects, status and retrieval time;
- SHA-256 of exact response-body bytes when verified retrieval succeeds;
- a useful failure record, with no claimed body hash, when retrieval fails;
- the source authority, remaining benchmark ambiguity and upstream terms; and
- explicit confirmation that no dataset or candidate artifact was committed.

TLS certificate verification stays enabled. Do not bypass a certificate error,
HTTP refusal or other failed gate to make a row appear available. A later dated
manifest may document a successful retry while preserving the older result.

Run the complete registered batch verifier from the repository root:

```powershell
python factory/reference_provenance/verify_reference_provenance.py
python -m unittest discover -s factory/reference_provenance/tests -p "test_*.py" -v
```

The verifier binds each configured batch to its exact station range, enforces
the closed schema, rejects duplicate JSON keys and catalogue drift, and checks
retrieval-state consistency. Adding a batch requires registering its path and
expected numeric range in `verify_reference_provenance.py`; an unregistered JSON
file does not extend verified coverage.

A small number of canonical catalogue rows name more than one required source
using the exact `https://… | https://…` notation. Those rows require one ordered
`catalogue-reference` retrieval for every component. If any component fails,
the station's dated reference assessment must remain `retrieval-failed`.
