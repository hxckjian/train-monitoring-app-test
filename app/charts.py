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


# --------------------------------------------------------------------- Rail

RAIL_COLOR = {"Normal": "status-ok", "Side I": "status-alert", "Side II": "status-alert"}


def _ramp_scale() -> list:
    return [[i / 4, T(f"ramp-{i + 1}")] for i in range(5)]


def rail_axle_grid(grid: pd.DataFrame) -> go.Figure:
    """AxleGrid: 8 cars across, positions down, split into the two rails."""
    fig = make_subplots(rows=1, cols=2, horizontal_spacing=0.06,
                        subplot_titles=("Side I rail · positions 1, 3, 5, 7",
                                        "Side II rail · positions 2, 4, 6, 8"))
    for col, side in ((1, "Side I"), (2, "Side II")):
        g = grid[grid["side"] == side]
        pv = g.pivot(index="position", columns="car", values="value").sort_index(ascending=False)
        rms = g.pivot(index="position", columns="car", values="rms").sort_index(ascending=False)
        fig.add_trace(go.Heatmap(
            z=pv.values, x=[f"Car {c}" for c in pv.columns], y=[f"Pos {p}" for p in pv.index],
            customdata=rms.values, zmin=0, zmax=1, colorscale=_ramp_scale(),
            xgap=2, ygap=2, showscale=(col == 2),
            colorbar=dict(title="relative<br>energy", thickness=10, len=0.9,
                          tickfont=dict(size=10, color=T("ink-muted"))),
            hovertemplate="%{x} · %{y} · " + side + "<br>vibration RMS %{customdata:.3f} m/s²"
                          "<br>relative %{z:.2f}<extra></extra>"), 1, col)
    for a in fig.layout.annotations:
        a.font = dict(size=12, color=T("ink-secondary"))
    fig = _base(fig, 300, legend=False)
    fig.update_layout(margin=dict(l=8, r=8, t=30, b=8))
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=False)
    return fig


def rail_spectrum(spec: pd.DataFrame) -> go.Figure:
    """Mean vibration spectrum per rail, in the wavelength domain (λ = v / f)."""
    use_wl = "wavelength_cm" in spec.columns
    x = spec["wavelength_cm"] if use_wl else spec["f_hz"]
    fig = go.Figure()
    for side, color in (("Side I", "series-1"), ("Side II", "ink-secondary")):
        fig.add_trace(go.Scatter(
            x=x, y=spec[side], mode="lines", name=side,
            line=dict(color=T(color), width=2),
            customdata=spec["f_hz"],
            hovertemplate=(side + "<br>" + ("wavelength %{x:.1f} cm · " if use_wl else "")
                           + "%{customdata:.0f} Hz<br>power %{y:.3g}<extra></extra>")))
    if use_wl:
        fig.add_vrect(x0=3, x1=30, fillcolor=T("status-watch-soft"), opacity=0.5, line_width=0,
                      annotation_text="typical corrugation pitch 3–30 cm",
                      annotation_position="top left",
                      annotation_font=dict(size=11, color=T("ink-secondary")))
        fig.update_xaxes(type="log", title="wavelength along the rail, cm (speed-normalised)",
                         autorange="reversed")
    else:
        fig.update_xaxes(type="log", title="frequency, Hz (speed unavailable)")
    fig.update_yaxes(type="log", title="mean vibration power")
    return _base(fig, 300)


def rail_summary(files: pd.DataFrame) -> go.Figure:
    counts = files["prediction"].value_counts().reindex(["Normal", "Side I", "Side II"]).fillna(0)
    fig = go.Figure(go.Bar(
        x=counts.index, y=counts.values,
        marker=dict(color=[T(RAIL_COLOR[k]) for k in counts.index],
                    line=dict(color=T("surface-plot"), width=2)),
        text=[f"{int(v)}" for v in counts.values], textposition="outside", cliponaxis=False,
        textfont=dict(family="IBM Plex Mono, monospace", size=12, color=T("ink-secondary")),
        hovertemplate="%{x}: %{y} file(s)<extra></extra>"))
    fig.update_yaxes(title="files", rangemode="tozero")
    return _base(fig, 240, legend=False)


# ---------------------------------------------------------------------- ACV

