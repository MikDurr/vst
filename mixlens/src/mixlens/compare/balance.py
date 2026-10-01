"""Findings about how the elements of a mix sit together, from the mix-balance
features (see features/mixbalance.py), compared with your references."""
from __future__ import annotations

from dataclasses import dataclass, field

from mixlens.compare.deviation import robust_z
from mixlens.compare.glossary import ACTIONS

BALANCE_FEATURES = {"stem_level", "stem_width", "stem_centroid", "stem_crest", "kick_bass_ratio",
                    "low_end_overlap", "masking", "width_motion", "spectral_motion"}

STEM_LABEL = {"drums": "Drums", "bass": "Bass", "other": "Synths, guitars & pads", "vocals": "Vocals"}
STEM_SHORT = {"drums": "the drums", "bass": "the bass", "other": "the synths, guitars and pads", "vocals": "the vocals"}
ZONE_LABEL = {"low-mid": "low-mids (200-800 Hz)", "mid": "mids (0.8-3 kHz)", "presence": "presence (3-6 kHz)"}
ORDER = ["drums", "bass", "other", "vocals"]

# (word when above the references, word when below)
WORDS = {
    "stem_level": ("louder", "quieter"), "stem_width": ("wider", "narrower"), "stem_centroid": ("brighter", "darker"),
    "stem_crest": ("more dynamic", "more compressed"), "masking": ("more crowded", "less crowded"),
    "low_end_overlap": ("more overlap", "less overlap"), "kick_bass_ratio": ("kick-heavy", "bass-heavy"),
}

MOVES = {
    ("stem_level", "high"): "Pull {the} down 1-2 dB, or EQ it so it stops crowding the rest.",
    ("stem_level", "low"): "Raise {the} 1-2 dB, or check something isn't masking it. A little saturation helps it cut through.",
    ("stem_width", "low"): "Widen {the}: stereo spread, a chorus or short stereo delay, or doubled layers panned apart. Keep everything below ~120 Hz centred.",
    ("stem_width", "high"): "Narrow {the} a little. Very wide parts thin out in mono and on phones; keep the low end centred.",
    ("stem_centroid", "low"): "{The} sounds darker than your references. Try a gentle high shelf (+1-2 dB around 8 kHz) or brighter sources.",
    ("stem_centroid", "high"): "{The} sounds brighter than your references. Check for harshness; a high shelf cut or a de-esser may help.",
    ("stem_crest", "low"): "{The} is flatter than your references. Ease the compression on it, or slow the attack so transients survive.",
    ("stem_crest", "high"): "{The} is more dynamic than your references. A touch of compression will sit it more firmly in the mix.",
    ("kick_bass_ratio", "low"): "The kick is buried under the bass. Sidechain the bass to the kick, or give them separate low ranges (kick around 50-60 Hz, bass 80-120 Hz).",
    ("kick_bass_ratio", "high"): "The kick dominates the bass. Lift the bass a little, or tame the kick's sub.",
    ("low_end_overlap", "high"): "Kick and bass hit together a lot, so the low end clashes. Sidechain the bass to the kick, or offset them rhythmically.",
    ("masking", "high"): "Carve space: cut 2-3 dB from {b} in the range {a} occupies, or pan them apart, or let them take turns with automation or sidechain.",
    ("width_motion", "low"): "The stereo image never changes. Automate width, or add movement: auto-pan, modulated stereo delays, different panning per section.",
    ("spectral_motion", "low"): "The tone barely changes over the song. Add filter sweeps, EQ automation, or bring layers in and out between sections.",
}


def describe(feature: str, band: str, direction: str) -> tuple[str, str] | None:
    """(title, action) for a deviation in one of the balance features, or None."""
    words = WORDS.get(feature)
    word = None if words is None else (words[0] if direction == "high" else words[1])
    stem = band.split("|")[0]
    if feature in ("stem_level", "stem_width", "stem_centroid", "stem_crest") and stem in STEM_SHORT:
        the = STEM_SHORT[stem]
        title = {"stem_level": f"{STEM_LABEL[stem]} are {word} than in your references" if stem != "bass" and stem != "drums" else f"The {stem} is {word} than in your references",
                 "stem_width": f"{STEM_LABEL[stem]} {'are' if stem in ('other', 'vocals') else 'is'} {word} than your references",
                 "stem_centroid": f"{STEM_LABEL[stem]} sound {word} than your references",
                 "stem_crest": f"{STEM_LABEL[stem]} {'are' if stem in ('other', 'vocals') else 'is'} {word} than your references"}[feature]
        return title, MOVES[(feature, direction)].format(the=the, The=the[0].upper() + the[1:])
    if feature == "kick_bass_ratio":
        return f"The low end is {word}", MOVES[(feature, direction)]
    if feature == "low_end_overlap" and direction == "high":
        return "Kick and bass clash in the low end", MOVES[(feature, direction)]
    if feature == "masking" and direction == "high" and "~" in band:
        pair, zone = band.split("|")
        a, b = pair.split("~")
        return (f"{STEM_LABEL[a]} and {STEM_LABEL[b].lower()} are crowding each other in the {ZONE_LABEL.get(zone, zone)}",
                MOVES[(feature, "high")].format(a=STEM_SHORT[a], b=STEM_SHORT[b]))
    if feature in ("width_motion", "spectral_motion") and direction == "low":
        return ("The stereo image is static" if feature == "width_motion" else "The tone barely changes over the song"), MOVES[(feature, "low")]
    return None


@dataclass(frozen=True)
class RangeRow:
    label: str
    feature: str
    band: str
    value: float
    lo: float | None
    hi: float | None
    med: float | None
    status: str          # words like "louder", or "in range", or "" without references
    z: float | None


