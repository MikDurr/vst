"""One plain verdict on how compressed a mix is, with the evidence.

Compression can't be measured directly from audio (ratio, threshold and gain
reduction are invisible), but its effects can: flattened short-term crest
factor, peaks pinned to the average (PLR), lost transients, pumping, and a
vocal that has lost or never had its dynamics. These are combined into a
single "openness" index:

- With a reference range, each core measurement is turned into a robust z
  (how many typical spreads from your references' median), and the index is a
  weighted mean. 0 means "like your references".
- Without references only PLR is used, against rule-of-thumb limits that are
  stated as such in the result.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from mixlens.compare.deviation import robust_z
from mixlens.compare.glossary import ACTIONS, format_value

SQUASHED, TIGHT, BALANCED, OPEN, VERY_OPEN = "squashed", "tight", "balanced", "open", "very open"
LABELS = {SQUASHED: "Squashed", TIGHT: "Tight", BALANCED: "Balanced", OPEN: "Open", VERY_OPEN: "Very open"}

# core measurement -> weight. All of them rise as the mix gets more dynamic.
CORE = {"st_crest": 2.0, "plr": 2.0, "transient_ratio": 1.0, "crest": 1.0}
# index (mean z) cut-offs between the verdicts, and PLR cut-offs without references
Z_CUTS = (-1.5, -0.75, 0.75, 1.5)
PLR_CUTS = (6.0, 8.0, 13.0, 16.0)

ADVICE = {
    SQUASHED: "More compressed than the sound you're aiming for. Back the limiter off 1-3 dB, check the bus compressor "
              "(slower attack, lower ratio, or less gain reduction), and consider blending the squashed copy in parallel "
              "instead of replacing the dry mix.",
    TIGHT: "A little tighter than your references. Fine if you want it dense; if the drums feel flat, ease the limiter "
           "or bus compressor by a dB.",
    BALANCED: "In line with your references. Nothing to change here.",
    OPEN: "More dynamic than your references. If it feels loose next to them, add 1-2 dB of gentle bus compression "
          "(slow attack, fast release) or a little more limiter gain.",
    VERY_OPEN: "Much more dynamic than your references, so it will sound quiet and uneven beside them. Add bus "
               "compression and limiting, and check that a few loud elements aren't driving the peaks.",
}
RULE_NOTE = "No references yet, so this uses a rule of thumb on peak-to-loudness (PLR). Add references for a real comparison."


@dataclass(frozen=True)
class Row:
    name: str
    value: float | None
    ref_low: float | None
    ref_high: float | None
    status: str          # "squashed" | "in range" | "open" | "" (no references)
    z: float | None = None
    feature: str = ""     # for unit formatting


@dataclass
class DynamicsSummary:
    verdict: str
    label: str
    basis: str                        # "references" | "rule of thumb"
    index: float | None               # mean z with references, else None
    position: float                   # 0..1, where the gauge marker sits
    headline: str
    advice: str
    drivers: list[str] = field(default_factory=list)
    rows: list[Row] = field(default_factory=list)       # core measurements
    bands: list[Row] = field(default_factory=list)      # low / mid / high crest
    pumping: Row | None = None
    vocal: list[str] = field(default_factory=list)
    sections: list[dict] = field(default_factory=list)
    section_note: str = ""


def _cut(x: float, cuts: tuple[float, float, float, float]) -> str:
    a, b, c, d = cuts
    return SQUASHED if x < a else TIGHT if x < b else BALANCED if x <= c else OPEN if x <= d else VERY_OPEN


def _row(name: str, feature: str, band: str, values: dict, envs: dict | None, low_word="squashed", high_word="open") -> Row | None:
    v = values.get((feature, band))
    if v is None:
        return None
    env = (envs or {}).get((feature, band))
    if env is None:
        return Row(name, v, None, None, "", None, feature)
    z = robust_z(v, env)
    status = low_word if z <= -1.0 else high_word if z >= 1.0 else "in range"
    return Row(name, v, env.p10, env.p90, status, z, feature)


def summarize_dynamics(values: dict[tuple[str, str], float], envelopes: dict | None) -> DynamicsSummary | None:
    """`values` is {(feature, band): value} for one version; `envelopes` is the
    style's reference range {(feature, band): Envelope}, or empty/None."""
    envs = envelopes or {}
    zs: dict[str, float] = {}
    for feat in CORE:
        env, v = envs.get((feat, "")), values.get((feat, ""))
        if env is not None and v is not None:
            zs[feat] = robust_z(v, env)

    if zs:
        index = sum(CORE[f] * z for f, z in zs.items()) / sum(CORE[f] for f in zs)
        verdict = _cut(index, Z_CUTS)
        basis, position = "references", min(max((index + 3.0) / 6.0, 0.0), 1.0)
        drivers = [
            f"{name_of(f)} is {format_value(f, values[(f, '')])} against your references' "
            f"{format_value(f, envs[(f, '')].p10)} to {format_value(f, envs[(f, '')].p90)}"
            for f, z in sorted(zs.items(), key=lambda kv: -abs(kv[1])) if abs(z) >= 1.0
        ][:3]
        headline = f"{LABELS[verdict]}: " + {
            SQUASHED: "this mix is clearly more compressed than your references.",
            TIGHT: "slightly more compressed than your references.",
            BALANCED: "about as compressed as your references.",
            OPEN: "more dynamic than your references.",
            VERY_OPEN: "much more dynamic than your references.",
        }[verdict]
    elif values.get(("plr", "")) is not None:
        plr = values[("plr", "")]
        verdict, index, basis = _cut(plr, PLR_CUTS), None, "rule of thumb"
        position = min(max((plr - 3.0) / 15.0, 0.0), 1.0)
        drivers = [f"Peak-to-loudness is {plr:.1f} dB. Under 6 dB is heavily limited; 8 to 13 dB is typical for a finished master."]
        headline = f"{LABELS[verdict]}: {RULE_NOTE}"
    else:
        return None

    rows = [r for r in (
        _row("Micro-dynamics (50 ms crest)", "st_crest", "", values, envs),
        _row("Peak vs average (PLR)", "plr", "", values, envs),
        _row("Punch (transient ratio)", "transient_ratio", "", values, envs),
        _row("Overall crest factor", "crest", "", values, envs),
    ) if r]
    bands = [r for r in (_row(f"{n} range", "band_crest", b, values, envs) for n, b in
                         (("Low", "low"), ("Mid", "mid"), ("High", "high"))) if r]

    advice = ADVICE[verdict]
    squashed_bands = [b.name.split()[0].lower() for b in bands if b.status == "squashed"]
    open_bands = [b.name.split()[0].lower() for b in bands if b.status == "open"]
    def names(items: list[str]) -> str:
        return " and ".join(items) + (" ranges" if len(items) > 1 else " range")

    if squashed_bands and len(squashed_bands) < len(bands):
        advice += f" The {names(squashed_bands)} " + ("are" if len(squashed_bands) > 1 else "is") + " the squashed part: " + ACTIONS[("band_crest", "low")]
    elif open_bands and len(open_bands) < len(bands) and verdict in (BALANCED, TIGHT, SQUASHED):
        advice += f" The {names(open_bands)} keep" + ("" if len(open_bands) > 1 else "s") + " more dynamics than the rest: " + ACTIONS[("band_crest", "high")]

    pump = _row("Pumping after kicks", "pump_depth", "", values, envs, low_word="steady", high_word="pumping")
    vocal = []
    for feat, band, word, tail in (
        ("vox_crest", "", "low", "The vocal is flatter than your references' vocals. Ease its compression or lower the ratio."),
        ("vox_consistency", "", "high", "The vocal's level is more uneven than your references'. Add compression or ride the quiet words up."),
        ("vox_floor_true", "", "high", "Breaths and noise between phrases are lifted more than in your references. Gate or edit gaps before upward compression like OTT."),
    ):
        r = _row(feat, feat, band, values, envs)
        if r and r.z is not None and ((word == "low" and r.z <= -1.0) or (word == "high" and r.z >= 1.0)):
            vocal.append(tail)

    sections, note = _sections(values, envs)
    return DynamicsSummary(verdict, LABELS[verdict], basis, index, position, headline, advice, drivers,
                           rows, bands, pump, vocal, sections, note)


def name_of(feature: str) -> str:
    return {"st_crest": "Micro-dynamics", "plr": "Peak-to-loudness", "transient_ratio": "Punch", "crest": "Crest factor"}[feature]


def _sections(values: dict, envs: dict) -> tuple[list[dict], str]:
    names = sorted({b for (f, b) in values if f == "st_crest_section"})
    if not names:
        return [], ""
    env = envs.get(("st_crest", ""))
    out = []
    for n in names:
        crest, loud = values.get(("st_crest_section", n)), values.get(("lufs_section", n))
        status = ""
        if env is not None and crest is not None:
            z = robust_z(crest, env)
            status = "squashed" if z <= -1.0 else "open" if z >= 1.0 else "in range"
        out.append({"section": n, "loudness": loud, "crest": crest, "status": status})
    crests = [(r["crest"], r["section"]) for r in out if r["crest"] is not None]
    note = ""
    if len(crests) >= 2:
        (lo, lo_n), (hi, hi_n) = min(crests), max(crests)
        if hi - lo >= 2.0:
            note = f"The {lo_n} is {hi - lo:.1f} dB more squashed than the {hi_n}. That's usually the loudest section being hit hardest by the limiter."
    return out, note
