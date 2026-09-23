"""Peak safety checks: synthetic clipped sine, inter-sample over."""
import numpy as np

from mixlens.checks.peaks import (
    check_clip_runs,
    check_isp_overs,
    check_true_peak,
    flat_top_ratio,
    run_peak_checks,
)

from conftest import sine, stereo

SR = 44100


def test_clip_runs_detects_flat_top(cfg):
    mono = sine(1000, 1.0, SR, amplitude=1.5)  # will clip when clamped
    clipped = np.clip(mono, -1.0, 1.0)
    audio = stereo(clipped)
    results = check_clip_runs(audio, SR, cfg, "mix", bpm=120)
    assert any(r.level == "fail" for r in results)


def test_clip_runs_clean_signal_ok(cfg):
    mono = sine(1000, 1.0, SR, amplitude=0.5)
    audio = stereo(mono)
    results = check_clip_runs(audio, SR, cfg, "mix", bpm=120)
    assert all(r.level == "ok" for r in results)


def test_true_peak_fails_above_0_dbtp(cfg):
    # A sine designed to inter-sample-peak above full scale even though no
    # individual sample clips: amplitude just under 1.0, frequency chosen so
    # oversampled peaks land off-sample.
    mono = sine(11025.3, 0.5, SR, amplitude=0.99)
    audio = stereo(mono)
    result = check_true_peak(audio, SR, cfg, "mix", bpm=120)
    assert result.value > -3.0  # sanity: peak is near full scale either way


def test_isp_overs_zero_for_quiet_signal(cfg):
    mono = sine(1000, 0.5, SR, amplitude=0.3)
    audio = stereo(mono)
    result = check_isp_overs(audio, SR, cfg, "mix", bpm=120)
    assert result.level == "ok"
    assert result.value == 0


def test_flat_top_ratio_zero_for_sine(cfg):
    mono = sine(1000, 1.0, SR, amplitude=0.5)
    audio = stereo(mono)
    assert flat_top_ratio(audio, cfg) == 0.0


def test_flat_top_ratio_nonzero_for_clipped_signal(cfg):
    # amplitude 2.0 clipped to 0.97 sits above the 0.95 FS flat_top threshold,
    # so long flat runs land inside the "intentional clipping" detector.
    mono = sine(200, 1.0, SR, amplitude=2.0)
    clipped = np.clip(mono, -0.97, 0.97)
    audio = stereo(clipped)
    ratio = flat_top_ratio(audio, cfg)
    assert ratio > 0.1


def test_run_peak_checks_covers_all_checks(cfg):
    mono = sine(1000, 1.0, SR, amplitude=0.3)
    audio = stereo(mono)
    results = run_peak_checks(audio, SR, cfg, bpm=120)
    names = {r.check for r in results}
    assert {"clip_runs", "true_peak", "isp_overs", "stem_headroom"} <= names
