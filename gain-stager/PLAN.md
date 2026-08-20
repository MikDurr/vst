# Gain Stager — Implementation Plan

A personal-use auto gain staging Audio Unit for Logic Pro 12.3 on Apple Silicon.

Insert it on slot 1 of an audio track. It measures the track's loudness while
you play, then applies a single static trim so the track hits a consistent
level before it reaches your EQ, compressor, and the mix bus.

Target: `mikaild` only. No distribution, no installer, no Windows, no VST3/AAX.

---

## 0. Hard constraints (established, not assumed)

| Constraint | Consequence |
|---|---|
| Logic loads **Audio Units only**, never VST | Ship an AUv2 `.component`. |
| An AU receives a **stream of blocks**, never a file | The plugin can never rewrite audio on disk, and never redraws the arrange waveform. Committing is Bounce in Place (⌘B) or Track Freeze. |
| An AU cannot see **region boundaries** | Per-region level matching (Pro Tools-style clip gain) is structurally impossible here. Out of scope — see §7. |
| ARA does **not** bind in Logic 12.3 native arm64 | Established empirically in `vocalign-personal/PLAN.md` §0. The file-level plugin route is closed on this machine. This project does not need it. |
| Machine: arm64, macOS 26.5.2, Logic Pro 12.3 | Build arm64-only. |

### What "gain staging" means here, precisely

**One number per track.** Measure the track, compute `trim = target − measured`,
apply it as a constant gain, stop. It is deliberately *not* dynamic.

Anything that adjusts gain continuously over time is a **leveler** — it pumps,
it interacts badly with the compressor after it, and it has an entirely
different set of failure modes. It is a different plugin. Do not let this one
drift into becoming that.

### Phase 0 result (resolved 2026-07-26): the AU shell works

Built a passthrough AU (JUCE 8.0.9), installed it, and tested directly in Logic
Pro 12.3 running native arm64.

- `auval -v aufx Gnst Mkdd` — **passes**, including render tests at 11.025 /
  22.05 / 44.1 / 48 / 96 / 192 kHz, mono and stereo.
- Logic lists it under **Audio Units → mikaild → Gain Stager** after a relaunch
  (Logic only scans for new AUs at launch — a rescan is required after every
  first install, not after every rebuild).
- Inserted on a real 19-track session: `prepareToPlay` reported **44100 Hz**,
  block size 1024, 2 channels, **0 samples latency**. Block counter climbed and
  the peak readout tracked audio live.

**Finding 1 — the session was 44.1 kHz, not 48 kHz.** The hardcoded-coefficient
bug described in §2 would have been silently wrong on the first real project it
touched. Deriving the K-weighting at runtime is not defensive caution, it is
required.

**Finding 2 — Logic does not call `processBlock` on a track with no audio in
range.** With the transport rolling and the Stereo Out metering, the block
counter stayed at exactly 0 until the playhead crossed a region on *that*
track. Two consequences:

- **The plugin cannot detect "transport stopped" from the audio thread.** A
  stopped transport and a silent track are indistinguishable — in both cases we
  simply stop being called. Commit-on-stop must be driven from a message-thread
  timer polling `AudioPlayHead`, never from the absence of callbacks. See §3.
- Harmless to the measurement: blocks Logic never sends are precisely the
  blocks the absolute gate would have discarded anyway.

---

## 1. Architecture

```
┌──────────────────── Logic Pro 12.3 ─────────────────────┐
│  audio region                                           │
│       ↓                                                 │
│  region gain / fades      ← redraws waveform (not us)   │
│       ↓                                                 │
│  ┌───────────────────────────────────────────────┐      │
│  │ slot 1:  GAIN STAGER    ← we live here        │      │
│  │ slot 2:  EQ                                   │      │
│  │ slot 3:  Compressor      (sees a consistent   │      │
│  │ ...                       input level now)    │      │
│  └───────────────────────────────────────────────┘      │
│       ↓                                                 │
│  fader → pan → sends → bus → Stereo Out                 │
└─────────────────────────────────────────────────────────┘
```

### Two-layer split

```
core/                          plugin/
─────                          ───────
LoudnessMeter   (BS.1770-4)    PluginProcessor   state machine, params
TruePeakMeter   (4x OS)        PluginEditor      native JUCE UI
GateAccumulator (R128 gating)
   ↑ no JUCE, no realtime           ↑ JUCE, realtime
   ↑ unit-testable in isolation
```

