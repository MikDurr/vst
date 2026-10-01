"""Plain-language explanations of every feature, for the UI.

Each entry: (name, what it measures, what a LOW value means, what a HIGH value
means). "Low"/"high" are relative to the style's reference envelope unless the
feature is only ever compared to your own history (the `_true` features).
"""
from __future__ import annotations

GLOSSARY: dict[str, tuple[str, str, str, str]] = {
    "lufs_i": ("Integrated loudness", "Overall loudness of the whole song (LUFS).",
               "Quieter than your references; you may lose out when levels are matched by ear.",
               "Louder than your references; usually means heavier limiting."),
    "lra": ("Loudness range", "How much the loudness moves between quiet and loud sections.",
            "Very even level: little contrast between sections.",
            "Big swings between sections, more than your references."),
    "plr": ("Peak-to-loudness", "True peak minus integrated loudness: headroom the limiter leaves.",
            "Heavily limited: peaks are pinned close to the average.",
            "Peaky: transients stick out well above the average level."),
    "crest": ("Crest factor", "Peak vs average level across the song.",
              "Squashed dynamics.", "Very dynamic, peaks far above the average."),
    "ltas": ("Tonal balance", "Average spectrum in 1/3-octave bands, relative to the 250 Hz-4 kHz mean.",
             "That band is weaker than in your references.", "That band is stronger than in your references."),
    "side_mid": ("Stereo width", "Side vs mid energy in a frequency band.",
                 "Narrower than your references in that band.", "Wider than your references in that band."),
    "corr": ("Phase correlation", "How well left and right agree in a band (+1 mono-compatible, negative = cancels).",
             "Left/right are fighting: this band may thin out in mono.", "Very mono-like in that band."),
    "vir_med": ("Vocal level vs instrumental", "How loud the vocal is over the instrumental while it's singing (LU).",
                "Vocal sits further back than your references.", "Vocal sits more forward than your references."),
    "vir_iqr": ("Vocal level spread", "How much the vocal/instrumental balance varies.",
                "Very steady balance.", "Balance wanders a lot across the song."),
    "vir_section": ("Vocal level per section", "Vocal-to-instrumental ratio within one song section.",
                    "Vocal recedes in that section.", "Vocal pushes forward in that section."),
    "vox_consistency": ("Vocal consistency", "Spread of the vocal's loudness from word to word.",
                        "Very even vocal (heavily controlled).", "Uneven vocal: quiet words risk sinking."),
    "vox_harsh": ("Vocal harshness", "Vocal 2-5 kHz energy relative to 200 Hz-1 kHz.",
                  "Vocal is warm or dull in the presence range.", "Vocal has a forward, potentially harsh edge."),
    "vox_sib": ("Vocal sibilance", "Vocal 5-10 kHz energy relative to 200 Hz-1 kHz.",
                "Soft, de-essed top.", "Sibilant: 's' sounds may be piercing, especially through bright reverb."),
    "csi": ("Lyric clarity (consonant survival)", "Fraction of 2-6 kHz bands where word onsets still poke above the instrumental.",
            "Consonants are masked: words lose clarity even if the vocal level seems fine.",
            "Consonants cut through clearly."),
    "csi_p10": ("Lyric clarity at the worst moments", "CSI at the weakest 10% of word onsets.",
                "Some words vanish completely.", "Even the worst moments stay intelligible."),
    "mask": ("Masking depth", "How far the instrumental sits above the vocal in a band (info only).",
             "Little overlap in that band.", "Instrumental crowds the vocal in that band (some is intended)."),
    "vox_tail_level": ("Vocal reverb level", "Loudness of the vocal tail 150-400 ms after each phrase, relative to the phrase.",
                       "Dry vocal tail.", "Loud reverb tail: can bury following words."),
    "vox_tail_decay": ("Vocal tail decay", "How fast the vocal tail falls (dB/s). Shallower = longer tail.",
                       "Falls quickly (steep): short reverb.", "Decays slowly: long, lingering reverb."),
    "vox_tail_bright": ("Vocal tail brightness", "Tail spectral centroid vs the phrase itself (octaves).",
                        "Tail is darker than the vocal.", "Tail is brighter than the vocal (shimmery)."),
    "inst_decay": ("Instrumental decay", "How fast the instrumental fades after strong hits (dB/s).",
                   "Long, sustained instrumental.", "Short, dry instrumental."),
    "space_contrast": ("Vocal wetness vs instrumental", "Instrumental decay minus vocal tail decay: how much wetter the vocal is than the instrumental.",
                       "Vocal and instrumental share the same space.", "Wet vocal over a dry instrumental (the target sound)."),
    "vox_attack": ("Vocal attack", "Rise of 2-8 kHz in the 10 ms after word onsets (info only).",
                   "Reverb is blurring word starts.", "Crisp word onsets."),
    "air_ratio": ("High-end shine", "Energy 10-16 kHz relative to 1-4 kHz.",
                  "Duller top end than your references.", "Brighter, airier top end."),
    "presence_ratio": ("Presence", "Energy 4-10 kHz relative to 1-4 kHz.",
                       "Recessed upper mids.", "Forward, bright upper mids."),
    "hf_density": ("Top-end density", "Short-term crest factor of everything above 4 kHz. Lower = denser.",
                   "Dense, saturated, polished top end.", "Peaky top end: transients aren't compressed or saturated."),
    "hf_flatness": ("Top-end fizz", "How noise-like the spectrum above 4 kHz is.",
                    "Clean, tonal top end.", "Noisy, fizzy top end (stacked saturation or OTT)."),
    "side_mid_air": ("Air width", "Side vs mid energy above 8 kHz.",
                     "Narrow highs.", "Wide shimmering highs."),
    "vox_air_ratio": ("Vocal air", "Air ratio of the vocal stem alone.",
                      "Dull vocal top.", "Bright, airy vocal."),
    "st_crest": ("Micro-dynamics", "Median crest factor in 50 ms windows.",
                 "Micro-dynamics flattened: the limiter/OTT is doing a lot.", "Lively, punchy dynamics."),
    "transient_ratio": ("Transient punch", "Level at strong onsets minus level 100-300 ms later.",
                        "Drums and plucks are losing their attack.", "Strong, snappy attacks."),
    "band_crest": ("Band dynamics", "Short-term crest within a frequency region.",
                   "That region is squashed (e.g. multiband/OTT).", "That region keeps its dynamics."),
    "pump_depth": ("Pumping", "Dip in the 200 Hz-8 kHz level 50-300 ms after each kick.",
                   "Steady: little audible pumping.", "Audible pumping from bus compression or sidechain."),
    "st_crest_section": ("Micro-dynamics by section", "How squashed each song section is (50 ms crest).",
                         "That section is heavily limited or compressed.", "That section keeps its dynamics."),
    "lufs_section": ("Loudness by section", "Integrated loudness of each song section.", "A quieter section.", "A louder section."),
    "stem_level": ("Level of each element", "How loud the drums, bass, synths and vocals are against the whole mix.", "Sits further back than your references.", "Sits further forward than your references."),
    "stem_width": ("Stereo width of each element", "How wide the drums, bass, synths or vocals are (side versus mid energy).", "Narrower than your references.", "Wider than your references."),
    "stem_centroid": ("Brightness of each element", "How bright each element is (where its energy is centred).", "Darker than your references.", "Brighter than your references."),
    "stem_crest": ("Dynamics of each element", "How dynamic each element is (peak versus average).", "More compressed than your references.", "More dynamic than your references."),
    "band_share": ("Who owns each frequency range", "The share of each frequency range's energy held by each element.", "Owns less of that range.", "Owns more of that range."),
    "kick_bass_ratio": ("Kick versus bass", "Level of the drums' low end against the bass's low end (30-100 Hz).", "Bass-heavy low end.", "Kick-heavy low end."),
    "low_end_overlap": ("Kick and bass hitting together", "How often the kick and bass are loud at the same moment (0 to 100%).", "They take turns.", "They hit together a lot, so the low end can clash."),
    "masking": ("Elements crowding each other", "How much two elements fill the same frequencies at the same time and level (0 to 100%).", "Plenty of room between them.", "Crowded: they are likely to mask each other."),
    "width_motion": ("Stereo-image movement", "How much the stereo width of the highs changes over the song.", "A static image, which sounds flat.", "A moving, lively image."),
    "spectral_motion": ("Tonal movement", "How much the tonal balance changes over the song.", "The tone barely changes, which sounds flat.", "The tone evolves through the song."),
    "vox_crest": ("Vocal dynamics", "Short-term crest on the vocal stem.",
                  "Over-flattened vocal.", "Uncontrolled vocal peaks."),
    "vox_floor_true": ("Vocal gap noise", "Level of the dry vocal in gaps between phrases, relative to the phrases.",
                       "Clean gaps.", "Breaths, mouth noise and noise floor lifted into the gaps (upward compression)."),
    "wet_dry_true": ("Wet/dry balance", "Loudness of the reverb/delay returns vs the dry vocal (your stems).",
                     "Mostly dry.", "Mostly wet."),
    "csi_wash_drop_true": ("Reverb wash", "How much CSI drops when the reverb counts as masker instead of signal.",
                           "Reverb isn't hurting consonants.", "Your reverb is covering your own consonants."),
    "duck_depth_true": ("Reverb ducking", "Reverb level in the gaps minus while the dry vocal sings.",
                        "Reverb does not duck: it sits on top of the words.", "Reverb ducks under the vocal and blooms in the gaps."),
    "predelay_true": ("Pre-delay", "Time from each dry onset until the reverb reaches half its level (ms).",
                      "Reverb starts immediately.", "Reverb is held back: clearer words."),
    "wet_bright_true": ("Reverb brightness", "Reverb centroid vs dry vocal centroid (octaves).",
                        "Reverb darker than the vocal.", "Reverb brighter than the vocal."),
    "vir_phone": ("Vocal level on a phone", "Vocal-to-instrumental ratio after phone-speaker filtering.",
                  "Vocal gets lost on small speakers.", "Vocal dominates on small speakers."),
    "vir_mono": ("Vocal level in mono", "Vocal-to-instrumental ratio after mono fold-down.",
                 "Vocal loses level in mono.", "Vocal gains level in mono."),
    "csi_phone": ("Lyric clarity on a phone", "CSI after phone-speaker filtering.",
                  "Words collapse on small speakers.", "Words stay clear on small speakers."),
    "csi_mono": ("Lyric clarity in mono", "CSI after mono fold-down.",
                 "Words get masked in mono.", "Words stay clear in mono."),
    "vir_phone_delta": ("Phone vocal-level change", "Phone VIR minus full-range VIR.",
                        "Vocal drops back on phones.", "Vocal comes forward on phones."),
    "vir_mono_delta": ("Mono vocal-level change", "Mono VIR minus full-range VIR.",
                       "Vocal drops back in mono.", "Vocal comes forward in mono."),
    "csi_phone_delta": ("Lyric clarity lost on a phone", "Phone CSI minus full-range CSI.",
                        "Words lose clarity on phones (below -0.15 is a problem).", "Clearer on phones than full range."),
    "csi_mono_delta": ("Lyric clarity lost in mono", "Mono CSI minus full-range CSI.",
                       "Words lose clarity in mono.", "Clearer in mono."),
    "true_peak": ("True peak", "Highest inter-sample peak in dBTP. Above 0 will clip after conversion.",
                  "Comfortable headroom.", "At or over full scale: risk of clipping on playback/encoding."),
    "flat_top_ratio": ("Clipping grit", "Share of flat-topped peaks below full scale (info only: your intentional distortion).",
                       "Little clipping.", "A lot of clip distortion."),
}


