# Content critics — the honest hierarchy

The content critic (matn criticism) checks whether a claim *contradicts* the
corpus, independently of chain quality. This is the framework's historically
weakest link (issue #34), so the critic tiers are documented with their
**measured** behaviour rather than marketed as equal.

`best_available_critic()` returns the strongest tier the current environment
can actually run.

Measured on the committed eval set (`experiments/critic_eval/` — 60 hand-labeled
cases: 20 consistent, 25 genuine contradiction, 15 unrelated, over a 30-fact
physics corpus; see `experiments/critic_eval/RESULTS.md`):

| Critic | Contra. recall | False-consistent (danger) | 3-way acc | Requirements |
|---|---|---|---|---|
| `LLMCritic` (DeepSeek) | **1.000** | **0.000** | 1.000 | API key |
| `EmbeddingCritic` | 0.120 | 0.320 | 0.550 | nothing |
| `HybridCritic` | 0.160 | 0.840 | 0.383 | `sentence-transformers` |
| `LocalNLICritic` | 0.120 | 0.880 | 0.383 | `sentence-transformers` |

**The honest headline.** Only the LLM tier works: it catches 100% of the genuine
contradictions with zero false-consistents. The offline critics all recall
~12–16% on *genuine* physics contradictions — and, crucially, the NLI critics
(`LocalNLICritic`, `HybridCritic`) have an **84–88% false-consistent rate**: the
cross-encoder's topic similarity is mistaken for entailment, so a weak model
confidently *mislabels contradictions as CONSISTENT*. That is the dangerous
failure (a wrong claim served as correct), and it is *worse* than the
`EmbeddingCritic` (32% false-consistent, perfect precision) — a word-overlap
critic is the safer offline default, not the NLI one. See the follow-up issue on
recalibrating/reordering the NLI decision.

> These replace the earlier "~90% LLM / ~40% NLI / ~30% LocalNLI" figures, which
> were estimated on a template-injected (word-swap) set the critics trivially
> caught and were never committed (issue #96). They were wrong, and are retracted.

## Usage

```python
from isnad.critics import best_available_critic

critic = best_available_critic()             # offline: NLI if installed, else TF-IDF
critic = best_available_critic(prefer_llm=True)  # use the LLM tier if a key is present
```

The factory never returns a critic it cannot run: it degrades LLM → NLI →
TF-IDF, and the `LLMCritic` itself returns `UNVERIFIABLE` (never crashes) when
no key is configured.

> **Note:** given the measured NLI false-consistent rate, a production gate that
> must auto-serve HASAN-tier claims should not rely on the offline NLI critics
> alone; either use the LLM tier or keep claims in review.
