"""ISNAD × LangChain — Honest End-to-End Demo.

Demonstrates ISNAD provenance tracking on a simple 2-step LangChain:
  source → retriever → LLM → answer

What this shows:
- Building a seeded registry (warm-start — required for coverage)
- Attaching the IsnadTracer callback
- Printing graded chains, matrix actions, and quarantine reasons
- The critic limitation: without a real critic, most claims are held for review

Run: python examples/langchain_demo.py
"""

from __future__ import annotations

import os
import sys

# Ensure isnad is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from isnad.integrations.langchain import IsnadTracer, seed_registry


def main() -> None:
    print("=" * 64)
    print("  ISNAD × LangChain — End-to-End Demo")
    print("=" * 64)

    # ── Step 1: Build a seeded registry ──────────────────────
    print("\n1. Building seeded registry (warm-start for coverage)...")
    reg = seed_registry({
        "source:physics-textbook": "reliable",
        "retriever:vector-db": "acceptable",
        "model:claude-sonnet": "acceptable",
        "model:untrusted-model": "weak",
    }, domain="physics")
    print(f"   Registered {len(reg)} narrators")

    # ── Step 2: Create the tracer ────────────────────────────
    print("\n2. Creating IsnadTracer...")
    tracer = IsnadTracer(registry=reg, domain="physics")
    print("   Tracer ready. Attach to any LangChain run.")

    # ── Step 3: Simulate a chain run (without real LangChain) ─
    print("\n3. Simulating a chain run...")
    print("   Chain: source → retriever → LLM")

    # Manually add links to simulate what the callbacks would do
    tracer._add_link("source:physics-textbook", "pass_through")
    tracer._add_link("retriever:vector-db", "destructive")
    tracer._add_link("model:claude-sonnet", "generative")

    # Simulate a chain output — two claims
    simulated_output = {
        "answer": "Force equals mass times acceleration. "
                  "This is Newton's Second Law."
    }
    tracer.on_chain_end(simulated_output)

    # ── Step 4: Show what happens with a WEAK model ──────────
    print("\n4. Simulating a run with an UNTRUSTED model...")
    tracer2 = IsnadTracer(registry=reg, domain="physics")
    tracer2._add_link("source:physics-textbook", "pass_through")
    tracer2._add_link("retriever:vector-db", "destructive")
    tracer2._add_link("model:untrusted-model", "generative")
    tracer2.on_chain_end({"answer": "Force equals mass divided by acceleration."})

    # ── Step 5: Print reports ────────────────────────────────
    print("\n" + "=" * 64)
    print("  REPORT — Trusted Model Chain")
    print("=" * 64)
    print(tracer.report())

    print("\n" + "=" * 64)
    print("  REPORT — Untrusted Model Chain")
    print("=" * 64)
    print(tracer2.report())

    # ── Step 6: Honest caveat ────────────────────────────────
    print("\n" + "=" * 64)
    print("  IMPORTANT LIMITATIONS")
    print("=" * 64)
    print("""
  ✓ Weakest-link quarantine WORKS: the untrusted model's claims
    were correctly quarantined because it was graded WEAK.

  ⚠ The default content critic is a non-functional STUB.  Claims
    are held for REVIEW (not auto-served) because the stub returns
    UNVERIFIABLE on real text.

  ⚠ For practical coverage, supply a REAL content critic:
      - LLM-backed via CriticAdapter.llm_backed(api_key="...")
      - Embedding-based similarity to an existing trusted corpus
      - Domain-specific heuristic critic

  ⚠ Corroboration (mutābaʿāt) is experimentally UNTESTED on real
    corpora.  It cannot activate until baseline grades are warm.

  See: experiments/s8_gated_vs_ungated/results/RESULTS.md
""")

    print("Done. Full pipeline traces above.")


if __name__ == "__main__":
    main()
