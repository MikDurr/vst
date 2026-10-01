"""MixLens visual system: a deep-purple world with lime display type, cyan pill
actions and confetti, after the Spotify for Developers site.

Everything visual lives here so the views stay plain Streamlit: `apply()` once
per run, `topbar()` for navigation, `page_header()` for each page's hero, and
`style_figure()` for charts.
"""
from __future__ import annotations

import html

import streamlit as st

# ---- tokens ---------------------------------------------------------------
BG = "#420068"          # page ground
BG_DEEP = "#35004F"     # nav bar, wells
PANEL = "#52127F"       # raised surfaces
PANEL_HI = "#63219A"
LINE = "rgba(255,255,255,0.14)"
TEXT = "#F6EDFF"
MUTED = "#CDB4EA"
LIME = "#CDF564"
CYAN = "#1CF3F3"
BLUE = "#1275F0"
PINK = "#F037A5"
CORAL = "#FF9F7A"
VIOLET = "#9B3DFF"
GREEN = "#2BD67B"
YELLOW = "#FFD25A"
LAVENDER = "#E3DAFF"

CATEGORICAL = [LIME, CYAN, PINK, CORAL, "#6EA8FF", YELLOW, VIOLET]


def _blob_svg() -> str:
    """Fixed confetti layer in a 1440x900 box (kept proportional, cropped at the
    edges): a thick lime ribbon down the left and blobs in the margins, which sit
    behind the panels. The top right is left clear for each page's own hero confetti."""
    blobs = [  # cx, cy, rx, ry, colour, rotation
        (70, 250, 44, 58, "#FF9F7A", -20), (120, 560, 38, 52, "#F037A5", 15), (60, 820, 50, 62, "#8EC7FF", 30),
        (1330, 470, 40, 56, "#9B3DFF", 20), (1390, 760, 66, 86, "#CDF564", -15), (1330, 900, 26, 36, "#FFD25A", 10),
        (40, 390, 18, 26, "#2BD67B", -30), (1395, 560, 20, 28, "#509BF5", 25),
    ]
    dots = [(150, 150), (30, 420), (210, 700), (1360, 330), (1260, 560), (1410, 640), (1180, 880), (110, 40)]
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1440 900" preserveAspectRatio="xMidYMid slice">',
        '<path d="M-60 90 C 20 -20, 80 40, 30 200 S -50 520, 30 640 S 110 800, 70 940" fill="none" stroke="#CDF564" '
        'stroke-width="20" stroke-linecap="round" opacity=".9"/>',
    ]
    for cx, cy, rx, ry, col, rot in blobs:
        parts.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="{col}" transform="rotate({rot} {cx} {cy})"/>')
    for x, y in dots:
        parts.append(f'<circle cx="{x}" cy="{y}" r="4" fill="#fff" opacity=".85"/>')
    parts.append("</svg>")
    return "".join(parts).replace("#", "%23").replace('"', "'")


