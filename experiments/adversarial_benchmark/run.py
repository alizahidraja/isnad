"""Adversarial corruption-detection benchmark.

The honest "does it actually work?" number the repo has been missing (issue
#50).  Offline and reproducible — no API keys, no LLM, the bundled
``DeterministicRuleCritic`` for matn criticism.

It injects four classes of case into a controlled corpus and measures what the
*full* pipeline (narrator grades → chain grade → critic → decision matrix)
catches, and — just as prominently — what it misses.

Run:  python experiments/adversarial_benchmark/run.py
"""

from __future__ import annotations

from dataclasses import dataclass, field

from isnad import Chain, ChainLinkSpec, Registry, decide, grade_chain
from isnad.matn import DeterministicRuleCritic
from isnad.types import NarratorGrade, NarratorType

# A small physics corpus — the "known-good" knowledge base.
CORPUS = [
    "force equals mass times acceleration",
    "energy is conserved",
    "the speed of light is constant",
    "momentum is mass times velocity",
    "electrons have negative charge",
    "gravity is attractive",
    "temperature increases with heat",
    "light is a wave",
    "the atom has a nucleus",
    "entropy always increases",
    "water freezes at zero degrees celsius",
    "pressure is force per unit area",
    "work is force times distance",
    "power is work per unit time",
    "charge is conserved",
    "mass is conserved",
    "velocity is displacement over time",
    "acceleration is the rate of change of velocity",
    "newton's second law relates force and acceleration",
    "the electric field points away from positive charge",
]

# Narrators, seeded with operator-assigned grades.
NARRATORS: dict[str, tuple[NarratorGrade, NarratorType]] = {
    "source:openstax": (NarratorGrade.RELIABLE, NarratorType.SOURCE),
    "model:reliable": (NarratorGrade.RELIABLE, NarratorType.MODEL),
    "model:good": (NarratorGrade.ACCEPTABLE, NarratorType.MODEL),
    "model:weak": (NarratorGrade.WEAK, NarratorType.MODEL),
    "model:bad": (NarratorGrade.REJECTED, NarratorType.MODEL),
}


@dataclass
class Case:
    """One benchmark case with ground truth."""

    claim: str
    chain_narrators: list[str]
    good: bool
    kind: str
    note: str = ""


@dataclass
class Result:
    caught: bool
    served: bool
    action: str
    chain_grade: str
    verdict: str


FLAG_ACTIONS = {"review", "quarantine", "reject_and_quarantine_narrator"}


def _build_cases() -> list[Case]:
    cases: list[Case] = []

    # 1. Good claims, clean SAHIH chains — should be served, not flagged.
    for i, claim in enumerate(CORPUS):
        cases.append(
            Case(
                claim=claim,
                chain_narrators=["source:openstax", "model:reliable"],
                good=True,
                kind="good",
            )
        )

    # 2. Weak-narrator corruption: a clean claim carried by a WEAK narrator.
    for i in range(10):
        cases.append(
            Case(
                claim=CORPUS[i % len(CORPUS)],
                chain_narrators=["source:openstax", "model:weak"],
                good=False,
                kind="weak-narrator",
                note="clean claim, weak synthesis model",
            )
        )

    # 3. Pattern contradictions — contradictions the reference critic CAN catch.
    contradictions = [
        "energy is not conserved",
        "the speed of light varies with the observer",
        "momentum is velocity divided by mass",
        "electrons have positive charge",
        "gravity is repulsive at large distances",
        "temperature decreases when heat is added",
        "light is purely a particle with no wave properties",
        "the atom has no nucleus",
        "entropy can decrease in isolated systems",
        "work is force divided by distance",
    ]
    for claim in contradictions:
        cases.append(
            Case(
                claim=claim,
                chain_narrators=["source:openstax", "model:reliable"],
                good=False,
                kind="pattern-contradiction",
                note="contradicts the corpus via a known phrase",
            )
        )

    # 4. Semantic contradictions — same falsehood, different wording; the
    #    reference critic (word-overlap) cannot see these.
    semantic = [
        "water solidifies at thirty-two degrees",
        "the atom contains no central core",
        "energy can be created from nothing",
        "light behaves as a pure particle",
        "electrical charge is not a conserved quantity",
        "mass varies with temperature",
        "objects move without any force acting",
        "gravity pushes masses apart",
        "entropy decreases over time in any system",
        "water boils at zero degrees",
    ]
    for claim in semantic:
        cases.append(
            Case(
                claim=claim,
                chain_narrators=["source:openstax", "model:reliable"],
                good=False,
                kind="semantic-contradiction",
                note="same falsehood, different wording (critic is blind)",
            )
        )

    return cases


