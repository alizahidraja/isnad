# Corpus Attribution
# §8 Validation Experiment — Gated vs. Ungated Serving

## Sources

### 1. OpenStax University Physics Volumes 1–3
- **Authors:** Samuel J. Ling, William Moebs, Jeff Sanny
- **Publisher:** OpenStax, Rice University
- **License:** Creative Commons Attribution 4.0 International (CC BY 4.0)
- **URL:** https://openstax.org/details/books/university-physics-volume-1
- **Volumes used:** 1 (Mechanics, Sound, Oscillations, Waves), 2 (Thermodynamics, Electricity & Magnetism), 3 (Optics, Modern Physics)

### 2. Light and Matter (series)
- **Author:** Benjamin Crowell
- **Publisher:** lightandmatter.com
- **License:** Creative Commons Attribution-ShareAlike (CC BY-SA)
- **URL:** https://www.lightandmatter.com/lm/

## License Compliance

- The OpenStax excerpts are used under CC BY 4.0. Attribution is provided above.
- The Crowell excerpts are used under CC BY-SA. Attribution is provided above.
- Per CC BY-SA terms, any derivative works based on the Crowell text (including
  corrupted/transformed versions in this experiment) are also shared under CC BY-SA.

## Corpus Provenance

- **411 of 417 chunk files** in `chunks/` are real PDF extractions downloaded from
  the official OpenStax and lightandmatter.com URLs, verified by SHA-256 checksums
  (recorded in `corpus/CHECKSUMS.txt`), and extracted via pdfplumber. Each chunk
  header includes the source PDF, license, and page range. Example header:
  `# REAL PDF — openstax_vol1.pdf, pages 36-39`
- **6 chunk files** are synthetic representative excerpts used for early-stage
  development and cross-source overlap testing. They are clearly marked with
  non-REAL-PDF headers.
- The raw PDFs (~203 MB total) are not committed to the repository (gitignored).
  Download them via `corpus/fetch.py`.
- The extracted text in `chunks/` represents short, attributed excerpts used for
  research validation purposes consistent with fair dealing / fair use.
- For the original full texts, visit the URLs above.
