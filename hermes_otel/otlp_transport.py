"""OTLP transport selection shared by all three signals.

HTTP exporters remain the default. Import gRPC only for a gRPC destination,
so an HTTP-only installation does not depend on importing grpcio at startup.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from .backends import _ResolvedBackend
from .helpers import derive_signal_endpoint


def signal_endpoint(backend: _ResolvedBackend, signal: str) -> str:
    """gRPC shares one target; HTTP derives /v1/metrics and /v1/logs."""
    override = getattr(backend, f"{signal}_endpoint", None)
    if override:
        return override
    if signal == "traces" or backend.protocol == "grpc":
        return backend.endpoint
    return derive_signal_endpoint(backend.endpoint, signal)


def create_exporter(
    backend: _ResolvedBackend, signal: str, http_exporter: Any, **kwargs: Any
) -> Any:
    """Build the selected SDK exporter, retaining existing HTTP constructor seams."""
    if backend.protocol == "http/protobuf":
        return http_exporter(**kwargs)
    if backend.protocol != "grpc":
        raise ValueError(f"unsupported OTLP protocol {backend.protocol!r}")
    endpoint = kwargs["endpoint"]
    parsed = urlparse(endpoint if "://" in endpoint else "//" + endpoint)
    if parsed.scheme not in ("", "http", "https") or not parsed.netloc:
        raise ValueError("gRPC endpoint must be host:port or an http(s) origin")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment or parsed.username:
        raise ValueError("gRPC endpoint must not contain a path, query, fragment or user info")

    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

    exporter = {
        "traces": OTLPSpanExporter,
        "metrics": OTLPMetricExporter,
        "logs": OTLPLogExporter,
    }[signal]
    if kwargs.get("headers"):
        # HTTP header names are case-insensitive; gRPC metadata requires lowercase.
        kwargs["headers"] = {k.lower(): v for k, v in kwargs["headers"].items()}
    return exporter(**kwargs)
