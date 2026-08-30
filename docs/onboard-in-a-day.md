# Onboard in a day — three copy-paste recipes

ISNAD is a **grading engine to embed**, not a turnkey app. It grades the
**transmitters and the chain**, not just the claim: every claim carries an
ordered chain of narrators (source → scraper → model), each narrator has a grade
in a living registry, the chain is capped at its weakest link, and the
*fabricated* (mawḍūʿ) tier is active containment, not a label.

This page is the shortest honest path to real value for the three users ISNAD
was audited for. Each recipe is self-contained. Read the **honesty contract**
at the bottom before you ship any of them.

---

## Recipe 1 — Self-maintaining knowledge base (LLM-wiki)

**The value:** no open-source tool grades *who* a claim came from and *how* it
got there. Your wiki pages become claims whose provenance is graded and
re-graded as new evidence arrives.

**The honest limit:** ISNAD grades *transmission*; it does not judge the truth
of your domain content by magic. It will surface "this claim entered through an
unverified scraper" — it will not tell you the claim is factually right. That is
the point.

```python
# kb.py — seed a registry, submit claims, read the graded surface
import os

os.environ["ISNAD_DATABASE_URL"] = "sqlite:///data/kb.db"

from isnad import Registry, grade
from isnad.core.registry import RegistryDB
from isnad.storage.sqlalchemy import get_session, init_db
from isnad.types import NarratorGrade

init_db()

with get_session() as session:
    reg = RegistryDB(session=session)
    reg.load()
    # Warm-start: a POPULATION PRIOR, not an observation. Seeded narrators are
    # prior-only — they can SERVE_WITH_CAVEAT, never plain-SERVE, until the
    # pipeline observes them (see the honesty contract).
    reg.registry.seed(
        "source:internal-docs", "kb", NarratorGrade.RELIABLE, source="operator"
    )
    reg.registry.seed(
        "model:gpt-4o@2026-01-15", "kb", NarratorGrade.ACCEPTABLE, source="operator"
    )
    reg.flush()

# A claim, its chain, and its grade:
v = grade(
    "The release shipped on 2026-08-29",
    ["source:internal-docs", "model:gpt-4o@2026-01-15"],
    reg.registry,
    domain="kb",
)
print(v.chain_grade, v.action, v.why)  # weakest link decides; `why` is the reason
```

**Day-one loop:** seed → submit → read `action` from the API or the `Verdict`.
Claims whose only support is a seed are caveat-served; the first
`record_survival` / post-hoc audit on a narrator unlocks plain serve.

**Give the critic your documents, not just prior claims.** The content critic
checks a claim against *what it was grounded in*. Pass the retrieved KB
documents as `corpus_docs` so consistency is judged against evidence, not
against other (unverified) claims:

```python
import requests
requests.post(
    "http://localhost:8000/v1/claims",
    json={"claim_text": "the release shipped 2026-08-29", "domain": "kb",
          "chain": [{"narrator_id": "source:internal-docs"}],
          "corpus_docs": ["release notes: shipped 2026-08-29"]},
    headers={"X-API-Key": "isnad-admin"},
)
```

(An operator-supplied corpus is an assumption, not an observation — ISNAD
records `critic_corpus_operator_docs` so the provenance is never hidden.)

**Serve the graded surface, not the raw table:**

```python
from isnad.api.app import app  # or run `uv run isnad api`
# GET /v1/claims            -> served-only (containment) surface
# GET /v1/claims?served_only=false -> audit view (everything, incl. quarantined)
```

---

## Recipe 2 — Medical RAG (conservative by default)

**The value:** RAGAS / Patronus / Galileo / TruLens grade *outputs*. None grades
the *transmission*: which source, which retriever, which model, and whether that
chain is trustworthy. A medical answer is only as good as its chain.

**The safety setting.** Put the high-stakes domain in *hold* mode: a
prior-only (unobserved) narrator then downgrades any serve to REVIEW, so a
seeded-but-never-observed source can never be served as-if-verified.

