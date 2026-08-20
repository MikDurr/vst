# Product

## Register

product

## Platform

web

## Users

One person — the developer — mixing their own music. Not multi-user, no
accounts, no sharing, nothing persisted between sessions. The user arrives
with files already in hand and a specific job to do; they are mid-session in a
DAW and this is a detour, not a destination.

The session shape is short and repetitive: load a guide and one or more
doubles, set two or three controls, run, audition, download, go back to Logic.
It may be run several times on the same song with different settings. Nobody
browses this app.

## Product Purpose

Lock doubled vocal takes onto a lead take — timing first, then pitch —
producing a corrected copy of each double that drops straight back into a DAW
session. A personal replacement for VocAlign, built because the commercial
in-DAW route was closed off (Logic on Apple Silicon won't host third-party
ARA) and because the alignment problem is the one piece no already-owned tool
solves.

Explicitly *not* a vocal training or practice tool. That is a separate app
(`vocal-pitch-analyzer`); this one is a production utility and the two were
deliberately split apart.

## Positioning

A studio tool that happens to run in a browser. It should feel like a plugin
sitting beside Logic, not a web app the user visits — dense, dark, controls
that behave like hardware, no marketing surface, no onboarding, no chrome that
isn't doing work.

## Brand Personality

Quiet and instrumental. The interface should disappear into the task; the
waveforms and the controls are the entire product. Confident about defaults
(they were chosen by blind listening, and the UI says so where it matters),
never chatty, never encouraging. Where it does speak — the hint under Pitch
target, the empty-state copy — it speaks like an engineer giving practical
advice, not like software.

## Constraints

- **Runs beside a DAW, in a dim room, at night.** This drives the dark surface
  — a light page next to a dark Logic window reads as "webpage", not "tool".
- **Two servers.** The UI is only an interface; all DSP runs in a local Python
  engine. Engine-down is a real, expected state and must be visible and
  explained, not a silent failure.
- **Long operations.** A render takes seconds to tens of seconds per take, and
  several takes run sequentially. Progress must be legible per-take, not one
  global spinner.
- **Local files only.** No uploads persist, no library, no history. Everything
  is transient and that's intentional.
