"""Nebula Wayside - train condition monitoring console.

Run from the project root:

    streamlit run app/streamlit_app.py

The app contains no modelling code. Every prediction comes from a subsystem
package's predict()/analyze(), discovered through core.registry, and every
download passes core.submission's schema validator first.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent
for p in (str(PROJECT_ROOT), str(APP_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

import charts  # noqa: E402
import components as ui  # noqa: E402
import livemap  # noqa: E402
from core.registry import SUBSYSTEMS, SubsystemSpec  # noqa: E402
from core.submission import SCHEMAS, build_predictions_zip, validate_submission  # noqa: E402
from theme import T, css  # noqa: E402

st.set_page_config(page_title="Nebula Wayside", page_icon="🚆", layout="wide")
st.markdown(css(), unsafe_allow_html=True)

IDENTITY = {"door": "subsystem-door", "shm": "subsystem-shm",
            "rail": "subsystem-rail", "acv": "subsystem-acv"}

#: Illustrative planning bands for SHM. Miner's rule fixes failure at D = 1;
#: where an operator starts watching or acting is their call, not the model's.
SHM_WATCH, SHM_ALERT = 0.5, 0.8
METRIC_SHORT = {"door": "IoU-weighted F1", "shm": "max(0, 1 − MAPE)",
                "rail": "macro F1", "acv": "rank decay"}


def html(s: str) -> None:
    st.markdown(s, unsafe_allow_html=True)


def plot(fig) -> None:
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def as_files(payload: list[tuple[str, bytes]]) -> list[io.BytesIO]:
    out = []
    for name, data in payload:
        b = io.BytesIO(data)
        b.name = name
        out.append(b)
    return out


def choose_input(spec: SubsystemSpec) -> list[tuple[str, bytes]] | None:
    """Provided test data or an upload - the same two choices on every page."""
    provided = spec.test_inputs()
    options = (["Provided test data", "Upload a file"] if provided else ["Upload a file"])
    mode = st.segmented_control("Data source", options, default=options[0],
                                key=f"{spec.key}_src") or options[0]
    if mode == "Provided test data":
        what = (provided[0].name if len(provided) == 1
                else f"{len(provided)} files, {provided[0].name} to {provided[-1].name}")
        st.caption(f"From the competition test set: {what}")
        return [(p.name, p.read_bytes()) for p in provided]
    up = st.file_uploader(
        f"Drop {'one or more' if spec.multi_file else 'a'} .{'/.'.join(spec.accepts)} file"
        f"{'s' if spec.multi_file else ''} here", type=list(spec.accepts),
        accept_multiple_files=spec.multi_file, key=f"{spec.key}_upload")
    if not up:
        return None
    ups = up if isinstance(up, list) else [up]
    return [(u.name, u.getvalue()) for u in ups]


def run_panel(spec: SubsystemSpec, button: str):
    """Input + run button. Returns the stored result for this subsystem, if any."""
    payload = choose_input(spec)
    if st.button(button, type="primary", disabled=payload is None, key=f"{spec.key}_run"):
        try:
            if spec.key in ("shm", "rail", "acv"):
                verb = {"shm": "Rainflow-counted", "rail": "Analysed", "acv": "Ranked"}[spec.key]
                bar = st.progress(0.0, text="Starting...")

                def tick(i, n, name):
                    bar.progress(i / n, text=f"{verb} {name}  ({i}/{n})")

                res = spec.module.analyze(as_files(payload), progress=tick)
                bar.empty()
            else:
                with st.spinner("Analysing..."):
                    res = spec.module.analyze(as_files(payload))
            st.session_state[f"{spec.key}_result"] = res
        except (ValueError, FileNotFoundError) as exc:
            st.session_state.pop(f"{spec.key}_result", None)
            html(ui.verdict("unknown", spec.name, "This input could not be assessed",
                            str(exc), "Check the file is the right format for this "
                            "subsystem and try again.", "no prediction was made"))
            return None
    return st.session_state.get(f"{spec.key}_result")


def download(spec: SubsystemSpec, df: pd.DataFrame) -> None:
    errors = validate_submission(spec.key, df)
    if errors:
        st.error("Not downloadable - the output failed schema validation:\n\n- "
                 + "\n- ".join(errors))
        return
    st.download_button(f"Download {SCHEMAS[spec.key].filename}",
                       df.to_csv(index=False).encode(), SCHEMAS[spec.key].filename,
                       "text/csv", type="primary", key=f"{spec.key}_dl")


def evidence_line(card: dict, metric_short: str) -> str:
    v = card["validation"]
    mean = v.get("mean_iou_weighted_f1", v.get("mean_score"))
    std = v.get("std_iou_weighted_f1", v.get("std_score"))
    return f"{metric_short} {mean:.3f} ± {std:.3f} · {v['split']} · model {card['model_version']}"


# =================================================================== pages

def overview_page() -> None:
    html(ui.header("Train condition monitoring", "Fleet condition",
                   "Four independent health checks on a rail vehicle, each with its own "
                   "validated model. Pick a subsystem, give it a file, and read the verdict."))
    html(ui.steps([
        ("Pick a subsystem", "Door, structural health, rail corrugation or air conditioning."),
        ("Give it data", "Use the provided competition test data, or drop in your own file."),
        ("Read the verdict", "A status, what it means, what to do, and the evidence behind it."),
        ("See it on the network", "Fleet view puts every verdict on the live rail map next to "
                                  "the current service alerts."),
    ]))
    html(ui.section("Subsystems"))
    cols = st.columns(4, gap="small")
    for col, spec in zip(cols, SUBSYSTEMS.values()):
        card = spec.model_card()
        color = T(IDENTITY[spec.key])
        with col:
            if card:
                v = card["validation"]
                mean = v.get("mean_iou_weighted_f1", v.get("mean_score"))
                std = v.get("std_iou_weighted_f1", v.get("std_score"))
                metric = METRIC_SHORT[spec.key]
                html(ui.system_tile(color, "ok", "Model live", spec.name, spec.question,
                                    f"{mean:.3f} ± {std:.3f}", f"{metric}, cross-validated",
                                    spec.method))
            else:
                html(ui.system_tile(color, "unknown", "Model pending", spec.name,
                                    spec.question, "—", "not yet validated", spec.method))
    st.caption("Scores are the official competition metric on held-out folds of the "
               "training data, with the split chosen to prevent leakage. They are estimates, "
               "not the final test score.")


def door_page() -> None:
    spec, card = SUBSYSTEMS["door"], SUBSYSTEMS["door"].model_card()
    html(ui.header("Door · abnormal resistance", "Door cycles",
                   "The door controller streams motor current, voltage, back-EMF and "
                   "door position. This finds every open or close cycle in the stream "
                   "and checks each one for abnormal resistance.", T("subsystem-door")))
    res = run_panel(spec, "Analyse door stream")
    if not res:
        return
    cyc, trace = res["cycles"], res["trace"]
    if cyc.empty:
        html(ui.verdict("unknown", "Door", "No door cycles found",
                        "The stream contained no gap-separated cycles.",
                        "Check this is a door-controller stream.", evidence_line(card, "IoU-F1")))
        return

    n = len(cyc)
    abn = cyc[cyc["prediction"] == "Abnormal resistance"]
    nrm = cyc[cyc["prediction"] == "Normal"]
    span = float(cyc["end_s"].max())

    html(ui.kpis([
        ("Cycles detected", f"{n}", f"in {span / 60:.1f} min of stream"),
        ("Abnormal resistance", f"{len(abn)}", f"{len(abn) / n:.0%} of cycles"),
        ("Normal", f"{len(nrm)}", None),
        ("Segmentation gap", f"{card['gap_seconds']:.2f}s", "derived from data, not tuned"),
    ]))
    st.write("")

    if len(abn):
        excess = []
        for op in ("Close", "Open"):
            a = abn[abn.operation == op]["cur_mean_mid"]
            b = nrm[nrm.operation == op]["cur_mean_mid"]
            if len(a) and len(b):
                excess.append(a.mean() / b.mean() - 1)
        pct = f"about {100 * sum(excess) / len(excess):.0f}% more" if excess else "more"
        ids = ", ".join(str(c) for c in abn["cycle"].head(8))
        more = f" and {len(abn) - 8} more" if len(abn) > 8 else ""
        html(ui.verdict(
            "alert", "Door",
            f"{len(abn)} of {n} door cycles show abnormal resistance",
            f"The flagged cycles drew {pct} sustained motor current than normal cycles "
            "moving the same way. Resistance forces the motor to work harder for the same "
            "travel, which is the signature of a foreign object in the slide rail, a "
            "jamming seal or a deformed door leaf.",
            f"Inspect the slide rails, rubber seals and leaf alignment. Flagged cycles: {ids}{more}.",
            evidence_line(card, "IoU-weighted F1"), "Abnormal resistance"))
    else:
        html(ui.verdict("ok", "Door", f"All {n} door cycles are normal",
                        "Every cycle drew motor current in line with normal operation.",
                        "No action needed.", evidence_line(card, "IoU-weighted F1")))

    html(ui.section("Where the cycles are"))
    plot(charts.door_timeline(cyc, span))

    left, right = st.columns([1.1, 1], gap="medium")
    with left:
        html(ui.section("Sustained current per cycle"))
        plot(charts.door_load(cyc))
        st.caption("Mean motor current over the middle 60% of each cycle, excluding "
                   "start-up inrush. This is the model's strongest single feature.")
    with right:
        html(ui.section("Inspect a cycle"))
        default = int(abn["cycle"].iloc[0]) if len(abn) else 1
        options = list(cyc["cycle"])
        pick = st.selectbox(
            "Cycle", options, index=options.index(default),
            format_func=lambda c: f"Cycle {c} · {cyc.set_index('cycle').loc[c, 'operation']}"
                                  f" · {cyc.set_index('cycle').loc[c, 'prediction']}")
        row = cyc.set_index("cycle").loc[pick]
        state = "alert" if row["prediction"] == "Abnormal resistance" else "ok"
        html(ui.chip(state, row["prediction"],
                     f"P(abnormal) {row['p_abnormal']:.0%} · {row['duration_s']:.2f}s · "
                     f"{row['start_time']}"))
        plot(charts.door_cycle_detail(trace[trace["cycle"] == pick]))

    html(ui.section("Predictions"))
    st.dataframe(
        cyc[["cycle", "start_time", "end_time", "operation", "prediction", "p_abnormal",
             "cur_mean_mid"]],
        hide_index=True, width="stretch",
        column_config={
            "p_abnormal": st.column_config.ProgressColumn("P(abnormal)", min_value=0.0,
                                                          max_value=1.0, format="%.2f"),
            "cur_mean_mid": st.column_config.NumberColumn("Sustained mA", format="%.0f"),
        })
    download(spec, res["predictions"])


def shm_page() -> None:
    spec, card = SUBSYSTEMS["shm"], SUBSYSTEMS["shm"].model_card()
    html(ui.header("Structural health · fatigue", "Cumulative fatigue damage",
                   "Each file is a long dynamic-stress recording from one measurement point. "
                   "This counts every stress cycle and converts them into fatigue damage, "
                   "where 1.0 is the end of the structure's fatigue life.", T("subsystem-shm")))
    res = run_panel(spec, "Assess fatigue damage")
    if not res:
        return

    files = pd.DataFrame([{k: v for k, v in f.items() if k not in ("profile", "envelope")}
                          for f in res["files"]])
    worst = files.loc[files["damage"].idxmax()]
    n_watch = int((files["damage"] >= SHM_WATCH).sum())
    n_alert = int((files["damage"] >= SHM_ALERT).sum())

    html(ui.kpis([
        ("Files assessed", f"{len(files)}", f"{files['n_cycles'].sum() / 1e6:.1f}M stress cycles counted"),
        ("Highest damage", f"{worst['damage']:.3f}", str(worst["file_id"])),
        ("Median damage", f"{files['damage'].median():.3f}", None),
        (f"At or above {SHM_WATCH}", f"{n_watch}", f"{n_alert} at or above {SHM_ALERT}"),
    ]))
    st.write("")

    ev = (evidence_line(card, "max(0,1−MAPE)") + f" · m = {card['m']:.3f}")
    if n_alert:
        state, title = "alert", f"{worst['file_id']} has used {worst['damage']:.0%} of its fatigue life"
        action = (f"Prioritise inspection at the measurement point behind {worst['file_id']}"
                  + (f" and {n_alert - 1} other file(s) above {SHM_ALERT}" if n_alert > 1 else "")
                  + ". Review the loading history for the high-amplitude cycles below.")
    elif n_watch:
        state, title = "watch", f"{n_watch} file(s) past the watch band"
        action = "Schedule inspection of the flagged measurement points at the next planned service."
    else:
        state, title = "ok", f"All {len(files)} files are below the watch band"
        action = "No action needed. Continue routine monitoring."
    html(ui.verdict(
        state, "Structural health", title,
        "Every stress cycle uses up a little fatigue life, and large cycles use far more than "
        "small ones - damage scales with stress range to the power m, and for this structure "
        f"m ≈ {card['m']:.1f}, the textbook exponent for welded steel. Under Miner's rule the "
        "structure reaches the end of its fatigue life at D = 1.",
        action, ev))
    st.caption(f"Watch ({SHM_WATCH}) and alert ({SHM_ALERT}) bands are illustrative planning "
               "thresholds for an operator to set. The model predicts D; it does not choose them.")

    html(ui.section("Damage by file"))
    plot(charts.shm_damage(files))

    html(ui.section("Inspect a file"))
    ids = list(files["file_id"])
    pick = st.selectbox("File", ids, index=ids.index(worst["file_id"]))
    f = next(x for x in res["files"] if x["file_id"] == pick)
    html(ui.kpis([
        ("Damage", f"{f['damage']:.4f}", f"{f['damage']:.1%} of fatigue life"),
        ("Stress cycles counted", f"{f['n_cycles']:,.0f}", f"from {f['n_samples']:,} samples"),
        ("Largest stress range", f"{f['max_range']:.1f}", None),
        ("Damage from the largest 0.1% of cycles", f"{f['top_share']:.1%}",
         "a handful of large cycles do almost all of it"),
    ]))
    a, b = st.columns(2, gap="medium")
    with a:
        html(ui.section("How many cycles, by stress range"))
        plot(charts.shm_cycles_by_range(f["profile"]))
    with b:
        html(ui.section("Where the damage comes from"))
        plot(charts.shm_damage_share(f["profile"]))
    st.caption("Almost all cycles are small, but damage grows as range to the power m, so "
               "the rare large cycles on the right cause most of it.")
    with st.expander("Stress history (min/max envelope, peaks preserved)"):
        plot(charts.shm_envelope(f["envelope"]))

    html(ui.section("Predictions"))
    st.dataframe(files[["file_id", "damage", "n_cycles", "top_share"]],
                 hide_index=True, width="stretch",
                 column_config={
                     "damage": st.column_config.ProgressColumn("Damage D", min_value=0.0,
                                                               max_value=1.0, format="%.4f"),
                     "n_cycles": st.column_config.NumberColumn("Cycles", format="%,.0f"),
                     "top_share": st.column_config.NumberColumn(
                         "Share from top 0.1% of cycles", format="percent"),
                 })
    download(spec, res["predictions"])


def pending_page(key: str, facts: list[str]) -> None:
    spec = SUBSYSTEMS[key]
    html(ui.header(f"{spec.name}", spec.name, spec.question, T(IDENTITY[key])))
    html(ui.empty(
        "No validated model yet",
        ["This console only shows predictions from models that have passed a leakage-safe "
         "validation. Rather than show an unvalidated guess, this subsystem stays pending "
         "until its model does.",
         f"When ready it will predict {spec.predicts}, using {spec.method.replace('planned: ', '')}."]))
    html(ui.section("What we already know about this data"))
    for fact in facts:
        st.markdown(f"- {fact}")


def rail_page() -> None:
    spec, card = SUBSYSTEMS["rail"], SUBSYSTEMS["rail"].model_card()
    html(ui.header("Rail · corrugation", "Rail corrugation",
                   "Each file is one second of axle-box vibration and shock from all 64 "
                   "bearings of an 8-car train at 10 kHz, plus a rotating-speed pulse. "
                   "Positions 1, 3, 5, 7 ride the Side I rail and 2, 4, 6, 8 the Side II rail, "
                   "so the two rails are judged independently.", T("subsystem-rail")))
    res = run_panel(spec, "Classify recordings")
    if not res:
        return
    files = pd.DataFrame([{"file_id": f["file_id"], "prediction": f["prediction"],
                           "speed_km_h": f["speed"]["speed_km_h"],
                           "side_i_rms": f["side_i_rms"], "side_ii_rms": f["side_ii_rms"],
                           **{f"p_{k}": v for k, v in f["proba"].items()}}
                          for f in res["files"]])
    flagged = files[files["prediction"] != "Normal"]
    v = card["validation"]
    ev = (f"macro F1 {v['mean_score']:.3f} ± {v['std_score']:.3f} · {v['split'].split(',')[0]} · "
          f"Side I recall {v['side_i_recall']:.2f} · model {card['model_version']}")

    html(ui.kpis([
        ("Recordings", f"{len(files)}", f"{files['speed_km_h'].mean():.0f} km/h mean speed from the pulse"),
        ("Side I corrugation", f"{int((files.prediction == 'Side I').sum())}", None),
        ("Side II corrugation", f"{int((files.prediction == 'Side II').sum())}", None),
        ("Normal", f"{int((files.prediction == 'Normal').sum())}", None),
    ]))
    st.write("")
    if len(flagged):
        ids = ", ".join(f"{r.file_id} ({r.prediction})" for r in flagged.head(6).itertuples())
        more = f" and {len(flagged) - 6} more" if len(flagged) > 6 else ""
        html(ui.verdict(
            "alert", "Rail corrugation",
            f"{len(flagged)} of {len(files)} recordings show a corrugated rail",
            "Corrugation is a periodic wear pattern on the rail head. As wheels roll over it, "
            "every axle box on that side of the train vibrates at the same wavelength, while the "
            "other side stays quiet - which is why the two rails are scored separately.",
            f"Schedule rail grinding on the flagged side and locate the section from the train's "
            f"position log. Flagged: {ids}{more}.", ev, "Corrugation"))
    else:
        html(ui.verdict("ok", "Rail corrugation", f"All {len(files)} recordings read as normal track",
                        "Neither rail shows the periodic axle-box vibration that corrugation produces.",
                        "No action needed. Continue routine monitoring.", ev))
    st.caption("Side I is the rare class (14 of 272 training files) and the model recalls about "
               "two-thirds of it in validation, so a clean Side I result carries less certainty "
               "than a clean Side II result.")

    left, right = st.columns([1, 1.2], gap="medium")
    with left:
        html(ui.section("Verdicts"))
        plot(charts.rail_summary(files))
    with right:
        html(ui.section("Inspect a recording"))
        ids = list(files["file_id"])
        default = flagged["file_id"].iloc[0] if len(flagged) else ids[0]
        pick = st.selectbox("Recording", ids, index=ids.index(default),
                            format_func=lambda i: f"{i} · {files.set_index('file_id').loc[i, 'prediction']}")
        f = next(x for x in res["files"] if x["file_id"] == pick)
        state = "ok" if f["prediction"] == "Normal" else "alert"
        pr = f["proba"]
        html(ui.chip(state, f["prediction"],
                     f"P(Normal) {pr['Normal']:.0%} · P(Side I) {pr['Side I']:.0%} · "
                     f"P(Side II) {pr['Side II']:.0%} · {f['speed']['speed_km_h']:.0f} km/h"))
        st.caption(f"Speed from {f['speed']['transitions']} pulse edges in one second: "
                   f"90-tooth wheel, 0.85 m diameter → {f['speed']['speed_m_s']:.2f} m/s.")

    html(ui.section("Vibration energy by axle box"))
    plot(charts.rail_axle_grid(f["grid"]))
    st.caption("Vibration RMS per bearing, normalised to the loudest box in this recording. A "
               "corrugated rail lights up one whole band, not one car.")
    html(ui.section("Spectrum per rail, in the wavelength domain"))
    plot(charts.rail_spectrum(f["spectrum"]))
    st.caption("λ = v / f converts each frequency to a distance along the rail using the measured "
               "speed, so the same corrugation pitch lands in the same place at any speed. The "
               "classifier itself uses per-side statistics and frequency bands; this view is the "
               "physical reading of the same signal.")

    html(ui.section("Predictions"))
    st.dataframe(files, hide_index=True, width="stretch",
                 column_config={
                     "speed_km_h": st.column_config.NumberColumn("Speed km/h", format="%.0f"),
                     "side_i_rms": st.column_config.NumberColumn("Side I RMS", format="%.3f"),
                     "side_ii_rms": st.column_config.NumberColumn("Side II RMS", format="%.3f"),
                     "p_Normal": st.column_config.ProgressColumn("P(Normal)", min_value=0.0, max_value=1.0, format="%.2f"),
                     "p_Side I": st.column_config.ProgressColumn("P(Side I)", min_value=0.0, max_value=1.0, format="%.2f"),
                     "p_Side II": st.column_config.ProgressColumn("P(Side II)", min_value=0.0, max_value=1.0, format="%.2f"),
                 })
    download(spec, res["predictions"])


def acv_page() -> None:
    spec, card = SUBSYSTEMS["acv"], SUBSYSTEMS["acv"].model_card()
    html(ui.header("Air conditioning · refrigerant leak", "Which car is leaking?",
                   "Each case is one train's air-conditioning telemetry: cabin temperature, "
                   "cooling setpoint and running mode for all eight cars, every 30 seconds. A car "
                   "that has lost refrigerant cannot pull its cabin down to the setpoint, so it "
                   "runs warmer than its neighbours under the same conditions.", T("subsystem-acv")))
    res = run_panel(spec, "Rank the cars")
    if not res:
        return
    v = card["validation"]
    ev = (f"rank decay {v['mean_score']:.3f} ± {v['std_score']:.3f} · {v['split'].split(',')[0]} · "
          f"random ranking {v['random_ranking_baseline']} · model {card['model_version']}")
    ids = [f["file_id"] for f in res["files"]]
    pick = ids[0] if len(ids) == 1 else st.selectbox("Case", ids)
    f = next(x for x in res["files"] if x["file_id"] == pick)
    top, second = f["ranking"][0], f["ranking"][1]
    s_top, s_2 = f["scores"][top], f["scores"][second]
    gap = (s_top - s_2) if (s_top is not None and s_2 is not None) else None
    cars = [(c, f["scores"][c]) for c in f["ranking"]]

    html(ui.kpis([
        ("Cases ranked", f"{len(ids)}", None),
        ("Most likely faulty", f"Car {top}", f"{s_top:+.2f} °C above the other cars" if s_top is not None else None),
        ("Margin to runner-up", f"{gap:.2f} °C" if gap is not None else "—", f"runner-up Car {second}"),
        ("Cooling readings used", f"{max(f['cooling_readings'].values()):,}", f"of {f['n_readings']:,} rows"),
    ]))
    st.write("")
    state = "alert" if (gap is not None and gap >= 0.03) else "watch"
    html(ui.verdict(
        state, "Air conditioning",
        f"Car {top} is the most likely refrigerant leak in {pick}",
        f"During cooling, Car {top}'s cabin ran {s_top:+.2f} °C against the median of the other "
        f"seven cars on the same train at the same moment. Comparing cars to each other cancels "
        f"the weather, the passenger load and the route, which all eight cars share."
        + (" The margin over the runner-up is narrow, so treat the top two as candidates."
           if state == "watch" else ""),
        f"Check refrigerant pressure and the condenser on Car {top} first"
        + (f", then Car {second}." if state == "watch" else "."),
        ev, "Leak suspected"))
    if f["unobserved"]:
        st.warning(f"No usable cooling evidence for car(s) {', '.join(f['unobserved'])}: placed "
                   "last by identifier order, which does not mean they are healthy.")

    left, right = st.columns([1, 1.4], gap="medium")
    with left:
        html(ui.section("All eight cars, ranked"))
        html(ui.car_rank(cars, "Every car is listed: the scoring gives partial credit for a close "
                               "miss and none for an omitted car. A random ordering scores 0.5625."))
    with right:
        html(ui.section("Temperature excess over the other cars"))
        plot(charts.acv_excess(f["excess_timeline"], f["ranking"]))
        st.caption("Cooling periods only. The ranked-first car is drawn in red.")

    html(ui.section("Predictions"))
    st.dataframe(res["predictions"], hide_index=True, width="stretch")
    download(spec, res["predictions"])


# ------------------------------------------------------------------ fleet

def fleet_status() -> list[tuple[str, str, str, str]]:
    """(state, name, headline, detail) per subsystem from whatever has been run."""
    out = []
    door = st.session_state.get("door_result")
    if door and not door["cycles"].empty:
        c = door["cycles"]
        n_ab = int((c.prediction == "Abnormal resistance").sum())
        out.append(("alert" if n_ab else "ok", "Door",
                    f"{n_ab} of {len(c)} cycles abnormal" if n_ab else f"all {len(c)} cycles normal",
                    "abnormal sustained motor current" if n_ab else "motor load in the normal band"))
    else:
        out.append(("unknown", "Door", "not assessed", "run the Door page"))
    shm = st.session_state.get("shm_result")
    if shm:
        d = pd.DataFrame([{"file_id": x["file_id"], "damage": x["damage"]} for x in shm["files"]])
        worst = d.loc[d.damage.idxmax()]
        state = "alert" if worst.damage >= SHM_ALERT else "watch" if worst.damage >= SHM_WATCH else "ok"
        out.append((state, "Structural health", f"highest damage {worst.damage:.2f} ({worst.file_id})",
                    f"{len(d)} measurement point(s), D = 1 is end of fatigue life"))
    else:
        out.append(("unknown", "Structural health", "not assessed", "run the Structural health page"))
    rail = st.session_state.get("rail_result")
    if rail:
        p = rail["predictions"]
        n1, n2 = int((p.prediction == "Side I").sum()), int((p.prediction == "Side II").sum())
        out.append(("alert" if n1 + n2 else "ok", "Rail corrugation",
                    f"Side I {n1} · Side II {n2} of {len(p)} recordings" if n1 + n2 else f"{len(p)} recordings normal",
                    "rail grinding candidate" if n1 + n2 else "no periodic wear signature"))
    else:
        out.append(("unknown", "Rail corrugation", "not assessed", "run the Rail page"))
    acv = st.session_state.get("acv_result")
    if acv:
        f = acv["files"][0]
        out.append(("watch", "Air conditioning", f"Car {f['ranking'][0]} most likely leaking",
                    f"{f['file_id']} · runner-up Car {f['ranking'][1]}"))
    else:
        out.append(("unknown", "Air conditioning", "not assessed", "run the Air conditioning page"))
    return out


LINE_NAMES = {"NSL": "North–South (NSL)", "EWL": "East–West (EWL)", "NEL": "North East (NEL)",
              "CCL": "Circle (CCL)", "DTL": "Downtown (DTL)", "TEL": "Thomson–East Coast (TEL)"}


def fleet_page() -> None:
    html(ui.header("Fleet view", "Where the train is, what the models say",
                   "The four verdicts from this session, placed on Singapore's rail network next "
                   "to the live service status. Set the line and train the uploaded data came "
                   "from; the map highlights that line in the colour of the worst verdict."))
    board = fleet_status()
    rank = {"alert": 3, "watch": 2, "ok": 1, "unknown": 0}
    worst = max(board, key=lambda r: rank[r[0]])[0]

    c1, c2, c3 = st.columns([1, 1, 1.4], gap="medium")
    with c1:
        line = st.selectbox("Line", list(livemap.LINES), index=0, key="fleet_line",
                            format_func=lambda k: LINE_NAMES[k])
    with c2:
        train = st.text_input("Train / set number", value="", placeholder="e.g. 3019", key="fleet_train")
    with c3:
        key = st.text_input("LTA DataMall AccountKey (optional, session only)", type="password",
                            key="fleet_lta_key", help="Enables the official TrainServiceAlerts feed. "
                            "Kept in this browser session only; never stored.")

    left, right = st.columns([1.55, 1], gap="medium")
    with left:
        html(ui.section("Network"))
        df = livemap.stations()
        if df.empty:
            html(ui.empty("Station map unavailable",
                          ["The PS2 station GeoJSON was not found in repo/PS2/data/. Re-clone the "
                           "dataset (HANDOFF.md section 3) to restore it."]))
        else:
            st.pydeck_chart(livemap.deck(df, line, worst, f"train {train}" if train else "train"),
                            height=520)
            st.caption(f"{len(df)} station polygons from the PS2 Master Plan 2014 amendment file, "
                       f"drawn at their centroids. Halo colour = worst verdict this session "
                       f"({ui.STATES[worst][1]}).")
    with right:
        html(ui.section(f"This train · {line}{' · ' + train if train else ''}"))
        for state, name, headline, detail in board:
            html(ui.fleet_row(state, name, headline, detail))

    html(ui.section("Live service status"))
    a, b = st.columns(2, gap="medium")
    with a:
        st.markdown("**LTA DataMall · TrainServiceAlerts**")
        if not key:
            st.caption("Enter an AccountKey above to read the official feed. Register free at "
                       "datamall.lta.gov.sg. Without it, the SGMRT feed on the right still works.")
        else:
            al = livemap.fetch_train_alerts(key)
            if not al["ok"]:
                html(ui.chip("unknown", "Feed unavailable", al["reason"]))
            elif al["status"] == 1 and not al["segments"]:
                html(ui.chip("ok", "All lines running normally", "DataMall status 1"))
            else:
                html(ui.chip("alert", "Disruption reported", f"{len(al['segments'])} affected segment(s)"))
                for seg in al["segments"]:
                    mine = str(seg.get("Line", "")).upper() == line
                    st.markdown(("🔴 **Affects your line** · " if mine else "") +
                                f"**{seg.get('Line', '?')}** {seg.get('Direction', '')} · stations "
                                f"{seg.get('Stations', '?')} · free bus: {seg.get('FreePublicBus', '-')}"
                                f" · shuttle: {seg.get('FreeMRTShuttle', '-')}")
                for m in al["messages"]:
                    st.caption(m)
            if st.button("Refresh DataMall", key="fleet_refresh_lta"):
                livemap.fetch_train_alerts.clear()
                st.rerun()
    with b:
        st.markdown("**SGMRT community channel · t.me/s/sgmrt**")
        feed = livemap.fetch_sgmrt()
        if not feed["ok"]:
            html(ui.chip("unknown", "Feed unavailable", feed["reason"]))
        elif not feed["posts"]:
            st.caption("No posts parsed.")
        else:
            hits = [p for p in feed["posts"] if livemap.line_mentioned(p["text"], line)]
            html(ui.chip("watch" if hits else "ok",
                         f"{len(hits)} recent post(s) mention {line}" if hits else f"no recent post mentions {line}",
                         "community reports, unverified"))
            for p in feed["posts"]:
                when = "" if pd.isna(p["time"]) else p["time"].tz_convert("Asia/Singapore").strftime("%d %b %H:%M")
                mark = "🔴 " if livemap.line_mentioned(p["text"], line) else ""
                st.markdown(f"{mark}`{when}` {p['text'][:280]}{'…' if len(p['text']) > 280 else ''}")
        if st.button("Refresh feed", key="fleet_refresh_tg"):
            livemap.fetch_sgmrt.clear()
            st.rerun()
    st.caption("Live feeds are context for the maintenance decision, not inputs to any model: "
               "every verdict above comes only from the uploaded sensor data.")


def submission_page() -> None:
    html(ui.header("Competition deliverable", "Build predictions.zip",
                   "Runs every validated model over the competition test inputs, checks each "
                   "output against the official schema, and packages the CSVs at the top "
                   "level of a single zip - the file judges score."))
    chosen = []
    for spec in SUBSYSTEMS.values():
        n = len(spec.test_inputs())
        c1, c2 = st.columns([3, 2])
        with c1:
            if spec.available:
                if st.checkbox(f"**{spec.name}** — {n} test file{'s' if n != 1 else ''} → "
                               f"`{SCHEMAS[spec.key].filename}`", value=True, key=f"sub_{spec.key}"):
                    chosen.append(spec)
            else:
                st.checkbox(f"**{spec.name}** — model pending", value=False, disabled=True,
                            key=f"sub_{spec.key}")
        with c2:
            html(ui.chip("ok", "Ready") if spec.available and n else
                 ui.chip("unknown", "Pending" if not spec.available else "No test input"))

    if not st.button("Run models and build predictions.zip", type="primary",
                     disabled=not chosen):
        st.caption("The specification allows zipping only the subsystems you attempted. "
                   "Pending subsystems are left out rather than filled with a guess.")
        return

    frames, report = {}, []
    bar = st.progress(0.0, text="Starting...")
    for i, spec in enumerate(chosen):
        inputs = spec.test_inputs()
        bar.progress(i / len(chosen), text=f"{spec.name}: running {len(inputs)} file(s)...")
        files = as_files([(p.name, p.read_bytes()) for p in inputs])
        df = spec.module.predict(files)
        expected = None if spec.key == "door" else [p.name for p in inputs]
        errs = validate_submission(spec.key, df, expected_ids=expected)
        report.append((spec, df, errs))
        if not errs:
            frames[spec.key] = df
    bar.progress(1.0, text="Validating and packaging...")

    for spec, df, errs in report:
        state = "ok" if not errs else "alert"
        html(ui.chip(state, "Schema valid" if not errs else "Failed validation",
                     f"{spec.name} · {len(df)} rows"))
        for e in errs:
            st.error(e)
        with st.expander(f"Preview {SCHEMAS[spec.key].filename}"):
            st.dataframe(df.head(12), hide_index=True, width="stretch")

    if not frames:
        st.error("Nothing passed validation; no zip was written.")
        return
    blob = build_predictions_zip(frames)
    out_dir = PROJECT_ROOT / "predictions"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "predictions.zip").write_bytes(blob)
    for key, df in frames.items():
        df.to_csv(out_dir / SCHEMAS[key].filename, index=False)
    bar.empty()
    st.success(f"predictions.zip built with {len(frames)} validated file(s) and saved to "
               f"predictions/predictions.zip")
    st.download_button("Download predictions.zip", blob, "predictions.zip",
                       "application/zip", type="primary")


def method_page() -> None:
    html(ui.header("How it works", "Method and architecture",
                   "Deterministic, physically grounded models; validation designed to "
                   "prevent leakage; one interface for every subsystem."))
    html(ui.section("Architecture"))
    st.graphviz_chart("""
