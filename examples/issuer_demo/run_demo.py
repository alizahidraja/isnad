#!/usr/bin/env python3
"""End-to-end issuer demo: claim in → graded → sealed → static files out.

Runs the full ISNAD grading pipeline on a worked claim, then seals the
resulting verdict as Live Verify files and writes them to ./public/verify/.

Run:
    python examples/issuer_demo/run_demo.py

Then serve the output and verify with the ISNAD client (or Paul's extension):
    cd examples/issuer_demo && python3 -m http.server 8000
    # ... and verify the claim page's text against verify:localhost:8000/verify
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from isnad.core.chain import Chain, ChainLinkSpec
from isnad.core.grading import grade_chain
from isnad.core.registry import Registry
from isnad.integrations.liveverify.issuer import (
    render_verdict,
    seal_verdict,
    write_issuer_files,
    write_verification_meta,
)
from isnad.types import ContentVerdict, NarratorGrade, TransformType

# ---------------------------------------------------------------------------
# Step 1 — a graded claim (the worked example from the paper, §4.5-ish)
# ---------------------------------------------------------------------------

claim_text = "the momentum of a photon is p = h/λ"

chain = Chain([
    ChainLinkSpec("source:openstax-vol3", 0, domain="physics"),
    ChainLinkSpec("pdf-scraper@1.2", 1, domain="physics", transform_type=TransformType.DESTRUCTIVE),
    ChainLinkSpec("ingest-model-v3", 2, domain="physics", transform_type=TransformType.GENERATIVE),
])

reg = Registry()
reg.register("source:openstax-vol3", "physics", grade=NarratorGrade.RELIABLE)
reg.register("pdf-scraper@1.2", "physics", grade=NarratorGrade.RELIABLE)
reg.register("ingest-model-v3", "physics", grade=NarratorGrade.ACCEPTABLE)

link_grades = [reg.get_grade(l.narrator_id, l.domain) for l in chain.links]
chain_grade = grade_chain(link_grades, [l.transform_type for l in chain.links], is_complete=True)
content_verdict = ContentVerdict.CONSISTENT

# ---------------------------------------------------------------------------
# Step 2 — render, seal, write
# ---------------------------------------------------------------------------

narrator_chain = [l.narrator_id for l in chain.links]
verdict_text = render_verdict(
    claim_text=claim_text,
    chain_grade=chain_grade.value,
    narrator_chain=narrator_chain,
    weakest_link="ingest-model-v3",  # the ACCEPTABLE link caps a would-be ṣaḥīḥ chain
    content_verdict=content_verdict.value,
)

verify_base = "verify:localhost:8000/verify"
sealed = seal_verdict(verdict_text, verify_base)

out_dir = Path(__file__).resolve().parent / "public" / "verify"
write_issuer_files(sealed, out_dir)
write_verification_meta(verify_base, out_dir)

print("Sealed verdict:")
print(f"  chain grade: {chain_grade.value}")
print(f"  hash:        {sealed.hash}")
print(f"  files →      {out_dir}")
print(f"\nTo verify: serve the dir (python3 -m http.server 8000) and select the")
print(f"claim text below, then run verify_claim() or Paul's extension.")
print(f"\n{sealed.page_body}")
