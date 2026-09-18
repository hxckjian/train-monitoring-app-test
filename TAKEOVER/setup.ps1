# One-shot setup on a fresh Windows PC. Run from the project root:
#   powershell -ExecutionPolicy Bypass -File TAKEOVER\setup.ps1
# Needs: Python 3.12+ on PATH, git on PATH, internet.
param([switch]$SkipDataset)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

Write-Host "== Python environment"
if (-not (Test-Path ".venv")) { python -m venv .venv }
.\.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
.\.venv\Scripts\python.exe -m pip install --quiet -r requirements.txt

if (-not $SkipDataset) {
  Write-Host "== Hackathon dataset (7.6 GB, only for the provided test data; skip with -SkipDataset)"
  if (-not (Test-Path "repo\PS3\02_Datasets")) {
    git clone --depth 1 https://github.com/aochinwen/NebulaX-Hackathon-ProblemStatement.git repo
  }
}

Write-Host "== Tests"
.\.venv\Scripts\python.exe -m pytest tests -q

if (Test-Path "repo\PS3\02_Datasets") {
  Write-Host "== predictions.zip and dashboard cache"
  .\.venv\Scripts\python.exe -m scripts.build_predictions
}

Write-Host ""
Write-Host "Ready. Start the app with:"
Write-Host "  .venv\Scripts\python -m streamlit run app\streamlit_app.py"
Write-Host "then open http://localhost:8501"
