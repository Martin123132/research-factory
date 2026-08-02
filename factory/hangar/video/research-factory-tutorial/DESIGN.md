# Research Factory Hangar — Video Design System

## Overview

The Research Factory Hangar combines an engineering operations manual with a physical factory control room. Layouts are ruled, modular, and strongly left-anchored, with large statements balanced by compact instrument panels. Warm paper surfaces make the interface approachable; near-black machinery panels and safety-orange controls establish authority. The tutorial should feel helpful and methodical, never promotional or futuristic for its own sake.

## Colors

- **Machinery / primary ink:** `#171A18` — dark scenes, headings, structural panels
- **Paper:** `#F2EFE6` — main light canvas
- **Raised panel:** `#FFFDF7` — cards, screenshots, callout surfaces
- **Paper depth:** `#E8E3D7` — inactive states and secondary fills
- **Safety orange:** `#E95C2B` — active steps, cursor path, key callouts
- **Deep orange:** `#A83E1C` — labels and readable orange text on paper
- **Safe-state green:** `#23755B` — verified zero-state and append-only invariants
- **Rule:** `#C9C3B6` — borders and measurement lines
- **Secondary ink:** `#4F544F` — supporting copy
- **Warning red:** `#A6392B` — prohibited or blocked states only

## Typography

- **Statement voice:** Geist variable, 650–900. Headlines at 72–118px with tight tracking around `-0.05em`.
- **Operational voice:** Geist Mono variable, 560–760. Identifiers, states, counters, and callout labels at 20–30px with positive tracking.
- **Body voice:** Geist variable, 350–500. Explanations at 24–34px with generous line height.
- The tension is institutional statement versus machine-readable evidence: Geist speaks to the person; Geist Mono speaks for the record.

## Elevation

Depth comes from one-pixel rules, layered paper panels, cropped screenshot planes, and a restrained `0 18px 45px rgba(31,32,27,0.08)` shadow. Dark scenes use localized radial orange glows rather than full-screen linear gradients. Screenshot planes may use slight perspective and slow pans, but must remain readable.

## Components

- **Safety strip:** full-width orange boundary label; never decorative
- **Hangar instrument:** near-black panel with ruled grid, numerical readout, and status bars
- **Workbench card:** off-white specification panel with code, benchmark, and hard gate
- **Evidence boundary notice:** pale orange warning panel with explicit non-scientific status
- **State rail:** OPEN → CLAIMED → IN PROGRESS → REVIEW → COMPLETED, with BLOCKED branching visibly
- **Trust card:** runner identity and allowed trust class, ending with “promotion eligible: no”
- **Append-only event row:** sequence, event type, actor, revision, and no-scientific-standing label
- **Tutorial bubble:** off-white or dark callout connected to a UI target by an orange rule

## Do's and Don'ts

### Do's

- Keep every statement tied to a visible UI control, state, or invariant.
- Use safety orange to direct attention and safe green only for verified invariants.
- Animate screenshots as large readable planes with slow, deliberate camera movement.
- Preserve the explicit synthetic-versus-scientific boundary throughout.
- Let important frames breathe after the callout lands.

### Don'ts

- Do not imply that a synthetic pass is evidence, reproduction, or a research result.
- Do not use neon cyberpunk effects, rainbow gradients, or decorative data noise.
- Do not invent scientific scores, claims, or validator identities.
- Do not use playful bounce for governance or safety states.
- Do not crowd explanatory bubbles over the UI text they describe.
