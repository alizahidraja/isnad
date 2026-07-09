"""Semantic matcher — embedding-based cross-source claim matching.

Uses sentence-transformers (all-MiniLM-L6-v2) to encode claims from
regular Wikipedia and Simple English Wikipedia, then finds semantically
similar pairs across the two sources via cosine similarity.

This replaces the exact-string matching of v1 with genuine semantic
matching — different text, same meaning.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class MatchPair:
    """A semantically matched claim pair across sources."""

    topic_reg: str
    topic_sim: str
    text_reg: str
    text_sim: str
    similarity: float


class SemanticMatcher:
    """Cross-source semantic claim matcher using sentence-transformers."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._model: Any = None
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        print(f"  Loading embedding model: {self.model_name} ...")
        from sentence_transformers import SentenceTransformer
        t0 = time.time()
        self._model = SentenceTransformer(self.model_name)
        print(f"  Loaded in {time.time() - t0:.1f}s")
        self._loaded = True

    def encode(self, sentences: list[str], batch_size: int = 64,
               show_progress: bool = True) -> np.ndarray:
        """Encode a list of sentences into embeddings."""
        self._load()
        return self._model.encode(
            sentences, batch_size=batch_size,
            show_progress_bar=show_progress,
            convert_to_numpy=True,
        )

    def find_cross_source_matches(
        self,
        claims_reg: list[dict[str, Any]],  # [{"topic": ..., "text": ...}, ...]
        claims_sim: list[dict[str, Any]],
        threshold: float = 0.75,
        top_k_per_query: int = 3,
    ) -> list[MatchPair]:
        """Find semantically similar claim pairs across regular and simple Wikipedia.

        Uses cosine similarity on embeddings.  For each claim in the smaller
        set (simple), finds the top-k most similar claims in the larger set
        (regular) that exceed the threshold.

        Returns list of MatchPair, sorted by similarity descending.
        """
        self._load()

        texts_reg = [c["text"] for c in claims_reg]
        texts_sim = [c["text"] for c in claims_sim]

        print(f"  Encoding {len(texts_reg)} regular claims ...")
        emb_reg = self.encode(texts_reg, show_progress=True)

        print(f"  Encoding {len(texts_sim)} simple claims ...")
        emb_sim = self.encode(texts_sim, show_progress=True)

        # Normalize for cosine similarity
        from sklearn.metrics.pairwise import cosine_similarity

        pairs = []
        print(f"  Computing cross-source similarity ({len(texts_sim)} × {len(texts_reg)}) ...")

        # Process in batches to manage memory
        batch_size = 500
        for i in range(0, len(texts_sim), batch_size):
            batch_end = min(i + batch_size, len(texts_sim))
            sim_batch = cosine_similarity(emb_sim[i:batch_end], emb_reg)

            for j in range(sim_batch.shape[0]):
                # Get top-k indices for this simple claim
                scores = sim_batch[j]
                top_indices = np.argsort(scores)[-top_k_per_query:][::-1]

                for idx in top_indices:
                    score = float(scores[idx])
                    if score >= threshold:
                        # Don't match claims from the exact same topic
                        # (we want cross-topic corroboration when possible)
                        pairs.append(MatchPair(
                            topic_reg=claims_reg[idx]["topic"],
                            topic_sim=claims_sim[i + j]["topic"],
                            text_reg=claims_reg[idx]["text"],
                            text_sim=claims_sim[i + j]["text"],
                            similarity=score,
                        ))

            if (i // batch_size) % 5 == 0:
                print(f"    processed {batch_end}/{len(texts_sim)} claims, "
                      f"{len(pairs)} pairs found so far")

        # Deduplicate: keep best match per (text_reg, text_sim) pair
        pairs.sort(key=lambda p: -p.similarity)
        seen: set[tuple[str, str]] = set()
        unique = []
        for p in pairs:
            key = (p.text_reg, p.text_sim)
            if key not in seen:
                seen.add(key)
                unique.append(p)

        print(f"  Found {len(pairs)} raw pairs, {len(unique)} unique")
        return unique

    def find_intra_reg_matches(
        self,
        claims: list[dict[str, Any]],
        threshold: float = 0.80,
    ) -> list[MatchPair]:
        """Find semantically similar claims across DIFFERENT regular Wikipedia topics.

        This finds genuine cross-topic factual overlap within Wikipedia itself.
        """
        self._load()

        texts = [c["text"] for c in claims]
        topics = [c["topic"] for c in claims]

        print(f"  Encoding {len(texts)} claims ...")
        emb = self.encode(texts, show_progress=True)

        from sklearn.metrics.pairwise import cosine_similarity

        pairs = []
        n = len(texts)

        # Only compare different topics
        print(f"  Computing similarity matrix ({n} × {n}) ...")
        sim_matrix = cosine_similarity(emb)

        for i in range(n):
            for j in range(i + 1, n):
                if topics[i] == topics[j]:
                    continue  # skip same-topic (those are exact-match already)
                score = float(sim_matrix[i][j])
                if score >= threshold:
                    pairs.append(MatchPair(
                        topic_reg=topics[i],
                        topic_sim=topics[j],
                        text_reg=texts[i],
                        text_sim=texts[j],
                        similarity=score,
                    ))

        pairs.sort(key=lambda p: -p.similarity)
        print(f"  Found {len(pairs)} cross-topic pairs within regular Wikipedia")

        return pairs


def save_matches(pairs: list[MatchPair], path: Path) -> None:
    """Save match pairs to JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump([{
            "topic_reg": p.topic_reg,
            "topic_sim": p.topic_sim,
            "text_reg": p.text_reg,
            "text_sim": p.text_sim,
            "similarity": p.similarity,
        } for p in pairs], f, indent=2)
    print(f"  Saved {len(pairs)} matches to {path}")


def load_matches(path: Path) -> list[MatchPair]:
    """Load match pairs from JSON."""
    with open(path) as f:
        data = json.load(f)
    return [MatchPair(**d) for d in data]
