"""Plotly figures shared across UI pages."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

import theme
from mixlens.compare.glossary import feature_name


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
    fig.update_layout(title=feature_name(feature), xaxis_title="version", yaxis_title=feature)
    return theme.style_figure(fig)


def effect_size_bar_figure(regret_df: pd.DataFrame, top_n: int = 20) -> go.Figure:
    sub = regret_df.head(top_n).iloc[::-1]
    colors = [theme.PINK if d > 0 else theme.CYAN for d in sub["delta"]]
    labels = [feature_name(f) + (f" [{b}]" if b else "") for f, b in zip(sub["feature"], sub["band"])]
    fig = go.Figure(go.Bar(x=sub["delta"], y=labels, orientation="h", marker_color=colors))
    fig.update_layout(title="Regret signature: Cliff's delta (regret vs held_up)", xaxis_title="delta")
    return theme.style_figure(fig)
