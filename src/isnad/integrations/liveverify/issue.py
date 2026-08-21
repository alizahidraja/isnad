"""ISNAD issuer CLI — seal a graded claim into publishable Live Verify files.

Usage:
    python -m isnad.integrations.liveverify.issue --claim-file X --out ./public/verify/

Reads a claim file describing a graded verdict, renders the canonical verdict,
hashes it, and writes the issuer files (hash file + claim page +
verification-meta.json) into ``--out``.

The claim file is JSON:
    {
      "claim_text": "the momentum of a photon is p = h/λ",
      "chain_grade": "hasan",
      "narrator_chain": ["source:openstax", "scraper@1.2", "model:gpt-4o"],
      "weakest_link": "scraper@1.2",
      "content_verdict": "consistent",
      "verify_base": "verify:alizahidraja.com/verify"
    }

Honest limit: the seal is self-attested (amber in Live Verify).  See issuer.py.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from isnad.integrations.liveverify.issuer import (
    render_verdict,
    seal_verdict,
    write_issuer_files,
    write_verification_meta,
)


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seal an ISNAD verdict as Live Verify files")
    parser.add_argument(
        "--claim-file", required=True, type=Path, help="JSON file describing the verdict"
    )
    parser.add_argument("--out", required=True, type=Path, help="Output directory")
    args = parser.parse_args(argv)

    data = json.loads(args.claim_file.read_text())

    verify_base = data["verify_base"]
    verdict_text = render_verdict(
        claim_text=data["claim_text"],
        chain_grade=data["chain_grade"],
        narrator_chain=data["narrator_chain"],
        weakest_link=data["weakest_link"],
        content_verdict=data["content_verdict"],
    )
    sealed = seal_verdict(verdict_text, verify_base)

    write_issuer_files(sealed, args.out)
    write_verification_meta(verify_base, args.out)

    print(f"Sealed verdict → {sealed.hash}")
    print(f"  claim page: {args.out / (sealed.hash + '.html')}")
    print(f"  hash file:  {args.out / sealed.hash}")
    print(f"  meta:       {args.out / 'verification-meta.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
