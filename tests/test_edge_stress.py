"""Edge-case and stress-test suite for ISNAD.

Tests:
  EDGE 1: Duplicate claim re-ingestion (store_claim upsert fix)
  EDGE 2: Empty chain, zero links, null narrator
  EDGE 3: Rapid grade oscillation (jarh-tadil-jarh-tadil-...)
  EDGE 4: Corroboration with 50 claims, mixed independence
  EDGE 5: Policy swap mid-session (bayesian -> threshold -> bayesian)
  EDGE 6: Narrator with massive evidence log (1000 entries)
  EDGE 7: Chain with 100 links (deepest-link test)
  EDGE 8: Mixed domain claims + domain-specific grading
  EDGE 9: Rapid Fire: 200 claims in sequence
  EDGE 10: Corroboration with cached metadata (madar edge)
  EDGE 11: Boundary: every grade tier transition
"""

import os
import sys
import time

os.environ["ISNAD_DATABASE_URL"] = "sqlite:///data/isnad_edge_stress.db"
os.environ.pop("ISNAD_POLICY", None)

from isnad.storage.sqlalchemy import drop_db, get_session, init_db, reset_engine

reset_engine()
drop_db("sqlite:///data/isnad_edge_stress.db")
init_db("sqlite:///data/isnad_edge_stress.db")

from isnad.core.chain import Chain, ChainLinkSpec, store_claim
from isnad.core.corroboration import CorroborationEngine, SharedLineageDetector
from isnad.core.grading import grade_chain
from isnad.core.registry import BayesianTransitionPolicy, Registry, ThresholdTransitionPolicy
from isnad.types import (
    ChainGrade,
    EvidenceAction,
    EvidenceType,
    NarratorGrade,
    TransformType,
)

SEP = "=" * 64
PASS = "✅"
FAIL = "❌"
results: list[tuple[str, bool, str]] = []
_start = time.time()


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((name, condition, detail))
    icon = PASS if condition else FAIL
    extra = f"  -> {detail}" if detail else ""
    print(f"  {icon} {name}{extra}")


# ===================================================================
print(f"\n{SEP}")
print("EDGE 1 -- DUPLICATE CLAIM RE-INGESTION (was identity-map bug)")
print(SEP)

with get_session() as session:
    chain1 = Chain([ChainLinkSpec("src", 0, domain="physics")])
    c1 = store_claim(session, "F = ma", "physics/intro", chain1, chain_grade="hasan")
    check("First store -> OK", c1 is not None)

    # Re-store same text (was the bug)
    chain2 = Chain(
        [ChainLinkSpec("src", 0, domain="physics"), ChainLinkSpec("model-v2", 1, domain="physics")]
    )
    try:
        c2 = store_claim(session, "F = ma", "physics/intro", chain2, chain_grade="sahih")
        check("Re-store same text -> NO crash", True)
        check("Updated chain has 2 links", len(c2.links) == 2, f"got {len(c2.links)}")
    except Exception as e:
        check("Re-store same text -> NO crash", False, str(e)[:80])

    # Third re-store with case variant
    chain3 = Chain([ChainLinkSpec("source:A", 0)])
    try:
        c3 = store_claim(session, "F = MA", "physics/summary", chain3)
        check("Re-store case-variant -> NO crash", True, f"links={len(c3.links)}")
    except Exception as e:
        check("Re-store case-variant -> NO crash", False, str(e)[:80])

    session.rollback()

# Test via API
from fastapi.testclient import TestClient

from isnad.api.app import app
from isnad.api.endpoints.claims import _app_state

reset_engine()
drop_db("sqlite:///data/isnad_edge_stress.db")
init_db("sqlite:///data/isnad_edge_stress.db")
_app_state.claims.clear()
_app_state._corroboration_index.clear()

client = TestClient(app)

r1 = client.post(
    "/v1/claims",
    json={
        "claim_text": "Newton second law",
        "domain": "physics",
        "chain": [{"narrator_id": "source:A", "domain": "physics"}],
    },
    headers={"X-API-Key": "isnad-admin"},
)
check("API first submit -> 200", r1.status_code == 200)

r2 = client.post(
    "/v1/claims",
    json={
        "claim_text": "Newton second law",
        "domain": "physics",
        "chain": [{"narrator_id": "source:B", "domain": "physics"}],
    },
    headers={"X-API-Key": "isnad-admin"},
)
check(
    "API re-submit same text -> 200 (was crash)", r2.status_code == 200, f"status={r2.status_code}"
)


