# FastAPI application entry point.
# Boot sequence: tracing → logging → DB → blockchain → app

import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.utils.logging import setup_logging
from app.utils.tracing import setup_tracing
from app.utils.metrics import get_metrics, http_requests_total, http_request_duration_seconds
from app.db.database import init_db, close_db, get_session
from app.services.blockchain import init_blockchain
from app.routes.blockchain import router as blockchain_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Runs startup logic before yielding, cleanup after.
    """
    # ── Startup ──────────────────────────────────────────────────────────────
    setup_logging()
    setup_tracing(app)

    from app.utils.logger import get_logger
    logger = get_logger(__name__)

    logger.info("service_starting", service=settings.service_name, port=settings.port)

    await init_db()
    logger.info("database_connected")

    # Initialize blockchain from DB (restores chain on restart)
    async for session in get_session():
        await init_blockchain(session)
        break

    logger.info(
        "service_ready",
        service=settings.service_name,
        version=settings.service_version,
        port=settings.port,
    )

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    await close_db()
    logger.info("service_stopped")


# ── FastAPI App ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Blockchain Service",
    description=(
        "Lightweight blockchain microservice for order transaction integrity "
        "and DevSecOps deployment verification. "
        "No mining, no tokens — immutable append-only ledger."
    ),
    version=settings.service_version,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if not settings.is_production else [],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ── Request timing + metrics middleware ───────────────────────────────────────

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start  = time.perf_counter()
    route  = request.url.path
    method = request.method

    response = await call_next(request)

    duration    = time.perf_counter() - start
    status_code = str(response.status_code)

    # Skip /metrics and /health from being tracked (avoid noise)
    if route not in ("/metrics", "/health"):
        http_requests_total.labels(
            method=method, route=route, status_code=status_code
        ).inc()
        http_request_duration_seconds.labels(
            method=method, route=route, status_code=status_code
        ).observe(duration)

    return response

# ── Routes ────────────────────────────────────────────────────────────────────

app.include_router(blockchain_router)

# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": settings.service_name, "version": settings.service_version}

# ── Prometheus metrics endpoint ───────────────────────────────────────────────

@app.get("/metrics", tags=["Observability"], include_in_schema=False)
async def metrics():
    data, content_type = get_metrics()
    return Response(content=data, media_type=content_type)