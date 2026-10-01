# mixlens

Measures your mix against reference tracks you choose, one reference set per
style, and flags where you drift outside that range. Runs hard safety checks
for clipping and over-peaking, stores every mix version, and, once you label
old mixes as "held up" or "regret", finds the features that predict your
regret.

See [`SPEC.md`](SPEC.md) for the full feature and comparison-logic
reference; this README covers day-to-day use.

Target aesthetic: electronic-inspired, blended and reverb-heavy vocals over
drier instrumentals, hyperpop-style top-end sheen. The reference sets you
build define the actual targets — the features only describe the dimensions
this sound varies along.

## Setup

Python 3.9-3.12 (3.9 matches the other tools in this repo, which need it for
PyTorch/numba wheels on this Mac):

```bash
cd mixlens
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

`ffmpeg` on PATH is only needed for the optional codec-overs check
(`peaks.codec_check_enabled: true` in `config.yaml`).

## Inputs

For each song version, export four WAVs from Logic (48kHz/24-bit, same
length, all starting at bar 1) named `{song}__{version}__{stem}.wav`:

| Stem | Contents |
|---|---|
| `mix` | Full bounce, master chain on |
| `vox_dry` | Vocal bus, inline processing, sends muted, master bypassed |
| `vox_wet` | Vocal reverb/delay aux returns only, master bypassed |
| `inst` | Everything except vocals and vocal auxes, master bypassed |

with a sidecar `song.yaml` next to them (`mixes/{song}/`):

```yaml
song: neon_altar
style: dream        # dream | hyperpop | electroclash
bpm: 140
sections:
  intro: [0, 14]
  verse1: [14, 48]
  hook1: [48, 70]
```

Reference tracks (12-20 per style, full songs, untouched) go under
`references/{style}/` and get registered in `references/references.yaml` —
see `mixlens ref add`.

## Instrumental songs

Tick **"This song is an instrumental"** when uploading (or set `instrumental: true` in `song.yaml`). Then:

- Only `mix` is required. Nothing is split with Demucs, and the vocal measurements (vocal level, consonant
  clarity, reverb space, ducking, wet/dry) are skipped, leaving the whole-mix ones: loudness, dynamics, tonal
  balance, stereo width, top end, punch, pumping.
- Every reference is also measured on its Demucs **accompaniment** (vocals removed), filed under the style key
  `<style>::instrumental`. Compare uses that set by default, so an instrumental is judged against references
  without a vocal sitting in their midrange. It is approximate (Demucs leaves a little vocal bleed); pick
  "References' full mix" instead if your references are themselves instrumentals.
- CLI: `mixlens report <song> <version>` does the same; add `--refs-full-mix` for the full-mix basis.
- Re-run **Build envelopes** once after upgrading so existing references get their accompaniment measurements.

## Usage

Everything below has a UI equivalent (`mixlens ui`) — see the next section.
The CLI is there for scripting or when you'd rather not open a browser tab:

```bash
mixlens ref add references/dream/*.flac --style dream
mixlens ref build-envelopes
mixlens ref audit                             # leave-one-out outliers

mixlens check mixes/neon_altar --version v3   # peak safety only, fast
mixlens analyze mixes/neon_altar --version v3 # checks + all features
mixlens report neon_altar v3                  # safety table, flag table, hints
mixlens diff neon_altar v2 v3

mixlens label neon_altar v1 regret --tag buried --note "hook vocal vanished"
mixlens regret                                # needs >=5 labeled held_up + regret

mixlens ui
```

All commands run from the `mixlens/` project root (they read `config.yaml`
and write `mixlens.db` there).

## UI

```bash
mixlens ui
```

opens a Streamlit app with five pages, each backing the CLI commands above:

| Page | Does |
|---|---|
| Analyze | Pick a song + version found under `mixes/`, run peak checks or the full analysis (Demucs + all features) |
| Compare | Peak-safety banner, LTAS vs. style envelope, flag table with hints, space-vs-sheen scatter |
| History | Feature trends across a song's versions, plus a two-version diff |
| References | Register reference files by glob + style, build/rebuild envelopes, leave-one-out audit, feature distributions |
| Regret | Label a version held_up/neutral/regret, and once you have 5+ of each, the effect-size ranking |

The Analyze and References pages call the same `pipeline`/`io` functions the
CLI does — nothing needs to be re-run afterward to pick up what you did in
the UI, and vice versa; both read and write the same `mixlens.db`.

## Calibration

Four thresholds in `config.yaml` are educated guesses: the CSI margin, the
active-frame loudness threshold, the phrase-end drop, and the strong-onset
percentile. Before trusting flags, run M2/M3 features on 3 songs you know
well, tune `config.yaml` until the flagged sections match what you hear, then
freeze it — each analysis records the config's hash.

## Build order (from the design spec)

| Milestone | Scope |
|---|---|
| M1 | Loader, loudness, peak safety checks, tonal, dynamics, envelopes, text report |
| M2 | Demucs caching, segments, vocal features, CSI, masking |
| M3 | Space, sheen, and micro-dynamics features, leave-one-out audit |
| M4 | Database, versions, `diff`, `check` |
| M5 | Wet/dry internal features, translation |
| M6 | Streamlit UI |
| M7 | Labels and regret analysis |

This build includes all seven milestones' code; M6/M7 need real analyzed
data (references built, several versions analyzed, 10+ labels) to be useful
end to end.

## Tests

```bash
.venv/bin/pytest tests/ -v
```

Synthetic-signal tests for loudness (vs `pyloudnorm`), peak checks (clipped
sine, inter-sample overs), CSI (clicks over noise at known SNRs), space
(exponential tail decay recovery), sheen (shaped-noise band ratios), and
micro-dynamics (compression, transients, sidechain-style pumping).
