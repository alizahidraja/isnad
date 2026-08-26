# Cold-start coverage — committed measurement (issue #33)

A seeded pipeline (source RELIABLE, scraper RELIABLE, model ACCEPTABLE via a
published benchmark accuracy) grades **ḥasan**, and coverage is then set by the
content critic (ḥasan × UNVERIFIABLE → REVIEW).

Coverage on 20 clean claims (15 verbatim corpus facts + 5 paraphrases):

| Critic | Coverage |
|---|---|
| LLMCritic (DeepSeek) | **100%** |
| DeterministicRuleCritic (stub) | 75% |
| EmbeddingCritic (TF-IDF) | 75% |
| HybridCritic (MiniLM → NLI) | 10% |
| LocalNLICritic (DeBERTa NLI) | 5% |

On **genuinely new** claims (a 300-claim sweep of clean §8 eval claims, not
curated paraphrases), the critic is correctly conservative — a new fact the
corpus doesn't know is UNVERIFIABLE → REVIEW — so the ceiling is lower:

| Critic | Coverage (new claims) |
|---|---|
| LLMCritic (DeepSeek) | 63% |
| EmbeddingCritic (TF-IDF) | 56% |
| DeterministicRuleCritic (stub) | 0% |

## Reading

- The **seed fix (#114) works**: a cold-start registry with evidence-backed seeds
  grades a chain ḥasan instead of ḍaʿīf, so claims are serveable.
- The **LLM critic is the answer to coverage**: it serves all 20 (understands
  paraphrase), while the stub/embedding critics serve only the 15 verbatim facts
  and the NLI critics are so conservative they hold almost everything for review.
- **For best results use the LLM critic** (cloud via any provider, or local via
  Ollama) in the serving gate. The offline critics are safe but conservative —
  they catch contradictions, not affirm consistency.