def acv_excess(excess: pd.DataFrame, ranking: list[str]) -> go.Figure:
    """Cabin temperature minus the other cars' median, per car, during cooling."""
    fig = go.Figure()
    top = ranking[0]
    for cid in ranking[::-1]:
        if cid not in excess.columns:
            continue
        is_top = cid == top
        fig.add_trace(go.Scatter(
            x=excess["time"], y=excess[cid], mode="lines", name=f"Car {cid}",
            line=dict(color=T("status-alert") if is_top else T("ink-muted"),
                      width=2.5 if is_top else 1),
            opacity=1.0 if is_top else 0.55,
            hovertemplate=f"Car {cid}<br>%{{x}}<br>%{{y:+.2f}} °C vs peers<extra></extra>"))
    fig.add_hline(y=0, line=dict(color=T("ink-primary"), width=1, dash="dot"))
    fig.update_yaxes(title="°C above the other cars")
    fig.update_xaxes(title="time")
    return _base(fig, 320)


# ----------------------------------------------------------- validation

def fold_scores(folds: list[float], mean: float, std: float, baseline: float | None,
                label: str, in_sample: float | None = None) -> go.Figure:
    """Per-fold scores as dots, the mean as a line, ±1 sd as a band, the baseline dotted."""
    fig = go.Figure()
    x = list(range(1, len(folds) + 1))
    fig.add_trace(go.Scatter(x=[0.5, len(folds) + 0.5, len(folds) + 0.5, 0.5],
                             y=[mean - std, mean - std, mean + std, mean + std], fill="toself",
                             fillcolor="rgba(0,149,236,0.12)", line=dict(width=0), hoverinfo="skip",
                             name="mean ± 1 sd"))
    fig.add_trace(go.Scatter(x=x, y=folds, mode="markers", name="held-out fold",
                             marker=dict(size=12, color=T("series-1"),
                                         line=dict(color=T("surface-plot"), width=2)),
                             hovertemplate="fold %{x}<br>" + label + " %{y:.4f}<extra></extra>"))
    fig.add_hline(y=mean, line=dict(color=T("ink-primary"), width=2))
    if in_sample is not None:
        fig.add_hline(y=in_sample, line=dict(color=T("status-watch"), width=1.5, dash="dash"),
                      annotation_text=f"in-sample {in_sample:.3f}", annotation_position="top left",
                      annotation_font=dict(size=11, color=T("ink-secondary")))
    if baseline is not None:
        fig.add_hline(y=baseline, line=dict(color=T("ink-muted"), width=1.5, dash="dot"),
                      annotation_text=f"naive baseline {baseline:.3f}",
                      annotation_position="bottom left",
                      annotation_font=dict(size=11, color=T("ink-secondary")))
    fig.update_xaxes(title="fold", dtick=1, range=[0.5, len(folds) + 0.5])
    lo = min([baseline if baseline is not None else mean] + folds + [in_sample or mean]) - 0.05
    fig.update_yaxes(title=label, range=[max(0, lo), 1.02])
    return _base(fig, 280)


# --------------------------------------------------------------- trends

def door_trend(g: pd.DataFrame) -> go.Figure:
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1,
                        subplot_titles=("Abnormal cycles per 5-minute window",
                                        "Mean sustained current, mA"))
    fig.add_trace(go.Bar(x=g["window_min"], y=g["abnormal"], name="abnormal",
                         marker=dict(color=T("status-alert")),
                         hovertemplate="min %{x}: %{y} abnormal<extra></extra>"), 1, 1)
    fig.add_trace(go.Bar(x=g["window_min"], y=g["cycles"] - g["abnormal"], name="normal",
                         marker=dict(color=T("status-ok")),
                         hovertemplate="min %{x}: %{y} normal<extra></extra>"), 1, 1)
    fig.add_trace(go.Scatter(x=g["window_min"], y=g["mean_current"], mode="lines+markers",
                             name="current", line=dict(color=T("series-1"), width=2),
                             hovertemplate="min %{x}: %{y:.0f} mA<extra></extra>"), 2, 1)
    fig.update_layout(barmode="stack")
    fig.update_xaxes(title="minutes from stream start", row=2, col=1)
    for a in fig.layout.annotations:
        a.font = dict(size=12, color=T("ink-secondary"))
        a.x = 0
        a.xanchor = "left"
    fig = _base(fig, 340, legend=False)
    fig.update_layout(margin=dict(l=8, r=8, t=30, b=8))
    return fig


def rail_trend(d: pd.DataFrame) -> go.Figure:
    fig = go.Figure(go.Bar(
        x=d["file_id"], y=d["p_corrugated"],
        marker=dict(color=[T(RAIL_COLOR[p]) for p in d["prediction"]], line=dict(width=0)),
        customdata=np.c_[d["prediction"], d["speed_km_h"]],
        hovertemplate="%{x}<br>P(corrugated) %{y:.0%}<br>%{customdata[0]} · "
                      "%{customdata[1]:.0f} km/h<extra></extra>"))
    fig.add_hline(y=0.5, line=dict(color=T("ink-muted"), width=1, dash="dot"))
    fig.update_yaxes(title="P(corrugated)", range=[0, 1])
    fig.update_xaxes(title="recording", showticklabels=len(d) <= 24)
    return _base(fig, 260, legend=False)


