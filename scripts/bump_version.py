#!/usr/bin/env python3
"""Bump the ISNAD version consistently across all version-bearing files.

Usage:
    python scripts/bump_version.py patch|minor|major [--dry-run]

Files updated:
    - pyproject.toml    ([project] version = "...")
    - src/isnad/__init__.py  (__version__ = "...")
    - CITATION.cff      (version: "...")

This script exists because the version lives in THREE places and they
drift apart (see git history: 2.0.9 on PyPI while __init__ said 2.0.7).
One command keeps them in lockstep.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FILES = [
    ROOT / "pyproject.toml",
    ROOT / "src" / "isnad" / "__init__.py",
    ROOT / "CITATION.cff",
]

# Per-file regex to find the current version.  Group 1 = the version string.
_PATTERNS: dict[Path, tuple[re.Pattern[str], str]] = {
    ROOT / "pyproject.toml": (
        re.compile(r'^version = "(\d+)\.(\d+)\.(\d+)"$', re.MULTILINE),
        'version = "{version}"',
    ),
    ROOT / "src" / "isnad" / "__init__.py": (
        re.compile(r'^__version__ = "(\d+)\.(\d+)\.(\d+)"$', re.MULTILINE),
        '__version__ = "{version}"',
    ),
    ROOT / "CITATION.cff": (
        re.compile(r'^version: "(\d+)\.(\d+)\.(\d+)"$', re.MULTILINE),
        'version: "{version}"',
    ),
}


# date-released is refreshed to today on every bump so the citation metadata
# never drifts from the actual release date.
_DATE_RELEASED_PATTERN = re.compile(r'^date-released: "[0-9-]+"$', re.MULTILINE)


def read_current() -> tuple[int, int, int]:
    """Read the current version, asserting all files agree."""
    versions: set[tuple[int, int, int]] = set()
    for path, (pat, _) in _PATTERNS.items():
        text = path.read_text()
        m = pat.search(text)
        if not m:
            print(f"ERROR: could not find version in {path}", file=sys.stderr)
            sys.exit(1)
        versions.add((int(m.group(1)), int(m.group(2)), int(m.group(3))))

    if len(versions) != 1:
        print(f"ERROR: version drift detected across files: {versions}", file=sys.stderr)
        sys.exit(1)
    return next(iter(versions))


def bump(current: tuple[int, int, int], part: str) -> tuple[int, int, int]:
    major, minor, patch = current
    if part == "major":
        return (major + 1, 0, 0)
    if part == "minor":
        return (major, minor + 1, 0)
    if part == "patch":
        return (major, minor, patch + 1)
    print(f"ERROR: unknown bump part '{part}' (use patch|minor|major)", file=sys.stderr)
    sys.exit(1)


def apply(new_version: tuple[int, int, int], dry_run: bool) -> None:
    version_str = ".".join(map(str, new_version))
    for path, (pat, template) in _PATTERNS.items():
        text = path.read_text()
        new_text, count = pat.subn(template.format(version=version_str), text)
        if count != 1:
            print(f"ERROR: expected 1 replacement in {path}, got {count}", file=sys.stderr)
            sys.exit(1)
        if dry_run:
            print(f"[dry-run] {path.relative_to(ROOT)}: -> {version_str}")
        else:
            path.write_text(new_text)
            print(f"updated {path.relative_to(ROOT)} -> {version_str}")

    # Refresh the release date in CITATION.cff to today so the metadata never
    # drifts from the actual release date.
    today = date.today().isoformat()
    citation = ROOT / "CITATION.cff"
    text = citation.read_text()
    new_text, count = _DATE_RELEASED_PATTERN.subn(f'date-released: "{today}"', text)
    if count == 1:
        if dry_run:
            print(f"[dry-run] {citation.relative_to(ROOT)}: date-released -> {today}")
        else:
            citation.write_text(new_text)


def main() -> None:
    parser = argparse.ArgumentParser(description="Bump ISNAD version across all files")
    parser.add_argument("part", choices=["patch", "minor", "major"])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    current = read_current()
    new_version = bump(current, args.part)
    print(f"bumping {'.'.join(map(str, current))} -> {'.'.join(map(str, new_version))}")
    apply(new_version, args.dry_run)


if __name__ == "__main__":
    main()
