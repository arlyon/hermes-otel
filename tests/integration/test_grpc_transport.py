"""Real local OTLP/gRPC exports for all three signals."""

import logging
import os
from concurrent.futures import ThreadPoolExecutor

import grpc
import pytest
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest,
    ExportLogsServiceResponse,
)
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceRequest,
    ExportMetricsServiceResponse,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)

from hermes_otel.plugin_config import BackendConfig, HermesOtelConfig
from hermes_otel.tracer import HermesOTelPlugin


@pytest.fixture
def receiver():
    received = {signal: [] for signal in ("traces", "metrics", "logs")}
    metadata = []
    server = grpc.server(ThreadPoolExecutor(max_workers=3))
    for signal, service, request, response in (
        (
            "traces",
            "opentelemetry.proto.collector.trace.v1.TraceService",
            ExportTraceServiceRequest,
            ExportTraceServiceResponse,
        ),
        (
            "metrics",
            "opentelemetry.proto.collector.metrics.v1.MetricsService",
            ExportMetricsServiceRequest,
            ExportMetricsServiceResponse,
        ),
        (
            "logs",
            "opentelemetry.proto.collector.logs.v1.LogsService",
            ExportLogsServiceRequest,
            ExportLogsServiceResponse,
        ),
    ):

        def export(request, context, signal=signal, response=response):
            received[signal].append(request)
            metadata.append(dict(context.invocation_metadata()))
            return response()

        server.add_generic_rpc_handlers(
            (
                grpc.method_handlers_generic_handler(
                    service,
                    {
                        "Export": grpc.unary_unary_rpc_method_handler(
                            export,
                            request_deserializer=request.FromString,
                            response_serializer=response.SerializeToString,
                        )
                    },
                ),
            )
        )
    port = server.add_insecure_port("127.0.0.1:0")
    assert port
    server.start()
    yield f"http://localhost:{port}", received, metadata
    server.stop(0).wait()


@pytest.fixture(autouse=True)
def clean_export_env(monkeypatch):
    for name in os.environ:
        if name.startswith("OTEL_EXPORTER_OTLP"):
            monkeypatch.delenv(name)


def test_all_three_signals_reach_real_grpc_receiver(receiver):
    target, received, metadata = receiver
    backend = BackendConfig(
        type="otlp", protocol="grpc", endpoint=target, headers={"Authorization": "test-token"}
    )
    plugin = HermesOTelPlugin(
        config=HermesOtelConfig(
            backends=(backend,),
            dashboard_live=False,
            content_capture="off",
            capture_logs=True,
            log_attach_logger="hermes-grpc-test",
            flush_interval_ms=60000,
        )
    )
    try:
        assert plugin.init()
        plugin.start_span(name="grpc-test", key="test", kind="general")
        plugin.end_span("test", status="ok")
        plugin.record_metric("session_count", 1, {"platform": "test"})
        logging.getLogger("hermes-grpc-test").warning("gRPC log test")
        plugin._force_flush(timeout_millis=5000)
        assert all(received.values()), {signal: len(items) for signal, items in received.items()}
        spans = [
            span
            for request in received["traces"]
            for resource in request.resource_spans
            for scope in resource.scope_spans
            for span in scope.spans
        ]
        assert any(span.name == "grpc-test" for span in spans)
        logs = [
            record
            for request in received["logs"]
            for resource in request.resource_logs
            for scope in resource.scope_logs
            for record in scope.log_records
        ]
        assert any(record.body.string_value == "gRPC log test" for record in logs)
        assert all(item.get("authorization") == "test-token" for item in metadata)
    finally:
        plugin.shutdown()
