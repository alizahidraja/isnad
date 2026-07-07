"""Rejected-claims diagnostic — shows what ISNAD quarantined and why.

For each quarantined claim, prints the full transmission chain with
each narrator's grade, transform type, and the exact rule that broke it.

Output: results/rejected_claims_diagnostic.txt — human-readable trace
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

_exp_dir = os.path.dirname(os.path.abspath(__file__))
if _exp_dir not in sys.path:
    sys.path.insert(0, _exp_dir)

from isnad.chain import Chain, ChainLinkSpec
from isnad.grading import grade_chain
from isnad.matrix import decide, describe_action
from isnad.registry import Registry
from isnad.types import (
    Action,
    ChainGrade,
    ContentVerdict,
    NarratorGrade,
    TransformType,
)


def _rebuild_chain(claim: dict) -> Chain:
    links = claim.get("chain_json", [])
    specs = []
    for i, link in enumerate(links):
        specs.append(ChainLinkSpec(
            narrator_id=link["narrator_id"], step=i,
            version=link.get("version", "unknown"),
            transform_type=TransformType(link.get("transform_type", "pass_through")),
            domain=link.get("domain", "general"),
        ))
    return Chain(specs)


GRADE_LABEL = {
    "reliable": "RELIABLE ✓",
    "acceptable": "ACCEPTABLE",
    "weak": "WEAK ✗",
    "rejected": "REJECTED ✗✗",
    "ungraded": "UNGRADED ?",
}
TRANSFORM_LABEL = {
    "pass_through": "[→]",
    "destructive": "[DESTRUCTIVE ▼]",
    "generative": "[GENERATIVE ▲]",
}


def main() -> None:
    results_dir = os.path.join(_exp_dir, "results")
    seed_dir = os.path.join(results_dir, "seed_1")
    cal_dir = os.path.join(seed_dir, "calibration")

    with open(os.path.join(cal_dir, "eval_claims.json")) as f:
        eval_claims = json.load(f)
    with open(os.path.join(seed_dir, "ground_truth.json")) as f:
        gt_lookup = {r["claim_id"]: r for r in json.load(f)}
    with open(os.path.join(cal_dir, "registry_snapshot.json")) as f:
        snap = json.load(f)

    reg = Registry()
    for key, data in snap.items():
        nid, domain = key.split("/", 1)
        reg.register(nid, domain, grade=NarratorGrade(data["grade"]))

    lines = []
    lines.append("=" * 72)
    lines.append("  ISNAD REJECTED-CLAIMS DIAGNOSTIC")
    lines.append("  Every quarantined claim traced through its full chain")
    lines.append("=" * 72)
    lines.append("")

    total = len(eval_claims)
    rejected = 0
    rejected_samples: list[dict] = []
    rejection_reasons: dict[str, int] = defaultdict(int)

    for claim in eval_claims:
        chain = _rebuild_chain(claim)
        link_grades = [reg.get_grade(l.narrator_id, l.domain) for l in chain.links]
        link_transforms = [l.transform_type for l in chain.links]
        cg = grade_chain(link_grades, link_transforms,
                         is_complete=claim.get("chain_complete", True))
        action = decide(cg, ContentVerdict.UNVERIFIABLE)

        if action in (Action.REJECT_AND_QUARANTINE_NARRATOR, Action.QUARANTINE):
            rejected += 1
            reason = "MAWDU chain → quarantine" if cg == ChainGrade.MAWDU else \
                     "DAIF + contradiction" if cg == ChainGrade.DAIF else \
                     f"Quarantined: {action.value}"
            rejection_reasons[reason] += 1

            if len(rejected_samples) < 15:
                rejected_samples.append({
                    "claim": claim,
                    "chain": chain,
                    "link_grades": link_grades,
                    "link_transforms": link_transforms,
                    "chain_grade": cg,
                    "action": action,
                    "gt": gt_lookup.get(claim["claim_id"], {}),
                })

    lines.append(f"Total eval claims: {total}")
    lines.append(f"Rejected/quarantined: {rejected} ({100*rejected/total:.1f}%)")
    lines.append(f"Served: {total - rejected} ({100*(total-rejected)/total:.1f}%)")
    lines.append("")
    lines.append("Rejection reason breakdown:")
    for reason, count in sorted(rejection_reasons.items(), key=lambda x: -x[1]):
        lines.append(f"  {count:>6d}  {reason}")
    lines.append("")

    # Show sampled rejected claims with full chain trace
    lines.append("=" * 72)
    lines.append(f"  SAMPLED REJECTED CLAIMS ({len(rejected_samples)} shown)")
    lines.append("=" * 72)

    for i, sample in enumerate(rejected_samples):
        claim = sample["claim"]
        chain = sample["chain"]
        gt = sample["gt"]
        cg = sample["chain_grade"]
        action = sample["action"]

        lines.append(f"\n── Claim #{i+1} ──")
        lines.append(f"  ID:       {claim['claim_id'][:16]}...")
        text = claim.get("corrupted_text", claim.get("text", ""))[:120]
        lines.append(f"  Text:     \"{text}\"")
        lines.append(f"  Source:   {claim.get('source', '?')}")
        lines.append(f"  Domain:   {claim.get('domain', '?')}")
        if gt.get("corrupted"):
            lines.append(f"  Corrupted: YES — {gt.get('fault_type','?')} by {gt.get('responsible_narrator','?')}")
            lines.append(f"  Original: \"{gt.get('original_text','')[:120]}\"")
        lines.append(f"  Complete: {'✓' if claim.get('chain_complete', True) else '✗ MUNQAṬIʿ'}")

        lines.append(f"\n  Transmission chain ({len(chain.links)} links):")
        lines.append(f"  {'Step':<5s} {'Narrator':<25s} {'Grade':<14s} {'Transform':<16s} {'Domain':<18s}")

        for j, link in enumerate(chain.links):
            grade = sample["link_grades"][j]
            xform = sample["link_transforms"][j]
            g_label = GRADE_LABEL.get(grade.value, grade.value)
            t_label = TRANSFORM_LABEL.get(xform.value, xform.value)
            breaker = " ← BREAKS" if grade in (NarratorGrade.REJECTED, NarratorGrade.WEAK) else ""
            lines.append(f"  {j:<5d} {link.narrator_id:<25s} {g_label:<14s} {t_label:<16s} {link.domain:<18s}{breaker}")

        lines.append(f"\n  Chain grade: {cg.value.upper()}")
        lines.append(f"  Matrix:      {describe_action(cg, ContentVerdict.UNVERIFIABLE)}")
        lines.append(f"  Action:      {action.value.upper()}")

        # Explain exactly what broke
        lines.append(f"\n  WHY REJECTED:")
        for j, (link, grade) in enumerate(zip(chain.links, sample["link_grades"])):
            if grade == NarratorGrade.REJECTED:
                lines.append(f"    Step {j}: {link.narrator_id} is REJECTED → chain becomes MAWDU")
                lines.append(f"             (rejected narrator caps entire chain at fabricated tier)")
                break
            elif grade == NarratorGrade.WEAK:
                xform = sample["link_transforms"][j]
                if xform == TransformType.DESTRUCTIVE:
                    lines.append(f"    Step {j}: {link.narrator_id} is WEAK + DESTRUCTIVE → permanent cap")
                else:
                    lines.append(f"    Step {j}: {link.narrator_id} is WEAK → weak link")
        if not claim.get("chain_complete", True):
            lines.append(f"    Chain is MUNQAṬIʿ (incomplete) → automatically capped at DAIF")

    lines.append(f"\n{'=' * 72}")
    lines.append(f"  SUMMARY")
    lines.append(f"{'=' * 72}")
    lines.append(f"  Served:    {total - rejected} claims ({100*(total-rejected)/total:.1f}%)")
    lines.append(f"  Rejected:  {rejected} claims ({100*rejected/total:.1f}%)")
    lines.append(f"  Key find:  Narrators graded REJECTED block ALL their claims,")
    lines.append(f"             regardless of downstream narrator quality.")
    lines.append(f"             This is the weakest-link rule working as designed.")

    out_path = os.path.join(results_dir, "rejected_claims_diagnostic.txt")
    with open(out_path, "w") as f:
        f.write("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
