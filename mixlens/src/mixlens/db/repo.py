"""SQLite repository: insert/query helpers returning DataFrames or dataclasses."""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from mixlens.compare.envelope import Envelope
from mixlens.checks.peaks import CheckResult
from mixlens.types import FeatureRow

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class Repo:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: the UI (Streamlit) reruns the script on a
        # different worker thread each time and reuses one cached Repo across
        # reruns, so the connection must be usable from more than the thread
        # that created it. The lock below is what actually keeps access safe,
        # since sqlite3 connections still aren't safe for concurrent use.
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(SCHEMA_PATH.read_text())
        self._conn.commit()

    @contextmanager
    def cursor(self):
        with self._lock:
            cur = self._conn.cursor()
            try:
                yield cur
                self._conn.commit()
            finally:
                cur.close()

    def _read_sql(self, query: str, params=()) -> pd.DataFrame:
        with self._lock:
            return pd.read_sql_query(query, self._conn, params=params)

    def close(self) -> None:
        self._conn.close()

    # -- songs / versions -----------------------------------------------

    def upsert_song(self, song_id: str, style: str, bpm: float) -> None:
        with self.cursor() as cur:
            cur.execute(
                "INSERT INTO songs (song_id, style, bpm) VALUES (?, ?, ?) "
                "ON CONFLICT(song_id) DO UPDATE SET style=excluded.style, bpm=excluded.bpm",
                (song_id, style, bpm),
            )

    def upsert_version(self, song_id: str, version: str, stem_hash: str, config_hash: str) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self.cursor() as cur:
            cur.execute(
                "INSERT INTO versions (song_id, version, analyzed_at, stem_hash, config_hash) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(song_id, version) DO UPDATE SET "
                "analyzed_at=excluded.analyzed_at, stem_hash=excluded.stem_hash, config_hash=excluded.config_hash",
                (song_id, version, now, stem_hash, config_hash),
            )
            cur.execute("SELECT version_id FROM versions WHERE song_id=? AND version=?", (song_id, version))
            return cur.fetchone()[0]

    def get_version_stem_hash(self, song_id: str, version: str) -> str | None:
        with self.cursor() as cur:
            cur.execute("SELECT stem_hash FROM versions WHERE song_id=? AND version=?", (song_id, version))
            row = cur.fetchone()
            return row[0] if row else None

    # -- refs -------------------------------------------------------------

    def upsert_ref(self, path: str, style: str, artist: str, title: str, audio_hash: str, note: str) -> int:
        with self.cursor() as cur:
            cur.execute(
                "INSERT INTO refs (path, style, artist, title, audio_hash, note) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(path) DO UPDATE SET style=excluded.style, artist=excluded.artist, "
                "title=excluded.title, audio_hash=excluded.audio_hash, note=excluded.note",
                (path, style, artist, title, audio_hash, note),
            )
            cur.execute("SELECT ref_id FROM refs WHERE path=?", (path,))
            return cur.fetchone()[0]

    def list_refs(self, style: str | None = None) -> pd.DataFrame:
        q = "SELECT * FROM refs"
        params = ()
        if style:
            q += " WHERE style=?"
            params = (style,)
        return self._read_sql(q, params)

    # -- features / checks --------------------------------------------------

    def insert_features(self, entity: str, entity_id: int, rows: list[FeatureRow]) -> None:
        with self.cursor() as cur:
            cur.executemany(
                "INSERT INTO features (entity, entity_id, feature, band, value) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(entity, entity_id, feature, band) DO UPDATE SET value=excluded.value",
                [(entity, entity_id, r.feature, r.band, r.value) for r in rows],
            )

    def insert_checks(self, version_id: int, results: list[CheckResult]) -> None:
        with self.cursor() as cur:
            cur.executemany(
                "INSERT INTO checks (version_id, check_name, level, value, t_sec, bar, stem) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(version_id, r.check, r.level, r.value, r.t_sec, r.bar, r.stem) for r in results],
            )

    def get_features(self, entity: str | None = None, entity_id: int | None = None) -> pd.DataFrame:
        q = "SELECT * FROM features WHERE 1=1"
        params: list = []
        if entity:
            q += " AND entity=?"
            params.append(entity)
        if entity_id is not None:
            q += " AND entity_id=?"
            params.append(entity_id)
        return self._read_sql(q, params)

    def get_features_for_style(self, style: str, entity: str = "ref") -> pd.DataFrame:
        if entity == "ref":
            q = (
                "SELECT f.*, r.style AS style FROM features f "
                "JOIN refs r ON f.entity_id = r.ref_id AND f.entity='ref' "
                "WHERE r.style = ?"
            )
        else:
            q = (
                "SELECT f.*, s.style AS style FROM features f "
                "JOIN versions v ON f.entity_id = v.version_id AND f.entity='version' "
                "JOIN songs s ON v.song_id = s.song_id "
                "WHERE s.style = ?"
            )
        return self._read_sql(q, (style,))

    def get_checks(self, version_id: int) -> pd.DataFrame:
        return self._read_sql("SELECT * FROM checks WHERE version_id=?", (version_id,))

    # -- envelopes ------------------------------------------------------

    def replace_envelopes(self, style: str, envelopes: list[Envelope]) -> None:
        with self.cursor() as cur:
            cur.execute("DELETE FROM envelopes WHERE style=?", (style,))
            cur.executemany(
                "INSERT INTO envelopes (style, feature, band, med, p10, p90, iqr, n) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(e.style, e.feature, e.band, e.med, e.p10, e.p90, e.iqr, e.n) for e in envelopes],
            )

    def get_envelopes(self, style: str) -> dict[tuple[str, str], Envelope]:
        df = self._read_sql("SELECT * FROM envelopes WHERE style=?", (style,))
        out = {}
        for _idx, row in df.iterrows():
            out[(row["feature"], row["band"])] = Envelope(
                style=row["style"], feature=row["feature"], band=row["band"],
                med=row["med"], p10=row["p10"], p90=row["p90"], iqr=row["iqr"], n=int(row["n"]),
            )
        return out

    # -- labels -----------------------------------------------------------

    def set_label(self, version_id: int, rating: str, tag: str = "", note: str = "") -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.cursor() as cur:
            cur.execute(
                "INSERT INTO labels (version_id, rating, tag, note, labeled_at) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(version_id) DO UPDATE SET rating=excluded.rating, tag=excluded.tag, "
                "note=excluded.note, labeled_at=excluded.labeled_at",
                (version_id, rating, tag, note, now),
            )

    def get_labels(self) -> pd.DataFrame:
        return self._read_sql("SELECT * FROM labels")

    def get_versions_for_song(self, song_id: str) -> pd.DataFrame:
        return self._read_sql("SELECT * FROM versions WHERE song_id=? ORDER BY version_id", (song_id,))

    def get_all_versions(self) -> pd.DataFrame:
        return self._read_sql("SELECT * FROM versions")