digraph G {
  rankdir=LR; bgcolor="transparent";
  node [shape=box, style="rounded,filled", fontname="IBM Plex Sans", fontsize=11,
        color="#e2e7ee", fillcolor="#ffffff", fontcolor="#10151c", margin="0.18,0.1"];
  edge [color="#848f9e", arrowsize=0.6];
  ui [label="Streamlit console\\napp/", fillcolor="#eef1f5"];
  reg [label="Subsystem registry\\ncore/registry.py"];
  sub [label="Submission validator\\n+ zip builder\\ncore/submission.py"];
  door [label="subsystems/door\\npredict() · analyze()"];
  shm [label="subsystems/shm\\npredict() · analyze()"];
  rail [label="subsystems/rail\\npredict() · analyze()"];
  acv [label="subsystems/acv\\npredict() · analyze()"];
  live [label="app/livemap.py\\nPS2 stations + LTA/SGMRT feeds", fillcolor="#eef1f5"];
  art [label="artifacts/\\nmodel + config.json", fillcolor="#eef1f5"];
  tok [label="design-system/\\ntokens.json", fillcolor="#eef1f5"];
  score [label="scoring/metrics.py\\nofficial formulas, 28 tests", fillcolor="#eef1f5"];
  zip [label="predictions.zip", shape=note];
  tok -> ui; ui -> reg; reg -> door; reg -> shm; reg -> rail; reg -> acv;
  door -> art; shm -> art; rail -> art; acv -> art; live -> ui; ui -> sub; sub -> zip; score -> door [style=dashed, label=" validates", fontsize=9, fontcolor="#626c7a"];
  score -> shm [style=dashed];
}""", width="stretch")

    html(ui.section("Validation"))
    rows = []
    for spec in SUBSYSTEMS.values():
        card = spec.model_card()
        if card:
            v = card["validation"]
            mean = v.get("mean_iou_weighted_f1", v.get("mean_score"))
            std = v.get("std_iou_weighted_f1", v.get("std_score"))
            rows.append({"Subsystem": spec.name, "Model": card["model_version"],
                         "Metric": v["metric"], "Split": v["split"],
                         "Score": f"{mean:.4f} ± {std:.4f}"})
        else:
            rows.append({"Subsystem": spec.name, "Model": "—", "Metric": "—",
                         "Split": "—", "Score": "pending"})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    html(ui.section("Principles"))
    st.markdown("""
