"""Tests for the OpenTelemetry ingestion (issue #73)."""

from __future__ import annotations

from isnad.core.registry import Registry
from isnad.integrations.otel import ingest_trace, parse_otlp_json
from isnad.types import ChainGrade, NarratorGrade


def _sample_trace() -> dict:
    return {
        "resourceSpans": [
            {
                "resource": {"attributes": []},
                "scopeSpans": [
                    {
                        "scope": {"name": "test-instrumentation"},
                        "spans": [
                            {
                                "traceId": "abc123",
                                "spanId": "1",
                                "parentSpanId": None,
                                "name": "retrieve docs",
                                "startTimeUnixNano": "100",
                                "attributes": [
                                    {
                                        "key": "gen_ai.operation.name",
                                        "value": {"stringValue": "retrieve"},
                                    }
                                ],
                            },
                            {
                                "traceId": "abc123",
                                "spanId": "2",
                                "parentSpanId": "1",
                                "name": "chat gpt-4",
                                "startTimeUnixNano": "200",
                                "attributes": [
                                    {
                                        "key": "gen_ai.operation.name",
                                        "value": {"stringValue": "chat"},
                                    },
                                    {
                                        "key": "gen_ai.request.model",
                                        "value": {"stringValue": "gpt-4"},
                                    },
                                    {
                                        "key": "gen_ai.completion",
                                        "value": {"stringValue": "F=ma"},
                                    },
                                ],
                            },
                            {
                                # A DB span — not a transmitter.
                                "traceId": "abc123",
                                "spanId": "3",
                                "parentSpanId": "1",
                                "name": "SELECT ...",
                                "startTimeUnixNano": "150",
                                "attributes": [
                                    {"key": "db.system", "value": {"stringValue": "postgresql"}}
                                ],
                            },
                        ],
                    }
                ],
            }
        ]
    }


class TestParse:
    def test_flattens_spans_and_attributes(self):
        spans = parse_otlp_json(_sample_trace())
        assert len(spans) == 3
        by_id = {s.span_id: s for s in spans}
        assert by_id["2"].attributes["gen_ai.request.model"] == "gpt-4"
        assert by_id["2"].name == "chat gpt-4"
        assert by_id["2"].parent_span_id == "1"
        assert by_id["1"].parent_span_id is None
        assert by_id["3"].attributes["db.system"] == "postgresql"

    def test_int_and_bool_values(self):
        data = {
            "resourceSpans": [
                {
                    "resource": {},
                    "scopeSpans": [
                        {
                            "scope": {},
                            "spans": [
                                {
                                    "traceId": "t",
                                    "spanId": "s",
                                    "attributes": [
                                        {
                                            "key": "gen_ai.usage.input_tokens",
                                            "value": {"intValue": "42"},
                                        },
                                        {
                                            "key": "gen_ai.is_streaming",
                                            "value": {"boolValue": True},
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        span = parse_otlp_json(data)[0]
        assert span.attributes["gen_ai.usage.input_tokens"] == 42
        assert span.attributes["gen_ai.is_streaming"] is True


class TestIngest:
    def test_reconstructs_chain_in_time_order(self):
        reg = Registry()
        reg.register("retrieve", "general", grade=NarratorGrade.RELIABLE)
        reg.register("model:gpt-4", "general", grade=NarratorGrade.ACCEPTABLE)

        spans = parse_otlp_json(_sample_trace())
        result = ingest_trace(spans, reg, "general")

        assert result.transmitter_count == 2  # DB span excluded
        assert [s.narrator_id for s in result.chain] == ["retrieve", "model:gpt-4"]
        assert result.chain_grade == ChainGrade.HASAN.value  # weakest = ACCEPTABLE
        assert result.weakest_link == "model:gpt-4"
        assert result.claim_text == "F=ma"

    def test_ungraded_narrator_is_daif_by_default(self):
        reg = Registry()  # nothing registered → all UNGRADED
        spans = parse_otlp_json(_sample_trace())
        result = ingest_trace(spans, reg, "general")
        # strict default: UNGRADED → ḍaʿīf
        assert result.chain_grade == ChainGrade.DAIF.value

    def test_ungraded_narrator_lenient_option(self):
        reg = Registry()
        spans = parse_otlp_json(_sample_trace())
        result = ingest_trace(spans, reg, "general", lenient_unknown=True)
        assert result.chain_grade == ChainGrade.HASAN.value  # lenient ceiling

    def test_no_transmitters_is_daif(self):
        reg = Registry()
        spans = parse_otlp_json({
            "resourceSpans": [
                {
                    "resource": {},
                    "scopeSpans": [
                        {
                            "scope": {},
                            "spans": [
                                {"traceId": "t", "spanId": "1", "name": "SELECT", "attributes": []}
                            ],
                        }
                    ],
                }
            ]
        })
        result = ingest_trace(spans, reg, "general")
        assert result.transmitter_count == 0
        assert result.chain_grade == ChainGrade.DAIF.value
        assert result.weakest_link is None

    def test_claim_text_none_when_no_completion(self):
        reg = Registry()
        spans = parse_otlp_json({
            "resourceSpans": [
                {
                    "resource": {},
                    "scopeSpans": [
                        {
                            "scope": {},
                            "spans": [
                                {
                                    "traceId": "t",
                                    "spanId": "1",
                                    "name": "chat gpt-4",
                                    "attributes": [
                                        {
                                            "key": "gen_ai.operation.name",
                                            "value": {"stringValue": "chat"},
                                        },
                                        {
                                            "key": "gen_ai.request.model",
                                            "value": {"stringValue": "gpt-4"},
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ]
        })
        result = ingest_trace(spans, reg, "general")
        assert result.claim_text is None
