# ISNAD → Live Verify issuer demo

Shows ISNAD acting as a Live Verify **issuer**: a graded claim is sealed into
publishable files, then verifiable by any Live Verify client (including Paul
Hammant's browser extension) or ISNAD's own `client.py`.

## Run it

```bash
python examples/issuer_demo/run_demo.py
```

This grades a worked claim (photon momentum, the paper's example), renders a
canonical verdict, hashes it, and writes into `examples/issuer_demo/public/verify/`:

- `<hash>` — the hash endpoint, containing `{"status": "verified"}`
- `<hash>.html` — the claim page (verdict text + `verify:` line)
- `verification-meta.json` — issuer metadata with an honest `authorityBasis`

## Verify it

```bash
cd examples/issuer_demo
python3 -m http.server 8000
```

Then, in another shell:

```python
from isnad.integrations.liveverify.client import verify_claim

# The claim page text (verdict + verify: line) — exactly what was hashed.
result = verify_claim(
    "ISNAD Claim Verdict\n...\nverify:localhost:8000/verify"
)
print(result.verified)  # True
```

## What the seal means — and doesn't

The seal proves the **verdict is the one ISNAD issued, unaltered**. It does
**not** prove the claim is true, and it does **not** mean anyone independent
endorses the grading.  In Live Verify this renders **amber**, not green —
which is correct.  ISNAD is self-attested; there is no external authority
endorsing its assessment.

See `src/isnad/integrations/liveverify/issuer.py` for the `authorityBasis`
and the point-in-time / revocation-on-regrade gap.
