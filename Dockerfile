FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY nosite_scout.py .
COPY accommodation_search.py .
COPY prospect_scoring.py .

WORKDIR /data
ENTRYPOINT ["python", "/app/nosite_scout.py"]
