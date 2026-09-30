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
    "vir_med": ("Vocal-to-instrumental ratio", "How loud the vocal is over the instrumental while it's singing (LU).",
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
    "csi": ("Consonant survival (CSI)", "Fraction of 2-6 kHz bands where word onsets still poke above the instrumental.",
            "Consonants are masked: words lose clarity even if the vocal level seems fine.",
            "Consonants cut through clearly."),
    "csi_p10": ("Worst-moment CSI", "CSI at the weakest 10% of word onsets.",
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
    "space_contrast": ("Space contrast", "Instrumental decay minus vocal tail decay: how much wetter the vocal is than the instrumental.",
                       "Vocal and instrumental share the same space.", "Wet vocal over a dry instrumental (the target sound)."),
    "vox_attack": ("Vocal attack", "Rise of 2-8 kHz in the 10 ms after word onsets (info only).",
                   "Reverb is blurring word starts.", "Crisp word onsets."),
    "air_ratio": ("Air", "Energy 10-16 kHz relative to 1-4 kHz.",
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
    "csi_phone": ("Consonants on a phone", "CSI after phone-speaker filtering.",
                  "Words collapse on small speakers.", "Words stay clear on small speakers."),
    "csi_mono": ("Consonants in mono", "CSI after mono fold-down.",
                 "Words get masked in mono.", "Words stay clear in mono."),
    "vir_phone_delta": ("Phone vocal-level change", "Phone VIR minus full-range VIR.",
                        "Vocal drops back on phones.", "Vocal comes forward on phones."),
    "vir_mono_delta": ("Mono vocal-level change", "Mono VIR minus full-range VIR.",
                       "Vocal drops back in mono.", "Vocal comes forward in mono."),
    "csi_phone_delta": ("Phone clarity change", "Phone CSI minus full-range CSI.",
                        "Words lose clarity on phones (below -0.15 is a problem).", "Clearer on phones than full range."),
    "csi_mono_delta": ("Mono clarity change", "Mono CSI minus full-range CSI.",
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
