"""Active-frame detection, onset detection, and phrase-end heuristics."""
from __future__ import annotations

import numpy as np

from mixlens.dsp.loudness import momentary_lufs_series


def active_mask(vocal_audio: np.ndarray, sr: int, threshold_lu: float, hop_s: float = 0.1) -> tuple[np.ndarray, np.ndarray]:
    """A vocal frame is active when within `threshold_lu` LU of the vocal's max momentary loudness."""
    times, lufs = momentary_lufs_series(vocal_audio, sr, hop_s=hop_s)
    finite = lufs[np.isfinite(lufs)]
    if len(finite) == 0:
        return times, np.zeros_like(lufs, dtype=bool)
    peak = np.max(finite)
    mask = lufs >= (peak - threshold_lu)
    return times, mask


def detect_onsets(audio_mono: np.ndarray, sr: int, hop: int = 256) -> np.ndarray:
    """Onset times (seconds) via librosa.onset.onset_detect."""
    import librosa

    onset_frames = librosa.onset.onset_detect(
        y=audio_mono.astype(np.float32), sr=sr, hop_length=hop, units="frames", backtrack=False
    )
    return librosa.frames_to_time(onset_frames, sr=sr, hop_length=hop)


def onset_strength_envelope(audio_mono: np.ndarray, sr: int, hop: int = 256) -> tuple[np.ndarray, np.ndarray]:
    import librosa

    env = librosa.onset.onset_strength(y=audio_mono.astype(np.float32), sr=sr, hop_length=hop)
    times = librosa.frames_to_time(np.arange(len(env)), sr=sr, hop_length=hop)
    return times, env


def strong_onsets(audio_mono: np.ndarray, sr: int, percentile: float, hop: int = 256) -> np.ndarray:
    """Onset times whose onset-strength peak exceeds the given percentile."""
    import librosa

    times, env = onset_strength_envelope(audio_mono, sr, hop=hop)
    onset_frames = librosa.onset.onset_detect(
        onset_envelope=env, sr=sr, hop_length=hop, units="frames", backtrack=False
    )
    if len(onset_frames) == 0:
        return np.array([])
    thresh = np.percentile(env, percentile)
    strong = [f for f in onset_frames if env[f] >= thresh]
    return librosa.frames_to_time(np.array(strong, dtype=int), sr=sr, hop_length=hop)


def envelope_db(audio_mono: np.ndarray, sr: int, hop_s: float = 0.005, win_s: float = 0.02) -> tuple[np.ndarray, np.ndarray]:
    """Simple RMS envelope in dBFS, for tail-decay and attack measurement."""
    hop = max(1, int(round(hop_s * sr)))
    win = max(hop, int(round(win_s * sr)))
    n = len(audio_mono)
    if n < win:
        return np.array([0.0]), np.array([-100.0])
    starts = np.arange(0, n - win + 1, hop)
    times = (starts + win / 2) / sr
    vals = np.empty(len(starts))
    for i, s in enumerate(starts):
        block = audio_mono[s : s + win]
        rms = np.sqrt(np.mean(block ** 2) + 1e-12)
        vals[i] = 20.0 * np.log10(max(rms, 1e-6))
    return times, vals


def find_phrase_ends(
    vocal_mono: np.ndarray,
    sr: int,
    active_times: np.ndarray,
    active_mask_arr: np.ndarray,
    drop_db: float,
    window_ms: float,
    active_min_ms: float,
) -> list[float]:
    """Frames where the vocal level drops > drop_db within window_ms after an
    active stretch of at least active_min_ms. Returns phrase-end times (s).

    `active_mask_arr` (400ms momentary loudness, per spec section 3) lags a
    fast level drop by up to its own window length, so its own stretch
    boundary is a poor estimate of *where* the drop happens -- by the time it
    flags "inactive" the fast envelope may already be silent. It's only used
    here to gate *whether* a stretch is long enough to count as a phrase; the
    actual drop point is found by scanning the fine envelope itself, from the
    start of each qualifying stretch through a short tolerance window past
    its coarse boundary.
    """
    env_t, env_db = envelope_db(vocal_mono, sr, hop_s=0.01, win_s=0.05)
    if len(env_t) < 2:
        return []

    active_interp = np.interp(env_t, active_times, active_mask_arr.astype(float)) >= 0.5

    dt = env_t[1] - env_t[0]
    min_len_frames = max(1, int(active_min_ms / 1000.0 / dt))
    window_frames = max(1, int(window_ms / 1000.0 / dt))
    tolerance_frames = max(1, int(0.3 / dt))

    phrase_ends: list[float] = []
    i = 0
    n = len(env_t)
    while i < n:
        if active_interp[i]:
            j = i
            while j < n and active_interp[j]:
                j += 1
            stretch_len = j - i
            if stretch_len >= min_len_frames:
                search_end = min(j + tolerance_frames, n)
                for k in range(i, search_end):
                    look_end = min(k + window_frames, n - 1)
                    if look_end <= k:
                        continue
                    min_after = np.min(env_db[k : look_end + 1])
                    if env_db[k] - min_after > drop_db:
                        phrase_ends.append(float(env_t[k]))
                        break
            i = j
        else:
            i += 1
    return phrase_ends
