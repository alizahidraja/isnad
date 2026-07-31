"""Narrator identity resolution — versioned registry keys for endpoint drift.

Grades are keyed by alias@version when a resolved version is supplied on the
chain link.  Legacy alias-only lookups remain for missing/unknown versions.
"""

from __future__ import annotations

VERSION_SEPARATOR = "@"
UNKNOWN_VERSIONS = frozenset({"", "unknown"})


def is_unknown_version(version: str | None) -> bool:
    """Return True when version should fall back to legacy alias-only lookup."""
    if version is None:
        return True
    return version.strip().lower() in UNKNOWN_VERSIONS


def resolve_narrator_id(narrator_id: str, version: str | None) -> str:
    """Build the registry key for a chain link.

    When version is known, returns ``{narrator_id}@{version}`` unless the id
    is already versioned.  Otherwise returns the alias unchanged.
    """
    if is_unknown_version(version):
        return narrator_id
    if VERSION_SEPARATOR in narrator_id:
        return narrator_id
    return f"{narrator_id}{VERSION_SEPARATOR}{version}"


def parse_narrator_id(resolved_id: str) -> tuple[str, str | None]:
    """Split a resolved registry id into ``(alias, version)``."""
    if VERSION_SEPARATOR not in resolved_id:
        return resolved_id, None
    alias, version = resolved_id.rsplit(VERSION_SEPARATOR, 1)
    return alias, version or None
