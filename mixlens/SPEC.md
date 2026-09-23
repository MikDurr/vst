# MixLens: Design Spec

MixLens measures your mix against reference tracks you choose, one reference set per style, and flags where you drift outside that range. It also runs hard safety checks for clipping and over-peaking, stores every mix version, and, once you label old mixes as "held up" or "regret", finds the features that predict your regret.

Target aesthetic: electronic-inspired, with blended and reverb-heavy vocals over drier instrumentals, and a hyperpop-style sheen (bright, dense, polished top end). The reference sets define the actual targets; the features below only describe the dimensions this sound varies along.

---

## 1. Inputs

### 1.1 Your mixes

For each song version, export four WAVs from Logic (48 kHz / 24-bit, same length, all starting at bar 1):

| Stem | Contents |
|---|---|
| `mix` | Full bounce, master chain **on** |
| `vox_dry` | Vocal bus with inline processing, send returns muted, master bypassed |
| `vox_wet` | Vocal reverb/delay aux returns only, master bypassed |
| `inst` | Everything except vocals and vocal auxes, master bypassed |

Naming: `{song}__{version}__{stem}.wav`, e.g. `neon_altar__v3__vox_dry.wav`.

Sidecar `song.yaml` in the same folder:

```yaml
song: neon_altar
style: dream        # dream | hyperpop | electroclash
bpm: 140
sections:           # seconds, from Logic markers
  intro: [0, 14]
  verse1: [14, 48]
  hook1: [48, 70]
```

### 1.2 References

References are songs whose **mix** you want yours to sit near. Picking them well matters more than any metric in this spec.

Selection rules:

1. **One set per style.** Keep `dream`, `hyperpop` and `electroclash` separate, since their vocal depth, reverb and loudness differ.
2. **12 to 20 tracks per style.** Fewer than 8 makes the percentiles meaningless.
3. **Pick for the mix.** A song you love with a vocal treatment you'd never use will pull the envelope the wrong way. Choose tracks where the vocal blend, reverb and top-end sheen match what you want.
4. **Max 3 tracks per artist.** Otherwise the envelope becomes one engineer's fingerprint.
5. **Lossless or high-bitrate only.** Use WAV/FLAC, or 256 kbps+ AAC/320 kbps MP3. Low-bitrate files cut everything above 16 kHz and blur transients, which corrupts the tonal and sheen features.
6. **Full songs, untouched.** Don't trim or normalize them yourself; the pipeline normalizes loudness.

Register them in `references/references.yaml`:

```yaml
- path: dream/track_01.flac
  style: dream
  artist: Example Artist
  title: Example Title
  note: "vocal sits deep but consonants cut through; bright gated verb"
```

**Leave-one-out audit.** After building envelopes, MixLens scores each reference against the envelope made from the other references in its set. A reference with more than 3 `flag` results probably belongs to another style, or is an outlier worth dropping. Run this whenever you add references.

### 1.3 Separation

Demucs (`htdemucs`) splits every reference into `vocals` and `accompaniment`. Its vocal stem includes reverb and some bleed, so to keep comparisons fair MixLens also runs **your** `mix` through Demucs. Two analysis paths follow:

| Path | Data | Compared against |
|---|---|---|
| Reference path | Demucs split (yours and refs) | Style envelope |
| Internal path | Your true stems | Your own version history |

Features from the internal path carry a `_true` suffix.

---

## 2. Peak Safety Checks (absolute, run first)

These are pass/fail rules. Envelopes don't apply to them.

| Check | Rule | Level |
|---|---|---|
| `clip_runs` | Runs of 3+ consecutive samples with \|x\| ≥ 0.999 FS, per channel | any run = **fail** |
| `true_peak` | 4× oversampled true peak (`scipy.signal.resample_poly`) | > 0.0 dBTP **fail**, > −1.0 dBTP **warn** |
| `isp_overs` | Count of oversampled points above 0 dBTP | > 0 = **fail** |
| `stem_headroom` | Sample peak of each stem | > −0.3 dBFS **warn** (bounce may clip at the 24-bit fixed-point stage) |
| `codec_overs` *(optional)* | Encode mix to 256 kbps AAC via ffmpeg, decode, re-check true peak | > 0.0 dBTP **warn** |

The report lists each failure with a timestamp and bar number, computed as `bar = t * bpm / 240 + 1` in 4/4.

**Intentional distortion.** Clip Distortion and hard clipping inside your chains flatten waveform peaks *below* full scale. The checks above only look at the file ceiling, so they won't flag your intentional grit. An info-only metric, `flat_top_ratio`, counts flat-topped runs below 0.95 FS, letting you see how much clipping you put in on purpose.

