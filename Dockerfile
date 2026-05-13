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
    pip install --no-cache-dir -r requirements.txt && \
    # Upgrade venv packages with known CVEs to their fixed versions
    pip install --no-cache-dir --force-reinstall \
        "wheel>=0.46.2" "setuptools>=80.0.0" "jaraco-context>=6.1.0" && \
    # Remove build-only packages from venv — not needed at runtime
    # This ensures Trivy finds NO vulnerable pip/wheel/jaraco in the final image
    pip uninstall -y pip setuptools wheel jaraco-context jaraco.functools 2>/dev/null; \
    rm -rf /opt/venv/lib/python3.11/site-packages/pip* \
           /opt/venv/lib/python3.11/site-packages/setuptools* \
           /opt/venv/lib/python3.11/site-packages/_distutils_hack* \
           /opt/venv/lib/python3.11/site-packages/pkg_resources* \
           /opt/venv/lib/python3.11/site-packages/wheel* \
           /opt/venv/lib/python3.11/site-packages/jaraco* \
           /opt/venv/bin/pip* /opt/venv/bin/wheel* /opt/venv/bin/easy_install*

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — python-clean: strip vulnerable system packages from Python image
# Trivy scans all Docker layers, so we must remove packages HERE (same stage)
# before COPY --from picks them up in the runner stage
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-alpine AS python-clean

RUN rm -rf /usr/local/lib/python3.11/site-packages/* \
           /usr/local/lib/python3.11/ensurepip/ \
           /usr/local/bin/pip* /usr/local/bin/wheel* \
           /usr/local/bin/easy_install*

# ─────────────────────────────────────────────────────────────────────────────
# Stage 3 — runner: clean Alpine base + stripped Python = 0 CVEs
# Base is alpine (no Python layer CVEs), Python copied without site-packages
# ─────────────────────────────────────────────────────────────────────────────
FROM alpine:3.21 AS runner

WORKDIR /app

# Install runtime OS dependencies
RUN apk add --no-cache libpq libffi libstdc++ libgcc && \
    apk upgrade --no-cache

# Copy CLEANED Python installation (without pip/wheel/setuptools/jaraco-context)
# COPY --from only copies files that EXIST — removed files won't transfer
COPY --from=python-clean /usr/local/ /usr/local/

# Make sure dynamic linker can find Python shared libs
RUN ldconfig /usr/local/lib 2>/dev/null || true

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create non-root user for security
RUN addgroup --system --gid 1001 appgroup && \
    adduser  --system --uid 1001 --ingroup appgroup --no-create-home appuser

# Copy application source
COPY --chown=appuser:appgroup app/ ./app/

USER appuser

EXPOSE ${PORT:-8000}

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD ["python", "-c", "import urllib.request, os; urllib.request.urlopen(f'http://localhost:{os.environ.get(\"PORT\", \"8000\")}/health')"]

CMD ["/opt/venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log", "--log-level", "warning"]