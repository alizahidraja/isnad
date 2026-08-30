"""Tests for co-failure calibration (issue #54 measurement half)."""

from __future__ import annotations

import pytest

from isnad.core.co_failure import compute_co_failure


def test_independent_errors_have_near_chance_double_fault():
    # Two narrators, each ~50% wrong, errors uncorrelated (alternating pattern
    # gives Q = -1, so use a shuffled mix that yields near-zero Q).
    verdicts = [
        (False, False),
        (False, True),
        (True, False),
        (True, True),
    ] * 10  # 40 cases; each cell ~10 -> independent
    s = compute_co_failure(verdicts)
    assert s.n_cases == 40
    # Errors are uncorrelated: double-fault ~ chance (0.25), Q ~ 0.
    assert abs(s.double_fault_rate - 0.25) < 0.05
    assert abs(s.q_statistic) < 0.2


def test_correlated_errors_have_high_q():
    # Two narrators share a blind spot: they are wrong together most of the time.
    verdicts = [(True, True)] * 30 + [(False, False)] * 10
    s = compute_co_failure(verdicts)
    assert s.both_wrong == 30
    assert s.double_fault_rate == 0.75
    assert s.q_statistic == 1.0  # perfectly positively associated


def test_negative_association():
    # A is wrong exactly when B is right (perfect anti-correlation).
    verdicts = [(True, False)] * 20 + [(False, True)] * 20
    s = compute_co_failure(verdicts)
    assert s.both_wrong == 0
    assert s.q_statistic == -1.0


def test_empty_input_is_all_zero():
    s = compute_co_failure([])
    assert s.n_cases == 0
    assert s.double_fault_rate == 0.0
    assert s.q_statistic == 0.0


def test_prior_floors_at_chance_when_no_co_failure_observed():
    # No observed co-failure, but each narrator is 20% wrong -> chance = 0.04.
    # The prior must NOT be zero (absence of observed co-failure != independence).
    verdicts = [(True, False)] * 10 + [(False, True)] * 10 + [(False, False)] * 30
    s = compute_co_failure(verdicts)
    assert s.both_wrong == 0
    assert s.err_a == 0.2
    assert s.err_b == 0.2
    assert s.prior() == pytest.approx(0.04)  # floored at chance product, not 0.0


def test_prior_uses_observed_rate_when_higher():
    verdicts = [(True, True)] * 20 + [(False, False)] * 20
    s = compute_co_failure(verdicts)
    assert s.double_fault_rate == 0.5
    assert s.prior() == 0.5  # observed co-failure exceeds the chance floor
