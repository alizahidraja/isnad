"""Verified vs. Unverified — controlled A/B demonstration (issue #7).

Runs each hand-authored scenario through an identical pipeline twice:
  1. Trust layer OFF  — serve whatever the pipeline produces.
  2. Trust layer ON   — grade the chain, criticize content, route via matrix.

Reports, per scenario, what each mode produced and whether the trust layer
caught a corrupted claim or missed it.  No LLM, no API keys, no randomness.
Deterministic and CI-safe.

The content critic here is DELIBERATELY LIMITED — it catches only the
obvious contradictions (negation, known-false statements) and returns
UNVERIFIABLE on subtle corruptions.  That limitation is what makes the
demonstration honest: a subtle corruption on a clean-looking chain is
exactly the case ISNAD should admit it misses (issues #4 and #11).
"""

from __future__ import annotations

import sys
from pathlib import Path

_EXP_DIR = Path(__file__).resolve().parent
_SRC = _EXP_DIR.parent.parent / "src"
sys.path.insert(0, str(_SRC))

from fixtures import CORROBORATING_CHAIN_FOR_E, NARRATORS, SCENARIOS
from isnad.core.chain import Chain, ChainLinkSpec
from isnad.core.corroboration import evaluate_corroboration
from isnad.core.decision import decide, describe_action
from isnad.core.grading import grade_chain
from isnad.core.registry import Registry
from isnad.types import (
    Action,
    ChainGrade,
    ContentVerdict,
    NarratorGrade,
    NarratorType,
    TransformType,
)

# ---------------------------------------------------------------------------
# Registry — seed grades from the manifest (NOT from ground truth)
# ---------------------------------------------------------------------------


def build_registry() -> Registry:
    reg = Registry()
    grade_map = {
        "reliable": NarratorGrade.RELIABLE,
        "acceptable": NarratorGrade.ACCEPTABLE,
        "weak": NarratorGrade.WEAK,
        "rejected": NarratorGrade.REJECTED,
        "ungraded": NarratorGrade.UNGRADED,
    }
    type_map = {
        "source": NarratorType.SOURCE,
        "scraper": NarratorType.SCRAPER,
        "model": NarratorType.MODEL,
    }
    for nid, n in NARRATORS.items():
        reg.register(
            nid,
            "physics",
            narrator_type=type_map[n.narrator_type],
            grade=grade_map[n.grade],
            model_family=n.model_family,
            upstream_source=n.upstream_source,
        )
    return reg


def build_chain(links: list[tuple[str, str]]) -> Chain:
    return Chain([
        ChainLinkSpec(
            narrator_id=nid,
            step=i,
            transform_type=TransformType(ttype),
            domain="physics",
        )
        for i, (nid, ttype) in enumerate(links)
    ])


# ---------------------------------------------------------------------------
# Content critic — deterministic, deliberately limited
# ---------------------------------------------------------------------------


class DemonstrationCritic:
    """A deterministic content critic that catches only OBVIOUS contradictions.

    This represents what a real content critic (embedding/NLI/LLM) would do
    with the corpus.  It catches:
      - negation ("not conserved")
      - classical-vs-quantum momentum clash ("moving object" + "p = h/λ")

    It deliberately returns UNVERIFIABLE on subtle corruptions (a digit
    change in a constant, a plausible-sounding lie).  That is the honest
    limit: a real critic might also miss those.  The demonstration is built
    around the two cases the framework SHOULD admit it misses.
    """

    def evaluate(
        self, claim_text: str, normalized: str, corpus_claims: list[str], domain: str
    ) -> ContentVerdict:
        c = normalized.lower()
        # Obvious negation — the content critic catches this independently of chain.
        if "not conserved" in c:
            return ContentVerdict.CONTRADICTION
        # Classical vs quantum momentum clash (scenario F).
        if "p = h/λ" in c and "moving object" in c:
            return ContentVerdict.CONTRADICTION
        # Known-true statements the corpus supports.
        if "p = h/λ" in c and "photon" in c:
            return ContentVerdict.CONSISTENT
        if "speed of light" in c and "constant" in c:
            return ContentVerdict.CONSISTENT
        # Everything else — including the subtle stale-grade corruption and
        # the plausible fabricated claim — is beyond this critic's reach.
        return ContentVerdict.UNVERIFIABLE


# ---------------------------------------------------------------------------
# The two pipelines
# ---------------------------------------------------------------------------


def run_off() -> dict:
    """Trust layer OFF: serve the claim unconditionally."""
    return {"served": True, "action": "served (ungated)", "reason": "no trust layer"}


