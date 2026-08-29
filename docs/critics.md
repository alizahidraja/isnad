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
| `LocalNLICritic` | 0.760 | 0.000 | 0.417 | `sentence-transformers` |
| `HybridCritic` | 0.720 | 0.040 | 0.433 | `sentence-transformers` |
| `EmbeddingCritic` | 0.120 | 0.320 | 0.550 | nothing |

**The honest headline.** Only the LLM tier is near-perfect (100% recall, zero
false-consistents). The offline NLI critics, after fixing three defects (issue
#110 — swapped label order, raw logits vs probability thresholds, and
max-over-whole-corpus "different fact" false positives), now *safely* recall
~72–76% of genuine contradictions with near-zero false-consistents — they are
conservative (low 3-way accuracy, most non-contradictions return UNVERIFIABLE),
which is the correct under-trust bias. The `EmbeddingCritic` remains the
safest zero-dependency option (perfect precision, lowest false-consistent), just
low-recall.

> These replace the earlier "~90% LLM / ~40% NLI / ~30% LocalNLI" figures, which
> were estimated on a template-injected (word-swap) set the critics trivially
> caught and were never committed (issue #96). They were wrong, and are retracted.

## Usage

```python
from isnad.critics import best_available_critic, LLMCritic

critic = best_available_critic()             # LLM if a key/local server is set, else NLI, else TF-IDF
critic = best_available_critic(prefer_llm=False)  # force an offline critic
critic = LLMCritic(provider="ollama", model="llama3.1")  # local LLM — no key, no cloud
```

The factory never returns a critic it cannot run: it degrades LLM → NLI →
TF-IDF, and the `LLMCritic` itself returns `UNVERIFIABLE` (never crashes) when
no key is configured.

**Local LLM (no key).** The `LLMCritic` supports a local Ollama server
(`provider="ollama"`, `base_url` `http://localhost:11434/v1`, no API key) — the
same LLM-tier quality with no data leaving the machine. Ollama is not in the
env-var auto-detect list (it has no key), so construct it explicitly as above.

> **Note:** the offline NLI critics are now *safe* (near-zero false-consistent),
> but conservative — they return UNVERIFIABLE for most non-contradictions, so a
> production gate that must auto-serve HASAN-tier claims still needs the LLM
> tier (or a larger review budget); the NLI critics are best for *catching*
> contradictions, not for affirming consistency.

## Numeric aggregates — the deterministic slice (#168/#180, issue #170)

Semantic critics (NLI, embedding) do *entailment*, not *arithmetic*. On a corpus
of hundreds of `"label: count"` rows, they go out of distribution and collapse
to indiscriminate contradiction. Two additive critics fix the *decidable* slice
(a count over returned rows manifestly can be checked):

- **`RecomputeCritic`** recomputes aggregates from the corpus rows and compares
  them to the numbers the claim asserts. It only speaks when it can confidently
  parse both a structured aggregate and a numeric assertion, and it **never**
  blesses a claim on a numeric match alone (a correct number inside a false
  qualifier is not a serve).
- **`EnsembleCritic`** composes a semantic critic with a deterministic one under
  a contradiction-priority, upgrade-only rule: any CONTRADICTION wins; CONSISTENT
  requires *both* critics to confirm; the deterministic critic can only upgrade,
  never override a contradiction.
- **`AggregateRouter`** scopes the semantic critic's corpus for count claims:
  when the corpus is a big list of counts, it hands the inner critic a summary
  (grand total + blank tally) instead of the raw rows, so the semantic critic is
  back in distribution. It never overrides a verdict — it only changes the input.

```python
from isnad.critics import EnsembleCritic, RecomputeCritic, HybridCritic

critic = EnsembleCritic(semantic=HybridCritic(), deterministic=RecomputeCritic())
```

The safety property, tested with real critics (`tests/test_aggregate_router.py`):
no false claim reaches CONSISTENT. A false qualifier the summary refutes is
caught; one the summary is silent about is held for review; a wrong number is
caught. These are opt-in and additive — nothing existing changes behaviour.
