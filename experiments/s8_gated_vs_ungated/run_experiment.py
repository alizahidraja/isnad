"""§8 Experiment Runner — Bayesian + Corroboration + DeepSeek LLM Critic.

Self-contained: no PDFs, no 500MB models. Uses claims.json directly.
DeepSeek as content critic (fallback to stub if no API key).

Usage:
    DEEPSEEK_API_KEY=sk-... python run_experiment.py
    python run_experiment.py  # stub critic (fast, all UNVERIFIABLE)
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
from dataclasses import dataclass

_exp_dir = os.path.dirname(os.path.abspath(__file__))
_parent = os.path.dirname(os.path.dirname(_exp_dir))
sys.path.insert(0, os.path.join(_parent, "src"))

from isnad.core.chain import Chain, ChainLinkSpec
from isnad.core.grading import grade_chain
from isnad.core.decision import decide, describe_action
from isnad.core.registry import Registry
from isnad.core.corroboration import evaluate_corroboration, SharedLineageDetector
from isnad.types import (
    Action, ChainGrade, ContentVerdict, EvidenceAction, EvidenceType,
    NarratorGrade, TransformType,
)

SEP = "=" * 64


# ═══════════════════════════════════════════════════════════════════
# DeepSeek LLM Critic
# ═══════════════════════════════════════════════════════════════════

class DeepSeekCritic:
    """Content critic using DeepSeek via OpenAI-compatible API."""

    def __init__(self):
        self.api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        self.base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.available = bool(self.api_key)
        self._cache: dict[str, ContentVerdict] = {}
        self.call_count = 0

    def evaluate(self, claim_text: str, normalized: str,
                 corpus_claims: list[str], domain: str = "") -> ContentVerdict:
        if not self.available:
            # Stub: check for self-contradiction patterns
            low = normalized.lower()
            if "not conserved" in low or "decreases" in low and "increases" in low:
                return ContentVerdict.CONTRADICTION
            return ContentVerdict.UNVERIFIABLE

        cache_key = normalized[:100]
        if cache_key in self._cache:
            return self._cache[cache_key]

        prompt = (
            f"Physics claim: {normalized}\n"
            f"Answer one word: CONSISTENT, CONTRADICTION, or UNVERIFIABLE.\n"
            f"CONSISTENT = plausible physics statement.\n"
            f"CONTRADICTION = physically impossible or self-contradicting.\n"
            f"UNVERIFIABLE = need more context."
        )

        try:
            import urllib.request
            req = urllib.request.Request(
                f"{self.base_url}/v1/chat/completions",
                data=json.dumps({
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 10, "temperature": 0,
                }).encode(),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
            self.call_count += 1
            resp = urllib.request.urlopen(req, timeout=15)
            body = json.loads(resp.read())
            text = body["choices"][0]["message"]["content"].strip().upper()

            if "CONTRADICTION" in text:
                verdict = ContentVerdict.CONTRADICTION
            elif "CONSISTENT" in text:
                verdict = ContentVerdict.CONSISTENT
            else:
                verdict = ContentVerdict.UNVERIFIABLE
        except Exception:
            verdict = ContentVerdict.UNVERIFIABLE

        self._cache[cache_key] = verdict
        return verdict


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

def run() -> None:
    print(f"\n{SEP}")
    print("§8 EXPERIMENT — Bayesian + Corroboration + DeepSeek")
    print(SEP)

    # ── 1. Load claims ──────────────────────────────────────────
    print("\n[1/5] Loading claims...")
    claims_path = os.path.join(_exp_dir, "results", "claims.json")
    with open(claims_path) as f:
        all_claims = json.load(f)

    rng = random.Random(42)
    claims = rng.sample(all_claims, min(500, len(all_claims)))

    # Assign diverse chains with 8 unique narrators across 3 sources
    SOURCES = ["openstax_v3", "crowell_lm", "wikisource"]
    SCRAPERS = ["pdf_scraper_a", "pdf_scraper_b"]
    MODELS = ["ingest_model_a", "ingest_model_b", "ingest_model_c"]

    for i, c in enumerate(claims):
        src = SOURCES[i % len(SOURCES)]
        scr = SCRAPERS[i % len(SCRAPERS)]
        mod = MODELS[i % len(MODELS)]
        c["chain"] = [
            {"narrator_id": src, "step": 0, "transform_type": "pass_through", "domain": "physics"},
            {"narrator_id": scr, "step": 1, "transform_type": "destructive", "domain": "physics"},
            {"narrator_id": mod, "step": 2, "transform_type": "generative", "domain": "physics", "version": "v1"},
        ]
        c["chain_complete"] = True
        c["_narrator_ids"] = [ln["narrator_id"] for ln in c["chain"]]

    # Inject errors into 15% of claims
    ERROR_PAIRS = [
        ("force", "power"), ("mass", "weight"), ("velocity", "speed"),
        ("acceleration", "velocity"), ("energy", "entropy"),
        ("increases", "decreases"), ("conserved", "not conserved"),
        ("attractive", "repulsive"),
    ]
    n_corrupt = int(len(claims) * 0.15)
    corrupt_idx = set(rng.sample(range(len(claims)), n_corrupt))
    gt_lookup: dict[str, dict] = {}

    for i, c in enumerate(claims):
        cid = c["claim_id"]
        gt_lookup[cid] = {"corrupted": False}
        if i in corrupt_idx:
            text = c.get("text", "")
            norm = c.get("normalized", "")
            for old, new in ERROR_PAIRS:
                if old in text.lower():
                    c["text"] = text.replace(old, new).replace(old.title(), new.title())
                    c["normalized"] = norm.replace(old, new)
                    gt_lookup[cid] = {"corrupted": True, "swap": f"{old}→{new}"}
                    break

    print(f"  {len(claims)} claims, {n_corrupt} corrupted")

    # ── 2. Registry ─────────────────────────────────────────────
    print("\n[2/5] Building registry (Bayesian)...")
    reg = Registry()

    all_narrators = set()
    for c in claims:
        for nid in c["_narrator_ids"]:
            all_narrators.add(nid)

    for nid in sorted(all_narrators):
        if nid in SOURCES:
            reg.register(nid, "physics", grade=NarratorGrade.RELIABLE)
        elif nid == "pdf_scraper_a":
            # Good scraper: ACCEPTABLE
            reg.register(nid, "physics", grade=NarratorGrade.ACCEPTABLE)
            for _ in range(5):
                reg.record_evidence(nid, "physics", EvidenceType.EVAL_HARNESS,
                                   EvidenceAction.TADIL, "Verified")
        elif nid == "pdf_scraper_b":
            # Bad scraper: REJECTED (injects errors)
            reg.register(nid, "physics", grade=NarratorGrade.UNGRADED)
            for _ in range(5):
                reg.record_evidence(nid, "physics", EvidenceType.POST_HOC_AUDIT,
                                   EvidenceAction.JARH, "Corruption detected")
        elif nid == "ingest_model_c":
            # Weak model: barely acceptable
            reg.register(nid, "physics", grade=NarratorGrade.UNGRADED)
            for _ in range(2):
                reg.record_evidence(nid, "physics", EvidenceType.CORROBORATION_OUTCOME,
                                   EvidenceAction.TADIL, "OK")
            for _ in range(3):
                reg.record_evidence(nid, "physics", EvidenceType.POST_HOC_AUDIT,
                                   EvidenceAction.JARH, "Hallucination")
        else:  # ingest_model_a, ingest_model_b: good models
            reg.register(nid, "physics", grade=NarratorGrade.UNGRADED)
            for _ in range(7):
                reg.record_evidence(nid, "physics", EvidenceType.CORROBORATION_OUTCOME,
                                   EvidenceAction.TADIL, "Corroborated")

    for nid in sorted(all_narrators):
        print(f"    {nid:22s} → {reg.get_grade(nid, 'physics').value}")

    # ── 3. Critic ───────────────────────────────────────────────
    print("\n[3/5] Initializing critic...")
    critic = DeepSeekCritic()
    if critic.available:
        print(f"  DeepSeek API ({critic.base_url})")
    else:
        print("  Stub critic (DEEPSEEK_API_KEY not set)")

    # ── 4. Grade ────────────────────────────────────────────────
    print(f"\n[4/5] Grading {len(claims)} claims...")
    t0 = time.time()
    graded: list[dict] = []
    stats: dict[str, int] = {g.value: 0 for g in ChainGrade}
    stats.update({"consistent": 0, "contradiction": 0, "unverifiable": 0,
                   "corroboration_upgrades": 0, "corroboration_checks": 0})

    for idx, claim in enumerate(claims):
        if idx % 100 == 0:
            print(f"  {idx}/{len(claims)}...")

        chain = Chain([ChainLinkSpec(
            narrator_id=ln["narrator_id"], step=ln["step"],
            version=ln.get("version", "unknown"),
            transform_type=TransformType(ln.get("transform_type", "pass_through")),
            domain=ln.get("domain", "physics"),
        ) for ln in claim.get("chain", [])])

        link_grades = [reg.get_grade(l.narrator_id, l.domain) for l in chain.links]
        cg = grade_chain(link_grades, [l.transform_type for l in chain.links],
                         is_complete=claim.get("chain_complete", True))
        cv = critic.evaluate(claim.get("text", ""), claim.get("normalized", ""),
                             [], claim.get("domain", "physics"))
        action = decide(cg, cv)

        stats[cg.value] += 1
        if cv == ContentVerdict.CONSISTENT:
            stats["consistent"] += 1
        elif cv == ContentVerdict.CONTRADICTION:
            stats["contradiction"] += 1
        else:
            stats["unverifiable"] += 1

        claim["chain_grade"] = cg.value
        claim["content_verdict"] = cv.value
        claim["action"] = action.value
        graded.append(claim)

    elapsed = time.time() - t0

    # ── Corroboration ───────────────────────────────────────────
    print("  Running corroboration...")
    by_norm: dict[str, list[dict]] = {}
    for c in graded:
        norm = c.get("normalized", "")
        if norm:
            by_norm.setdefault(norm, []).append(c)

    narrator_meta = {nid: reg.get_metadata(nid, "physics") for nid in all_narrators}

    for norm, matched in by_norm.items():
        if len(matched) < 2:
            continue
        for i, c_a in enumerate(matched):
            for c_b in matched[i + 1:]:
                if c_a.get("source") == c_b.get("source"):
                    continue
                try:
                    cg_a = ChainGrade(c_a["chain_grade"])
                    cg_b = ChainGrade(c_b["chain_grade"])
                    stats["corroboration_checks"] += 1
                    upgraded = evaluate_corroboration(
                        base_grade=cg_a,
                        corroborating_chain_grades=[cg_b],
                        base_narrators=c_a.get("_narrator_ids", []),
                        corroborating_narrators=[c_b.get("_narrator_ids", [])],
                        narrator_metadata=narrator_meta,
                    )
                    if upgraded != cg_a:
                        c_a["chain_grade"] = upgraded.value
                        stats["corroboration_upgrades"] += 1
                except (ValueError, KeyError):
                    pass

    # ── 5. Results ──────────────────────────────────────────────
    served = sum(1 for c in graded if c.get("action") in ("serve", "serve_with_caveat"))
    review = sum(1 for c in graded if c.get("action") == "review")
    quar = sum(1 for c in graded if c.get("action") in ("quarantine", "reject_and_quarantine_narrator"))
    corrupted_served = sum(1 for c in graded
                          if c.get("action") in ("serve", "serve_with_caveat")
                          and gt_lookup.get(c["claim_id"], {}).get("corrupted"))

    print(f"\n[5/5] Results ({elapsed:.1f}s, {len(claims)/max(0.01,elapsed):.0f} claims/s)")
    print(f"\n{SEP}")
    print("GRADE DISTRIBUTION")
    print(SEP)
    for grade in ["sahih", "hasan", "daif", "mawdu"]:
        count = stats[grade]
        pct = count / len(claims) * 100
        bar = "█" * int(pct / 2)
        print(f"  {grade.upper():8s} {count:5d} ({pct:5.1f}%) {bar}")

    print(f"\n{SEP}")
    print("DECISIONS")
    print(SEP)
    print(f"  SERVED:       {served:5d} ({served/len(claims)*100:5.1f}%)  [corrupted: {corrupted_served}]")
    print(f"  REVIEW:       {review:5d} ({review/len(claims)*100:5.1f}%)")
    print(f"  QUARANTINED:  {quar:5d} ({quar/len(claims)*100:5.1f}%)")

    print(f"\n{SEP}")
    print("CONTENT VERDICTS")
    print(SEP)
    print(f"  CONSISTENT:     {stats['consistent']:5d} ({stats['consistent']/len(claims)*100:5.1f}%)")
    print(f"  CONTRADICTION:  {stats['contradiction']:5d} ({stats['contradiction']/len(claims)*100:5.1f}%)")
    print(f"  UNVERIFIABLE:   {stats['unverifiable']:5d} ({stats['unverifiable']/len(claims)*100:5.1f}%)")

    print(f"\n{SEP}")
    print("CORROBORATION")
    print(SEP)
    print(f"  Checks:    {stats['corroboration_checks']}")
    print(f"  Upgrades:  {stats['corroboration_upgrades']}")
    print(f"  LLM calls: {critic.call_count}")

    # Save
    out = os.path.join(_exp_dir, "results", "s8_bayesian_corroboration.json")
    with open(out, "w") as f:
        json.dump({
            "config": {"policy": "bayesian", "critic": "deepseek" if critic.available else "stub",
                       "claims": len(claims), "error_rate": 0.15},
            "stats": stats,
            "served": served, "review": review, "quarantined": quar,
            "corrupted_served": corrupted_served,
            "elapsed_s": round(elapsed, 2),
            "sample_graded": graded[:5],
        }, f, indent=2)
    print(f"\n  → {out}")
    print(f"\n{SEP}\nDONE\n{SEP}")


if __name__ == "__main__":
    run()
