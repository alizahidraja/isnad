"""OpenTelemetry ingestion — grade an existing OTel GenAI trace as an isnād.

The premise (issue #73): every serious agent framework already emits OTLP, and
the GenAI semantic conventions cover model/token/latency but *not* output
quality. ISNAD grades the transmission — so ``isnad ingest --otlp`` sits on top
of the standard instead of asking anyone to instrument twice.

Honest limits (read before trusting the output):

- The GenAI conventions are in **Development** status and may change.
- OTel spans record model/token/latency, **not the claim text**. The isnād
  (transmission chain) is fully reconstructable; the matn (claim content) is
  only available if a span carries a ``gen_ai.completion`` attribute (legacy) —
  otherwise it is reported as ``null`` and only the chain is graded.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OtelSpan:
    """One OTLP span, flattened to the fields ISNAD needs."""

    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str
    attributes: dict[str, object]
    start_ns: int | None


def _scalar(value: dict[str, object]) -> object:
    """OTLP AnyValue → Python scalar (stringValue/intValue/…)."""
    if "stringValue" in value:
        return value["stringValue"]
    if "intValue" in value:
        return int(value["intValue"])
    if "boolValue" in value:
        return value["boolValue"]
    if "doubleValue" in value:
        return float(value["doubleValue"])
    return None


def _flatten(attributes: list[dict[str, object]]) -> dict[str, object]:
    """OTLP attribute list ``[{key, value}]`` → ``{key: scalar}``."""
    out: dict[str, object] = {}
    for a in attributes:
        key = a.get("key")
        if key is not None:
            out[str(key)] = _scalar(a.get("value", {}))
    return out


def _to_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(str(value))
    except (ValueError, TypeError):
        return None


def parse_otlp_json(data: dict[str, object]) -> list[OtelSpan]:
    """Parse an OTLP/JSON trace export into a flat list of spans.

    Walks ``resourceSpans → scopeSpans → spans``. Accepts the standard
    camelCase wire format (``traceId``, ``spanId``, ``parentSpanId``,
    ``startTimeUnixNano``).
    """
    spans: list[OtelSpan] = []
    for rs in data.get("resourceSpans", []):
        for ss in rs.get("scopeSpans", []):  # type: ignore[union-attr]
            for s in ss.get("spans", []):  # type: ignore[union-attr]
                spans.append(
                    OtelSpan(
                        trace_id=str(s.get("traceId", "")),
                        span_id=str(s.get("spanId", "")),
                        parent_span_id=s.get("parentSpanId"),
                        name=str(s.get("name", "")),
                        attributes=_flatten(s.get("attributes", [])),
                        start_ns=_to_int(s.get("startTimeUnixNano")),
                    )
                )
    return spans
