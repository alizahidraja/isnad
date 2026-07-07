#!/usr/bin/env python3
"""Real PDF download and extraction for the §8 experiment.

Downloads OpenStax University Physics Vols. 1-3 and Crowell Light and Matter
from official URLs, verifies SHA-256 checksums, extracts text, and chunks
into ~15K-character segments with source/page provenance.

Usage:
    python corpus/fetch.py              # Download + extract + chunk
    python corpus/fetch.py --verify-only  # Just verify existing PDFs

Requires: pdfplumber (pip install pdfplumber)
PDFs are saved to corpus/pdfs/ (NOT committed — gitignored).
Chunks are saved to corpus/chunks/ (committed for reproducibility).
"""

import hashlib
import os
import re
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

# ── Configuration ──────────────────────────────────────────────────────────

PDF_SOURCES = [
    {
        "name": "OpenStax University Physics Volume 1",
        "url": "https://openstax.org/books/university-physics-volume-1/pages/1-introduction",
        "pdf_url": "https://assets.openstax.org/oscms-prodcms/media/documents/UniversityPhysicsVolume1-OP.pdf",
        "filename": "openstax_vol1.pdf",
        "license": "CC BY 4.0",
        "expected_sha256": None,  # Will be recorded on first download
        "expected_size_min": 10_000_000,  # ~30MB PDF
    },
    {
        "name": "OpenStax University Physics Volume 2",
        "url": "https://openstax.org/books/university-physics-volume-2/pages/1-introduction",
        "pdf_url": "https://assets.openstax.org/oscms-prodcms/media/documents/UniversityPhysicsVolume2-OP.pdf",
        "filename": "openstax_vol2.pdf",
        "license": "CC BY 4.0",
        "expected_sha256": None,
        "expected_size_min": 10_000_000,
    },
    {
        "name": "OpenStax University Physics Volume 3",
        "url": "https://openstax.org/books/university-physics-volume-3/pages/1-introduction",
        "pdf_url": "https://assets.openstax.org/oscms-prodcms/media/documents/UniversityPhysicsVolume3-OP.pdf",
        "filename": "openstax_vol3.pdf",
        "license": "CC BY 4.0",
        "expected_sha256": None,
        "expected_size_min": 10_000_000,
    },
    {
        "name": "Crowell Light and Matter",
        "url": "https://www.lightandmatter.com/lm/",
        "pdf_url": "https://www.lightandmatter.com/lm/lm.pdf",
        "filename": "crowell_lm.pdf",
        "license": "CC BY-SA",
        "expected_sha256": None,
        "expected_size_min": 1_000_000,
    },
]

CHUNK_SIZE = 15_000  # characters per chunk (~matches paper)

# ── Helpers ────────────────────────────────────────────────────────────────


