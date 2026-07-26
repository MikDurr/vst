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
- **20 s of gated-in audio** accumulated (not 20 s of wall clock — silence must
  not count, or a sparse vocal commits on almost no data)
- user presses Hold

### Computing the trim

```
trim = clamp(target − measured, ±24 dB)

if ceilingEnabled and (measuredTruePeak + trim) > ceiling:
    trim = ceiling − measuredTruePeak        # back off
    flag "ceiling-limited" in the UI          # never silently
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

| Phase | Work | Est. |
|---|---|---|
| **0** | Repo, CMake pointing at shared JUCE, hello-world AU passing `auval` | ½ day |
| **1** | `core/` loudness engine + reference tests (§5). No plugin work. | 1 day |
| **2** | Processor: state machine, params, persistence, ring buffer | 1 day |
| **3** | Native JUCE editor — big LUFS readout, trim readout, target field, Learn/Hold/Reset, gated-audio progress, ceiling-limited warning | ½ day |
| **4** | Validation in Logic on a real session | ½ day |

Phase 1 is the one with real content. Do not start Phase 2 until the reference
tests pass — a meter that is quietly 2 dB off produces a tool that is worse
than doing it by hand.

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