`core/` is plain C++ with no JUCE dependency and no allocation in its hot path.
It is the piece worth getting exactly right, it is the piece that can be tested
against published reference values, and it is the piece a future CLI would
reuse unchanged.

---

## 2. Measurement

### K-weighting (ITU-R BS.1770-4)

Two biquads in series, per channel:

1. **High-shelf** ("head effect"), ≈ +4 dB above 1.5 kHz
2. **High-pass** (RLB), ≈ 38 Hz

> **The bug to avoid.** The coefficients published in BS.1770 are specified at
> **48 kHz only**. A large number of implementations hardcode them and are
> quietly wrong at 44.1 kHz and 96 kHz. Logic projects are routinely 44.1 k.
> Derive the coefficients analytically from the filter's pole/zero definition
> at the actual `sampleRate` handed to `prepareToPlay`, and prove it with the
> sample-rate test in §5.

### Gated integrated loudness

- Mean square over **400 ms blocks, 75 % overlap** (100 ms hop)
- Block loudness `L = −0.691 + 10·log₁₀(Σ Gᵢ·zᵢ)`; for stereo `G_L = G_R = 1.0`
- **Absolute gate**: discard blocks below −70 LUFS
- **Relative gate**: mean the survivors, set threshold at `mean − 10 LU`,
  discard below it, re-mean

The relative gate is the entire reason to use LUFS over RMS. A vocal track that
is 60 % silence reads catastrophically low on plain RMS, and a naive tool would
trim it up by 15 dB into the ceiling. Gating throws the gaps away.

### True peak

4× oversampled peak (BS.1770 minimum for ≤ 48 k), used **only** to clamp the
trim. This runs in a measurement side-chain — it must not add latency to the
audio path. `setLatencySamples(0)` is a hard requirement; this plugin has no
lookahead and should report none.

---

## 3. Behaviour

### State machine

```
        ┌──────── Reset ─────────┐
        ↓                        │
      IDLE ──transport rolls──► LEARN ──commit──► HOLD
                                          (trim frozen)
```

`LEARN` passes audio at unity gain while metering. `HOLD` applies the frozen
trim. Commit fires on whichever comes first:

- transport stops — **detected on the message thread**, by polling
  `AudioPlayHead` from a timer. It cannot be inferred from callbacks drying up:
  per the Phase 0 finding in §0, Logic stops calling `processBlock` entirely on
  a silent track, so "stopped" and "silent" are indistinguishable from the
  audio thread.
- **`learnSeconds` of gated-in audio** accumulated (not wall clock — silence
  must not count, or a sparse vocal commits on almost no data). Default 10 s;
  presets lower it for sparse sources, which gate at ~53%.
- user presses Hold

### Computing the trim

```
targetTrim = clamp(target − measured, ±24 dB)

# The ceiling may stop the trim making peaks WORSE. It may never force them
# below where they started: a source already above the ceiling is not the
# trim's doing, and turning a track down cannot clip.
reachable   = max(ceiling, measuredTruePeak)
ceilingTrim = reachable − measuredTruePeak      # never negative

if targetTrim > ceilingTrim:
    trim = ceilingTrim
    flag "ceiling-limited" in the UI            # never silently
else:
    trim = targetTrim
```

Applied through a ~50 ms `SmoothedValue` ramp so committing mid-playback
doesn't click. Constant thereafter.

### Parameters

All automatable, all persisted via `AudioProcessorValueTreeState`.

| Param | Range | Default |
|---|---|---|
| `target` | −36 … −6 LUFS | **−18** |
| `mode` | LUFS-I / LUFS-S max / RMS / Peak | LUFS-I |
| `trim` | −24 … +24 dB | 0 — the *output*, but user-editable to nudge |
| `hold` | bool | false |
| `autoLearn` | bool | true |
| `learnSeconds` | 5 … 120 | 20 |
| `ceiling` | −12 … 0 dBTP | −6 |
| `ceilingEnabled` | bool | true |
| `bypass` | bool | false — AU needs this declared explicitly |

### Persistence rule

**Reopening a project must never change the mix.** If a trim was committed,
the plugin loads in `HOLD` with that exact trim. It must not re-arm and
re-learn on the next transport roll. Store `trim`, `measured`, and `state` in
the APVTS tree.

