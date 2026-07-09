"""Data loader v2 — full Wikipedia articles from regular + Simple English.

Fetches complete page extracts (not just intros) for 30 science topics
from both en.wikipedia.org and simple.wikipedia.org.

Regular Wikipedia: ~70K chars/article, ~200 factual sentences each
Simple Wikipedia: ~35K chars/article, different text by different editors

These are genuinely independent sources — different text, same facts.
Perfect for cross-source corroboration with semantic matching.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

# ── 30 science topics spanning physics, chemistry, biology, earth science ──

TOPICS = [
    # Physics
    "Quantum mechanics", "General relativity", "Black hole", "Thermodynamics",
    "Electromagnetic radiation", "Nuclear fusion", "Superconductivity",
    "Standard Model", "Dark matter", "Entropy",
    # Chemistry
    "Periodic table", "Chemical bond", "Catalysis", "Electrolysis",
    "Polymer", "Acid–base reaction",
    # Biology
    "DNA", "Photosynthesis", "Natural selection", "Cell (biology)",
    "Enzyme", "Mitosis", "CRISPR",
    # Earth / Space
    "Plate tectonics", "Greenhouse effect", "Carbon cycle",
    "Solar System", "Milky Way",
    # Cross-domain
    "Atom", "Evolution",
]

# Pairs likely to have semantic overlap (for targeted matching)
OVERLAP_PAIRS = [
    ("Quantum mechanics", "Standard Model"),
    ("General relativity", "Black hole"),
    ("Thermodynamics", "Entropy"),
    ("DNA", "CRISPR"),
    ("DNA", "Mitosis"),
    ("Natural selection", "Evolution"),
    ("Atom", "Periodic table"),
    ("Atom", "Chemical bond"),
    ("Photosynthesis", "Carbon cycle"),
    ("Greenhouse effect", "Carbon cycle"),
    ("Solar System", "Milky Way"),
    ("Nuclear fusion", "Solar System"),
    ("Cell (biology)", "Mitosis"),
    ("Electromagnetic radiation", "Quantum mechanics"),
    ("Dark matter", "Milky Way"),
]


@dataclass
class TopicData:
    topic: str
    source: str  # "regular" or "simple"
    page_id: int = 0
    url: str = ""
    text: str = ""
    sentences: list[str] = field(default_factory=list)
    fetched_at: str = ""


class DualWikipediaLoader:
    """Load full articles from both regular and Simple English Wikipedia."""

    REGULAR_API = "https://en.wikipedia.org/w/api.php"
    SIMPLE_API = "https://simple.wikipedia.org/w/api.php"

    def __init__(self, cache_dir: str | Path | None = None):
        if cache_dir is None:
            cache_dir = Path(__file__).parent / "data"
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "isnad-corroboration-v2/1.0 (academic research)"
        })

    def _fetch_article(self, api_url: str, topic: str) -> dict[str, Any]:
        params = {
            "action": "query", "format": "json",
            "prop": "extracts|info",
            "explaintext": True,
            "inprop": "url",
            "titles": topic,
        }
        resp = self._session.get(api_url, params=params, timeout=45)
        resp.raise_for_status()
        data = resp.json()
        pages = data.get("query", {}).get("pages", {})
        page_id_str = list(pages.keys())[0]
        if page_id_str == "-1":
            return {}
        page = pages[page_id_str]
        return {
            "page_id": int(page_id_str),
            "url": page.get("fullurl", ""),
            "text": page.get("extract", ""),
        }

    def _cache_path(self, topic: str, source: str) -> Path:
        safe = re.sub(r"[^a-zA-Z0-9_]", "_", topic.lower())
        subdir = "regular" if source == "regular" else "simple"
        return self.cache_dir / subdir / f"{safe}.json"

    def _load_cache(self, topic: str, source: str) -> TopicData | None:
        path = self._cache_path(topic, source)
        if path.exists():
            try:
                with open(path) as f:
                    d = json.load(f)
                return TopicData(**d)
            except Exception:
                pass
        return None

    def _save_cache(self, td: TopicData) -> None:
        path = self._cache_path(td.topic, td.source)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump({
                "topic": td.topic, "source": td.source,
                "page_id": td.page_id, "url": td.url,
                "text": td.text, "sentences": td.sentences,
                "fetched_at": td.fetched_at,
            }, f, indent=2)

    def get_article(self, topic: str, source: str = "regular",
                    force_refresh: bool = False) -> TopicData:
        """Get full article text for a topic from regular or simple Wikipedia.

        Caches to disk.  On HTTP 429 (rate limit), sleeps and retries up
        to 3 times with exponential backoff.
        """
        if not force_refresh:
            cached = self._load_cache(topic, source)
            if cached is not None and cached.text:
                return cached

        api = self.REGULAR_API if source == "regular" else self.SIMPLE_API
        label = "Regular" if source == "regular" else "Simple"
        raw: dict[str, Any] = {}

        for attempt in range(3):
            if attempt > 0:
                wait = 3 * (2 ** attempt)  # 6s, 12s, 24s
                print(f"    Rate-limited, waiting {wait}s (attempt {attempt + 1}/3)...")
                time.sleep(wait)
            else:
                print(f"  [{label}] {topic}")

            try:
                raw = self._fetch_article(api, topic)
                break  # success — exit retry loop
            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg:
                    if attempt < 2:
                        continue
                    print(f"    ERROR (final): rate limit exhausted after 3 attempts")
                else:
                    print(f"    ERROR: {e}")
                    break
                raw = {}

        text = raw.get("text", "") if raw else ""
        sentences = extract_factual_sentences(text)

        td = TopicData(
            topic=topic, source=source,
            page_id=raw.get("page_id", 0),
            url=raw.get("url", ""),
            text=text, sentences=sentences,
            fetched_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        self._save_cache(td)
        time.sleep(0.3)  # rate limit
        return td

    def load_all(self, topics: list[str] | None = None) -> dict[str, dict[str, TopicData]]:
        """Load all topics from both sources.

        Returns: {topic_name: {"regular": TopicData, "simple": TopicData}}
        """
        if topics is None:
            topics = TOPICS
        result: dict[str, dict[str, TopicData]] = {}
        for topic in topics:
            result[topic] = {
                "regular": self.get_article(topic, "regular"),
                "simple": self.get_article(topic, "simple"),
            }
        return result


def extract_factual_sentences(text: str, min_len: int = 40, max_len: int = 500) -> list[str]:
    """Extract fact-bearing sentences from article text."""
    raw = re.split(r"(?<=[.!?])\s+", text)
    sentences = []
    for s in raw:
        s = s.strip()
        if len(s) < min_len or len(s) > max_len:
            continue
        # Skip navigation, section headers, references
        if re.match(r"^[A-Z][a-z]+ [A-Z][a-z]+ \(", s):
            continue
        if s.startswith("==") or s.startswith("†") or s.startswith("^"):
            continue
        if re.match(r"^\d+\.\s", s):  # numbered list items
            continue
        # Skip pure citation/see-also lines
        if re.match(r"^(See also|References|External links|Further reading|Notes|Bibliography)", s):
            continue
        sentences.append(s)
    return sentences


def normalize_claim(text: str) -> str:
    """Normalize claim text for comparison."""
    return " ".join(text.lower().strip().split())


if __name__ == "__main__":
    loader = DualWikipediaLoader()
    print("Testing dual Wikipedia loader...\n")

    # Test a few topics
    for topic in ["Quantum mechanics", "DNA", "Plate tectonics"]:
        reg = loader.get_article(topic, "regular")
        sim = loader.get_article(topic, "simple")
        print(f"\n{topic}:")
        print(f"  Regular: {len(reg.sentences)} sentences, {len(reg.text):,} chars")
        print(f"  Simple:  {len(sim.sentences)} sentences, {len(sim.text):,} chars")
        if reg.sentences and sim.sentences:
            print(f"  Reg[0]: {reg.sentences[0][:100]}...")
            print(f"  Sim[0]: {sim.sentences[0][:100]}...")
