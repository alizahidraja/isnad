# The 1,200-year-old trick for catching a sleeper agent

In 2024, an account named "Jia Tan" spent two years contributing genuinely
good, well-reviewed patches to xz-utils — the compression library inside most
of Linux — and was rewarded with maintainership. Then it shipped a backdoor
into the release tarball.

Classical hadith scholarship faced this exact problem eight centuries earlier,
and it had a name for the shape of it: the **sleeper narrator** — a transmitter
who is sound for a long period in order to earn the critics' trust, then spends
that trust once. And it had a remedy so precise that it maps onto xz
one-to-one.

## The problem: a grade is a single point, but a narrator is a timeline

ISNAD grades narrators — the "rijāl" — the way the hadith critics graded
transmitters. A narrator who transmits faithfully earns a high grade; one who
fabricates is struck down. The obvious failure mode is a single scalar grade:
Jia Tan, the moment the backdoor is discovered, is a *fabricator*. But the two
years of genuine patches before the backdoor were still transmitted by a
*reliable* hand.

One number can't say both. If you quarantine Jia Tan wholesale, you discard
two years of sound work. If you keep the grade, you understate the breach.

## The remedy: the *mukhtaliṭūn*, or "the declined"

The classical critics catalogued a class of transmitters called the
**mukhtaliṭūn** — those who were sound and then *declined* (classically through
age or illness; in xz, through a slow-motion takeover). Their rule was
surprisingly modern:

> **Do not re-grade the narrator as a whole. Date the decline, and accept what
> came before it.**

The decline is a *point in time*, not a property of the whole record.
Everything the narrator transmitted before that point stands; everything after
is suspect.

## The implementation: `get_grade_as_of()`

ISNAD's evidence log is append-only and timestamped. So the remedy falls out
of one method:

```python
reg.get_grade_as_of("jia", "compression", before_backdoor)  # -> RELIABLE
reg.get_grade_as_of("jia", "compression", after_backdoor)   # -> REJECTED
```

The grade is **re-derived** from the evidence recorded up to the instant you
ask about — it never reads the narrator's current, mutated state. It is a
reconstruction, not a guess. The result is two honest answers where one number
could only give a lie:

| Question | Grade |
| --- | --- |
| What grade did the 40 genuine patches get? | **RELIABLE** |
| What grade did the payload get? | **REJECTED** |

Nothing is discarded. The record is *dated*, not erased.

Run it: `python examples/sleeper_narrator_demo.py`.

## Why this matters beyond xz

Every trust system over time will face the same question: *is this narrator the
same narrator they were two years ago?* The answer is never yes-or-no — it's
*until when*. Period-sliced grades are the mechanical form of that answer, and
they compose with the rest of ISNAD's machinery:

- a **version bump** is a natural slice boundary (`alias@version`);
- a **quarantine** is a slice boundary too — the moment of active containment;
- a **dated integrity strike** lets an operator quarantine a payload era
  without re-litigating the genuine record.

The tradition that spent twelve centuries refining "how much should I trust
this report and the hands it passed through" had already solved the problem
that bit the Linux supply chain in 2024. This is that solution, in a library.

---

*See the xz case study (`docs/case-study-xz-sleeper-narrator.md`) by Paul
Hammant for the full mapping, and `tests/test_period_sliced.py` for the
guarantees this feature pins.*
