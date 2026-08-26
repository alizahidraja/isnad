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

    false_consistent = 0
    caught = 0  # CONTRADICTION — the critic correctly flagged the corruption
    unverifiable = 0
    for r in mutated:
        verdict = critic.evaluate(
            r["corrupted_text"],
            r["corrupted_text"].lower().strip(),
            clean_corpus,
            r.get("domain", "general"),
        )
        if verdict == ContentVerdict.CONSISTENT:
            false_consistent += 1
        elif verdict == ContentVerdict.CONTRADICTION:
            caught += 1
        else:
            unverifiable += 1

    n = len(mutated)
    return {
        "critic": critic_identity(critic),
        "seed": seed,
        "mutated_corrupted": n,
        "false_consistent": false_consistent,
        "false_consistent_rate": (false_consistent / n) if n else 0.0,
        "caught_contradiction": caught,
        "unverifiable": unverifiable,
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

    print("=" * 70)
    print("CRITIC FALSE-CONSISTENT MEASUREMENT (#126 safety gate)")
    print("=" * 70)
    print(f"  Critic:                {result['critic']}")
    print(f"  Seed:                  {result['seed']}")
    print(f"  Mutated corruptions:   {result['mutated_corrupted']}")
    print(
        f"  False-CONSISTENT:      {result['false_consistent']} "
        f"({result['false_consistent_rate']:.1%})"
    )
    print(f"  Correctly CONTRADICT:  {result['caught_contradiction']}")
    print(f"  UNVERIFIABLE:          {result['unverifiable']}")
    print()
    print("Reading the number:")
    print("  - false-consistent = corrupted claims the critic would let through as")
    print("    CONSISTENT → these become served errors. This must stay ~0.")
    print("  - UNVERIFIABLE is safe (routes to REVIEW) but caps coverage (§8.6).")
    print("  - The offline critic's number is NOT the LLM critic's number.")
    print("    To measure the LLM tier, set a provider key (e.g. DEEPSEEK_API_KEY)")
    print("    and re-run — best_available_critic() will pick it up automatically.")
    print("=" * 70)

    out = os.path.join(_exp_dir, "results", f"critic_false_consistent_seed{args.seed}.json")
    with open(out, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\n  Saved: {out}")


if __name__ == "__main__":
    main()
