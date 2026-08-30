# Security Policy

## What ISNAD is — and is not

ISNAD grades **post-entry provenance**: who handled a claim after it entered
your pipeline, and how much you trust them. It is a *decision aid*, not a
security boundary on its own.

It does **not** verify that a source is authentic, that a claim is objectively
true, or that an input is faithful. The operator's boundary vetting is the
root of trust; ISNAD sits downstream of it. See
[`THREAT_MODEL.md`](THREAT_MODEL.md) for the full statement of what ISNAD
does and does not protect against.

## Supported versions

We patch only the **latest release**. Security fixes are released as patch
bumps and backported only if a severe issue affects a widely deployed older
version.

| Version | Supported |
| ------- | --------- |
| 2.18.x | ✅ |
| < 2.18 | ❌ |

## Reporting a vulnerability

If you believe you have found a security issue — especially one that lets a
quarantined narrator recover, lets a grade be forged, or lets the
integrity/precision distinction be bypassed — please report it privately:

**Email: <alizahidrajaa@gmail.com>**

Please do **not** open a public issue for a suspected vulnerability. Include:

1. A minimal reproduction.
2. The affected version and code path.
3. Whether the issue is integrity bypass (a permanent strike that can be
   lifted), precision non-recoverability (a recoverable strike that isn't),
   or a trust-elevation gap (a narrator graded higher than its evidence
   justifies).

You will receive an acknowledgment within 72 hours and an assessment within
14 days. We will credit you in the release notes unless you ask otherwise.

## Honesty is a security property

The framework's credibility is built on **not over-claiming**. If you find a
place where the code, the README's "What's Validated vs. What's Not" table, or
a docstring overstates what is enforced, please report it through the same
channel. An over-stated guarantee is a vulnerability in a trust framework,
even when no line of code is wrong.
