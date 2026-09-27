# NagarNetra API. CPU-only, no GPU, no model download at runtime.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONIOENCODING=utf-8

WORKDIR /app

# libgomp is needed by scikit-learn; libgeos by shapely.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 libgeos-c1v5 curl \
 && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/requirements-dev.txt /app/backend/
RUN pip install --no-cache-dir -r /app/backend/requirements-dev.txt cryptography

COPY backend /app/backend
COPY scripts /app/scripts
COPY data /app/data

# Build the artefacts the app needs so the container starts ready to serve.
RUN python scripts/build_wards.py \
 && (test -f data/synthetic_complaints.csv || python scripts/generate_synthetic.py) \
 && python scripts/train_fallback.py > /dev/null \
 && python scripts/seed_db.py --reset

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
  CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--app-dir", "backend", \
     "--host", "0.0.0.0", "--port", "8000"]
