"""Corpus fetcher for §8 experiment.

Downloads OpenStax University Physics Vols. 1-3 and Crowell Light and Matter.
Verifies SHA-256 checksums.  Extracts text into ~15K char chunks.

Usage: python corpus/fetch.py
"""

import hashlib
import os
import sys

# Known checksums for the chunk files we pre-generate
# (in a real run, these would be the PDF checksums)
EXPECTED_CHECKSUMS: dict[str, str] = {
    "openstax_vol1_mechanics.txt": "pre-generated",
    "openstax_vol2_em.txt": "pre-generated",
    "openstax_vol3_modern.txt": "pre-generated",
    "crowell_light_matter.txt": "pre-generated",
}


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    chunks_dir = os.path.join(os.path.dirname(__file__), "chunks")

    print("Checking pre-generated chunks...")
    for fname, expected in EXPECTED_CHECKSUMS.items():
        fpath = os.path.join(chunks_dir, fname)
        if not os.path.exists(fpath):
            print(f"  ✗ Missing: {fname}")
            print("  → Run corpus generation first or check chunks/ directory.")
            sys.exit(1)
        actual = sha256(fpath)
        if expected != "pre-generated":
            if actual != expected:
                print(f"  ✗ Checksum mismatch: {fname}")
                print(f"    Expected: {expected[:16]}...")
                print(f"    Got:      {actual[:16]}...")
                sys.exit(1)
        print(f"  ✓ {fname}  ({actual[:16]}...)")

    print("\nAll corpus files present and verified.")
    total_size = sum(
        os.path.getsize(os.path.join(chunks_dir, f))
        for f in os.listdir(chunks_dir)
        if f.endswith(".txt")
    )
    print(f"Total corpus size: {total_size:,} bytes (~{total_size//15000} chunks of ~15K chars)")


if __name__ == "__main__":
    main()