def _css() -> str:
    return f"""
<style>
@font-face {{
  font-family: 'Figtree'; font-weight: 300 900; font-style: normal; font-display: swap;
  src: url(app/static/Figtree.woff2) format('woff2');
}}
:root {{
  --bg:{BG}; --bg-deep:{BG_DEEP}; --panel:{PANEL}; --panel-hi:{PANEL_HI}; --line:{LINE};
  --text:{TEXT}; --muted:{MUTED}; --lime:{LIME}; --cyan:{CYAN}; --blue:{BLUE}; --pink:{PINK};
  --ease: cubic-bezier(.16,1,.3,1);
}}
html, body, .stApp, .stApp *, button, input, textarea, select {{
  font-family: 'Figtree', ui-sans-serif, system-ui, sans-serif !important;
}}
/* material icons must keep their own font */
[data-testid="stIconMaterial"], .material-icons, [class*="material"] {{ font-family: 'Material Symbols Rounded' !important; }}

.stApp {{ background: var(--bg); color: var(--text); }}
.stApp::before {{
  content:""; position: fixed; inset: 0; z-index: 0; pointer-events: none;
  background: url("data:image/svg+xml;utf8,{_blob_svg()}") center/cover no-repeat;
  opacity: .8; animation: drift 18s ease-in-out infinite alternate;
}}
@keyframes drift {{ from {{ transform: translateY(0) }} to {{ transform: translateY(-14px) }} }}
@media (prefers-reduced-motion: reduce) {{ .stApp::before {{ animation: none }} }}

/* strip Streamlit chrome */
header[data-testid="stHeader"], footer, #MainMenu, [data-testid="stToolbar"],
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="stDecoration"] {{ display: none !important; }}
html, body {{ overflow-x: hidden; }}
[data-testid="stMain"], [data-testid="stAppViewContainer"] {{ background: transparent; position: relative; z-index: 1; }}
[data-testid="stMainBlockContainer"] {{ max-width: 1120px; padding: 5.4rem 1.5rem 5rem; }}

::selection {{ background: var(--lime); color: var(--bg-deep); }}
* {{ scrollbar-color: #8A4CC0 transparent; scrollbar-width: thin; }}

/* ---- top bar ---- */
.st-key-topbar {{
  position: fixed; top: 0; left: 0; right: 0; z-index: 999; width: auto; margin: 0;
  padding: .55rem max(1.5rem, calc((100vw - 1120px) / 2 + 1.5rem));
  background: color-mix(in srgb, var(--bg-deep) 94%, transparent); backdrop-filter: blur(10px);
  border-bottom: 1px solid var(--line);
}}
.st-key-topbar [data-testid="stHorizontalBlock"] {{ align-items: center; gap: 1rem; }}
.brand {{ display:flex; align-items:center; gap:.7rem; white-space:nowrap; }}
.brand svg {{ width: 40px; height: 40px; flex: none; }}
.brand b {{ font-size: 1.55rem; font-weight: 800; letter-spacing: -.03em; color:#fff; }}
.brand span {{ font-size: 1.2rem; font-weight: 300; color: var(--lavender, {LAVENDER}); letter-spacing: -.02em; }}
.status-pill {{
  display:inline-flex; align-items:center; gap:.55rem; float:right; background:{LAVENDER}; color:{BG_DEEP};
  font-weight:800; padding:.5rem 1.1rem; border-radius:999px; font-size:.95rem; white-space:nowrap;
}}
.status-pill i {{ width:.65rem; height:.65rem; border-radius:50%; background:{GREEN}; display:inline-block; }}

/* nav radio -> text links with a lime underline */
.st-key-topbar [role="radiogroup"] {{ gap: .35rem; justify-content: center; }}
.st-key-topbar label[data-baseweb="radio"] {{
  padding: .45rem .95rem; border-radius: 999px; margin: 0; cursor: pointer; white-space: nowrap;
  transition: background .25s var(--ease), color .25s var(--ease);
}}
.st-key-topbar label[data-baseweb="radio"] > div:first-child {{ display: none; }}
.st-key-topbar label[data-baseweb="radio"] p {{ font-size: 1.1rem; font-weight: 600; color: {TEXT}; margin: 0; }}
.st-key-topbar label[data-baseweb="radio"]:hover {{ background: rgba(255,255,255,.1); }}
.st-key-topbar label[data-baseweb="radio"]:has(input:checked) {{ background: {LIME}; }}
.st-key-topbar label[data-baseweb="radio"]:has(input:checked) p {{ color: {BG_DEEP}; font-weight: 800; }}
.st-key-topbar label[data-baseweb="radio"]:has(input:focus-visible) {{ outline: 3px solid {CYAN}; outline-offset: 2px; }}

/* ---- hero ---- */
.hero {{ position: relative; padding: 2.6rem 0 1.6rem; }}
.hero h1 {{
  padding: 0 !important; font-size: clamp(2.6rem, 5vw, 4rem); line-height: 1.04; letter-spacing: -.035em; font-weight: 900;
  color: {LIME}; margin: 0 0 .6rem; text-wrap: balance; max-width: 16ch;
}}
.hero p {{ font-size: 1.2rem; font-weight: 400; color: {LAVENDER}; margin: 0; max-width: 46ch; text-wrap: pretty; }}
.hero .conf {{ position:absolute; right: 0; top: 1.2rem; width: min(46%, 440px); height: 240px; pointer-events:none; }}
@media (max-width: 760px) {{ .hero .conf {{ display:none }} }}

/* ---- type ---- */
h1, h2, h3, h4 {{ color: #fff; letter-spacing: -.02em; }}
[data-testid="stHeading"] h2, .stMarkdown h2 {{ font-size: 1.9rem; font-weight: 800; margin-top: 2rem; color: #fff; }}
[data-testid="stHeading"] h3, .stMarkdown h3 {{ font-size: 1.7rem; font-weight: 800; margin-top: 2.2rem; color: #fff; }}
[data-testid="stHeading"] h3::after {{ content: ''; display: block; width: 44px; height: 4px; border-radius: 4px; background: {LIME}; margin-top: .45rem; }}
.stMarkdown h5 {{ font-size: 1.15rem; font-weight: 800; color: {LAVENDER}; margin: 1.4rem 0 .4rem; }}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] *, .stCaption, small {{ opacity: 1 !important; color: #D8C3F0 !important; font-size: .92rem; font-weight: 400; }}
.stMarkdown p, .stMarkdown li {{ font-size: 1.04rem; line-height: 1.6; font-weight: 400; }}
.stMarkdown strong {{ font-weight: 800; }}
.stMarkdown a {{ color: {CYAN}; text-underline-offset: 3px; }}
.stMarkdown code {{ background: rgba(255,255,255,.12); color: #fff; border-radius: 6px; padding: .1rem .4rem; font-family: ui-monospace, Menlo, monospace !important; }}
.stMarkdown table {{ border-collapse: separate; border-spacing: 0; width: 100%; border: 1px solid var(--line); border-radius: 14px; overflow: hidden; }}
.stMarkdown th {{ background: {BG_DEEP}; color: {LIME}; font-weight: 800; text-align:left; padding:.7rem .9rem; }}
.stMarkdown td {{ padding: .65rem .9rem; border-top: 1px solid var(--line); vertical-align: top; }}

/* ---- buttons ---- */
.stButton > button, [data-testid^="stBaseButton"] {{
  border-radius: 999px; font-weight: 800; font-size: 1.05rem; padding: .7rem 1.6rem; min-height: 3rem;
  transition: transform .25s var(--ease), background .25s var(--ease), box-shadow .25s var(--ease);
}}
[data-testid="stBaseButton-primary"] {{ background: {CYAN}; color: {BG_DEEP}; border: 0; box-shadow: 0 6px 0 rgba(0,0,0,.18); }}
[data-testid="stBaseButton-primary"]:hover:not(:disabled) {{ background: #6BFFFF; transform: translateY(-2px); color: {BG_DEEP}; }}
[data-testid="stBaseButton-primary"]:active:not(:disabled) {{ transform: translateY(2px); box-shadow: 0 2px 0 rgba(0,0,0,.18); }}
[data-testid="stBaseButton-secondary"] {{ background: transparent; color: #fff; border: 2px solid rgba(255,255,255,.55); }}
[data-testid="stBaseButton-secondary"]:hover:not(:disabled) {{ border-color: {LIME}; color: {LIME}; background: rgba(205,245,100,.08); transform: translateY(-2px); }}
[data-testid^="stBaseButton"]:disabled {{ opacity: .4; cursor: not-allowed; background-image: repeating-linear-gradient(135deg, transparent 0 8px, rgba(0,0,0,.14) 8px 16px); }}
[data-testid^="stBaseButton"]:focus-visible {{ outline: 3px solid {LIME}; outline-offset: 3px; }}

/* ---- inputs ---- */
[data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="select"] > div, [data-baseweb="textarea"] {{
  background: rgba(0,0,0,.22) !important; border-radius: 14px !important; border: 1.5px solid #8F63C9 !important; min-height: 2.9rem;
}}
[data-baseweb="input"]:focus-within, [data-baseweb="select"]:focus-within > div {{ border-color: {CYAN} !important; box-shadow: 0 0 0 3px rgba(28,243,243,.25); }}
input, textarea {{ color: #fff !important; font-weight: 600; }}
label, [data-testid="stWidgetLabel"] p {{ color: {LAVENDER} !important; font-weight: 700; font-size: .98rem; }}
[data-baseweb="popover"] ul {{ background: {BG_DEEP} !important; border-radius: 14px; }}
[data-baseweb="menu"] li:hover {{ background: {PANEL_HI} !important; }}
[data-testid="stCheckbox"] label span[role="checkbox"], [data-baseweb="checkbox"] > div:first-child {{ border-radius: 6px; }}

/* ---- panels ---- */
[data-testid="stExpander"] {{ background: {PANEL}; border: 1px solid var(--line); border-radius: 20px; overflow: hidden; box-shadow: 0 14px 30px -18px rgba(0,0,0,.6); }}
[data-testid="stExpander"] details {{ border: 0; }}
[data-testid="stExpander"] summary {{ padding: 1.05rem 1.4rem; font-weight: 800; font-size: 1.12rem; }}
[data-testid="stExpander"] summary:hover {{ background: rgba(255,255,255,.06); }}
[data-testid="stExpander"] [data-testid="stExpanderDetails"] {{ padding: .4rem 1.4rem 1.4rem; }}
[data-testid="stExpander"] [data-testid="stExpander"] {{ background: rgba(0,0,0,.2); box-shadow: none; }}

/* help panels: quiet text links, not another box */
.st-key-help [data-testid="stExpander"] {{ background: transparent; border: 0; box-shadow: none; }}
.st-key-help [data-testid="stExpander"] summary {{ padding: .4rem 0; font-size: 1rem; color: {CYAN}; font-weight: 700; }}
.st-key-help [data-testid="stExpander"] summary:hover {{ background: transparent; text-decoration: underline; text-underline-offset: 4px; }}
.st-key-help [data-testid="stExpanderDetails"] {{ padding: .4rem 0 1rem; }}
h1, h2, h3, h4, h5, .hero {{ scroll-margin-top: 90px; }}
.tile {{ background: {PANEL}; border: 1px solid var(--line); border-radius: 20px; padding: 1.2rem 1.4rem; height: 100%; }}
.tile .big {{ font-size: 2.4rem; font-weight: 900; letter-spacing: -.03em; color: {LIME}; line-height: 1.1; }}
.tile .name {{ font-weight: 800; color: #fff; margin-top: .3rem; }} .tile p {{ margin: .35rem 0 0; color: #D8C3F0; font-size: .95rem; }}
/* ---- dynamics gauge ---- */
.dyn {{ background: {PANEL}; border: 1px solid var(--line); border-radius: 24px; padding: 1.5rem 1.7rem; margin: .6rem 0 1rem;
        box-shadow: 0 14px 30px -18px rgba(0,0,0,.6); }}
.dyn .verdict {{ font-size: 2.6rem; font-weight: 900; letter-spacing: -.035em; color: {LIME}; line-height: 1; }}
.dyn .head {{ font-size: 1.1rem; color: #fff; margin: .5rem 0 1.1rem; }}
.gauge {{ position: relative; margin: 1.6rem 0 .4rem; }}
.gauge .track {{ display: flex; height: 16px; border-radius: 999px; overflow: hidden; }}
.gauge .track i {{ display: block; height: 100%; }}
.gauge .marker {{ position: absolute; top: -7px; width: 30px; height: 30px; margin-left: -15px; border-radius: 50%;
                  background: {LIME}; border: 4px solid {BG_DEEP}; box-shadow: 0 4px 10px rgba(0,0,0,.45); transition: left .6s var(--ease); }}
.gauge .ends {{ display: flex; justify-content: space-between; margin-top: .55rem; font-size: .85rem; font-weight: 700; color: #D8C3F0; }}
.dyn ul {{ margin: .9rem 0 .2rem 1.1rem; padding: 0; color: #E3D2F7; }} .dyn li {{ margin: .2rem 0; font-size: .98rem; }}
.dyn .try {{ color: {LIME}; font-weight: 700; margin: .9rem 0 0; font-size: 1.04rem; }}
.dyn .basis {{ font-size: .88rem; color: #CDB4EA; margin-top: .6rem; }}
/* ---- alerts ---- */
[data-testid="stAlertContainer"] {{ background: transparent !important; border-radius: 16px; }}
[data-testid="stAlert"] {{ border-radius: 16px; border: 1px solid transparent; padding: .35rem .4rem; }}
[data-testid="stAlert"]:has([data-testid="stAlertContentInfo"]) {{ background: {BLUE}; border-color: rgba(255,255,255,.25); }}
[data-testid="stAlert"]:has([data-testid="stAlertContentInfo"]) * {{ color: #fff !important; }}
[data-testid="stAlert"]:has([data-testid="stAlertContentSuccess"]) {{ background: rgba(43,214,123,.17); border-color: rgba(43,214,123,.6); }}
[data-testid="stAlert"]:has([data-testid="stAlertContentWarning"]) {{ background: rgba(255,196,70,.26); border-color: rgba(255,210,90,.75); }}
[data-testid="stAlert"]:has([data-testid="stAlertContentError"]) {{ background: rgba(255,107,107,.18); border-color: rgba(255,107,107,.7); }}
[data-testid="stAlert"]:has([data-testid="stAlertContentSuccess"]) * {{ color: #B9F7D6 !important; }}
[data-testid="stAlert"]:has([data-testid="stAlertContentWarning"]) * {{ color: #FFEFB8 !important; }}
[data-testid="stAlert"]:has([data-testid="stAlertContentError"]) * {{ color: #FFD0D0 !important; }}

/* ---- uploader ---- */
[data-testid="stFileUploaderDropzone"] {{
  background: rgba(0,0,0,.2); border: 2.5px dashed {LIME}; border-radius: 22px; padding: 1.6rem;
  transition: background .25s var(--ease), border-color .25s var(--ease);
}}
[data-testid="stFileUploaderDropzone"]:hover {{ background: rgba(205,245,100,.08); border-color: {CYAN}; }}
[data-testid="stFileUploaderDropzone"] svg {{ color: {LIME}; }}
[data-testid="stFileUploaderFile"] {{ background: rgba(0,0,0,.18); border-radius: 12px; }}

/* ---- data ---- */
[data-testid="stDataFrame"], [data-testid="stDataEditor"] {{ border: 1px solid var(--line); border-radius: 16px; overflow: hidden; }}
[data-testid="stPlotlyChart"] {{ background: {PANEL}; border: 1px solid var(--line); border-radius: 20px; padding: .6rem; box-shadow: 0 14px 30px -18px rgba(0,0,0,.6); }}
[data-testid="stProgress"] > div > div > div {{ background: {LIME}; }}
[data-testid="stSpinner"] p {{ color: {LIME}; font-weight: 700; }}
hr {{ border-color: var(--line); }}
@media (max-width: 1100px) {{
  .stApp::before {{ opacity: .22; }}
  .brand span, .status-pill {{ display: none; }}
}}
@media (max-width: 760px) {{
  .st-key-topbar [role="radiogroup"] {{ justify-content: flex-start; flex-wrap: wrap; gap: .25rem; }}
  .st-key-topbar label[data-baseweb="radio"] {{ padding: .35rem .8rem; }}
  .st-key-topbar [data-testid="stHorizontalBlock"] {{ flex-wrap: wrap; gap: .8rem; }}
  .st-key-topbar [data-testid="stColumn"] {{ min-width: 100% !important; }}
  [data-testid="stMainBlockContainer"] {{ padding-top: 11rem; }}
  .hero {{ padding-top: 2rem; }}
}}

/* ---- recommendation + job cards ---- */
.rec {{ background: {PANEL}; border: 1px solid var(--line); border-radius: 20px; padding: 1.15rem 1.4rem; margin: .75rem 0;
        box-shadow: 0 14px 30px -18px rgba(0,0,0,.6); }}
.rec .top {{ display: flex; align-items: center; gap: .75rem; flex-wrap: wrap; margin-bottom: .35rem; }}
.rec h4 {{ margin: 0; font-size: 1.25rem; font-weight: 800; color: #fff; letter-spacing: -.02em; }}
.rec p {{ margin: .25rem 0; font-size: 1.02rem; line-height: 1.55; color: #E3D2F7; }}
.rec .try {{ color: {LIME}; font-weight: 700; }}
.rec .ev {{ font-size: .88rem; color: #CDB4EA; margin-top: .45rem; }}
.chip {{ font-size: .78rem; font-weight: 800; letter-spacing: .02em; text-transform: uppercase; padding: .25rem .7rem; border-radius: 999px; color: {BG_DEEP}; }}
.chip.fix {{ background: #FF8A8A; }} .chip.check {{ background: {YELLOW}; }} .chip.note {{ background: {LAVENDER}; }} .chip.ok {{ background: {GREEN}; }}
.job {{ display: flex; align-items: center; gap: 1rem; border-radius: 18px; padding: .9rem 1.3rem; margin: .8rem 0 .3rem; border: 1px solid var(--line); background: {PANEL_HI}; }}
.job b {{ font-size: 1.08rem; color: #fff; display: block; }} .job span {{ color: #E3D2F7; font-size: .96rem; }}
.job .dot {{ width: 14px; height: 14px; border-radius: 50%; background: {LIME}; flex: none; animation: pulse 1.2s ease-in-out infinite; }}
.job.done .dot {{ background: {GREEN}; animation: none; }} .job.error .dot {{ background: #FF6B6B; animation: none; }}
.job.done {{ border-color: rgba(43,214,123,.7); }} .job.error {{ border-color: rgba(255,107,107,.8); }}
@keyframes pulse {{ 50% {{ transform: scale(1.5); opacity: .5 }} }}
@media (prefers-reduced-motion: reduce) {{ .job .dot {{ animation: none }} }}
.summary-line {{ font-size: 1.15rem; font-weight: 600; color: #fff; margin: .2rem 0 .6rem; }}
.callout {{ background: rgba(0,0,0,.22); border: 1px solid var(--line); border-radius: 16px; padding: 1rem 1.3rem; margin: .5rem 0 1rem; color: #E3D2F7; }}
.callout b {{ color: #fff; }}
</style>
"""


