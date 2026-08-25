# Content critics — the honest hierarchy

The content critic (matn criticism) checks whether a claim *contradicts* the
corpus, independently of chain quality. This is the framework's historically
weakest link (issue #34), so the critic tiers are documented with their measured
recall rather than marketed as equal.

`best_available_critic()` returns the strongest tier the current environment
can actually run.

| Tier | Critic | Semantic recall (synthetic adversarial corpus) | Requirements |
|---|---|---|---|
| 1 | `LLMCritic` | ~90% | API key (OpenRouter / OpenAI / DeepSeek / Anthropic / …) |
| 2 | `HybridCritic` | ~40% | `sentence-transformers` (~500 MB models, offline) |
| 2b | `LocalNLICritic` | ~30% | `sentence-transformers` (one cross-encoder, offline) |
| 3 | `EmbeddingCritic` | ~10% (word-overlap only) | nothing |
| ref | `DeterministicRuleCritic` | ~10% (word-overlap + negation) | nothing |

Numbers are from the bundled adversarial benchmark
(`experiments/adversarial_benchmark/run.py --semantic`) on a synthetic 20-claim
physics corpus — indicative, not definitive. The honest headline: **the semantic
gap is solved by the LLM critic, but the no-key ceiling is ~40% (NLI)**. There
is no offline critic that approaches the LLM tier today.

## Usage

```python
from isnad.critics import best_available_critic

critic = best_available_critic()             # offline: NLI if installed, else TF-IDF
critic = best_available_critic(prefer_llm=True)  # use the LLM tier if a key is present
```

The factory never returns a critic it cannot run: it degrades LLM → NLI →
TF-IDF, and the `LLMCritic` itself returns `UNVERIFIABLE` (never crashes) when
no key is configured.
