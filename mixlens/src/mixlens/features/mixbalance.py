"""How the elements of a mix sit together, from a drums / bass / other / vocals split.

Works on any song (including instrumentals) because it needs only the stereo
mix: Demucs separates it. Everything here is relative, so it can be compared
with references measured the same way:

- stem_level      how loud each element is against the whole mix (dB)
- stem_width      stereo width of each element (side vs mid, dB)
- stem_centroid   brightness of each element (octaves above 1 kHz)
- stem_crest      how dynamic each element is (dB)
- band_share      which element owns each frequency range (% of that range's energy)
- kick_bass_ratio / low_end_overlap   whether kick and bass fight for the bottom
- masking         how much two elements pile into the same frequencies at the same time
- width_motion / spectral_motion   whether the stereo image and the tone change over the song
"""
from __future__ import annotations

import numpy as np

from mixlens.config import Config
from mixlens.dsp.loudness import integrated_lufs, windowed_crest_db
from mixlens.io.loader import to_mono
from mixlens.types import FeatureRow

EPS = 1e-12
BANDS = {"sub": (20, 60), "bass": (60, 200), "low-mid": (200, 800), "mid": (800, 3000), "high": (3000, 20000)}
ZONES = {"low-mid": (200, 800), "mid": (800, 3000), "presence": (3000, 6000)}
PAIRS = [("vocals", "other"), ("other", "drums"), ("bass", "other"), ("vocals", "drums")]
ABSENT_LUFS = -55.0       # a stem quieter than this is treated as not present


def _stft_power(mono: np.ndarray, sr: int, n_fft: int = 2048, hop: int = 1024) -> tuple[np.ndarray, np.ndarray]:
    import librosa

    S = librosa.stft(mono.astype(np.float32), n_fft=n_fft, hop_length=hop, window="hann")
    return librosa.fft_frequencies(sr=sr, n_fft=n_fft), (np.abs(S) ** 2).T      # (bins,), (frames, bins)


def _db(x) -> np.ndarray:
    return 10.0 * np.log10(np.maximum(x, EPS))


def _width_db(audio: np.ndarray) -> float:
    if audio.shape[0] < 2:
        return -60.0
    mid, side = (audio[0] + audio[1]) / 2.0, (audio[0] - audio[1]) / 2.0
    return float(max(_db(np.mean(side ** 2)) - _db(np.mean(mid ** 2)), -60.0))


def present_stems(stems: dict[str, np.ndarray], sr: int) -> dict[str, np.ndarray]:
    """Drop stems with essentially no signal (e.g. vocals of an instrumental)."""
    return {k: v for k, v in stems.items() if integrated_lufs(v, sr) > ABSENT_LUFS}


def extract_mix_balance(mix: np.ndarray, stems: dict[str, np.ndarray], sr: int, cfg: Config) -> list[FeatureRow]:
    stems = present_stems(stems, sr)
    rows: list[FeatureRow] = []
    if not stems:
        return rows
    mix_lufs = integrated_lufs(mix, sr)

    power: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for name, audio in stems.items():
        freqs, P = _stft_power(to_mono(audio), sr)
        power[name] = (freqs, P)
        mono = to_mono(audio)
        avg = P.mean(axis=0)
        centroid = float((freqs * avg).sum() / max(avg.sum(), EPS))
        rows += [
            FeatureRow("stem_level", float(integrated_lufs(audio, sr) - mix_lufs), name),
            FeatureRow("stem_width", _width_db(audio), name),
            FeatureRow("stem_centroid", float(np.log2(max(centroid, 20.0) / 1000.0)), name),
            FeatureRow("stem_crest", windowed_crest_db(mono, sr, 50.0), name),
        ]

    # who owns each frequency range
    freqs = next(iter(power.values()))[0]
    for band, (lo, hi) in BANDS.items():
        m = (freqs >= lo) & (freqs < hi)
        energy = {n: float(P[:, m].sum()) for n, (_f, P) in power.items()}
        total = sum(energy.values()) or EPS
        rows += [FeatureRow("band_share", 100.0 * e / total, f"{n}|{band}") for n, e in energy.items()]

    rows += _low_end(stems, power, sr)
    rows += _masking(power)
    rows += _motion(mix, sr)
    return rows


