"""Backend-neutral OTLP transport and endpoint contracts."""

from dataclasses import replace
from unittest.mock import Mock

import pytest

from hermes_otel.backends import _ResolvedBackend, resolve
from hermes_otel.otlp_transport import create_exporter, signal_endpoint
from hermes_otel.plugin_config import BackendConfig, coerce_backends


@pytest.fixture(autouse=True)
def clean_transport_env(monkeypatch):
    import os

    for name in os.environ:
        if name.startswith("OTEL_EXPORTER_OTLP"):
            monkeypatch.delenv(name)


@pytest.fixture
def backend():
    return resolve(
        BackendConfig(type="otlp", endpoint="https://telemetry.example:443", protocol="grpc")
    )


@pytest.fixture
def grpc_exporters(monkeypatch):
    mocks = {}
    for signal, module, cls in (
        ("traces", "trace_exporter", "OTLPSpanExporter"),
        ("metrics", "metric_exporter", "OTLPMetricExporter"),
        ("logs", "_log_exporter", "OTLPLogExporter"),
    ):
        factory = Mock()
        monkeypatch.setattr(f"opentelemetry.exporter.otlp.proto.grpc.{module}.{cls}", factory)
        mocks[signal] = factory
    return mocks


@pytest.mark.parametrize("signal", ["traces", "metrics", "logs"])
def test_grpc_uses_same_target_and_selected_exporter(backend, grpc_exporters, signal):
    http = Mock()
    endpoint = signal_endpoint(backend, signal)
    result = create_exporter(
        backend, signal, http, endpoint=endpoint, headers={"Authorization": "token"}
    )
    grpc_exporters[signal].assert_called_once_with(
        endpoint="https://telemetry.example:443", headers={"authorization": "token"}
    )
    assert result is grpc_exporters[signal].return_value
    http.assert_not_called()


@pytest.mark.parametrize("signal", ["traces", "metrics", "logs"])
def test_http_defaults_preserve_constructor_arguments(signal):
    backend = resolve(BackendConfig(type="otlp", endpoint="http://localhost:4318/v1/traces"))
    endpoint = signal_endpoint(backend, signal)
    assert endpoint == f"http://localhost:4318/v1/{signal}"
    http = Mock()
    create_exporter(backend, signal, http, endpoint=endpoint, headers=None)
    http.assert_called_once_with(endpoint=endpoint, headers=None)


@pytest.mark.parametrize("protocol", ["grpc", "http/protobuf"])
@pytest.mark.parametrize("signal", ["metrics", "logs"])
def test_signal_endpoint_overrides(protocol, signal):
    backend = _ResolvedBackend(type="otlp", endpoint="https://traces:443", protocol=protocol)
    backend = replace(backend, **{f"{signal}_endpoint": "https://other:443"})
    assert signal_endpoint(backend, signal) == "https://other:443"


def test_yaml_loads_transport_fields(monkeypatch):
    entries = coerce_backends(
        [
            {"type": "otlp", "protocol": "grpc", "endpoint": "https://telemetry:443"},
        ]
    )
    backend = resolve(entries[0])
    assert backend.protocol == "grpc"
    assert backend.endpoint == "https://telemetry:443"


@pytest.mark.parametrize(
    "config",
    [
        BackendConfig(type="otlp", endpoint="localhost:4317", protocol="unknown"),
        BackendConfig(type="langfuse", protocol="grpc"),
    ],
)
def test_resolution_rejects_unsupported_protocol(config):
    with pytest.raises(ValueError):
        resolve(config)


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://collector/v1/traces",
        "https://collector?secret=x",
        "https://collector#fragment",
        "https://user:pass@collector:443",
        "ftp://collector:443",
        "",
        "/path",
    ],
)
def test_grpc_rejects_http_paths_and_invalid_targets(backend, endpoint):
    with pytest.raises(ValueError):
        create_exporter(backend, "traces", Mock(), endpoint=endpoint)


def test_factory_rejects_unknown_protocol(backend):
    with pytest.raises(ValueError, match="unsupported OTLP protocol"):
        create_exporter(
            replace(backend, protocol="invalid"), "traces", Mock(), endpoint=backend.endpoint
        )
