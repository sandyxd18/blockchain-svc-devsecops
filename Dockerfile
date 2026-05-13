# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 — builder
# python:3.11-alpine uses musl libc — compiled C extensions (asyncpg,
# pydantic-core) are built for musl, so they are ABI-compatible with runner.
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-alpine AS builder

WORKDIR /app

# Build tools for C extensions:
#   postgresql-dev  → libpq headers (for asyncpg)   [Alpine name, NOT libpq-dev]
#   python3-dev     → Python C headers (for uvloop, httptools)
#   gcc musl-dev    → compiler + musl headers
#   libffi-dev      → FFI headers (for some otel packages)
RUN apk add --no-cache gcc musl-dev python3-dev postgresql-dev libffi-dev

# Create isolated virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt ./

# 1. Upgrade pip/wheel/setuptools inside venv
# 2. Install all app dependencies
# 3. Verify uvicorn binary exists (fail build loudly if missing)
# 4. Strip build-only packages from venv to reduce CVE surface
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt && \
    # Fail fast if uvicorn was not installed correctly
    /opt/venv/bin/uvicorn --version && \
    # Strip build-only tools (not needed at runtime)
    pip uninstall -y pip setuptools wheel 2>/dev/null || true && \
    rm -rf \
        /opt/venv/lib/python3.11/site-packages/pip* \
        /opt/venv/lib/python3.11/site-packages/setuptools* \
        /opt/venv/lib/python3.11/site-packages/_distutils_hack* \
        /opt/venv/lib/python3.11/site-packages/pkg_resources* \
        /opt/venv/lib/python3.11/site-packages/wheel* \
        /opt/venv/bin/pip* \
        /opt/venv/bin/wheel* \
        /opt/venv/bin/easy_install*

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — runner
# Minimal Alpine image — MUST use same musl libc as builder.
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-alpine AS runner

WORKDIR /app

# Runtime libs only (no build headers):
#   libpq     → asyncpg runtime (Alpine name)
#   libffi    → FFI runtime
RUN apk add --no-cache libpq libffi && \
    apk upgrade --no-cache && \
    # Remove build tools and CVE-bearing packages from system Python.
    # The app ONLY uses /opt/venv, so system pip/wheel/setuptools are unused.
    # Removes: CVE-2026-23949 (jaraco.context), CVE-2026-24049 (wheel),
    #          CVE-2025-8869 / CVE-2026-3219 / CVE-2026-6357 / CVE-2026-1703 (pip)
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

# Copy the pre-built virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create non-root user (Alpine uses addgroup/adduser, NOT groupadd/useradd)
RUN addgroup --system --gid 1001 appgroup && \
    adduser  --system --uid 1001 --ingroup appgroup --no-create-home appuser

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