def _low_end(stems, power, sr) -> list[FeatureRow]:
    if "drums" not in stems or "bass" not in stems:
        return []
    from scipy.signal import butter, sosfiltfilt

    freqs = power["drums"][0]
    band = (freqs >= 30) & (freqs < 100)
    d = _db(power["drums"][1][:, band].sum()) 
    b = _db(power["bass"][1][:, band].sum())
    sos = butter(4, [30, 120], btype="bandpass", fs=sr, output="sos")
    hop = int(0.05 * sr)

    def env(x):
        y = sosfiltfilt(sos, to_mono(x))
        n = len(y) // hop
        return np.sqrt((y[: n * hop].reshape(n, hop) ** 2).mean(axis=1) + EPS)

    ed, eb = env(stems["drums"]), env(stems["bass"])
    n = min(len(ed), len(eb))
    a, c = ed[:n] > np.percentile(ed[:n], 60), eb[:n] > np.percentile(eb[:n], 60)
    union = (a | c).sum()
    return [
        FeatureRow("kick_bass_ratio", float(d - b)),
        FeatureRow("low_end_overlap", float((a & c).sum() / union) if union else 0.0),
    ]


def _masking(power) -> list[FeatureRow]:
    """Share of time-frequency cells, in each zone, where both elements are active
    and within 6 dB of each other: the cells where they are likely to mask each other."""
    rows: list[FeatureRow] = []
    for a, b in PAIRS:
        if a not in power or b not in power:
            continue
        freqs, Pa = power[a]
        _f, Pb = power[b]
        n = min(len(Pa), len(Pb))
        da, db = _db(Pa[:n]), _db(Pb[:n])
        act_a, act_b = da > da.max() - 35.0, db > db.max() - 35.0
        for zone, (lo, hi) in ZONES.items():
            m = (freqs >= lo) & (freqs < hi)
            both = act_a[:, m] & act_b[:, m] & (np.abs(da[:, m] - db[:, m]) < 6.0)
            either = act_a[:, m] | act_b[:, m]
            if either.sum():
                rows.append(FeatureRow("masking", float(both.sum() / either.sum()), f"{a}~{b}|{zone}"))
    return rows


def _motion(mix: np.ndarray, sr: int) -> list[FeatureRow]:
    """Does the stereo image, and the tone, change over the song? Static is 'flat'."""
    mono = to_mono(mix)
    freqs, P = _stft_power(mono, sr)
    frames_per_s = max(1, int(sr / 1024))
    n = (len(P) // frames_per_s) * frames_per_s
    rows: list[FeatureRow] = []
    if n < frames_per_s * 3:
        return rows
    groups = P[:n].reshape(-1, frames_per_s, P.shape[1]).sum(axis=1)            # one row per second
    edges = [(20, 120), (120, 400), (400, 1500), (1500, 5000), (5000, 16000)]
    bands = np.stack([groups[:, (freqs >= lo) & (freqs < hi)].sum(axis=1) for lo, hi in edges], axis=1)
    rows.append(FeatureRow("spectral_motion", float(np.mean(np.std(_db(bands), axis=0)))))

    if mix.shape[0] >= 2:
        _f, Pm = _stft_power((mix[0] + mix[1]) / 2.0, sr)
        _f, Ps = _stft_power((mix[0] - mix[1]) / 2.0, sr)
        hi = freqs >= 2000
        m = Pm[:n][:, hi].reshape(-1, frames_per_s, hi.sum()).sum(axis=(1, 2))
        s = Ps[:n][:, hi].reshape(-1, frames_per_s, hi.sum()).sum(axis=(1, 2))
        rows.append(FeatureRow("width_motion", float(np.std(_db(s) - _db(m)))))
    return rows
