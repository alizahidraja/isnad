"""ISNAD Pipeline Deep-Dive — Single Known Fact, Every Edge Case.

Takes one ground-truth physics fact, builds a SAHIH chain around it,
then explores every degradation, upgrade, and edge case.

Fact: "momentum is mass times velocity" (p = mv)

Chain:  openstax_v3 (RELIABLE) → pdf_scraper_a (ACCEPTABLE) → ingest_model_a (ACCEPTABLE)
Grade:  HASAN (weakest-link = ACCEPTABLE)

Edge cases explored:
  A. Clean chain → HASAN
  B. All narrators RELIABLE → SAHIH
  C. One weak narrator → DAIF
  D. One rejected narrator → MAWDU
  E. Incomplete chain → DAIF (ittiṣāl cap)
  F. Destructive link + corroboration repair
  G. Corroboration: 2 independent HASAN chains → upgrade
  H. Corroboration: same model family → no upgrade (madār)
  I. Version bump → UNGRADED
  J. Bayesian: evidence progression UNGRADED→WEAK→ACCEPTABLE→RELIABLE→WEAK→REJECTED
  K. Decision matrix: every chain×content combination
  L. Stale grade recovery (evidence after version bump)
"""

from __future__ import annotations

import os
import sys
import time

_parent = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_parent, "src"))

from isnad.core.chain import Chain, ChainLinkSpec
from isnad.core.grading import grade_chain
from isnad.core.decision import decide, describe_action
from isnad.core.registry import Registry, BayesianTransitionPolicy
from isnad.core.corroboration import (
    CorroborationEngine,
    SharedLineageDetector,
    evaluate_corroboration,
)
from isnad.types import (
    Action, ChainGrade, ContentVerdict, EvidenceAction, EvidenceType,
    NarratorGrade, TransformType,
)

SEP = "═" * 72
PASS = "✅"
FAIL = "❌"
NOTE = "📝"
results: list[tuple[str, bool, str]] = []
_start = time.time()


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((name, condition, detail))
    icon = PASS if condition else FAIL
    extra = f"  → {detail}" if detail else ""
    print(f"  {icon} {name}{extra}")


def note(msg: str) -> None:
    print(f"  {NOTE} {msg}")


# ═══════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("ISNAD PIPELINE DEEP-DIVE")
print(f"FACT: 'momentum is mass times velocity' (p = mv)")
print(SEP)

# ── Setup: build the canonical chain ────────────────────────────
BASE_NARRATORS = {
    "openstax_v3": "Source — OpenStax physics textbook",
    "pdf_scraper_a": "Scraper — reliable PDF extractor",
    "ingest_model_a": "Model — LLM that paraphrases faithfully",
}

canonical_chain = Chain([
    ChainLinkSpec("openstax_v3", 0, transform_type=TransformType.PASS_THROUGH, domain="physics"),
    ChainLinkSpec("pdf_scraper_a", 1, transform_type=TransformType.DESTRUCTIVE, domain="physics"),
    ChainLinkSpec("ingest_model_a", 2, transform_type=TransformType.GENERATIVE, domain="physics"),
])


# ═══════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("A. CLEAN CHAIN — mixed grades, weakest-link rule")
print(SEP)

reg = Registry()
reg.register("openstax_v3", "physics", grade=NarratorGrade.RELIABLE)
reg.register("pdf_scraper_a", "physics", grade=NarratorGrade.ACCEPTABLE)
reg.register("ingest_model_a", "physics", grade=NarratorGrade.ACCEPTABLE)

grades = [reg.get_grade(l.narrator_id, l.domain) for l in canonical_chain.links]
note(f"Link grades: {[g.value for g in grades]}")
cg = grade_chain(grades, [l.transform_type for l in canonical_chain.links], is_complete=True)
check("A1. RELIABLE → ACCEPTABLE → ACCEPTABLE = HASAN",
      cg == ChainGrade.HASAN, f"got {cg.value}")
check("A2. HASAN + UNVERIFIABLE → REVIEW",
      decide(cg, ContentVerdict.UNVERIFIABLE) == Action.REVIEW)


# ═══════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("B. ALL RELIABLE — should reach SAHIH")
print(SEP)

reg2 = Registry()
for nid in BASE_NARRATORS:
    reg2.register(nid, "physics", grade=NarratorGrade.RELIABLE)
grades2 = [reg2.get_grade(l.narrator_id, l.domain) for l in canonical_chain.links]
cg2 = grade_chain(grades2, [l.transform_type for l in canonical_chain.links], is_complete=True)
check("B1. All RELIABLE → SAHIH", cg2 == ChainGrade.SAHIH, f"got {cg2.value}")
check("B2. SAHIH + CONSISTENT → SERVE (cache!)",
      decide(cg2, ContentVerdict.CONSISTENT) == Action.SERVE)
