"""Typer entry point: `mixlens ref|check|analyze|report|diff|label|regret|ui`."""
from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from mixlens.checks.peaks import any_fail
from mixlens.compare.envelope import build_envelopes, leave_one_out_audit
from mixlens.compare.deviation import classify_level
from mixlens.compare.regret import compare_groups
from mixlens.config import load_config
from mixlens.db.repo import Repo
from mixlens.io.sidecar import load_references_yaml, register_references
from mixlens.pipeline import analyze_reference, analyze_version, build_hints, run_checks_only, score_version_against_envelopes

app = typer.Typer(add_completion=False, help="MixLens: measure your mix against reference tracks.")
ref_app = typer.Typer(help="Manage reference tracks and style envelopes.")
app.add_typer(ref_app, name="ref")

console = Console()

PROJECT_ROOT = Path.cwd()


def _config_path_option() -> Path:
    return PROJECT_ROOT / "config.yaml"


def _db_path() -> Path:
    return PROJECT_ROOT / "mixlens.db"


def _references_dir() -> Path:
    return PROJECT_ROOT / "references"


# --------------------------------------------------------------------------
# ref
# --------------------------------------------------------------------------


@ref_app.command("add")
def ref_add(
    patterns: list[str] = typer.Argument(..., help="Glob(s) of audio files to register, e.g. references/dream/*.flac"),
    style: str = typer.Option(..., "--style", help="dream | hyperpop | electroclash"),
):
    """Register audio files into references/references.yaml (does not analyze them)."""
    refs_dir = _references_dir()
    new_entries = register_references(patterns, style, refs_dir)

    if not new_entries:
        console.print("No new references to add.")
        raise typer.Exit()

    console.print(f"Added {len(new_entries)} references to {refs_dir / 'references.yaml'}. Fill in artist/title/note by hand.")


@ref_app.command("build-envelopes")
def ref_build_envelopes():
    """Analyze every registered reference not yet in the DB, then rebuild envelopes per style."""
    cfg = load_config(_config_path_option())
    repo = Repo(_db_path())
    entries = load_references_yaml(_references_dir())
    if not entries:
        console.print("[yellow]No references registered. Run `mixlens ref add` first.[/yellow]")
        raise typer.Exit(1)

    for entry in entries:
        result = analyze_reference(entry, _references_dir(), cfg, repo, PROJECT_ROOT / ".cache")
        console.print(f"Analyzed {result['path']} ({result['style']}): {result['n_features']} feature rows")

    styles = sorted({e.style for e in entries})
    for style in styles:
        df = repo.get_features_for_style(style, entity="ref")
        envelopes = build_envelopes(df)
        repo.replace_envelopes(style, envelopes)
        console.print(f"Built {len(envelopes)} envelope entries for style '{style}'")


@ref_app.command("audit")
def ref_audit():
    """Leave-one-out audit: score each reference against an envelope built from the others."""
    cfg = load_config(_config_path_option())
    repo = Repo(_db_path())
    entries = load_references_yaml(_references_dir())
    styles = sorted({e.style for e in entries})

    for style in styles:
        df = repo.get_features_for_style(style, entity="ref")
        if df.empty:
            continue
        result_df = leave_one_out_audit(df, style, lambda v, env: classify_level(v, env, cfg))
        table = Table(title=f"Leave-one-out audit: {style}")
        table.add_column("ref_id")
        table.add_column("n_flags")
        table.add_column("flagged features")
        for _idx, row in result_df.sort_values("n_flags", ascending=False).iterrows():
            style_flag = "[red]" if row["n_flags"] > 3 else ""
            table.add_row(str(row["entity_id"]), f"{style_flag}{row['n_flags']}", ", ".join(row["flagged"][:6]))
        console.print(table)
        console.print("References with > 3 flags may belong to another style or be outliers worth dropping.\n")


# --------------------------------------------------------------------------
# check / analyze
# --------------------------------------------------------------------------


