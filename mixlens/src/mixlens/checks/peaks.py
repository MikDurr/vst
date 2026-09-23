"""Peak safety checks (spec section 2): pass/fail, run first, envelopes don't apply."""
from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from mixlens.config import Config
from mixlens.dsp.loudness import true_peak_dbtp
from mixlens.io.sidecar import bar_from_seconds

EPS = 1e-12


@dataclass(frozen=True)
class CheckResult:
    check: str
    level: str  # "ok" | "warn" | "fail"
    value: float
    t_sec: float | None
    bar: float | None
    stem: str


def _runs_at_or_above(x: np.ndarray, threshold: float, min_run: int) -> list[tuple[int, int]]:
    """Contiguous index ranges [start, end) where |x| >= threshold, length >= min_run."""
    above = np.abs(x) >= threshold
    runs = []
    i = 0
    n = len(above)
    while i < n:
        if above[i]:
            j = i
            while j < n and above[j]:
                j += 1
            if j - i >= min_run:
                runs.append((i, j))
            i = j
        else:
            i += 1
    return runs


def check_clip_runs(audio: np.ndarray, sr: int, cfg: Config, stem: str, bpm: float) -> list[CheckResult]:
    threshold = cfg.get("peaks.clip_threshold_fs", 0.999)
    min_run = cfg.get("peaks.clip_run_samples", 3)
    results = []
    for ch_idx, ch in enumerate(audio):
        runs = _runs_at_or_above(ch, threshold, min_run)
        for start, _end in runs:
            t = start / sr
            results.append(
                CheckResult("clip_runs", "fail", float(np.abs(ch[start])), t, bar_from_seconds(t, bpm), f"{stem}[ch{ch_idx}]")
            )
    if not results:
        results.append(CheckResult("clip_runs", "ok", 0.0, None, None, stem))
    return results


def check_true_peak(audio: np.ndarray, sr: int, cfg: Config, stem: str, bpm: float) -> CheckResult:
    oversample = cfg.get("peaks.oversample_factor", 4)
    fail_dbtp = cfg.get("peaks.true_peak_fail_dbtp", 0.0)
    warn_dbtp = cfg.get("peaks.true_peak_warn_dbtp", -1.0)
    dbtp, _up = true_peak_dbtp(audio, oversample=oversample)
    level = "ok"
    if dbtp > fail_dbtp:
        level = "fail"
    elif dbtp > warn_dbtp:
        level = "warn"
    return CheckResult("true_peak", level, dbtp, None, None, stem)


def check_isp_overs(audio: np.ndarray, sr: int, cfg: Config, stem: str, bpm: float) -> CheckResult:
    oversample = cfg.get("peaks.oversample_factor", 4)
    _dbtp, up = true_peak_dbtp(audio, oversample=oversample)
    count = int(np.sum(np.abs(up) > 1.0))  # > 0 dBTP == amplitude > 1.0 FS
    level = "fail" if count > 0 else "ok"
    return CheckResult("isp_overs", level, float(count), None, None, stem)


def check_stem_headroom(audio: np.ndarray, sr: int, cfg: Config, stem: str, bpm: float) -> CheckResult:
    warn_dbfs = cfg.get("peaks.stem_headroom_warn_dbfs", -0.3)
    peak = np.max(np.abs(audio)) if audio.size else 0.0
    peak_dbfs = float(20.0 * np.log10(max(peak, EPS)))
    level = "warn" if peak_dbfs > warn_dbfs else "ok"
    return CheckResult("stem_headroom", level, peak_dbfs, None, None, stem)


def check_codec_overs(audio: np.ndarray, sr: int, cfg: Config, stem: str, bpm: float) -> CheckResult | None:
    """Optional: encode to AAC via ffmpeg, decode, re-check true peak."""
    if not cfg.get("peaks.codec_check_enabled", False):
        return None
    import shutil

    if shutil.which("ffmpeg") is None:
        return None
    bitrate = cfg.get("peaks.codec_bitrate_kbps", 256)
    with tempfile.TemporaryDirectory() as td:
        wav_path = Path(td) / "in.wav"
        aac_path = Path(td) / "out.m4a"
        dec_path = Path(td) / "dec.wav"
        sf.write(str(wav_path), audio.T, sr)
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(wav_path), "-c:a", "aac", "-b:a", f"{bitrate}k", str(aac_path)],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(aac_path), str(dec_path)],
            check=True, capture_output=True,
        )
        dec_audio, dec_sr = sf.read(str(dec_path), dtype="float32", always_2d=True)
        dec_audio = dec_audio.T
    dbtp, _up = true_peak_dbtp(dec_audio, oversample=cfg.get("peaks.oversample_factor", 4))
    fail_dbtp = cfg.get("peaks.true_peak_fail_dbtp", 0.0)
    level = "warn" if dbtp > fail_dbtp else "ok"
    return CheckResult("codec_overs", level, dbtp, None, None, stem)


def flat_top_ratio(audio: np.ndarray, cfg: Config) -> float:
    """Info-only: fraction of samples inside flat-topped runs below full scale.

    Flags intentional clip-distortion / hard clipping that flattens peaks
    below the file ceiling, which the fail/warn checks above won't catch.
    """
    threshold = cfg.get("peaks.flat_top_threshold_fs", 0.95)
    total_flat = 0
    total = 0
    for ch in audio:
        above = np.abs(ch) >= threshold
        total += len(ch)
        i = 0
        n = len(ch)
        while i < n:
            if above[i]:
                j = i
                while j < n and above[j]:
                    j += 1
                if j - i >= 3:
                    total_flat += j - i
                i = j
            else:
                i += 1
    return total_flat / total if total else 0.0


def run_peak_checks(mix: np.ndarray, sr: int, cfg: Config, bpm: float, extra_stems: dict[str, np.ndarray] | None = None) -> list[CheckResult]:
    """Run all peak safety checks on the mix (and optionally other stems for headroom)."""
    results: list[CheckResult] = []
    results.extend(check_clip_runs(mix, sr, cfg, "mix", bpm))
    results.append(check_true_peak(mix, sr, cfg, "mix", bpm))
    results.append(check_isp_overs(mix, sr, cfg, "mix", bpm))
    results.append(check_stem_headroom(mix, sr, cfg, "mix", bpm))
    codec_result = check_codec_overs(mix, sr, cfg, "mix", bpm)
    if codec_result:
        results.append(codec_result)

    for name, audio in (extra_stems or {}).items():
        results.append(check_stem_headroom(audio, sr, cfg, name, bpm))

    return results


def any_fail(results: list[CheckResult]) -> bool:
    return any(r.level == "fail" for r in results)