LOGO = (
    f'<svg viewBox="0 0 48 48" aria-hidden="true"><circle cx="24" cy="24" r="22" fill="{LIME}"/>'
    f'<g fill="{BG_DEEP}"><rect x="11" y="21" width="4" height="6" rx="2"/><rect x="17.5" y="15" width="4" height="18" rx="2"/>'
    f'<rect x="24" y="10" width="4" height="28" rx="2"/><rect x="30.5" y="17" width="4" height="14" rx="2"/>'
    f'<rect x="37" y="22" width="3" height="4" rx="1.5"/></g></svg>'
)


def apply() -> None:
    st.markdown(_css(), unsafe_allow_html=True)


def topbar(pages: list[str], status: str) -> str:
    """Brand, page navigation and a status pill. Returns the selected page."""
    with st.container(key="topbar"):
        left, mid, right = st.columns([3, 6, 1.7], vertical_alignment="center")
        left.markdown(f'<div class="brand">{LOGO}<b>MixLens</b><span>for producers</span></div>', unsafe_allow_html=True)
        with mid:
            page = st.radio("Page", pages, key="page", horizontal=True, label_visibility="collapsed")
        right.markdown(f'<div class="status-pill"><i></i>{html.escape(status)}</div>', unsafe_allow_html=True)
    return page


