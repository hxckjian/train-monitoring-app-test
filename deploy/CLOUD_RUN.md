# Deploying the console

Two hosted options. Both run the same code; neither needs the 7.6 GB dataset,
because every page works from uploads and the station map is bundled.

## A. Streamlit Community Cloud (no container, free)

1. Push to GitHub (done: `mantaikosauce/train-monitoring-app`, branch `master`).
2. https://share.streamlit.io → Create app → repo, branch `master`, main file
   `app/streamlit_app.py`, Advanced settings → Python 3.12. No secrets.
3. Free tier has about 1 GB RAM: upload Rail files a few at a time.

## B. Google Cloud Run (container, scales to zero, more memory)

Follows the official "deploy from source" flow:
https://cloud.google.com/run/docs/deploying-source-code and the Streamlit
port/address rules in `Dockerfile`.

Prerequisites: a Google Cloud project with billing, and the `gcloud` CLI
(https://cloud.google.com/sdk/docs/install).

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
```

Deploy from this folder (Cloud Build builds the `Dockerfile`; `.dockerignore`
keeps the dataset and environments out of the image):

```bash
gcloud run deploy nebula-wayside --source . --region asia-southeast1 --allow-unauthenticated --memory 2Gi --cpu 2 --timeout 900
```

Notes that matter for this app:

- **Memory.** Rail uploads are 17 MB each and the analysis holds a few in
  memory; `--memory 2Gi` handles a batch of ten comfortably. Raise it rather
  than shrinking batches if judges will upload all 68.
- **Timeout.** Rail on 68 files takes about a minute; `--timeout 900` leaves
  headroom. Streamlit keeps a websocket open, which Cloud Run supports.
- **Upload limit.** `.streamlit/config.toml` allows 400 MB per upload and is
  inside the image, so it applies on Cloud Run too.
- **No secrets.** The LTA DataMall key is typed into the Fleet page per session.
  If you want it server-side, store it in Secret Manager and read it with
  `os.environ` in `app/livemap.py`; never commit it.
- **Region.** `asia-southeast1` is Singapore, the closest to the judges.
- **Cost.** Scales to zero when idle; a demo day costs cents.

Verify after deploy: open the printed URL, run the Air conditioning page on an
uploaded case, and download the CSV. Cloud Run logs are in the console under
Cloud Run → service → Logs if a page errors.

Local check of the same image before pushing to the cloud:

```bash
docker build -t nebula-wayside . && docker run -p 8080:8080 nebula-wayside
```

then open http://localhost:8080.
