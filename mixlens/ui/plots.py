"""Plotly figures shared across UI pages."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

import theme
from mixlens.compare.glossary import UNITS, feature_name


def ltas_vs_envelope_figure(version_ltas: pd.DataFrame, envelope_df: pd.DataFrame) -> go.Figure:
    """LTAS band values (x = band center Hz) vs style p10-p90 shaded band."""
    env = envelope_df[envelope_df["feature"] == "ltas"].copy()
    env["hz"] = env["band"].str.replace("Hz", "", regex=False).astype(float)
    env = env.sort_values("hz")

    mix = version_ltas[version_ltas["feature"] == "ltas"].copy()
    mix["hz"] = mix["band"].str.replace("Hz", "", regex=False).astype(float)
    mix = mix.sort_values("hz")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=env["hz"], y=env["p90"], mode="lines", line=dict(width=0), showlegend=False))
    fig.add_trace(
        go.Scatter(
            x=env["hz"], y=env["p10"], mode="lines", fill="tonexty", line=dict(width=0),
            fillcolor="rgba(28,243,243,0.20)", name="style p10-p90",
        )
    )
    fig.add_trace(go.Scatter(x=env["hz"], y=env["med"], mode="lines", name="style median", line=dict(dash="dot", color="#FFFFFF", width=2)))
    fig.add_trace(go.Scatter(x=mix["hz"], y=mix["value"], mode="lines+markers", name="your mix", line=dict(color=theme.LIME, width=4), marker=dict(size=8, color=theme.LIME, line=dict(color=theme.BG, width=2))))
    fig.update_layout(xaxis_type="log", xaxis_title="Hz", yaxis_title="dB (250Hz-4kHz = 0)", title="Tonal balance vs references")
    return theme.style_figure(fig)


def csi_timeline_figure(times: list[float], scores: list[float], sections: dict[str, tuple[float, float]] | None = None) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=times, y=scores, mode="lines+markers", name="CSI per onset", line=dict(color=theme.LIME, width=3), marker=dict(color=theme.CYAN, size=9)))
    if sections:
        for name, (start, end) in sections.items():
            fig.add_vrect(x0=start, x1=end, annotation_text=name, fillcolor="white", opacity=0.07, line_width=0)
    fig.update_layout(title="Consonant Survival Index timeline", xaxis_title="time (s)", yaxis_title="CSI (fraction of bands surviving)")
    return theme.style_figure(fig)


def space_sheen_scatter(rows: pd.DataFrame) -> go.Figure:
    """rows: columns entity ('yours'/'ref'), space_contrast, air_ratio, label."""
    fig = go.Figure()
    for entity, group in rows.groupby("entity"):
        fig.add_trace(
            go.Scatter(
                x=group["space_contrast"], y=group["air_ratio"], mode="markers",
                name=entity, text=group.get("label", None),
                marker=dict(size=22 if entity == "yours" else 11, symbol="star" if entity == "yours" else "circle",
                            color=theme.LIME if entity == "yours" else "rgba(155,61,255,0.85)",
                            line=dict(color="#fff" if entity == "yours" else theme.LAVENDER, width=2 if entity == "yours" else 1)),
            )
        )
    fig.update_layout(title="Space vs sheen", xaxis_title="space_contrast (dB/s)", yaxis_title="air_ratio (dB)")
    return theme.style_figure(fig)


def history_line_figure(df: pd.DataFrame, feature: str) -> go.Figure:
    """df: columns version (ordered), value."""
    sub = df[df["feature"] == feature]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=sub["version"], y=sub["value"], mode="lines+markers", name=feature, line=dict(color=theme.LIME, width=4), marker=dict(size=11, color=theme.CYAN, line=dict(color=theme.BG, width=2))))
    unit = UNITS.get(feature, "")
    fig.update_layout(title=feature_name(feature), xaxis_title="version", yaxis_title=f"{feature_name(feature)}" + (f" ({unit})" if unit else ""))
    return theme.style_figure(fig)


def effect_size_bar_figure(regret_df: pd.DataFrame, top_n: int = 20) -> go.Figure:
    sub = regret_df.head(top_n).iloc[::-1]
    colors = [theme.PINK if d > 0 else theme.CYAN for d in sub["delta"]]
    labels = [feature_name(f) + (f" [{b}]" if b else "") for f, b in zip(sub["feature"], sub["band"])]
    fig = go.Figure(go.Bar(x=sub["delta"], y=labels, orientation="h", marker_color=colors))
    fig.update_layout(title="Regret signature: Cliff's delta (regret vs held_up)", xaxis_title="delta")
    return theme.style_figure(fig)


def range_figure(rows, title: str, formatter, height: int | None = None) -> go.Figure:
    """One line per row: the shaded band is where your references sit (their middle 80%),
    the lime marker is you. Without references only the markers show."""
    fig = go.Figure()
    labels = [r.label for r in rows][::-1]
    for i, r in enumerate(rows[::-1]):
        if r.lo is not None and r.hi is not None:
            fig.add_shape(type="rect", x0=r.lo, x1=r.hi, y0=i - 0.32, y1=i + 0.32, line_width=0,
                          fillcolor="rgba(28,243,243,0.28)", layer="below")
    fig.add_trace(go.Scatter(
        x=[r.value for r in rows[::-1]], y=labels, mode="markers", name="you",
        marker=dict(size=16, color=theme.LIME, line=dict(color=theme.BG, width=3)),
        customdata=[formatter(r) for r in rows[::-1]],
        hovertemplate="%{y}<br>you: %{customdata}<extra></extra>",
    ))
    if any(r.med is not None for r in rows):
        fig.add_trace(go.Scatter(
            x=[r.med for r in rows[::-1]], y=labels, mode="markers", name="references (typical)",
            marker=dict(size=9, color="#FFFFFF", symbol="line-ns-open", line=dict(width=3, color="#FFFFFF")),
        ))
    fig.update_layout(title=title, yaxis=dict(automargin=True), showlegend=any(r.med is not None for r in rows))
    return theme.style_figure(fig, height=height or max(220, 70 + 52 * len(rows)))


def share_figure(share: dict) -> go.Figure:
    """Who owns each frequency range: a stacked bar for you, and one for your references' typical."""
    from mixlens.compare.balance import ORDER, STEM_LABEL

    ranges = ["sub", "bass", "low-mid", "mid", "high"]
    ranges = [r for r in ranges if r in share][::-1]
    colours = {"drums": theme.CORAL, "bass": theme.VIOLET, "other": theme.CYAN, "vocals": theme.LIME}
    fig = go.Figure()
    cats = []
    for r in ranges:
        cats += [f"{r} · references", f"{r} · you"] if any(v[1] is not None for v in share[r].values()) else [f"{r} · you"]
    for stem in ORDER:
        xs, ys = [], []
        for r in ranges:
            if stem not in share[r]:
                continue
            you, ref = share[r][stem]
            if ref is not None:
                ys.append(f"{r} · references"); xs.append(ref)
            ys.append(f"{r} · you"); xs.append(you)
        if xs:
            fig.add_trace(go.Bar(x=xs, y=ys, orientation="h", name=STEM_LABEL[stem], marker_color=colours[stem],
                                 hovertemplate="%{y}<br>" + STEM_LABEL[stem] + ": %{x:.0f}%<extra></extra>"))
    fig.update_layout(barmode="stack", title="Who owns each frequency range", xaxis_title="share of the range's energy (%)",
                      yaxis=dict(categoryorder="array", categoryarray=cats))
    return theme.style_figure(fig, height=max(320, 60 * len(cats) + 120))
