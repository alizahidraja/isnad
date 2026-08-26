# Licensing Commitment

This document is a *public commitment*, made so that ambiguity about future
licensing can never be a reason not to depend on ISNAD or contribute to it.

## The core library is Apache-2.0, permanently

The `isnad` Python package — everything under `src/isnad/` — is and will remain
licensed under the **Apache License 2.0**. This is irrevocable and royalty-free,
including for commercial use. This commitment is not time-limited and will not be
revisited as a "future versions" clause: if ISNAD ever evolves, the core library
under `src/isnad/` stays Apache-2.0.

Rationale: a trust framework cannot ask its users to trust it on a licence they
have to re-check every release. The permission to fork, inspect, and vendor the
grading logic is part of the value — the "how do you know?" answer is only
credible if the answer's own machinery is open.

## What Apache-2.0 does *not* cover (and never will, from this repo)

- **Trademark and the "ISNAD" name.** The licence covers the code, not the brand.
- **Conformity, certification, or legal opinion.** Nothing in this repository
  certifies that a deployment is compliant with the EU AI Act, ISO/IEC 42001, the
  NIST AI RMF, or any other framework. The audit layer *produces evidence
  artifacts; it does not confer conformity.*
- **Hosted services.** The licence permits running ISNAD as a service; it does not
  entitle anyone to the author's infrastructure, support, or the "ISNAD" name on
  a commercial offering.

## If a commercial surface is ever built (open core, explicitly not committed)

There is currently **no** proprietary companion repository, and there may never be.
If one is ever created — for example, a multi-tenant registry, SSO, compliance
report generation, or retention/attestation infrastructure — it will live in a
**separate repository under its own licence**, and the boundary will be drawn so
that `src/isnad/` is never partially closed. This paragraph is a statement of
*where* any such line would be drawn, not an announcement that one will be drawn.

## Paper and documentation

The paper and documentation are licensed **CC BY 4.0**, as stated in the README.