@app.command()
def check(mix_dir: str = typer.Argument(...), version: str = typer.Option(..., "--version")):
    """Peak safety only, fast."""
    cfg = load_config(_config_path_option())
    results, song = run_checks_only(mix_dir, version, cfg)
    _print_check_table(results, f"{song.song} {version}")
    if any_fail(results):
        raise typer.Exit(1)


@app.command()
def analyze(mix_dir: str = typer.Argument(...), version: str = typer.Option(..., "--version"), force: bool = typer.Option(False, "--force")):
    """Checks + all features (reference path via Demucs + internal path)."""
    cfg = load_config(_config_path_option())
    repo = Repo(_db_path())
    result = analyze_version(mix_dir, version, cfg, repo, PROJECT_ROOT / ".cache", force=force)
    if result.get("skipped"):
        console.print(f"[dim]Skipped {result['song']} {result['version']}: {result['reason']}[/dim]")
        return
    console.print(
        f"Analyzed {result['song']} {result['version']}: {result['n_checks']} checks, {result['n_features']} feature rows"
    )


# --------------------------------------------------------------------------
# report / diff
# --------------------------------------------------------------------------


@app.command()
def report(song: str = typer.Argument(...), version: str = typer.Argument(...)):
    """Safety table, flag table, hints for one analyzed version."""
    cfg = load_config(_config_path_option())
    repo = Repo(_db_path())
    versions = repo.get_versions_for_song(song)
    row = versions[versions["version"] == version]
    if row.empty:
        console.print(f"[red]No analyzed version {song} {version}. Run `mixlens analyze` first.[/red]")
        raise typer.Exit(1)
    version_id = int(row.iloc[0]["version_id"])

    checks_df = repo.get_checks(version_id)
    _print_checks_df(checks_df, f"{song} {version}")

    songs_df_style = _song_style(repo, song)
    if songs_df_style is None:
        console.print("[yellow]Unknown style; skipping envelope comparison.[/yellow]")
        return

    results = score_version_against_envelopes(repo, version_id, songs_df_style, cfg)
    table = Table(title=f"Deviation: {song} {version} vs style '{songs_df_style}'")
    table.add_column("feature")
    table.add_column("band")
    table.add_column("value")
    table.add_column("z")
    table.add_column("level")
    for r in sorted(results, key=lambda r: -abs(r.z)):
        if r.level == "ok":
            continue
        color = "red" if r.level == "flag" else "yellow"
        table.add_row(r.feature, r.band, f"{r.value:.2f}", f"{r.z:.2f}", f"[{color}]{r.level}[/{color}]")
    console.print(table)

    hints = build_hints(results, repo, version_id, cfg)
    if hints:
        console.print("\n[bold]Hints[/bold]")
        for h in hints:
            console.print(f"  - {h['message']}")


@app.command()
def diff(song: str = typer.Argument(...), version_a: str = typer.Argument(...), version_b: str = typer.Argument(...)):
    """Show feature deltas between two analyzed versions of the same song."""
    repo = Repo(_db_path())
    versions = repo.get_versions_for_song(song)
    id_a = versions[versions["version"] == version_a]
    id_b = versions[versions["version"] == version_b]
    if id_a.empty or id_b.empty:
        console.print(f"[red]Both versions must be analyzed first.[/red]")
        raise typer.Exit(1)
    feats_a = repo.get_features(entity="version", entity_id=int(id_a.iloc[0]["version_id"])).set_index(["feature", "band"])["value"]
    feats_b = repo.get_features(entity="version", entity_id=int(id_b.iloc[0]["version_id"])).set_index(["feature", "band"])["value"]

    table = Table(title=f"{song}: {version_a} -> {version_b}")
    table.add_column("feature")
    table.add_column("band")
    table.add_column(version_a)
    table.add_column(version_b)
    table.add_column("delta")
    common = sorted(set(feats_a.index) & set(feats_b.index))
    for key in common:
        va, vb = feats_a[key], feats_b[key]
        delta = vb - va
        if abs(delta) < 1e-6:
            continue
        feature, band = key
        table.add_row(feature, band, f"{va:.2f}", f"{vb:.2f}", f"{delta:+.2f}")
    console.print(table)


