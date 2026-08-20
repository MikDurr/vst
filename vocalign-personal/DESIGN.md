# Design System: vocalign

## 1. Overview

**Creative North Star: "The Plugin Window"**

This is a piece of studio gear that happens to be served over HTTP. It sits
open beside Logic during a mix — not visited, not browsed, opened for ninety
seconds and dismissed. Every decision follows from that: it should be
indistinguishable in feel from the plugin windows it lives next to.

The reference is the VocAlign plugin UI: stacked colour-coded waveform lanes
occupying most of the surface, a narrow fixed control panel on the right, tiny
uppercase labels above hardware-style rotary knobs, near-black ground.

Deliberately **not** a web form with file inputs and range sliders. That was
the first attempt and it was wrong — it read as a webpage pretending to be a
tool. It is also not a dashboard: there are no cards, no stat tiles, no
sections, no navigation. There is one screen and one job.

**Key characteristics**
- Near-black violet-cast ground, so the saturated lane hues sit on a related
  surface instead of fighting a neutral gray
- Three track colours that *identify* rather than decorate — this is why the
  palette is Committed rather than the product-default Restrained
- Rotary knobs, not sliders; the plugin convention, and precise under a
  vertical drag
- Waveforms are the interface: they're also the drop targets and file pickers
- No page-load choreography. It opens ready.

## 2. Colors

**Strategy: Committed.** Normally product UI defaults to Restrained (tinted
neutrals + one accent ≤10%). Here the lane colours carry information — which
take is which — so saturation is functional identification. The accent stays
Restrained on top of that: violet appears only on the primary action and
active states.

All values are OKLCH.

### Track identity — the functional palette
- **Guide** (`oklch(0.88 0.15 98)`, yellow): the reference take. Read-only,
  never modified, never in the output.
- **Dub** (`oklch(0.76 0.13 62)`, orange): a take being moved.
- **Result** (`oklch(0.70 0.16 289)`, violet): aligned output.

The guide→dub→result progression is warm→warm→cool, so "this one is the
product" is legible at a glance without reading a label.

### Surfaces
- **Bg** (`oklch(0.17 0.025 288)`): the window ground.
- **Surface** (`oklch(0.21 0.028 288)`): panels, titlebar, lane headers.
- **Surface Raised** (`oklch(0.25 0.03 288)`): knob bodies, ruler, hovered rows.
- **Surface Sunken** (`oklch(0.13 0.022 288)`): waveform beds, knob wells —
  anything that should read as recessed.
- **Line** (`oklch(0.31 0.03 288)`) / **Line Soft** (`oklch(0.26 0.028 288)`):
  hairlines. Structure is carried by borders, never shadows.

### Ink
- **Ink** (`oklch(0.96 0.005 288)`): primary text, readouts.
- **Ink Dim** (`oklch(0.76 0.015 288)`): lane names.
- **Ink Muted** (`oklch(0.62 0.02 288)`): micro-labels and hints — verified
  ≥4.5:1 on Surface.
- **Ink Faint** (`oklch(0.50 0.02 288)`): decorative and disabled only. **Never
  body copy.**

### Accent & semantic
- **Accent** (`oklch(0.60 0.19 288)`, violet): the Align button, toggle-on,
  focus rings, drag-over highlight. Nothing else.
- **OK** (`oklch(0.75 0.16 162)`): engine-ready.
- **Warn** (`oklch(0.80 0.14 78)`): engine-offline.
- **Danger** (`oklch(0.68 0.19 22)`): errors, on a 12%-alpha bed.

### Named rules

**The Identity Rule.** A track colour always means *which take*, never
"emphasis" or "state." If something needs to look active, that's the accent's
job. A lane never changes colour to indicate status.

**The Faint Floor.** `--ink-faint` is below body-text contrast by design. It
may hold knob edge-labels and disabled values; the moment it holds something a
user must read, it's a bug.

## 3. Typography

**Family:** `ui-sans-serif, -apple-system, "SF Pro Text", system-ui, sans-serif`
**Readout:** `ui-monospace, "SF Mono", "JetBrains Mono", Menlo, monospace`

One family. Product UI doesn't need display pairing, and a plugin window least
of all. The monospace face marks a *value* — knob readouts, timeline ticks,
drift figures — and appears nowhere else.

**Fixed rem scale, not fluid.** Viewed at consistent DPI in a fixed-width
panel; a clamp() heading that shrinks in a sidebar looks worse, not better.

### Hierarchy
- **Micro-label** (600, 11px, 0.07em tracking, uppercase): control names,
  lane names, metric captions.
- **Small** (600, 13px): panel group titles, buttons.
- **Body** (400, 14px): the Align button, titlebar.
- **Readout** (500, 13px mono, tabular-nums): every knob value, tick, metric.
- **Edge** (9px, 0.06em, uppercase, ink-faint): the LOOSE/TIGHT pair flanking
  a knob.

