"""ltas: 1/3-octave long-term average spectrum (whole mix)."""
from __future__ import annotations

import numpy as np

from mixlens.config import Config
from mixlens.dsp.bands import band_energy, energy_to_db, stft_mag, third_octave_edges
from mixlens.io.loader import to_mono
from mixlens.types import FeatureRow


def extract_ltas(mix: np.ndarray, sr: int, cfg: Config) -> list[FeatureRow]:
    """28-band 1/3-octave LTAS, 31.5 Hz-16 kHz, offset so 250 Hz-4 kHz mean = 0."""
    n_fft = cfg.get("stft.tonal.n_fft", 4096)
    hop = cfg.get("stft.tonal.hop", 1024)
    low = cfg.get("ltas.low_hz", 31.5)
    high = cfg.get("ltas.high_hz", 16000.0)
    ref_low = cfg.get("ltas.ref_low_hz", 250.0)
    ref_high = cfg.get("ltas.ref_high_hz", 4000.0)

    mono = to_mono(mix)
    freqs, mag = stft_mag(mono, sr, n_fft, hop)
    power = (mag ** 2).mean(axis=0, keepdims=True)  # time-averaged power spectrum, shape (1, bins)

    edges = third_octave_edges(low, high)
    band_db = []
    for lo, _fc, hi in edges:
        e = band_energy(freqs, power, lo, hi)[0]
        band_db.append(10.0 * np.log10(max(e, 1e-12)))
    band_db = np.array(band_db)

    ref_e = band_energy(freqs, power, ref_low, ref_high)[0]
    # Reference offset computed directly over the ref range rather than by
    # averaging already-quantized band_db, to avoid double log-averaging bias.
    ref_offset = 10.0 * np.log10(max(ref_e, 1e-12)) - 10.0 * np.log10(max(ref_high - ref_low, 1e-9))
    band_width_db_mean = np.mean(
        [10.0 * np.log10(max(band_energy(freqs, power, lo, hi)[0] / max(hi - lo, 1e-9), 1e-12)) for lo, _fc, hi in edges if ref_low <= _fc <= ref_high]
    ) if any(ref_low <= fc <= ref_high for _lo, fc, _hi in edges) else ref_offset

    offset = band_width_db_mean
    rows = []
    for (lo, fc, hi), db in zip(edges, band_db):
        rows.append(FeatureRow(feature="ltas", value=float(db - offset), band=f"{fc:.1f}Hz"))
    return rows