def _row(label, feature, band, values, envs) -> RangeRow | None:
    v = values.get((feature, band))
    if v is None:
        return None
    env = envs.get((feature, band))
    if env is None:
        return RangeRow(label, feature, band, v, None, None, None, "", None)
    z = robust_z(v, env)
    words = WORDS.get(feature, ("above", "below"))
    status = words[0] if z >= 1.0 else words[1] if z <= -1.0 else "in range"
    return RangeRow(label, feature, band, v, env.p10, env.p90, env.med, status, z)


# ------------------------------------------------------------------ depth
FLAT, A_BIT_FLAT, GOOD_DEPTH, LIVELY, VERY_LIVELY = "Flat", "A bit flat", "Good depth", "Lively", "Very lively"
DEPTH_CUTS = (-1.5, -0.6, 0.8, 1.6)
DEPTH_PARTS = {"width_motion": 1.5, "spectral_motion": 1.5, "stem_width|other": 1.0, "lra": 0.5}
DEPTH_NOTES = {
    "width_motion": "The stereo image changes less over the song than your references'",
    "spectral_motion": "The tone changes less over the song than your references'",
    "stem_width|other": "The synths, guitars and pads are narrower than your references'",
    "lra": "The loudness moves less between sections than your references'",
}


@dataclass
class Depth:
    label: str
    position: float
    headline: str
    drivers: list[str]
    advice: str


def summarize_depth(values: dict, envs: dict) -> Depth | None:
    """How flat or alive the mix sounds, from stereo-image movement, tonal movement,
    the width of the main harmonic layers, and loudness movement between sections.
    Needs references: 'flat' only means something relative to the sound you want."""
    zs: dict[str, float] = {}
    for part in DEPTH_PARTS:
        feat, _, band = part.partition("|")
        env, v = envs.get((feat, band)), values.get((feat, band))
        if env is not None and v is not None:
            zs[part] = robust_z(v, env)
    if not zs:
        return None
    index = sum(DEPTH_PARTS[p] * z for p, z in zs.items()) / sum(DEPTH_PARTS[p] for p in zs)
    a, b, c, d = DEPTH_CUTS
    label = FLAT if index < a else A_BIT_FLAT if index < b else GOOD_DEPTH if index <= c else LIVELY if index <= d else VERY_LIVELY
    low = [p for p, z in sorted(zs.items(), key=lambda kv: kv[1]) if z <= -1.0]
    drivers = [DEPTH_NOTES[p] for p in low][:3]
    moves = [MOVES[(p.split("|")[0], "low")] if p.split("|")[0] in ("width_motion", "spectral_motion")
             else MOVES[("stem_width", "low")].format(the="the synths, guitars and pads", The="The synths") if p.startswith("stem_width")
             else "Automate bigger loudness moves between sections." for p in low][:3]
    headline = {
        FLAT: "this mix sounds flat next to your references: little changes over time and little is happening across the stereo field.",
        A_BIT_FLAT: "a little flatter than your references.",
        GOOD_DEPTH: "about as much movement and width as your references.",
        LIVELY: "more movement and width than your references.",
        VERY_LIVELY: "much more movement and width than your references.",
    }[label]
    advice = " ".join(moves) if moves else {
        GOOD_DEPTH: "Nothing to change here.", LIVELY: "Nothing to fix; check it still holds together in mono.",
        VERY_LIVELY: "Check it holds together in mono and on a phone speaker.",
    }.get(label, "")
    return Depth(label, min(max((index + 3.0) / 6.0, 0.0), 1.0), headline, drivers, advice)


# ------------------------------------------------------------------ report
@dataclass
class BalanceReport:
    has_reference: bool
    stems: list[str]
    levels: list[RangeRow] = field(default_factory=list)
    widths: list[RangeRow] = field(default_factory=list)
    brightness: list[RangeRow] = field(default_factory=list)
    crest: list[RangeRow] = field(default_factory=list)
    low_end: list[RangeRow] = field(default_factory=list)
    masking: list[RangeRow] = field(default_factory=list)
    share: dict[str, dict[str, tuple[float, float | None]]] = field(default_factory=dict)   # band -> stem -> (you %, ref %)
    depth: Depth | None = None


def build_balance(values: dict, envs: dict) -> BalanceReport | None:
    stems = [s for s in ORDER if ("stem_level", s) in values]
    if not stems:
        return None
    rep = BalanceReport(any(k[0] == "stem_level" for k in envs), stems)
    for s in stems:
        for fam, label in (("levels", "stem_level"), ("widths", "stem_width"), ("brightness", "stem_centroid"), ("crest", "stem_crest")):
            r = _row(STEM_LABEL[s], label, s, values, envs)
            if r:
                getattr(rep, fam).append(r)
    for label, feat in (("Kick vs bass level", "kick_bass_ratio"), ("Kick and bass hitting together", "low_end_overlap")):
        r = _row(label, feat, "", values, envs)
        if r:
            rep.low_end.append(r)
    for (feat, band), _v in sorted(values.items()):
        if feat == "masking":
            pair, zone = band.split("|")
            a, b = pair.split("~")
            r = _row(f"{STEM_LABEL[a]} vs {STEM_LABEL[b].lower()}, {ZONE_LABEL.get(zone, zone)}", feat, band, values, envs)
            if r:
                rep.masking.append(r)
    for (feat, band), v in values.items():
        if feat == "band_share":
            stem, rng = band.split("|")
            env = envs.get((feat, band))
            rep.share.setdefault(rng, {})[stem] = (v, env.med if env is not None else None)
    rep.depth = summarize_depth(values, envs) if rep.has_reference else None
    return rep