def _lookup(feature: str):
    if feature in GLOSSARY:
        return GLOSSARY[feature], False
    if feature.endswith("_true") and feature[:-5] in GLOSSARY:
        return GLOSSARY[feature[:-5]], True
    return None, False


def feature_name(feature: str) -> str:
    entry, from_true = _lookup(feature)
    if not entry:
        return feature
    return entry[0] + (" (your true stems)" if from_true else "")


def what_it_measures(feature: str) -> str:
    entry, _ = _lookup(feature)
    return entry[1] if entry else ""


def explain(feature: str, direction: str) -> str:
    """Sentence for a feature that is `direction` ("low"/"high") vs the envelope."""
    entry, _ = _lookup(feature)
    if not entry or direction not in ("low", "high"):
        return ""
    return entry[2] if direction == "low" else entry[3]


def trend_note(feature: str, first: float, last: float) -> str:
    """One-line reading of how a metric moved between the first and last version.

    Only interprets moves bigger than ~5% of the value (or 0.05 absolute);
    smaller ones are reported as unchanged rather than over-read.
    """
    if feature == "true_peak":
        state = "FAIL (over 0 dBTP)" if last > 0 else "warning (above -1 dBTP)" if last > -1 else "ok"
        return f"Latest true peak is {last:.2f} dBTP: {state}. Fails above 0, warns above -1."
    delta = last - first
    if abs(delta) < max(0.05, 0.05 * max(abs(first), abs(last))):
        return f"Essentially unchanged across versions ({first:.2f} to {last:.2f})."
    entry, _ = _lookup(feature)
    verb = "Rose" if delta > 0 else "Fell"
    note = f"{verb} from {first:.2f} to {last:.2f}."
    if entry:
        note += f" Moving toward: {entry[3] if delta > 0 else entry[2]}"
    return note


