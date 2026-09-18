# One-shot deploy to Google Cloud Run. Run from the project root after:
#   1. Install the Google Cloud CLI: https://cloud.google.com/sdk/docs/install
#   2. gcloud auth login
#   3. gcloud config set project YOUR_PROJECT_ID   (the project holding the NebulaX credits)
#
#   powershell -ExecutionPolicy Bypass -File deploy\deploy_cloud_run.ps1
param(
  [string]$Service = "nebula-wayside",
  [string]$Region = "asia-southeast1",
  [string]$Memory = "2Gi",
  [string]$Cpu = "2"
)
$ErrorActionPreference = "Stop"
if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) { throw "gcloud is not installed. See deploy/CLOUD_RUN.md step 1." }
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
gcloud run deploy $Service --source . --region $Region --allow-unauthenticated --memory $Memory --cpu $Cpu --timeout 900 --port 8080
$url = gcloud run services describe $Service --region $Region --format "value(status.url)"
Write-Host "Deployed: $url"
Write-Host "Health check:"; (Invoke-WebRequest "$url/_stcore/health").Content