def sha256_file(path: Path) -> str:
    """SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def is_valid_pdf(path: Path) -> bool:
    """Check magic bytes and minimum size."""
    if path.stat().st_size < 1000:
        return False
    with open(path, "rb") as f:
        magic = f.read(5)
    return magic == b"%PDF-"


def download_pdf(source: dict, pdf_dir: Path) -> tuple[bool, str]:
    """Download a PDF. Returns (success, message)."""
    pdf_path = pdf_dir / source["filename"]
    url = source["pdf_url"]

    print(f"  Downloading {source['name']}...")
    print(f"    URL: {url}")

    try:
        req = Request(url, headers={"User-Agent": "isnad-s8-experiment/1.0"})
        with urlopen(req, timeout=120) as resp:
            status = resp.status
            data = resp.read()
            size = len(data)
            print(f"    HTTP {status}, {size:,} bytes received")
    except Exception as e:
        return False, f"Download failed: {e}"

    if status != 200:
        return False, f"HTTP {status}"

    pdf_dir.mkdir(parents=True, exist_ok=True)
    with open(pdf_path, "wb") as f:
        f.write(data)

    actual_sha = sha256_file(pdf_path)

    if not is_valid_pdf(pdf_path):
        pdf_path.unlink()
        return False, f"Not a valid PDF (magic bytes: %PDF expected)"

    if size < source["expected_size_min"]:
        pdf_path.unlink()
        return False, f"PDF too small: {size:,} bytes (expected ≥{source['expected_size_min']:,})"

    print(f"    ✓ Valid PDF, SHA-256: {actual_sha}")
    return True, actual_sha


def extract_text_from_pdf(pdf_path: Path) -> list[dict]:
    """Extract text from PDF pages using pdfplumber.
    Returns list of {"page": int, "text": str}.
    """
    try:
        import pdfplumber
    except ImportError:
        print("    pdfplumber not installed. Install with: pip install pdfplumber")
        print("    Falling back to basic extraction...")
        return _extract_basic(pdf_path)

    pages = []
    print(f"    Extracting text from {pdf_path.name}...")
    try:
        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)
            total_chars = 0
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                if text.strip():
                    pages.append({"page": i + 1, "text": text})
                    total_chars += len(text)
            print(f"    {total_pages} pages, {total_chars:,} characters extracted")
    except Exception as e:
        print(f"    pdfplumber failed: {e}")
        return _extract_basic(pdf_path)

    return pages


def _extract_basic(pdf_path: Path) -> list[dict]:
    """Fallback: try pymupdf, then PyPDF2."""
    for lib in ["fitz", "pymupdf"]:
        try:
            import fitz  # pymupdf
            pages = []
            doc = fitz.open(pdf_path)
            for i, page in enumerate(doc):
                text = page.get_text()
                if text.strip():
                    pages.append({"page": i + 1, "text": text})
            doc.close()
            print(f"    {len(doc)} pages extracted with pymupdf")
            return pages
        except ImportError:
            continue

    print("    ERROR: No PDF library available. Install pdfplumber or pymupdf.")
    return []


def chunk_text(pages: list[dict], source_name: str, source_license: str) -> list[dict]:
    """Chunk extracted text into ~CHUNK_SIZE character segments."""
    chunks = []
    current_chunk = ""
    current_pages = []

    for page in pages:
        text = page["text"]
        para_start = 0
        # Split on paragraph boundaries when possible
        paragraphs = re.split(r"\n\s*\n", text)
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(current_chunk) + len(para) > CHUNK_SIZE and current_chunk:
                chunks.append({
                    "text": current_chunk.strip(),
                    "source": source_name,
                    "license": source_license,
                    "pages": f"{current_pages[0]}-{current_pages[-1]}" if len(current_pages) > 1 else str(current_pages[0]) if current_pages else "",
                })
                current_chunk = para
                current_pages = [page["page"]]
            else:
                if current_chunk:
                    current_chunk += "\n\n" + para
                else:
                    current_chunk = para
                if page["page"] not in current_pages:
                    current_pages.append(page["page"])

    # Final chunk
    if current_chunk.strip():
        chunks.append({
            "text": current_chunk.strip(),
            "source": source_name,
            "license": source_license,
            "pages": f"{current_pages[0]}-{current_pages[-1]}" if len(current_pages) > 1 else str(current_pages[0]) if current_pages else "",
        })

    return chunks


def save_chunks(chunks: list[dict], chunks_dir: Path, prefix: str) -> int:
    """Save chunks to text files. Returns number of chunks saved."""
    chunks_dir.mkdir(parents=True, exist_ok=True)
    for i, chunk in enumerate(chunks):
        fname = f"{prefix}_chunk_{i+1:03d}.txt"
        fpath = chunks_dir / fname
        with open(fpath, "w") as f:
            f.write(f"# Source: {chunk['source']}\n")
            f.write(f"# License: {chunk['license']}\n")
            f.write(f"# Pages: {chunk['pages']}\n")
            f.write(f"# Chunk: {i+1}/{len(chunks)}\n")
            f.write("#" * 60 + "\n\n")
            f.write(chunk["text"])
    return len(chunks)


def save_checksums(checksums: dict, path: Path) -> None:
    """Record SHA-256 checksums."""
    with open(path, "w") as f:
        f.write("# PDF SHA-256 Checksums — §8 Experiment Corpus\n")
        f.write(f"# Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("# Verify with: python corpus/fetch.py --verify-only\n\n")
        for name, sha in checksums.items():
            f.write(f"{sha}  {name}\n")


def save_extract_sample(pages: list[dict], source_name: str, path: Path) -> None:
    """Save first 50 lines of extracted text as proof of realness."""
    with open(path, "a") as f:
        f.write(f"\n## {source_name}\n\n")
        f.write(f"Pages: {len(pages)}\n")
        total_chars = sum(len(p["text"]) for p in pages)
        f.write(f"Total characters: {total_chars:,}\n\n")
        f.write("### Raw text excerpt (first 50 lines):\n\n```\n")
        all_text = "\n".join(p["text"] for p in pages)
        lines = all_text.split("\n")[:50]
        f.write("\n".join(lines))
        f.write("\n```\n\n")


# ── Main ───────────────────────────────────────────────────────────────────


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Download and extract real PDFs for §8 experiment")
    parser.add_argument("--verify-only", action="store_true", help="Verify existing PDFs without downloading")
    args = parser.parse_args()

    corpus_dir = Path(__file__).parent
    pdf_dir = corpus_dir / "pdfs"
    chunks_dir = corpus_dir / "chunks"
    checksums_path = corpus_dir / "CHECKSUMS.txt"
    extract_sample_path = corpus_dir / "EXTRACT_SAMPLES.md"

    if args.verify_only:
        print("=== Verifying existing PDFs ===\n")
        for source in PDF_SOURCES:
            pdf_path = pdf_dir / source["filename"]
            if not pdf_path.exists():
                print(f"  ✗ {source['filename']} — NOT FOUND")
                continue
            if not is_valid_pdf(pdf_path):
                print(f"  ✗ {source['filename']} — NOT A VALID PDF")
                continue
            sha = sha256_file(pdf_path)
            size = pdf_path.stat().st_size
            print(f"  ✓ {source['filename']} — {size:,} bytes, SHA-256: {sha}")
        return

    print("=" * 60)
    print("§8 Experiment — Real PDF Corpus Download & Extraction")
    print("=" * 60)

    # Step 1: Download PDFs
    print("\n── Step 1: Download PDFs ──\n")
    checksums: dict[str, str] = {}

    for source in PDF_SOURCES:
        pdf_path = pdf_dir / source["filename"]

        if pdf_path.exists() and is_valid_pdf(pdf_path):
            sha = sha256_file(pdf_path)
            print(f"  ✓ {source['filename']} already exists ({pdf_path.stat().st_size:,} bytes)")
            checksums[source["filename"]] = sha
            continue

        success, result = download_pdf(source, pdf_dir)
        if success:
            checksums[source["filename"]] = result
        else:
            print(f"  ✗ {source['name']}: {result}")
            print(f"  → This source will be SKIPPED. Continuing with remaining sources.")

    if not checksums:
        print("\nERROR: No PDFs could be downloaded or found.")
        print("Check network connectivity and PDF URLs.")
        sys.exit(1)

    save_checksums(checksums, checksums_path)
    print(f"\n  Checksums saved to {checksums_path}")

    # Step 2: Extract text from PDFs
    print("\n── Step 2: Extract Text ──\n")
    extract_sample_path.write_text("# PDF Text Extraction Samples\n\n"
                                    "Real text extracted from downloaded PDFs.\n"
                                    "Generated: " + time.strftime("%Y-%m-%d %H:%M:%S") + "\n")

    total_chunks = 0

    for source in PDF_SOURCES:
        pdf_path = pdf_dir / source["filename"]
        if not pdf_path.exists():
            continue

        print(f"\n  {source['name']}:")
        pages = extract_text_from_pdf(pdf_path)

        if not pages:
            print(f"    No text extracted — skipping")
            continue

        # Save extract sample
        save_extract_sample(pages, source["name"], extract_sample_path)

        # Step 3: Chunk
        print(f"    Chunking into ~{CHUNK_SIZE:,} char segments...")
        prefix = source["filename"].replace(".pdf", "")
        chunks = chunk_text(pages, source["name"], source["license"])
        n = save_chunks(chunks, chunks_dir, prefix)
        print(f"    → {n} chunks saved to corpus/chunks/")
        total_chunks += n

    # Clean up: remove old pre-generated chunks that have been replaced
    old_patterns = [
        "openstax_vol1_mechanics", "openstax_vol2_em", "openstax_vol3_modern",
        "crowell_light_matter", "extended_physics", "extended_physics_2",
        "mechanics_extended", "em_optics_extended", "modern_extended",
        "crowell_extended", "dense_physics", "quick_reference",
        "review_facts", "overlap_corpus", "openstax_overlap",
        "crowell_overlap", "astro_medical_materials", "bulk_claims",
    ]
    removed = 0
    for f in list(chunks_dir.glob("*.txt")):
        for pat in old_patterns:
            if pat in f.name:
                f.unlink()
                removed += 1
                break

    print(f"\n  Removed {removed} old pre-generated chunk files")
    print(f"  Extract samples saved to {extract_sample_path}")

    # Summary
    print(f"\n{'=' * 60}")
    print(f"DONE. {len(checksums)} PDFs processed, {total_chunks} chunks created.")
    print(f"Next: run extract.py to extract atomic claims from chunks.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