# What to actually do about it: (feature, direction vs references) -> a concrete move.
ACTIONS: dict[tuple[str, str], str] = {
    ("lufs_i", "high"): "Back the limiter off 1-2 dB. Streaming services turn loud masters down anyway, so you gain nothing and lose punch.",
    ("lufs_i", "low"): "Raise the limiter input gain a little, or check the mix bus isn't being held back by one loud element.",
    ("plr", "low"): "You are limiting hard. Lower the limiter gain or raise its threshold so peaks stand out from the average again.",
    ("plr", "high"): "Peaks stick out a lot. A touch more bus compression or limiter gain would tighten it.",
    ("crest", "low"): "Dynamics are squashed. Ease off bus compression and the limiter, and check for stacked compressors.",
    ("st_crest", "low"): "Ease the bus compressor, limiter or OTT depth. Parallel-blend the heavily compressed copy instead of replacing the dry one.",
    ("transient_ratio", "low"): "Drums and plucks are losing their attack. Slow the compressor attack, or add a transient shaper on the drum bus.",
    ("pump_depth", "high"): "Lengthen the compressor release or reduce sidechain depth so the bed recovers faster between kicks.",
    ("vir_med", "high"): "Pull the vocal fader down about 1-2 dB, or automate it down in the busiest sections.",
    ("vir_med", "low"): "Raise the vocal 1-2 dB, or carve space for it in the instrumental around 1-4 kHz.",
    ("csi", "low"): "Words are getting buried. EQ the instrumental down 2-3 dB around 2-5 kHz under the vocal, or lift the vocal's presence band.",
    ("csi_p10", "low"): "The quietest words vanish. Compress or ride the vocal so soft words keep up, and automate problem phrases.",
    ("vox_consistency", "high"): "The vocal level is uneven. Add compression or clip-gain the quiet words up.",
    ("vox_sib", "high"): "Add or deepen a de-esser before the reverb send, and check bright reverb isn't amplifying the S sounds.",
    ("vox_harsh", "high"): "Dip the vocal 2-5 dB around 3-4 kHz with a dynamic EQ, or soften the saturation stage.",
    ("vox_tail_level", "high"): "The reverb is loud. Lower the return level or add a high-cut and pre-delay so it doesn't cover the next word.",
    ("space_contrast", "low"): "Vocal and instrumental share one space. Make the instrumental drier (less reverb on synths/drums) or add more vocal reverb.",
    ("vox_tail_bright", "low"): "The reverb tail is darker than your references. Raise the reverb's high cut, or add a high shelf on the return.",
    ("air_ratio", "low"): "The top end is dull. Try a high shelf (+1-2 dB around 10 kHz) on the mix bus, or brighter sources.",
    ("air_ratio", "high"): "Very bright top end. Roll back the high shelf or check for harsh exciters.",
    ("hf_density", "high"): "The top end is peaky rather than dense. Add saturation or gentle upward compression on bright elements.",
    ("hf_flatness", "high"): "The top is fizzy. Check stacked distortion and de-essing; low-pass noisy layers around 14-16 kHz.",
    ("side_mid_air", "low"): "Highs are narrow. Widen bright layers with a stereo widener or short stereo delays.",
    ("vox_floor_true", "high"): "Breaths and noise are being lifted. Gate or edit the gaps before any upward compression like OTT.",
    ("duck_depth_true", "low"): "Add sidechain compression on the reverb return, keyed from the dry vocal, so it blooms in the gaps.",
    ("csi_wash_drop_true", "high"): "Your reverb is covering your own consonants. Add pre-delay, duck the return, or shorten the decay.",
    ("csi_phone_delta", "low"): "Words collapse on small speakers. Check the vocal against a phone-speaker EQ and lift 1-3 kHz.",
    ("pump_depth", "low"): "Little pumping versus your references. If you want that feel, increase sidechain depth.",
}