# ===================================================================
print(f"\n{SEP}")
print("EDGE 2 -- EMPTY CHAINS, ZERO LINKS, MISSING NARRATORS")
print(SEP)

cg_empty = grade_chain([], [], is_complete=True)
check("Empty chain -> DAIF", cg_empty == ChainGrade.DAIF, f"got {cg_empty.value}")

cg_incomplete = grade_chain(
    [NarratorGrade.RELIABLE],
    [TransformType.PASS_THROUGH],
    is_complete=False,
)
check("Single-link incomplete -> DAIF", cg_incomplete == ChainGrade.DAIF)

cg_unknown = grade_chain(
    [NarratorGrade.UNGRADED, NarratorGrade.RELIABLE],
    [TransformType.PASS_THROUGH, TransformType.PASS_THROUGH],
    is_complete=True,
)
check(
    "UNGRADED + RELIABLE -> HASAN (cap)", cg_unknown == ChainGrade.HASAN, f"got {cg_unknown.value}"
)

r = client.post(
    "/v1/claims",
    json={
        "claim_text": "test unknown narrator",
        "chain": [{"narrator_id": "nonexistent_12345", "domain": "nowhere"}],
    },
    headers={"X-API-Key": "isnad-admin"},
)
check("API claim with unknown narrator -> 200", r.status_code == 200)
check(
    "Grade is not empty (defaults to UNGRADED->HASAN cap)",
    r.json()["chain_grade"] != "",
    f"grade={r.json()['chain_grade']}",
)


# ===================================================================
print(f"\n{SEP}")
print("EDGE 3 -- RAPID GRADE OSCILLATION (jarh<->tadil ping-pong)")
print(SEP)

reg_osc = Registry()
reg_osc.register("pingpong", "physics")
grades_seen: list[NarratorGrade] = []

for i in range(20):
    action = EvidenceAction.JARH if i % 2 == 0 else EvidenceAction.TADIL
    g = reg_osc.record_evidence(
        "pingpong", "physics", EvidenceType.POST_HOC_AUDIT, action, f"event {i}"
    )
    grades_seen.append(g)

final = reg_osc.get_grade("pingpong", "physics")
check(
    "Ping-pong converges to WEAK (Beta(11,11) mean=0.5)",
    final == NarratorGrade.WEAK,
    f"got {final.value}",
)
check("No crash during 20 rapid transitions", len(grades_seen) == 20)


# ===================================================================
print(f"\n{SEP}")
print("EDGE 4 -- CORROBORATION WITH 50 CLAIMS (mixed independence)")
print(SEP)

engine = CorroborationEngine(correlation_detector=SharedLineageDetector())

all_chains: list[dict] = []
for i in range(50):
    if i < 10:
        claim_text = "force equals mass times acceleration"
        chain_grade = "hasan"
        narrator_ids = [f"src_corroborate_{i}", f"model_{i}"]
    else:
        claim_text = f"other claim about concept {i}"
        chain_grade = "daif"
        narrator_ids = [f"src_other_{i}"]
    all_chains.append(
        {
            "claim_text": claim_text,
            "chain_grade": chain_grade,
            "narrator_ids": narrator_ids,
            "source": f"page_{i}",
        }
    )

result_50 = engine.evaluate(
    claim_text="force equals mass times acceleration",
    base_chain_grade=ChainGrade.DAIF,
    base_narrators=["base_src_A", "base_model_Z"],
    all_chains=all_chains,
    narrator_metadata={},
)
check(
    "50 claims, 10 corroborating -> upgrade fires",
    result_50.upgraded,
    f"corr={result_50.corroborating_chains}, ind={result_50.independent_chains}",
)


# ===================================================================
print(f"\n{SEP}")
print("EDGE 5 -- POLICY SWAP MID-SESSION")
print(SEP)

# Bayesian: fresh narrator, 1 JARH -> Beta(1,2) mean=0.33 -> REJECTED
reg_swap = Registry(transition_policy=BayesianTransitionPolicy())
reg_swap.register("swapper", "physics")
g1 = reg_swap.record_evidence(
    "swapper", "physics", EvidenceType.POST_HOC_AUDIT, EvidenceAction.JARH
)
check(
    "Bayesian: 1 JARH from cold start -> REJECTED (Beta(1,2) mean=0.33)",
    g1 == NarratorGrade.REJECTED,
    f"got {g1.value}",
)