### Named rules

**The Micro-label Convention.** Tiny uppercase tracked labels appear
throughout — above every knob and control. This is the hardware-panel
convention, and it is *not* the section-eyebrow trope the general rules ban:
those labels name **controls**, not sections. There are no sections here.

**The Readout Rule.** If it's a measurement (%, ms, drift, timecode) it's
monospace with tabular figures. If it's prose it isn't. Values must not shift
horizontally while a knob is dragged.

## 4. Elevation

**No shadows anywhere.** Depth is carried entirely by surface value and
hairlines, the way a hardware panel does. Sunken wells recede, raised knob
bodies advance, borders separate.

The only box-shadow in the system is functional, not decorative: an inset 2px
accent ring on a lane while a file is dragged over it.

**Named rule — The Flat Panel Rule.** If a drop shadow appears, something has
been styled like a web card. Rewrite it with surface value instead.

## 5. Components

### Waveform lane (`WaveLane.svelte`) — the signature component
A canvas-rendered peak waveform on a sunken bed, with a colour dot, a name,
and an optional header action. Also the file input: click to browse, drop to
load, with an accent ring while dragging.

- Peaks computed **client-side** from decoded audio, so a take paints
  instantly instead of round-tripping to the server for a picture.
- **Canvas colours must be resolved before use.** `ctx.fillStyle =
  'var(--guide)'` is silently ignored and leaves the fill at default black —
  invisible here. `resolveColor()` exists for exactly this and shipping a
  regression around it is a real bug that has already happened once.
- States: empty (instructional copy), loading (shimmer), loaded, drag-over.

### Rotary knob (`Knob.svelte`)
270° sweep from 8 to 4 o'clock, filled arc in the owning group's track colour,
value readout beneath flanked by edge labels.

- **Vertical drag**, not rotational — far more precise on a 64px circle, and
  the plugin convention.
- Wraps a real `<input type="range">`: keyboard, screen-reader and form
  semantics all work; the SVG is presentation layered on top.
- Disabled knobs desaturate to `--ink-faint` and keep their value visible.

### Toggle (`Toggle.svelte`)
`role="switch"`. Off = sunken well, on = accent fill. One per control group,
in the group header, gating the controls beneath it.

### Segmented (`Segmented.svelte`)
Used instead of a `<select>` where there are only two or three options.
Showing the choices beats hiding them behind a menu in a control panel.

### Buttons
- **Primary** (`.go`): accent fill, full panel width, one per screen. Carries
  an inline spinner and a live count while running.
- **Secondary** (`.dl`): hairline border, transparent fill.
- **Icon** (`.x`): faint until hover. Remove-a-take only.
- Focus-visible is a 2px accent outline, offset 2px. Never removed.

### Layout
- Two columns: lanes take remaining width, panel is a fixed **268px**.
- The panel is `position: sticky` and scrolls internally — the lane stack
  grows with every dub added, and the controls must stay reachable.
- **Responsive behaviour is structural.** Under 860px the panel drops beneath
  the lanes and un-sticks. Type never scales.

## 6. Motion

150–250 ms, `cubic-bezier(0.22, 1, 0.36, 1)` (ease-out-quart). Motion conveys
state only: toggle travel, drag-over ring, hover fills, the running spinner,
the loading shimmer.

**No page-load choreography, no reveal animations, no staggered entrances.**
The user is mid-task in a DAW; they don't want to watch it arrive.

Every animation has a `prefers-reduced-motion` alternative — the shimmer
becomes a flat fill, the spinner stops.

**Named rule — The State-Only Rule.** If an animation isn't reporting a state
change, it shouldn't exist.

## 7. Copy

Engineer-to-engineer. Practical, specific, never encouraging.

- Say what a control does in its own terms: *"0 = leave the dub where it is · 1
  = snap hard to the guide."*
- Volunteer real advice where a default is non-obvious: the Pitch target hint
  says 50% is the sweet spot, and that switching it off can suit a wide stack —
  because that's what someone who'd used it would tell you.
- Errors say what to do: engine-down names the command that starts it.
- Empty states teach the interface: *"Drop the take(s) to be aligned — several
  at once is fine."*

## 8. Bans

On top of the shared absolute bans:

- **Cards.** There is one screen; nothing needs boxing. Result rows are the
  single exception and use surface value, not elevation.
- **Shadows.** See §4.
- **Light mode.** Not a preference — the tool sits beside a dark DAW in a dim
  room, and a bright surface there reads as "webpage."
- **CSS variables passed into canvas.** See §5.
- **Fluid type.** Fixed rem scale only.
- **Global progress for per-item work.** Takes render sequentially; each
  reports its own state.
