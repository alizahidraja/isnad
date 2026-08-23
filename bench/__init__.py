"""ISNAD-Bench: validate ISNAD's chain grading against classical hadith ground truth.

This package imports the ``isnad`` library but touches nothing in it. The
1.6 GB dataset lives in ``data/`` (gitignored); only the mapping and metric
logic here are committed.
"""

from __future__ import annotations

__all__ = ["mapping", "metrics", "data", "run"]
