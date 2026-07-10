"""Data loader v2 — full Wikipedia articles with source URLs and filtering.

Fetches complete page extracts from both en.wikipedia.org and
simple.wikipedia.org.  Every claim carries its source URL and page ID
for full provenance.

Filters out citation boilerplate, reference lists, and other non-factual
text before claim extraction.
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
    "Quantum mechanics", "General relativity", "Black hole", "Thermodynamics",
    "Electromagnetic radiation", "Nuclear fusion", "Superconductivity",
    "Standard Model", "Dark matter", "Entropy",
    "Periodic table", "Chemical bond", "Catalysis", "Electrolysis",
    "Polymer", "Acid–base reaction",
    "DNA", "Photosynthesis", "Natural selection", "Cell (biology)",
    "Enzyme", "Mitosis", "CRISPR",
    "Plate tectonics", "Greenhouse effect", "Carbon cycle",
    "Solar System", "Milky Way",
    "Atom", "Evolution",
]

# Pairs likely to have semantic overlap (for targeted matching)
OVERLAP_PAIRS = [
    ("Quantum mechanics", "Standard Model"),
    ("General relativity", "Black hole"),
    ("Thermodynamics", "Entropy"),
    ("DNA", "CRISPR"), ("DNA", "Mitosis"),
    ("Natural selection", "Evolution"),
    ("Atom", "Periodic table"), ("Atom", "Chemical bond"),
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


# ── Citation boilerplate patterns to filter ──

CITATION_PATTERNS = [
    r"^\s*Archived from the original",
    r"^\s*Retrieved\s",
    r"^\s*ISBN\s",
    r"^\s*doi\s*:",
    r"^\s*DOI\s*:",
    r"^\s*Vol\.\s",
    r"^\s*pp\.\s",
    r"^\s*Copyright\s",
    r"^\s*©\s",
    r"^\s*All rights reserved",
    r"^\s*This page was last edited",
    r"^\s*Citation\s",
    r"^\s*Cite\s",
    r"^\s*References?\s*$",
    r"^\s*Further reading\s*$",
    r"^\s*External links\s*$",
    r"^\s*Notes\s*$",
    r"^\s*Bibliography\s*$",
    r"^\s*See also\s*$",
    r"^\s*\d+\.\s",  # numbered list items
    r"^\s*\*\s",    # bullet points
    r"^\s*\[\d+\]",  # citation markers like [42]
    r"^\s*\[note\s",  # [note 1]
    r"\b(?:University Press|Cambridge University Press|Oxford University Press)\b",
]

# Patterns that look like pure URLs or references
URL_PATTERNS = [
    r"https?://",
    r"www\.",
    r"\.pdf\b",
    r"doi\.org",
]

def is_citation_boilerplate(text: str) -> bool:
    """Check if a sentence is citation boilerplate, not a factual claim."""
    t = text.strip()
    for pat in CITATION_PATTERNS:
        if re.search(pat, t, re.IGNORECASE):
            return True
    # If >40% of characters are in URLs, it's boilerplate
    url_chars = sum(1 for pat in URL_PATTERNS if re.search(pat, t))
    if url_chars >= 2 and len(t) < 200:
        return True
    # Pure numbers and symbols
    alpha_ratio = sum(1 for c in t if c.isalpha()) / max(1, len(t))
    if alpha_ratio < 0.3 and len(t) > 30:
        return True
    return False


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
            "User-Agent": "isnad-corroboration-v2/1.0 (academic research; mailto:alizahidrajaa@gmail.com)"
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
        """Get full article text with retry logic for rate limiting."""
        if not force_refresh:
            cached = self._load_cache(topic, source)
            if cached is not None and cached.text:
                return cached

        api = self.REGULAR_API if source == "regular" else self.SIMPLE_API
        label = "Regular" if source == "regular" else "Simple"
        raw: dict[str, Any] = {}

        for attempt in range(3):
            if attempt > 0:
                wait = 3 * (2 ** attempt)
                print(f"    Rate-limited, waiting {wait}s (attempt {attempt + 1}/3)...")
                time.sleep(wait)
            else:
                print(f"  [{label}] {topic}")

            try:
                raw = self._fetch_article(api, topic)
                break
            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg:
                    if attempt < 2:
                        continue
                    print(f"    ERROR (final): rate limit exhausted")
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
        time.sleep(0.3)
        return td

    def load_all(self, topics: list[str] | None = None) -> dict[str, dict[str, TopicData]]:
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
    """Extract fact-bearing sentences, filtering out boilerplate."""
    raw = re.split(r"(?<=[.!?])\s+", text)
    sentences = []
    for s in raw:
        s = s.strip()
        if len(s) < min_len or len(s) > max_len:
            continue
        if s.startswith("==") or s.startswith("†") or s.startswith("^"):
            continue
        if is_citation_boilerplate(s):
            continue
        sentences.append(s)
    return sentences


def normalize_claim(text: str) -> str:
    return " ".join(text.lower().strip().split())


if __name__ == "__main__":
    loader = DualWikipediaLoader()
    print("Testing...")
    for topic in ["Quantum mechanics", "DNA"]:
        reg = loader.get_article(topic, "regular")
        sim = loader.get_article(topic, "simple")
        print(f"\n{topic}:")
        print(f"  Regular: {len(reg.sentences)} sents, URL: {reg.url}")
        print(f"  Simple:  {len(sim.sentences)} sents, URL: {sim.url}")
        # Check for boilerplate in first 5 sentences
        for s in reg.sentences[:3]:
            bp = "BOILERPLATE" if is_citation_boilerplate(s) else "ok"
            print(f"    [{bp}] {s[:100]}...")
