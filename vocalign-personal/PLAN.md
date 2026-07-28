# Personal VocAlign — Implementation Plan

A personal-use vocal alignment tool for Logic Pro 12.3 on Apple Silicon.
Two pages: **Match Timing** (align dub takes to a guide) and **Match Pitch**
(apply the guide's pitch contour to the dub). Automatic, with strength controls
— no per-note manual editing.

Target: `mikaild` only. No distribution, no installer, no Windows, no VST3/AAX,
no copy protection.

---

## 0. Hard constraints (established, not assumed)

| Constraint | Consequence |
|---|---|
| Logic Pro loads **Audio Units only**, never VST | Ship an AUv2 `.component`. JUCE builds this from the same source as everything else, so this costs nothing. |
| A normal AU sees only a streaming block and cannot look ahead | Time alignment is **impossible** in a plain AU. Must be **ARA 2**. |
| ARA SDK is Apache 2.0, JUCE 7+ has ARA in mainline | No licence fee, no application to Celemony, no fork needed. |
| Flex Pitch has no public API; Scripter is MIDI-only | **Do not attempt Flex Pitch integration.** The plugin owns the pitch move. |
| Logic historically hosted ARA only under Rosetta on Apple Silicon | The single blocking unknown. Phase 0 resolves it. |
| Machine: arm64, macOS 26.5.2, Logic Pro 12.3 | Build arm64-only. Rosetta is not a viable long-term fallback. |

### The ARA question

Every public source stating "ARA needs Rosetta in Logic" dates from the Logic
10.x / 11 era. Logic 12.3 is much newer. Direct inspection of the installed app:

```
/Applications/Logic Pro.app/Contents/Frameworks/MAAudioEngine.framework
  → arm64 slice contains ARA host code
  → assertion string referencing ARA::kARADocumentControllerInterfaceMinSize
```

ARA host code is compiled into the **native arm64 slice**. That is strong
evidence Apple now hosts ARA natively, but presence of code is not proof it is
reachable. Phase 0 settles it empirically before any real work happens.

### Phase 0 result (resolved 2026-07-25): ARA does NOT bind natively

Built a minimal ARA-tagged AU plugin (JUCE 8.0.9 + ARA SDK 2.2.0), installed
it, and tested directly in Logic Pro 12.3 running native arm64 (confirmed via
`vmmap` on the running process: `Code Type: ARM64`, no Rosetta).

- `auval -v aufx Arsp Mkdd` — **passes**.
- Logic's plugin menu correctly lists both **"ARA Spike"** (plain) and
  **"ARA Spike (ARA)"** — it reads the AU's `ARA` tag from `Info.plist` fine.
- Inserting on a compressed/MP3 region produces Logic's own dialog: *"Region
  cannot be processed by ARA. Apple Loops, compressed audio files, and
  reversed regions cannot be processed, nor can regions on a track with Flex
  active."* — proof Logic's **UI layer** is ARA-aware.
- With that eliminated (bounced to clean 16-bit PCM WAV, Flex off, two fresh
  tracks, both audio sources present, explicit "(ARA)" insert, host relaunched
  to force a clean AU rescan) — the plugin still reported
  **`Bound to ARA: no (plain AU insert)`**.
- Added process-wide counters incremented directly inside `createARAFactory()`,
  the `ARADocumentControllerSpecialisation` constructor, and the
  `ARAPlaybackRenderer` constructor — i.e. instrumentation that doesn't depend
  on any of our own lookup logic being correct. Result after all of the above:
  **`createARAFactory() calls: 0`**.

> **Evidence caveat (added on later review — the original write-up overstated
> this).** `Bound to ARA: no` is *conclusive* for the instances tested: that
> flag reads the instance's own `PlugInExtension`, in the same process as the
> editor displaying it. The `createARAFactory() calls: 0` counter is weaker
> than it first appears — Logic may query a plugin's ARA factory from a
> separate scanning process, in which case a zero in the editor's process
> wouldn't prove the factory was never called anywhere. The conclusion below
> still stands, but it rests on the binding check plus external corroboration,
> not on the factory counter alone.

**Conclusion: on this machine (macOS 26.5.2, Logic Pro 12.3, native arm64),
Logic's ARA-aware dialogs are cosmetic — it reads the `Info.plist` tag to
decide what to *say*, but the plugin instance never actually gets ARA-bound.**
This matches the long-standing "ARA needs Rosetta on Apple Silicon"
limitation, independently documented by **both Celemony (Melodyne) and Synchro
Arts (VocAlign/RePitch)** — two commercial vendors with far more resources
than this project, hitting the identical wall. That corroboration is what
makes the conclusion safe despite the caveat above. Rosetta remains off the
table per the existing decision in this plan (§8) — Apple is winding it down,
and running the whole DAW emulated for one plugin is a dead end.

**→ ARA plugin form abandoned.** Phases 1 (Python prototype), 2 (renderer
selection), and 4 (UI) are entirely unaffected — only the ARA plugin shell is
discarded, replaced by the capture-mode design in §5.

---

## 1. Architecture

```
┌─────────────────────────── Logic Pro 12.3 ────────────────────────────┐
│                                                                       │
│  Guide track ──[ Align AU (ARA) ]──┐                                  │
│  Dub 1 track ──[ Align AU (ARA) ]──┤   one shared ARA document        │
│  Dub 2 track ──[ Align AU (ARA) ]──┘   → plugin sees all lanes        │
└───────────────────────────────┬───────────────────────────────────────┘
                                │
                ┌───────────────▼────────────────┐
                │   ARADocumentController        │
                │   • audio source registry      │
                │   • guide/dub role assignment  │
                │   • archive (saves with song)  │
                └───────────────┬────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
┌───────▼────────┐   ┌──────────▼─────────┐   ┌─────────▼──────────┐
│ Analysis       │   │ Warp solver        │   │ Playback renderer  │
│ (worker thread)│   │ (worker thread)    │   │ (audio thread)     │
│ • log-mel      │──▶│ • banded DTW       │──▶│ • reads precomputed│
│ • f0 (YIN)     │   │ • time map f(t)    │   │   buffer, lock-free│
│ • epochs       │   │ • pitch delta ¢(t) │   │                    │
│ • phrase segs  │   │ • TD-PSOLA render  │   │                    │
└────────────────┘   └────────────────────┘   └────────────────────┘
                                │
                ┌───────────────▼────────────────┐
                │  WKWebView UI (Svelte)         │
                │  page 1: Match Timing          │
                │  page 2: Match Pitch           │
                └────────────────────────────────┘
```

**Key design decision: render offline, not streaming.** After analysis, the
plugin computes the *entire* processed dub into a buffer and the audio thread
just reads from it. A 4-minute stereo track at 48k is ~90 MB float — trivially
affordable for personal use, and it removes the hardest class of bug (real-time
PSOLA under a deadline). This is the single biggest complexity saving available
and it is only available because this isn't a commercial product.

### One engine for both pages

Match Timing and Match Pitch are **the same operation**. TD-PSOLA repositions
glottal pulses; moving them in time is time-stretching, changing their spacing
is pitch-shifting, and it preserves formants for free in both cases. Build one
epoch-synchronous overlap-add engine that takes a time map *and* a pitch map.
Page 1 passes an identity pitch map, page 2 passes a real one. Do not build two
engines.

---

## 2. Phase 0 — ARA viability spike

**Goal: prove Logic 12.3 native arm64 loads a third-party ARA plugin.**
Nothing else in this plan matters until this is answered. Timebox: half a day.
If it fails, stop and go to §8 (fallback).

1. `git clone --recursive` JUCE 8 and `Celemony/ARA_SDK`.
2. CMake project, `juce_add_plugin(... IS_ARA_EFFECT TRUE FORMATS AU Standalone)`.
   Minimal `ARADocumentControllerSpecialisation` that does nothing but log.
   Editor that renders one label: the number of audio sources it can see.
3. Ad-hoc codesign post-build (`codesign --force --sign - --timestamp=none`),
   install to `~/Library/Audio/Plug-Ins/Components/`.
4. `auval -v aufx <SUBT> <MANU>` — must pass.
5. Launch Logic 12.3 **natively** (confirm "Open using Rosetta" is unchecked).
   Insert on slot 1 of an audio track with a region.

**Success criteria, in order:**
- [ ] Logic's plugin manager lists it and validation passes
- [ ] Inserting it in slot 1 offers/engages ARA mode
- [ ] `didAddAudioSource` fires — the plugin receives the region's audio
- [ ] Inserting on a **second** track surfaces **both** sources in one document
- [ ] Reversing playback of the audio proves the render path works
- [ ] Roles + a dummy parameter survive save/reopen of the Logic project

The fourth item is the one that could quietly fail and would be expensive to
discover in month two — multi-track visibility is the entire premise of a
guide/dub tool. Test it in the spike, not later.

---

## 2.5 R2 spike — do AU instances share process memory in Logic?

**Promoted out of Phase 3 on review.** This was originally buried as a
sub-bullet of the capture-mode design, to be checked "before designing
further." That placement contradicted this plan's own operating principle:
*de-risk the form before spending on it.* It is a half-day binary question
whose answer invalidates the entire capture-mode architecture if negative, so
it belongs alongside Phase 0, not after a C++ port.

**The question**: when two instances of the same AU are inserted on two tracks
in one Logic project, do they share process-wide state (statics/singletons)?

**Why it's genuinely uncertain**: Logic hosts AUs *out of process* — that is
part of why ARA failed in Phase 0. If each instance gets its own host process,
a shared `std::map<String, GuideBuffer>` singleton is simply invisible across
instances and the guide/dub pairing model in §5 collapses.

**The test** (reuse `plugin/spike/`, it already builds and installs cleanly):
1. Add a process-wide `static std::atomic<int>` incremented once per
   constructed instance, plus a static holding a random per-process ID.
2. Display both in the editor.
3. Insert on two tracks. Read both editors.
   - Same process ID + count of 2 → **shared**, capture-mode design works as written.
   - Different process IDs + count of 1 each → **isolated**, need real IPC
     (shared memory / XPC / a file-backed handoff) or a different pairing model.

**If isolated**: not automatically fatal, but it materially raises Phase 3's
cost, and combined with a negative 2a result would make the standalone path
(§8) clearly correct.

---

## 3. Phase 1 — Python algorithm prototype

Tune the algorithm **by ear, offline, in Python**, before writing a line of DSP
C++. Two wav files in, one wav out. This is where the quality is actually
decided, and iterating here is ~20× faster than iterating in a plugin.

Reuses from the existing repo:
- `vpa/pitch.py` — `extract_pitch` / `PitchCurve` (pYIN, hop 256). Already the
  right shape; needs a 48 kHz path and a confidence threshold.
- `vpa/analysis.py` — silence and note-change segmentation, vibrato-aware
  debouncing. Becomes phrase segmentation for anchored DTW.
- `vpa/audio.py` — loading, ffmpeg conversion.
- `vpa/compare.py` — existing guide/take comparison logic.

New: `vpa/align.py` (DTW time-map), `vpa/matchpitch.py` (pitch-ratio math),
`vpa/praatrender.py` (rendering — see §1b for why this replaced a from-scratch
`vpa/psola.py`, since deleted), `vpa/vocalign.py` (ties them together), plus a
CLI `vpa align guide.wav dub.wav -o out.wav --tightness --max-shift
--pitch-strength`. No separate A/B harness was built — real listening via
`SendUserFile` round-trips with the actual user turned out to be the harness.

### 1a. Alignment solver (`vpa/align.py`)

- **Features**: 40-band log-mel, 1024 window / 256 hop (~5.3 ms at 48 k),
  per-frame mean-variance normalised so level differences don't drive the path.
  Append a delta-energy band — onsets are what the ear actually judges.
- **Cost**: cosine distance between guide and dub feature frames.
- **DTW**: Sakoe-Chiba band = the **Maximum Shift** control (±200 ms → ±38
  frames). Itakura slope constraint capped at 2:1 so no syllable gets absurdly
  stretched. Open-ended at both ends (the dub may start late).
- **Phrase anchoring**: segment both tracks at silences first (existing
  `analysis.py` logic), match phrases, then DTW *within* each phrase pair. This
  is what makes it robust — it stops one bad phrase from corrupting the whole
  path, and it's how VocAlign's "Synch Points" behave.
- **Path → time map**: median filter, then smooth to a monotone `t_dub = f(t_guide)`.
- **Controls**:
  - *Tightness / Max Difference* → clamp `|f(t) − t| ≤ D` ms, then blend
    `f_final = (1−α)·identity + α·f_dtw`.
  - *Alignment Rule / flexibility* → smoothing kernel width + slope penalty weight.

### 1b. Renderer — superseded: Praat's PSOLA (`vpa/praatrender.py`), not TD-PSOLA from scratch

The from-scratch TD-PSOLA design originally sketched here (epoch detection via
low-pass + f0-guided peak picking, WSOLA fallback for unvoiced) **was actually
built and it sounded bad** — confirmed by ear, not just numerically. Two real
bugs were found along the way (see below), and even after fixing them the
hand-rolled renderer had a persistently harsh, artifact-heavy character on
real vocals. Root cause: no true glottal-pulse epoch detection, which is a
known source of robotic/phasey texture — real epoch detection (DYPSA-style)
is a much bigger undertaking than the original sketch assumed.

**Fix: stopped re-deriving PSOLA and used Praat's, via `parselmouth`.** Praat's
`To Manipulation` / `DurationTier` / `PitchTier` / `Get resynthesis
(overlap-add)` pipeline is a decades-refined reference PSOLA implementation
built for exactly this (pitch/duration manipulation of real voice recordings).
Swapping the renderer (leaving `align.py`'s DTW and `matchpitch.py`'s ratio
math untouched — both had already been validated independently) went from
"sounds bad" to "95% there, only the expected amount of pitch-correction
character" after three further tuning passes:

1. **Duration-tier "gargle"**: an early version fed Praat a duration-stretch
   ratio computed as a raw, unsmoothed numerical derivative at every 10ms —
   real tempo drift between two takes changes slowly (over syllables, not
   milliseconds), so this made the engine constantly speed up/slow down in
   tiny bursts. Fixed with a wide-baseline derivative (150ms), a smoothing
   pass (200ms), and sparse tier points (50ms spacing) — Praat interpolates
   linearly between points, which itself bounds how fast the stretch can change.
2. **Octave-tracking wobble**: Praat's own internal pitch tracker was given a
   generic wide floor/ceiling (55-800Hz) for every voice, which gives it more
   room to grab a subharmonic/overtone by mistake. Fixed by measuring the
   take's actual pitch range (5th/95th percentile, not min/max, so a stray
   floor-pinned frame doesn't blow out the range) and narrowing floor/ceiling
   to that — see `praatrender.estimate_pitch_range`.
3. **Median-filtering the raw pitch track before scaling it**: helps kill
   isolated octave-error blips, but overdoing it (tried a 70ms window) flattens
   natural pitch variation into a *more* robotic sound than no filtering at
   all — backed off to a light 30ms window (`median_window_points=3`), just
   enough for single-frame glitches.
4. **Pitch-match strength**: β=1.0 (full lock) is a meaningfully harder case
   than a partial correction and sounds more processed. **β≈0.5 is the
   practical sweet spot** — reads as "the expected amount of character that
   comes with any real pitch correction," not an artifact to keep chasing.
   Recommendation carried forward: default the eventual plugin's Pitch Target
   knob to ~50%, not 100%.

### 1c. Match Pitch (`vpa/matchpitch.py`)

Runs *after* time alignment, so both f0 curves share a time axis.

- `shift_cents(t) = β · (cents(guide_f0(t)) − cents(dub_f0(t)))`, β = strength.
- *Target Mode: Nearest Octave* — fold the guide↔dub interval to the nearest
  octave before applying, so an octave double or a deliberate harmony isn't
  collapsed onto the guide.
- Gate to frames where **both** are voiced and confident; hold and interpolate
  across gaps rather than snapping to zero.
- Smooth the shift contour (~50 ms) — an unsmoothed contour zippers audibly.
- *Formant shift* is **stretch goal only**, unchanged from the original plan.

### Phase 1 exit criteria

- [x] A double-tracked vocal of yours aligns audibly tighter than the raw take
      — confirmed on a real double-tracked clip (`test_input/guide.mp3` /
      `dub.mp3`), not just the synthetic test.
- [x] No audible artifacts on sustained notes, breaths, or sibilance — "95%
      there," the residual character is the expected kind for pitch
      correction, not a rendering bug. Gargle-type artifacts (real renderer
      bug) are gone.
- [x] Tightness knob has a smooth, musical range end to end — both extremes
      (0 and ~0.9) verified to behave correctly on the synthetic ground-truth
      test; full range not exhaustively re-tested on real audio.
- [x] Match Pitch is usable — **at β≈0.5, not β=1.0** (see above; the original
      criterion assumed 1.0 would be the clean target, which turned out wrong).
- [ ] Runs a 4-minute track in under ~30s — currently ~70s extrapolated
      (13.5s for a 45s clip). Left as a known, accepted gap for Phase 2 (C++)
      to close, per the original plan.

**Phase 1 is done.** Remaining polish (wider variety of real test material,
more tightness-range testing) can happen opportunistically; it's no longer
gating the next phase.

---

## 4. Phase 2 — Renderer selection, then C++ engine

> **This phase was rewritten after Phase 1.** The original version said "port
> the tuned Python to C++, function for function," listing a `psola.cpp`
> alongside `dtw.cpp` and `f0.cpp`. That premise died with the from-scratch
> PSOLA (§3, Phase 1b): the tuned Python is now substantially a wrapper around
> **Praat**, which is a large GPL application, not something you port
> function-for-function. What was a mechanical translation task is now an open
> question — *which embeddable C++ renderer matches Praat's quality on this
> voice?* — and it has to be answered before any C++ is written.

### 2a. Renderer A/B, in Python, by ear — **do this first**

Same method that worked in Phase 1: test candidates on the real
`test_input/guide.mp3` + `dub.mp3` pair, listen, decide. All candidates have
Python bindings or equivalents, so this costs no C++ at all.

| Candidate | Licence | Algorithm | Notes |
|---|---|---|---|
| **Praat** (current baseline) | GPL, huge app | PSOLA | The quality bar to match. Not embeddable in a plugin. |
| **Rubber Band** | GPL *or* paid commercial | phase-vocoder + transient handling | GPL is fine here — personal, non-distributed use never triggers GPL obligations. Mature, widely used in DAWs. |
| **Signalsmith Stretch** | MIT | phase-vocoder family | Header-only C++11, trivial to embed. Docs note time-stretch is best within 0.75–1.5× — our clamp is 0.5–2.0× and real drift is a few percent, so that fits. Python binding: `python-stretch`. |
| **WORLD** | modified BSD | vocoder (analysis/resynthesis) | Built for speech/singing specifically; very embeddable. Heavier analysis step. |

Note the algorithmic split: Praat is **PSOLA**, most embeddable options are
**phase-vocoder** family. PSOLA historically wins on monophonic voice, phase
vocoders can sound smeared/phasey on it. So a quality regression is a real
possibility, not a formality — which is exactly why this is tested before
committing.

**Decision point, not just prep:** if nothing matches Praat closely enough,
that is a signal to reconsider the whole delivery form. The standalone path
(§8) can simply *use* Praat, since it has no embedding constraint. Capture-mode
only makes sense if an embeddable renderer holds up.

### 2a result (resolved 2026-07-25): WORLD is the embeddable winner

Two blind, level-matched listening rounds on the real `test_input/` pair
(labels reshuffled between rounds; renderer identities withheld until after
each verdict, to keep the Praat baseline from steering the result).

| Renderer | Verdict | Licence | Embeddable? |
|---|---|---|---|
| **Praat** | **Best** — "most natural," one audible pitch-shifted word | GPL, monolithic app | No (baseline only) |
| **WORLD** | **Close second** — "pretty good," slight roboticness on **breaths**, "could be masked by instrumental" | modified BSD | **Yes — the pick** |
| Rubber Band R3 | "sounds like a vocoder" | GPL / commercial | Ruled out on quality |
| Signalsmith | "sounds like a vocoder" | MIT | Ruled out on quality |

**The phase-vocoder family is conclusively out.** This was predicted (PSOLA
wins on monophonic voice) but is now confirmed by ear, twice, independently.
Importantly it is *not* an integration bug on my side: Signalsmith was driven
by a crude chunked-streaming wrapper I suspected was at fault, but Rubber Band
R3 — driven properly via its native `--timemap`/`--pitchmap` API, on its
highest-quality engine — drew the identical description. Same artifact from a
good integration and a bad one ⇒ algorithm class, not wrapper.

**Two silent integration bugs were caught before they could corrupt the
verdict**, both of the "ran fine, produced wrong audio" variety that a
listening-only test would have misattributed to quality:
- Rubber Band ignores `--timemap` entirely unless an overall duration
  (`-D`/`-t`/`-T`) is also supplied. First render came back with the dub's
  *uncorrected* onset — i.e. "Rubber Band can't align" would have been a
  false conclusion about the library.
- WORLD's resynthesis clipped (peak pinned at exactly 1.0), which would have
  penalised it for distortion that was ours, not its.

**Consequence for R8**: raised but not fatal. WORLD is BSD, small, pure C, and
close enough to the Praat baseline to carry capture-mode. Remaining gap is
narrow and specific — breath/unvoiced realism, which is exactly WORLD's
*aperiodicity* stream, so it is a targeted fix rather than a vague quality
hunt. See §4 2a-bis.

### 2a-ter. Two further "improvements" that were tried and REJECTED

Both were blind-tested against the unmodified version and both sounded
clearly **worse**. Recorded so they don't get re-proposed later.

1. **Bypass WORLD where the required correction is tiny (<8 cents).** The
   reasoning seemed to follow directly from the breath fix — if resynthesis
   buys nothing where there's no pitch to move, it also buys nothing where the
   pitch barely moves. It sounded bad. **Why:** WORLD's resynthesis and the raw
   recording have subtly different timbre, so switching between them *mid-phrase*
   produces audible fluttering seams. The breath hybrid works because
   voiced↔unvoiced is a **natural perceptual boundary** that masks the switch;
   a cents threshold crosses no such boundary. This also matches earlier
   feedback preferring WORLD's *uniform* mild character over Praat's
   *localised* standout words — uniformity is worth more than local optimality.
   **Principle: blend at natural perceptual boundaries, never at arbitrary
   thresholds.**
2. **Finer WORLD frame period (5 ms → 2.5 ms).** Worse again, and worse still
   when combined with (1). Smaller hops are not automatically better — WORLD's
   5 ms default is tuned, and going finer makes the spectral-envelope estimate
   noisier.

Both are left in `worldrender.py` as parameters defaulting to off/5 ms, with
the reasoning in the docstring, purely to document the dead ends.

### 2a-bis. Closing WORLD's breath gap

WORLD decomposes voice into `f0` + `sp` (spectral envelope) + `ap`
(aperiodicity). Breaths and consonants are near-pure aperiodicity — the most
parametric of the three streams and the most prone to sounding synthetic on
resynthesis. Pitch correction is also *meaningless* in unvoiced regions, so
there is no reason to pay resynthesis cost there at all.

Approach: **hybrid render** — use WORLD's full resynthesis only where the
signal is voiced (where pitch actually needs moving), and for unvoiced regions
fall back to plain time-warped source audio, crossfaded at the boundaries.
Keeps WORLD's formant-preserving pitch control where it earns its keep, and
keeps real recorded breath where it does not.

**Result (blind round 3): the fix landed, and WORLD reached parity.** Same
renderer, only the unvoiced handling changed:

| | Verdict |
|---|---|
| WORLD plain | "still somewhat noticeable, especially in **breaths**" |
| **WORLD hybrid** | **"very very light and soft, almost unnoticeable robotic tone"** |
| Praat (baseline) | "fine breaths, overall less robotic — but **certain words sound more**" |

The remaining difference is a **trade, not a deficit**: Praat is smoother on
average but has localised bad spots (matching the round-2 note about "one word
where I could hear it was pitch shifted"); WORLD-hybrid is uniformly, mildly
processed with no standouts. For a double-track sitting under a lead vocal,
uniform-and-mild is arguably the better failure mode — localised glitches draw
the ear, uniform slight processing does not.

**→ Decision: WORLD (hybrid) is the renderer.** BSD-licensed, small, pure C,
embeddable, and at parity with a baseline that was never shippable anyway.

### 2a verdict → consequences

- **R8 resolved favourably.** An embeddable renderer holds up, so capture-mode
  is *not* invalidated and the standalone fallback (§8) is not forced.
- **Praat becomes prototype-only.** It stays in the repo as the reference
  baseline to A/B future changes against, but is not on the shipping path.
- **`--renderer world` becomes the default** for any further tuning, so the
  Python prototype and the eventual C++ engine are testing the same algorithm.
- **The next real gate is now §2.5** (do AU instances share process memory?),
  since renderer risk is retired and that is the remaining assumption
  capture-mode rests on.

### 2b. C++ engine — after 2a picks a winner

Port the parts that are genuinely ours (the alignment logic), and link the
chosen library for the rendering.

- `engine/` — `features.cpp`, `dtw.cpp`, `f0.cpp`, `warp.cpp`, plus a thin
  adapter around the chosen renderer. Pure functions over `float*` spans.
  **Note there is no `psola.cpp`** — that is deliberately the borrowed part.
- FFT and vector math via **Accelerate/vDSP** (free, fast, already on the machine).
- f0: port YIN (simpler) rather than full pYIN; validate against the Python
  pYIN output on the same files and only add the probabilistic layer if the
  simpler version measurably underperforms.
- **Regression harness**: a CLI that takes the same two wavs and must produce
  output within a tight tolerance of the Python reference. This is what keeps
  the port honest.

### Guiding principle (learned the hard way in Phase 1)

**Own the novel logic, borrow the solved DSP.** The guide/dub alignment is the
part nothing off-the-shelf does; time/pitch modification of a voice is a
decades-solved problem with mature implementations. The original plan had this
exactly backwards — it specified hand-rolling epoch detection and WSOLA
fallbacks while treating the alignment as routine — and that cost a full build
cycle before the ear test caught it.

---

## 5. Phase 3 — Capture-mode AU plugin shell

**ARA is out** (see Phase 0 result above — confirmed dead on this machine).
Instead: a plain AUv2 that captures audio during a single realtime playback
pass, the way VocAlign worked before ARA existed. Still a real Logic insert,
still saves with the project — just needs one play-through before it has
anything to align.

- **Role**: each instance is Guide or Dub, picked in the plugin UI. Roles and
  captured buffers are per-instance (no shared ARA document), so guide/dub
  pairing has to be done some other way — options, cheapest first:
  - A tiny shared registry keyed by a user-assigned **session name/ID** typed
    into both instances (e.g. a text field: "Take 1"). Any Dub instance with
    the same session ID as a Guide instance pairs with it. Simple, no IPC.
  - A shared singleton in the plugin's own process space holding
    `std::map<String, GuideBuffer>` — *if* AU instances of the same plugin
    load into the same Logic process, they can share process-wide state and no
    inter-plugin registry is needed at all.

> **This is an assumption, not a proven fact — see the R2 spike in §2.5.** An
> earlier draft of this plan claimed the Phase 0 diagnostic counters "proved
> process-wide statics work." They did not. Those counters only ever read zero,
> and two instances were never observed seeing each other's increments, so the
> spike said nothing either way about cross-instance sharing. Logic is also
> known to host AUs out-of-process (that's part of why ARA failed), which makes
> per-instance process isolation a live possibility rather than a remote one.
> **Capture-mode's entire guide/dub pairing model depends on this being true.**
- **Capture**: each instance appends incoming audio to an in-memory buffer
  in `processBlock`, tagged with the host's sample position from
  `AudioPlayHead`, while transport is running. A "Capture" toggle starts/stops
  recording (so a partial playback doesn't leave a corrupt buffer); a
  "Captured: 3:08" readout confirms it worked.
- **Compute trigger**: once both Guide and Dub buffers exist for a session,
  run the alignment/pitch-match engine on a background thread (same engine as
  Phase 2, unchanged), then atomically swap in the rendered output buffer.
- **Playback**: after processing, the Dub instance's `processBlock` reads from
  the rendered buffer at the host-reported position instead of passing
  through live input — so once computed, normal playback (no re-capture
  needed) hears the aligned result. Bypass reverts to the raw captured audio.
- Guide instances always pass through unmodified.
- Re-capture is manual (a button), not automatic — captured audio doesn't
  silently go stale if you tweak something upstream, which would be a much
  worse surprise than requiring an explicit re-take.

---

## 6. Phase 4 — WebView UI (Svelte)

JUCE 8 `WebBrowserComponent` with the native `WebSliderRelay` / `WebToggleRelay`
parameter bridge, resources served from an in-binary ZIP via
`ResourceProvider` (no localhost server, no file:// origin issues).

- Svelte app built with Vite to a single bundle, embedded via `juce_add_binary_data`.
- Waveform peaks and pitch curves pushed C++→JS as typed arrays through
  `emitEvent`; they're too large for the parameter bridge.
- **Page 1 — Match Timing**: stacked lanes (guide on top, dubs below), a
  role/solo control per lane, warp path shown as a shaded deviation ribbon on
  the dub lane. Controls: Match Timing on/off, Max Difference, Alignment Rule,
  Maximum Shift.
- **Page 2 — Match Pitch**: guide and dub f0 curves overlaid on a semitone grid
  — read-only, as decided. Controls: Match Pitch on/off, Max Difference,
  Target Mode, Pitch Target (dub↔guide blend), Transpose.
- Reuse the visual language and any suitable components from `web/src/lib`.

> **Risk**: `WKWebView` inside an out-of-process AU host may hit entitlement or
> sandbox restrictions. Prove a webview renders *inside Logic* (not just in the
> standalone build) as a one-hour check at the very start of this phase, before
> building any of the Svelte UI. If it fails, fall back to native JUCE painting
> — the engine and ARA layers are unaffected, so the loss is contained to UI work.

---

## 7. Phase 5 — Integration and polish

- Bypass / A-B compare, per-lane solo, "reset this lane"
- Sensible defaults so the common case is: insert on two tracks, hit Match, done
- A parameter and preset sanity pass
- `install.sh`: build → ad-hoc sign → copy to `~/Library/Audio/Plug-Ins/Components`
- Notes on rebuilding after a Logic or macOS update (AU cache clearing, revalidation)

---

## 8. **CHOSEN PATH (2026-07-25): standalone app, file round-trip**

> **Promoted from fallback to the chosen architecture.** The deciding factor
> was a downstream-workflow requirement that had not been on the table when
> capture-mode was picked: the aligned vocal then goes into **Melodyne or Flex
> Pitch**.
>
> **An AU plugin does not alter the audio file.** It processes in the signal
> chain; its output exists only as live audio. Flex Pitch and Melodyne operate
> on a *region*, so they physically cannot see a plugin's output — the plugin
> path would require a **bounce in place** before either could touch it. Add
> that capture-mode *also* needs a full realtime playback pass to capture, and
> the in-DAW workflow becomes: play through → process → bounce → *then* edit.
> The standalone workflow is: export → process → drag in → edit. Comparable
> step count, fewer moving parts. (Note too that Melodyne can't use ARA on
> this machine either — same Phase 0 finding — so it would be running its own
> transfer/capture mode, stacking two capture workflows back to back.)

### What this decision eliminates

| Risk / work item | Status under standalone |
|---|---|
| **R2** — do AU instances share process memory (§2.5) | **Moot.** Gate removed entirely. |
| **R3** — WKWebView blocked in out-of-process AU | **Moot.** Normal browser UI. |
| **R7** — capture-mode session-ID pairing UX | **Moot.** No pairing needed. |
| **Phase 2b** — C++ engine port | **Deleted.** Python ships as-is. |
| **Phase 3** — capture-mode plugin shell | **Deleted.** |
| Renderer restricted to embeddable libs (R8) | **Lifted** — Praat is eligible again. |

That is two unresolved unknowns and the entire C++ port, gone. The Phase 0/1/2a
work all survives: the DTW aligner, the pitch-ratio math, the renderer, the
44.1 kHz fix, and every tuning decision carry over untouched.

### Shape

Extend the existing FastAPI + SvelteKit app (`api/`, `web/`) with an alignment
page — the pitch plumbing, audio loading, and UI language are already there.
Two files in, one file out, using the tuned `vpa align` pipeline directly.

- **Everything in Phases 1, 2, 4 survives.** Only Phase 3 (the plugin shell) is lost.
- Shell options, cheapest first: extend the existing FastAPI + SvelteKit app
  (`api/`, `web/`) with an alignment page — the pitch plumbing and UI are
  already there — or build a JUCE Standalone target from the same engine.
- Workflow cost is real but bounded, and it is permanently immune to both
  Apple's ARA decisions and any AU process-hosting quirks.

---

## 9. Risk register

| # | Risk | Impact | Mitigation | Status |
|---|---|---|---|---|
| R1 | Logic 12.3 native won't host third-party ARA | Fatal to ARA plugin form | Phase 0 spike | **Confirmed true — ARA abandoned, see §5** |
| R2 | Same-plugin AU instances don't share process-wide state in Logic | Fatal to capture-mode's guide/dub pairing | **Promoted to its own early spike (§2.5)** — was wrongly buried inside Phase 3, and an earlier draft wrongly claimed Phase 0 had already proven it | Open — **untested, and the plan previously overstated it as proven** |
| R3 | WKWebView blocked in out-of-process AU | UI rework | One-hour check at start of Phase 4; native JUCE UI as fallback | Open |
| R4 | PSOLA artifacts on breathy / noisy vocals | Quality | Caught in Phase 1 on your own material, before any C++ | **Addressed — see §3 Phase 1b for the from-scratch→Praat swap and tuning history** |
| R5 | Ad-hoc signing rejected by Logic's AU scan | Blocks local install | Already proven fine in the Phase 0 spike (ad-hoc sign + `auval` passed) | Resolved |
| R6 | Logic/macOS update breaks the plugin | Maintenance | Pin JUCE versions; keep the standalone target (§8) working as an escape hatch | Open |
| R7 | Capture-mode session pairing (typed session ID) is fiddly in practice | Workflow friction | Tune the UX in Phase 5; fall back to §8 if it's never comfortable | Open |
| R8 | **No embeddable C++ renderer matches Praat's quality on this voice** | Would invalidate capture-mode (Praat can't ship in a plugin); standalone §8 becomes correct instead | **Phase 2a A/B in Python, by ear, before any C++** | Open — the current next step |

---

## 10. Sequence and rough effort

| Phase | Work | Rough effort | Status |
|---|---|---|---|
| 0 | ARA viability spike | half a day | **Done — ARA ruled out** |
| 1 | Python prototype, tuned by ear | the bulk of the quality work | **Done** |
| 2a | Renderer A/B, by ear | ~half a day | **Done — embeddability constraint since lifted, so renderer re-decided at 44.1 kHz** |
| — | Bandwidth fix (22.05 → 44.1 kHz render) | trivial, large payoff | **Done — confirmed by ear** |
| 2.5 | R2 spike: AU process sharing | — | **Cancelled — moot under standalone (§8)** |
| 2b | C++ engine port | — | **Cancelled — moot under standalone (§8)** |
| 3 | Capture-mode AU plugin shell | — | **Cancelled — moot under standalone (§8)** |
| **4** | **Alignment page in the existing FastAPI + SvelteKit app** | **moderate; iterative** | **Next** |
| 5 | Polish | small | Not started |

The ordering matters more than the estimates: **cheap tests that can
invalidate an expensive direction always come first.** Phase 0 de-risked the
form (and duly killed ARA); Phase 1 de-risked the quality (and duly killed the
from-scratch PSOLA). 2a and 2.5 are the same move applied to the two
assumptions capture-mode still rests on — an embeddable renderer that sounds
good enough, and cross-instance state sharing. Both are half-day questions
guarding multi-week commitments.

**Review note (2026-07-25):** phases were re-ordered after a retrospective.
Two errors were corrected — Phase 2's premise had silently died when the
renderer changed in Phase 1, and R2 was mis-filed as a Phase 3 sub-task while
also being wrongly described as already proven. Both are fixed above.

---

## 11. Proposed repo layout

Separate repo (`vocalign-personal`), with `vpa/` consumed as the prototyping
ground. Mixing a C++/JUCE build into this Python/SvelteKit repo would make both
harder to reason about.

```
vocalign-personal/
├── CMakeLists.txt
├── third_party/          JUCE (ARA_SDK no longer needed — kept for reference)
├── engine/               portable C++ DSP, no JUCE
│   └── test/             regression vs Python reference
├── plugin/
│   ├── spike/            the Phase 0 ARA spike (kept for reference; superseded)
│   └── align/            the real capture-mode plugin
├── ui/                   Svelte app → embedded bundle
├── proto/                symlink or submodule → vpa/ prototyping
└── install.sh
```

---

## 12. Explicitly out of scope

- Flex Pitch integration (no API; the plugin does the pitch work itself)
- Manual per-note pitch editing (decided: auto-match only)
- VST3, AAX, Windows, Intel
- Installer, licensing, presets beyond ARA state
- Polyphonic material — monophonic vocals only
```
