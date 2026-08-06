"""Volatility policies — how long a narrator grade stays trustworthy.

Implements the time-decay half of the grade-expiry fix (Part 1 of the
proposal).  Following the framework's convention, this is a pluggable
parameter (paper §4.2): the Registry only knows the VolatilityPolicy
protocol; any implementation can be swapped in.

The default implementation, FixedVolatilityPolicy, derives TTLs from
*configuration* rather than a hardcoded lookup table:

- a base TTL in days,
- a multiplier per narrator type (models drift faster than sources),
- an optional per-domain override (some facts are more stable than others),
- a stale (grace) ratio that carves out the "needs re-check" window at
  the end of the TTL.

All values can be overridden via environment variables, so a deployment
never needs to edit code to tune freshness:

    ISNAD_TTL_BASE_DAYS      base time-to-live in days        (default 90)
    ISNAD_TTL_TYPE_FACTORS   JSON: type -> TTL multiplier
                            {"model":0.5,"scraper":1.0,"source":2.0,"human":3.0}
    ISNAD_TTL_DOMAIN_DAYS    JSON: domain -> TTL days (overrides)
    ISNAD_STALE_RATIO        grace window as fraction of TTL (default 0.2)

The defaults are reference values, not empirically calibrated (see paper
§8) — they are priors over how fast sources drift, not measurements.
Calibrate ISNAD_TTL_* against your observed drift before trusting them.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta

from isnad.types import NarratorType

# Reference type factors (not a hardcoded table — overridable via env).
_DEFAULT_TYPE_FACTORS: dict[str, float] = {
    NarratorType.MODEL.value: 0.5,  # LLMs drift; short window
    NarratorType.SCRAPER.value: 1.0,  # extraction tools, moderate
    NarratorType.SOURCE.value: 2.0,  # external sources, slower-moving
    NarratorType.HUMAN.value: 3.0,  # human reviewers, slowest-moving
}


def _load_env_json(name: str) -> dict[str, object]:
    """Read a JSON dict from an env var; invalid/empty -> {}."""
    raw = os.environ.get(name)
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


class FixedVolatilityPolicy:
    """Config-driven fixed time-to-live per (narrator_type, domain).

    The default VolatilityPolicy.  TTL = base_days * type_factor, with an
    optional per-domain override replacing the result.  The stale window is
    the final `stale_ratio` of the TTL.

    This is one instantiation of a parameter the framework leaves open
    (see paper §4.2/§4.3).  Swap freely.
    """

    def __init__(
        self,
        base_days: float | None = None,
        type_factors: dict[str, float] | None = None,
        domain_days: dict[str, float] | None = None,
        stale_ratio: float | None = None,
    ):
        self.base_days = float(
            base_days if base_days is not None else os.environ.get("ISNAD_TTL_BASE_DAYS", "90")
        )
        if self.base_days <= 0:
            raise ValueError("base_days must be positive")

        self.type_factors: dict[str, float] = dict(_DEFAULT_TYPE_FACTORS)
        if type_factors is not None:
            self.type_factors.update(type_factors)
        for key, value in _load_env_json("ISNAD_TTL_TYPE_FACTORS").items():
            try:
                self.type_factors[str(key)] = float(value)
            except (TypeError, ValueError):
                continue

        self.domain_days: dict[str, float] = dict(domain_days or {})
        for key, value in _load_env_json("ISNAD_TTL_DOMAIN_DAYS").items():
            try:
                self.domain_days[str(key)] = float(value)
            except (TypeError, ValueError):
                continue

        self.stale_ratio = float(
            stale_ratio if stale_ratio is not None else os.environ.get("ISNAD_STALE_RATIO", "0.2")
        )
        if not 0.0 <= self.stale_ratio <= 1.0:
            raise ValueError("stale_ratio must be in [0, 1]")

    @staticmethod
    def _type_value(narrator_type: NarratorType | str) -> str:
        """Extract the string value from a narrator type, whether enum or raw string."""
        if isinstance(narrator_type, NarratorType):
            return narrator_type.value
        return str(narrator_type)

    def time_to_live(self, narrator_type: NarratorType | str, domain: str) -> timedelta:
        """TTL for a (narrator_type, domain), from config not a lookup table."""
        days = self.base_days * self.type_factors.get(self._type_value(narrator_type), 1.0)
        days = self.domain_days.get(domain, days)
        return timedelta(days=days)

    def stale_window(self, narrator_type: NarratorType | str, domain: str) -> timedelta:
        """The grace period at the end of the TTL (downgrade + re-check)."""
        return self.time_to_live(narrator_type, domain) * self.stale_ratio

    def valid_until(
        self,
        narrator_type: NarratorType | str,
        domain: str,
        now: datetime | None = None,
    ) -> datetime:
        """The expiry instant for a grade validated at `now`."""
        return (now or datetime.now(UTC)) + self.time_to_live(narrator_type, domain)

    def __repr__(self) -> str:
        return (
            f"FixedVolatilityPolicy(base_days={self.base_days}, "
            f"type_factors={self.type_factors}, domain_days={self.domain_days}, "
            f"stale_ratio={self.stale_ratio})"
        )
