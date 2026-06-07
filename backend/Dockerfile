# ── Build stage ──────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build tools needed for some native extensions (caldav, cryptography).
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.11-slim

# Create a non-root user for the application.
RUN addgroup --system familycal && adduser --system --ingroup familycal familycal

WORKDIR /app

# Copy installed packages from builder.
COPY --from=builder /install /usr/local

# Copy application source.
COPY app/       ./app/
COPY plugins/   ./plugins/

# Ensure the data directory exists and is writable by the non-root user.
RUN mkdir -p /data/photos && chown -R familycal:familycal /data

USER familycal

ENV DATA_DIR=/data \
    HOST=0.0.0.0 \
    PORT=8000

EXPOSE 8000

# Healthcheck: hits the /api/system/health endpoint.
# start_period gives the app time to initialise the DB before checks begin.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/system/health')"

# Run the backend.  sys.path must include plugins/ for plugin imports.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
