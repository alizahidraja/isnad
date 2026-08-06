"""ISNAD Trace — versioned, serializable schema for transmission chain capture and rendering.

isnad_trace v0.1 is the contract between:
- Capture (LangChain callbacks, manual construction, PROV-AGENT ingestion)
- Rendering (the viewer component)

PROV mapping: Entity ↔ DocumentRef, Activity ↔ TransmitterNode, Agent ↔ (narrator_id, role).
"""

from isnad.trace.schema import (
    ChainIntegrity,
    ContradictionFlag,
    CorroborationVerdict,
    DocumentRef,
    Grade,
    OriginStrength,
    Role,
    TraceV01,
    TransmitterNode,
)

__all__ = [
    "ChainIntegrity",
    "ContradictionFlag",
    "CorroborationVerdict",
    "DocumentRef",
    "Grade",
    "OriginStrength",
    "Role",
    "TraceV01",
    "TransmitterNode",
]
