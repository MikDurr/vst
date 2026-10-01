"""Instrumental mode: mix-only songs, accompaniment-based reference envelopes."""
import numpy as np
import pytest
import soundfile as sf
import yaml

from mixlens import pipeline
from mixlens.db.repo import Repo
from mixlens.io.sidecar import RefEntry, load_song_yaml
from mixlens.io.stems import find_stem_set, load_stem_set

SR = 44100


def _noise_wav(path, seed=0, secs=3):
    rng = np.random.default_rng(seed)
    t = np.arange(SR * secs) / SR
    x = 0.1 * np.sin(2 * np.pi * 110 * t)[:, None] + 0.02 * rng.standard_normal((SR * secs, 2))
    sf.write(path, x.astype("float32"), SR, subtype="PCM_24")


def _instrumental_song(tmp_path):
    d = tmp_path / "mixes" / "beat"
    d.mkdir(parents=True)
    _noise_wav(d / "beat__v1__mix.wav")
    (d / "song.yaml").write_text(yaml.dump({"song": "beat", "style": "dream", "bpm": 120, "instrumental": True}))
    return d


def test_song_yaml_flag_and_mix_only_loading(tmp_path):
    d = _instrumental_song(tmp_path)
    assert load_song_yaml(d).instrumental is True
    with pytest.raises(FileNotFoundError):
        find_stem_set(d, "v1")  # a normal song still needs all four
    s = load_stem_set(d, "v1", SR, instrumental=True)
    assert s.vox_dry is None and set(s.as_dict()) == {"mix"}


def test_instrumental_analysis_skips_demucs_and_vocal_features(tmp_path, cfg, monkeypatch):
    d = _instrumental_song(tmp_path)

    def boom(*a, **k):
        raise AssertionError("Demucs must not run for an instrumental")

    monkeypatch.setattr(pipeline, "_demucs_split", boom)
    repo = Repo(tmp_path / "t.db")
    result = pipeline.analyze_version(d, "v1", cfg, repo, tmp_path / ".cache")
    assert not result["skipped"]
    feats = set(repo.get_features(entity="version")["feature"])
    assert {"ltas", "lufs_i", "st_crest", "air_ratio", "flat_top_ratio"} <= feats
    assert not {"csi", "vir_med", "space_contrast", "vox_floor_true", "wet_dry_true"} & feats
    assert repo.get_song("beat")["instrumental"] is True


def test_reference_gets_accompaniment_row_and_envelopes(tmp_path, cfg, monkeypatch):
    refs = tmp_path / "references"
    (refs / "dream").mkdir(parents=True)
    repo = Repo(tmp_path / "t.db")

    def fake_split(mix, sr, cache, tag):
        return mix * 0.0 + 0.001, mix * 0.5  # (vocal, accompaniment)

    monkeypatch.setattr(pipeline, "_demucs_split", fake_split)
    for i in range(3):
        _noise_wav(refs / "dream" / f"r{i}.wav", seed=i)
        pipeline.analyze_reference(RefEntry(f"dream/r{i}.wav", "dream", "a", "t"), refs, cfg, repo, tmp_path)

    all_refs = repo.list_refs()
    assert sorted(set(all_refs["style"])) == ["dream", "dream::instrumental"]
    assert all_refs["path"].str.endswith("#accompaniment").sum() == 3

    built = pipeline.build_style_envelopes(repo, "dream")
    assert set(built) == {"dream", "dream::instrumental"}
    plain = {k: v for k, v in repo.get_envelopes("dream").items() if k[0] == "lufs_i"}
    acc = {k: v for k, v in repo.get_envelopes("dream::instrumental").items() if k[0] == "lufs_i"}
    # the accompaniment is quieter than the full mix by construction
    assert acc[("lufs_i", "")].med < plain[("lufs_i", "")].med
    # and it holds only whole-mix measurements, no vocal ones
    assert not any(k[0] in ("csi", "vir_med") for k in repo.get_envelopes("dream::instrumental"))


def test_old_database_gains_instrumental_column(tmp_path):
    import sqlite3

    db = tmp_path / "old.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE songs (song_id TEXT PRIMARY KEY, style TEXT, bpm REAL)")
    con.execute("INSERT INTO songs VALUES ('x', 'dream', 120)")
    con.commit()
    con.close()
    repo = Repo(db)
    assert repo.get_song("x") == {"style": "dream", "bpm": 120.0, "instrumental": False}


def test_deleting_a_version_and_a_reference_cleans_the_database(tmp_path, cfg, monkeypatch):
    repo = Repo(tmp_path / "t.db")
    repo.upsert_song("s", "dream", 120)
    vid = repo.upsert_version("s", "v1", "h", "c")
    from mixlens.types import FeatureRow
    repo.insert_features("version", vid, [FeatureRow("lufs_i", -10.0)])
    repo.set_label(vid, "regret")
    repo.delete_version("s", "v1")
    assert repo.get_all_versions().empty and repo.get_features().empty and repo.get_labels().empty and repo.get_song("s") is None

    rid = repo.upsert_ref("dream/a.wav", "dream", "", "", "h", "")
    aid = repo.upsert_ref("dream/a.wav#accompaniment", "dream::instrumental", "", "", "h", "")
    repo.insert_features("ref", rid, [FeatureRow("lufs_i", -9.0)])
    repo.insert_features("ref", aid, [FeatureRow("lufs_i", -10.0)])
    repo.delete_ref("dream/a.wav")
    assert repo.list_refs().empty and repo.get_features().empty


def test_remove_reference_from_yaml_and_disk(tmp_path):
    from mixlens.io.sidecar import load_references_yaml, remove_reference
    from mixlens.io.ingest import save_references
    import io as _io
    import soundfile as sf
    buf = _io.BytesIO(); sf.write(buf, np.zeros((100, 2), dtype="float32"), 44100, format="WAV")
    save_references(tmp_path, "dream", [("a.wav", buf.getvalue()), ("b.wav", buf.getvalue())])
    remove_reference(tmp_path, "dream/a.wav")
    assert [e.path for e in load_references_yaml(tmp_path)] == ["dream/b.wav"] and not (tmp_path / "dream" / "a.wav").exists()


def test_repo_survives_its_database_file_being_deleted(tmp_path):
    db = tmp_path / "t.db"
    repo = Repo(db)
    repo.upsert_song("s", "dream", 120)
    db.unlink()                                  # e.g. a reset while the app is running
    assert repo.get_all_versions().empty         # reconnects to a fresh database, no I/O error
    repo.upsert_song("s2", "dream", 120)
    assert repo.get_song("s2") is not None and db.exists()