---

## 3. Features

Conventions:

- Resample to 44.1 kHz. Spectral features use loudness-normalized audio (−14 LUFS).
- STFT: `n_fft=4096, hop=1024` for tonal work; `n_fft=1024, hop=256` for transients.
- A vocal frame (400 ms momentary) counts as **active** when its loudness sits within 30 LU of the vocal's max (configurable).

### 3.1 Whole mix

| Feature | Definition |
|---|---|
| `ltas` (28 bands) | 1/3-octave long-term average spectrum, 31.5 Hz to 16 kHz, dB, offset so the 250 Hz to 4 kHz mean = 0 |
| `lufs_i` | Integrated loudness |
| `lra` | Short-term (3 s) loudness, gated, 95th minus 10th percentile |
| `plr` | True peak minus `lufs_i` |
| `crest` | Peak-to-RMS ratio, dB |
| `side_mid_{band}` | Side/mid energy ratio, dB, in bands <120 Hz, 120 to 500 Hz, 500 Hz to 4 kHz, >4 kHz |
| `corr_{band}` | Phase correlation per band |

### 3.2 Vocal level and tone

| Feature | Definition |
|---|---|
| `vir_med`, `vir_iqr` | Vocal-to-instrumental ratio: momentary LUFS of vocal minus instrumental over active frames |
| `vir_{section}` | Median VIR per section from `song.yaml` |
| `vox_consistency` | Std of vocal momentary loudness over active frames |
| `vox_harsh` | Vocal 2 to 5 kHz energy minus 200 Hz to 1 kHz, dB |
| `vox_sib` | Vocal 5 to 10 kHz energy minus 200 Hz to 1 kHz, dB |

### 3.3 Blend: consonant survival

`csi` separates a vocal that sits deep in the mix from one that has been buried.

1. High-pass the vocal at 2 kHz and detect onsets (`librosa.onset.onset_detect`, hop 256).
2. For each onset, take a 40 ms window. For each ERB band from 2 to 6 kHz, the band survives if `vocal_dB ≥ inst_dB − 6` (margin configurable).
3. Onset score = fraction of surviving bands.
4. `csi` = mean onset score; `csi_p10` = 10th percentile (the worst moments).

| Feature | Definition |
|---|---|
| `csi`, `csi_p10` | As above |
| `mask_{body,presence,air}` | Median of inst dB minus vocal dB per ERB band, grouped 200 Hz to 1 kHz / 1 to 4 kHz / 4 kHz+. Info only, since some overlap is the point |

Blended references show low `vir_med` with healthy `csi`. A buried mix shows both low.

### 3.4 Space and sheen

Two things define this sound beyond vocal level: **space contrast** (wet vocals over a drier instrumental) and **sheen** (the bright, dense, polished top end of hyperpop-style production). The references set what "right" looks like; these features measure where you sit.

**Space: reference path** (Demucs stems; the vocal stem carries its reverb)

| Feature | Definition |
|---|---|
| `vox_tail_level` | Median level 150 to 400 ms after each vocal phrase end, relative to the phrase. How loud the vocal reverb sits |
| `vox_tail_decay` | Level slope (dB/s) over the first 300 ms after each phrase end. Shallower = longer tail |
| `vox_tail_bright` | Tail spectral centroid minus phrase centroid, in octaves. Positive = bright tail |
| `inst_decay` | Median level slope (dB/s) over the 300 ms after strong onsets in the accompaniment stem. Steeper = drier instrumental |
| `space_contrast` | `inst_decay` minus `vox_tail_decay`, in dB/s. Larger = wetter vocal relative to the instrumental |
| `vox_attack` | Median dB rise over the 10 ms after each vocal onset, 2 to 8 kHz. Info only: tracks whether the reverb blurs word onsets |

Phrase end: the frame where the 50 ms vocal level drops more than 15 dB within 100 ms after an active stretch of at least 500 ms. Strong onset: onset-strength peaks above the 80th percentile. Both are heuristics; tune them during calibration (section 9).

**Sheen: reference path** (full mix, loudness-normalized)

