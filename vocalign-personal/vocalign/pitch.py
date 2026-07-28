"""Core pitch extraction: librosa.pyin -> reusable reference-curve JSON."""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional

import numpy as np

from .audio import DEFAULT_SR, load_audio
from .notes import hz_to_note_name

# Default vocal range. A1 (~55 Hz) to C5 (~523 Hz) covers most singing voices.
DEFAULT_FMIN_NOTE = "A1"
DEFAULT_FMAX_NOTE = "C5"


@dataclass
class PitchCurve:
    """Reusable reference-curve schema, identical for voice or reference song."""

    source: str
    sr: int
    frame_length: int
    hop_length: int
    fmin_hz: float
    fmax_hz: float
    times: List[float]
    freq_hz: List[Optional[float]]      # None where unvoiced
    voiced_flag: List[bool]
    voiced_prob: List[float]
    note_names: List[Optional[str]]     # None where unvoiced

    def to_json(self, path: str | Path, indent: int = 2) -> Path:
        path = Path(path)
        path.write_text(json.dumps(asdict(self), indent=indent))
        return path

    @property
    def freq_array(self) -> np.ndarray:
        """freq_hz as a float array with NaN for unvoiced frames."""
        return np.array(
            [f if f is not None else np.nan for f in self.freq_hz], dtype=float
        )

    @classmethod
    def from_json(cls, path: str | Path) -> "PitchCurve":
        data = json.loads(Path(path).read_text())
        return cls(**data)


def extract_pitch(
    input_path: str | Path,
    sr: int = DEFAULT_SR,
    fmin_note: str = DEFAULT_FMIN_NOTE,
    fmax_note: str = DEFAULT_FMAX_NOTE,
    frame_length: int = 2048,
    hop_length: int = 256,
) -> PitchCurve:
    """Extract an F0 curve from an audio/video file using probabilistic YIN.

    Returns a PitchCurve whose JSON schema is the shared "reference curve"
    format used for both the singer's own takes and reference songs.
    """
    y, sr = load_audio(input_path, sr=sr)
    return extract_pitch_from_samples(
        y, sr, source=str(Path(input_path)),
        fmin_note=fmin_note, fmax_note=fmax_note,
        frame_length=frame_length, hop_length=hop_length,
    )


def _correct_octave_jumps(f0: np.ndarray) -> np.ndarray:
    """Snap octave-error frames onto the melody line.

    pyin (especially on isolated/mixed vocals) occasionally jumps an octave for
    a few frames, showing as vertical spikes on the plot. We build a robust
    median reference of the contour and shift any frame that sits ~a whole
    number of octaves away back onto it — leaving normal pitch motion untouched.
    """
    out = np.array(f0, dtype=float)
    voiced = np.isfinite(out)
    if voiced.sum() < 8:
        return out
    from scipy.ndimage import median_filter

    idx = np.arange(len(out))
    logf = np.log2(np.where(voiced, out, np.nan))
    # Continuous reference: interpolate over gaps, then median-filter (~150 ms).
    ref = median_filter(np.interp(idx, idx[voiced], logf[voiced]),
                        size=11, mode="nearest")
    k = np.round(ref - logf)                      # octaves each frame is off by
    fix = voiced & (np.abs(k) >= 1)
    out[fix] = out[fix] * (2.0 ** k[fix])
    return out


def extract_pitch_from_samples(
    y: np.ndarray,
    sr: int,
    source: str = "(array)",
    fmin_note: str = DEFAULT_FMIN_NOTE,
    fmax_note: str = DEFAULT_FMAX_NOTE,
    frame_length: int = 2048,
    hop_length: int = 256,
) -> PitchCurve:
    """Same as extract_pitch but on an in-memory mono waveform. Used for live
    mic clips and synthesized tones that never touch disk."""
    import librosa

    y = np.asarray(y, dtype=float)
    fmin = librosa.note_to_hz(fmin_note)
    fmax = librosa.note_to_hz(fmax_note)

    f0, voiced_flag, voiced_prob = librosa.pyin(
        y, fmin=fmin, fmax=fmax, sr=sr,
        frame_length=frame_length, hop_length=hop_length,
    )
    f0 = _correct_octave_jumps(f0)   # snap octave-error spikes to the melody line
    times = librosa.times_like(f0, sr=sr, hop_length=hop_length)

    freq_list: List[Optional[float]] = []
    note_list: List[Optional[str]] = []
    for f in f0:
        if f is None or not np.isfinite(f):
            freq_list.append(None)
            note_list.append(None)
        else:
            freq_list.append(round(float(f), 4))
            note_list.append(hz_to_note_name(float(f)))

    return PitchCurve(
        source=source,
        sr=int(sr),
        frame_length=int(frame_length),
        hop_length=int(hop_length),
        fmin_hz=round(float(fmin), 4),
        fmax_hz=round(float(fmax), 4),
        times=[round(float(t), 5) for t in times],
        freq_hz=freq_list,
        voiced_flag=[bool(v) for v in voiced_flag],
        voiced_prob=[round(float(p), 4) for p in voiced_prob],
        note_names=note_list,
    )
