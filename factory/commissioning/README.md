# Synthetic factory shift

This drill runs the complete local WB-001 workflow without claiming a discovery
or a human reproduction. It exists to test whether the Factory behaves properly
when evidence conflicts.

It creates distinct **synthetic identity records** for an administrator, author,
two initial rerunners and one diagnostic rerunner. Those records exercise the
identity rules, but they do not prove that five different biological humans ran
the work. The generated report therefore fixes `distinct_humans_proven` and
`promotion_eligible` to `false`.

Run it from the `factory` directory:

```powershell
python commissioning/run_synthetic_shift.py `
  --output state/commissioning/wb001-synthetic-dispute-001
```

The destination must not already exist. The runner never overwrites an earlier
shift.

Verify an existing output without opening its sealed rerun store:

```powershell
python commissioning/verify_synthetic_shift.py `
  state/commissioning/wb001-synthetic-dispute-001
```

The route is deliberately awkward:

1. the author passes the entry gate and releases one bounded Work Order
   Envelope v2;
2. the local monitored executor records a non-promotion receipt;
3. the author result is sealed and its metric-free source package is exported;
4. two rerunners commit blind, with a deliberate deterministic split;
5. a third diagnostic rerun agrees with one side but cannot create a majority
   promotion;
6. the attempt enters dispute review, receives a post-blind diagnosis and keeps
   all contrary evidence;
7. the public ledger is audited without opening the sealed stores.

`public/` contains the append-only ledger, blindness audit, checkpoint,
normalized report and metric-free candidate. `private/` contains entry evidence,
measurements and evaluator-side sealed records. Never commit a generated output
directory; the default destination is already ignored.

The commissioning harness is intentionally outside the frozen Pilot Round 1
control-plane software lock. It calls that frozen machinery and records its own
source and schema hashes in the report. Changing the harness cannot silently
change the round's scientific acceptance contract.
