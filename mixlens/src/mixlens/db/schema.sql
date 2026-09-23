-- MixLens database (spec section 5). Long format; new features need no migration.

CREATE TABLE IF NOT EXISTS songs (
    song_id TEXT PRIMARY KEY,
    style TEXT,
    bpm REAL
);

CREATE TABLE IF NOT EXISTS versions (
    version_id INTEGER PRIMARY KEY,
    song_id TEXT,
    version TEXT,
    analyzed_at TEXT,
    stem_hash TEXT,
    config_hash TEXT,
    UNIQUE(song_id, version)
);

CREATE TABLE IF NOT EXISTS refs (
    ref_id INTEGER PRIMARY KEY,
    path TEXT UNIQUE,
    style TEXT,
    artist TEXT,
    title TEXT,
    audio_hash TEXT,
    note TEXT
);

CREATE TABLE IF NOT EXISTS features (
    entity TEXT CHECK(entity IN ('version','ref')),
    entity_id INTEGER,
    feature TEXT,
    band TEXT,
    value REAL,
    PRIMARY KEY(entity, entity_id, feature, band)
);

CREATE TABLE IF NOT EXISTS checks (
    version_id INTEGER,
    check_name TEXT,
    level TEXT,
    value REAL,
    t_sec REAL,
    bar REAL,
    stem TEXT
);

CREATE TABLE IF NOT EXISTS envelopes (
    style TEXT,
    feature TEXT,
    band TEXT,
    med REAL,
    p10 REAL,
    p90 REAL,
    iqr REAL,
    n INTEGER,
    PRIMARY KEY(style, feature, band)
);

CREATE TABLE IF NOT EXISTS labels (
    version_id INTEGER PRIMARY KEY,
    rating TEXT CHECK(rating IN ('held_up','neutral','regret')),
    tag TEXT,
    note TEXT,
    labeled_at TEXT
);