---

## 4. Threading

The audio thread runs the K-filter (two biquads per channel — negligible) and
accumulates block mean-squares. It **must not** compute the gating, which needs
the whole block history.

Audio thread pushes block energies into a **preallocated ring buffer**
(36 000 entries ≈ 1 hour at 100 ms hop). Commit runs on the message thread and
reads from it. No locks, no allocation, no `std::vector::push_back` on the
audio thread.

---

## 5. Validation

**Reference tests (`core/tests/`, no JUCE, no DAW):**

- 1 kHz sine at −23 dBFS reads **−23.0 LUFS ± 0.1** — the EBU R128 anchor case
- EBU Tech 3341 compliance cases, momentary / short-term / integrated
- **Same signal at 44.1 k, 48 k, 96 k must agree within 0.1 LU** — this is the
  test that catches the hardcoded-coefficient bug in §2
- Silence does not produce `NaN` or `−inf` propagating into the trim
- A signal that is 90 % digital silence reads the same as the 10 % alone
  (proves gating works)

**Plugin-level:**

- `auval -v aufx Gnst Mkdd` passes
- Bypass is sample-accurate null against dry
- `getLatencySamples() == 0`
- Save / reopen a Logic project → identical trim, no re-learn

**Real-world:** drop it on 8 tracks of an existing session, learn, then check
every track reads within ±1 LU of target on a reference meter.

### Phase 1 result (resolved 2026-07-26): core passes, 33/33

`core/` builds free of JUCE and `./build/core/test_loudness` is green.

- K-weighting derived at runtime reproduces the **BS.1770-4 48 kHz table to
  1e-9**, so every other rate is correct by construction rather than by luck.
- 44.1 / 48 / 96 kHz agree within **0.02 LU** (−22.99 / −22.99 / −23.01).
- Both calibration anchors land exactly: 0 dBFS mono sine → −3.01 LKFS,
  −23 dBFS stereo sine → −23.0 LUFS. Linearity exact to 0.01 LU.
- True peak catches the fs/4 inter-sample case at −0.075 dBTP where the sample
  peak reads −3.01 dBFS.

**Known characteristic — sparse material reads slightly low.** With 400 ms
blocks at 75 % overlap, blocks straddling a tone/silence edge are genuinely
quieter and still clear the relative gate, so they pull the mean down. Measured
at 20 % duty cycle: **−24.06 LUFS with 1 s bursts, −23.22 LUFS with 5 s
bursts** — the deviation tracks *edge count*, not the amount of silence. This
is correct R128 behaviour, not a defect.

Consequence for gain staging: a very choppy source (a gated vocal, stabs) will
be trimmed up to ~1 LU hot. That is the residue after gating removes the ~7 dB
error an ungated mean would have made at the same duty cycle, so it is not
worth chasing — but it is the reason the ±1 LU real-world criterion above is
the right bar rather than ±0.2.

---

## 6. Phases

| Phase | Work | Status |
|---|---|---|
| **0** | Repo, CMake pointing at shared JUCE, hello-world AU passing `auval` | **done** |
| **1** | `core/` loudness engine + reference tests (§5). No plugin work. | **done** — 58/58 |
| **2** | Processor: state machine, params, persistence, ring buffer | **done** — `auval` green |
| **3** | Native JUCE editor — big LUFS readout, trim readout, target field, Learn/Hold/Reset, gated-audio progress, ceiling-limited warning | **done** |
| **4** | Validation in Logic on a real session | **done** |

### Phase 3 result: the editor, and a way to look at it

Custom `LookAndFeel`, 470 x 464. Two numbers carry the panel — **measured** and
**trim** — and they are the only large type on it. The trim greys out whenever
it is not actually being applied, so the panel never implies the audio is being
changed when it is not.

Everything else on it exists because Phase 4 found it missing:

- **Learn progress bar**, with a notch at the commit-on-stop threshold. A silent
  LEARN state was indistinguishable from a stuck one, and without the notch the
  bar suggests nothing can happen until it reaches the far end.
- **A status line that is never blank** — "needs 0.3 s more audio before it can
  commit" is the sentence whose absence cost an afternoon.