# Swap to threshold mid-stream
reg_swap.transition_policy = ThresholdTransitionPolicy()
reg_swap.register("swapper2", "physics", grade=NarratorGrade.RELIABLE)
for _ in range(3):
    reg_swap.record_evidence(
        "swapper2", "physics", EvidenceType.POST_HOC_AUDIT, EvidenceAction.JARH
    )
g2 = reg_swap.get_grade("swapper2", "physics")
check(
    "Threshold after swap: 3 JARH -> ACCEPTABLE", g2 == NarratorGrade.ACCEPTABLE, f"got {g2.value}"
)

# Swap back to fresh Bayesian instance
reg_swap.transition_policy = BayesianTransitionPolicy()
# "swapper" has 1 JARH in evidence log; new policy re-evaluates from log
g3 = reg_swap.get_grade("swapper", "physics")
check(
    "Bayesian fresh instance: re-evaluates from evidence log",
    g3 == NarratorGrade.REJECTED,
    f"got {g3.value}",
)


# ===================================================================
print(f"\n{SEP}")
print("EDGE 6 -- NARRATOR WITH MASSIVE EVIDENCE LOG (1000 entries)")
print(SEP)

reg_massive = Registry()
reg_massive.register("heavy", "physics")
t0 = time.time()
for i in range(1000):
    action = EvidenceAction.TADIL if i < 700 else EvidenceAction.JARH
    reg_massive.record_evidence("heavy", "physics", EvidenceType.EVAL_HARNESS, action, f"ev-{i}")
elapsed = time.time() - t0
final_grade = reg_massive.get_grade("heavy", "physics")
narrator = reg_massive.get("heavy", "physics")
evidence_count = len(narrator.evidence_log) if narrator else 0

check("1000 evidence entries stored", evidence_count == 1000, f"got {evidence_count}")
# 700 TADIL + 300 JARH -> Beta(701,301) mean=0.6996 < 0.75 -> WEAK
check(
    "700 TADIL + 300 JARH -> WEAK (Beta(701,301) mean=0.70 < 0.75)",
    final_grade == NarratorGrade.WEAK,
    f"got {final_grade.value}",
)
check("1000 entries processed in < 2s", elapsed < 2.0, f"{elapsed:.2f}s")


# ===================================================================
print(f"\n{SEP}")
print("EDGE 7 -- DEEP CHAIN (100 links)")
print(SEP)

deep_links = [
    ChainLinkSpec(f"step-{i}", i, domain="physics", transform_type=TransformType.PASS_THROUGH)
    for i in range(100)
]
deep_chain = Chain(deep_links)
check("100-link chain is complete", deep_chain.is_complete)
check("100-link chain has 100 narrator_ids", len(deep_chain.narrator_ids) == 100)

deep_grades = [NarratorGrade.RELIABLE] * 99 + [NarratorGrade.WEAK]
deep_transforms = [TransformType.PASS_THROUGH] * 100
cg_deep = grade_chain(deep_grades, deep_transforms, is_complete=True)
check(
    "99 RELIABLE + 1 WEAK -> DAIF (100 links deep)",
    cg_deep == ChainGrade.DAIF,
    f"got {cg_deep.value}",
)

with get_session() as session:
    stored = store_claim(session, "deep chain test", "test/deep", deep_chain)
    check("Deep chain stored", stored is not None)
    check("Deep chain links persisted", len(stored.links) == 100, f"got {len(stored.links)}")
    session.rollback()


# ===================================================================
print(f"\n{SEP}")
print("EDGE 8 -- MIXED DOMAIN GRADING")
print(SEP)

reg_dom = Registry()
reg_dom.register("multi-model", "physics", grade=NarratorGrade.RELIABLE)
reg_dom.register("multi-model", "history", grade=NarratorGrade.WEAK)
reg_dom.register("multi-model", "chemistry", grade=NarratorGrade.ACCEPTABLE)
reg_dom.register("multi-model", "biology", grade=NarratorGrade.UNGRADED)

check(
    "Same narrator, physics=RELIABLE",
    reg_dom.get_grade("multi-model", "physics") == NarratorGrade.RELIABLE,
)
check(
    "Same narrator, history=WEAK", reg_dom.get_grade("multi-model", "history") == NarratorGrade.WEAK
)
check(
    "Same narrator, chemistry=ACCEPTABLE",
    reg_dom.get_grade("multi-model", "chemistry") == NarratorGrade.ACCEPTABLE,
)
check(
    "Same narrator, biology=UNGRADED",
    reg_dom.get_grade("multi-model", "biology") == NarratorGrade.UNGRADED,
)