check("B3. SAHIH + CONTRADICTION → REVIEW (ʿilal signal)",
      decide(cg2, ContentVerdict.CONTRADICTION) == Action.REVIEW)
note("   This is the highest-value review signal in the paper.")


# ═══════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("C. ONE WEAK LINK — chain collapses to DAIF")
print(SEP)

reg3 = Registry()
reg3.register("openstax_v3", "physics", grade=NarratorGrade.RELIABLE)
reg3.register("pdf_scraper_a", "physics", grade=NarratorGrade.WEAK)  # ← weak
reg3.register("ingest_model_a", "physics", grade=NarratorGrade.RELIABLE)
grades3 = [reg3.get_grade(l.narrator_id, l.domain) for l in canonical_chain.links]
cg3 = grade_chain(grades3, [l.transform_type for l in canonical_chain.links], is_complete=True)
check("C1. WEAK scraper contaminates chain → DAIF",
      cg3 == ChainGrade.DAIF, f"got {cg3.value}")
check("C2. DAIF + CONSISTENT → REVIEW (seek corroboration)",
      decide(cg3, ContentVerdict.CONSISTENT) == Action.REVIEW)
check("C3. DAIF + CONTRADICTION → QUARANTINE",
      decide(cg3, ContentVerdict.CONTRADICTION) == Action.QUARANTINE)


# ═══════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("D. REJECTED NARRATOR → MAWDU (active containment)")
print(SEP)

reg4 = Registry()
reg4.register("openstax_v3", "physics", grade=NarratorGrade.RELIABLE)
reg4.register("pdf_scraper_a", "physics", grade=NarratorGrade.REJECTED)  # ← poisoned
reg4.register("ingest_model_a", "physics", grade=NarratorGrade.RELIABLE)
grades4 = [reg4.get_grade(l.narrator_id, l.domain) for l in canonical_chain.links]
cg4 = grade_chain(grades4, [l.transform_type for l in canonical_chain.links], is_complete=True)
check("D1. Any REJECTED → MAWDU immediately", cg4 == ChainGrade.MAWDU, f"got {cg4.value}")
check("D2. MAWDU + CONSISTENT → REJECT_AND_QUARANTINE",
      decide(cg4, ContentVerdict.CONSISTENT) == Action.REJECT_AND_QUARANTINE_NARRATOR)
check("D3. ALL MAWDU cells → REJECT_AND_QUARANTINE",
      decide(cg4, ContentVerdict.CONTRADICTION) == Action.REJECT_AND_QUARANTINE_NARRATOR
      and decide(cg4, ContentVerdict.UNVERIFIABLE) == Action.REJECT_AND_QUARANTINE_NARRATOR)
note("   MAWDU is active containment — narrator gets quarantined, never served.")


# ═══════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("E. INCOMPLETE CHAIN (munqaṭiʿ) → DAIF cap")
print(SEP)

gap_chain = Chain([
    ChainLinkSpec("openstax_v3", 0, domain="physics"),
    # STEP 1 MISSING — gap in transmission
    ChainLinkSpec("ingest_model_a", 2, domain="physics"),
])
check("E1. Gap chain is munqaṭiʿ", not gap_chain.is_complete)
reg5 = Registry()
reg5.register("openstax_v3", "physics", grade=NarratorGrade.RELIABLE)
reg5.register("ingest_model_a", "physics", grade=NarratorGrade.RELIABLE)
grades5 = [reg5.get_grade(l.narrator_id, l.domain) for l in gap_chain.links]
cg5 = grade_chain(grades5, [TransformType.PASS_THROUGH, TransformType.GENERATIVE], is_complete=False)
check("E2. All RELIABLE but incomplete → DAIF (ittiṣāl cap)",
      cg5 == ChainGrade.DAIF, f"got {cg5.value}")
note("   Completeness is an epistemic property — gaps auto-cap at DAIF.")


# ═══════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("F. DESTRUCTIVE LINK + CORROBORATION REPAIR")
print(SEP)

# Destructive links (extraction, chunking) create a permanent floor
# that can ONLY be repaired by a corroborated generative link.
reg_f = Registry()
reg_f.register("openstax_v3", "physics", grade=NarratorGrade.RELIABLE)
reg_f.register("pdf_scraper_a", "physics", grade=NarratorGrade.WEAK)     # ← bad scraper
reg_f.register("ingest_model_a", "physics", grade=NarratorGrade.RELIABLE) # ← good model