- **The ceiling notice is a note, not an alarm.** It was first drawn as a red
  banner reading "target not reached", and a real user read that as a failure —
  reasonably, because red plus the word "not" is what an error looks like.
  Nothing has failed: the plugin still raised the level, it just could not go
  the whole way. It now gets an amber left accent on the normal panel and leads
  with what it did: "Applied +7.98 dB of the +9.94 dB the target asked for",
  then the reason underneath.

**`plugin/tools/ui_snapshot.cpp` renders the editor to PNGs with no host.** It
drives the processor directly, pumps the message loop so the timers fire, and
writes one image per state (idle / learning / holding / ceiling-limited).
Reviewing a UI change previously meant inserting into a live Logic session,
which is disruptive and not repeatable — this is neither. Run it after any UI
change:

```
cmake --build build --target ui_snapshot
./build/plugin/ui_snapshot_artefacts/RelWithDebInfo/ui_snapshot <out-dir>
```

Two defects it caught immediately that a compile could not: a ~90 px dead zone
where a usually-absent warning banner was being reserved, and an em-dash in a
drawn string rendering as mojibake. **Keep drawn strings ASCII** — the `char*`
is not read back as UTF-8.

### Phase 4 result (resolved 2026-07-26): correct to 0.01 dB, after two fixes

Tested twice: once on a real 27-track session, once against a synthetic file of
known loudness (30 s stereo 1 kHz sine at exactly -30.0 LUFS by construction,
44.1 kHz 16-bit) in a throwaway project.

Against ground truth, target -18 LUFS:

| | expected | measured |
|---|---|---|
| loudness | -30.00 LUFS | **-29.99** |
| true peak | -30.00 dBTP | **-30.00** |
| trim | +12.00 dB | **+11.99** |

The 0.01 dB is 16-bit source quantisation. Auto-commit fired on its own at
10.0 s of gated audio. The channel meter held -18.0 dBFS afterwards, confirming
the gain reaches the audio and not just the readout. Save, close, reopen: came
back in HOLD at 11.99 dB, and ten seconds of further playback did not re-learn
or move the trim — the §3 persistence rule holds in the real host.

**Two bugs the synthetic tests could never have caught:**

1. **Reset did nothing while the transport was stopped.** `requestReset()`
   cleared the display, then the 10 Hz timer overwrote it 100 ms later by
   reading meters the audio thread had not cleared yet — and on a stopped
   transport that callback never arrives. Fixed by having the timer bail out
   while a reset is in flight. The hazard was anticipated in §4; the fix for it
   was not.

2. **Auto-commit never fired on real material.** A vocal produced 2.7 s of
   gated audio from ~20 s of playback — a ~1:7 ratio — leaving it just under
   the old 3.0 s floor, and the UI said nothing about why it was idle. The old
   `learnSeconds` default of 20 s would have needed two and a half minutes of
   playback. Now: floor 2.0 s, default 10 s, and the UI states what it is
   waiting for ("needs 0.3 s more audio before it can commit").

The general lesson for Phase 3: **sparse material is the design centre, not the
edge case.** Vocals are what this gets used on, and every threshold expressed in
gated seconds behaves very differently there than on a synthetic tone.

**Phase 2 note — the trim arithmetic lives in `core/`, not the processor.**
`gs::computeTrim()` takes the measurement, target, true peak and ceiling and
returns the trim plus a ceiling-limited flag. Putting it behind the JUCE
boundary would have made the single most consequential calculation in the
plugin untestable, and a sign error there is silent and wrecks a mix. It is
covered end-to-end: measure a signal, compute, apply, re-measure, land on
target to within 0.001 dB.

Two behaviours pinned by those tests, both intentional:

- A source too quiet to reach the target **lands short rather than exceeding
  ±24 dB**. At -43 dBFS RMS against a -18 target the ask is +25.01 and the
  result is +24, finishing 1 dB low.
- The ceiling **backs the trim off to land exactly on the ceiling** and raises
  a flag. Under-trimming without saying so would leave the track quieter than
  the readout claims.

Phase 1 is the one with real content. Do not start Phase 2 until the reference
tests pass — a meter that is quietly 2 dB off produces a tool that is worse
than doing it by hand.

### Phase 5 result: calibrated against real material, and presets

The question was whether the plugin could be "trained" on real vocals to make
it more accurate. It cannot, and does not need to be: BS.1770 is an exact
algorithm, not a learned model. What real material *can* do is validate it and
calibrate the defaults.

