# Research Factory Hangar — Workflow Tutorial Storyboard

**Format:** 1920×1080 landscape, 30 fps
**Audio:** British-English tutorial voiceover; no music required, restrained mechanical SFX optional
**VO direction:** Calm engineering tutor, conversational and unhurried; confidence comes from precision, not salesmanship
**Style basis:** `DESIGN.md`
**Measured narration:** 154.5 seconds

## Global guardrails

- The entire walkthrough is explicitly synthetic and demonstrates the factory, not scientific research.
- Safety orange directs attention; safe green confirms invariants; warning red marks prohibited states.
- Every screenshot remains readable and receives a slow pan, perspective settle, or crop movement.
- Callout bubbles explain both the action and the reason for the control.
- Primary transition is a 0.5-second horizontal push; topic changes use a restrained focus pull; the evidence boundary uses a color dip to `#171A18`.
- No invented scientific score, result, validator, or claim appears.

## Asset audit

| Asset | Type | Assign to beat | Role |
| --- | --- | --- | --- |
| `capture/screenshots/scroll-000.png` | Homepage screenshot | 1, 8 | Hangar identity, 100-station readiness, opening and closing brand frame |
| `captures/stations/screenshots/scroll-000.png` | Product screenshot | 2 | Searchable station floor and bounded problem cards |
| `captures/station-001/screenshots/scroll-000.png` | Product screenshot | 3 | WB-001 hard gate and measurement contract |
| `captures/operations/screenshots/scroll-000.png` | Product screenshot | 4 | Work-order form, locked lane, state-controlled board |
| `captures/runners/screenshots/scroll-000.png` | Product screenshot | 5 | Runner trust class and promotion-ineligible status |
| `captures/history/screenshots/scroll-000.png` | Product screenshot | 6 | Append-only event history and search surface |
| `captures/architecture/screenshots/scroll-000.png` | Product screenshot | 7 | One-way boundary between commissioning and live science |

All seven primary screenshots are used. The homepage appears in the first and final beats.

## Beat 1 — THE QUESTION (0.00–10.10s)

**VO:** “Imagine a factory for difficult problems… before any answer earns trust.”

**Concept:** The viewer enters the dark hero panel as if stepping onto the hangar floor. The question is not whether an agent can produce text; it is whether the work has a route through measurable gates.

**Visual:** The homepage screenshot fills a tilted machinery plane. A slow push travels from the “100” readiness instrument toward the headline. Two callouts land in sequence: “Answers are cheap” and “Trust needs a process.” A thin orange path draws between the headline and readiness instrument while the live-research bar remains visibly zero.

**Techniques:** CSS 3D screenshot plane, SVG path drawing, per-phrase callout typography.

**Transition:** Focus pull into the station floor.

**Depth:** BG ruled dark grid; MG screenshot plane; FG orange route line, bubble labels, station counter.

## Beat 2 — CHOOSE A BOUNDED PROBLEM (10.10–27.84s)

**VO:** “The hangar begins with one hundred bounded workbenches… not by how exciting a claim sounds.”

**Concept:** The hundred problems are a navigable floor, not a wall of prompts. The camera inspects the filter rail and settles on the first compression card.

**Visual:** The station directory enters from the right. The “100” counter counts up, the nine-domain label stamps in, and an orange cursor path moves from search to domain to evidence lane. The WB-001 card lifts slightly while four compact bubbles cascade: truth condition, benchmark, hard gate, guardrail. A fifth bubble lands: “Measured, not vibes.”

**Techniques:** counter animation, MotionPath-style cursor movement, staggered callout cascade.

**Transition:** Horizontal push following the cursor into WB-001.

**Depth:** BG paper grid; MG full-page screenshot; FG filter highlights, pointer, measurement bubbles.

## Beat 3 — READ THE CONTRACT (27.84–48.88s)

**VO:** “Here we open workbench zero zero one… stays a recorded attempt.”

**Concept:** The workbench is treated like a test specification on a bench. The visual emphasis moves from the name to the hard gate, then breaks the gate into measurable outputs.

**Visual:** The WB-001 screenshot settles from a slight perspective angle. An orange rule frames “What has to be true.” Five metric chips enter from different directions: exact reconstruction, bytes, speed, memory, energy. A dark bubble states “A clever idea still has to pass.” A small failed-route tag moves into a retained-log tray instead of disappearing.

**Techniques:** CSS 3D settle, SVG framing path, kinetic metric chips.

**Transition:** Vertical push down to the shift board.

**Depth:** BG dark WB-001 code; MG screenshot specification; FG metric chips and retained-attempt tray.

## Beat 4 — CONTROL THE WORK (48.88–71.74s)

