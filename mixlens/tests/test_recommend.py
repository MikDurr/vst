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
