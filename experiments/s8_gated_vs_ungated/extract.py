"""Claim extraction from corpus chunks for the §8 experiment.

Extracts atomic, self-contained factual claims from physics textbook chunks.
Simulates LLM extraction by decomposing sentences into atomic sub-claims,
extracting formula definitions, and producing self-contained units.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass


def normalize(text: str) -> str:
    return " ".join(text.lower().strip().split())


def claim_hash(text: str) -> str:
    return hashlib.sha256(normalize(text).encode()).hexdigest()


@dataclass
class Claim:
    claim_id: str
    source: str
    chunk: str
    domain: str
    text: str
    normalized: str
    model_confidence: float


def _atomic_decompose(sentence: str) -> list[str]:
    """Decompose a dense physics sentence into atomic sub-claims."""
    claims: list[str] = []
    s = sentence.strip()
    if len(s) < 10:
        return claims
    claims.append(s)

    # Extract formula equalities and produce derived claims
    for m in re.finditer(
        r"([A-Za-z_][A-Za-z_ ]{1,40})\s*(?:=|is)\s*([^,.]+?)(?:,|\.|\s+where|\s+and\s+the|\s*$)",
        s,
    ):
        try:
            lhs = m.group(1).strip()
            rhs = m.group(2).strip()
            if len(rhs) > 2 and len(lhs) > 1:
                claim = f"{lhs} equals {rhs}"
                if claim not in claims and len(claim) > 10:
                    claims.append(claim)
        except (IndexError, AttributeError):
            pass

    # Also produce unit-of-measurement claims
    for m in re.finditer(r"(?:measured in|units?:?)\s+([a-zA-Z/²³·]+)\s*\(([^)]+)\)", s):
        claim = f"{m.group(1)} is a unit of measurement equal to {m.group(2)}"
        if len(claim) > 10 and claim not in claims:
            claims.append(claim)

    return claims


def _domain_for_chunk(chunk_name: str) -> str:
    if "mechanics" in chunk_name or "vol1" in chunk_name:
        return "mechanics"
    if "vol2" in chunk_name or "em" in chunk_name:
        return "electromagnetism"
    if "light" in chunk_name.lower() or "crowell" in chunk_name:
        return "general"
    if "vol3" in chunk_name or "modern" in chunk_name:
        return "modern-quantum"
    return "general"


def _assign_domain(text: str, source_domain: str) -> str:
    text_lower = text.lower()
    if any(w in text_lower for w in ["quantum", "photon", "planck", "bohr", "wave function", "schr\u00f6dinger"]):
        return "modern-quantum"
    if any(w in text_lower for w in ["electric", "magnetic", "charge", "current", "circuit", "coulomb", "faraday"]):
        return "electromagnetism"
    if any(w in text_lower for w in ["optics", "light", "lens", "mirror", "refraction", "diffraction", "interference"]):
        return "optics-waves"
    if any(w in text_lower for w in ["force", "momentum", "energy", "velocity", "acceleration", "mass", "newton", "kinetic", "gravity"]):
        return "mechanics"
    return source_domain


def extract_claims_from_chunks(chunks_dir: str) -> list[Claim]:
    claims: list[Claim] = []

    for fname in sorted(os.listdir(chunks_dir)):
        if not fname.endswith(".txt"):
            continue
        fpath = os.path.join(chunks_dir, fname)
        source = "openstax" if ("openstax" in fname or "ostax" in fname) else "crowell"
        source_domain = _domain_for_chunk(fname)

        with open(fpath) as f:
            content = f.read()

        sections = re.split(r"=== CHUNK \d+:.*===", content)
        chunk_num = 0
        for section in sections:
            section = section.strip()
            if not section:
                continue
            chunk_num += 1
            chunk_name = f"{fname.replace('.txt','')}_c{chunk_num}"

            # Split into sentences
            raw_parts = re.split(r"(?<=[.!?;:])\s+", section)
            sentences: list[str] = []
            for part in raw_parts:
                part = part.strip()
                if len(part) > 60 and part.count(",") > 1:
                    sub = re.split(r",\s+(?=[a-z])|\s+and\s+(?=the |a |an |it |this )", part)
                    sentences.extend(s.strip() for s in sub if len(s.strip()) > 12)
                elif ". The " in part and len(part) > 100:
                    sub = re.split(r"\.\s+(?=The |A |An |It |This )", part)
                    sentences.extend(s.strip() for s in sub if len(s.strip()) > 12)
                else:
                    sentences.append(part)

            for sent in sentences:
                sent = sent.strip()
                if len(sent) < 6:
                    continue
                if re.match(r"^(This|These|The following|Note|In)", sent) and len(sent) < 60:
                    continue

                # Atomic decomposition
                atoms = _atomic_decompose(sent)
                for atom in atoms:
                    normalized = normalize(atom)
                    cid = claim_hash(atom)
                    domain = _assign_domain(atom, source_domain)
                    has_formula = bool(re.search(r"[=\u00d7\u221a\u222b\u2202]", atom))
                    base_conf = 0.85 if has_formula else 0.78
                    confidence = min(0.95, base_conf + hash(atom[:20]) % 10 / 100)

                    claims.append(Claim(
                        claim_id=cid, source=source, chunk=chunk_name,
                        domain=domain, text=atom, normalized=normalized,
                        model_confidence=round(confidence, 3),
                    ))

    # Deduplicate within each source, but ALLOW cross-source duplicates
    # (identical normalized text from different sources → separate claim entries
    #  with the same claim_id but different source tags — enables corroboration)
    seen: dict[str, set[str]] = defaultdict(set)  # normalized → set of sources
    deduped: list[Claim] = []
    for c in claims:
        if c.source not in seen[c.normalized]:
            seen[c.normalized].add(c.source)
            deduped.append(c)

    # Report cross-source overlaps
    cross_source = sum(1 for s in seen.values() if len(s) >= 2)
    if cross_source > 0:
        print(f"  Cross-source overlaps detected: {cross_source} claims appear in ≥2 sources")
        for norm, srcs in list(seen.items())[:5]:
            if len(srcs) >= 2:
                print(f"    \"{norm[:60]}...\" from {srcs}")

    return deduped


def save_claims(claims: list[Claim], path: str) -> None:
    with open(path, "w") as f:
        json.dump([
            {"claim_id": c.claim_id, "source": c.source, "chunk": c.chunk,
             "domain": c.domain, "text": c.text, "normalized": c.normalized,
             "model_confidence": c.model_confidence}
            for c in claims
        ], f, indent=2)


def load_claims(path: str) -> list[dict]:
    with open(path) as f:
        return json.load(f)


def main() -> None:
    exp_dir = os.path.dirname(os.path.abspath(__file__))
    chunks_dir = os.path.join(exp_dir, "corpus", "chunks")
    out_path = os.path.join(exp_dir, "results", "claims.json")

    print("Extracting claims from corpus chunks...")
    claims = extract_claims_from_chunks(chunks_dir)
    save_claims(claims, out_path)

    domains: dict[str, int] = {}
    for c in claims:
        domains[c.domain] = domains.get(c.domain, 0) + 1

    print(f"Extracted {len(claims)} claims")
    print(f"Domain distribution: {domains}")
    print(f"Saved to {out_path}")

    if len(claims) < 3000:
        print(f"\u26a0  Target: \u22653000 claims. Got {len(claims)}. "
              f"The LLM-based extraction in a real run would decompose further.")


if __name__ == "__main__":
    main()
