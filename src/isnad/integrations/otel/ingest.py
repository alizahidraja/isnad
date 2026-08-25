"""Map an OTel GenAI trace onto an isnād and grade it (issue #73)."""

from __future__ import annotations

from dataclasses import dataclass

from isnad.core.grading import grade_chain
from isnad.integrations.otel.parse import OtelSpan
from isnad.types import ChainGrade, NarratorGrade, TransformType


@dataclass(frozen=True)
class ChainStep:
    """One transmitter in the reconstructed isnād."""

    narrator_id: str
    grade: str
    span_name: str
    model: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "narrator_id": self.narrator_id,
            "grade": self.grade,
            "span_name": self.span_name,
            "model": self.model,
        }


@dataclass(frozen=True)
class IngestedTrace:
    """The result of grading an OTel trace."""

    trace_id: str
    chain: tuple[ChainStep, ...]
    chain_grade: str
    weakest_link: str | None
    claim_text: str | None
    span_count: int
    transmitter_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "trace_id": self.trace_id,
            "span_count": self.span_count,
            "transmitter_count": self.transmitter_count,
            "chain": [s.to_dict() for s in self.chain],
            "chain_grade": self.chain_grade,
            "weakest_link": self.weakest_link,
            "claim_text": self.claim_text,
        }


def _narrator_id(span: OtelSpan) -> str | None:
    """Map a span to a narrator id, or None if it is not a transmitter.

    A transmitter is a span that carries a GenAI model or operation attribute.
    The model is preferred (it is the "who"); the operation is a fallback.
    """
    model = span.attributes.get("gen_ai.response.model") or span.attributes.get(
        "gen_ai.request.model"
    )
    if model:
        return f"model:{model}"
    operation = span.attributes.get("gen_ai.operation.name")
    if operation:
        return str(operation)
    return None


def ingest_trace(
    spans: list[OtelSpan],
    registry,
    domain: str = "general",
    *,
    lenient_unknown: bool = False,
) -> IngestedTrace:
    """Reconstruct the isnād from an OTel trace and grade it.

    Transmitters are the spans with a GenAI model/operation attribute, ordered
    by ``startTimeUnixNano`` (the order things happened). Each is looked up in
    the registry; the chain is graded weakest-link. The claim text is taken from
    the last transmitter's ``gen_ai.completion`` if present (else ``None``).
    """
    transmitters: list[tuple[OtelSpan, str]] = []
    for span in spans:
        nid = _narrator_id(span)
        if nid is not None:
            transmitters.append((span, nid))
    transmitters.sort(key=lambda t: t[0].start_ns if t[0].start_ns is not None else 0)

    chain: list[ChainStep] = []
    grades: list[NarratorGrade] = []
    for span, nid in transmitters:
        grade = registry.get_grade(nid, domain)
        grades.append(grade)
        model = span.attributes.get("gen_ai.response.model") or span.attributes.get(
            "gen_ai.request.model"
        )
        chain.append(
            ChainStep(
                narrator_id=nid,
                grade=grade.value,
                span_name=span.name,
                model=str(model) if model is not None else None,
            )
        )

    if grades:
        chain_grade = grade_chain(
            grades,
            [TransformType.PASS_THROUGH] * len(grades),
            is_complete=True,
            lenient_unknown=lenient_unknown,
        )
        weakest = chain[grades.index(min(grades))].narrator_id
    else:
        chain_grade = ChainGrade.DAIF
        weakest = None

    claim: str | None = None
    if transmitters:
        candidate = transmitters[-1][0].attributes.get("gen_ai.completion")
        if isinstance(candidate, str):
            claim = candidate

    trace_id = spans[0].trace_id if spans else ""
    return IngestedTrace(
        trace_id=trace_id,
        chain=tuple(chain),
        chain_grade=chain_grade.value,
        weakest_link=weakest,
        claim_text=claim,
        span_count=len(spans),
        transmitter_count=len(transmitters),
    )