| Feature | Definition |
|---|---|
| `air_ratio` | Energy 10 to 16 kHz minus 1 to 4 kHz, dB |
| `presence_ratio` | Energy 4 to 10 kHz minus 1 to 4 kHz, dB |
| `hf_density` | Short-term (100 ms) crest factor of the >4 kHz band, median. Lower = denser, more compressed and saturated top end |
| `hf_flatness` | Median spectral flatness above 4 kHz. Higher = noisier, fizzier top (saturation, OTT); lower = cleaner tonal top |
| `side_mid_air` | Side/mid energy ratio above 8 kHz, dB. Wide shimmering highs |
| `vox_air_ratio` | Same as `air_ratio` on the vocal stem alone |

**Space: internal path** (your true stems)

| Feature | Definition |
|---|---|
| `wet_dry_true` | Loudness of `vox_wet` minus `vox_dry` |
| `csi_wash_drop_true` | CSI with wet counted as signal minus CSI with wet counted as masker. Large = your reverb covers your own consonants |
| `duck_depth_true` | Wet level in dry-gap frames minus wet level in dry-active frames (100 ms windows). Positive = reverb ducks under the dry vocal and blooms in the gaps |
| `predelay_true` | Median time from each dry onset to the wet envelope reaching half its local max |
| `wet_bright_true` | Centroid of `vox_wet` minus centroid of `vox_dry`, in octaves |

### 3.5 Translation

Recompute `vir_med` and `csi` under two simulations:

| Sim | Processing |
|---|---|
| `phone` | 4th-order Butterworth HP 300 Hz, LP 8 kHz, mono sum |
| `mono` | L+R fold-down |

Features: `vir_phone`, `csi_phone`, `vir_mono`, `csi_mono`, stored as deltas from the full-range value as well.

---

## 4. Comparison Logic

**Envelopes.** Per style and feature (per band for vector features): median, p10, p90, IQR, n. Cached in the DB and rebuilt by `mixlens ref build-envelopes`.

**Deviation.** Robust z: `z = (x − median) / (IQR / 1.349)`.

| Level | Condition |
|---|---|
| `ok` | inside p10 to p90 |
| `watch` | 1.5 < \|z\| ≤ 2.5 |
| `flag` | \|z\| > 2.5 |

With 12 to 20 references, treat `watch` as a hint.

**Hint rules** (feature, direction, message), stored in `config.yaml`:

| Trigger | Hint |
|---|---|
| `csi` low | Consonants masked. Check the inst 2 to 5 kHz under the vocal, and `csi_wash_drop_true` |
| `vir_med` high | Vocal sits more forward than your references |
| `space_contrast` low | Vocal and instrumental share the same space. Dry the instrumental or push more vocal reverb |
| `vox_tail_level` high + `csi` low | Vocal reverb burying the words. Add ducking or pre-delay before cutting the reverb level |
| `air_ratio` low | Top end duller than references. Try a high shelf on the mix bus or brighter vocal/synth sources |
| `hf_density` high | Top end peaky rather than dense. More saturation or upward compression (OTT) on bright elements |
| `hf_flatness` high + `vox_sib` high | Top end fizzy or harsh rather than polished. Check stacked distortion and de-essing |
| `vox_tail_bright` low | Tail darker than references. Raise reverb high cut or add a high shelf on the aux |
| `duck_depth_true` ≤ 0 | Reverb isn't ducking under the dry vocal. Add sidechain compression on the aux keyed from the dry vocal |
| `vox_sib` high | Sibilance above references. Check de-essing before bright reverb sends |
| `csi_phone` drop > 0.15 | Blend collapses on small speakers |

**Regret analysis.** Requires at least 5 labeled mixes each for `held_up` and `regret`. For each feature, compare z-scores between groups with Cliff's delta, rank by |δ|, and show direction. Also report your **signature**: features where 75%+ of your mixes deviate in the same direction, which point to a consistent habit. Skip p-values; the sample is too small.

---

## 5. Database (SQLite, long format)

```sql
CREATE TABLE songs    (song_id TEXT PRIMARY KEY, style TEXT, bpm REAL);
CREATE TABLE versions (version_id INTEGER PRIMARY KEY, song_id TEXT, version TEXT,
                       analyzed_at TEXT, stem_hash TEXT, UNIQUE(song_id, version));
CREATE TABLE refs     (ref_id INTEGER PRIMARY KEY, path TEXT UNIQUE, style TEXT,
                       artist TEXT, title TEXT, audio_hash TEXT, note TEXT);
CREATE TABLE features (entity TEXT CHECK(entity IN ('version','ref')), entity_id INTEGER,
                       feature TEXT, band TEXT, value REAL,
                       PRIMARY KEY(entity, entity_id, feature, band));
CREATE TABLE checks   (version_id INTEGER, check_name TEXT, level TEXT,
                       value REAL, t_sec REAL, bar REAL, stem TEXT);
CREATE TABLE envelopes(style TEXT, feature TEXT, band TEXT, med REAL, p10 REAL,
                       p90 REAL, iqr REAL, n INTEGER, PRIMARY KEY(style, feature, band));
CREATE TABLE labels   (version_id INTEGER PRIMARY KEY, rating TEXT
                       CHECK(rating IN ('held_up','neutral','regret')),
                       tag TEXT, note TEXT, labeled_at TEXT);
```