# --------------------------------------------------------------------------
# label / regret
# --------------------------------------------------------------------------


@app.command()
def label(
    song: str = typer.Argument(...),
    version: str = typer.Argument(...),
    rating: str = typer.Argument(..., help="held_up | neutral | regret"),
    tag: str = typer.Option("", "--tag"),
    note: str = typer.Option("", "--note"),
):
    """Label an analyzed version for the regret analysis."""
    if rating not in ("held_up", "neutral", "regret"):
        console.print("[red]rating must be held_up, neutral, or regret[/red]")
        raise typer.Exit(1)
    repo = Repo(_db_path())
    versions = repo.get_versions_for_song(song)
    row = versions[versions["version"] == version]
    if row.empty:
        console.print(f"[red]No analyzed version {song} {version}.[/red]")
        raise typer.Exit(1)
    repo.set_label(int(row.iloc[0]["version_id"]), rating, tag=tag, note=note)
    console.print(f"Labeled {song} {version} as {rating}.")


@app.command()
def regret():
    """Effect-size ranking between held_up and regret groups (needs >=5 labeled each)."""
    repo = Repo(_db_path())
    labels_df = repo.get_labels()
    all_versions = repo.get_all_versions()
    features_df = repo.get_features(entity="version")
    try:
        result = compare_groups(features_df, labels_df)
    except ValueError as e:
        console.print(f"[yellow]{e}[/yellow]")
        raise typer.Exit(1)

    table = Table(title="Regret analysis: ranked by |Cliff's delta|")
    table.add_column("feature")
    table.add_column("band")
    table.add_column("held_up median")
    table.add_column("regret median")
    table.add_column("delta")
    table.add_column("direction")
    for _idx, row in result.head(25).iterrows():
        table.add_row(
            row["feature"], row["band"], f"{row['held_up_median']:.2f}", f"{row['regret_median']:.2f}",
            f"{row['delta']:+.2f}", row["direction"],
        )
    console.print(table)


@app.command()
def ui():
    """Launch the Streamlit UI."""
    import subprocess

    ui_app = Path(__file__).resolve().parents[2] / "ui" / "app.py"
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(ui_app)])


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _song_style(repo: Repo, song: str) -> str | None:
    import pandas as pd

    with repo.cursor() as cur:
        cur.execute("SELECT style FROM songs WHERE song_id=?", (song,))
        row = cur.fetchone()
    return row[0] if row else None


def _print_check_table(results, title: str) -> None:
    table = Table(title=f"Peak safety: {title}")
    table.add_column("check")
    table.add_column("level")
    table.add_column("value")
    table.add_column("t_sec")
    table.add_column("bar")
    table.add_column("stem")
    for r in results:
        color = {"fail": "red", "warn": "yellow", "ok": "green"}[r.level]
        table.add_row(
            r.check, f"[{color}]{r.level}[/{color}]", f"{r.value:.3f}",
            f"{r.t_sec:.2f}" if r.t_sec is not None else "-",
            f"{r.bar:.1f}" if r.bar is not None else "-", r.stem,
        )
    console.print(table)


def _print_checks_df(df, title: str) -> None:
    table = Table(title=f"Peak safety: {title}")
    table.add_column("check")
    table.add_column("level")
    table.add_column("value")
    table.add_column("bar")
    table.add_column("stem")
    for _idx, r in df.iterrows():
        color = {"fail": "red", "warn": "yellow", "ok": "green"}.get(r["level"], "white")
        table.add_row(
            r["check_name"], f"[{color}]{r['level']}[/{color}]", f"{r['value']:.3f}",
            f"{r['bar']:.1f}" if r["bar"] is not None else "-", r["stem"],
        )
    console.print(table)


if __name__ == "__main__":
    app()
