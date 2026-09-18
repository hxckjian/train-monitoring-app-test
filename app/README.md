# Nebula Wayside — the app

The compulsory deliverable (spec §4.1 item 3): one app, every subsystem, usable by
a non-technical person, and the tool that generates `predictions.zip`.

## Run it

From the project root, in the project venv (`python -m venv .venv` then
`.venv/Scripts/python -m pip install -r requirements.txt`):

```bash
.venv/Scripts/python -m streamlit run app/streamlit_app.py
```

Or from the command line, the same pipeline without the UI:

```bash
.venv/Scripts/python -m scripts.build_predictions
```

Then open http://localhost:8501.

## Architecture

```
design-system/project/tokens.json ──► app/theme.py ──► page CSS + chart palette
                                                        │
app/streamlit_app.py  (pages, no modelling code) ◄──────┘
        │
        ├──► core/registry.py      which subsystems exist, which are live
        │         └──► subsystems/<key>/predict.py   predict() · analyze()
        │                   └──► artifacts/ model + config.json
        │
        └──► core/submission.py    official schemas, validation, zip builder
                  └──► predictions/predictions.zip
```

- **The app contains no modelling code.** It calls `analyze()` for display and
  `predict()` for submission — both go through the same inference path inside
  each package, so the screen and the CSV cannot disagree.
- **Adding a subsystem** is one `SubsystemSpec` entry in `core/registry.py` plus a
  package exposing `predict()` and `analyze()`. No page code changes for the
  overview, submission or method pages.
- **Colour and type come from the design system's `tokens.json`**, resolved at
  startup. Change a token there and the app follows.
- **Nothing downloads unless it passes `core/submission.py`**, which enforces the
  official column names, order, label spelling, timestamp format, ID set and
  extension rules. A malformed file is refused with the reason shown.

## Pages

| Page | What it does |
|---|---|
| Dashboard | dark, map-first: KPI cards, status-overview bar, trend, the network map with line paths, zones, live NEA weather (rain gauges, temperatures), events table with status pills and a Fault/Watch filter; tabs for subsystems, trends, zones and the training data. Opens on the cached run of the competition test data |
| Door | segment a stream, verdict card, cycle timeline, sustained-current scatter, per-cycle inspector, download |
| Structural health | damage per file against D = 1, per-file cycle and damage-share profiles, stress envelope, download |
| Fleet view | the four session verdicts on a live map of the rail network (PS2 station GeoJSON), with the LTA DataMall TrainServiceAlerts feed (user's own AccountKey, session only) and the public SGMRT channel |
| Rail | classify 1-second recordings, per-side axle-box energy grid, wavelength-domain spectrum from the measured speed, class probabilities, download |
| Air conditioning | rank all eight cars by cabin-temperature excess over the other cars during cooling, CarRank bars, excess timeline, download |
| Parameter monitor | label-free screen for a new dataset: peer comparison across units (the ACV method) or robust drift for one series; recipe for promoting it to a subsystem |
| Validation | per-fold scores with mean, sd, naive baseline and in-sample line for every subsystem; the Rail pre-registered experiment table |
| Submission | runs every live model over the test inputs, validates, builds and saves `predictions.zip` (all four subsystems) |
| Method | architecture diagram, validation table, principles |

## Demo video path (≤ 3 minutes)

1. Overview — the four tiles and what "cross-validated" means (15 s)
2. Door — Analyse → verdict → inspect a flagged cycle → download (60 s)
3. Structural health — Assess → worst file → "0.1% of cycles cause 99% of damage" (45 s)
4. Submission — build `predictions.zip` through the app (30 s)
5. Method — one sentence on leakage-safe validation (15 s)

## Notes

- `.streamlit/config.toml` holds the theme and a 400 MB upload limit. If the
  launcher runs from another directory, pass the same values as `--theme.*` flags.
- SHM on all 16 test files takes ~20 s (rainflow counting) and Rail on all 68
  takes ~3 min (17 MB each); both pages show a per-file progress bar.
- Rail and ACV models are ported unchanged from the teammate's
  `PS3/final_streamlit_app` build; `subsystems/<key>/artifacts/config.json` is
  the model card, `validation_source.json` the original report.
- The station map is bundled at `data/stations/`. Live feeds: NEA weather from
  data.gov.sg needs no key; LTA DataMall TrainServiceAlerts needs the user's own
  AccountKey (register at datamall.lta.gov.sg), typed into the Fleet page per
  session; the public SGMRT channel needs no key. All are time-limited and the
  pages render without them.
- `predictions/analysis_cache.pkl` (gitignored) is written by
  `scripts/build_predictions.py` and gives every page results on open. Delete it
  or press Run all to refresh.