cg_mixed = grade_chain(
    [NarratorGrade.RELIABLE, NarratorGrade.WEAK, NarratorGrade.ACCEPTABLE],
    [TransformType.PASS_THROUGH, TransformType.DESTRUCTIVE, TransformType.GENERATIVE],
    is_complete=True,
)
check("Mixed-domain chain: weak link -> DAIF", cg_mixed == ChainGrade.DAIF, f"got {cg_mixed.value}")


# ===================================================================
print(f"\n{SEP}")
print("STRESS 9 -- RAPID FIRE: 200 claims in sequence")
print(SEP)

reset_engine()
drop_db("sqlite:///data/isnad_edge_stress.db")
init_db("sqlite:///data/isnad_edge_stress.db")
_app_state.claims.clear()
_app_state._corroboration_index.clear()

t0 = time.time()
success = 0
fail = 0
for i in range(200):
    r = client.post(
        "/v1/claims",
        json={
            "claim_text": f"stress claim number {i}",
            "domain": "stress_test",
            "chain": [{"narrator_id": f"stress_narrator_{i % 20}", "domain": "stress_test"}],
        },
        headers={"X-API-Key": "isnad-admin"},
    )
    if r.status_code == 200:
        success += 1
    else:
        fail += 1
elapsed = time.time() - t0

check(
    f"200 claims: {success} OK, {fail} failed",
    fail == 0,
    f"in {elapsed:.1f}s ({200 / elapsed:.0f} claims/s)",
)
check("All 200 in < 10s", elapsed < 10.0, f"{elapsed:.1f}s")

r = client.get("/v1/claims?domain=stress_test&limit=250")
list_data = r.json()
check("Claims list shows all 200", list_data["total"] == 200, f"total={list_data['total']}")


# ===================================================================
print(f"\n{SEP}")
print("EDGE 10 -- CORROBORATION WITH MADAR EDGE CASES")
print(SEP)

detector = SharedLineageDetector()
engine2 = CorroborationEngine(correlation_detector=detector)

# Different model families -> independent
result_mix = engine2.evaluate(
    claim_text="the earth orbits the sun",
    base_chain_grade=ChainGrade.DAIF,
    base_narrators=["claude_opus"],
    all_chains=[
        {
            "claim_text": "the earth orbits the sun",
            "chain_grade": "hasan",
            "narrator_ids": ["gpt4"],
            "source": "",
        },
        {
            "claim_text": "the earth orbits the sun",
            "chain_grade": "hasan",
            "narrator_ids": ["gemini_pro"],
            "source": "",
        },
    ],
    narrator_metadata={
        "claude_opus": {"model_family": "claude"},
        "gpt4": {"model_family": "gpt-4"},
        "gemini_pro": {"model_family": "gemini"},
    },
)
check(
    "Different model families -> independent -> upgrade",
    result_mix.upgraded,
    f"ind={result_mix.independent_chains}, reason={result_mix.reason}",
)

# Same upstream source -> correlated
result_same_source = engine2.evaluate(
    claim_text="water boils at 100 celsius",
    base_chain_grade=ChainGrade.DAIF,
    base_narrators=["scraper_wiki_v1"],
    all_chains=[
        {
            "claim_text": "water boils at 100 celsius",
            "chain_grade": "hasan",
            "narrator_ids": ["scraper_wiki_v2"],
            "source": "",
        },
        {
            "claim_text": "water boils at 100 celsius",
            "chain_grade": "hasan",
            "narrator_ids": ["scraper_britannica"],
            "source": "",
        },
    ],
    narrator_metadata={
        "scraper_wiki_v1": {"upstream_source": "wikipedia.org"},
        "scraper_wiki_v2": {"upstream_source": "wikipedia.org"},
        "scraper_britannica": {"upstream_source": "britannica.com"},
    },
)
check(
    "Shared upstream source -> partial discount",
    not result_same_source.upgraded,
    f"ind={result_same_source.independent_chains}, reason={result_same_source.reason}",
)

# No metadata -> assume independent
result_no_meta = engine2.evaluate(
    claim_text="speed of light is constant",
    base_chain_grade=ChainGrade.DAIF,
    base_narrators=["a", "b"],
    all_chains=[
        {
            "claim_text": "speed of light is constant",
            "chain_grade": "hasan",
            "narrator_ids": ["c", "d"],
            "source": "",
        },
        {
            "claim_text": "speed of light is constant",
            "chain_grade": "hasan",
            "narrator_ids": ["e", "f"],
            "source": "",
        },
    ],
    narrator_metadata={},
)
check(
    "No metadata -> assumed independent -> upgrade",
    result_no_meta.upgraded,
    f"ind={result_no_meta.independent_chains}",
)

