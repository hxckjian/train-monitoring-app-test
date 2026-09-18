# Container image for the console. Works locally and on Google Cloud Run.
#
#   docker build -t nebula-wayside .
#   docker run -p 8080:8080 nebula-wayside
#
# Cloud Run (see deploy/CLOUD_RUN.md):
#   gcloud run deploy nebula-wayside --source . --region asia-southeast1 --allow-unauthenticated
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

# Cloud Run injects $PORT; Streamlit must bind 0.0.0.0 on it.
ENV PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "python -m streamlit run app/streamlit_app.py --server.port=${PORT} --server.address=0.0.0.0 --server.headless=true"]