def acv_trend(d: pd.DataFrame) -> go.Figure:
    fig = go.Figure(go.Bar(x=d["day"], y=d["excess"], marker=dict(color=T("status-alert")),
                           hovertemplate="%{x|%d %b}: %{y:+.2f} °C<extra></extra>"))
    fig.add_hline(y=0, line=dict(color=T("ink-primary"), width=1))
    fig.update_yaxes(title=f"Car {d['car'].iloc[0]} excess, °C / day")
    return _base(fig, 240, legend=False)


def generic_excess(ex: pd.DataFrame, units: list[str], top: str) -> go.Figure:
    fig = go.Figure()
    for u in units[::-1]:
        is_top = u == top
        fig.add_trace(go.Scatter(x=ex["time"], y=ex[u], mode="lines", name=str(u),
                                 line=dict(color=T("status-alert") if is_top else T("ink-muted"),
                                           width=2.5 if is_top else 1),
                                 opacity=1 if is_top else 0.5,
                                 hovertemplate=f"{u}<br>%{{y:+.2f}} vs peers<extra></extra>"))
    fig.add_hline(y=0, line=dict(color=T("ink-primary"), width=1, dash="dot"))
    fig.update_yaxes(title="excess over the other units")
    return _base(fig, 300)


def generic_drift(d: pd.DataFrame) -> go.Figure:
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1,
                        subplot_titles=("Value and rolling median",
                                        "Robust drift score (MAD units)"))
    fig.add_trace(go.Scatter(x=d["index"], y=d["value"], mode="lines", name="value",
                             line=dict(color=T("ink-muted"), width=1)), 1, 1)
    fig.add_trace(go.Scatter(x=d["index"], y=d["rolling_median"], mode="lines",
                             name="rolling median", line=dict(color=T("series-1"), width=2)), 1, 1)
    fig.add_trace(go.Scatter(x=d["index"], y=d["robust_z"], mode="lines", name="score",
                             line=dict(color=T("status-alert"), width=2)), 2, 1)
    for y in (-3, 3):
        fig.add_hline(y=y, line=dict(color=T("ink-muted"), width=1, dash="dot"), row=2, col=1)
    for a in fig.layout.annotations:
        a.font = dict(size=12, color=T("ink-secondary"))
        a.x = 0
        a.xanchor = "left"
    fig = _base(fig, 380, legend=False)
    fig.update_layout(margin=dict(l=8, r=8, t=30, b=8))
    return fig


# ----------------------------------------------------------- forecast / importances

def shm_forecast(files: pd.DataFrame) -> go.Figure:
    d = files.sort_values("segments_to_failure")
    fig = go.Figure(go.Bar(
        orientation="h", y=d["file_id"], x=d["segments_to_failure"],
        marker=dict(color=[ramp_color(1 - min(1.0, v / max(float(d["segments_to_failure"].max()), 1e-9)))
                           for v in d["segments_to_failure"]],
                    line=dict(color=T("surface-plot"), width=2)),
        text=[f"{v:.1f}" for v in d["segments_to_failure"]], textposition="outside", cliponaxis=False,
        textfont=dict(family="IBM Plex Mono, monospace", size=11, color=T("ink-secondary")),
        customdata=d["damage"],
        hovertemplate="%{y}<br>%{x:.1f} more segments at this rate<br>D now %{customdata:.3f}<extra></extra>"))
    fig.update_xaxes(title="segments of equal length until D = 1 (log)", type="log")
    fig.update_yaxes(showgrid=False)
    return _base(fig, max(240, 26 * len(d) + 80), legend=False)


def importances(imp: pd.Series, top: int = 12) -> go.Figure:
    s = imp.sort_values(ascending=False).head(top)[::-1]
    fig = go.Figure(go.Bar(
        orientation="h", y=[str(i)[:38] for i in s.index], x=s.values,
        marker=dict(color=T("series-1"), line=dict(color=T("surface-plot"), width=2)),
        hovertemplate="%{y}<br>importance %{x:.3f}<extra></extra>"))
    fig.update_xaxes(title="importance")
    fig.update_yaxes(showgrid=False, tickfont=dict(size=10))
    return _base(fig, 26 * len(s) + 60, legend=False)
