You are taking over the NebulaX 2026 hackathon Problem Statement 3 project (train
condition monitoring) in this folder. Work carefully, verify before you claim, and
never type a number that a script did not produce.

Read, in this order, before doing anything else:
1. TAKEOVER/README.md      what exists, what is unfinished, the commands
2. HANDOFF.md              status per subsystem, decisions, compliance table
3. PROJECT-STATE.md        the verified facts about the data and scoring
4. DESIGN.md               the interface method and its sources
5. WRITEUP.md              the generated submission write-up

Then prove the project is healthy on this machine:
    .venv\Scripts\python -m pytest tests -q          (expect all passed)
    .venv\Scripts\python -m streamlit run app\streamlit_app.py   (open http://localhost:8501)

Rules you must keep:
- Leakage-safe validation only: Door by contiguous time blocks, SHM by file with
  constants fitted in-fold, Rail by grouped files, ACV leave-one-case-out.
- Any model change goes through scripts/model_search.py with a decision rule written
  before the run; a null result is reported as a null result.
- Every figure shown to the user comes from subsystems/*/artifacts/*.json or a
  benchmark file; regenerate WRITEUP.md with `python -m scripts.write_up`.
- Run the tests before every push; the page tests render every page headlessly.
- Push to GitHub (origin master) after each verified step; Streamlit Cloud deploys
  from master. If a cloud page errors after a deploy, Manage app → Reboot once.
- The app must stay usable by a non-technical operator: actions first, evidence
  behind an Engineer view, plain-language "How to read this" on every subsystem.

Unfinished, in priority order:
1. Demo video ≤ 3 minutes showing select subsystem → upload → verdict → download → predictions.zip.
2. Google Cloud Run deployment under the team's account (deploy/CLOUD_RUN.md). Ask the
   human to run `gcloud auth login`; do not create accounts or enter credentials.
3. LTA DataMall AccountKey: ask the human to register and paste it into the Fleet page.
4. Optional model work: Rail Side I recall (~0.64) is the weakest number.

When you report, lead with what you verified and how, then what changed, then what
is still open. If something could not be verified, say so first.