`band` is `''` for scalar features. New features need no migration.

---

## 6. Project Layout

```
mixlens/
├── pyproject.toml
├── config.yaml                  # thresholds, band edges, frame sizes, hint rules
├── src/mixlens/
│   ├── config.py                # load + validate config -> Config dataclass
│   ├── pipeline.py              # analyze_version(), analyze_reference()
│   ├── cli.py                   # typer entry point
│   ├── io/
│   │   ├── loader.py            # load_wav, resample, length/alignment checks
│   │   ├── stems.py             # filename parsing -> StemSet
│   │   ├── sidecar.py           # song.yaml / references.yaml parsing
│   │   └── separate.py          # demucs wrapper, cached by audio hash
│   ├── dsp/
│   │   ├── bands.py             # 1/3-oct + ERB edges, band energy from STFT
│   │   ├── loudness.py          # momentary/short-term/integrated, LRA, true peak
│   │   ├── segments.py          # active frames, onsets, phrase ends
│   │   └── sims.py              # phone + mono
│   ├── checks/
│   │   └── peaks.py             # clip_runs, true_peak, isp_overs, headroom, codec, flat_top
│   ├── features/
│   │   ├── tonal.py             # ltas
│   │   ├── dynamics.py          # lufs_i, lra, plr, crest
│   │   ├── stereo.py
│   │   ├── vocal.py             # vir, consistency, harsh, sib
│   │   ├── masking.py           # csi, mask groups
│   │   ├── space.py             # vocal tails, inst decay, space contrast, attack
│   │   ├── sheen.py             # air/presence ratios, hf density/flatness, air width
│   │   ├── wetdry.py            # wet_dry, wash_drop, duck_depth, predelay, wet_bright
│   │   ├── translation.py
│   │   └── registry.py          # runs extractors -> list[FeatureRow]
│   ├── compare/
│   │   ├── envelope.py          # build/load envelopes, leave-one-out audit
│   │   ├── deviation.py         # robust z, levels, hint matching
│   │   └── regret.py            # cliff's delta ranking, signature
│   └── db/
│       ├── schema.sql
│       └── repo.py              # insert/query helpers returning DataFrames
├── ui/
│   ├── app.py                   # streamlit entry
│   ├── pages/
│   │   ├── compare.py
│   │   ├── history.py
│   │   ├── references.py
│   │   └── regret.py
│   └── plots.py                 # plotly figures
├── references/
│   ├── references.yaml
│   └── {dream,hyperpop,electroclash}/
├── mixes/{song}/                # stems + song.yaml
└── tests/
    ├── test_loudness.py         # vs pyloudnorm and known tones
    ├── test_peaks.py            # synthetic clipped sine, inter-sample over
    ├── test_csi.py              # clicks over noise at known SNRs
    ├── test_space.py            # dry burst + synthetic exponential tail
    ├── test_sheen.py            # shaped noise with known band ratios
    └── test_bands.py
```

Keep every module under 500 lines; split by feature family if one grows past that.

### Core types

```python
@dataclass(frozen=True)
class StemSet:
    song: str; version: str; sr: int
    mix: np.ndarray; vox_dry: np.ndarray; vox_wet: np.ndarray; inst: np.ndarray

@dataclass(frozen=True)
class FeatureRow:
    feature: str; value: float; band: str = ""

@dataclass(frozen=True)
class CheckResult:
    check: str; level: str; value: float; t_sec: float | None; stem: str

Extractor = Callable[[np.ndarray, np.ndarray, int, Config], list[FeatureRow]]
```

The registry runs each extractor on the Demucs pair and on the true-stem pair, suffixing true-stem output with `_true`. Wet/dry extractors take the full `StemSet` and run only on the internal path.

---

## 7. CLI and UI

