import logging

log = logging.getLogger(__name__)


def setup_telemetry(app) -> None:
    """Configure OpenTelemetry tracing. No-op if Tempo is unreachable or SDK missing."""
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        from app.core.config import get_settings
        settings = get_settings()

        exporter = OTLPSpanExporter(
            endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT,
            insecure=True,
        )
        provider = TracerProvider()
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        FastAPIInstrumentor.instrument_app(app)
        SQLAlchemyInstrumentor().instrument()

        try:
            from opentelemetry.instrumentation.redis import RedisInstrumentor
            RedisInstrumentor().instrument()
        except ImportError:
            pass

        log.info("OpenTelemetry tracing enabled — endpoint=%s", settings.OTEL_EXPORTER_OTLP_ENDPOINT)
    except Exception as exc:
        log.warning("OpenTelemetry setup failed — tracing disabled: %s", exc)
