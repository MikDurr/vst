"""'What to do next': safety first, reference-free sanity checks, then deviations."""
import pandas as pd

from mixlens.compare.deviation import DeviationResult
from mixlens.compare.recommend import FIX, NOTE, recommend


def checks(*rows):
    return pd.DataFrame(rows, columns=["check_name", "level", "value", "t_sec", "bar", "stem"])


def titles(recs):
    return [r.title for r in recs]


def test_clipping_is_a_fix_with_a_concrete_action_and_bar():
    recs = recommend(checks(("clip_runs", "fail", 1.0, 3.0, 5.0, "mix")), {}, [], [], {}, True)
    assert recs[0].severity == FIX and "bar 5" in recs[0].title and "-1.0 dBTP" in recs[0].action


def test_clean_mix_without_references_still_gets_something_useful():
    recs = recommend(checks(("true_peak", "ok", -2.0, None, None, "mix")), {("lufs_i", ""): -6.5}, [], [], {}, False)
    t = titles(recs)
    assert any("Very loud" in x for x in t) and any("Add references" in x for x in t)
    assert recs[-1].severity == NOTE  # the nudge to add references never outranks a real finding


def test_mono_cancellation_and_phone_clarity_are_called_out():
    f = {("corr", "low"): -0.3, ("csi_phone_delta", ""): -0.4, ("duck_depth_true", ""): -1.0}
    t = titles(recommend(None, f, [], [], {}, True))
    assert any("low end may cancel" in x for x in t)
    assert any("small speakers" in x for x in t)
    assert any("doesn't duck" in x for x in t)


def test_deviations_become_actions_and_hints_are_not_duplicated():
    results = [
        DeviationResult("csi", "", 0.2, -3.2, "flag", "low"),
        DeviationResult("pump_depth", "", 9.0, 2.9, "flag", "high"),
    ]
    rules = {"csi_low": {"id": "csi_low", "conditions": [{"feature": "csi", "direction": "low"}], "message": "Consonants masked. Check the 2-5 kHz."}}
    recs = recommend(None, {}, results, [{"id": "csi_low", "message": rules["csi_low"]["message"]}], rules, True)
    t = titles(recs)
    assert t.count("Consonants masked") == 1                       # the curated hint
    assert not any("Consonant survival" in x for x in t)           # not repeated as a raw deviation
    pump = next(r for r in recs if "Pumping" in r.title)
    assert pump.severity == FIX and "release" in pump.action


def test_fixes_sort_before_checks_before_notes():
    recs = recommend(
        checks(("true_peak", "warn", -0.5, None, None, "mix"), ("clip_runs", "fail", 1.0, 1.0, 1.0, "mix")),
        {}, [], [], {}, False,
    )
    sev = [r.severity for r in recs]
    assert sev == sorted(sev, key=["fix", "check", "note"].index)


def test_advice_quotes_units_and_the_reference_range_without_z_scores():
    results = [DeviationResult("lufs_i", "", -16.1, -8.5, "flag", "low", ref_low=-12.0, ref_high=-9.0)]
    recs = recommend(None, {}, results, [], {}, True)
    r = next(x for x in recs if "loud" in x.title.lower())
    assert "-16.1 LUFS" in r.evidence and "-12.0 LUFS to -9.0 LUFS" in r.evidence and "z" not in r.evidence.replace("references", "")


def test_a_hint_and_its_sanity_twin_appear_once():
    f = {("duck_depth_true", ""): -1.0}
    results = [DeviationResult("duck_depth_true", "", -1.0, 0.0, "ok", "ok")]
    rules = {"duck": {"id": "duck", "conditions": [{"feature": "duck_depth_true", "direction": "low_abs"}], "message": "Reverb isn't ducking under the dry vocal. Add sidechain."}}
    recs = recommend(None, f, results, [{"id": "duck", "message": rules["duck"]["message"]}], rules, True)
    assert sum("duck" in r.title.lower() or "duck" in r.action.lower() for r in recs) == 1


def test_tonal_band_advice_names_the_frequency_and_the_move():
    results = [DeviationResult("ltas", "250.0Hz", 6.0, 3.0, "flag", "high", ref_low=0.0, ref_high=3.0)]
    r = recommend(None, {}, results, [], {}, True)[0]
    assert "250 Hz" in r.action and "cut" in r.action