repair_chain = Chain([
    ChainLinkSpec("openstax_v3", 0, transform_type=TransformType.PASS_THROUGH, domain="physics"),
    ChainLinkSpec("pdf_scraper_a", 1, transform_type=TransformType.DESTRUCTIVE, domain="physics"),
    ChainLinkSpec("ingest_model_a", 2, transform_type=TransformType.GENERATIVE, domain="physics"),
])
grades_f = [reg_f.get_grade(l.narrator_id, l.domain) for l in repair_chain.links]
transforms_f = [l.transform_type for l in repair_chain.links]

# Without corroboration: WEAK destructive creates permanent DAIF floor
cg_f_no_corr = grade_chain(grades_f, transforms_f, is_complete=True, corroboration_support=False)
check("F1. WEAK destructive → DAIF (no corroboration)",
      cg_f_no_corr == ChainGrade.DAIF, f"got {cg_f_no_corr.value}")

# With corroboration: RELIABLE generative can repair the floor
cg_f_corr = grade_chain(grades_f, transforms_f, is_complete=True, corroboration_support=True)
check("F2. With corroboration → generative REPAIRS to SAHIH",
      cg_f_corr == ChainGrade.SAHIH, f"got {cg_f_corr.value}")
note("   Corroboration flips 'destructive WEAK → permanent floor' into 'generative repairs'.")


# ═══════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("G. CORROBORATION: 2 independent HASAN chains → upgrade")
print(SEP)

# CorroborationEngine evaluates a claim against existing chains
engine = CorroborationEngine()

corr_result = engine.evaluate(
    claim_text="momentum is mass times velocity",
    base_chain_grade=ChainGrade.DAIF,
    base_narrators=["openstax_v3", "pdf_scraper_a", "ingest_model_a"],
    all_chains=[
        {
            "claim_text": "momentum is mass times velocity",
            "chain_grade": "hasan",
            "narrator_ids": ["crowell_lm", "pdf_scraper_b", "ingest_model_b"],
            "source": "crowell",
        },
        {
            "claim_text": "momentum is mass times velocity",
            "chain_grade": "hasan",
            "narrator_ids": ["wikisource", "parser_v2", "ingest_model_c"],
            "source": "wiki",
        },
    ],
    narrator_metadata={},
)
check("G1. 2 independent HASAN corroboration → fires upgrade",
      corr_result.upgraded, f"reason: {corr_result.reason}")
check("G2. DAIF → HASAN (not SAHIH — cap)",
      corr_result.upgraded_grade == ChainGrade.HASAN,
      f"got {corr_result.upgraded_grade.value}")
check("G3. Effective weight > 1.0",
      corr_result.effective_weight > 1.0,
      f"weight={corr_result.effective_weight:.2f}")


# ═══════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("H. CORROBORATION: same model family → NO upgrade (madār)")
print(SEP)

# All three chains use GPT-4 variants → not truly independent
madar_result = engine.evaluate(
    claim_text="momentum is mass times velocity",
    base_chain_grade=ChainGrade.DAIF,
    base_narrators=["source_A", "model_gpt4"],
    all_chains=[
        {"claim_text": "momentum is mass times velocity",
         "chain_grade": "hasan",
         "narrator_ids": ["source_B", "model_gpt4o"], "source": ""},
        {"claim_text": "momentum is mass times velocity",
         "chain_grade": "hasan",
         "narrator_ids": ["source_C", "model_gpt4_turbo"], "source": ""},
    ],
    narrator_metadata={
        "model_gpt4": {"model_family": "gpt-4"},
        "model_gpt4o": {"model_family": "gpt-4"},
        "model_gpt4_turbo": {"model_family": "gpt-4"},
    },
)
check("H1. Same model family (gpt-4) → NO upgrade (madār detected)",
      not madar_result.upgraded,
      f"independent={madar_result.independent_chains}")
note("   Naive set-disjointness would say 'independent'. Madār detection catches this.")


# ═══════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("I. VERSION BUMP → UNGRADED")
print(SEP)

reg_ver = Registry()
reg_ver.register("ingest_model_a", "physics", grade=NarratorGrade.RELIABLE,
                 model_version="v1")
check("I1. Before bump: RELIABLE",
      reg_ver.get_grade("ingest_model_a", "physics") == NarratorGrade.RELIABLE)

reg_ver.bump_version("ingest_model_a", "physics", "v2")
check("I2. After bump: UNGRADED",
      reg_ver.get_grade("ingest_model_a", "physics") == NarratorGrade.UNGRADED)

