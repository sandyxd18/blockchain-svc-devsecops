# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 — builder
# Uses python:3.11-slim (Debian/glibc) — reliable package availability,
# no Alpine musl/glibc ABI mismatch, no Alpine package name confusion.
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# Build deps for C extensions (asyncpg compiles C, pydantic-core uses Rust wheels)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./

# Install all app dependencies into a venv for clean isolation
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt && \
    # Verify uvicorn is installed — fail loudly if not
    /opt/venv/bin/uvicorn --version && \
    echo "=== venv bin contents ===" && \
    ls -la /opt/venv/bin/

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — runner
# MUST use same glibc base as builder so compiled .so files are ABI-compatible.
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runner

WORKDIR /app

# Runtime libs only (libpq5 = asyncpg runtime, no -dev headers needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/* && \
    # Remove pip/wheel/setuptools/jaraco from system Python to eliminate CVEs:
    # CVE-2026-23949 (jaraco.context), CVE-2026-24049 (wheel),
    # CVE-2025-8869 / CVE-2026-3219 / CVE-2026-6357 / CVE-2026-1703 (pip)
    pip uninstall -y pip setuptools wheel 2>/dev/null || true && \
    rm -rf \
        /usr/local/lib/python3.11/site-packages/pip* \
        /usr/local/lib/python3.11/site-packages/wheel* \
        /usr/local/lib/python3.11/site-packages/setuptools* \
        /usr/local/lib/python3.11/site-packages/_distutils_hack* \
        /usr/local/lib/python3.11/site-packages/pkg_resources* \
        /usr/local/lib/python3.11/site-packages/jaraco* \
        /usr/local/lib/python3.11/ensurepip/ \
        /usr/local/bin/pip* \
        /usr/local/bin/wheel* \
        /usr/local/bin/easy_install*

# Copy the fully-built virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Verify the venv copy worked correctly
RUN ls -la /opt/venv/bin/uvicorn

ENV PATH="/opt/venv/bin:$PATH"

# Create non-root user (Debian uses groupadd/useradd)
RUN groupadd --system --gid 1001 appgroup && \
    useradd  --system --uid 1001 --gid appgroup --no-create-home appuser

# Copy application source
COPY --chown=appuser:appgroup app/ ./app/

USER appuser

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:3000/health')"

CMD ["/opt/venv/bin/uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "3000", \
     "--workers", "1", \
     "--no-access-log", \
     "--log-level", "warning"]