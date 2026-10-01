"""UI upload ingest: naming, format normalisation, song.yaml, reference registration."""
import io

import numpy as np
import pytest
import soundfile as sf
import yaml

from mixlens.io.ingest import save_references, save_stems, validate_name
from mixlens.io.sidecar import load_references_yaml, update_reference_meta
from mixlens.io.stems import STEM_NAMES, find_stem_set


def _wav_bytes(fmt="WAV"):
    buf = io.BytesIO()
    sf.write(buf, np.zeros((4410, 2), dtype="float32"), 44100, format=fmt)
    return buf.getvalue()


def test_save_stems_names_and_yaml(tmp_path):
    song_dir = save_stems(tmp_path, "neon-altar", "v1", "dream", 140, {s: _wav_bytes("FLAC") for s in STEM_NAMES})
    assert set(find_stem_set(song_dir, "v1")) == set(STEM_NAMES)
    meta = yaml.safe_load((song_dir / "song.yaml").read_text())
    assert meta["style"] == "dream" and meta["bpm"] == 140.0


def test_second_version_keeps_sections(tmp_path):
    stems = {s: _wav_bytes() for s in STEM_NAMES}
    d = save_stems(tmp_path, "s", "v1", "dream", 120, stems)
    (d / "song.yaml").write_text(yaml.dump({"song": "s", "style": "dream", "bpm": 120, "sections": {"a": [0, 5]}}))
    save_stems(tmp_path, "s", "v2", "dream", 120, stems)
    assert yaml.safe_load((d / "song.yaml").read_text())["sections"] == {"a": [0, 5]}


def test_missing_stem_and_bad_names(tmp_path):
    with pytest.raises(ValueError):
        save_stems(tmp_path, "s", "v1", "dream", 120, {"mix": _wav_bytes()})
    for bad in ("my_song", "a b", "../x", ""):
        with pytest.raises(ValueError):
            validate_name("Song", bad)


def test_references_saved_registered_and_editable(tmp_path):
    added = save_references(tmp_path, "dream", [("a.wav", _wav_bytes()), ("b.wav", _wav_bytes())])
    assert len(added) == 2 and (tmp_path / "dream" / "a.wav").exists()
    assert save_references(tmp_path, "dream", [("a.wav", _wav_bytes())]) == []
    update_reference_meta(tmp_path, "dream/a.wav", "Artist", "Title", "deep verb")
    row = [e for e in load_references_yaml(tmp_path) if e.path == "dream/a.wav"][0]
    assert (row.artist, row.note) == ("Artist", "deep verb")


def test_guess_stem_from_common_export_names():
    from mixlens.io.ingest import assign_stems, guess_song_version, guess_stem

    assert guess_stem("neon_altar__v3__vox_dry.wav") == "vox_dry"
    assert guess_stem("Neon Altar - Vocal Dry.wav") == "vox_dry"
    assert guess_stem("Neon Altar - Vox Wet (Reverb Returns).wav") == "vox_wet"
    assert guess_stem("neon_altar_instrumental.flac") == "inst"
    assert guess_stem("Neon Altar FINAL MASTER.wav") == "mix"
    assert guess_stem("bounce123.wav") == "mix"
    assert guess_stem("untitled.wav") is None
    assert guess_song_version(["neon_altar__v3__mix.wav"]) == ("neon_altar", "v3")


def test_assign_stems_never_double_books_a_slot():
    from mixlens.io.ingest import assign_stems

    got = assign_stems(["a_vox_dry.wav", "b_vocal.wav", "c_inst.wav"])
    assert got["a_vox_dry.wav"] == "vox_dry"
    assert got["b_vocal.wav"] is None
    assert got["c_inst.wav"] == "inst"


def _stereo_wav(x, sr=44100):
    buf = io.BytesIO()
    sf.write(buf, x, sr, format="WAV", subtype="PCM_24")
    return buf.getvalue()


def _synth(seed=0, n=44100 * 4):
    """Bursty band-limited noise as a stand-in vocal (a pure tone would make the
    alignment check ambiguous), with a noise-burst reverb as its returns."""
    rng = np.random.default_rng(seed)
    t = np.arange(n) / 44100
    env = np.clip(np.sin(2 * np.pi * 1.5 * t), 0, None)[:, None]
    dry = 0.08 * env * rng.standard_normal((n, 2))
    ir = np.exp(-np.arange(6000) / 1200) * rng.standard_normal(6000) * 0.03
    wet = np.stack([np.convolve(dry[:, c], ir)[:n] for c in range(2)], axis=1)
    return dry, wet


def test_derive_wet_recovers_the_returns():
    from mixlens.io.ingest import derive_wet

    dry, wet = _synth()
    out, warnings = derive_wet(_stereo_wav(dry + wet), _stereo_wav(dry))
    got, _ = sf.read(io.BytesIO(out), dtype="float64", always_2d=True)
    assert warnings == []
    assert np.max(np.abs(got - wet)) < 1e-4


def test_derive_wet_rejects_misaligned_and_mismatched_bounces():
    from mixlens.io.ingest import derive_wet

    dry, wet = _synth()
    full = dry + wet
    shifted = np.roll(full, 200, axis=0)
    with pytest.raises(ValueError, match="offset"):
        derive_wet(_stereo_wav(shifted), _stereo_wav(dry))
    with pytest.raises(ValueError, match="length"):
        derive_wet(_stereo_wav(full[:-44100]), _stereo_wav(dry))
    with pytest.raises(ValueError, match="sample rate|Hz"):
        derive_wet(_stereo_wav(full, 48000), _stereo_wav(dry, 44100))


def test_derive_wet_warns_when_dry_does_not_cancel_or_returns_absent():
    from mixlens.io.ingest import derive_wet

    dry, wet = _synth()
    _, w1 = derive_wet(_stereo_wav(dry), _stereo_wav(dry))
    assert any("silent" in w or "identical" in w for w in w1)
    _, w2 = derive_wet(_stereo_wav(dry * 2.5 + wet), _stereo_wav(dry))  # dry level differs between bounces
    assert w2


def test_guess_stem_recognises_vox_full():
    from mixlens.io.ingest import guess_stem

    assert guess_stem("Neon Altar - Vocal Full (with FX).wav") == "vox_full"
    assert guess_stem("neon_altar_vox_all.wav") == "vox_full"
    assert guess_stem("neon_altar_full_mix.wav") == "mix"
    assert guess_stem("vox_dry.wav") == "vox_dry"


def test_derive_wet_rejects_gross_offset():
    from mixlens.io.ingest import derive_wet

    dry, wet = _synth()
    with pytest.raises(ValueError, match="offset"):
        derive_wet(_stereo_wav(np.roll(dry + wet, 30000, axis=0)), _stereo_wav(dry))


def test_save_stems_instrumental_needs_only_mix(tmp_path):
    d = save_stems(tmp_path, "beat", "v1", "dream", 128, {"mix": _wav_bytes()}, instrumental=True)
    assert [p.name for p in d.glob("*.wav")] == ["beat__v1__mix.wav"]
    assert yaml.safe_load((d / "song.yaml").read_text())["instrumental"] is True
    with pytest.raises(ValueError):  # a normal song still requires all four
        save_stems(tmp_path, "vox", "v1", "dream", 128, {"mix": _wav_bytes()})
