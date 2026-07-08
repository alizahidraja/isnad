"""Integration verification: Bayesian policy + corroboration + madār detection + DB persistence.

Runs end-to-end checks that each new component actually fires.
"""

import os
import sys

# Ensure clean test DB
os.environ["ISNAD_DATABASE_URL"] = "sqlite:///data/isnad_verify.db"

from isnad.storage.sqlalchemy import drop_db, init_db, reset_engine

reset_engine()
drop_db("sqlite:///data/isnad_verify.db")
init_db("sqlite:///data/isnad_verify.db")

from isnad.core.corroboration import CorroborationEngine, SharedLineageDetector
from isnad.core.grading import grade_chain
from isnad.core.registry import (
    BayesianTransitionPolicy,
    Registry,
    RegistryDB,
    ThresholdTransitionPolicy,
)
from isnad.types import (
    ChainGrade,
    ContentVerdict,
    EvidenceAction,
    EvidenceType,
    NarratorGrade,
    TransformType,
)

SEP = "─" * 60
PASS = "✅"
FAIL = "❌"

results: list[tuple[str, bool]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((name, condition))
    icon = PASS if condition else FAIL
    extra = f"  → {detail}" if detail else ""
    print(f"  {icon} {name}{extra}")


# ═══════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("1. BAYESIAN ENGINE — default policy + evidence-driven grading")
print(SEP)

# Default Registry uses BayesianTransitionPolicy
reg = Registry()
check("Registry() default is BayesianTransitionPolicy",
      isinstance(reg.transition_policy, BayesianTransitionPolicy))

# Threshold fallback: explicit
reg_t = Registry(transition_policy=ThresholdTransitionPolicy())
check("ThresholdTransitionPolicy remains as named fallback",
      isinstance(reg_t.transition_policy, ThresholdTransitionPolicy))

# Bayesian: 1 positive → WEAK (Beta(2,1), mean=0.67)
g1 = reg.record_evidence("bayes_test", "physics",
                         EvidenceType.EVAL_HARNESS, EvidenceAction.TADIL, "Pass 1")
check("1 TADIL → WEAK (not RELIABLE)", g1 == NarratorGrade.WEAK,
      f"got {g1.value}")

# Bayesian: 3 adverse → REJECTED (Beta(1,4), mean=0.20)
reg2 = Registry()
for i in range(3):
    reg2.record_evidence("bad_model", "physics",
                         EvidenceType.POST_HOC_AUDIT, EvidenceAction.JARH, f"Fail {i}")
g3 = reg2.get_grade("bad_model", "physics")
check("3 JARH → REJECTED (Bayesian dominates fast)", g3 == NarratorGrade.REJECTED,
      f"got {g3.value}")

# Bayesian: sustained → ACCEPTABLE (5 TADIL + 1 JARH)
reg3 = Registry()
for i in range(5):
    reg3.record_evidence("good_model", "physics",
                         EvidenceType.CORROBORATION_OUTCOME, EvidenceAction.TADIL, f"OK {i}")
reg3.record_evidence("good_model", "physics",
                     EvidenceType.POST_HOC_AUDIT, EvidenceAction.JARH, "minor")
g4 = reg3.get_grade("good_model", "physics")
check("5 TADIL + 1 JARH → ACCEPTABLE", g4 == NarratorGrade.ACCEPTABLE,
      f"got {g4.value}")

# Bayesian: many positives → RELIABLE
reg4 = Registry()
for i in range(10):
    reg4.record_evidence("excellent", "physics",
                         EvidenceType.CORROBORATION_OUTCOME, EvidenceAction.TADIL, f"OK {i}")
g5 = reg4.get_grade("excellent", "physics")
check("10 TADIL → RELIABLE", g5 == NarratorGrade.RELIABLE,
      f"got {g5.value}")

# Version bump still resets
reg4.bump_version("excellent", "physics", "v2")
g6 = reg4.get_grade("excellent", "physics")
check("Version bump → UNGRADED", g6 == NarratorGrade.UNGRADED,
      f"got {g6.value}")

# ISNAD_POLICY env var
os.environ["ISNAD_POLICY"] = "threshold"
from isnad.api.dependencies import _build_policy

policy_t = _build_policy()
check("ISNAD_POLICY=threshold → ThresholdTransitionPolicy",
      isinstance(policy_t, ThresholdTransitionPolicy))
os.environ["ISNAD_POLICY"] = "bayesian"
policy_b = _build_policy()
check("ISNAD_POLICY=bayesian → BayesianTransitionPolicy",
      isinstance(policy_b, BayesianTransitionPolicy))
os.environ.pop("ISNAD_POLICY", None)


# ═══════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("2. CORROBORATION ENGINE — disjoint chains + madār detection")
print(SEP)

detector = SharedLineageDetector()
engine = CorroborationEngine(correlation_detector=detector)

# Test 1: Two truly independent HASAN chains → upgrade DAIF base to HASAN
# (Cannot reach SAHIH — corroboration cap)
result1 = engine.evaluate(
    claim_text="photon momentum is h over lambda",
    base_chain_grade=ChainGrade.DAIF,
    base_narrators=["openstax_v3", "pdf_scraper_a", "ingest_model_a"],
    all_chains=[
        {"claim_text": "photon momentum is h over lambda",
         "chain_grade": "hasan",
         "narrator_ids": ["wikisource", "pdf_scraper_b", "ingest_model_b"],
         "source": "wiki"},
        {"claim_text": "photon momentum is h over lambda",
         "chain_grade": "hasan",
         "narrator_ids": ["arxiv_source", "parser_v2", "model_claude"],
         "source": "arxiv"},
    ],
    narrator_metadata={},
)
check("Two independent chains → upgrade fires", result1.upgraded,
      f"reason: {result1.reason}, independent={result1.independent_chains}")

# Test 2: Same model family → madār detection blocks upgrade
result2 = engine.evaluate(
    claim_text="energy is conserved",
    base_chain_grade=ChainGrade.DAIF,
    base_narrators=["model_gpt4"],
    all_chains=[
        {"claim_text": "energy is conserved",
         "chain_grade": "hasan",
         "narrator_ids": ["model_gpt4o"],
         "source": ""},
        {"claim_text": "energy is conserved",
         "chain_grade": "hasan",
         "narrator_ids": ["model_gpt4_turbo"],
         "source": ""},
    ],
    narrator_metadata={
        "model_gpt4": {"model_family": "gpt-4"},
        "model_gpt4o": {"model_family": "gpt-4"},
        "model_gpt4_turbo": {"model_family": "gpt-4"},
    },
)
check("Shared model family → no upgrade (madār detected)", not result2.upgraded,
      f"reason: {result2.reason}")

# Test 3: DAIF + 2 HASAN independent chains → upgrade to HASAN
result3 = engine.evaluate(
    claim_text="F equals ma",
    base_chain_grade=ChainGrade.DAIF,
    base_narrators=["source:A"],
    all_chains=[
        {"claim_text": "F equals ma", "chain_grade": "hasan",
         "narrator_ids": ["source:C"], "source": ""},
        {"claim_text": "F equals ma", "chain_grade": "hasan",
         "narrator_ids": ["source:D"], "source": ""},
    ],
    narrator_metadata={},
)
check("DAIF + 2 independent HASAN → upgraded to HASAN", result3.upgraded,
      f"got {result3.upgraded_grade.value}, reason: {result3.reason}")

# Test 4: MAWDU never upgraded
result4 = engine.evaluate(
    claim_text="poison",
    base_chain_grade=ChainGrade.MAWDU,
    base_narrators=["bad"],
    all_chains=[
        {"claim_text": "poison", "chain_grade": "sahih",
         "narrator_ids": ["good"], "source": ""},
    ],
    narrator_metadata={},
)
check("MAWDU → never upgraded", not result4.upgraded)

# Test 5: Different claims → don't match (corroboration requires same text)
result5 = engine.evaluate(
    claim_text="F equals ma",
    base_chain_grade=ChainGrade.DAIF,
    base_narrators=["src"],
    all_chains=[
        {"claim_text": "something completely different", "chain_grade": "hasan",
         "narrator_ids": ["other"], "source": ""},
    ],
    narrator_metadata={},
)
check("Different claim text → no corroboration", not result5.upgraded,
      f"corroborating chains matched: {result5.corroborating_chains}")


# ═══════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("3. DATABASE PERSISTENCE — RegistryDB loads + saves")
print(SEP)

from isnad.storage.sqlalchemy import get_session

with get_session() as session:
    rdb = RegistryDB(session=session)
    rdb.registry.register("persist_test", "physics", grade=NarratorGrade.RELIABLE)
    rdb.flush()

# New session — must reload from DB
with get_session() as session:
    rdb2 = RegistryDB(session=session)
    rdb2.load()
    grade_loaded = rdb2.registry.get_grade("persist_test", "physics")
    check("Grade survives across sessions (DB persistence)",
          grade_loaded == NarratorGrade.RELIABLE,
          f"got {grade_loaded.value}")


# ═══════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("4. CHAIN GRADING — weakest-link + completeness")
print(SEP)

cg_all_reliable = grade_chain(
    [NarratorGrade.RELIABLE, NarratorGrade.RELIABLE],
    [TransformType.PASS_THROUGH, TransformType.PASS_THROUGH],
    is_complete=True,
)
check("All RELIABLE → SAHIH", cg_all_reliable == ChainGrade.SAHIH,
      f"got {cg_all_reliable.value}")

cg_with_weak = grade_chain(
    [NarratorGrade.RELIABLE, NarratorGrade.WEAK],
    [TransformType.PASS_THROUGH, TransformType.PASS_THROUGH],
    is_complete=True,
)
check("RELIABLE + WEAK → DAIF (weakest-link)", cg_with_weak == ChainGrade.DAIF,
      f"got {cg_with_weak.value}")

cg_incomplete = grade_chain(
    [NarratorGrade.RELIABLE, NarratorGrade.RELIABLE],
    [TransformType.PASS_THROUGH, TransformType.PASS_THROUGH],
    is_complete=False,
)
check("Incomplete chain → DAIF (ittisal cap)",
      cg_incomplete == ChainGrade.DAIF, f"got {cg_incomplete.value}")


# ═══════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("5. CRITIC FALLBACK — HybridCritic gracefully degrades")
print(SEP)

from isnad.critics.embedding import EmbeddingCritic
from isnad.critics.nli import HybridCritic

# If sentence-transformers not installed, HybridCritic returns UNVERIFIABLE
hc = HybridCritic()
result_empty = hc.evaluate("test", "test", [], "physics")
check("HybridCritic empty corpus → UNVERIFIABLE",
      result_empty == ContentVerdict.UNVERIFIABLE)

# EmbeddingCritic works without deps — test with high word overlap

ec = EmbeddingCritic()
# Test 1: exact match → CONSISTENT
result_exact = ec.evaluate(
    "force equals mass times acceleration",
    "force equals mass times acceleration",
    ["force equals mass times acceleration", "momentum is mass times velocity"],
    "physics",
)
check("EmbeddingCritic exact match → CONSISTENT",
      result_exact == ContentVerdict.CONSISTENT,
      f"got {result_exact.value}")

# Test 2: contradiction detection
result_contra = ec.evaluate(
    "energy is not conserved",
    "energy is not conserved",
    ["energy is conserved in all closed systems"],
    "physics",
)
check("EmbeddingCritic negation contradiction → CONTRADICTION",
      result_contra == ContentVerdict.CONTRADICTION,
      f"got {result_contra.value}")


# ═══════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("SUMMARY")
print(SEP)

passed = sum(1 for _, ok in results if ok)
total = len(results)
for name, ok in results:
    icon = PASS if ok else FAIL
    print(f"  {icon} {name}")
print(f"\n  {passed}/{total} checks passed")

if passed == total:
    print(f"\n{PASS} ALL CHECKS PASS — system is wired correctly.")
    sys.exit(0)
else:
    print(f"\n{FAIL} {total - passed} CHECK(S) FAILED.")
    sys.exit(1)
# ruff: noqa: E402