**Independent validation.** `core/tools/gs_analyze.cpp` is the CLI over `core/`
that §7 always said was possible. Piping real session files through it and
comparing against **ffmpeg's `ebur128`** — a completely separate implementation
— gives **0.03 LU mean absolute error, 0.05 LU worst case** over 11 files,
which is inside ffmpeg's own printed precision. The meter is correct.

**Calibration.** 200 files from the user's own sessions, grouped by instrument:

| class | median LUFS | median crest | p90 crest | gated |
|---|---|---|---|---|
| vocals | -26.8 | 12.6 | **21.0** | 53% |
| drums | -15.5 | 13.9 | 20.5 | 85% |
| bass | -10.5 | 9.8 | 11.9 | 96% |
| guitar | -13.8 | 12.1 | 14.4 | 93% |
| keys | -18.8 | 13.7 | 16.7 | 95% |
| synth | -18.9 | 12.7 | 16.4 | 95% |
| brass/strings | -15.2 | 12.4 | 14.6 | 85% |
| fx | -17.9 | 14.6 | 34.3 | 93% |

This drove three changes:

1. **Ceiling default -6 -> -1 dBTP.** Ceiling minus target caps the crest
   factor the plugin tolerates. At -6 against a -18 target that was 12 dB —
   below the median crest of every class measured except bass.

2. **The ceiling rule itself was wrong**, which the -6 default merely exposed.
   It compared `peak + trim` against the ceiling in absolute terms, so a source
   that already sat above the ceiling was dragged *down* even when the trim was
   negative — and turning a track down cannot clip. The rule is now: the
   ceiling may stop the trim making peaks worse, never force them below where
   they started. A real case (V4: -17.93 LUFS, -3.11 dBTP, already on target)
   was being pushed 2.8 dB under target and told the ceiling did it. That case
   is now a permanent regression test.

3. **Factory presets** in `core/Presets.h`, exposed as AU programs so Logic
   lists them in its own header menu. Values come from measurement, not taste.
   Expanded to **21** after a second pass over the library discovered the
   synth family was being lumped into one bucket: arps gate at 84% and pads at
   97%, which is a real difference in how long each must play before it can
   commit. Plucks, arps, chords/stabs, pads, lead synth, bells, percussion,
   sub/808 and choir were measured separately and given their own entries.

   Three rules turn the measurements into values: `learnSeconds` is set to
   about `12 x gated-ratio`, so every preset takes a comparable ~12 s of
   *playing* to commit; anything above ~14.5 dB median crest uses short-term
   max, since integrated loudness under-reads bursts; and one-shots and fx are
   staged by **peak** at -6 dBTP, because a gated loudness target on a 0.3 s
   sample is meaningless and fx measured a p90 crest of 34.7 dB.

   **Preset order is load-bearing.** The AU program index is a position in this
   table and saved projects store that index, so reordering makes an old
   project display the wrong preset name. Parameter values still restore
   correctly from the APVTS state, so nothing sounds different -- but append
   new presets rather than inserting them. Tests look presets up by name for
   the same reason. `learnSeconds` counts gated audio, so sparse sources get
   smaller numbers to commit in comparable wall-clock time; transient material
   uses short-term max or true peak, where integrated loudness under-reads
   bursts. Where classes measured the same they share values — guitar, keys and
   synth sit within 1.5 dB of each other on both crest and gating, so inventing
   a difference would be dishonest.

### Audit (2026-08-19)

A full pass over build, tests, threading, and behaviour. Everything below was
found by the audit, not by use.

**Build.** Clean-room rebuild is warning-free in `core/` and `plugin/`. Four
real warnings were fixed: a private `setParameter` helper shadowing
`AudioProcessor`'s deprecated virtual of the same name (renamed
`setParamValue`), an unused parameter, an implicit int-to-float narrowing, and
six float-equality comparisons now using `juce::exactlyEqual`.

**Data race — fixed.** `TruePeakMeter::peak` was a plain `double`, written on
the audio thread by `process()` and read on the message thread by the
processor's timer and by `commit()`. Now `std::atomic<double>`, relaxed, the
same way `LoudnessMeter::shortTermMaxPower` already was. Aligned doubles happen
to be atomic on arm64, so this would likely never have misbehaved in
practice — but it was formally undefined and free to fix.