# Partial metadata
result_partial_meta = engine2.evaluate(
    claim_text="newton discovered gravity",
    base_chain_grade=ChainGrade.DAIF,
    base_narrators=["historian_1"],
    all_chains=[
        {
            "claim_text": "newton discovered gravity",
            "chain_grade": "hasan",
            "narrator_ids": ["historian_2"],
            "source": "",
        },
        {
            "claim_text": "newton discovered gravity",
            "chain_grade": "hasan",
            "narrator_ids": ["historian_3"],
            "source": "",
        },
    ],
    narrator_metadata={"historian_1": {"model_family": "gpt-4"}},
)
check(
    "Partial metadata -> independent (no shared lineage detected)",
    result_partial_meta.upgraded,
    f"ind={result_partial_meta.independent_chains}",
)


# ===================================================================
print(f"\n{SEP}")
print("EDGE 11 -- BOUNDARY: EVERY GRADE TIER TRANSITION")
print(SEP)

reg_edge = Registry()
reg_edge.register("edge_narrator", "physics", grade=NarratorGrade.UNGRADED)

# UNGRADED -> WEAK (1 TADIL: Beta(2,1) mean=0.67)
g1 = reg_edge.record_evidence(
    "edge_narrator", "physics", EvidenceType.EVAL_HARNESS, EvidenceAction.TADIL
)
check("UNGRADED -> WEAK (1 TADIL)", g1 == NarratorGrade.WEAK, f"got {g1.value}")

# WEAK -> ACCEPTABLE (need 5 TADIL total: Beta(6,1) mean=0.857)
for i in range(4):
    reg_edge.record_evidence(
        "edge_narrator", "physics", EvidenceType.CORROBORATION_OUTCOME, EvidenceAction.TADIL
    )
g2 = reg_edge.get_grade("edge_narrator", "physics")
check("WEAK -> ACCEPTABLE (5 TADIL total)", g2 == NarratorGrade.ACCEPTABLE, f"got {g2.value}")

# ACCEPTABLE -> RELIABLE (need 10 TADIL total: Beta(11,1) mean=0.917)
for i in range(5):
    reg_edge.record_evidence(
        "edge_narrator", "physics", EvidenceType.CORROBORATION_OUTCOME, EvidenceAction.TADIL
    )
g3 = reg_edge.get_grade("edge_narrator", "physics")
check("ACCEPTABLE -> RELIABLE (10 TADIL total)", g3 == NarratorGrade.RELIABLE, f"got {g3.value}")

# RELIABLE -> WEAK (3 JARH: Beta(11,4) mean=0.733 < 0.75)
for i in range(3):
    reg_edge.record_evidence(
        "edge_narrator", "physics", EvidenceType.POST_HOC_AUDIT, EvidenceAction.JARH
    )
g4 = reg_edge.get_grade("edge_narrator", "physics")
check(
    "RELIABLE -> WEAK (3 JARH: Beta(11,4) mean=0.73 < 0.75)",
    g4 == NarratorGrade.WEAK,
    f"got {g4.value}",
)

# WEAK -> REJECTED (need mean < 0.50: 11 more JARH = Beta(11,15) mean=0.423)
for i in range(11):
    reg_edge.record_evidence(
        "edge_narrator", "physics", EvidenceType.POST_HOC_AUDIT, EvidenceAction.JARH
    )
g5 = reg_edge.get_grade("edge_narrator", "physics")
check(
    "WEAK -> REJECTED (14 JARH total: Beta(11,15) mean=0.42)",
    g5 == NarratorGrade.REJECTED,
    f"got {g5.value}",
)


# ===================================================================
elapsed = time.time() - _start
passed = sum(1 for _, ok, _ in results if ok)
total = len(results)

print(f"\n{SEP}")
print(f"EDGE + STRESS RESULTS: {passed}/{total} passed in {elapsed:.1f}s")
print(SEP)

if passed < total:
    print(f"\n{FAIL} FAILURES:")
    for name, ok, detail in results:
        if not ok:
            print(f"  {FAIL} {name}  -> {detail}")
    sys.exit(1)
else:
    print(f"\n{PASS} ALL {total} EDGE + STRESS CHECKS PASSED\n")
# ruff: noqa: E402
