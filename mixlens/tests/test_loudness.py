"""Loudness features vs pyloudnorm directly and known tones."""
import numpy as np
import pyloudnorm as pyln

from mixlens.dsp.loudness import crest_factor_db, integrated_lufs, true_peak_dbtp

from conftest import sine, stereo

SR = 44100


def test_integrated_lufs_matches_pyloudnorm_directly():
    mono = sine(1000, 3.0, SR, amplitude=0.3)
    audio = stereo(mono)
    ours = integrated_lufs(audio, SR)

    meter = pyln.Meter(SR)
    reference = meter.integrated_loudness(audio.T)

    assert abs(ours - reference) < 0.01


def test_true_peak_full_scale_sine_near_zero_dbtp():
    mono = sine(1000, 1.0, SR, amplitude=0.999)
    audio = stereo(mono)
    dbtp, _up = true_peak_dbtp(audio)
    assert -0.5 < dbtp < 0.5


def test_true_peak_half_scale_near_minus_6_dbtp():
    mono = sine(1000, 1.0, SR, amplitude=0.5)
    audio = stereo(mono)
    dbtp, _up = true_peak_dbtp(audio)
    assert -6.5 < dbtp < -5.5


def test_crest_factor_of_pure_sine_near_3db():
    mono = sine(1000, 1.0, SR, amplitude=0.5)
    audio = stereo(mono)
    crest = crest_factor_db(audio)
    assert 2.5 < crest < 3.5


def test_quieter_signal_has_lower_integrated_lufs():
    loud = stereo(sine(1000, 2.0, SR, amplitude=0.5))
    quiet = stereo(sine(1000, 2.0, SR, amplitude=0.05))
    assert integrated_lufs(quiet, SR) < integrated_lufs(loud, SR)