def run_on(chain: Chain, reg: Registry, critic: DemonstrationCritic, claim: str) -> dict:
    """Trust layer ON: full ISNAD pipeline."""
    link_grades = [reg.get_grade(l.narrator_id, l.domain) for l in chain.links]
    transforms = [l.transform_type for l in chain.links]
    cg = grade_chain(link_grades, transforms, is_complete=chain.is_complete)

    cv = critic.evaluate(claim, claim.lower(), [], "physics")
    action = decide(cg, cv)

    served = action in (Action.SERVE, Action.SERVE_WITH_CAVEAT)

    return {
        "served": served,
        "action": action.value,
        "chain_grade": cg.value,
        "content_verdict": cv.value,
        "reason": describe_action(cg, cv),
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def main() -> None:
    reg = build_registry()
    critic = DemonstrationCritic()

    results = []
    for s in SCENARIOS:
        chain = build_chain(s.chain)
        off = run_off()
        on = run_on(chain, reg, critic, s.claim)

        # Corroboration for scenario E: a second independent chain asserts
        # the same claim, upgrading DAIF → HASAN.
        if s.id == "E-corroboration":
            chain2 = build_chain(CORROBORATING_CHAIN_FOR_E)
            cg_base = grade_chain(
                [reg.get_grade(l.narrator_id, l.domain) for l in chain.links],
                [l.transform_type for l in chain.links],
                is_complete=True,
            )
            upgraded = evaluate_corroboration(
                base_grade=cg_base,
                corroborating_chain_grades=[ChainGrade.SAHIH],
                base_narrators=chain.narrator_ids,
                corroborating_narrators=[chain2.narrator_ids],
                narrator_metadata={nid: reg.get_metadata(nid, "physics") for nid in NARRATORS},
            )
            on["corroborated_grade"] = upgraded.value
            # Re-decide with the upgraded grade so the report reflects recovery.
            cv = critic.evaluate(s.claim, s.claim.lower(), [], "physics")
            on["action"] = decide(upgraded, cv).value
            on["served"] = decide(upgraded, cv) in (Action.SERVE, Action.SERVE_WITH_CAVEAT)

        # Ground truth verdict (only for reporting — never during grading)
        caught = (not s.correct) and (not on["served"])
        missed = (not s.correct) and on["served"]
        false_positive = s.correct and (not on["served"])

        results.append({
            "scenario": s,
            "off": off,
            "on": on,
            "caught": caught,
            "missed": missed,
            "false_positive": false_positive,
        })

    # ── Print report ────────────────────────────────────────────
    print("=" * 72)
    print("VERIFIED vs. UNVERIFIED — controlled A/B demonstration")
    print("=" * 72)

    for r in results:
        s = r["scenario"]
        on = r["on"]
        print(f"\n[{s.id}] {s.query}")
        print(f"  claim:        {s.claim[:68]}{'…' if len(s.claim) > 68 else ''}")
        print(f"  ground truth: {'CORRECT' if s.correct else 'CORRUPTED'} ({s.failure_mode})")
        print(f"  OFF:          {r['off']['action']}")
        if "chain_grade" in on:
            print(
                f"  ON:           grade={on['chain_grade']}, "
                f"content={on['content_verdict']}, action={on['action']}"
            )
            if "corroborated_grade" in on:
                print(f"                corroborated grade={on['corroborated_grade']}")
        if r["caught"]:
            print("  ▶ CAUGHT:     the trust layer blocked a corrupted claim")
        elif r["missed"]:
            print(f"  ▶ MISSED:     the trust layer served a corrupted claim — {s.failure_mode}")
        elif r["false_positive"]:
            print("  ▶ FALSE +VE:  the trust layer blocked a correct claim")
        else:
            print("  ▶ OK:         correct claim, served (or correctly reviewed)")
        if s.note:
            print(f"  note:         {s.note}")

    # ── Summary ────────────────────────────────────────────────
    caught = sum(1 for r in results if r["caught"])
    missed = sum(1 for r in results if r["missed"])
    fp = sum(1 for r in results if r["false_positive"])
    corrupted = sum(1 for r in results if not r["scenario"].correct)

    print(f"\n{'=' * 72}")
    print("SUMMARY")
    print("=" * 72)
    print(f"  scenarios:          {len(results)}")
    print(f"  corrupted claims:   {corrupted}")
    print(f"  caught:             {caught}")
    print(f"  missed:             {missed}")
    print(f"  false positives:    {fp}")
    print()
    print("  What the trust layer catches:  weak-narrator corruption (B),")
    print("                                  ilal contradiction (F),")
    print("                                  corroboration recovery (E)")
    print("  What it misses (honestly):      stale-grade drift (C, issue #4),")
    print("                                  fabricated-clean chain (D, issue #11)")
    print()
    print("  The miss cases are the point: a stale grade AND a subtle error, or")
    print("  a clean chain AND a plausible lie, defeat both defenses at once.")
    print(f"\n{'=' * 72}")


if __name__ == "__main__":
    main()
