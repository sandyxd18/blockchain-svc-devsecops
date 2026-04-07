# OpenTelemetry SDK setup for FastAPI + SQLAlchemy + asyncpg.
# Call setup_tracing() before creating the FastAPI app instance.
#
# Trace pipeline:
#   blockchain-service → OTLP/gRPC → Alloy → Tempo → Grafana

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from app.config import get_settings


def setup_tracing(app=None) -> None:
    settings = get_settings()

    resource = Resource.create({
        SERVICE_NAME:    settings.service_name,
        SERVICE_VERSION: settings.service_version,
    })

    exporter = OTLPSpanExporter(
        endpoint=settings.otel_exporter_otlp_endpoint,
        insecure=True,
    )

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    # Auto-instrument FastAPI (incoming HTTP spans)
    if app is not None:
        FastAPIInstrumentor.instrument_app(app)

    # Auto-instrument SQLAlchemy (DB query spans)
    SQLAlchemyInstrumentor().instrument()

    print(f"[Tracer] OpenTelemetry started → {settings.otel_exporter_otlp_endpoint}")