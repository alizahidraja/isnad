"""Live Verify text normalization — a byte-compatible Python port.

This mirrors the canonical JavaScript `normalizeText()` from
`live-verify/public/normalize.js` EXACTLY, so that a claim normalized here
hashes identically to one normalized by the browser extension or the mobile
apps.  That byte-compatibility is the whole point: ISNAD must produce the
same SHA-256 as any other Live Verify client, or verification fails.

The canonical algorithm (in order):

1. Document-specific normalization (charNormalization + ocrNormalizationRules)
   from verification-meta.json, if present.
2. Unicode character normalization: curly quotes → straight, en/em dash →
   hyphen, non-breaking space → space, ellipsis → three periods.
3. Line-by-line: strip leading/trailing whitespace, collapse internal runs.
4. Remove blank lines.
5. Join with '\\n', no trailing newline.

Verified against the `normalization-hashes/*.md` fixtures in the Live Verify
repo — the same cross-platform test vectors its own JS, Android, and iOS
implementations are held to.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Document-specific normalization (from verification-meta.json)
# ---------------------------------------------------------------------------


def apply_doc_specific_norm(text: str, metadata: dict | None) -> str:
    """Apply charNormalization and ocrNormalizationRules from metadata.

    Mirrors `applyDocSpecificNorm()` in the canonical JS.

    charNormalization is compact notation: "éèêë→e àáâä→a" means é→e, è→e,
    etc.  Each group is `sourceChars→targetChar` where targetChar is a single
    character.
    """
    if not metadata:
        return text

    result = text

    char_norm = metadata.get("charNormalization")
    if char_norm:
        for group in str(char_norm).strip().split():
            if "→" not in group:
                continue
            source_chars, target_char = group.split("→", 1)
            if len(target_char) != 1:
                continue
            for source_char in source_chars:
                result = result.replace(source_char, target_char)

    ocr_rules = metadata.get("ocrNormalizationRules")
    if isinstance(ocr_rules, list):
        for rule in ocr_rules:
            if not isinstance(rule, dict):
                continue
            pattern = rule.get("pattern")
            replacement = rule.get("replacement")
            if pattern and replacement is not None:
                try:
                    result = re.sub(pattern, str(replacement), result)
                except re.error:
                    # Canonical JS logs and continues on invalid regex.
                    continue

    return result


# ---------------------------------------------------------------------------
# Standard normalization
# ---------------------------------------------------------------------------


def normalize_text(text: str, metadata: dict | None = None) -> str:
    """Normalize claim text for hashing, byte-compatible with canonical JS.

    Args:
        text: Raw claim text (everything before the verify: line).
        metadata: Optional verification-meta.json dict for document-specific
            rules.

    Returns:
        The normalized text.  Hashing this with SHA-256 (UTF-8) yields the
        value Live Verify looks up.
    """
    text = apply_doc_specific_norm(text, metadata)

    # Unicode character normalization (canonical JS order).
    text = text.replace("\u201c", '"').replace("\u201d", '"').replace("\u201e", '"')
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u00ab", '"').replace("\u00bb", '"')
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = text.replace("\u00a0", " ")
    text = text.replace("\u2026", "...")

    # Line-by-line normalization.
    normalized_lines = []
    for line in text.split("\n"):
        line = line.lstrip()  # remove leading whitespace
        line = line.rstrip()  # remove trailing whitespace
        line = re.sub(r"\s+", " ", line)  # collapse internal whitespace
        if line:
            normalized_lines.append(line)

    return "\n".join(normalized_lines)


def sha256_hex(text: str) -> str:
    """SHA-256 of UTF-8 text, lowercase hex (canonical hashing)."""
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()
