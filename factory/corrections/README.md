# Append-only artifact corrections

This directory defines the universal public correction and retraction record.
It changes an artifact's **derived standing** without changing or deleting the
artifact bytes that people previously saw.

The correction ledger is deliberately separate from the frozen Pilot Round 1
control-plane software lock. It can target a control-plane event, shift report,
portable package, station contract, contribution record, rights record, quality
assessment, another correction record or any other public artifact by immutable
ID and SHA-256. It cannot contain hidden inputs, credentials or private evidence.

## Standing transitions

| Action | Required result | Replacement |
| --- | --- | --- |
| `CORRIGENDUM` | `CURRENT_WITH_CORRECTION` | Required |
| `RIGHTS_CORRECTION` | `CURRENT_WITH_CORRECTION` | Required |
| `SUPERSESSION` | `SUPERSEDED` | Required |
| `INVALIDATION` | `INVALIDATED` | Forbidden |
| `RETRACTION` | `RETRACTED` | Forbidden |

`SUPERSEDED`, `INVALIDATED` and `RETRACTED` are terminal in v1. Restoring one
would require a future governance migration; it cannot be smuggled in as another
record. Multiple corrigenda may accumulate before a terminal action, and the
history command reports both the standing recorded at each step and the current
standing derived from the complete chain.

Every record includes:

- the exact original artifact ID, class, locator, media type and SHA-256;
- the accountable identity record and its assurance limitation;
- the asserted authority basis, scope, conflict declaration and evidence hashes;
- a typed reason and public evidence references;
- the before and after standing;
- the previous record hash and its own canonical self-hash; and
- fixed construction-only flags denying scientific evidence, reproduction credit
  and promotion eligibility.

Schema validity records an assertion of authority. It does not prove that the
actor is the rights holder, author, independent reviewer or legally entitled to
act. A disputed authority assertion must itself receive a later correction or
enter the governance dispute route.

## Engine commands

Prepare a draft shaped like [`correction-draft.example.json`](correction-draft.example.json),
then append it from the `factory` directory:

```powershell
.\.venv\Scripts\python.exe enginectl.py correction-append `
  --ledger state\public\corrections.jsonl `
  --draft corrections\correction-draft.example.json

.\.venv\Scripts\python.exe enginectl.py correction-verify `
  --ledger state\public\corrections.jsonl

.\.venv\Scripts\python.exe enginectl.py correction-history `
  --ledger state\public\corrections.jsonl `
  --standing RETRACTED

.\.venv\Scripts\python.exe enginectl.py correction-export `
  --ledger state\public\corrections.jsonl `
  --output state\public\correction-index.json
```

`correction-export` refuses to overwrite an existing index. The Hangar can read
an exported projection, but it cannot alter the engine ledger or become the
source of truth.

## Synthetic commissioning

Run the known-answer false-statement drill into a fresh ignored directory:

```powershell
.\.venv\Scripts\python.exe -m corrections.run_synthetic_drill `
  --output state\correction-synthetic-001

.\.venv\Scripts\python.exe -m corrections.verify_synthetic_drill `
  state\correction-synthetic-001
```

The drill appends a corrigendum and then a retraction, proves that the original
bytes remain, exports the derived current standing and detects tampering. It is
one local operator working with visible fixtures and has no scientific standing.

## Verify the implementation

```powershell
.\.venv\Scripts\python.exe -m unittest discover `
  -s corrections\tests -p "test_*.py" -v
```

The tests cover duplicate JSON keys, private locators, action/standing mismatch,
artifact identity rebinding, changed bytes, terminal-state restoration,
no-overwrite export and the complete engine CLI path.
