"""HTML components mirroring the design system's StatusChip / VerdictCard.

Every user-derived string is escaped. State is always colour + glyph + word,
never colour alone.
"""
from __future__ import annotations

from html import escape

STATES = {
    "ok": ("●", "Normal"),
    "watch": ("◐", "Watch"),
    "alert": ("✕", "Fault"),
    "unknown": ("—", "Unknown"),
}


def chip(state: str, label: str | None = None, detail: str | None = None) -> str:
    state = state if state in STATES else "unknown"
    glyph, word = STATES[state]
    d = f'<span class="d">{escape(detail)}</span>' if detail else ""
    return (f'<span class="nw-chip {state}" role="status"><span class="g" aria-hidden="true">'
            f'{glyph}</span>{escape(label or word)}{d}</span>')


def header(eyebrow: str, title: str, lede: str, color: str | None = None) -> str:
    dot = f'<span class="dot" style="background:{color}"></span>' if color else ""
    return (f'<div class="nw-eyebrow">{dot}{escape(eyebrow)}</div>'
            f'<div class="nw-h1">{escape(title)}</div><p class="nw-lede">{escape(lede)}</p>')


def section(label: str) -> str:
    return f'<div class="nw-section">{escape(label)}</div>'


def verdict(state: str, subsystem: str, title: str, meaning: str,
            action: str, evidence: str, chip_label: str | None = None) -> str:
    return f"""<div class="nw-card">
  <div class="head">{chip(state, chip_label)}<span class="sub">{escape(subsystem)}</span></div>
  <h3>{escape(title)}</h3>
  <p class="meaning">{escape(meaning)}</p>
  <p class="action"><b>Action &mdash; </b>{escape(action)}</p>
  <p class="evidence">{escape(evidence)}</p>
</div>"""


def kpis(items: list[tuple[str, str, str | None]]) -> str:
    cells = "".join(
        f'<div class="nw-kpi"><div class="l">{escape(l)}</div><div class="v">{escape(v)}</div>'
        + (f'<div class="s">{escape(s)}</div>' if s else "") + "</div>"
        for l, v, s in items)
    return f'<div class="nw-kpis">{cells}</div>'


def system_tile(color: str, state: str, state_label: str, name: str, question: str,
                score: str, metric: str, split: str) -> str:
    return f"""<div class="nw-sys"><div class="bar" style="background:{color}"></div>
  {chip(state, state_label)}
  <div class="name">{escape(name)}</div>
  <p class="q">{escape(question)}</p>
  <div class="score">{escape(score)}</div>
  <div class="metric">{escape(metric)}</div>
  <div class="split">{escape(split)}</div>
</div>"""


def steps(items: list[tuple[str, str]]) -> str:
    cells = "".join(
        f'<div class="nw-step"><div class="n">0{i}</div><div class="t">{escape(t)}</div>'
        f'<div class="b">{escape(b)}</div></div>' for i, (t, b) in enumerate(items, 1))
    return f'<div class="nw-steps">{cells}</div>'


def empty(title: str, paragraphs: list[str]) -> str:
    body = "".join(f"<p>{escape(p)}</p>" for p in paragraphs)
    return f'<div class="nw-empty">{chip("unknown", "Model pending")}<h3>{escape(title)}</h3>{body}</div>'


def car_rank(cars: list[tuple[str, float | None]], baseline: str | None = None,
             fmt=lambda s: f"{s:+.2f} °C") -> str:
    """CarRank: every car listed best-first; rank 1 wears status-alert, the rest series-1.
    Bars normalise to the top score so a near-tie looks like a near-tie."""
    finite = [s for _, s in cars if s is not None]
    lo = min(finite) if finite else 0.0
    hi = max(finite) if finite else 1.0
    span = (hi - lo) or 1.0
    rows = []
    for i, (cid, s) in enumerate(cars, 1):
        if s is None:
            w, cls, txt = 0, "na", "no cooling evidence"
        else:
            w = max(6, round(100 * (s - lo) / span)) if hi > lo else 100
            cls, txt = ("top" if i == 1 else ""), fmt(s)
        rows.append(f'<div class="nw-rank-row {cls}"><span class="r">{i}</span>'
                    f'<span class="id">Car {escape(cid)}</span>'
                    f'<span class="bar"><span style="width:{w}%"></span></span>'
                    f'<span class="v">{escape(txt)}</span></div>')
    cap = f'<div class="cap">{escape(baseline)}</div>' if baseline else ""
    return f'<div class="nw-rank">{"".join(rows)}{cap}</div>'


def fleet_row(state: str, name: str, headline: str, detail: str) -> str:
    return (f'<div class="nw-fleet {state}"><div class="n">{escape(name)}</div>'
            f'<div class="h">{chip(state)}<span>{escape(headline)}</span></div>'
            f'<div class="d">{escape(detail)}</div></div>')
