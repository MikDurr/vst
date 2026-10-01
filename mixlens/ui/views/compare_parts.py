"""The Instruments and Space & depth tabs on the Compare page."""
from __future__ import annotations

import pandas as pd
import streamlit as st

import theme
from mixlens.compare.balance import DEPTH_CUTS, RangeRow, describe
from mixlens.compare.glossary import format_value
from plots import range_figure, share_figure


def _fmt(r: RangeRow) -> str:
    return format_value(r.feature, r.value)


def _findings(rows: list[RangeRow], trusted: bool = True) -> None:
    """One plain line for each row that sits outside your references."""
    out = [r for r in rows if r.status not in ("", "in range")]
    if not out:
        if rows and rows[0].status and trusted:
            st.success("Everything here sits inside your references' range.")
        return
    for r in sorted(out, key=lambda r: -abs(r.z or 0)):
        direction = "high" if (r.z or 0) > 0 else "low"
        found = describe(r.feature, r.band, direction)
        st.markdown(f"- **{found[0] if found else r.label}.** {found[1] if found else ''}")


def reanalyze_callout(what: str, on_click) -> None:
    theme.callout(f"<b>{what}</b> This version was analyzed before instrument balance existed, so there's nothing to show yet.")
    st.button("Analyze this version again", type="primary", on_click=on_click, key="cmp_reanalyze")


def references_callout() -> None:
    theme.callout(
        "<b>Add or re-measure your references to compare.</b> Your references were measured before instrument balance "
        "existed (or there are none yet), so there's no range to compare against. On the References page, click "
        "<i>Measure</i> (tick 're-measure all' if they show as done)."
    )


def few_references_callout(n: int) -> None:
    theme.callout(
        f"<b>Only {n} reference{'s' if n != 1 else ''} so far.</b> With so few, your references' range is nearly a single "
        "point, so nothing can look out of range and the comparisons can't be trusted yet. Add more references for this style "
        "(at least 3, ideally 8 to 20) and measure them."
    )


def instruments_tab(report, instrumental: bool, n_refs: int = 99) -> None:
    trusted = n_refs >= 3
    theme.callout(
        "We split your mix into <b>drums, bass, synths/guitars/pads and vocals</b> so we can see how they sit together. "
        "The split is done by an AI separator, so it's approximate: treat small differences as noise, and trust big ones."
    )
    if not report.has_reference:
        references_callout()
    elif not trusted:
        few_references_callout(n_refs)

    st.markdown("##### How loud is each element?")
    st.caption("Level against the whole mix. The shaded band is where your references sit; the lime dot is you.")
    st.plotly_chart(range_figure(report.levels, "Level of each element (dB re the whole mix)", _fmt), use_container_width=True)
    _findings(report.levels, trusted)

    st.markdown("##### How wide is each element?")
    st.caption("Stereo width of each element. Higher means wider; very low means nearly mono.")
    st.plotly_chart(range_figure(report.widths, "Stereo width of each element (dB, side vs mid)", _fmt), use_container_width=True)
    _findings(report.widths, trusted)

    st.markdown("##### Who owns which frequencies?")
    st.caption("For each range, how the energy is split between the elements. If one element owns a range it doesn't "
               "normally own in your references, something else is probably being masked there.")
    if report.share:
        st.plotly_chart(share_figure(report.share), use_container_width=True)

    if report.low_end:
        st.markdown("##### Kick and bass")
        st.plotly_chart(range_figure(report.low_end, "The low end", _fmt), use_container_width=True)
        _findings(report.low_end, trusted)

    if report.masking:
        st.markdown("##### Who's crowding whom?")
        st.caption("How much two elements fill the same frequencies at the same time and level. Higher means more crowded, "
                   "so one is more likely to mask the other.")
        worst = sorted(report.masking, key=lambda r: -(r.z if r.z is not None else r.value))[:8]
        st.plotly_chart(range_figure(worst, "Most crowded pairs", _fmt), use_container_width=True)
        _findings(report.masking, trusted)

    with st.expander("Brightness and dynamics of each element"):
        st.plotly_chart(range_figure(report.brightness, "Brightness (octaves above 1 kHz)", _fmt), use_container_width=True)
        _findings(report.brightness, trusted)
        st.plotly_chart(range_figure(report.crest, "Dynamics (crest factor, dB)", _fmt), use_container_width=True)
        _findings(report.crest, trusted)


def depth_tab(report, motion_rows: list[RangeRow], n_refs: int = 99) -> None:
    theme.callout(
        "A mix sounds <b>flat</b> when little changes over time and little is happening across the stereo field. "
        "This looks at how much the stereo image and the tone move through the song, and how wide the main layers are."
    )
    if report is None or not report.has_reference or report.depth is None:
        references_callout()
        return
    if n_refs < 3:
        few_references_callout(n_refs)
        return
    d = report.depth
    theme.gauge_card(d.label, d.headline, d.position, d.drivers, d.advice, "Compared with your references.",
                     DEPTH_CUTS, -3.0, 3.0, ("Flat", "Good depth", "Lively"))
    if motion_rows:
        st.markdown("##### The measurements behind it")
        st.plotly_chart(range_figure(motion_rows, "Movement over the song", _fmt), use_container_width=True)
