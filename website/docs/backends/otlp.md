---
sidebar_position: 8
title: "Generic OTLP"
description: "Send Hermes traces, metrics and logs to an OTLP/HTTP or OTLP/gRPC endpoint."
---

# Generic OTLP

If your backend isn't on the list but it accepts **OTLP over HTTP or gRPC**, the generic `otlp` type has you covered. Point at an endpoint, set any auth headers, and go. HTTP/protobuf remains the default; gRPC is opt-in per destination.

**Signals:** traces, metrics and logs; turn off any signal your endpoint does not accept.

## Typical use cases

- Company-wide OTel collector (OpenTelemetry Collector, Grafana Alloy, etc.)
- Commercial vendors with an OTLP ingest path (Honeycomb, New Relic, Datadog, Uptrace, OpenObserve)
- Custom sink you're prototyping

## Configuration

Via `config.yaml`:

```yaml
backends:
  - type: otlp
    name: my-collector           # Friendly name shown in logs
    endpoint: http://collector:4318/v1/traces
    headers:
      X-Auth: secret
      X-Tenant: acme
    metrics: true                # Default true — set false for traces-only collectors
```

The `name` is purely for log output ("`[hermes-otel] ✓ my-collector connected`") — it doesn't affect the spans themselves.

## gRPC transport

Set `protocol: grpc` on a generic `type: otlp` entry. All three signals use the same gRPC target; `/v1/traces`, `/v1/metrics` and `/v1/logs` are HTTP paths and must not be included.

```yaml
backends:
  - type: otlp
    name: telemetry
    protocol: grpc
    endpoint: http://localhost:4317
    headers:
      Authorization: Bearer ${TELEMETRY_TOKEN}
```

The SDK's existing connection-security defaults and environment settings apply. `http://host:port` selects plaintext by default; HTTPS or a bare target uses TLS by default. `protocol` is selected by YAML, not by `OTEL_EXPORTER_OTLP_PROTOCOL`.

`protocol: grpc` is supported by the generic `otlp` type; named vendor backends retain their HTTP URL conventions. A single `backends:` list can mix HTTP and gRPC destinations, each with its own independent export queue. Header names are lowercased for gRPC metadata; values and per-backend precedence are unchanged.

## Examples

### Honeycomb

```yaml
backends:
  - type: otlp
    name: honeycomb
    endpoint: https://api.honeycomb.io/v1/traces
    headers:
      x-honeycomb-team: ${HONEYCOMB_API_KEY}
      x-honeycomb-dataset: hermes-agent
```

### telemetry.dev

```yaml
backends:
  - type: otlp
    name: telemetry-dev
    endpoint: https://ingest.telemetry.dev/v1/traces
    headers:
      Authorization: Bearer ${TELEMETRY_DEV_API_KEY}
```

See the dedicated [telemetry.dev](/backends/telemetry) page for endpoints, attribute fit, and troubleshooting.

### New Relic (OTLP endpoint)

```yaml
backends:
  - type: otlp
    name: new-relic
    endpoint: https://otlp.nr-data.net/v1/traces
    headers:
      api-key: ${NEW_RELIC_LICENSE_KEY}
```

### Datadog (via Datadog Agent with OTLP ingest)

```yaml
backends:
  - type: otlp
    name: datadog
    endpoint: http://datadog-agent:4318/v1/traces
    # Datadog's OTLP ingest goes through the local agent; no auth header needed there.
```

### A central OTel Collector

```yaml
backends:
  - type: otlp
    name: central
    endpoint: http://otel-collector.internal:4318/v1/traces
```

The repo ships a ready-made one for destinations the plugin cannot reach with a static header ([Azure Monitor](/backends/azure-monitor), AWS, Google Cloud) and for printing the raw export: see [OpenTelemetry Collector](/backends/collector).

### Metrics-only at a separate endpoint

If your collector splits traces and metrics across different paths, the plugin derives the metrics endpoint by replacing `/v1/traces` with `/v1/metrics`. If that doesn't match your setup, open an issue — we can add a `metrics_endpoint:` override.

## Env var auth

Secrets inline in YAML are discouraged. Use env var interpolation (`${VAR_NAME}`) for headers:

```yaml
backends:
  - type: otlp
    endpoint: https://api.honeycomb.io/v1/traces
    headers:
      x-honeycomb-team: ${HONEYCOMB_API_KEY}
```

Alternatively, set global headers once (applies to every backend):

```yaml
headers:
  X-Company-Auth: ${SHARED_SECRET}

backends:
  - type: otlp
    endpoint: https://api.honeycomb.io/v1/traces
    headers:
      x-honeycomb-team: ${HONEYCOMB_API_KEY}
```

Per-backend headers are merged on top of global headers; same-named keys get overwritten by the per-backend value.

## Troubleshooting

**"Which attribute convention does my backend use?"**

The plugin emits **both** `gen_ai.*` and OpenInference `llm.*` on every span — whichever one your backend indexes on, it'll pick up.

**"Traces show up; metrics don't"**

- Not every backend accepts OTLP metrics. Set `metrics: false` on the backend entry to silence the metrics exporter.
- If your metrics endpoint isn't `/v1/metrics` derived from the trace endpoint, open an issue.

**"TLS handshake errors"**

- The plugin uses `opentelemetry-exporter-otlp-proto-http`, which relies on the system cert store. If you're behind a corporate MITM CA, you may need `REQUESTS_CA_BUNDLE` or `SSL_CERT_FILE` pointing at your CA bundle.
