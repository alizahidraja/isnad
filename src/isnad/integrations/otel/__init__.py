"""OpenTelemetry ingestion — grade an existing OTel GenAI trace as an isnād.

``isnad ingest --otlp trace.json`` reconstructs the transmission chain from an
OTLP/JSON trace, looks each transmitter up in the registry, and grades the
chain weakest-link. See ``docs/otel-mapping.md`` for the span→narrator mapping
and its honest limits.
"""

from __future__ import annotations

from isnad.integrations.otel.ingest import ChainStep, IngestedTrace, ingest_trace
from isnad.integrations.otel.parse import OtelSpan, parse_otlp_json

__all__ = [
    "ChainStep",
    "IngestedTrace",
    "OtelSpan",
    "ingest_trace",
    "parse_otlp_json",
]