- **Models encode the physics.** SHM fits the two constants of the S-N curve that generated
  its labels - and recovers m ≈ 5, the standard exponent for welded steel. Door's strongest
  features are sustained motor current and current per unit back-EMF: the mechanical
  resistance signal itself.
- **Validation cannot leak.** Door is split into contiguous time blocks, never random rows.
  SHM's constants are fitted inside each fold only. Every score is on data the model did not
  see, with its spread shown.
- **Best model per subsystem, from two builds.** Door and SHM come from this workspace (physics
  first: Miner's rule recovers m ≈ 5). Rail and ACV are ported unchanged from the teammate's
  final_streamlit_app build, whose leakage-safe folds beat every alternative tried. On the Door
  test stream the two builds agree on all 38 boundaries and 37 of 38 labels.
- **Live context stays outside the models.** The Fleet page reads LTA DataMall and the SGMRT
  channel for situational awareness; no live feed touches a prediction.
- **One interface.** Every subsystem exposes `predict(uploaded_files)`; the app never
  contains modelling code, so a better model drops in without touching the interface.
- **Every download is schema-checked** against the official format before it can leave.
""")


pages = [
    st.Page(overview_page, title="Overview", icon=":material/dashboard:", default=True),
    st.Page(fleet_page, title="Fleet view", icon=":material/map:", url_path="fleet"),
    st.Page(door_page, title="Door", icon=":material/door_sliding:", url_path="door"),
    st.Page(shm_page, title="Structural health", icon=":material/architecture:", url_path="shm"),
    st.Page(rail_page, title="Rail", icon=":material/train:", url_path="rail"),
    st.Page(acv_page, title="Air conditioning", icon=":material/ac_unit:", url_path="acv"),
    st.Page(submission_page, title="Submission", icon=":material/inventory_2:", url_path="submission"),
    st.Page(method_page, title="Method", icon=":material/schema:", url_path="method"),
]
st.navigation(pages, position="top").run()
