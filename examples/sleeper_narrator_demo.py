"""The sleeper narrator — period-sliced grades in action (issue #43).

A "sleeper narrator" is an identity that transmits faithfully for a long
period to earn a grade, then spends that grade once on one target — the xz-utils
backdoor (CVE-2024-3094) is the canonical example.  See
``docs/case-study-xz-sleeper-narrator.md``.

This demo shows the *ikhtilāṭ* remedy: the classical critics did not re-grade a
declined narrator wholesale — they **dated the decline** and accepted what came
before it.  ISNAD's ``get_grade_as_of()`` re-derives a narrator's grade at any
past instant from the append-only evidence log, so an operator can quarantine
the payload era while preserving the genuine record.

Run:  python examples/sleeper_narrator_demo.py
"""

from __future__ import annotations

from datetime import UTC, datetime

from isnad import Registry
from isnad.types import NarratorGrade


def main() -> None:
    print("=" * 68)
    print("SLEEPER NARRATOR — period-sliced grades (the ikhtilāṭ remedy)")
    print("=" * 68)

    reg = Registry()
    reg.register("jia", "compression")

    # Two years of genuine, well-reviewed work: 40 claims survive review.
    print("\nJia contributes 40 genuine patches over two years...")
    for i in range(40):
        reg.record_survival("jia", "compression", f"patch-{i}", "reviewer")

    print(f"  grade after the genuine run: {reg.get_grade('jia', 'compression').value}")

    # Snapshot the timeline: everything up to here is the *genuine* record.
    before_backdoor = datetime.now(UTC)

    # The backdoor is discovered; the operator quarantines the narrator.
    reg.quarantine("jia", "compression", "caught injecting a backdoor")
    print(f"\n  the backdoor is discovered and Jia is quarantined")
    print(f"  live grade now: {reg.get_grade('jia', 'compression').value}")

    print("\n" + "-" * 68)
    print("THE PERIOD-SLICED QUESTION: which claims were transmitted by whom?")
    print("-" * 68)

    # Re-derive the grade *as of* a moment before the decline.
    before = reg.get_grade_as_of("jia", "compression", before_backdoor)
    after = reg.get_grade_as_of("jia", "compression", datetime.now(UTC))

    print(f"  grade BEFORE the decline:  {before.value.upper()}")
    print(f"  grade AFTER  the decline:  {after.value.upper()}")

    print("\n  This is the ikhtilāṭ remedy, made mechanical:")
    print("  - the 40 genuine patches were transmitted by a RELIABLE narrator;")
    print("  - the payload was transmitted by a REJECTED (quarantined) narrator.")
    print("  - nothing is discarded; the record is *dated*, not erased.")

    print("\n" + "=" * 68)
    print("Done.")
    print("=" * 68)


if __name__ == "__main__":
    main()
