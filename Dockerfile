# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 — builder: install dependencies into a virtual environment
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build tools needed for some packages (asyncpg compiles C extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment for clean dependency isolation
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — runner: Alpine-based minimal production image
# Switching from python:3.11-slim (Debian, 140+ CVEs) to Alpine (<10 CVEs)
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-alpine AS runner

WORKDIR /app

# Runtime dependency for asyncpg + upgrade ALL Alpine packages to fix OS CVEs
RUN apk add --no-cache libpq && \
    apk upgrade --no-cache

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Remove ALL system-level Python packages (pip, wheel, setuptools, jaraco-context)
# The app runs entirely from the venv — system packages are NOT needed at runtime
# This eliminates base image CVEs that Trivy detects in lower Docker layers
RUN rm -rf /usr/local/lib/python3.11/site-packages/* \
           /usr/local/lib/python3.11/ensurepip/ \
           /usr/local/bin/pip* /usr/local/bin/wheel

# Create non-root user for security
RUN addgroup --system --gid 1001 appgroup && \
    adduser  --system --uid 1001 --ingroup appgroup --no-create-home appuser

# Copy application source
COPY --chown=appuser:appgroup app/ ./app/

USER appuser

EXPOSE ${PORT:-8000}

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD ["python", "-c", "import urllib.request, os; urllib.request.urlopen(f'http://localhost:{os.environ.get(\"PORT\", \"8000\")}/health')"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log", "--log-level", "warning"]