"""Plotly figures, styled from the design-system tokens.

Rules carried from design-system/project/charts.md:
- one y-axis per chart; two measures become two panels, never a second axis
- text wears ink tokens, never a series colour
- status colours only for state; sequential ramp only for magnitude
- recessive hairline grid; hover on every mark
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from theme import T

LABEL_COLOR = {"Normal": "status-ok", "Abnormal resistance": "status-alert"}


def _base(fig: go.Figure, height: int, legend: bool = True) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=8, b=8),
        paper_bgcolor=T("surface-card"),
        plot_bgcolor=T("surface-plot"),
        font=dict(family="IBM Plex Sans, system-ui, sans-serif", size=12,
                  color=T("ink-secondary")),
        hoverlabel=dict(bgcolor=T("surface-card"), bordercolor=T("line-hairline"),
                        font=dict(family="IBM Plex Mono, monospace", size=12,
                                  color=T("ink-primary"))),
        showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0,
                    font=dict(color=T("ink-secondary"), size=12),
                    bgcolor="rgba(0,0,0,0)"),
        bargap=0.12,
    )
    axis = dict(gridcolor=T("line-hairline"), linecolor=T("line-hairline"),
                zerolinecolor=T("line-hairline"), tickcolor=T("line-hairline"),
                tickfont=dict(family="IBM Plex Mono, monospace", size=11,
                              color=T("ink-muted")),
                title_font=dict(size=12, color=T("ink-secondary")))
    fig.update_xaxes(**axis)
    fig.update_yaxes(**axis)
    return fig


def ramp_color(t: float) -> str:
    step = int(np.clip(np.ceil(np.clip(t, 0, 1) * 5), 1, 5))
    return T(f"ramp-{step}")


# --------------------------------------------------------------------- Door

def door_timeline(cycles: pd.DataFrame, span_s: float) -> go.Figure:
    fig = go.Figure()
    for label in ("Normal", "Abnormal resistance"):
        c = cycles[cycles["prediction"] == label]
        if c.empty:
            continue
        fig.add_trace(go.Bar(
            name=f"{label} ({len(c)})", orientation="h",
            y=["Stream"] * len(c), x=c["end_s"] - c["start_s"], base=c["start_s"],
            # No separator stroke: a 3.7 s cycle on a 24-minute axis is ~3 px wide,
            # and a 2 px stroke would erase it. The silence between cycles already
            # separates them.
            marker=dict(color=T(LABEL_COLOR[label]), line=dict(width=0)),
            width=0.9,
            customdata=np.c_[c["cycle"], c["operation"], c["start_time"],
                             c["p_abnormal"] * 100],
            hovertemplate=("Cycle %{customdata[0]} · %{customdata[1]}<br>"
                           "starts %{customdata[2]}<br>"
                           "P(abnormal) %{customdata[3]:.0f}%<extra>" + label + "</extra>"),
        ))
    fig.update_layout(barmode="overlay")
    fig.update_xaxes(title="seconds from stream start", range=[-span_s * 0.01, span_s * 1.01])
    fig.update_yaxes(showticklabels=False, showgrid=False)
    return _base(fig, 170)


def door_load(cycles: pd.DataFrame) -> go.Figure:
    """Sustained mid-cycle current per cycle: the feature the model leans on."""
    fig = go.Figure()
    for label in ("Normal", "Abnormal resistance"):
        for op, symbol in (("Close", "circle"), ("Open", "diamond")):
            c = cycles[(cycles["prediction"] == label) & (cycles["operation"] == op)]
            if c.empty:
                continue
            fig.add_trace(go.Scatter(
                name=f"{label} · {op}", mode="markers",
                x=c["cycle"], y=c["cur_mean_mid"],
                marker=dict(size=11, symbol=symbol, color=T(LABEL_COLOR[label]),
                            line=dict(color=T("surface-plot"), width=2)),
                customdata=np.c_[c["p_abnormal"] * 100, c["start_time"]],
                hovertemplate=("Cycle %{x} · " + op + "<br>sustained current %{y:.0f} mA"
                               "<br>P(abnormal) %{customdata[0]:.0f}%<br>%{customdata[1]}"
                               "<extra></extra>"),
            ))
    fig.update_xaxes(title="cycle", dtick=5)
    fig.update_yaxes(title="sustained current, mA")
    return _base(fig, 320)


def door_cycle_detail(trace: pd.DataFrame) -> go.Figure:
    """Current and door position for one cycle: two aligned panels, one axis each."""
    t = trace["t_s"] - trace["t_s"].iloc[0]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                        subplot_titles=("Motor current (mA)", "Door leaf position"))
    fig.add_trace(go.Scatter(x=t, y=trace["current_mA"], mode="lines", name="current",
                             line=dict(color=T("series-1"), width=2),
                             hovertemplate="%{x:.2f}s · %{y:.0f} mA<extra></extra>"), 1, 1)
    fig.add_trace(go.Scatter(x=t, y=trace["position"], mode="lines", name="position",
                             line=dict(color=T("ink-secondary"), width=2),
                             hovertemplate="%{x:.2f}s · position %{y:.0f}<extra></extra>"), 2, 1)
    fig.update_xaxes(title="seconds into cycle", row=2, col=1)
    for a in fig.layout.annotations:
        a.font = dict(size=12, color=T("ink-secondary"))
        a.x = 0
        a.xanchor = "left"
    fig = _base(fig, 400, legend=False)
    fig.update_layout(margin=dict(l=8, r=8, t=30, b=8))
    return fig


# ---------------------------------------------------------------------- SHM

def shm_damage(files: pd.DataFrame) -> go.Figure:
    d = files.sort_values("damage")
    fig = go.Figure(go.Bar(
        orientation="h", y=d["file_id"], x=d["damage"],
        marker=dict(color=[ramp_color(v) for v in d["damage"]],
                    line=dict(color=T("surface-plot"), width=2)),
        text=[f"{v:.3f}" for v in d["damage"]], textposition="outside",
        textfont=dict(family="IBM Plex Mono, monospace", size=11, color=T("ink-secondary")),
        cliponaxis=False,
        hovertemplate="%{y}<br>damage %{x:.4f}<br>%{customdata:.1f}% of fatigue life"
                      "<extra></extra>",
        customdata=d["damage"] * 100,
    ))
    fig.add_vline(x=1.0, line=dict(color=T("ink-primary"), width=2, dash="dot"))
    fig.add_annotation(x=1.0, y=1.0, yref="paper", text="end of fatigue life, D = 1",
                       showarrow=False, xanchor="right", yanchor="bottom",
                       font=dict(size=11, color=T("ink-secondary")))
    fig.update_xaxes(title="cumulative damage D", range=[0, 1.12])
    fig.update_yaxes(showgrid=False)
    return _base(fig, max(260, 26 * len(d) + 80), legend=False)


def shm_cycles_by_range(profile: pd.DataFrame) -> go.Figure:
    fig = go.Figure(go.Bar(
        x=profile["range_mid"], y=profile["cycles"],
        marker=dict(color=T("series-1"), line=dict(color=T("surface-plot"), width=1)),
        hovertemplate="stress range %{x:.1f}<br>%{y:,.0f} cycles<extra></extra>"))
    fig.update_yaxes(type="log", title="cycles (log scale)")
    fig.update_xaxes(title="stress range")
    return _base(fig, 280, legend=False)


def shm_damage_share(profile: pd.DataFrame) -> go.Figure:
    fig = go.Figure(go.Bar(
        x=profile["range_mid"], y=profile["damage_share"] * 100,
        marker=dict(color=T("ramp-4"), line=dict(color=T("surface-plot"), width=1)),
        hovertemplate="stress range %{x:.1f}<br>%{y:.1f}% of damage<extra></extra>"))
    fig.update_yaxes(title="share of damage, %")
    fig.update_xaxes(title="stress range")
    return _base(fig, 280, legend=False)


def shm_envelope(env: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=env["sample"], y=env["max"], mode="lines",
                             line=dict(color=T("series-1"), width=1), name="max",
                             hovertemplate="sample %{x:,}<br>max %{y:.2f}<extra></extra>"))
    fig.add_trace(go.Scatter(x=env["sample"], y=env["min"], mode="lines", fill="tonexty",
                             fillcolor="rgba(0,149,236,0.18)",
                             line=dict(color=T("series-1"), width=1), name="min",
                             hovertemplate="sample %{x:,}<br>min %{y:.2f}<extra></extra>"))
    fig.update_xaxes(title="sample index")
    fig.update_yaxes(title="stress")
    return _base(fig, 240, legend=False)
