# vocalign

A personal VocAlign. Locks a doubled vocal take onto a guide take — timing
first, then pitch — and hands back a 44.1 kHz WAV you drop into your DAW.

Built for one person, not for release. macOS, Apple Silicon.

```bash
./run.sh          # starts the engine + UI, prints the URL
```

Then open **http://localhost:5180**.

---

## What it actually does

**The output is your dub take, moved to fit the guide.** Nothing is mixed or
combined. The guide is read-only reference: it's analysed to work out *where*
the dub should land and *what pitch* it should hit, and its audio never enters
the output.

For a three-part stack:

```
main vocal ─┐
            ├─ guide (reference only, never output)
double L ───┴──→ double L, aligned to main
double R ──────→ double R, aligned to main
```

Load the guide once, add both doubles, hit Align — you get two corrected files
and your main vocal is untouched.

## Controls

| Control | What it does |
|---|---|
| **Match Timing** | Master on/off for time alignment. |
| **Max difference** | 0 = leave the dub where it is · 1 = snap hard to the guide. Default 0.85. |
| **Maximum shift** | How far a syllable may be nudged. Raise it if the takes start far apart. Default 400 ms. |
| **Match Pitch** | Master on/off for pitch correction. |
| **Pitch target** | 0 = dub's own pitch · 1 = fully locked to the guide. **Default 0.5** — a full lock sounds noticeably more processed. |
| **Target mode** | *Nearest oct* folds the interval so a deliberate octave harmony isn't collapsed onto the guide. *Absolute* doesn't. |
| **Renderer** | `praat` (default, best-sounding) or `world`. See [PLAN.md](PLAN.md) §4 for how this was chosen. |

**Worth trying:** on a wide stack, turn **Match Pitch off** entirely. Pitch
variance between takes is a lot of what creates thickness — lock a double too
tightly to the lead and it can start sounding like a phasey copy rather than a
second performance. Tight timing + natural pitch is a very common way to treat
a stack.

## Where this sits in a session

```
1. Record everything
2. Fix the guide      — Flex Time, then Melodyne / Flex Pitch
3. Bounce the corrected guide          ← this is what you feed in
4. Export each raw double
5. Align the doubles → corrected guide ← vocalign
6. Import each aligned file back onto its own track
7. Gain stage / balance the finished stack
```

**The guide must be fixed before you align to it.** The doubles are aligned
*to* the guide, so it's the target — correct it first and the doubles inherit
that correction. Do it the other way round and you'd align to an uncorrected
guide, then move the guide out from under them.

**Gain stage last.** Levels barely move through the tool (measured: −0.20 dB
RMS, −0.08 dB peak), so it isn't disturbed either way — but a tightened stack
*sounds* denser than a loose one, and the balance you'd dial before alignment
isn't the one you'll want after.

**Importing:** drop the aligned file onto the *existing* double track,
replacing the raw region. The channel strip, plugins and fader all stay; only
the audio swaps.

## Panning and stereo

Align **before** panning. A double is recorded mono and panned in the DAW
afterwards, so panning never touches this tool.

Stereo files work too — channel layout and width are preserved (measured:
panning ratio 3.00 in → 3.00 out, L/R correlation 0.9998, no phase
cancellation on mono sum). The same time and pitch maps are applied to every
channel so they stay locked together.

## Naming

Output is `<dubname>_aligned.wav`. Name your takes distinctly
(`double_L.mp3` / `double_R.mp3`) or you'll get two files with the same name.

---

## Running it

```bash
./run.sh
```

Starts the Python engine on **:8010** and the UI on **:5180**, waits for both
to answer, then prints the URL. Ctrl+C stops both. If either port is already
in use it reuses what's there rather than failing.

Ports deliberately avoid 8000/5173 — the vocal training studio uses those, and
both projects may be running at once.

To run the halves separately:

```bash
.venv/bin/python -m uvicorn api.main:app --reload --port 8010
cd web && npm run dev
```

The UI is only the interface; all the DSP runs in the Python engine. If the
engine isn't up, the titlebar shows **Engine offline** and Align will fail with
a message telling you how to start it.

### First-time setup

```bash
/usr/bin/python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cd web && npm install
```

Python 3.9 (librosa/numba wheels). `ffmpeg` must be on PATH for video input.

---

## Layout

```
vocalign/          the DSP — align, pitch-match, render
  align.py         DTW time-map solver (guide ↔ dub)
  matchpitch.py    pitch-ratio curve
  praatrender.py   PSOLA renderer via parselmouth  ← default
  worldrender.py   WORLD vocoder renderer          ← embeddable alternative
  rbrender.py      Rubber Band  ┐ evaluated and rejected on quality,
  ssrender.py      Signalsmith  ┘ kept so the A/B is reproducible
  vocalign.py      ties it together (align_takes)
  audio.py         loading, ffmpeg, multichannel  ┐ copied from the training
  pitch.py         pYIN pitch extraction           │ studio so this project
  notes.py         note naming                     ┘ stands alone
api/               FastAPI wrapper — one endpoint, POST /api/align
web/               SvelteKit UI
plugin/spike/      the abandoned ARA plugin spike (kept for reference)
test_input/        guide.mp3 + dub.mp3 used throughout development
test_output/       every render from the renderer A/B rounds
```

`audio.py`, `pitch.py` and `notes.py` were **copied** from
`vocal-pitch-analyzer` rather than imported, so this project has no dependency
on it. They're the stable part of that codebase and rarely change.

## Why it's a standalone app and not a plugin

Short version: Logic on Apple Silicon won't host third-party ARA, and a plain
AU can't alter the audio *file* — which Melodyne and Flex Pitch both need,
since they edit regions, not plugin output.

The full decision history, including two blind listening rounds that picked the
renderer and several documented dead ends, is in **[PLAN.md](PLAN.md)**.