def action_for(feature: str, direction: str) -> str:
    base = feature[:-5] if feature.endswith("_true") and feature not in {a for a, _ in ACTIONS} else feature
    return ACTIONS.get((feature, direction)) or ACTIONS.get((base, direction), "")


# Units for quoting values the way a producer reads them.
UNITS: dict[str, str] = {
    "lufs_i": "LUFS", "lra": "LU", "plr": "dB", "crest": "dB", "st_crest": "dB", "transient_ratio": "dB", "pump_depth": "dB",
    "band_crest": "dB", "vir_med": "dB", "vir_iqr": "dB", "vir_section": "dB", "vir_phone": "dB", "vir_mono": "dB",
    "vox_consistency": "dB", "vox_harsh": "dB", "vox_sib": "dB", "vox_crest": "dB", "vox_floor_true": "dB", "mask": "dB",
    "vox_tail_level": "dB", "vox_tail_decay": "dB/s", "inst_decay": "dB/s", "space_contrast": "dB/s", "vox_tail_bright": "oct",
    "air_ratio": "dB", "presence_ratio": "dB", "side_mid_air": "dB", "vox_air_ratio": "dB", "hf_density": "dB", "side_mid": "dB",
    "ltas": "dB", "wet_dry_true": "dB", "duck_depth_true": "dB", "predelay_true": "ms", "wet_bright_true": "oct",
    "true_peak": "dBTP", "stem_level": "dB", "stem_width": "dB", "stem_centroid": "oct", "stem_crest": "dB", "kick_bass_ratio": "dB",
    "width_motion": "dB", "spectral_motion": "dB", "band_share": "%", "vir_phone_delta": "dB", "vir_mono_delta": "dB",
}
PERCENT = {"low_end_overlap", "masking", "csi", "csi_p10", "csi_phone", "csi_mono", "csi_wash_drop_true", "csi_phone_delta", "csi_mono_delta", "flat_top_ratio"}


