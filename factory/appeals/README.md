# Conflict-independent procedural appeals

This directory defines the public, append-only appeal decision record. It is
for a disputed scientific procedure, rights/credit record, safety decision or
governance decision after the normal disagreement route has preserved the
evidence.

It is deliberately **not** a new way to decide scientific truth. An appeal
record cannot create scientific evidence, independent reproduction credit,
promotion eligibility or an automatic change to an artifact's standing. A
material correction or quarantine still needs the separate
[`factory/corrections/`](../corrections/README.md) record and its own stated
authority.

## Non-negotiable panel rules

Every final v1 appeal record includes two to five accountable reviewer identity
records. The verifier rejects a record unless:

- each reviewer identity is distinct;
- no reviewer is the requester or named materially involved author, validator
  or reviewer;
- each reviewer has declared `NO_MATERIAL_CONFLICT_DECLARED`;
- each reviewer supplied exactly one finding and a distinct evidence hash; and
- the outcome is unanimous or `RETURN_FOR_DIAGNOSIS`.

A split does not become a majority vote. It is routed to a fresh diagnostic
run. A unanimous procedural uphold requests a **separate** correction or remedy
record; it does not alter standing on its own.

The record's identity warning is intentional: a local or platform identity
record is not proof of a distinct real person, impartiality, authority or legal
entitlement. That remains a live onboarding and governance responsibility.

## Engine commands

From the `factory` directory, prepare a closed draft based on
[`appeal-draft.example.json`](appeal-draft.example.json), then run:

```powershell
.\.venv\Scripts\python.exe enginectl.py appeal-append `
  --ledger state\public\appeals.jsonl `
  --draft appeals\appeal-draft.example.json

.\.venv\Scripts\python.exe enginectl.py appeal-verify `
  --ledger state\public\appeals.jsonl

.\.venv\Scripts\python.exe enginectl.py appeal-history `
  --ledger state\public\appeals.jsonl `
  --outcome RETURN_FOR_DIAGNOSIS

.\.venv\Scripts\python.exe enginectl.py appeal-export `
  --ledger state\public\appeals.jsonl `
  --output state\public\appeal-index.json
```

`appeal-export` refuses to overwrite an existing public projection. The Hangar
may display an export but cannot mutate the ledger or act as its source of
truth.

## Synthetic commissioning

The known-answer drill first attempts to seat a named author on the panel and
proves that the ledger rejects them. It then records a two-reviewer split and
proves that the only permitted outcome is `RETURN_FOR_DIAGNOSIS`.

```powershell
.\.venv\Scripts\python.exe -m appeals.run_synthetic_drill `
  --output state\appeal-synthetic-001

.\.venv\Scripts\python.exe -m appeals.verify_synthetic_drill `
  state\appeal-synthetic-001
```

All identities and conclusions in this drill are explicitly synthetic. It has
zero scientific, validation, promotion or legal standing.

## Verify the implementation

```powershell
.\.venv\Scripts\python.exe -m unittest discover `
  -s appeals\tests -p "test_*.py" -v
```

The tests cover conflict exclusion, duplicate reviewer identities, duplicate
evidence commitments, unanimous mapping, split diagnosis, hash tampering,
no-overwrite export, strict JSON loading, the engine CLI and the complete
synthetic drill.