```
mixlens ref add references/dream/*.flac --style dream
mixlens ref build-envelopes
mixlens ref audit                             # leave-one-out outliers
mixlens check mixes/neon_altar --version v3   # peak safety only, fast
mixlens analyze mixes/neon_altar --version v3 # checks + all features
mixlens report neon_altar v3                  # safety table, flag table, hints
mixlens diff neon_altar v2 v3
mixlens label neon_altar v1 regret --tag buried --note "hook vocal vanished"
mixlens regret
mixlens ui
```

UI pages:

| Page | Contents |
|---|---|
| Compare | Peak-safety banner; LTAS vs style p10 to p90 band; flag table with hints; CSI timeline with section shading; space vs sheen scatter (`space_contrast` vs `air_ratio`, yours vs refs) |
| History | `vir_med`, `csi`, `space_contrast`, `air_ratio`, `true_peak` across versions |
| References | Per-style list, leave-one-out results, feature distributions |
| Regret | Effect-size bars, signature list, labeling form |

---

## 8. Build Order

| Milestone | Scope | Done when |
|---|---|---|
| M1 | Loader, loudness, **peak safety checks**, tonal, dynamics, envelopes, text report | A synthetic clipped file fails; a reference scored against its own style mostly shows `ok` |
| M2 | Demucs caching, segments, vocal features, CSI, masking | Synthetic CSI test passes; CSI timeline agrees with your ears on 3 songs |
| M3 | Space and sheen features, leave-one-out audit | Synthetic tail test recovers decay within 10%; shaped-noise test recovers band ratios within 0.5 dB |
| M4 | Database, versions, `diff`, `check` command | Unchanged stems skip re-analysis via hash |
| M5 | Wet/dry internal features, translation | Raising a reverb send 6 dB raises `csi_wash_drop_true`; adding aux sidechain raises `duck_depth_true` |
| M6 | Streamlit UI | All four pages render from the DB |
| M7 | Labels and regret analysis | Runs once 10+ mixes are labeled |

**Dependencies:** `numpy scipy librosa soundfile pyloudnorm demucs torch pandas pyyaml typer streamlit plotly` (plus `ffmpeg` on PATH for the optional codec check).

---

## 9. Calibration

Four thresholds are educated guesses: the 6 dB CSI margin, the 30 LU active threshold, the 15 dB phrase-end drop, and the 80th-percentile strong-onset cut. Before trusting flags:

1. Pick 3 of your songs where you already know which sections feel buried or smeared.
2. Run M2/M3 and look at the CSI timeline and tail metrics.
3. Adjust the thresholds in `config.yaml` until the flagged sections match what you hear.
4. Freeze the config and record its hash in each analysis, so version comparisons stay valid.

---

## Addendum: Micro-dynamics

### Whole mix

| Feature | Definition | Catches |
|---|---|---|
| `st_crest` | Median crest factor in 50ms windows | Micro-dynamics flattened. PLR misses this when only the limiter is doing the work |
| `transient_ratio` | Level at each strong onset minus level 100-300ms later | Drums and plucks losing their attack |
| `band_crest_{low,mid,high}` | Short-term crest per band | Multiband or OTT squashing one region, for example a lifeless low end under a lively top |
| `pump_depth` | Median dip in the 200Hz-8kHz level in the 50-300ms after each kick onset (<120Hz) | Audible pumping from the bus compressor or sidechain. Your references define how much pumping is intended |

### Vocal

| Feature | Definition | Catches |
|---|---|---|
| `vox_crest` | Short-term crest on the vocal stem | Over-flattened vocal, or an uncontrolled one |
| `vox_floor_true` | Level of `vox_dry` in the gaps between phrases, relative to the phrases | Upward compression like OTT lifting breaths, mouth noise and the noise floor into the gaps. The true stem is needed here, because the Demucs vocal carries reverb in its gaps |

### Hints

- Over-compressed: low `st_crest` with low `transient_ratio` → "Mix flattened below your references. Ease the bus compressor or limiter, or the OTT depth."
- Pumping: high `pump_depth` → "More pumping than your references. Check bus compressor release or sidechain depth."
- Noisy gaps: high `vox_floor_true` → "Vocal gaps lifted. Upward compression is raising breaths and noise, so gate before OTT or reduce its upward amount."
- Under-compressed: high `vox_consistency` with `csi_p10` much lower than `csi` → "Vocal level uneven; quiet words sink below the mix. More compression or level riding."

Implemented in [`src/mixlens/features/microdynamics.py`](src/mixlens/features/microdynamics.py),
wired into the whole-mix/vocal/internal registries in
[`registry.py`](src/mixlens/features/registry.py), with thresholds in
`config.yaml`'s `microdynamics` block and the four hint rules appended to
`hints`.
