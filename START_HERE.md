# Start here: from nothing to a working console

Three ways in, from easiest to most complete. Pick one.

---

## A. Just use the app in a browser (no install)

The app is deployed on Streamlit Community Cloud from this repository's `master`
branch. Open the app link the team shared (it ends in `.streamlit.app`).

If a page shows a red error box after a new version was pushed: click **Manage app**
(bottom right) → **Reboot app**, then reload.

What you can do there:
1. **Dashboard**: drop any competition file (Door CSV, Rail CSV, SHM CSV, ACV XLSX)
   into the box at the top; the console works out which subsystem it is and
   analyses it. Read **What to do now**.
2. **Check a train** menu: one page per subsystem, with the verdict, the action, a
   diagram drawn from the data, and "How to read this" for anyone new to it.
3. **Work queue** on the Dashboard: Acknowledge, Shelve 4 h, or Close a fault with
   what was found. Closed outcomes are what the models learn from.
4. **Fleet view**: the network map, time range, train health, live weather. Paste
   an LTA DataMall AccountKey (free at datamall.lta.gov.sg) to switch on service
   alerts and platform crowding.
5. **Evidence** menu: Validation (how every score was measured), Submission
   (build `predictions.zip`), Method.

The cloud copy has no dataset on it, so the "Provided test data" option and the
Submission page's bundled inputs are absent there; uploads work for everything.

---

## B. Run it on your own Windows PC (about 10 minutes, one command)

Prerequisites, both free:
- Git: https://git-scm.com/download/win
- Python 3.12 or newer: https://www.python.org/downloads/ (tick "Add Python to PATH")

Open **PowerShell** and paste these three lines one at a time:

```powershell
git clone https://github.com/mantaikosauce/train-monitoring-app.git
cd train-monitoring-app
powershell -ExecutionPolicy Bypass -File TAKEOVER\setup.ps1
```

The script creates a private Python environment, installs the dependencies, clones
the hackathon dataset (7.6 GB; add `-SkipDataset` to the last line to skip it and
work from uploads only), runs the tests, and builds `predictions.zip` and the
dashboard cache.

Then start the app:

```powershell
.venv\Scripts\python -m streamlit run app\streamlit_app.py
```

and open http://localhost:8501 in any browser. Stop it with Ctrl+C.

---

## C. Continue the engineering work (human or AI)

Read, in this order: `TAKEOVER/README.md`, `HANDOFF.md`, `PROJECT-STATE.md`,
`DESIGN.md`, `WRITEUP.md`.

To hand the project to an AI assistant, open a terminal in the project folder,
start the assistant (for Claude Code: type `claude`), and paste the contents of
`TAKEOVER/PROMPT_FOR_AI.md` as the first message.

On the original laptop the exact session can be resumed by double-clicking
`TAKEOVER/resume-here.cmd`.

Everyday commands (run from the project folder):

| Task | Command |
|---|---|
| Prove everything works | `.venv\Scripts\python -m pytest tests -q` |
| Rebuild `predictions.zip` + dashboard cache | `.venv\Scripts\python -m scripts.build_predictions` |
| Build the team submission folder | `.venv\Scripts\python -m scripts.package_submission --team "<team name>"` |
| Regenerate the write-up | `.venv\Scripts\python -m scripts.write_up` |
| Retrain from operator outcomes (gated) | `.venv\Scripts\python -m scripts.retrain --dry-run` |
| Deploy to Google Cloud Run | install gcloud, `gcloud auth login`, then `deploy\deploy_cloud_run.ps1` |

Push to GitHub after each verified step; the cloud app redeploys from `master`.

---

## Still to do for the hackathon submission

1. Record the demo video (≤ 3 minutes): pick a subsystem → upload → verdict →
   download → build `predictions.zip`.
2. Deploy on Google Cloud Run under the team's Google account (the organisers
   require the submission to be reachable on Google Cloud).
3. Put `demo_video`, `predictions.zip`, `app/` and `Optional_Items/` in a folder
   named exactly as the registered team (`scripts/package_submission.py` does this).
