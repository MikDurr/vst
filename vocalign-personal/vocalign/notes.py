"""Note-name and cents helpers built around 12-TET (A4 = 440 Hz)."""

from __future__ import annotations

import math
import re
from typing import Optional

import numpy as np

A4_HZ = 440.0
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_NOTE_NAME_RE = re.compile(r"^([A-Ga-g])(#|b)?(-?\d+)$")
_FLAT_TO_SHARP = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}


def hz_to_midi(freq_hz: float) -> float:
    """Continuous MIDI number for a frequency (69.0 == A4 == 440 Hz)."""
    return 69.0 + 12.0 * math.log2(freq_hz / A4_HZ)


def midi_to_note_name(midi: int) -> str:
    """Nearest-integer MIDI -> scientific pitch name, e.g. 69 -> 'A4'."""
    midi = int(round(midi))
    name = NOTE_NAMES[midi % 12]
    octave = midi // 12 - 1
    return f"{name}{octave}"


def note_name_to_midi(name: str) -> int:
    """Scientific pitch name -> integer MIDI, e.g. 'A4' -> 69 (inverse of
    `midi_to_note_name`). Accepts sharps or flats, case-insensitive letter."""
    m = _NOTE_NAME_RE.match(name.strip())
    if not m:
        raise ValueError(f"Not a note name: {name!r}")
    letter, accidental, octave = m.group(1).upper(), m.group(2) or "", int(m.group(3))
    pitch = letter + accidental
    pitch = _FLAT_TO_SHARP.get(pitch, pitch)
    return (octave + 1) * 12 + NOTE_NAMES.index(pitch)


def hz_to_note_name(freq_hz: float) -> Optional[str]:
    """Frequency -> nearest note name, or None for NaN/invalid input."""
    if freq_hz is None or not np.isfinite(freq_hz) or freq_hz <= 0:
        return None
    return midi_to_note_name(round(hz_to_midi(freq_hz)))


def hz_array_to_cents_off(freq_hz: np.ndarray) -> np.ndarray:
    """Vectorized signed cents-from-nearest-note; NaN stays NaN."""
    freq = np.asarray(freq_hz, dtype=float)
    out = np.full(freq.shape, np.nan)
    mask = np.isfinite(freq) & (freq > 0)
    midi = 69.0 + 12.0 * np.log2(freq[mask] / A4_HZ)
    out[mask] = (midi - np.round(midi)) * 100.0
    return out
