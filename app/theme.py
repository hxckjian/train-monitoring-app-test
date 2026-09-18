"""App theme, derived from the design system's tokens.json.

There is exactly one source of colour, type and spacing: the published Nebula
Wayside design system. This module reads it, resolves aliases, and emits both
the page CSS and the chart palette, so the app cannot drift from the system.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

TOKENS_PATH = (Path(__file__).resolve().parents[1]
               / "design-system" / "project" / "tokens.json")
THEME = "dark"          # active theme; set_theme() switches it per run


def set_theme(name: str) -> None:
    """'light' or 'dark'. Called once per script run before anything draws."""
    global THEME
    THEME = "light" if name == "light" else "dark"


def map_style() -> str:
    return "light" if THEME == "light" else "dark"


def tokens() -> dict[str, str]:
    return _tokens(THEME)


@lru_cache(maxsize=2)
def _tokens(theme: str) -> dict[str, str]:
    """Flat name -> CSS value map for one theme, aliases resolved."""
    THEME_ = theme
    data = json.loads(TOKENS_PATH.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    raw_colors = {}
    for t in data["color"]["tokens"]:
        v = t["value"]
        raw_colors[t["name"]] = v.get(THEME_, v.get("light")) if isinstance(v, dict) else v
    alias = re.compile(r"^\{(.+)\}$")

    def resolve(name: str, depth: int = 0) -> str:
        v = raw_colors[name]
        m = alias.match(v)
        if m and depth < 16:
            return resolve(m.group(1), depth + 1)
        return v

    for name in raw_colors:
        out[name] = resolve(name)
    for fam in ("spacing", "radius", "stroke"):
        for t in data.get(fam, {}).get("tokens", []):
            out[t["name"]] = str(t["value"])
    for t in data.get("shadow", {}).get("tokens", []):
        v = t["value"]
        out[t["name"]] = v.get(THEME_, v.get("light")) if isinstance(v, dict) else v
    for key, stack in data["type"]["families"].items():
        out[f"font-{key}"] = stack
    return out


def T(name: str) -> str:
    return tokens()[name]


STATE_TOKEN = {"ok": "status-ok", "watch": "status-watch",
               "alert": "status-alert", "unknown": "status-unknown"}


def css() -> str:
    t = tokens()
    root = "\n".join(f"  --{k}: {v};" for k, v in t.items())
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap');
:root {{
{root}
}}
html, body, .stApp, [data-testid="stAppViewContainer"] {{
  background: var(--surface-page);
  color: var(--ink-primary);
  font-family: var(--font-sans);
}}
.stApp :is(p, li, label, h1, h2, h3, h4, input, textarea, button, td, th, a),
.stApp [data-testid="stMarkdownContainer"] {{ font-family: var(--font-sans); }}
/* never restyle icon glyphs: they are a ligature font, not text */
[data-testid="stIconMaterial"] {{ font-family: "Material Symbols Rounded" !important; }}
.stApp code, .stApp pre {{ font-family: var(--font-mono); }}
[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding-top: 4.2rem; padding-bottom: 4rem; max-width: 1240px; }}
h1, h2, h3 {{ font-family: var(--font-sans); color: var(--ink-primary); letter-spacing: -0.01em; }}

/* ---- page header ---- */
.nw-eyebrow {{ font-size: 11px; line-height: 15px; letter-spacing: .08em; text-transform: uppercase;
  color: var(--ink-muted); font-weight: 600; margin: 0 0 6px; display:flex; align-items:center; gap:8px; }}
.nw-eyebrow .dot {{ width: 8px; height: 8px; border-radius: 2px; display:inline-block; }}
.nw-h1 {{ font-size: 32px; line-height: 36px; font-weight: 600; letter-spacing: -0.01em; margin: 0 0 6px; }}
.nw-lede {{ font-size: 16px; line-height: 22px; color: var(--ink-secondary); margin: 0 0 20px; max-width: 760px; }}
.nw-section {{ font-size: 12px; line-height: 16px; font-weight: 600; letter-spacing: .06em;
  text-transform: uppercase; color: var(--ink-muted); margin: 28px 0 10px; }}

/* ---- status chip ---- */
.nw-chip {{ display:inline-flex; align-items:center; gap:8px; padding:4px 12px; border-radius:999px;
  font-size:12px; line-height:16px; font-weight:600; letter-spacing:.04em; white-space:nowrap; }}
.nw-chip .g {{ font-size: 11px; line-height: 1; }}
.nw-chip .d {{ color: var(--ink-secondary); font-weight: 400; letter-spacing: 0; }}
.nw-chip.ok {{ background: var(--status-ok-soft); color: var(--status-ok); }}
.nw-chip.watch {{ background: var(--status-watch-soft); color: var(--status-watch); }}
.nw-chip.alert {{ background: var(--status-alert-soft); color: var(--status-alert); }}
.nw-chip.unknown {{ background: var(--surface-sunken); color: var(--status-unknown); }}

/* ---- verdict card ---- */
.nw-card {{ background: var(--surface-card); border: 1px solid var(--line-hairline);
  border-radius: var(--radius-lg); box-shadow: var(--shadow-card); padding: 24px; }}
.nw-card .head {{ display:flex; justify-content:space-between; align-items:center; gap:12px; margin-bottom:12px; }}
.nw-card .sub {{ font-size:11px; letter-spacing:.06em; text-transform:uppercase; color:var(--ink-muted); }}
.nw-card h3 {{ font-size:22px; line-height:28px; font-weight:600; margin:0 0 8px; }}
.nw-card .meaning {{ font-size:16px; line-height:23px; color:var(--ink-secondary); margin:0 0 16px; }}
.nw-card .action {{ background:var(--surface-sunken); border-radius:var(--radius-md); padding:12px 16px;
  font-size:15px; line-height:22px; margin:0; }}
.nw-card .action b {{ font-weight:600; }}
.nw-card .evidence {{ font-family:var(--font-mono); font-size:11px; line-height:16px; color:var(--ink-muted); margin:12px 0 0; }}

/* ---- KPI tiles ---- */
.nw-kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:12px; margin: 0 0 4px; }}
.nw-kpi {{ background:var(--surface-card); border:1px solid var(--line-hairline); border-radius:var(--radius-lg); padding:16px 18px; }}
.nw-kpi .l {{ font-size:12px; line-height:16px; font-weight:500; color:var(--ink-secondary); margin-bottom:6px; }}
.nw-kpi .v {{ font-family:var(--font-mono); font-size:28px; line-height:32px; font-weight:500; color:var(--ink-primary); }}
.nw-kpi .s {{ font-size:12px; line-height:16px; color:var(--ink-muted); margin-top:4px; }}

/* ---- subsystem tiles (overview) ---- */
.nw-sys {{ background:var(--surface-card); border:1px solid var(--line-hairline); border-radius:var(--radius-lg);
  padding:20px; height:100%; position:relative; overflow:hidden; }}
.nw-sys .bar {{ position:absolute; left:0; top:0; right:0; height:4px; }}
.nw-sys .name {{ font-size:18px; line-height:24px; font-weight:600; margin:6px 0 4px; }}
.nw-sys .q {{ font-size:14px; line-height:20px; color:var(--ink-secondary); margin:0 0 14px; min-height:40px; }}
.nw-sys .score {{ font-family:var(--font-mono); font-size:26px; line-height:30px; font-weight:500; }}
.nw-sys .metric {{ font-size:12px; color:var(--ink-muted); margin-top:2px; }}
.nw-sys .split {{ font-family:var(--font-mono); font-size:11px; line-height:15px; color:var(--ink-muted);
  border-top:1px solid var(--line-hairline); margin-top:14px; padding-top:10px; }}

/* ---- steps ---- */
.nw-steps {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; }}
.nw-step {{ border:1px dashed var(--line-control); border-radius:var(--radius-lg); padding:16px 18px; background:transparent; }}
.nw-step .n {{ font-family:var(--font-mono); font-size:12px; color:var(--ink-muted); }}
.nw-step .t {{ font-size:15px; font-weight:600; margin:4px 0 2px; }}
.nw-step .b {{ font-size:13px; line-height:18px; color:var(--ink-secondary); }}

/* ---- empty / pending state ---- */
.nw-empty {{ background:var(--surface-sunken); border-radius:var(--radius-lg); padding:28px; }}
.nw-empty h3 {{ font-size:18px; margin:10px 0 6px; }}
.nw-empty p {{ color:var(--ink-secondary); font-size:15px; line-height:22px; margin:0 0 8px; max-width:720px; }}


/* ---- car rank ---- */
.nw-rank {{ background:var(--surface-card); border:1px solid var(--line-hairline); border-radius:var(--radius-lg); padding:14px 18px; }}
.nw-rank-row {{ display:grid; grid-template-columns:24px 64px 1fr 120px; align-items:center; gap:10px; padding:6px 0; }}
.nw-rank-row .r {{ font-family:var(--font-mono); font-size:12px; color:var(--ink-muted); }}
.nw-rank-row .id {{ font-weight:600; font-size:14px; }}
.nw-rank-row .bar {{ height:12px; background:var(--surface-sunken); border-radius:999px; overflow:hidden; }}
.nw-rank-row .bar span {{ display:block; height:100%; background:var(--series-1); border-radius:999px; }}
.nw-rank-row.top .bar span {{ background:var(--status-alert); }}
.nw-rank-row.top .id {{ color:var(--status-alert); }}
.nw-rank-row.na .v {{ color:var(--ink-muted); }}
.nw-rank-row .v {{ font-family:var(--font-mono); font-size:12px; color:var(--ink-secondary); text-align:right; }}
.nw-rank .cap {{ font-size:12px; color:var(--ink-muted); margin-top:8px; }}

/* ---- fleet board ---- */
.nw-fleet {{ background:var(--surface-card); border:1px solid var(--line-hairline); border-left:4px solid var(--status-unknown);
  border-radius:var(--radius-lg); padding:14px 16px; margin-bottom:10px; }}
.nw-fleet.ok {{ border-left-color:var(--status-ok); }}
.nw-fleet.watch {{ border-left-color:var(--status-watch); }}
.nw-fleet.alert {{ border-left-color:var(--status-alert); }}
.nw-fleet .n {{ font-size:11px; letter-spacing:.06em; text-transform:uppercase; color:var(--ink-muted); margin-bottom:6px; }}
.nw-fleet .h {{ display:flex; align-items:center; gap:10px; font-size:15px; font-weight:600; }}
.nw-fleet .d {{ font-size:13px; color:var(--ink-secondary); margin-top:4px; }}

/* ---- dashboard panels ---- */
.nw-panel {{ background:var(--surface-card); border:1px solid var(--line-hairline); border-radius:var(--radius-lg); padding:18px 20px; margin-bottom:12px; }}
.nw-panel .t {{ font-size:15px; font-weight:600; margin-bottom:12px; }}
.nw-panel .muted {{ color:var(--ink-muted); font-size:13px; margin:0; }}
.nw-stack {{ display:flex; height:14px; border-radius:999px; overflow:hidden; background:var(--surface-sunken); gap:2px; }}
.nw-stack span {{ display:block; height:100%; }}
.nw-stack .alert, .nw-legend i.alert {{ background:var(--status-alert); }}
.nw-stack .watch, .nw-legend i.watch {{ background:var(--status-watch); }}
.nw-stack .ok, .nw-legend i.ok {{ background:var(--status-ok); }}
.nw-stack .unknown, .nw-legend i.unknown {{ background:var(--line-control); }}
.nw-legend {{ display:flex; flex-wrap:wrap; gap:14px; margin-top:10px; font-size:12px; color:var(--ink-secondary); }}
.nw-legend i {{ display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px; }}
.nw-pill {{ display:inline-flex; align-items:center; gap:6px; font-size:12px; font-weight:600; white-space:nowrap; }}
.nw-pill i {{ width:8px; height:8px; border-radius:50%; display:inline-block; }}
.nw-pill.alert {{ color:var(--status-alert); }} .nw-pill.alert i {{ background:var(--status-alert); }}
.nw-pill.watch {{ color:var(--status-watch); }} .nw-pill.watch i {{ background:var(--status-watch); }}
.nw-pill.ok {{ color:var(--status-ok); }} .nw-pill.ok i {{ background:var(--status-ok); }}
.nw-pill.unknown {{ color:var(--ink-muted); }} .nw-pill.unknown i {{ background:var(--line-control); }}
.nw-table {{ width:100%; border-collapse:collapse; font-size:13px; }}
.nw-table th {{ text-align:left; font-size:11px; letter-spacing:.06em; text-transform:uppercase; color:var(--ink-muted); font-weight:600; padding:6px 8px; border-bottom:1px solid var(--line-hairline); }}
.nw-table td {{ padding:10px 8px; border-bottom:1px solid var(--line-hairline); vertical-align:top; }}
.nw-table tr:last-child td {{ border-bottom:0; }}
.nw-table .mono {{ font-family:var(--font-mono); color:var(--ink-muted); font-size:12px; }}
.nw-table .muted {{ color:var(--ink-secondary); font-size:12px; }}
.nw-kpis.two {{ grid-template-columns:repeat(2, 1fr); }}
.nw-kpi .v.sm {{ font-size:24px; line-height:28px; }}
.nw-hero {{ display:flex; align-items:center; gap:10px; margin:0 0 10px; }}
.nw-hero .n {{ font-family:var(--font-mono); font-size:22px; font-weight:500; background:var(--surface-card); border:1px solid var(--line-hairline); border-radius:999px; padding:6px 16px; }}

.nw-health {{ display:inline-block; width:64px; height:8px; background:var(--surface-sunken); border-radius:999px; overflow:hidden; vertical-align:middle; margin-right:8px; }}
.nw-health span {{ display:block; height:100%; border-radius:999px; }}
.nw-health .ok {{ background:var(--status-ok); }} .nw-health .watch {{ background:var(--status-watch); }} .nw-health .alert {{ background:var(--status-alert); }}
.nw-cell {{ display:inline-block; width:14px; height:14px; border-radius:3px; margin-right:3px; background:var(--surface-sunken); }}
.nw-cell.ok {{ background:var(--status-ok); }} .nw-cell.watch {{ background:var(--status-watch); }} .nw-cell.alert {{ background:var(--status-alert); }}


/* ---- motion: entrance, live bars, and a blinking warning state ---- */
@keyframes nw-rise {{ from {{ opacity:0; transform:translateY(8px); }} to {{ opacity:1; transform:none; }} }}
@keyframes nw-blink {{ 0%,100% {{ box-shadow:0 0 0 0 rgba(224,67,79,.55); }} 50% {{ box-shadow:0 0 0 8px rgba(224,67,79,0); }} }}
@keyframes nw-blink-text {{ 0%,100% {{ opacity:1; }} 50% {{ opacity:.35; }} }}
@keyframes nw-grow {{ from {{ transform:scaleX(0); }} to {{ transform:scaleX(1); }} }}
@keyframes nw-sweep {{ 0% {{ background-position:-200% 0; }} 100% {{ background-position:200% 0; }} }}
.nw-card, .nw-panel, .nw-kpi, .nw-sys, .nw-fleet, .nw-rank, .nw-empty, .nw-step {{ animation: nw-rise .45s cubic-bezier(.2,.7,.2,1) both; }}
.nw-kpis .nw-kpi:nth-child(2) {{ animation-delay:.06s; }} .nw-kpis .nw-kpi:nth-child(3) {{ animation-delay:.12s; }} .nw-kpis .nw-kpi:nth-child(4) {{ animation-delay:.18s; }}
.nw-kpi, .nw-sys, .nw-panel, .nw-fleet {{ transition: transform .18s ease, border-color .18s ease, box-shadow .18s ease; }}
.nw-kpi:hover, .nw-sys:hover, .nw-fleet:hover {{ transform: translateY(-2px); border-color: var(--line-control); box-shadow: var(--shadow-card); }}
.nw-rank-row .bar span, .nw-health span, .nw-stack span {{ transform-origin:left; animation: nw-grow .7s cubic-bezier(.2,.7,.2,1) both; }}
.nw-chip.alert, .nw-pill.alert i, .nw-fleet.alert .nw-chip {{ animation: nw-blink 1.6s ease-out infinite; }}
.nw-pill.alert {{ animation: nw-blink-text 1.6s ease-in-out infinite; }}
.nw-card:has(.nw-chip.alert) {{ border-color: var(--status-alert); }}
.nw-kpi.warn .v {{ color: var(--status-alert); animation: nw-blink-text 1.6s ease-in-out infinite; }}
.nw-beacon {{ display:flex; align-items:center; gap:10px; background:var(--status-alert-soft); border:1px solid var(--status-alert);
  color:var(--ink-primary); border-radius:var(--radius-lg); padding:10px 16px; margin:0 0 12px; font-size:14px; font-weight:600;
  animation: nw-rise .45s both; }}
.nw-beacon i {{ width:10px; height:10px; border-radius:50%; background:var(--status-alert); animation: nw-blink 1.2s ease-out infinite; flex:none; }}
.nw-beacon .d {{ font-weight:400; color:var(--ink-secondary); margin-left:auto; font-size:12px; }}
.nw-live {{ display:inline-flex; align-items:center; gap:6px; font-size:11px; letter-spacing:.06em; text-transform:uppercase; color:var(--status-ok); }}
.nw-live i {{ width:7px; height:7px; border-radius:50%; background:var(--status-ok); animation: nw-blink-text 1.4s ease-in-out infinite; }}
.nw-skeleton {{ background: linear-gradient(90deg, var(--surface-sunken) 25%, var(--surface-card) 50%, var(--surface-sunken) 75%); background-size:200% 100%; animation: nw-sweep 1.4s linear infinite; border-radius:var(--radius-md); }}
@media (prefers-reduced-motion: reduce) {{ .nw-card, .nw-panel, .nw-kpi, .nw-sys, .nw-fleet, .nw-rank, .nw-empty, .nw-step, .nw-chip, .nw-pill i, .nw-pill, .nw-beacon i, .nw-live i, .nw-kpi.warn .v, .nw-rank-row .bar span, .nw-health span, .nw-stack span {{ animation:none !important; }} }}

/* ---- hero + glass ---- */
@keyframes nw-float {{ 0%,100% {{ transform:translateY(0); }} 50% {{ transform:translateY(-4px); }} }}
.nw-hero-card {{ position:relative; overflow:hidden; border-radius:22px; padding:22px 26px; margin:0 0 14px;
  background: linear-gradient(135deg, rgba(46,143,212,.16), color-mix(in srgb, var(--surface-card) 70%, transparent) 45%, rgba(224,67,79,.10));
  border:1px solid var(--line-hairline); backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
  animation: nw-rise .5s both; display:grid; grid-template-columns: 1fr auto; gap:18px; align-items:center; }}
.nw-hero-card::before {{ content:""; position:absolute; inset:-40% -20% auto auto; width:420px; height:420px; border-radius:50%;
  background: radial-gradient(closest-side, rgba(46,143,212,.28), transparent); pointer-events:none; }}
.nw-hero-card .k {{ font-size:11px; letter-spacing:.12em; text-transform:uppercase; color:var(--ink-muted); font-weight:600; }}
.nw-hero-card .t {{ font-size:34px; line-height:38px; font-weight:600; letter-spacing:-.02em; margin:4px 0 6px; }}
.nw-hero-card .s {{ font-size:15px; color:var(--ink-secondary); max-width:720px; }}
.nw-hero-card .wx {{ text-align:right; font-family:var(--font-mono); font-size:13px; color:var(--ink-secondary); line-height:1.5; }}
.nw-hero-card .wx .e {{ display:inline-block; font-size:44px; line-height:1; animation: nw-float 3.2s ease-in-out infinite; filter: drop-shadow(0 6px 14px rgba(0,0,0,.35)); }}
.nw-hero-card .wx .big {{ font-size:26px; color:var(--ink-primary); font-weight:500; }}
.nw-panel, .nw-kpi, .nw-card, .nw-sys, .nw-fleet, .nw-rank {{ background: color-mix(in srgb, var(--surface-card) 82%, transparent);
  backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); }}
.nw-emoji {{ display:inline-block; margin-right:6px; animation: nw-float 3.6s ease-in-out infinite; }}
.nw-drop {{ border:1px dashed var(--line-control); border-radius:var(--radius-lg); padding:10px 14px; font-size:13px; color:var(--ink-secondary); }}
.nw-drop b {{ color:var(--ink-primary); }}
[data-testid="stFileUploaderDropzone"] {{ min-height:64px; }}

.nw-urg {{ font-size:11px; font-weight:700; letter-spacing:.08em; text-transform:uppercase; padding:4px 10px; border-radius:999px; }}
.nw-urg.alert {{ background:var(--status-alert); color:#fff; animation: nw-blink 1.6s ease-out infinite; }}
.nw-urg.watch {{ background:var(--status-watch); color:#111; }}
.nw-urg.ok {{ background:var(--status-ok-soft); color:var(--status-ok); }}
.nw-act.alert {{ border-left:4px solid var(--status-alert); }} .nw-act.watch {{ border-left:4px solid var(--status-watch); }} .nw-act.ok {{ border-left:4px solid var(--status-ok); }}
.nw-tips {{ margin:0; padding-left:18px; font-size:14px; line-height:1.55; color:var(--ink-secondary); }}
.nw-tips li {{ margin:4px 0; }}

/* ---- transitions ---- */
html {{ scroll-behavior: smooth; }}
.block-container {{ animation: nw-rise .35s ease-out both; }}
[data-testid="stTabs"] [role="tabpanel"] {{ animation: nw-rise .3s ease-out both; }}
[data-testid="stExpander"] details summary, .stButton > button, a[data-testid="stPageLink-NavLink"] {{ transition: background .15s ease, transform .15s ease, border-color .15s ease; }}
a[data-testid="stPageLink-NavLink"]:hover {{ transform: translateX(3px); }}
[data-testid="stSegmentedControl"] button {{ transition: background .15s ease, color .15s ease; }}
[data-testid="stDeckGlJsonChart"], [data-testid="stPlotlyChart"] {{ animation: nw-rise .4s ease-out both; }}

/* ---- streamlit widget polish ---- */
.stButton > button, .stDownloadButton > button {{ border-radius: var(--radius-md); font-weight: 600;
  border: 1px solid var(--line-control); }}
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {{
  background: var(--ink-primary); border-color: var(--ink-primary); color: var(--ink-inverse); }}
.stButton > button[kind="primary"]:hover {{ filter: brightness(1.15); color: var(--ink-inverse); }}
[data-testid="stTabs"] button {{ font-weight:600; }}
[data-testid="stFileUploaderDropzone"] {{ background: var(--surface-card); border: 1px dashed var(--line-control);
  border-radius: var(--radius-lg); }}
[data-testid="stExpander"] {{ border-radius: var(--radius-lg); border-color: var(--line-hairline); background: var(--surface-card); }}
[data-testid="stDataFrame"] {{ border: 1px solid var(--line-hairline); border-radius: var(--radius-md); }}
*:focus-visible {{ outline: 2px solid var(--focus-ring) !important; outline-offset: 2px; }}
</style>
"""
