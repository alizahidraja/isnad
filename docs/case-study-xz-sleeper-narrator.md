# Case study: the xz-utils backdoor as a sleeper narrator

> **Status:** draft for discussion. Not yet referenced from the README.
>
> This document reads a real-world software supply-chain compromise through
> ISNAD's vocabulary. The goal is not to claim ISNAD would have stopped it —
> ISNAD grades claim transmission, not source code — but to use a case everyone
> in security already knows to make one specific attack pattern against ISNAD
> concrete, and to show which of ISNAD's existing design choices answer it and
> which do not.
>
> The case straddles a line, and the document is read best with that in
> mind. **§1–5 and §7 Tiers 1–2 use ISNAD as it exists today** — registry,
> per-domain grades, chain completeness, madār detection, the
> precision/integrity axis, versioned identity — applied to a supply chain
> rather than a multi-agent pipeline. **§6, §7 Tier 3 and §8 are where the
> case points beyond ISNAD** — semantic critics, period-sliced grades,
> evidence-not-grade federation, reproducible traces. The attack was strongest
> exactly where the second half lives; the first half is what would have
> stood in its way regardless.
>
> This is one half of a two-repo case study. The companion,
> [Case study: the xz-utils backdoor as a Live Verify release attestation](https://github.com/live-verify/live-verify/blob/main/docs/xz-release-attestation-case-study.md),
> reads the same incident from the document-verification side: what a
> release claim would have said on each side of the CVE (correctly
> `verified` for the backdoored release — authentic ≠ safe), the sideways
> endorser chain an open-source release can have, and why a revocation is
> the kind of evidence record §6 item 5 wants. See also §10.

---

## 1. What happened (established facts)

The following is not in dispute and is drawn from the public post-mortems of
CVE-2024-3094 (disclosed 29 March 2024).

- An account named **"Jia Tan"** (`JiaT75`) began submitting patches to
  **xz-utils** — the compression library behind `liblzma`, linked into a great
  deal of Linux userland — around late 2021/2022.
- Over roughly two years the account contributed clean, useful, well-reviewed
  work. It was granted commit access, then co-maintainership, and by 2023 was
  cutting releases.
- During the same period, other accounts with no footprint elsewhere
  (**"Jigar Kumar"**, **"Dennis Ens"**) appeared on the project mailing list to
  pressure the original sole maintainer, Lasse Collin, about slow progress and
  to argue for handing over control. They are widely taken to be sock puppets
  of the same operation.
- Several changes that later turned out to be **preparatory** landed well in
  advance: build-system changes enabling `ifunc` resolution, a request to
  disable `ifunc` under oss-fuzz, and a one-character "typo" that silently
  disabled a Landlock sandbox check.
- Releases **5.6.0** (24 Feb 2024) and **5.6.1** (9 Mar 2024) shipped a
  backdoor. The payload was hidden inside binary **test fixture files**; a
  modified `m4` macro present only in the release tarball (not in git)
  extracted and linked it during `configure`.
- The payload targeted **OpenSSH `sshd`** on distributions that patch `sshd` to
  link `libsystemd`, which transitively loads `liblzma`. It hooked RSA key
  verification and, on presentation of a specific attacker-held Ed448 key,
  executed attacker-supplied commands as root, pre-authentication.
- It was caught by **Andres Freund**, a PostgreSQL developer, who noticed
  `sshd` consuming unexpected CPU and Valgrind complaints, and pulled the thread.
  The backdoored versions had reached Debian unstable, Fedora rawhide/40 beta,
  openSUSE Tumbleweed, Arch and Kali, but not major stable releases.

## 2. What is *not* established

This matters for how the case should be described, and for what ISNAD can and
cannot learn from it.

- **Whether "Jia Tan" is a person.** The identity has never been established
  publicly, never charged, never attributed by any government on the record.
  Commit-timestamp analysis suggests a working pattern inconsistent with the
  Chinese name on the account. The consensus inference is a persona operated by
  a well-resourced (probably state-level) team, but that is inference from
  patience and sophistication, not evidence.
- **Motive and sponsor.** Unknown.
- **Whether a "hacked" or "coerced" defence could exist.** Nobody has raised
  one, because nobody has come forward. Hypothetically it is weak: the sock
  puppets, the multi-year trail of preparatory commits in a consistent style,
  and the fabricated-looking persona mean any "coercion" would have to cover
  the entire lifetime of the account — at which point "coerced" and "was
  always the operation" are indistinguishable from the outside.

The correct noun is therefore the **xz account** or the **Jia Tan persona**,
not "a developer." That phrasing is also the ISNAD-correct one: ISNAD grades
narrator *identities* by their *transmissions*, never humans by their
intentions. Whoever or whatever sat behind `JiaT75`, the narrator `JiaT75` did
the thing.

## 3. The attack pattern, in ISNAD's terms

Call it a **sleeper narrator**: an identity that transmits faithfully for a
long period in order to earn a grade, then spends that grade — once, on one
target.

This is distinct from **reputation farming**, which is the commodity version
("buy a +10k karma account"): no particular agenda, trust built to be *sold*.
The sleeper builds trust to be *spent*, and has a single payload in mind from
the start. The classical hadith literature knew the shape: fabricators who
first transmitted sound material to be accepted by the critics, and the
converse problem of the *mukhtaliṭūn* — narrators who were sound and then were
not, whose material the critics dated relative to the onset of decline.

Mapped onto ISNAD's objects:

| xz                                        | ISNAD                                                            |
| ----------------------------------------- | ---------------------------------------------------------------- |
| The `JiaT75` account                      | A **narrator** (`NarratorGrade` in the **registry**)             |
| Two years of clean patches                | A run of claims surviving review → grade climbs toward `RELIABLE` |
| Lasse Collin handing over maintainership  | **Operator boundary decision** — registering a narrator as trusted |
| Jigar Kumar / Dennis Ens                  | **Correlated chains** — apparently independent voices with one upstream (*madār*) |
| Preparatory commits (ifunc, Landlock typo) | Claims that pass **matn criticism** individually but are load-bearing for a later lie |
| The payload in test fixtures              | The **payload claim** — transmitted by a high-grade narrator, contradicting the corpus only if you look |
| Andres Freund                             | **`HUMAN_REVIEW`** arriving from outside the pipeline           |
| "Was Jia Tan hacked?"                     | **Endpoint identity** — is the narrator ID still the same narrator? |

## 4. Which ISNAD mechanisms answer it

**Per-domain grades.** ISNAD grades `(narrator, domain)`, not `narrator`. A
sleeper has to earn its grade in the *domain of the eventual lie*, where the
corpus is densest and matn criticism sharpest. Two years of clean compression
code would not, in ISNAD, buy any standing in a different domain.

**Matn criticism is independent of chain grade.** The decision matrix
(`core/decision.py`) refuses to let chain quality override content conflict: a
`SAHIH` chain carrying a `CONTRADICTION` verdict routes to `REVIEW`, not
`SERVE`. A `RELIABLE` narrator asserting something the corpus contradicts is
held regardless of its track record. (The xz payload's analogue here is weak —
it was *engineered* to have no observable contradiction until run under
specific conditions; see §5.)

**Integrity strikes are permanent and come only from humans.** `EvidenceAxis`
(`types.py`) splits narrator criticism into *precision* (ḍabṭ — windowed,
recoverable) and *integrity* (ʿadālah — permanent). Automated signals can only
ever record precision lapses, because an automated check knows an answer was
*wrong*, not that it was a *lie*. A deliberate fabrication, once established by
`HUMAN_REVIEW` or an explicit `INTEGRITY` tag, can never be lifted by later
good conduct. This is the direct answer to "but look at my 10,000 good
claims": the 10,000 earn precision credit; the one caught fabrication is an
integrity strike, and *al-jarḥ muqaddam ʿalā al-taʿdīl* — the impugnment
outranks the praise.

**Capped corroboration and madār detection.** The sock-puppet pattern is the
echo case. `SharedLineageDetector` collapses chains that share upstream, and
`CappedCorroborationPolicy` means that even genuinely independent chains can
lift a claim to `HASAN`, never to `SAHIH`. Volume has a ceiling.

**Endpoint identity.** For model narrators, grades are keyed `alias@version`;
a new deployment behind the same service name is a new identity with no
inherited track record. The "I was hacked" defence maps onto exactly this: an
account takeover is a *new narrator wearing an old narrator's ID*. ISNAD's
response is not to adjudicate the human but to ask whether the identity was
ever strong enough that the claim could be attributed to it at all.

**No shared registry.** Each operator's registry is local. There is no global
ISNAD ledger a sleeper (or a flood of sleepers) can poison; an adversary's
traces scattered across the internet are inert unless an operator deliberately
ingests their author as a narrator. This is a design choice worth keeping
explicit: the day grades become *importable* between operators, the sleeper
problem acquires a Sybil dimension it does not currently have.

## 5. Which mechanisms do *not* answer it — honest limits

**ISNAD grades transmission, not truth at the boundary.** The README says it
plainly: a `RELIABLE` fake publisher plus a clean pipeline yields a high chain
grade. The xz operation's real achievement was at the *boundary* — getting the
persona accepted as a maintainer. ISNAD can make the payoff of such an
acceptance small (per-domain, capped) and the exposure permanent (integrity
strike), but it cannot make an operator's onboarding good. Lasse Collin's
decision is the operator's decision, and ISNAD sits downstream of it.

**A payload with no observable contradiction passes matn.** The backdoor was
engineered so that nothing looked wrong until a specific key was presented to
a specific binary under specific linkage. The claim-world analogue is a lie
crafted to be consistent with the corpus at ingestion time and only
contradicted by evidence that arrives later. ISNAD's `POST_HOC_AUDIT` and
`SURVIVAL` evidence exist for this, but they fire *after* serving. Detection
is retrospective; containment is prospective.

**The preparatory commits are the hard case.** Each was individually
defensible. The Landlock typo *was* a typo, if you didn't know what came next.
ISNAD evaluates claims one at a time; a sequence of individually-sound claims
that are jointly load-bearing for a later lie is not something weakest-link
grading sees. Whether there is a tractable "this narrator's recent claims are
unusually *enabling*" signal is an open question, and probably not one ISNAD
should try to answer automatically — it is the kind of determination the
framework deliberately reserves for humans. (That said, ISNAD does not need
to read the diff itself; §8 covers what happens when something else does.)

**Discovery was luck.** Andres Freund was not auditing xz. ISNAD's `REVIEW`
queue exists so that human attention is spent where the grading says it is
ambiguous; a sleeper's whole strategy is to never be ambiguous until the
payload. The framework cannot manufacture the Freund.

## 6. Design implications worth considering

None of these are proposals yet; they are the places where this case points.

1. **Period-sliced grades (the ikhtilāṭ remedy).** The classical critics did
   not re-grade a declined narrator as a whole; they dated the decline and
   accepted transmissions from before it. ISNAD's integrity strike is currently
   a cap on the narrator. A *dated* strike — "everything from this narrator
   after timestamp T is suspect; everything before stands" — would let an
   operator quarantine a sleeper's payload era without discarding two years of
   claims that were, in fact, sound. `types.py` already names the
   *mukhtaliṭūn* in the `EvidenceAxis` docstring; this would be the mechanism.
   It also composes with endpoint identity: a version bump is a natural slice
   boundary.

2. **Pin policy and registry versions in the trace.** The `isnad_trace` v0.1
   schema records the grades a claim was served under. A post-incident auditor
   asking "was this decision correct under the rules then in force?" also
   needs *which* rules and *which* registry snapshot. Without that the trace
   answers "what was decided," not "whether it was decided correctly." This is
   the difference between an auditable record and a reproducible one.

3. **Name the no-federation invariant.** §4's last point — grades are local,
   never imported — is currently an absence rather than a stated rule. Stating
   it in the threat-model section of the README means the first contributor
   who proposes "let operators share registries" sees the cost up front.

4. **Keep integrity human-only.** The temptation after a case like xz is to
   add an automated "sleeper detector" that issues integrity strikes. The
   current design's refusal to do this — automated signals are precision,
   full stop — is correct and should survive the temptation. A false
   integrity strike is permanent by construction; the cost of a wrong one is
   exactly the cost the permanence was meant to impose on fabricators.
   §8 makes this concrete for machine critics.

5. **Share evidence, never grades.** Once distribution portals run ISNAD
   (§8), their registries become de facto authoritative because they sit at
   the chokepoint, and downstream operators will want to read them. That is
   grade import — the Sybil surface item 3 says ISNAD does not have. The
   resolution is to let operators exchange **evidence records** (facts:
   "critic X, version Y, flagged artifact Z for reason R at time T") and
   re-derive grades under their *own* policy and registry. Facts are cheap to
   verify and hard to forge in volume — an artifact either matches its tag or
   it does not; judgements are what an adversary wants to inject. This is
   what makes item 2 load-bearing rather than cosmetic: evidence can only be
   re-derived if the policy and registry it was produced under are pinned.

## 7. Where the datapoints were

If ISNAD had been in wide use at the outset of the sleeper work, which of the
operation's channels could have produced datapoints, and how automatically?
The public timeline gives eight channels.

| # | Channel | What the personas did there | Claim transmitted |
| --- | --- | --- | --- |
| 1 | GitHub PR on another project (libarchive, 2021) | `JiaT75`'s first known contribution: replaced `safe_fprintf` with `fprintf` under a cosmetic message | "harmless text fix" |
| 2 | xz-devel mailing list — patches (2022) | Jia Tan submits patches; Collin reviews alone | "this patch does what its message says" |
| 3 | xz-devel mailing list — pressure (2022) | "Jigar Kumar", "Dennis Ens" complain about slow progress, argue for a new maintainer | "the maintainer is a bottleneck; hand over" |
| 4 | Git commits (tukaani.org, mirrored to GitHub, 2023–24) | ifunc plumbing, the Landlock "typo", binary test fixtures | "build improvement / test data" |
| 5 | GitHub PR on oss-fuzz (2023) | Disable ifunc under fuzzing; change project contact | "ifunc causes false positives" |
| 6 | Release tarballs (Feb–Mar 2024) | The `m4` file that extracts the payload exists **only in the tarball**, not in git | "this tarball is the tagged tree" |
| 7 | Distro bug trackers (Debian BTS, Launchpad, Fedora) | "Hans Jansen" and other fresh accounts ask distros to pull 5.6.x | "5.6.x should ship now" |
| 8 | Direct email to distro maintainers | Jia Tan lobbies personally | "5.6.1 fixes a valgrind issue, please include it" |

Ranked by how strong and how automatic the ISNAD signal would have been:

**Tier 1 — mechanical; fires on ingest with no judgement.**

- *#6, tarball ≠ git tree.* This is *ittiṣāl* (chain completeness). A
  release artifact containing content traceable to no commit is a gap in the
  chain — `MUNQATI`, automatic `DAIF` cap (`types.py`). Any operator
  ingesting the tarball as a narrator-transmitted artifact would have had the
  chain capped before anyone read a line of code. It is the single most
  actionable datapoint in the case, and it requires nothing but a diff.
- *#4, commits with no independent reviewer.* Every link in xz's chain was
  one of two people, and for the payload era, one. In ISNAD terms,
  corroboration is structurally impossible: there is no second independent
  narrator. Not a strike — a standing datapoint that this project's claims
  arrive uncorroborated by construction.

**Tier 2 — registry-driven; fires if the decision point is instrumented.**

- *#3 and #7, fresh identities arriving at decision points.* Jigar Kumar,
  Dennis Ens, Hans Jansen and the distro-tracker pushers had zero prior
  history. They enter `UNGRADED` with `adalah=SUSPECT`; their claims carry no
  weight. And they arrived together, with one agenda — `SharedLineageDetector`
  flags correlated chains: **echo, not consensus**. This is the datapoint
  Lasse Collin needed in 2022 and had no way to produce.
- *#8, the grade of the release manager.* When a Fedora maintainer is asked
  to ship 5.6.1, "who cut this release?" has an ISNAD answer: `JiaT75@xz`,
  ~18 months of history, against `Larhzu@xz` (Collin), ~15 years. Not
  damning — but a `HASAN`-grade release manager requesting an out-of-cycle
  pull is `SERVE_WITH_CAVEAT`, not `SERVE`.
- *#1 and #5, cross-domain.* Jia Tan's xz standing does not transfer to
  libarchive or oss-fuzz. Each is its own operator; each would have seen an
  `UNGRADED` narrator requesting a change with security consequences.

**Tier 3 — matn; where ISNAD alone is weakest.**

- *#2 and #4, does the diff do what the message says?* The Landlock typo's
  message and its effect disagree. That is a matn contradiction in principle,
  but seeing it means understanding C build semantics. ISNAD by itself can
  route a single-maintainer, uncorroborated commit to `REVIEW`; it cannot see
  the typo. §8 is about what changes when something else can.

The shape that emerges: the operation's strongest moves were on channels
ISNAD cannot see into (private email, the semantics of a C diff). Its
*weakest* moves — the ones that would have produced clean datapoints — were
structural: an artifact that does not match its source, a burst of
history-less identities agreeing with each other, a trust handover to a
narrator with a short record. Those are exactly what ISNAD grades: **chain
completeness, narrator history, independence**. So the defensible claim is
not "ISNAD would have caught xz" but "ISNAD would have put three separate
caveats in front of the humans who had the power to say no — Collin in 2022,
the distro maintainers in March 2024 — at the moment they were deciding."

## 8. Machine critics and the andon cord

Tier 3 is not a permanent limit, but it is worth being precise about which
part of it is already closing and which part is uncertain.

The **structural** checks — artifact matches its tagged source, build
provenance, reviewer count, maintainer change — do not require reading a
diff, and they already run at the chokepoints. PyPI has an admin quarantine
feature and build-provenance attestations (PEP 740); npm has provenance
attestations and pulls packages; Sigstore, SLSA and reproducible builds make
"tarball ≠ tag" mechanically checkable; OpenSSF Scorecard already scores
single-maintainer, no-review projects as a standing risk; several
distributions moved to building from git tags rather than tarballs because of
this case; and the EU Cyber Resilience Act and US SBOM mandates are pushing
liability toward whoever distributes. These are andon cords, present tense,
and they cover the Tier 1 signals — which were the strongest xz signals
anyway.

The **semantic** checks — does this diff do what its message says — are less
certain, for three reasons. First, false-positive cost at a chokepoint: an
andon cord works at Toyota because stops are rare and a supervisor arrives in
minutes; at npm scale there is no supervisor, and a critic that is right 95%
of the time pulls the cord on 5% of millions of uploads until someone raises
the threshold past usefulness. Second, cost: xz was the poster child for an
unfunded maintainer, and the portals are under-funded too; LLM-judged review
of every diff will arrive unevenly, big ecosystems first and the long tail —
where the next xz lives — last. Third, adaptation: xz was engineered to pass
every check that existed in 2024, and a semantic scanner becomes the next
spec to evade, whereas "does the tarball match the tag" is a fact an attacker
cannot argue with.

The likely equilibrium is therefore a division of labour: structural checks
auto-quarantine; semantic critics emit evidence and route to review; whether
a semantic critic ever pulls the cord on its own depends on its false-positive
rate and on someone being there to answer. That division is the one ISNAD's
precision/integrity axis already encodes, which is the point of the rest of
this section.

**A scanner is a critic, not a competitor.** ISNAD never needed to read
diffs, any more than it needs to compute embeddings. `EmbeddingCritic` does
not live in the grading core; it is one implementation of the `ContentCritic`
protocol (`critics/base.py`) that returns a `ContentVerdict`, alongside
`LocalNLICritic`, `LLMCritic` and `HybridCritic`. A supply-chain scanner that understands C is
the same shape: a matn critic whose domain is code. It returns
`CONSISTENT` / `CONTRADICTION` for "does this artifact do what its narrator
says," and the decision matrix takes it from there. The table below is what
such a critic could have emitted, machine-to-machine, at upload time.

| Signal | ISNAD datapoint | Would have fired |
| --- | --- | --- |
| Tarball content absent from tagged tree | `MUNQATI` → chain capped `DAIF` | 24 Feb 2024, on upload of 5.6.0 |
| Opaque binary added under `tests/` by the release manager | `CONTRADICTION` vs. "test data" | Feb 2024 |
| Commit-message semantics ≠ diff semantics (LLM-judged) | `CONTRADICTION`, precision evidence | Landlock typo, on push |
| Maintainer-of-record change | identity event, track record reset (cf. `alias@version`) | 2023 |
| Burst of zero-history identities requesting one action | madār warning on the request | 2022 (list), Mar 2024 (trackers) |

The first row alone holds 5.6.0 at the portal before any distribution sees
it.

**Andon cord versus conviction — keep them separate.** A machine-pulled stop
must be a **`QUARANTINE`**: hold the artifact, hold the narrator's new claims,
stop the line. It must *not* be an integrity strike. This is the Toyota
model: anyone on the floor can stop the line; a supervisor decides what it
meant. So a scanner has two powers and lacks a third:

1. *Emit precision evidence freely.* Every flag is `EvidenceAxis.PRECISION`
   — windowed, recoverable. A scanner that is wrong fifty times costs a
   narrator some standing, temporarily.
2. *Pull the cord.* `QUARANTINE` / `REJECT_AND_QUARANTINE_NARRATOR`,
   immediate, human-free.
3. *Not convict.* Converting a quarantine into a permanent integrity strike
   stays `HUMAN_REVIEW`. The cord buys time for the Freund; it does not
   replace the Freund.

A scanner wired to issue integrity strikes directly is a machine that can
permanently destroy a narrator on a false positive, and the permanence meant
to punish fabricators now punishes everyone. `default_axis_for()` — automated
signals resolve to precision, full stop — is the guard rail. It should be
stated as a contract that machine critics must honour, not left as an
internal default.

**The critics are narrators too.** A scanner has a grade. If
`pypi-diff-critic@2.3` produces ten thousand false positives, its verdicts
are discounted like any narrator's. "Grade the narrators" applies recursively
to the graders — the rijāl critics were themselves criticised. It also means a
compromised scanner, the obvious next target once portals run them, is a
sleeper narrator with a short record in a new identity, and the same
machinery applies.

**This is where federation pressure arrives.** A portal running ISNAD *is* an
operator — a chokepoint one. Its grade for `JiaT75@xz` becomes the de facto
grade because everyone downstream consumes through it, and downstream will
want to read it. That is the scenario §6 item 5 addresses: exchange evidence,
re-derive grades locally, never import a judgement.

## 9. Why this case and not a fictional one

A constructed example ("narrator X emits 10,000 true claims then asserts
π = 3.0") makes the same points, but readers discount constructed examples. xz
is a case security practitioners recognise on sight, in which the attacker's
patience, the trust-then-spend shape, the sock-puppet echo, and the
retrospective, lucky discovery are all matters of record rather than
hypothesis. The mapping in §3 is meant to let someone who already understands
xz understand what ISNAD's registry, axes, caps and identity rules are *for*.

## 10. The Live Verify half

[Live Verify](https://github.com/live-verify/live-verify) is a sibling
project that seals a specific artifact to an issuer domain via SHA-256 and a
`verify:` lookup, so a person with no tooling can confirm "this is what the
issuer issued, unaltered." Its
[companion document](https://github.com/live-verify/live-verify/blob/main/docs/xz-release-attestation-case-study.md)
reads the same incident from that side. The short version, because it sharpens
what this document is and is not:

- Live Verify would have said `verified` for 5.6.0 on 24 February 2024, and
  been right. The release was exactly what the issuer issued. Authentic ≠
  safe — the incident is the cleanest example of that distinction there is.
- Its value arrives on 29 March: the endpoint flips to `REVOKED` with a link,
  and every human who re-checks the claim sees it. Live Verify is the
  revocation broadcast channel for humans; ISNAD is the grading engine for
  machines.
- Open source has no regulator or sovereign root, so the endorser chain for a
  release is *sideways* (build attestation plus independent rebuilders), not
  *upward*. That chain is "amber-unanchored" in Live Verify's display — a
  real chain, no government behind it. Amber measures anchoring; ISNAD's
  grade measures independence. Three hostile rebuilders agreeing is weak on
  the first axis and strong on the second, and both readings are correct.
- A revocation — "issuer X recanted artifact Y at time T", or "endorser E
  restricted issuer X for reason R" — is a fact, not a judgement. It is
  exactly the evidence record §6 item 5 says operators should exchange
  instead of grades. That is where the two projects meet.

| | Live Verify | ISNAD |
| --- | --- | --- |
| 24 Feb 2024 | `OK` — correctly; it was official | `MUNQATI` cap (tarball ≠ tag); release-manager grade `HASAN` → caveats |
| 29 Mar 2024 | `REVOKED`; endorsers `RESTRICTED` | `HUMAN_REVIEW` → integrity strike on `JiaT75@xz` |
| Answers | "Is this what the issuer issued?" | "How much should I trust the hands it passed through?" |
| Human | at the threshold, deciding | at the review queue, adjudicating |

---

### References

- CVE-2024-3094 — NVD entry.
- Andres Freund, "backdoor in upstream xz/liblzma leading to ssh server
  compromise," oss-security mailing list, 29 March 2024.
- Evan Boehs, "Everything I know about the xz backdoor" (timeline of the
  account's history and the mailing-list pressure campaign).
- Russ Cox, "Timeline of the xz open source attack" (research.swtch.com).
- Live Verify, "Case study: the xz-utils backdoor as a Live Verify release
  attestation" —
  [docs/xz-release-attestation-case-study.md](https://github.com/live-verify/live-verify/blob/main/docs/xz-release-attestation-case-study.md)
  (companion to this document).