def format_value(feature: str, value: float) -> str:
    """'-16.1 LUFS', '62%', ... so numbers always carry their unit."""
    base = feature[:-5] if feature.endswith("_true") and feature not in UNITS else feature
    if base in PERCENT or feature in PERCENT:
        return f"{value * 100:.0f}%"
    unit = UNITS.get(feature) or UNITS.get(base, "")
    return f"{value:.1f} {unit}".strip()


ACTIONS.update({
    ("side_mid", "low"): "The stereo image is narrower than your references. Try a stereo widener or short stereo delays on pads and synths, and keep bass and kick centred.",
    ("side_mid", "high"): "Wider than your references. Narrow the widest layers, and keep everything below ~120 Hz in mono so it holds up on club systems and phones.",
    ("corr", "low"): "Left and right are working against each other here. Check the mix in mono and pull back wideners, chorus or detuned layers.",
    ("band_crest", "low"): "That frequency range is squashed. Check multiband compression or OTT on the bus, and lower its depth.",
    ("band_crest", "high"): "That range is more dynamic than your references. A little compression on the elements living there would even it out.",
    ("presence_ratio", "low"): "The upper mids are recessed. Try +1-2 dB around 5-8 kHz on the mix bus or on the lead.",
    ("presence_ratio", "high"): "Forward, bright upper mids. A 1-2 dB dip around 5-8 kHz on the bus will smooth it.",
    ("lra", "low"): "Very even loudness from section to section. Automate more contrast, such as quieter verses and bigger hooks.",
    ("lra", "high"): "Big loudness swings between sections. Even them out with bus automation or compression.",
    ("crest", "high"): "More dynamic than your references. A touch more bus compression or limiting would tighten it.",
    ("vox_tail_level", "low"): "Dry vocal tail compared with your references. Raise the reverb return if you want more space.",
    ("vox_tail_decay", "low"): "The vocal tail dies quickly. Lengthen the reverb decay if you want it to linger.",
    ("side_mid_air", "high"): "The highs are very wide. Pull back stereo wideners and bright stereo effects so the top end holds up in mono.",
    ("hf_density", "low"): "A very dense, compressed top end. Fine if intentional; otherwise back off saturation or OTT on bright elements.",
})
for _k in [("ltas", "low"), ("ltas", "high")]:
    pass


def band_action(band: str, direction: str) -> str:
    """EQ move for a tonal-balance band like '1000.0Hz'."""
    try:
        hz = float(band.replace("Hz", ""))
    except ValueError:
        return ""
    label = f"{hz / 1000:.1f} kHz".replace(".0 kHz", " kHz") if hz >= 1000 else f"{hz:.0f} Hz"
    if direction == "high":
        return f"There's more energy around {label} than in your references. Try a gentle 1-3 dB cut there (a wide dynamic EQ band works well), or check which element is piling up."
    return f"There's less energy around {label} than in your references. Try a gentle 1-3 dB boost there, or look for an element that could fill it."