**Behaviour bug — fixed.** Moving Target or Ceiling while in HOLD did nothing.
The measurement is frozen once committed, so the trim was never recomputed and
the Target slider silently stopped working the moment it mattered. The timer
now recomputes from the frozen measurement whenever those settings move. The
committed true peak is persisted too, so a reloaded project can still honour
the ceiling.

**UI gap — fixed.** In short-term-max mode with under 3 s of audio the panel
said "Ready" and then `Hold now` did nothing, because the mode had no reading
to commit. The status line now says so.

**Memory.** The block ring defaulted to an hour of capacity: 576 kB per
instance, ~15 MB across a 27-track session. `learnSeconds` maxes at 120, so
600 s is still 5x headroom — now 94 kB per instance, 2.5 MB per session.

**Realtime safety** re-verified: no allocation, locks, or I/O in `processBlock`.
Meter resets run on the audio thread by design (clearing buffers the audio
thread is reading would race); it is a one-off memset, now ~94 kB.

**Meter accuracy, independently confirmed.** 39 real session files piped through
`gs_analyze` and compared against **ffmpeg's `ebur128`**: mean absolute error
**0.023 LU**, worst **0.050 LU** — inside ffmpeg's own printed precision.

**Test suites now:**

| suite | what it covers | count |
|---|---|---|
| `core/tests/test_loudness.cpp` | DSP: coefficients, calibration, gating, rate invariance, trim maths | 64 |
| `plugin/tools/plugin_tests.cpp` | processor: gain reaching the audio, bypass null, state round-trip, presets, commit state machine | 21 |

`plugin_tests` is what caught the HOLD-editing bug; no amount of DSP testing
would have. Run both plus `auval` after any change:

```
cmake --build build --target test_loudness plugin_tests GainStager_AU
./build/core/test_loudness && ./build/plugin/plugin_tests_artefacts/RelWithDebInfo/plugin_tests
auval -v aufx Gnst Mkdd
```

---

## 7. Explicitly out of scope

- **Per-region / clip-gain-style level matching.** Structurally impossible from
  inside an AU (§0). It would require an external tool driving Logic's Region
  inspector via accessibility automation. Gated behind its own spike if ever
  wanted — the question to answer first is *"can we reliably read and write the
  Region Gain field for 20 consecutive regions?"*
- **Dynamic gain riding / leveling.** Different plugin (§0).
- **Cross-track coordination.** Each instance independently targets the same
  absolute LUFS number, which is what gain staging means — there is nothing to
  coordinate. Avoids the unresolved out-of-process AU question in
  `vocalign-personal/PLAN.md` §2.5 entirely.
- **Rewriting audio files on disk.** A CLI over the same `core/` could do it.
  Deliberately deferred; it has no undo and the AU makes it unnecessary.
- VST3, AAX, Windows, Intel, installers, presets sharing.

---

## 8. Repo layout

```
M_VSTs/
├── vocalign-personal/          own git repo — UNTOUCHED by this project
│   └── third_party/JUCE/       submodule, JUCE 8.0.9
└── gain-stager/                own git repo
    ├── CMakeLists.txt          JUCE_PATH → ../vocalign-personal/third_party/JUCE
    ├── PLAN.md
    ├── core/                   no JUCE
    │   ├── LoudnessMeter.{h,cpp}
    │   ├── TruePeakMeter.{h,cpp}
    │   └── tests/
    └── plugin/
        ├── CMakeLists.txt
        └── Source/PluginProcessor.{h,cpp}, PluginEditor.{h,cpp}
```

**JUCE is shared by path, not by hoisting.** `JUCE_PATH` is a CMake cache
variable defaulting to the sibling checkout. This avoids moving
`vocalign-personal`'s submodule — surgery on a repo with a working ARA spike in
it, to save 85 MB. Cost: a fresh clone of `gain-stager` alone won't build until
JUCE exists at that path or `-DJUCE_PATH=` is passed. Acceptable for a repo
that never leaves this machine.

`gain-stager/` **must** stay a separate git repo. `/Users/mikaild` is itself a
git repo, so an un-`init`ed directory here would commit alongside `~/.ssh` and
shell history.

**Plugin identity:** `PLUGIN_MANUFACTURER_CODE Mkdd`, `PLUGIN_CODE Gnst`,
`BUNDLE_ID com.mikaild.gainstager` — manufacturer code matches the existing
spike, plugin code must not collide with `Arsp`.
