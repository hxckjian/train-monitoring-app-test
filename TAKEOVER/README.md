# Take over this project on another PC (human or AI)

Everything lives in the GitHub repository. Nothing on the old laptop is needed
except the 7.6 GB dataset, which is re-cloned by the script below.

## 1. Get the code and set up (one command)

Open PowerShell anywhere and run:

```powershell
git clone https://github.com/mantaikosauce/train-monitoring-app.git
cd train-monitoring-app
powershell -ExecutionPolicy Bypass -File TAKEOVER\setup.ps1
```

`setup.ps1` creates `.venv`, installs `requirements.txt`, clones the hackathon
dataset into `repo/` (needed only for the competition test data; every page also
works from uploads), runs the tests, builds `predictions.zip` and the dashboard
cache, and prints how to start the app.

## 2. Run the app

```powershell
.venv\Scripts\python -m streamlit run app\streamlit_app.py
```

Open http://localhost:8501. Stop with Ctrl+C.

## 3. Hand the work to an AI assistant

Open a terminal in the project folder and paste `TAKEOVER\PROMPT_FOR_AI.md`
into the assistant as its first message. It tells the assistant what exists,
what the rules are, what is unfinished, and which commands prove the project is
healthy.

If the assistant is Claude Code: `claude` in the project folder, then paste the
prompt. Sessions are keyed to the folder; `scripts\resume-claude.ps1` resumes an
existing session id from anywhere.

## 4. What is where

| Item | Path |
|---|---|
| Status, decisions, next steps | `HANDOFF.md` (read first), then `PROJECT-STATE.md` |
| Design method and sources | `DESIGN.md` |
| Generated write-up for the submission | `WRITEUP.md` (`python -m scripts.write_up`) |
| The app | `app/` (`streamlit_app.py` pages; `theme.py`, `charts.py`, `insight.py`, `livemap.py`, `schematics.py`) |
| Models and model cards | `subsystems/<door|shm|rail|acv>/artifacts/` |
| Official metrics + tests | `scoring/metrics.py`, `tests/` (`python -m pytest tests -q`) |
| Build the submission zip | `python -m scripts.build_predictions` |
| Build the team folder | `python -m scripts.package_submission --team "<name>"` |
| Model search (pre-registered) | `python -m scripts.model_search` |
| Learning loop: retrain from operator outcomes (gated) | `python -m scripts.retrain [--dry-run]`; outcomes come from closing faults in the work queue; drift stats via `python -m scripts.feature_stats` |
| Cloud Run deploy | `deploy/CLOUD_RUN.md`, `deploy/deploy_cloud_run.ps1` |
| Streamlit Cloud | deploys from `master` automatically; Manage app → Reboot if a page errors after a deploy |

## 5. Unfinished, in priority order

1. Record the ≤ 3-minute demo video (spec §4.1 item 1). Path in `app/README.md`.
2. Deploy to Google Cloud Run under the team's account (mandatory per the organisers):
   install gcloud, `gcloud auth login`, then `deploy\deploy_cloud_run.ps1`.
3. Paste an LTA DataMall AccountKey into the Fleet page to switch on service alerts
   and platform crowding (register at datamall.lta.gov.sg).
4. Optional: Rail Side I recall is the weakest number (~0.64); any change must go
   through `scripts/model_search.py` and beat the nested estimate honestly.

## 6. Ground rules the project runs on

- Every number on screen comes from a file a script wrote; none is typed.
- Splits cannot leak (time blocks, by file, by case; constants fitted in-fold).
- Model changes are pre-registered: decision rule first, then the run, null kept as null.
- `python -m pytest tests -q` must pass before any push. The page tests render every
  page headlessly in empty, populated and full-results states.