# Chain with bumped narrator → HASAN (UNGRADED caps)
bumped_chain = Chain([
    ChainLinkSpec("openstax_v3", 0, transform_type=TransformType.PASS_THROUGH, domain="physics"),
    ChainLinkSpec("pdf_scraper_a", 1, transform_type=TransformType.PASS_THROUGH, domain="physics"),
    ChainLinkSpec("ingest_model_a", 2, transform_type=TransformType.GENERATIVE, domain="physics"),
])
reg_ver.register("openstax_v3", "physics", grade=NarratorGrade.RELIABLE)
reg_ver.register("pdf_scraper_a", "physics", grade=NarratorGrade.RELIABLE)
grades_ver = [reg_ver.get_grade(l.narrator_id, l.domain) for l in bumped_chain.links]
cg_ver = grade_chain(grades_ver, [l.transform_type for l in bumped_chain.links], is_complete=True)
check("I3. Chain with bumped UNGRADED → HASAN (cap)",
      cg_ver == ChainGrade.HASAN, f"got {cg_ver.value}")
note("   Paper §4.2: version drift is a new narrator, not inherited reputation.")


# ═══════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("J. BAYESIAN EVIDENCE PROGRESSION")
print(SEP)

bayes_reg = Registry()
bayes_reg.register("test_model", "physics", grade=NarratorGrade.UNGRADED)

# Cold start: UNGRADED
check("J1. Fresh narrator → UNGRADED",
      bayes_reg.get_grade("test_model", "physics") == NarratorGrade.UNGRADED)

# 1 TADIL → Beta(2,1) mean=0.67 → WEAK
g1 = bayes_reg.record_evidence("test_model", "physics",
                               EvidenceType.EVAL_HARNESS, EvidenceAction.TADIL, "OK")
check("J2. 1 TADIL → WEAK (Beta(2,1) mean=0.67, NOT RELIABLE)",
      g1 == NarratorGrade.WEAK, f"got {g1.value}")

# 5 total TADIL → Beta(6,1) mean=0.857 → ACCEPTABLE
for _ in range(4):
    bayes_reg.record_evidence("test_model", "physics",
                              EvidenceType.CORROBORATION_OUTCOME, EvidenceAction.TADIL, "OK")
g2 = bayes_reg.get_grade("test_model", "physics")
check("J3. 5 TADIL → ACCEPTABLE (Beta(6,1) mean=0.86 ≥ 0.75)",
      g2 == NarratorGrade.ACCEPTABLE, f"got {g2.value}")

# 10 total TADIL → Beta(11,1) mean=0.917 → RELIABLE
for _ in range(5):
    bayes_reg.record_evidence("test_model", "physics",
                              EvidenceType.CORROBORATION_OUTCOME, EvidenceAction.TADIL, "OK")
g3 = bayes_reg.get_grade("test_model", "physics")
check("J4. 10 TADIL → RELIABLE (Beta(11,1) mean=0.92 ≥ 0.90)",
      g3 == NarratorGrade.RELIABLE, f"got {g3.value}")

# 3 JARH → Beta(11,4) mean=0.733 < 0.75 → WEAK
for _ in range(3):
    bayes_reg.record_evidence("test_model", "physics",
                              EvidenceType.POST_HOC_AUDIT, EvidenceAction.JARH, "Error")
g4 = bayes_reg.get_grade("test_model", "physics")
check("J5. 3 JARH → falls to WEAK (Beta(11,4) mean=0.73 < 0.75)",
      g4 == NarratorGrade.WEAK, f"got {g4.value}")

# 14 total JARH → Beta(11,15) mean=0.423 < 0.50 → REJECTED
for _ in range(11):
    bayes_reg.record_evidence("test_model", "physics",
                              EvidenceType.POST_HOC_AUDIT, EvidenceAction.JARH, "Error")
g5 = bayes_reg.get_grade("test_model", "physics")
check("J6. 14 JARH → REJECTED (Beta(11,15) mean=0.42 < 0.50)",
      g5 == NarratorGrade.REJECTED, f"got {g5.value}")
note("   Bayesian: continuous Beta posterior, calibrated grade thresholds.")


# ═══════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("K. DECISION MATRIX — every chain×content combination")
print(SEP)

