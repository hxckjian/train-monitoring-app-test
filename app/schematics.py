"""Data-driven schematics, drawn only from values the models actually produce.

Each function returns inline SVG for st.markdown(unsafe_allow_html=True). Nothing
here invents a position or a value: the ACV train colours cars by their own
ranking scores, the Rail train colours each axle box by its own vibration RMS,
the Door diagram annotates a real cycle. SHM has no location data, so it gets
no schematic (see shm page: damage gauges per file instead).
"""
from __future__ import annotations

from html import escape

import pandas as pd

RAMP = ["#1b4a6b", "#1f6f9a", "#2e8fd4", "#d68a00", "#e0434f"]   # cool -> hot


def _ramp(v: float) -> str:
    v = 0.0 if v != v else max(0.0, min(1.0, v))
    return RAMP[min(4, int(v * 5))]


def _car(x: float, y: float, w: float, h: float, fill: str, label: str, sub: str = "", stroke: str = "#e8edf3") -> str:
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="9" fill="{fill}" stroke="{stroke}" stroke-opacity=".25"/>'
            f'<text x="{x + w / 2}" y="{y + 22}" text-anchor="middle" font-size="13" font-weight="600" fill="#e8edf3">{escape(label)}</text>'
            + (f'<text x="{x + w / 2}" y="{y + 40}" text-anchor="middle" font-size="11" fill="#e8edf3" fill-opacity=".85">{escape(sub)}</text>' if sub else ""))


def acv_train(ranking: list[str], scores: dict, hot: dict | None, unobserved: list[str]) -> str:
    """Eight cars in physical order (01..08), coloured by rank: rank 1 red, then the ramp
    down. Each car shows its mean excess and, when the v2 rule applies, hot-episode share."""
    cars = sorted(ranking)
    n = len(cars)
    w, gap, h = 96, 8, 64
    total = n * w + (n - 1) * gap + 40
    out = [f'<svg viewBox="0 0 {total} 120" width="100%" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Train cars ranked by likelihood of refrigerant leak">']
    out.append(f'<text x="20" y="16" font-size="11" fill="#8b96a3" letter-spacing="1.5">TRAIN · CARS 01–08 · RANK 1 = MOST LIKELY LEAK</text>')
    for i, c in enumerate(cars):
        x = 20 + i * (w + gap)
        rank = ranking.index(c) + 1
        if c in unobserved:
            fill, sub = "#0a0e13", "no evidence"
        else:
            fill = "#e0434f" if rank == 1 else _ramp(1 - (rank - 1) / max(1, n - 1)) if rank <= 3 else "#1b2a3a"
            s = scores.get(c)
            sub = (f"{hot.get(c, 0):.1%} hot · " if hot else "") + (f"{s:+.2f} °C" if isinstance(s, (int, float)) else "")
        out.append(_car(x, 30, w, h, fill, f"Car {c} · #{rank}", sub))
        # bogies
        for bx in (x + 18, x + w - 18):
            out.append(f'<circle cx="{bx}" cy="104" r="6" fill="#161d26" stroke="#8b96a3"/>')
    out.append('</svg>')
    return "".join(out)