_CONFETTI = (
    '<svg class="conf" viewBox="0 0 440 240" aria-hidden="true">'
    '<ellipse cx="330" cy="46" rx="28" ry="34" fill="#FF9F7A" transform="rotate(-20 330 46)"/>'
    '<ellipse cx="236" cy="62" rx="17" ry="24" fill="#509BF5" transform="rotate(15 236 62)"/>'
    '<ellipse cx="394" cy="118" rx="22" ry="30" fill="#9B3DFF" transform="rotate(20 394 118)"/>'
    '<ellipse cx="290" cy="150" rx="30" ry="18" fill="#F037A5" transform="rotate(-12 290 150)"/>'
    '<ellipse cx="190" cy="132" rx="9" ry="15" fill="#FFD25A" transform="rotate(20 190 132)"/>'
    '<ellipse cx="368" cy="206" rx="20" ry="26" fill="#2BD67B" transform="rotate(-25 368 206)"/>'
    '<ellipse cx="226" cy="200" rx="13" ry="18" fill="#8EC7FF"/>'
    '<ellipse cx="414" cy="30" rx="14" ry="20" fill="#CDF564"/>'
    '<g fill="#fff"><circle cx="270" cy="16" r="3"/><circle cx="352" cy="92" r="3"/><circle cx="214" cy="104" r="2.5"/>'
    '<circle cx="410" cy="170" r="3"/><circle cx="306" cy="226" r="2.5"/><circle cx="170" cy="60" r="2.5"/></g></svg>'
)