matrix_tests = [
    (ChainGrade.SAHIH, ContentVerdict.CONSISTENT, Action.SERVE, "Serve + cache — best case"),
    (ChainGrade.SAHIH, ContentVerdict.CONTRADICTION, Action.REVIEW, "ʿIlal signal — highest value"),
    (ChainGrade.SAHIH, ContentVerdict.UNVERIFIABLE, Action.SERVE_WITH_CAVEAT, "Serve w/ confidence caveat"),
    (ChainGrade.HASAN, ContentVerdict.CONSISTENT, Action.SERVE_WITH_CAVEAT, "Serve w/ caveat, seek corrob."),
    (ChainGrade.HASAN, ContentVerdict.CONTRADICTION, Action.REVIEW, "Hold, do not serve"),
    (ChainGrade.HASAN, ContentVerdict.UNVERIFIABLE, Action.REVIEW, "Hold, do not serve"),
    (ChainGrade.DAIF, ContentVerdict.CONSISTENT, Action.REVIEW, "Seek corroboration first"),
    (ChainGrade.DAIF, ContentVerdict.CONTRADICTION, Action.QUARANTINE, "Quarantine claim"),
    (ChainGrade.DAIF, ContentVerdict.UNVERIFIABLE, Action.REVIEW, "Hold for review"),
    (ChainGrade.MAWDU, ContentVerdict.CONSISTENT, Action.REJECT_AND_QUARANTINE_NARRATOR, "Contain narrator"),
    (ChainGrade.MAWDU, ContentVerdict.CONTRADICTION, Action.REJECT_AND_QUARANTINE_NARRATOR, "Contain narrator"),
    (ChainGrade.MAWDU, ContentVerdict.UNVERIFIABLE, Action.REJECT_AND_QUARANTINE_NARRATOR, "Contain narrator"),
]

for cg, cv, expected, desc in matrix_tests:
    actual = decide(cg, cv)
    check(f"K. {cg.value:6s} × {cv.value:15s} → {expected.value:30s}",
          actual == expected, desc if actual != expected else "")


# ═══════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("L. STALE GRADE RECOVERY (evidence after version bump)")
print(SEP)

recov_reg = Registry()
recov_reg.register("recovery_model", "physics", grade=NarratorGrade.RELIABLE)

# Bump → UNGRADED
recov_reg.bump_version("recovery_model", "physics", "v2")
check("L1. After bump: UNGRADED",
      recov_reg.get_grade("recovery_model", "physics") == NarratorGrade.UNGRADED)

# Give sustained evidence → should recover
for i in range(8):
    recov_reg.record_evidence("recovery_model", "physics",
                              EvidenceType.CORROBORATION_OUTCOME, EvidenceAction.TADIL, f"v2-ok-{i}")
g = recov_reg.get_grade("recovery_model", "physics")
check("L2. 8 TADIL after bump → RELIABLE (Beta(9,1) mean=0.90)",
      g == NarratorGrade.RELIABLE, f"got {g.value}")


# ═══════════════════════════════════════════════════════════════════
elapsed = time.time() - _start
passed = sum(1 for _, ok, _ in results if ok)
total = len(results)

print(f"\n{SEP}")
print(f"DEEP-DIVE RESULTS: {passed}/{total} passed in {elapsed:.1f}s")
print(SEP)

if passed < total:
    for name, ok, detail in results:
        if not ok:
            print(f"  {FAIL} {name}  → {detail}")
    sys.exit(1)
else:
    print(f"""
{PASS} ALL {total} CHECKS PASSED

Observations from the deep-dive:

1. SAHIH is rare. It requires ALL narrators at RELIABLE.
   In practice, any scraper/model UNGRADED caps you at HASAN.

2. Corroboration can rescue a DAIF claim to HASAN — but never SAHIH.
   The cap is deliberate (paper §4.3): corroboration can't manufacture
   sound-tier trust from independently weak chains.

3. Madār detection catches correlated chains that naive set-disjointness
   would miss. Same model family (gpt-4 → gpt-4o) = not independent.

4. Bayesian prior provides continuous confidence. A fresh narrator doesn't
   jump to RELIABLE after 1 TADIL — it goes to WEAK (Beta(2,1) mean=0.67).
   Threshold policy would still have it UNGRADED until 5 events.

5. The destructive→generative repair mechanic is the most interesting:
   a WEAK destructive link creates a permanent DAIF floor, but a
   RELIABLE generative link WITH corroboration can repair it to SAHIH.
   Without corroboration, it stays DAIF forever.

6. Version bumps reset to UNGRADED — but sustained evidence can rebuild.
   Recovery from UNGRADED→ACCEPTABLE took 8 TADIL events.

7. REJECTED/MaWDU is the nuclear option — all 3 content verdict cells
   map to REJECT_AND_QUARANTINE_NARRATOR. Active containment, no exceptions.

8. The decision matrix is deterministic. For any (chain_grade, content_verdict)
   pair, the action is always the same. Human reviewers are the only way
   out of REVIEW and QUARANTINE states.
""")
