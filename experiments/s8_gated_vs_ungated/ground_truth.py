"""Ground Truth Module — Injection Manifest.

**FIREWALL MODULE**: This module records which claims were corrupted during
fault injection.  It MUST NEVER be imported by ANY grading, gating, or
routing module (grading.py, corroboration.py, registry.py, matrix.py, chain.py).

Permitted consumers:
- inject.py  (writes ground truth during injection)
- calibrate.py  (simulates audit verdicts from ground truth — legitimate)
- run.py  (simulates human-reviewer verdicts — legitimate)
- analyze.py  (computes evaluation metrics)
- audit_sample.py  (exports for human verification)

Forbidden consumers: all modules that compute grades, chain trust, or routing
decisions.  This separation is enforced by the firewall test in
tests/test_firewall.py.

Each entry records:
- claim_id: hash of original (pre-corruption) normalized claim text
- corrupted: whether the claim was altered by fault injection
- fault_type: class of fault applied (or "none")
- responsible_narrator: which narrator introduced the fault
- original_text: the pre-corruption claim text
- corrupted_text: the post-corruption claim text (same as original if not corrupted)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class InjectionRecord:
    """One claim's injection ground truth."""

    claim_id: str
    corrupted: bool
    fault_type: str  # "none", "ocr_noise", "negation_drop", "digit_swap", etc.
    responsible_narrator: str  # narrator_id of fault source, or "none"
    original_text: str
    corrupted_text: str
    domain: str = "general"
    chain_complete: bool = True  # False if chain was marked incomplete
    assigned_scraper: str = ""  # scraper variant assigned to this claim's chain
    assigned_ingest: str = ""  # ingest variant assigned to this claim's chain
    model_confidence: float = 0.0  # self-confidence score from extraction


@dataclass
class GroundTruth:
    """The injection manifest for the entire experiment.

    Populated during injection; read only during calibration (audit simulation)
    and evaluation (reviewer simulation, metric computation).  Never read by
    grading/gating code.
    """

    records: list[InjectionRecord] = field(default_factory=list)

    def add(self, record: InjectionRecord) -> None:
        self.records.append(record)

    def get(self, claim_id: str) -> InjectionRecord | None:
        for r in self.records:
            if r.claim_id == claim_id:
                return r
        return None

    def is_corrupted(self, claim_id: str) -> bool:
        r = self.get(claim_id)
        return r.corrupted if r else False

    def get_original_text(self, claim_id: str) -> str:
        r = self.get(claim_id)
        return r.original_text if r else ""

    @property
    def total_claims(self) -> int:
        return len(self.records)

    @property
    def corrupted_count(self) -> int:
        return sum(1 for r in self.records if r.corrupted)

    @property
    def incomplete_count(self) -> int:
        return sum(1 for r in self.records if not r.chain_complete)

    def summary(self) -> str:
        return (
            f"GroundTruth: {self.total_claims} claims, "
            f"{self.corrupted_count} corrupted "
            f"({100*self.corrupted_count/max(1,self.total_claims):.1f}%), "
            f"{self.incomplete_count} incomplete chains"
        )
