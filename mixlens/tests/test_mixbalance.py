"""Balance features against synthetic stems with known answers."""
import numpy as np

from mixlens.features.mixbalance import extract_mix_balance, present_stems

from conftest import stereo

SR = 44100


def rows(mix, stems, cfg):
    return {(r.feature, r.band): r.value for r in extract_mix_balance(mix, stems, SR, cfg)}


def tone(f, secs=6, amp=0.2):
    t = np.arange(int(secs * SR)) / SR
    return (amp * np.sin(2 * np.pi * f * t)).astype(np.float32)


def noise(secs=6, amp=0.05, seed=0):
    return (amp * np.random.default_rng(seed).standard_normal(int(secs * SR))).astype(np.float32)


def test_louder_element_reads_louder_and_owns_its_frequency_range(cfg):
    stems = {"bass": stereo(tone(90, amp=0.4)), "other": stereo(tone(2000, amp=0.05)), "drums": stereo(noise(amp=0.01))}
    mix = sum(stems.values())
    r = rows(mix, stems, cfg)
    assert r[("stem_level", "bass")] > r[("stem_level", "other")] + 6
    assert r[("band_share", "bass|bass")] > 90 and r[("band_share", "other|mid")] > 60


def test_width_and_brightness_are_measured_per_element(cfg):
    wide = np.stack([noise(seed=1), noise(seed=2)]).astype(np.float32)   # independent L/R: wide
    mono = stereo(noise(seed=3))
    stems = {"other": wide, "drums": mono}
    r = rows(wide + mono, stems, cfg)
    assert r[("stem_width", "other")] > r[("stem_width", "drums")] + 20
    bright = stereo(tone(6000)); dark = stereo(tone(150))
    r2 = rows(bright + dark, {"other": bright, "bass": dark}, cfg)
    assert r2[("stem_centroid", "other")] > r2[("stem_centroid", "bass")] + 3


def test_an_absent_stem_is_ignored(cfg):
    stems = {"drums": stereo(noise(amp=0.1)), "vocals": stereo(np.zeros(SR * 6, dtype=np.float32))}
    assert set(present_stems(stems, SR)) == {"drums"}
    assert not any(b == "vocals" for (_f, b) in rows(stems["drums"], stems, cfg))


def test_masking_is_high_when_elements_share_frequencies_and_low_when_they_dont(cfg):
    a, b = noise(seed=1, amp=0.1), noise(seed=2, amp=0.1)                 # both broadband, same level
    clash = rows(stereo(a + b), {"other": stereo(a), "vocals": stereo(b)}, cfg)
    from scipy.signal import butter, sosfiltfilt
    low = sosfiltfilt(butter(4, 600, "lowpass", fs=SR, output="sos"), noise(seed=1, amp=0.3)).astype(np.float32)
    high = sosfiltfilt(butter(4, 4000, "highpass", fs=SR, output="sos"), noise(seed=2, amp=0.3)).astype(np.float32)
    apart = rows(stereo(low + high), {"other": stereo(low), "vocals": stereo(high)}, cfg)
    assert clash[("masking", "vocals~other|mid")] > 0.4
    assert apart[("masking", "vocals~other|mid")] < clash[("masking", "vocals~other|mid")] - 0.25


def test_kick_and_bass_overlap_depends_on_whether_they_hit_together(cfg):
    n = SR * 8
    def pulses(offset):
        x = np.zeros(n, dtype=np.float32)
        for k in range(offset, n - 4000, SR // 2):
            x[k:k + 4000] = 0.5 * np.sin(2 * np.pi * 60 * np.arange(4000) / SR)
        return x
    together = rows(stereo(pulses(0) + pulses(0)), {"drums": stereo(pulses(0)), "bass": stereo(pulses(0))}, cfg)
    alternate = rows(stereo(pulses(0) + pulses(SR // 4)), {"drums": stereo(pulses(0)), "bass": stereo(pulses(SR // 4))}, cfg)
    assert together[("low_end_overlap", "")] > 0.8 > 0.3 > alternate[("low_end_overlap", "")]


def test_a_static_mix_has_less_motion_than_one_that_changes(cfg):
    static = stereo(noise(secs=10, seed=1))
    t = np.arange(SR * 10) / SR
    changing = static * (0.2 + 0.8 * np.abs(np.sin(2 * np.pi * 0.2 * t))).astype(np.float32)
    s = rows(static, {"other": static}, cfg)
    c = rows(changing, {"other": changing}, cfg)
    assert c[("spectral_motion", "")] >= s[("spectral_motion", "")]
    assert ("width_motion", "") in s