def page_header(title: str, subtitle: str) -> None:
    st.markdown(
        f'<section class="hero">{_CONFETTI}<h1>{html.escape(title)}</h1><p>{html.escape(subtitle)}</p></section>',
        unsafe_allow_html=True,
    )


def style_figure(fig, height: int | None = None):
    """Dark-purple Plotly styling shared by every chart."""
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Figtree, sans-serif", color=TEXT, size=14),
        title=dict(font=dict(size=20, color="#fff"), x=0.01),
        colorway=CATEGORICAL,
        margin=dict(l=48, r=24, t=64, b=48),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=13)),
        hoverlabel=dict(bgcolor=BG_DEEP, font=dict(family="Figtree, sans-serif", color="#fff")),
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,.1)", zerolinecolor="rgba(255,255,255,.2)", linecolor="rgba(255,255,255,.25)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,.1)", zerolinecolor="rgba(255,255,255,.2)", linecolor="rgba(255,255,255,.25)")
    if height:
        fig.update_layout(height=height)
    return fig


def rec_card(rec) -> None:
    label = {"fix": "Fix first", "check": "Take a look", "note": "Good to know"}[rec.severity]
    ev = f'<div class="ev">{html.escape(rec.evidence)}</div>' if rec.evidence else ""
    st.markdown(
        f'<div class="rec"><div class="top"><span class="chip {rec.severity}">{label}</span>'
        f"<h4>{html.escape(rec.title)}</h4></div>"
        f"<p>{html.escape(rec.why)}</p><p class=\"try\">Try: {html.escape(rec.action)}</p>{ev}</div>",
        unsafe_allow_html=True,
    )


