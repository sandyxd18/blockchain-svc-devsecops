# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 — builder
# Uses python:3.11-alpine to ensure ABI compatibility with the runner
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-alpine AS builder

WORKDIR /app

# Build deps for C extensions (asyncpg compiles C, pydantic-core uses Rust wheels)
RUN apk add --no-cache \
        gcc \
        musl-dev \
        postgresql-dev \
        python3-dev \
        libffi-dev \
        g++ \
        make

COPY requirements.txt ./

# Install all app dependencies into a venv for clean isolation
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt && \
    # Verify uvicorn is installed — fail loudly if not
    /opt/venv/bin/uvicorn --version && \
    # Remove vulnerable packages from the venv
    /opt/venv/bin/pip uninstall -y pip setuptools wheel jaraco-context jaraco.functools 2>/dev/null || true && \
    rm -rf /opt/venv/lib/python3.11/site-packages/pip* \
           /opt/venv/lib/python3.11/site-packages/wheel* \
           /opt/venv/lib/python3.11/site-packages/setuptools* \
           /opt/venv/lib/python3.11/site-packages/_distutils_hack* \
           /opt/venv/lib/python3.11/site-packages/pkg_resources* \
           /opt/venv/lib/python3.11/site-packages/jaraco* \
           /opt/venv/bin/pip* /opt/venv/bin/wheel* /opt/venv/bin/easy_install*

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — runner
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-alpine AS runner

WORKDIR /app

# Runtime libs only
RUN apk add --no-cache \
        libpq \
        libstdc++ \
        libgcc && \
    # Remove pip/wheel/setuptools from system Python to eliminate CVEs
    rm -rf \
        /usr/local/lib/python3.11/site-packages/* \
        /usr/local/lib/python3.11/ensurepip/ \
        /usr/local/bin/pip* \
        /usr/local/bin/wheel* \
        /usr/local/bin/easy_install*

# Copy the fully-built virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Verify the venv copy worked correctly
RUN ls -la /opt/venv/bin/uvicorn

ENV PATH="/opt/venv/bin:$PATH"

# Create non-root user
RUN addgroup -S appgroup && \
    adduser -S appuser -G appgroup -h /app

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