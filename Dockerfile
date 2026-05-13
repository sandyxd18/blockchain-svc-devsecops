# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 — builder: install dependencies into a virtual environment
# Uses python:3.11-alpine so compiled C extensions (pydantic-core, asyncpg)
# target musl libc — MUST match the runner base to avoid ABI mismatch.
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-alpine AS builder

WORKDIR /app

# Build tools required to compile C extensions (asyncpg, pydantic-core)
RUN apk add --no-cache gcc musl-dev libpq-dev libffi-dev

# Create virtual environment for clean dependency isolation
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt ./

# Install all dependencies into the venv, then strip build-only packages
# to minimise the attack surface visible to Trivy in the final image.
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt && \
    # Remove build-only packages — not needed at runtime
    pip uninstall -y pip setuptools wheel 2>/dev/null || true && \
    rm -rf /opt/venv/lib/python3.11/site-packages/pip* \
           /opt/venv/lib/python3.11/site-packages/setuptools* \
           /opt/venv/lib/python3.11/site-packages/_distutils_hack* \
           /opt/venv/lib/python3.11/site-packages/pkg_resources* \
           /opt/venv/lib/python3.11/site-packages/wheel* \
           /opt/venv/bin/pip* \
           /opt/venv/bin/wheel* \
           /opt/venv/bin/easy_install*

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — runner: minimal Alpine production image
# Same musl ABI as builder — compiled .so files are ABI-compatible.
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-alpine AS runner

WORKDIR /app

# Runtime libraries only (no build tools)
RUN apk add --no-cache libpq libffi && \
    apk upgrade --no-cache && \
    # Remove vulnerable build-only packages from system Python:
    # pip (CVE-2025-8869, CVE-2026-3219, CVE-2026-6357, CVE-2026-1703)
    # wheel (CVE-2026-24049), jaraco.context (CVE-2026-23949)
    # These are NOT needed at runtime — app uses /opt/venv exclusively.
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

# Copy virtual environment from builder (contains uvicorn + all app deps)
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create non-root user for security (addgroup/adduser = Alpine commands)
RUN addgroup --system --gid 1001 appgroup && \
    adduser  --system --uid 1001 --ingroup appgroup --no-create-home appuser

# Copy application source
COPY --chown=appuser:appgroup app/ ./app/

USER appuser

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:3000/health')"

CMD ["/opt/venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3000", "--workers", "1", "--no-access-log", "--log-level", "warning"]