"""Live Verify normalization fixtures — vendored from live-verify/live-verify.

These are the canonical cross-platform test vectors.  Each .md file's
*filename* is the expected SHA-256 hash of its normalized body text.
The same fixtures gate the Live Verify JS, Android, and iOS implementations.

Source: https://github.com/live-verify/live-verify/tree/main/normalization-hashes
License: Apache-2.0 (code) / CC BY-SA 4.0 (content) — see upstream LICENSING.md.

The `canonical-normalize.js` is the canonical JavaScript `normalizeText()`
implementation.  ISNAD does NOT run it at runtime (that would require Node),
but tests may cross-check the Python port against it to guarantee byte
compatibility.  The port lives at `src/isnad/integrations/liveverify/normalize.py`.
"""
