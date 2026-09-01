"""Default-ON affirmation gate — a critic may not AFFIRM (CONSISTENT) without evidence.

The content critic's ``CONSISTENT`` verdict is the single catastrophic-error surface:
a false-CONSISTENT blesses a contradiction (a wrong claim served as if correct). So by
default NO critic may return CONSISTENT. An operator must first record a domain-scoped
evaluation — a re-runnable measurement of the false-consistent rate — that licenses
affirmation. Without a valid, unexpired, within-threshold record, CONSISTENT is
downgraded to UNVERIFIABLE (fail safe).

This is a safety interlock, not a cryptographic boundary: an operator who can write the
records directory already has code execution. The trust is *re-runnability* — the record
pins an eval-set hash so ``experiments/critic_eval/run.py`` can reproduce the measurement.
A hand-authored, self-attested claim is not a license.

Records live one JSON object per file under ``ISNAD_AFFIRMATION_RECORDS_DIR`` (default
``data/affirmation_records/``); a runtime ``register()`` exists for tests and embedded
callers that compute the eval programmatically.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from isnad.types import ContentVerdict

_DEFAULT_DIR = "data/affirmation_records"
_DEFAULT_MAX_AGE_DAYS = 90.0
_DEFAULT_MAX_FCR = 0.0
_MIN_CONTRADICTION_CASES = 25

# The critic kinds that can AFFIRM (return CONSISTENT) and are therefore gated.
_AFFIRMING_KINDS = frozenset({"llm", "nli", "hybrid"})


@dataclass(frozen=True)
class EvalRecord:
    """A re-runnable measurement that licenses CONSISTENT for one (kind, domain)."""

    schema_version: int
    domain: str
    critic_kind: str
    provider: str | None
    model: str | None
    n_cases: int
    n_contradiction_cases: int
    false_consistent_count: int
    false_consistent_rate: float
    eval_set_sha256: str
    evaluated_at: str


_records: list[EvalRecord] = []
_loaded = False


def _records_dir() -> Path:
    return Path(os.environ.get("ISNAD_AFFIRMATION_RECORDS_DIR", _DEFAULT_DIR))


def _max_fcr() -> float:
    raw = os.environ.get("ISNAD_AFFIRMATION_MAX_FCR", "").strip()
    if not raw:
        return _DEFAULT_MAX_FCR
    try:
        return float(raw)
    except ValueError:
        return _DEFAULT_MAX_FCR


def _max_age_days() -> float:
    raw = os.environ.get("ISNAD_AFFIRMATION_MAX_AGE_DAYS", "").strip()
    if not raw:
        return _DEFAULT_MAX_AGE_DAYS
    try:
        return float(raw)
    except ValueError:
        return _DEFAULT_MAX_AGE_DAYS


def register(record: dict[str, Any]) -> None:
    """Register an eval record (in-memory; for tests and programmatic callers)."""
    rec = EvalRecord(
        schema_version=int(record.get("schema_version", 1)),
        domain=str(record["domain"]),
        critic_kind=str(record["critic_kind"]),
        provider=record.get("provider"),
        model=record.get("model"),
        n_cases=int(record["n_cases"]),
        n_contradiction_cases=int(record["n_contradiction_cases"]),
        false_consistent_count=int(record["false_consistent_count"]),
        false_consistent_rate=float(record["false_consistent_rate"]),
        eval_set_sha256=str(record.get("eval_set_sha256", "")),
        evaluated_at=str(record["evaluated_at"]),
    )
    _records.append(rec)


def _load_if_needed() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    d = _records_dir()
    if not d.is_dir():
        return
    for path in sorted(d.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(data, dict):
            # A malformed record must fail safe (skip -> refuse), never crash the
            # gate. register() is strict for programmatic callers; disk loads skip.
            try:
                register(data)
            except (KeyError, TypeError, ValueError):
                continue


def _match(
    rec: EvalRecord, critic_kind: str, domain: str, provider: str | None, model: str | None
) -> bool:
    # provider/model are identity when the record pins them; unpinned = wildcard.
    return (
        rec.critic_kind == critic_kind
        and rec.domain == domain
        and rec.provider == provider
        and rec.model == model
    )


def allows(
    critic_kind: str,
    domain: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    now: datetime | None = None,
) -> bool:
    """True iff a valid, unexpired eval record licenses CONSISTENT for (kind, domain).

    Boolean only — never surfaces the numeric rate (the honesty moat: ordinal, not
    confidence). A record must be: within threshold, non-expired, backed by a
    re-runnable eval-set hash, and measured over >= 25 contradiction cases.
    """
    _load_if_needed()
    now = now or datetime.now(UTC)
    for rec in _records:
        if not _match(rec, critic_kind, domain, provider, model):
            continue
        if rec.eval_set_sha256 == "":
            continue  # not re-runnable — refuse
        if rec.n_contradiction_cases < _MIN_CONTRADICTION_CASES:
            continue  # too small a denominator to trust
        try:
            evaluated = datetime.fromisoformat(rec.evaluated_at.replace("Z", "+00:00"))
        except ValueError:
            continue
        if evaluated.tzinfo is None:
            evaluated = evaluated.replace(tzinfo=UTC)
        age_days = (now - evaluated).total_seconds() / 86400.0
        if age_days < 0 or age_days > _max_age_days():
            continue  # future-dated or stale — refuse
        if rec.false_consistent_rate > _max_fcr():
            continue
        return True
    return False


def gated(
    critic_kind: str,
    domain: str,
    verdict: ContentVerdict,
    *,
    provider: str | None = None,
    model: str | None = None,
) -> ContentVerdict:
    """Downgrade CONSISTENT to UNVERIFIABLE unless affirmation is licensed.

    CONTRADICTION and UNVERIFIABLE pass through untouched — the gate only withholds
    affirmation, never suppresses a contradiction.
    """
    if verdict is not ContentVerdict.CONSISTENT:
        return verdict
    if allows(critic_kind, domain, provider=provider, model=model):
        return verdict
    return ContentVerdict.UNVERIFIABLE
