"""Data loader for the corroboration experiment.

Fetches Wikipedia summaries for overlapping science topics and extracts
atomic factual claims (sentences that make truth-apt assertions).
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests


# ── Wikipedia topics with overlapping content (for cross-topic matching) ──

WIKIPEDIA_TOPICS = [
    "Quantum mechanics",
    "Wave-particle duality",
    "Black hole",
    "General relativity",
    "DNA",
    "Photosynthesis",
    "Natural selection",
    "Plate tectonics",
    "Periodic table",
    "Atom",
    "Electromagnetic radiation",
    "Thermodynamics",
]

# Pairs that should yield overlapping factual claims
OVERLAP_PAIRS = [
    ("Quantum mechanics", "Wave-particle duality"),
    ("Black hole", "General relativity"),
    ("DNA", "Natural selection"),
    ("Atom", "Periodic table"),
    ("Electromagnetic radiation", "Thermodynamics"),
]


@dataclass
class TopicData:
    """Data for one Wikipedia topic."""

    topic: str
    page_id: int = 0
    url: str = ""
    summary: str = ""
    sentences: list[str] = field(default_factory=list)
    fetched_at: str = ""


# ── Wikipedia API ──


class WikipediaLoader:
    """Load topic summaries from Wikipedia API."""

    API_URL = "https://en.wikipedia.org/w/api.php"

    def __init__(self, cache_dir: str | Path | None = None):
        if cache_dir is None:
            cache_dir = Path(__file__).parent / "data"
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._session = requests.Session()
        self._session.headers.update(
            {"User-Agent": "isnad-corroboration-experiment/1.0 (research)"}
        )

    def _cache_path(self, topic: str) -> Path:
        safe = re.sub(r"[^a-zA-Z0-9_]", "_", topic.lower())
        return self.cache_dir / f"{safe}.json"

    def _load_cache(self, topic: str) -> TopicData | None:
        path = self._cache_path(topic)
        if path.exists():
            try:
                with open(path) as f:
                    data = json.load(f)
                return TopicData(**data)
            except Exception:
                pass
        return None

    def _save_cache(self, td: TopicData) -> None:
        path = self._cache_path(td.topic)
        with open(path, "w") as f:
            json.dump(
                {
                    "topic": td.topic,
                    "page_id": td.page_id,
                    "url": td.url,
                    "summary": td.summary,
                    "sentences": td.sentences,
                    "fetched_at": td.fetched_at,
                },
                f,
                indent=2,
            )

    def get_summary(self, topic: str, force_refresh: bool = False) -> TopicData:
        """Get Wikipedia summary for a topic. Cached to disk."""
        if not force_refresh:
            cached = self._load_cache(topic)
            if cached is not None and cached.summary:
                return cached

        print(f"  Fetching Wikipedia: {topic}")

        params = {
            "action": "query",
            "format": "json",
            "prop": "extracts|info",
            "exintro": True,
            "explaintext": True,
            "inprop": "url",
            "titles": topic,
        }

        try:
            resp = self._session.get(self.API_URL, params=params, timeout=30)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
        except Exception as e:
            print(f"    ERROR: {e}")
            return TopicData(topic=topic, summary="")

        pages = data.get("query", {}).get("pages", {})
        if not pages:
            print(f"    No pages found for '{topic}'")
            return TopicData(topic=topic, summary="")

        # Get first page
        page_id_str = list(pages.keys())[0]
        if page_id_str == "-1":
            print(f"    Page not found for '{topic}'")
            return TopicData(topic=topic, summary="")

        page = pages[page_id_str]
        summary = page.get("extract", "")
        url = page.get("fullurl", "")
        page_id = int(page_id_str)

        # Split into sentences
        sentences = extract_sentences(summary)

        td = TopicData(
            topic=topic,
            page_id=page_id,
            url=url,
            summary=summary,
            sentences=sentences,
            fetched_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )

        self._save_cache(td)
        time.sleep(0.5)  # Rate limiting
        return td

    def load_all_topics(
        self, topics: list[str] | None = None
    ) -> dict[str, TopicData]:
        """Load all topics. Returns dict topic_name → TopicData."""
        if topics is None:
            topics = WIKIPEDIA_TOPICS
        result = {}
        for topic in topics:
            td = self.get_summary(topic)
            result[topic] = td
        return result


# ── Sentence extraction ──


def extract_sentences(text: str, min_length: int = 30) -> list[str]:
    """Extract fact-bearing sentences from text.

    Splits on sentence boundaries, filters out short fragments
    and sentences that are clearly not truth-apt.
    """
    # Split on sentence boundaries
    raw = re.split(r"(?<=[.!?])\s+", text)
    sentences = []
    for s in raw:
        s = s.strip()
        if len(s) < min_length:
            continue
        # Skip pure section headers, navigation, etc.
        if re.match(r"^[A-Z][a-z]+ [A-Z][a-z]+ \(", s):
            continue
        if s.startswith("==") or s.startswith("†"):
            continue
        sentences.append(s)
    return sentences


# ── Claim canonicalization ──


def normalize_claim(text: str) -> str:
    """Normalize claim text for comparison. Same as framework's normalize_claim_text."""
    return " ".join(text.lower().strip().split())


def find_near_duplicates(
    claims_a: list[str],
    claims_b: list[str],
    threshold: float = 0.60,
) -> list[tuple[str, str, float]]:
    """Find near-duplicate claim pairs across two sets using TF-IDF similarity.

    Returns list of (claim_a, claim_b, similarity_score) tuples.
    """
    # Build vocabulary from both sets
    all_claims = claims_a + claims_b

    # Simple word-overlap Jaccard for finding candidates
    def tokenize(text: str) -> set[str]:
        return set(re.findall(r"[a-z0-9]+", text.lower()))

    pairs = []
    tokens_a = [tokenize(c) for c in claims_a]
    tokens_b = [tokenize(c) for c in claims_b]

    for i, ta in enumerate(tokens_a):
        if len(ta) < 3:
            continue
        for j, tb in enumerate(tokens_b):
            if len(tb) < 3:
                continue
            if not ta or not tb:
                continue
            jaccard = len(ta & tb) / len(ta | tb)
            if jaccard >= threshold:
                pairs.append((claims_a[i], claims_b[j], jaccard))

    # Sort by similarity descending
    pairs.sort(key=lambda x: -x[2])
    return pairs


# ── Main ──

if __name__ == "__main__":
    loader = WikipediaLoader()
    print("Loading Wikipedia topics...")
    all_data = loader.load_all_topics()

    for topic, td in all_data.items():
        print(f"\n{topic}:")
        print(f"  Page ID: {td.page_id}")
        print(f"  Sentences: {len(td.sentences)}")
        for i, s in enumerate(td.sentences[:3]):
            print(f"    [{i}] {s[:100]}...")

    # Check for overlaps
    print("\n\nOverlapping claims across topic pairs:")
    for t_a, t_b in OVERLAP_PAIRS:
        if t_a in all_data and t_b in all_data:
            pairs = find_near_duplicates(
                all_data[t_a].sentences,
                all_data[t_b].sentences,
                threshold=0.40,
            )
            print(f"\n  {t_a} ↔ {t_b}: {len(pairs)} near-duplicates found")
            for ca, cb, score in pairs[:2]:
                print(f"    [{score:.3f}] {ca[:80]}...")
                print(f"             {cb[:80]}...")
