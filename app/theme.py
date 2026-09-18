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
THEME = "light"


@lru_cache(maxsize=1)
def tokens() -> dict[str, str]:
    """Flat name -> CSS value map for the active theme, aliases resolved."""
    data = json.loads(TOKENS_PATH.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    raw_colors = {}
    for t in data["color"]["tokens"]:
        v = t["value"]
        raw_colors[t["name"]] = v.get(THEME, v.get("light")) if isinstance(v, dict) else v
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
        out[t["name"]] = v.get(THEME, v.get("light")) if isinstance(v, dict) else v
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

/* ---- streamlit widget polish ---- */
.stButton > button, .stDownloadButton > button {{ border-radius: var(--radius-md); font-weight: 600;
  border: 1px solid var(--line-control); }}
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {{
  background: var(--ink-primary); border-color: var(--ink-primary); color: var(--ink-inverse); }}
.stButton > button[kind="primary"]:hover {{ background: #2a323d; border-color: #2a323d; color: var(--ink-inverse); }}
[data-testid="stFileUploaderDropzone"] {{ background: var(--surface-card); border: 1px dashed var(--line-control);
  border-radius: var(--radius-lg); }}
[data-testid="stExpander"] {{ border-radius: var(--radius-lg); border-color: var(--line-hairline); background: var(--surface-card); }}
[data-testid="stDataFrame"] {{ border: 1px solid var(--line-hairline); border-radius: var(--radius-md); }}
*:focus-visible {{ outline: 2px solid var(--focus-ring) !important; outline-offset: 2px; }}
</style>
"""