```bash
# Hold every domain, or just the high-stakes ones:
export ISNAD_SERVE_GATE=hold            # strictest: prior-only -> REVIEW everywhere
# or: export ISNAD_SERVE_HOLD_DOMAINS=medical,pediatric
```

```python
# medical_rag.py
from isnad import Registry
from isnad.integrations.langchain import IsnadTracer
from isnad.integrations.langchain.middleware import gate

registry = Registry()  # your operator-assigned grades live here

# 1. Trace the actual retrieval -> model chain (retrieved docs are the corpus,
#    so the content critic judges the claim against what was actually read).
tracer = IsnadTracer(registry, domain="medical")

# 2. Grade + gate each claim the moment it enters:
result = gate(
    "ibuprofen 200mg is safe for this patient",
    chain=["source:uptodate", "model:med-llm@2026-06"],
    registry=registry,
    domain="medical",
)
if result.gated:
    # hold — do not surface to the clinician
    ...
```

**The invariant you must keep:** a `REVIEW`/`QUARANTINE`/`REJECT` verdict is
containment, not a suggestion. Do not render `gated` output to a patient-facing
surface. A seeded source is an *assumption*; only an observed or human-vetted
narrator plain-serves.

---

## Recipe 3 — Legal RAG (chain-of-custody for re-summarization)

**The value:** every legal-AI vendor validates *authority*; none grades
*transmission*. The unique risk in legal work is the **summary-of-a-summary
cited back as primary**: a claim re-summarized through several agents loses its
connection to the underlying document. ISNAD records that connection as a
chain with full SHA-256 content hashes and an append-only audit trail.

**What custody gives you:** for a claim, you can answer *"what document, what
hash, through which models, at what time, and who changed it"* — and the audit
record self-hashes, so a tampered record fails verification.

```python
# legal_rag.py — capture the chain, then export a tamper-evident record
from isnad import Registry
from isnad.core.chain import Chain, ChainLinkSpec, store_claim
from isnad.types import TransformType
from isnad.audit.exporter import build_audit_record
from isnad.storage.sqlalchemy import get_session

registry = Registry()
chain = Chain([
    ChainLinkSpec("source:case-file-1234", 0, document_hashes=["<full sha256>"]),
    # Summarization is lossy -> destructive; the weak link caps the chain.
    ChainLinkSpec("model:summarizer@v3", 1, transform_type=TransformType.DESTRUCTIVE),
    ChainLinkSpec("model:citation-check@v2", 2, transform_type=TransformType.PASS_THROUGH),
])

with get_session() as session:
    # The claim must be stored before its audit record can be exported.
    claim = store_claim(session, "<the claim text>", "case-1234", chain)
    record = build_audit_record(
        claim_id=claim.claim_id, session=session, registry=registry,
    )
# record.record_hash -> self-hash; a re-export after any edit changes it.
```

**The invariant you must keep:** custody is only as good as the *ingest*. The
document content hash must be the full SHA-256 of what was actually retrieved —
a truncated prefix or a fabricated timestamp breaks the chain. ISNAD records
what it observed and marks the rest "not captured" (`None`), never invents it.

---

## The honesty contract (do not break)

1. **No numeric confidence.** Grades are ordinal (ṢAḤĪḤ/ḤASAN/ḌAʿĪF/MAWḌŪʿ) and
   the action is a route (serve/review/quarantine). Never emit a 0–100% score or
   a "probability of correctness".
2. **Evidence artifacts, not conformity.** Every downgrade carries its full
   chain + evidence log. A reviewer sees *why*, not a verdict in a vacuum.
3. **Grades are operator-assigned and local.** ISNAD does not import any
   universal "trust score" — your registry is your evidence.
4. **A seed is an assumption.** `prior_only` narrators caveat-serve at best;
   they plain-serve only after the pipeline observes them or a human vets them.
5. **MAWḌŪʿ is containment.** A rejected/quarantined narrator is not "less
   trusted" — it is stopped, and the quarantine is permanent per-person.