**VO:** “The shift board is where the factory itself is built and tested… or blocked with a reason.”

**Concept:** A synthetic work order travels through a visible state machine. The viewer sees that progress is a sequence of commands, not an editable status label.

**Visual:** The operations screenshot fills the frame. The form fields illuminate in order—station, synthetic mode, task, done condition—then a human identity tag bolts onto the order. Across the lower third, a state rail draws OPEN → CLAIMED → IN PROGRESS → REVIEW → COMPLETED, with BLOCKED branching downward. A revision counter increments beside each transition. Bubble: “Commands are revision-checked.” Bubble: “Blocked is useful information.”

**Techniques:** SVG state-rail drawing, counter increments, typing effect for the done condition.

**Transition:** Horizontal push into the runner registry.

**Depth:** BG paper grid; MG shift-board screenshot; FG state rail, revision tokens, operator tag.

## Beat 5 — DECLARE THE RUNNER BOUNDARY (71.74–88.94s)

**VO:** “Runner interfaces are registered separately… mark themselves promotion grade.”

**Concept:** The machine is treated as an accountable interface with declared permissions, not an invisible omnipotent agent.

**Visual:** The runner page slides in. A scanning rule moves down the runner card and extracts three labels: trusted code only, metadata only, promotion eligible: no. Three prohibited capability stamps—NO ARBITRARY UPLOAD, NO LIVE DISPATCH, NO SELF-PROMOTION—appear in warning red but remain subordinate to the trust card. Bubble: “The runner declares its boundary.”

**Techniques:** scanning-line reveal, staggered trust labels, restrained stamp animation.

**Transition:** Focus pull into history.

**Depth:** BG enlarged RUNNER label; MG runner screenshot; FG trust summary and prohibited stamps.

## Beat 6 — PRESERVE THE ATTEMPTS (88.94–104.54s)

**VO:** “Every change creates a new append-only history event… without knowing it.”

**Concept:** Events accumulate like a shift log that cannot be rewritten. Failure becomes a map of explored space rather than embarrassment to delete.

**Visual:** History rows cascade upward as sequence numbers count. A green invariant bar locks into place: UPDATE AND DELETE REJECTED. A correction enters as a new row while the earlier row stays visible. Search terms type into the query box: blocked, disagreement, runner. Bubble: “Dead ends are reusable knowledge.”

**Techniques:** row cascade, typing effect, SVG lock bracket.

**Transition:** Color dip to near-black for the boundary statement.

**Depth:** BG ruled paper; MG history screenshot; FG invariant lock and retained correction rows.

## Beat 7 — KEEP SCIENCE SEPARATE (104.54–135.79s)

**VO:** “And here is the most important guardrail… It cannot approve its own science.”

**Concept:** The flow reaches a physical bulkhead. Synthetic commissioning can propose a package, but the scientific lane starts fresh under different authority.

**Visual:** The architecture screenshot enters sharp against near-black. The first three cards illuminate in order: catalogue, construction, synthetic commissioning. At the boundary, an orange package stops against a vertical lock. On the far side, three counters remain at zero: evidence, reproductions, promotion authority. Two independent-person tokens appear above the future lane without names or results. Large bubble: “Synthetic pass ≠ scientific evidence.” Secondary bubble: “Different people. Fresh counts. Separate authority.”

**Techniques:** SVG flow drawing, counter hold at zero, split-plane depth.

**Transition:** Slow focus pull back to the homepage.

**Depth:** BG near-black control plane; MG system-flow screenshot; FG lock, zero counters, independent-person tokens.

## Beat 8 — THE WORKFLOW (135.79–154.50s)

**VO:** “That is the workflow… legible, repeatable, and harder to fake.”

**Concept:** The factory is summarized as six durable verbs. The ending promises disciplined progress rather than instant discovery.

**Visual:** The homepage readiness instrument returns. Six labels stamp into a ruled checklist: BOUND, GATE, ATTRIBUTE, CONSTRAIN, RETAIN, SEPARATE. The first five connect to the hangar; SEPARATE sits across a small bulkhead. Final statement fills the left: “Make progress repeatable.” The live research lane remains at zero through the final frame.

**Techniques:** checklist path drawing, typographic stamping, slow screenshot pan.

**Transition:** Final-scene fade to `#171A18` only after a two-second hold.

**Depth:** BG homepage hero; MG readiness panel; FG workflow checklist and final statement.

## Production architecture

```text
research-factory-tutorial/
├── index.html
├── DESIGN.md
├── SCRIPT.md
├── STORYBOARD.md
├── narration.txt
├── narration.wav
├── transcript.json
├── capture/
├── captures/
├── compositions/
├── snapshots/
└── renders/
```
