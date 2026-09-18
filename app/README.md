# Nebula Wayside — the app

The compulsory deliverable (spec §4.1 item 3): one app, every subsystem, usable by
a non-technical person, and the tool that generates `predictions.zip`.

## Run it

From the project root, in the `nebula-ps3` environment:

```bash
streamlit run app/streamlit_app.py
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
| Overview | four subsystem tiles with live/pending status and the cross-validated score |
| Door | segment a stream, verdict card, cycle timeline, sustained-current scatter, per-cycle inspector, download |
| Structural health | damage per file against D = 1, per-file cycle and damage-share profiles, stress envelope, download |
| Rail / Air conditioning | honest pending state plus the verified data facts — no unvalidated prediction is shown |
| Submission | runs every live model over the test inputs, validates, builds and saves `predictions.zip` |
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
- SHM on all 16 test files takes ~20 s (rainflow counting); the page shows a
  per-file progress bar.
