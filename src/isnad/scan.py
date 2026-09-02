"""Pipeline coverage scan — map live transmitters onto the warm registry (#206).

The scan answers one question: of the narrators a live pipeline uses, which are
*vouched* (the registry has a grade) and which are *cold* (UNGRADED → REVIEW
under the strict default)? It lists evidence — the ordinal grade + its
provenance (prior vs observation) — and never emits a numeric trust score.
"""

from __future__ import annotations

from dataclasses import dataclass

from isnad.core.registry import Registry
from isnad.types import NarratorGrade


@dataclass(frozen=True)
class ScanResult:
    """Which transmitters are vouched (graded) vs cold (ungraded)."""

    vouched: list[dict[str, str]]
    cold: list[dict[str, str]]


def scan_registry(
    narrator_ids: list[str],
    registry: Registry,
    domain: str = "general",
) -> ScanResult:
    """Map ``narrator_ids`` onto ``registry``.

    A narrator is *vouched* when the registry has a grade for it; otherwise it
    is *cold*. Vouched entries carry the ordinal grade + provenance, not a
    numeric confidence. Grades stay operator-local: a vouched "prior" grade is
    still gated to SERVE_WITH_CAVEAT/REVIEW, never plain SERVE.
    """
    vouched: list[dict[str, str]] = []
    cold: list[dict[str, str]] = []
    for nid in narrator_ids:
        narrator = registry.get(nid, domain)
        effective = registry.get_grade(nid, domain)
        if narrator is None or effective is NarratorGrade.UNGRADED:
            cold.append({
                "narrator_id": nid,
                "status": "cold",
                "note": "not in registry or UNGRADED — REVIEW (strict default)",
            })
        else:
            prov = registry.evidence_provenance(nid, domain)
            if prov.observation_backed:
                provenance = "observation (Supported)"
            elif prov.prior_only:
                provenance = "prior (Estimated)"
            elif prov.human_count > 0:
                provenance = "human (Reviewed)"
            else:
                provenance = "unvalidated (no observed or human evidence)"
            vouched.append({
                "narrator_id": nid,
                "status": "vouched",
                "grade": effective.value,
                "provenance": provenance,
            })
    return ScanResult(vouched=vouched, cold=cold)