def _run_case(case: Case, reg: Registry, critic: DeterministicRuleCritic) -> Result:
    chain = Chain(
        [ChainLinkSpec(nid, i, domain="physics") for i, nid in enumerate(case.chain_narrators)]
    )
    grades = [reg.get_grade_for_link(l.narrator_id, l.domain, l.version) for l in chain.links]
    chain_grade = grade_chain(grades, [l.transform_type for l in chain.links], is_complete=True)
    verdict = critic.evaluate(case.claim, case.claim.lower(), CORPUS, "physics")
    action = decide(chain_grade, verdict)
    return Result(
        caught=action.value in FLAG_ACTIONS,
        served=action.value in ("serve", "serve_with_caveat"),
        action=action.value,
        chain_grade=chain_grade.value,
        verdict=verdict.value,
    )


def main() -> None:
    reg = Registry()
    for nid, (grade, ntype) in NARRATORS.items():
        reg.register(nid, "physics", grade=grade, narrator_type=ntype)

    critic = DeterministicRuleCritic()
    cases = _build_cases()
    results = [_run_case(c, reg, critic) for c in cases]

    # Confusion matrix, keyed by case kind.
    by_kind: dict[str, dict[str, int]] = {}
    for case, r in zip(cases, results):
        k = by_kind.setdefault(case.kind, {"tp": 0, "fn": 0, "tn": 0, "fp": 0})
        if case.good:
            k["tn" if r.served else "fp"] += 1
        else:
            k["tp" if r.caught else "fn"] += 1

    total_bad = sum(1 for c in cases if not c.good)
    total_good = sum(1 for c in cases if c.good)
    tp = sum(v["tp"] for v in by_kind.values())
    fn = sum(v["fn"] for v in by_kind.values())
    fp = sum(v["fp"] for v in by_kind.values())
    tn = sum(v["tn"] for v in by_kind.values())

    recall = tp / max(1, tp + fn)
    fpr = fp / max(1, fp + tn)

    print("=" * 70)
    print("ISNAD adversarial corruption-detection benchmark")
    print("=" * 70)
    print(f"\ncorpus: {len(CORPUS)} known-good claims; {len(cases)} cases")
    print(f"bad cases: {total_bad}  good cases: {total_good}")
    print("\nby corruption class:")
    print(f"  {'class':24} {'caught':>7} {'missed':>7} {'rate':>7}")
    for kind in ["weak-narrator", "pattern-contradiction", "semantic-contradiction"]:
        k = by_kind[kind]
        caught, missed = k["tp"], k["fn"]
        denom = caught + missed
        rate = f"{caught / denom:.0%}" if denom else "n/a"
        print(f"  {kind:24} {caught:>7} {missed:>7} {rate:>7}")
    g = by_kind["good"]
    print(f"  {'good (served vs flagged)':24} {g['tn']:>7} {g['fp']:>7} {g['tn'] / max(1, g['tn'] + g['fp']):>7.0%}")

    print("\nsummary:")
    print(f"  bad-claim recall (fraction of corruptions caught): {recall:.0%}")
    print(f"  false-positive rate (good claims flagged):        {fpr:.0%}")
    print(f"  overall accuracy:                                 {(tp + tn) / len(cases):.0%}")

    print("\n" + "-" * 70)
    print("HONEST LIMITS (the point of the benchmark):")
    print("- 'caught' means REVIEW/QUARANTINE/REJECT — routed to a human, not")
    print("  auto-deleted. ISNAD surfaces; it does not adjudicate.")
    print("- The reference critic is word-overlap only. It catches pattern")
    print("  contradictions, but a semantic contradiction on a SAHIH chain is")
    print("  served WITH_CAVEAT — not flagged. That gap is issue #34, and the")
    print("  semantic-contradiction row above is its honest, quantitative size.")
    print("- This corpus is synthetic and physics-only. Real recall will differ.")
    print("-" * 70)


if __name__ == "__main__":
    main()
