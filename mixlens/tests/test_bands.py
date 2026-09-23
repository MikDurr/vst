"""1/3-octave and ERB band edge math."""
import numpy as np

from mixlens.dsp.bands import band_energy, energy_to_db, erb_band_edges, third_octave_edges


def test_third_octave_edges_cover_range():
    edges = third_octave_edges(31.5, 16000.0)
    assert edges[0][1] < 40  # first center near 31.5
    assert edges[-1][1] > 10000  # last center near the top
    # centers should be monotonically increasing
    centers = [c for _lo, c, _hi in edges]
    assert centers == sorted(centers)


def test_third_octave_edges_no_gaps():
    edges = third_octave_edges(100.0, 1000.0)
    for i in range(len(edges) - 1):
        assert abs(edges[i][2] - edges[i + 1][0]) < 1.0  # adjacent bands touch


def test_erb_band_edges_count_and_monotonic():
    bands = erb_band_edges(2000.0, 6000.0, 4)
    assert len(bands) == 4
    assert abs(bands[0][0] - 2000.0) < 1e-6
    assert abs(bands[-1][1] - 6000.0) < 1e-6
    for lo, hi in bands:
        assert hi > lo


def test_band_energy_isolates_target_band():
    freqs = np.linspace(0, 20000, 2000)
    power = np.zeros((1, 2000))
    # put all energy in a bin near 1000 Hz
    idx = np.argmin(np.abs(freqs - 1000))
    power[0, idx] = 1.0
    e_in = band_energy(freqs, power, 900, 1100)
    e_out = band_energy(freqs, power, 5000, 6000)
    assert e_in[0] > 0
    assert e_out[0] == 0


def test_energy_to_db_monotonic():
    vals = energy_to_db(np.array([0.001, 0.01, 0.1, 1.0]))
    assert np.all(np.diff(vals) > 0)
