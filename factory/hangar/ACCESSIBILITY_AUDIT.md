# Contributor-route accessibility audit

- Audit date: 2026-08-06
- Audit scope: `HANGAR_CONSTRUCTION`
- Source revision: `37ff0dd2efbffec31c31a651f02f6bd000e93263`
- Routes: `/contribute`, `/workbenches`, `/operations`

This is a construction audit. It contains no scientific evidence, creates no
independent reproduction credit and cannot promote a workbench result.

## Environment and method

- Windows 10, local Vinext development server, Node.js 24.15.0.
- Codex in-app Chromium, user agent `Chrome/151.0.0.0`.
- Default viewport: 1280 x 720 CSS pixels at device-pixel ratio 1.
- Reflow proxy for 200% zoom from the default width: 640 x 720 CSS pixels.
- Narrow-screen viewport: 390 x 844 CSS pixels.
- The semantic tree, DOM order, accessible names, computed focus styles,
  heading levels, landmarks, viewport dimensions and overflow values were read
  from the rendered routes. Screenshots were inspected at the narrow viewport.
- No form was submitted, no Hangar state was changed and no UI source was
  changed by the audit.

The browser-control surface did not expose a browser-zoom command or a reduced-
motion emulation switch. The 640-pixel check is therefore a reflow proxy, not a
claim that native 200% browser zoom was directly exercised. The active browser
profile reported `prefers-reduced-motion: reduce` as false. The reduced-motion
stylesheet was inspected separately, as recorded below.

## Summary

| Check | `/contribute` | `/workbenches` | `/operations` |
| --- | --- | --- | --- |
| DOM focus order follows reading order | Pass, with shared-shell bypass defect | Pass, with shared-shell bypass defect | Pass, with shared-shell bypass defect |
| Visible focus | Pass for links | **Fail for the three directory filters** | Pass for form controls and buttons |
| Heading structure | Pass | Pass | Pass |
| Landmarks | Pass | Pass | Pass |
| Link/control names | Pass | **Fail for 100 repeated station-link names** | Pass |
| 640-pixel reflow proxy | Pass | Pass | Pass |
| 390-pixel reading order | Pass with observation | Pass with observation | Pass with observation |
| Reduced-motion handling | Pass by source inspection; runtime emulation not available | Same | Same |

Three defects were confirmed and filed separately as
[#22](https://github.com/Martin123132/research-factory/issues/22),
[#23](https://github.com/Martin123132/research-factory/issues/23) and
[#24](https://github.com/Martin123132/research-factory/issues/24).

## Reproduction steps and observations

### Shared shell and keyboard order

1. Open any audited route at the default viewport.
2. Inspect the semantic tree and enumerate enabled elements matching links,
   buttons, inputs, selects, textareas or an explicit `tabindex` in DOM order.
3. Move focus through the header and into the route controls.

The first nine controls are identical on every route: the Hangar home link,
then Stations, Shift board, Runners, History, System, Standards, Tutorial and
Contribute. Their order matches the visual header order. The route content also
follows its visual reading order, and no positive `tabindex` was present.

There is no skip link or equivalent mechanism before this repeated block. This
is tracked in [#23](https://github.com/Martin123132/research-factory/issues/23).

### `/contribute`

1. Open `/contribute`.
2. Read the heading outline and landmarks.
3. Enumerate links after the shared header and inspect their accessible names.
4. Focus representative header and content links and inspect the visible focus
   state.

Observed:

- one `h1`, eight section-level `h2` headings and four licence-card `h3`
  headings; levels do not skip;
- `header`, labelled primary `nav`, `main`, `aside` and `footer` landmarks;
- five route-content links, all with destination-specific names;
- the focused home link matched `:focus-visible` and retained a user-agent
  outline; header navigation also receives the orange underline treatment;
- no hidden or disabled route-content control interrupted the order.

### `/workbenches`

1. Open `/workbenches` with all domains and lanes shown.
2. Inspect the first route controls and count the station links.
3. Focus Search stations, Domain and Evidence lane.
4. Inspect each focused control's outline, border and box shadow.
5. Compare the accessible names of links to `/workbenches/1` through
   `/workbenches/100`.

Observed:

- 112 enabled controls: nine shared-header links, three labelled filters and
  100 station links;
- the route controls occur in the expected order: Search stations, Domain,
  Evidence lane, then WB-001 through WB-100;
- one `h1` followed by 100 card `h2` headings;
- `header`, labelled primary `nav`, `main` and `footer` landmarks;
- Search stations matched `:focus-visible`, but computed styles were
  `outline: none`, `border: 0` and `box-shadow: none`. The same CSS rule covers
  both selects. This defect is tracked in
  [#22](https://github.com/Martin123132/research-factory/issues/22);
- all 100 station destinations exposed the identical accessible name
  `Open station brief →`. This defect is tracked in
  [#24](https://github.com/Martin123132/research-factory/issues/24).

### `/operations`

1. Open `/operations` in the local preview.
2. Inspect labels, heading order, landmarks and enabled-control order.
3. Focus the Station select and inspect its computed focus treatment.
4. Continue through operating mode, title, brief, Create open order and
   Refresh without submitting the form.

Observed:

- every input, select and textarea has a visible label;
- route order is Station, Operating mode, Order title, Construction brief,
  Create open order, then Refresh and the controls belonging to each listed
  order;
- one `h1`, two `h2` headings and five order-card `h3` headings;
- `header`, labelled primary `nav`, `main`, two `aside` regions and `footer`;
- the focused Station select matched `:focus-visible` and showed a one-pixel
  orange border plus a two-pixel orange focus shadow;
- buttons that were unavailable in the current state were natively disabled
  and therefore skipped by keyboard navigation.

## Reflow, zoom proxy and narrow-screen reading order

At 640 x 720 CSS pixels, all three routes had a 625-pixel document client width
and scroll width. The primary navigation had a 577-pixel client width and
scroll width. No document or navigation horizontal overflow was present.

At 390 x 844 CSS pixels, all three routes had a 375-pixel document client width
and scroll width. Content changed to one-column layouts without reordering:

- `/contribute` retained Choose, Build, Check and Hand off before the call to
  action and licence sections;
- `/workbenches` retained the three filters before sequential station cards;
- `/operations` retained the work-order form before the operational orders.

The shared primary navigation becomes an independently horizontally scrollable
single row at 390 pixels. All links remain in DOM order and the document itself
does not overflow. This is recorded as an observation, not a confirmed defect;
it should be included in any later mobile usability test.

## Reduced motion

The rendered profile reported that reduced motion was not requested. Source
inspection found only short CSS transitions in the audited interface and the
following global reduced-motion behavior:

```css
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
  *, *::before, *::after { transition: none !important; }
}
```

No keyframe animation was found in the audited route source. This supports the
expected reduced-motion result, but should not be represented as a dynamic
emulation run; a future browser harness with media-feature emulation should add
that regression check.

## Follow-up boundary

This audit deliberately does not alter the UI. Confirmed defects are isolated
in their own construction issues:

- [#22 — Restore visible focus on station-directory filters](https://github.com/Martin123132/research-factory/issues/22)
- [#23 — Add a skip link past the repeated Hangar navigation](https://github.com/Martin123132/research-factory/issues/23)
- [#24 — Give station-card links unique accessible names](https://github.com/Martin123132/research-factory/issues/24)
