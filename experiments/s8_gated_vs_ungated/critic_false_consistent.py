"""Critic false-consistent measurement — the safety gate for §8.4 (#126).

Measures the *dangerous* critic error: a **corrupted** claim that the critic
labels CONSISTENT, which the decision matrix would then route to SERVE as if it
were clean.  This is the number that must stay ~0 before a critic can be trusted
to unlock the coverage ceiling in the matched-coverage comparison.

Firewall note: this is *measurement/reporting* code, which the firewall test
explicitly permits (alongside analyze.py / audit_sample.py).  It reads the
injection manifest **from the committed JSON file** (``results/seed_1/
ground_truth.json``) — it never imports the ``ground_truth`` module, and it
never feeds manifest fields into any grading/gating decision.  It only counts
what a critic said about a claim whose corruption status is already known.

Honesty contract:
- Reports **which** critic actually ran (LLM / Hybrid NLI / TF-IDF embedding).
  The offline critic is NOT the LLM critic; its number must not be read as the
  LLM's number.
- Reports on the *meaningful* subset: corrupted claims whose text was actually
  mutated (``original_text != corrupted_text``).  "Corrupted" records with no
  text change are noise for this measurement.
- Splits faults by the two-axis divide (#124): **content** (meaning-changing —
  entity swap, sign flip, regime confusion, fabricated numeric, digit swap,
  unit corruption, formula mangling, negation drop, truncation) vs
  **transmission** (OCR character substitution, same meaning).  The headline
  false-consistent rate is computed on *content* corruptions only, because that
  is the fault class content criticism exists to catch; transmission noise is
  the isnād chain grader's responsibility, and a critic that reads a typo as
  CONSISTENT is doing its job correctly.

  NOTE: ``fabricated_numeric`` is content corruption ("L3"→"L2.61" changes the
  claim), not transmission — an earlier version misclassified it.

Usage:
    python critic_false_consistent.py               # best available critic
    python critic_false_consistent.py --seed 1      # other seed (1..10)
    python critic_false_consistent.py --max 500     # cap for speed
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_exp_dir = os.path.dirname(os.path.abspath(__file__))
if _exp_dir not in sys.path:
    sys.path.insert(0, _exp_dir)

from isnad.critics import best_available_critic
from isnad.types import ContentVerdict


# Fault classes (issue #124's two-axis split, applied to measurement):
#   content      — the corruption CHANGES WHAT THE CLAIM ASSERTS (entity swap,
#                  sign flip, regime confusion, negation drop, fabricated
#                  numeric, digit swap, unit corruption, formula mangling,
#                  truncation). This is what content criticism (matn) is
#                  responsible for catching.
#   transmission — the corruption is character-level noise with the SAME
#                  meaning (OCR noise: "ball"→"ba1l"). Content criticism is
#                  the WRONG tool here; the isnād chain grader catches these via
#                  the narrator's ḍabṭ (precision) grade.
#
# NOTE (corrected 2026-08-27): fabricated_numeric is CONTENT corruption, not
# transmission — "mass scales as L3" vs "L2.61" are different claims. An
# earlier version misclassified it, which inflated the 'transmission' bucket
# and deflated the headline content-corruption number.
_TRANSMISSION_FAULTS = ("ocr_noise",)


def _classify(fault_type: str) -> str:
    parts = list(fault_type.split("+"))
    content = [p for p in parts if not any(s in p for s in _TRANSMISSION_FAULTS)]
    if not content:
        return "transmission"
    if len(content) < len(parts):
        return "mixed"
    return "content"


def load_manifest(seed: int) -> list[dict]:
    """Load the injection manifest JSON (the committed ground-truth file)."""
    path = os.path.join(_exp_dir, "results", f"seed_{seed}", "ground_truth.json")
    with open(path) as f:
        return json.load(f)


def critic_identity(critic) -> str:
    """Return a human-readable identity for the critic that actually ran."""
    cls = type(critic).__name__
    if cls == "LLMCritic":
        provider = getattr(critic, "provider", None) or "auto"
        model = getattr(critic, "model", None) or "default"
        return f"LLMCritic (provider={provider}, model={model})"
    if cls == "HybridCritic":
        return "HybridCritic (MiniLM embedding → DeBERTa NLI)"
    if cls == "LocalNLICritic":
        return "LocalNLICritic (DeBERTa NLI)"
    return "EmbeddingCritic (TF-IDF)"


def run_measurement(seed: int, max_claims: int | None, offline: bool = False) -> dict:
    records = load_manifest(seed)

    # The meaningful corrupted subset: text actually mutated by injection.
    mutated = [
        r
        for r in records
        if r.get("corrupted") and (r.get("original_text") != r.get("corrupted_text"))
    ]
    if max_claims is not None:
        mutated = mutated[:max_claims]

    # Clean corpus = the original (pre-injection) text of all records, so the
    # critic judges a corrupted claim against what the corpus *should* say.
    clean_corpus = [r["original_text"] for r in records if r.get("original_text")]

    # offline → force the instant TF-IDF critic (no ~500MB model download);
    # default → best available (LLM if a key is set, else Hybrid NLI).
    if offline:
        from isnad.critics.embedding import EmbeddingCritic

        critic = EmbeddingCritic()
    else:
        critic = best_available_critic()

    # Per-class tallies, because the two-axis split matters (issue #124): a
    # false-CONSISTENT on *content* corruption is the dangerous error (the
    # critic's actual job); a "false-CONSISTENT" on transmission noise is the
    # critic correctly recognising unchanged meaning.
    tally: dict[str, dict[str, int]] = {
        cls: {"false_consistent": 0, "caught": 0, "unverifiable": 0}
        for cls in ("content", "transmission", "mixed")
    }
    for r in mutated:
        verdict = critic.evaluate(
            r["corrupted_text"],
            r["corrupted_text"].lower().strip(),
            clean_corpus,
            r.get("domain", "general"),
        )
        k = _classify(r["fault_type"])
        if verdict == ContentVerdict.CONSISTENT:
            tally[k]["false_consistent"] += 1
        elif verdict == ContentVerdict.CONTRADICTION:
            tally[k]["caught"] += 1
        else:
            tally[k]["unverifiable"] += 1

    # The headline number is the false-consistent rate on *content* corruptions
    # only — the fault class content criticism exists to catch.
    sem = tally["content"]
    sem_total = sum(sem.values())
    false_consistent = sem["false_consistent"]

    n = len(mutated)
    return {
        "critic": critic_identity(critic),
        "seed": seed,
        "mutated_corrupted": n,
        "content_total": sem_total,
        "content_false_consistent": false_consistent,
        "content_false_consistent_rate": (false_consistent / sem_total) if sem_total else 0.0,
        "content_caught": sem["caught"],
        "content_unverifiable": sem["unverifiable"],
        "by_class": {
            k: {
                "false_consistent": v["false_consistent"],
                "caught": v["caught"],
                "unverifiable": v["unverifiable"],
            }
            for k, v in tally.items()
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--max", type=int, default=None, help="cap mutated claims (speed)")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="force the instant TF-IDF critic (no ~500MB NLI model download)",
    )
    args = parser.parse_args()

    result = run_measurement(args.seed, args.max, offline=args.offline)

    by_class = result["by_class"]
    print("=" * 70)
    print("CRITIC FALSE-CONSISTENT MEASUREMENT (#126 safety gate)")
    print("=" * 70)
    print(f"  Critic:              {result['critic']}")
    print(f"  Seed:                {result['seed']}")
    print(f"  Mutated corruptions: {result['mutated_corrupted']}")
    print()
    print("  The headline number is the false-consistent rate on *content* corruptions")
    print("  (meaning-changing: entity swap, sign flip, regime confusion, fabricated")
    print("  numeric, digit swap, unit corruption, formula mangling, negation drop,")
    print("  truncation) — the fault class content criticism exists to catch.")
    print("  Transmission noise (OCR character substitution) is the isnād chain")
    print("  grader's job, not the critic's (§124 two-axis split).")
    print()
    for cls in ("content", "mixed", "transmission"):
        v = by_class[cls]
        total = sum(v.values())
        fc = v["false_consistent"]
        if total:
            print(f"  {cls:14s} n={total:3d}  false-CONSISTENT={fc:3d} ({fc / total:.1%})")
        else:
            print(f"  {cls:14s} n=0")
    print()
    r = result
    ct = r["content_total"]
    print(
        f"  CONTENT false-consistent: {r['content_false_consistent']}/"
        f"{ct} ({r['content_false_consistent_rate']:.1%})  "
        f"— the number that must stay ~0"
    )
    print(f"  CONTENT caught:          {r['content_caught']}")
    print(f"  CONTENT unverifiable:    {r['content_unverifiable']}")
    print()
    print("Reading the number:")
    print("  - Content false-consistent = meaning-changing corruptions the critic")
    print("    would serve as if clean. This must stay ~0 before trusting the critic")
    print("    to unlock coverage.")
    print("  - Transmission 'false-consistent' is the critic correctly seeing the")
    print("    meaning is unchanged — those are caught by the chain grader instead.")
    print("=" * 70)

    out = os.path.join(_exp_dir, "results", f"critic_false_consistent_seed{args.seed}.json")
    with open(out, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\n  Saved: {out}")


if __name__ == "__main__":
    main()
