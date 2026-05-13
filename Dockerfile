# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 — builder: install dependencies into a virtual environment
# ─────────────────────────────────────────────────────────────────────────────
# Pin to a specific slim tag so builder & runner share the EXACT same glibc/ABI.
# This prevents pydantic-core's compiled C extension (_pydantic_core.so) from
# being built against a different libc version than what the runner uses.
FROM python:3.11.9-slim-bookworm AS builder

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

# Upgrade pip first, then install with --no-cache-dir to avoid stale wheels.
# --only-binary=pydantic_core ensures we always get the correct pre-built wheel
# matching the current CPython 3.11 + glibc (bookworm) combination.
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir \
        --only-binary=pydantic_core \
        -r requirements.txt

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — runner: minimal production image
# ─────────────────────────────────────────────────────────────────────────────
# MUST use the identical base as builder so the compiled .so files are ABI-compatible.
FROM python:3.11.9-slim-bookworm AS runner

WORKDIR /app

# Runtime dependency for asyncpg (libpq5) — apt-get because base is Debian/bookworm
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create non-root user for security (groupadd/useradd = Debian commands, NOT Alpine)
RUN groupadd --system --gid 1001 appgroup && \
    useradd  --system --uid 1001 --gid appgroup --no-create-home appuser

# Copy application source
COPY --chown=appuser:appgroup app/ ./app/

USER appuser

EXPOSE ${PORT:-8000}

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD ["python", "-c", "import urllib.request, os; urllib.request.urlopen(f'http://localhost:{os.environ.get(\"PORT\", \"8000\")}/health')"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log", "--log-level", "warning"]