def rail_train(grid: pd.DataFrame, prediction: str) -> str:
    """Side view: 8 cars, each with 4 axle boxes per rail side, coloured by that box's
    own vibration RMS (normalised within the recording). Side I row above, Side II below."""
    cars = sorted(grid["car"].unique())
    w, gap = 104, 8
    total = 20 + len(cars) * (w + gap) + 60
    lookup = {(int(r.car), int(r.position)): (float(r.value), float(r.rms)) for r in grid.itertuples()}
    out = [f'<svg viewBox="0 0 {total} 170" width="100%" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Axle-box vibration per car and rail side">']
    hot = "SIDE I" if prediction == "Side I" else "SIDE II" if prediction == "Side II" else "NEITHER"
    out.append(f'<text x="20" y="16" font-size="11" fill="#8b96a3" letter-spacing="1.5">AXLE-BOX VIBRATION · VERDICT {escape(prediction.upper())} · CORRUGATED RAIL: {hot}</text>')
    out.append('<text x="20" y="62" font-size="10" fill="#b3bdc9">Side I rail</text>')
    out.append('<text x="20" y="152" font-size="10" fill="#b3bdc9">Side II rail</text>')
    for i, car in enumerate(cars):
        x = 80 + i * (w + gap)
        out.append(f'<rect x="{x}" y="70" width="{w}" height="50" rx="8" fill="#161d26" stroke="#e8edf3" stroke-opacity=".2"/>')
        out.append(f'<text x="{x + w / 2}" y="100" text-anchor="middle" font-size="12" font-weight="600" fill="#e8edf3">Car {car}</text>')
        for k, pos in enumerate((1, 3, 5, 7)):        # Side I boxes above
            v, rms = lookup.get((car, pos), (0.0, 0.0))
            out.append(f'<circle cx="{x + 14 + k * 25}" cy="60" r="8" fill="{_ramp(v)}" stroke="#0e1319"><title>Car {car} pos {pos} · RMS {rms:.3f}</title></circle>')
        for k, pos in enumerate((2, 4, 6, 8)):        # Side II boxes below
            v, rms = lookup.get((car, pos), (0.0, 0.0))
            out.append(f'<circle cx="{x + 14 + k * 25}" cy="132" r="8" fill="{_ramp(v)}" stroke="#0e1319"><title>Car {car} pos {pos} · RMS {rms:.3f}</title></circle>')
    # rails
    y1 = 60 if prediction == "Side I" else None
    for y, side in ((48, "Side I"), (144, "Side II")):
        col = "#e0434f" if prediction == side else "#3a4756"
        out.append(f'<line x1="70" y1="{y}" x2="{total - 20}" y2="{y}" stroke="{col}" stroke-width="{4 if prediction == side else 2}" stroke-dasharray="{"6 4" if prediction == side else "0"}"/>')
    out.append('</svg>')
    return "".join(out)


def door_cycle(row: pd.Series) -> str:
    """One door cycle: leaf travel, sustained current, duration, verdict, from that cycle's values."""
    abnormal = row["prediction"] == "Abnormal resistance"
    col = "#e0434f" if abnormal else "#16a97a"
    travel = float(row.get("pos_range", 0) or 0)
    out = ['<svg viewBox="0 0 640 150" width="100%" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Door cycle diagram">',
           '<text x="16" y="16" font-size="11" fill="#8b96a3" letter-spacing="1.5">DOOR LEAF · MOTOR · ONE CYCLE</text>',
           # door frame and leaf
           '<rect x="16" y="30" width="220" height="100" rx="6" fill="#0a0e13" stroke="#3a4756"/>',
           f'<rect x="{30 if row["operation"] == "Close" else 120}" y="38" width="100" height="84" rx="4" fill="{col}" fill-opacity=".85"/>',
           f'<text x="126" y="140" text-anchor="middle" font-size="10" fill="#b3bdc9">leaf {row["operation"].lower()}s · travel {travel:.0f}</text>',
           # motor + values
           '<circle cx="300" cy="80" r="26" fill="#161d26" stroke="#8b96a3"/>',
           '<text x="300" y="84" text-anchor="middle" font-size="10" fill="#e8edf3">motor</text>',
           f'<line x1="236" y1="80" x2="274" y2="80" stroke="{col}" stroke-width="3"/>',
           f'<text x="350" y="56" font-size="13" font-weight="600" fill="#e8edf3">{escape(str(row["prediction"]))}</text>',
           f'<text x="350" y="78" font-size="12" fill="#b3bdc9">sustained current {row["cur_mean_mid"]:.0f} mA · P(abnormal) {row["p_abnormal"]:.0%}</text>',
           f'<text x="350" y="98" font-size="12" fill="#b3bdc9">duration {row["duration_s"]:.2f} s · current per back-EMF {row.get("cur_per_emf", float("nan")):.2f}</text>',
           f'<text x="350" y="118" font-size="11" fill="#8b96a3">{escape(str(row["start_time"]))}</text>',
           '</svg>']
    return "".join(out)
