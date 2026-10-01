"""Turn raw measurements into a short, ordered "what to do next" list.

Three sources, in order of importance:
1. Safety: clipping, true-peak overs, stem headroom (no references needed).
2. Sanity checks that don't need references (loudness, squashed dynamics, mono
   compatibility), so a first mix is never met with an empty page.
3. Deviations from the style's reference range, with the curated hints merged in.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from mixlens.compare.deviation import DeviationResult
from mixlens.compare.glossary import action_for, band_action, explain, feature_name, format_value

FIX, CHECK, NOTE = "fix", "check", "note"
_ORDER = {FIX: 0, CHECK: 1, NOTE: 2}


@dataclass(frozen=True)
class Recommendation:
    severity: str   # fix | check | note
    title: str
    why: str
    action: str
    evidence: str = ""


def _safety(checks: pd.DataFrame) -> list[Recommendation]:
    recs: list[Recommendation] = []
    if checks is None or checks.empty:
        return recs
    for _i, c in checks.iterrows():
        name, level, value, bar, stem = c["check_name"], c["level"], c["value"], c.get("bar"), c["stem"]
        where = f" around bar {bar:.0f}" if pd.notna(bar) else ""
        if name == "clip_runs" and level == "fail":
            recs.append(Recommendation(FIX, f"The bounce clips{where}",
                "Several samples in a row hit full scale, which is audible distortion.",
                "Lower the master output or limiter ceiling to -1.0 dBTP and re-bounce. If it only clips at one spot, fix that bar at the source.",
                f"{stem}, peak {value:.3f}"))
        elif name == "true_peak" and level == "fail":
            recs.append(Recommendation(FIX, "True peak is over 0 dBTP",
                "Between the samples the waveform goes above full scale, so it will clip when converted to MP3/AAC or on some DACs.",
                "Set the limiter's true-peak ceiling to -1.0 dBTP.", f"{value:.2f} dBTP"))
        elif name == "true_peak" and level == "warn":
            recs.append(Recommendation(CHECK, "True peak is above -1 dBTP",
                "Streaming encoders can push peaks this close to zero over the line.",
                "Lower the limiter ceiling to -1.0 dBTP for safety.", f"{value:.2f} dBTP"))
        elif name == "isp_overs" and level == "fail":
            recs.append(Recommendation(FIX, "Inter-sample overs detected",
                "The reconstructed waveform exceeds full scale in places.",
                "Enable true-peak limiting on your limiter, ceiling -1.0 dBTP.", f"{int(value)} overs"))
        elif name == "stem_headroom" and level == "warn":
            recs.append(Recommendation(CHECK, f"The {stem} stem is very hot ({value:.1f} dBFS)",
                "Stems this close to full scale can clip during the bounce.",
                "Re-bounce that stem with about 1 dB less level.", f"{value:.1f} dBFS"))
    return recs


def _sanity(f: dict[tuple[str, str], float]) -> list[Recommendation]:
    recs: list[Recommendation] = []
    g = lambda name, band="": f.get((name, band))
    lufs, plr = g("lufs_i"), g("plr")
    if lufs is not None and lufs > -8:
        recs.append(Recommendation(CHECK, f"Very loud master ({lufs:.1f} LUFS)",
            "Streaming platforms normalise to around -14 LUFS, so anything this loud is simply turned down.",
            "Try 2-4 dB less limiting. It will sound the same loudness on Spotify with more punch.", f"{lufs:.1f} LUFS"))
    if plr is not None and plr < 6:
        recs.append(Recommendation(CHECK, "Heavily limited",
            "Peaks are only a few dB above the average level, so there is little dynamic range left.",
            "Back the limiter off and let the transients through.", f"PLR {plr:.1f} dB"))
    for band, label in (("sub", "sub bass"), ("low", "low end"), ("mid", "mids"), ("high", "highs")):
        c = g("corr", band)
        if c is not None and c < 0:
            recs.append(Recommendation(CHECK, f"The {label} may cancel in mono",
                "Left and right are out of phase in this range, so it can thin out on phones, club mono systems and some Bluetooth speakers.",
                "Check the mix in mono. Common culprits: stereo wideners, chorus and detuned layers. Keep bass below ~120 Hz centred.",
                f"correlation {c:.2f}"))
    d = g("duck_depth_true")
    if d is not None and d <= 0:
        recs.append(Recommendation(CHECK, "The vocal reverb doesn't duck",
            "It sits at the same level while the vocal sings as in the gaps, which can blur words.",
            action_for("duck_depth_true", "low"), f"{d:.2f} dB"))
    p = g("csi_phone_delta")
    if p is not None and p < -0.15:
        recs.append(Recommendation(CHECK, "Words get lost on small speakers",
            "Consonant clarity drops a lot after phone-speaker filtering.",
            action_for("csi_phone_delta", "low"), f"{p:+.2f}"))
    return recs


def _range(feature: str, r: DeviationResult) -> str:
    """'you -16.1 LUFS, your references -12.0 to -9.0 LUFS': numbers a producer can use."""
    mine = f"you {format_value(feature, r.value)}"
    if r.ref_low is None or r.ref_high is None:
        return mine
    lo, hi = format_value(feature, r.ref_low), format_value(feature, r.ref_high)
    return f"{mine}; your references {lo}" if lo == hi else f"{mine}; your references {lo} to {hi}"


def _deviations(results: list[DeviationResult], hints: list[dict], rules: dict[str, dict]) -> tuple[list[Recommendation], set[str]]:
    recs: list[Recommendation] = []
    by_feature = {r.feature: r for r in results}
    covered: set[str] = set()
    for h in hints:
        conds = rules.get(h["id"], {}).get("conditions", [])
        feats = [c["feature"] for c in conds]
        covered.update(feats)
        ev = "; ".join(
            f"{feature_name(c['feature'])}: {_range(c['feature'], by_feature[c['feature']])}"
            for c in conds if c["feature"] in by_feature and c["direction"] in ("low", "high")
        )
        worst = max((by_feature[f].level for f in feats if f in by_feature), key=lambda l: l == "flag", default="watch")
        sentences = [s.strip() for s in h["message"].split(". ") if s.strip()]
        first = conds[0] if conds else {}
        concrete = action_for(first.get("feature", ""), first.get("direction", "").replace("_abs", "")) if first else ""
        # a hint's own text is 'diagnosis. what to do'; with no second sentence, use the curated move for it
        action = ". ".join(sentences[1:]) if len(sentences) > 1 else (concrete or h["message"])
        recs.append(Recommendation(FIX if worst == "flag" else CHECK, sentences[0].rstrip("."),
                                   "This measurement is outside what your references do.", action, ev))
    flagged = sorted((r for r in results if r.level != "ok" and r.feature not in covered), key=lambda r: -abs(r.z))
    for r in flagged[:6]:
        name = feature_name(r.feature) + (f" ({r.band.replace('Hz', ' Hz')})" if r.band else "")
        action = band_action(r.band, r.direction) if r.feature == "ltas" else action_for(r.feature, r.direction)
        how = "much " if abs(r.z) > 4 else ""
        recs.append(Recommendation(
            FIX if r.level == "flag" else CHECK,
            f"{name} is {how}{r.direction}er than your references" if r.direction in ("low", "high") else name,
            explain(r.feature, r.direction) or "Outside the range your references cover.",
            action or "Compare this with a reference in solo and adjust the elements that live here if the difference isn't intentional.",
            _range(r.feature, r),
        ))
    return recs, covered


def recommend(
    checks: pd.DataFrame | None,
    features: dict[tuple[str, str], float],
    results: list[DeviationResult],
    hints: list[dict],
    rules: dict[str, dict],
    has_reference_range: bool,
) -> list[Recommendation]:
    recs = _safety(checks)
    covered: set[str] = set()
    deviation_recs: list[Recommendation] = []
    if has_reference_range:
        deviation_recs, covered = _deviations(results, hints, rules)
    # reference-based hints already cover some sanity checks (e.g. reverb ducking): don't say it twice
    topic = {"The vocal reverb doesn't duck": "duck_depth_true", "Words get lost on small speakers": "csi_phone_delta"}
    recs += [r for r in _sanity(features) if topic.get(r.title) not in covered]
    recs += deviation_recs
    if not has_reference_range:
        recs.append(Recommendation(NOTE, "Add references to unlock comparisons",
            "Everything above works without references. To see how the mix sits against the sound you're aiming for, "
            "add reference songs for this style on the References page.",
            "Open References, add 8-20 songs you love the mix of, and click Measure references."))
    seen: set[str] = set()
    unique = [r for r in recs if not (r.title in seen or seen.add(r.title))]
    return sorted(unique, key=lambda r: _ORDER[r.severity])
