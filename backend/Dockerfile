# automation_machine_learning — backend image (FastAPI + scikit-learn/XGBoost/SHAP).
#
# Build context is the REPO ROOT (not backend/) because the app resolves its demo
# datasets relative to the package: DATA_DIR = backend/app.py -> parent.parent/data.
# So the image needs both /app/backend (code) and /app/data (datasets) side by side.
#
#   docker build -f backend/Dockerfile -t automation-machine-learning-backend .
#
# Single stage: the runtime IS the test image (tests/ ship so `mlauto test` runs
# the same code in-container). Non-root, OpenMP runtime for XGBoost, deps cached.

FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MPLBACKEND=Agg \
    ML_SESSION_DB=/data/sessions.db

WORKDIR /app

# libgomp1: OpenMP runtime required by the XGBoost wheel at import time.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Dedicated non-root runtime user (least privilege; binds 8000 which is > 1024).
RUN useradd --create-home --shell /usr/sbin/nologin mlauto

# Dependency manifest first for better layer caching (deps change rarely).
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install -r backend/requirements.txt

# Application code + demo datasets (the root .dockerignore strips secrets,
# the venv, caches and the internal notebooks/PDFs under data/).
COPY backend/ ./backend/
COPY data/ ./data/

# /data is the SQLite persistence mount-point. Pre-creating it owned by the
# runtime user means a fresh named volume inherits that ownership on first mount,
# so the non-root process can write sessions.db there (session persistence).
RUN mkdir -p /data && chown -R mlauto:mlauto /app /data

USER mlauto
WORKDIR /app/backend

EXPOSE 8000

# Deterministic, dependency-free liveness probe (no curl needed in the image).
HEALTHCHECK --interval=10s --timeout=3s --retries=12 --start-period=20s \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"]

CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
