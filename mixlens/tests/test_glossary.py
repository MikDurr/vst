"""Every feature the pipeline can emit or a hint can name should be explainable in the UI."""
import numpy as np

from mixlens.compare.glossary import GLOSSARY, explain, feature_name, trend_note


def test_every_hint_feature_has_an_explanation(cfg):
    for rule in cfg.get("hints"):
        for cond in rule["conditions"]:
            assert feature_name(cond["feature"]) != cond["feature"], cond["feature"]
            for other in (cond.get("other"),):
                if other:
                    assert feature_name(other) != other


def test_every_extracted_feature_is_in_the_glossary(cfg):
    from mixlens.features.registry import extract_whole_mix, extract_vocal_inst_pair

    rng = np.random.default_rng(0)
    sr = 44100
    x = (0.1 * rng.standard_normal((2, sr * 3))).astype(np.float32)
    names = {r.feature for r in extract_whole_mix(x, sr, cfg)}
    names |= {r.feature for r in extract_vocal_inst_pair(x, x * 0.5, sr, cfg)}
    missing = sorted(n for n in names if feature_name(n) == n)
    assert not missing, missing


def test_true_suffix_and_direction_text():
    assert "true stems" in feature_name("vir_med_true")
    assert explain("csi", "low") and explain("csi", "high") and explain("csi", "ok") == ""


def test_trend_note_does_not_overread_noise():
    assert "unchanged" in trend_note("csi", 0.600, 0.601).lower()
    assert "Moving toward" in trend_note("vir_med", -3, -1)
    assert "FAIL" in trend_note("true_peak", -1, 0.4)
