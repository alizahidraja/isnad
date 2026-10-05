"""Tests for the ISNAD φ study (correlated-errors experiment).

Covers the statistics exclusion rule and the Experiment B/C φ-discount direction:
the discounted corroboration policy must never upgrade MORE than naive.
"""

from __future__ import annotations

import math

from experiments.correlated_errors import experiment_bc as bc
from experiments.correlated_errors import stats


def test_n_eff_formula():
    # φ=0 → full independence → n_eff == k
    assert bc.n_eff(0.0, 8) == 8
    # φ=1 → perfect correlation → n_eff == 1
    assert math.isclose(bc.n_eff(1.0, 8), 1.0)
    # φ>0 → n_eff < k
    assert bc.n_eff(0.7, 8) < 8


def test_corroboration_strength_naive_equals_m():
    # With φ=0 (naive), strength of m agreeing models is exactly m.
    for m in range(1, 6):
        assert bc.corroboration_strength(m, 0.0, 8) == m


def test_corroboration_strength_discounted_lower():
    # With φ>0, each extra agreeing route counts <1, so strength < m for m>1.
    for m in (2, 3, 4):
        assert bc.corroboration_strength(m, 0.5, 8) < m


def test_is_correct_oracle():
    assert bc.is_correct(206.0, "206") is True
    assert bc.is_correct(206.0, "207") is False
    assert bc.is_correct(None, "206") is False
    assert bc.is_correct(0.0, "0") is True
    assert bc.is_correct(1e-7, "0") is False


def _fixture():
    """3 claims × 3 models.

    c1: all three correct (true corroboration).
    c2: a+b agree on a WRONG answer, c correct (the classic correlated-wrong pair).
    c3: all three agree on the same WRONG answer (unanimous wrong).
    """
    answers_by_claim = {
        "c1": {"a": "10", "b": "10", "c": "10"},
        "c2": {"a": "999", "b": "999", "c": "20"},
        "c3": {"a": "888", "b": "888", "c": "888"},
    }
    oracle_by_claim = {"c1": "10", "c2": "20", "c3": "30"}
    return answers_by_claim, oracle_by_claim


def test_discounted_never_upgrades_more_than_naive():
    answers, oracle = _fixture()
    naive = bc.policy(answers, 0.0, k=3, threshold=2)
    discounted = bc.policy(answers, 0.5, k=3, threshold=2)

    naive_up = {cid for cid, (up, _a, _s) in naive.items() if up}
    disc_up = {cid for cid, (up, _a, _s) in discounted.items() if up}

    # The discount only lowers the strength of correlated extra votes → it can
    # only ever SHRINK the upgrade set, never grow it.
    assert disc_up <= naive_up
    # In this fixture it genuinely removes the correlated-wrong pair (c2):
    assert "c2" in naive_up
    assert "c2" not in disc_up


def test_false_upgrade_reduction_direction():
    answers, oracle = _fixture()
    result = bc.compare(answers, oracle, phi_bar=0.5, k=3, threshold=2)
    # Discounted upgrades strictly fewer claims (lower coverage)…
    assert result["discounted"]["coverage"] < result["naive"]["coverage"]
    # …and strictly fewer false upgrades, so Δfalse-upgrade ≥ 0 and Δrisk ≥ 0.
    assert result["discounted"]["false_upgrades"] < result["naive"]["false_upgrades"]
    assert result["delta_false_upgrade_rate"] >= 0
    assert result["delta_risk"] >= 0


def test_agreement_counts_float_equality():
    # "43.03" and 43.03 agree as the same number; None is ignored.
    counts = bc.agreement_counts({"a": "43.03", "b": 43.03, "c": None})
    assert counts[43.03] == 2
    assert len(counts) == 1


def test_phi_known_table():
    # a=both wrong, b=i wrong j right, c=i right j wrong, d=both right
    assert math.isclose(stats._phi(16, 0, 4, 44), 0.8563, abs_tol=1e-3)
    assert stats._phi(1, 0, 0, 1) == 1.0
    assert stats._phi(0, 1, 1, 0) == -1.0
    assert stats._phi(0, 0, 0, 0) is None


def test_retained_models_band():
    rates = {"a": 0.5, "b": 0.5, "c": 0.5, "d": 0.005, "e": 0.999}
    covs = {"a": 1.0, "b": 0.5, "c": 1.0, "d": 1.0, "e": 1.0}
    kept = stats.retained_models(rates, covs)
    # a: ok; b: coverage <0.9 excluded; c: ok; d: rate <1% excluded; e: rate >99% excluded
    assert kept == ["a", "c"]


def test_error_vector_missing_is_not_error():
    corpus = [
        {"id": "f1", "oracle_value": "10"},
        {"id": "f2", "oracle_value": "20"},
        {"id": "f3", "oracle_value": "30"},
    ]
    rows = {"f1": {"answer_value": "10"}, "f3": {"answer_value": "999"}}  # f2 missing
    err, ans, covered = stats.error_vector(rows, corpus)
    assert covered == [True, False, True]
    # f1 correct (0.0), f3 wrong (1.0); f2 missing is NOT an error
    assert err[0] == 0.0
    assert err[2] == 1.0
    rate = sum(e for e, c in zip(err, covered, strict=True) if c) / sum(covered)
    assert rate == 0.5  # 1 of 2 covered facts wrong (missing f2 excluded)


def test_percentile_linear_interpolation():
    vals = list(range(1000))
    assert stats._percentile(vals, 0.025) == 24.975
    assert stats._percentile(vals, 0.975) == 974.025


def test_strength_equals_n_eff_at_m_k():
    k = 8
    phi_bar = 0.5667
    assert bc.corroboration_strength(1, phi_bar, k) == 1.0
    assert math.isclose(
        bc.corroboration_strength(k, phi_bar, k), bc.n_eff(phi_bar, k), rel_tol=1e-12
    )
    # discounted is strictly below the naive count for m > 1 and phi > 0
    for m in (2, 3, 4, 5):
        assert bc.corroboration_strength(m, phi_bar, k) < m