def job_card(state: str, title: str, body: str) -> None:
    st.markdown(
        f'<div class="job {state}"><i class="dot"></i><div><b>{html.escape(title)}</b>'
        f"<span>{html.escape(body)}</span></div></div>",
        unsafe_allow_html=True,
    )


def callout(html_body: str) -> None:
    """A quiet explanatory panel. `html_body` is trusted markup written in the views."""
    st.markdown(f'<div class="callout">{html_body}</div>', unsafe_allow_html=True)


def stat_tile(value: str, name: str, blurb: str) -> None:
    st.markdown(
        f'<div class="tile"><div class="big">{html.escape(value)}</div><div class="name">{html.escape(name)}</div>'
        f"<p>{html.escape(blurb)}</p></div>",
        unsafe_allow_html=True,
    )


def scroll_to_top() -> None:
    """Pages open at the top rather than wherever the last page was scrolled to."""
    import streamlit.components.v1 as components

    components.html(
        "<script>const m=window.parent.document.querySelector('[data-testid=stMain]');if(m)m.scrollTo(0,0);</script>",
        height=0,
    )


# gauge zone colours, squashed -> very open
_ZONES = ["#FF8A8A", "#FFC46B", "#2BD67B", "#1CF3F3", "#8EC7FF"]


def dynamics_card(summary, cuts: tuple[float, float, float, float], lo: float, hi: float) -> None:
    """The verdict, a gauge placing the mix between squashed and open, and why.
    `cuts`/`lo`/`hi` give the zone boundaries on the gauge's own scale."""
    edges = [lo, *cuts, hi]
    widths = [(edges[i + 1] - edges[i]) / (hi - lo) * 100 for i in range(5)]
    segs = "".join(f'<i style="width:{w:.1f}%;background:{c}"></i>' for w, c in zip(widths, _ZONES))
    bullets = "".join(f"<li>{html.escape(d)}</li>" for d in summary.drivers)
    basis = ("Compared with your references." if summary.basis == "references"
             else "Rule of thumb: add references for a real comparison.")
    st.markdown(
        f'<div class="dyn"><div class="verdict">{html.escape(summary.label)}</div>'
        f'<div class="head">{html.escape(summary.headline.split(": ", 1)[-1])}</div>'
        f'<div class="gauge"><div class="track">{segs}</div><span class="marker" style="left:{summary.position * 100:.1f}%"></span>'
        f'<div class="ends"><span>Squashed</span><span>Balanced</span><span>Open</span></div></div>'
        f"<ul>{bullets}</ul><p class=\"try\">Try: {html.escape(summary.advice)}</p>"
        f'<div class="basis">{html.escape(basis)}</div></div>',
        unsafe_allow_html=True,
    )
