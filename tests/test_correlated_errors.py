"""Tests for the ISNAD φ study (correlated-errors experiment).

Covers the statistics exclusion rule, the φ/same-wrong computation, the
cluster-bootstrap CI, the number parser, and the Experiment B/C φ-discount
direction: the discounted corroboration policy must never upgrade MORE than naive.
"""

from __future__ import annotations

import math

import pytest

from experiments.correlated_errors import experiment_bc as bc
from experiments.correlated_errors import runner
from experiments.correlated_errors import stats


def test_n_eff_formula():
    assert bc.n_eff(0.0, 8) == 8
    assert math.isclose(bc.n_eff(1.0, 8), 1.0)
    assert bc.n_eff(0.7, 8) < 8


def test_corroboration_strength_naive_equals_m():
    for m in range(1, 6):
        assert bc.corroboration_strength(m, 0.0, 8) == m


def test_corroboration_strength_discounted_lower():
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

    assert disc_up <= naive_up
    assert "c2" in naive_up
    assert "c2" not in disc_up


def test_false_upgrade_reduction_direction():
    answers, oracle = _fixture()
    result = bc.compare(answers, oracle, phi_bar=0.5, k=3, threshold=2)

    assert result["discounted"]["coverage"] < result["naive"]["coverage"]
    assert result["discounted"]["false_upgrades"] < result["naive"]["false_upgrades"]
    assert result["delta_false_upgrade_rate"] >= 0
    assert result["delta_risk"] >= 0


def test_agreement_counts_float_equality():
    counts = bc.agreement_counts({"a": "43.03", "b": 43.03, "c": None})
    assert counts[43.03] == 2
    assert len(counts) == 1


def test_phi_known_table():
    assert math.isclose(stats._phi(16, 0, 4, 44), 0.8563, abs_tol=1e-3)
    assert stats._phi(1, 0, 0, 1) == 1.0
    assert stats._phi(0, 1, 1, 0) == -1.0
    assert stats._phi(0, 0, 0, 0) is None


def test_retained_models_band():
    rates = {"a": 0.5, "b": 0.5, "c": 0.5, "d": 0.005, "e": 0.999}
    covs = {"a": 1.0, "b": 0.5, "c": 1.0, "d": 1.0, "e": 1.0}
    kept = stats.retained_models(rates, covs)

    assert kept == ["a", "c"]


def test_error_vector_missing_is_not_error():
    corpus = [
        {"id": "f1", "oracle_value": "10"},
        {"id": "f2", "oracle_value": "20"},
        {"id": "f3", "oracle_value": "30"},
    ]
    rows = {"f1": {"answer_value": "10"}, "f3": {"answer_value": "999"}}
    err, ans, covered = stats.error_vector(rows, corpus)
    assert covered == [True, False, True]

    assert err[0] == 0.0
    assert err[2] == 1.0
    rate = sum(e for e, c in zip(err, covered, strict=True) if c) / sum(covered)
    assert rate == 0.5


def test_percentile_linear_interpolation():
    vals = list(range(1000))
    assert stats._percentile(vals, 0.025) == 24.975
    assert stats._percentile(vals, 0.975) == 974.025


@pytest.mark.parametrize("phi_bar", [0.0, 0.4, 0.5599, 0.8])
def test_strength_equals_n_eff_at_m_k(phi_bar):
    k = 8
    assert bc.corroboration_strength(1, phi_bar, k) == 1.0
    assert math.isclose(
        bc.corroboration_strength(k, phi_bar, k), bc.n_eff(phi_bar, k), rel_tol=1e-12
    )
    for m in (2, 3, 4, 5):
        if phi_bar == 0.0:
            assert bc.corroboration_strength(m, phi_bar, k) == m
        else:
            assert bc.corroboration_strength(m, phi_bar, k) < m


def test_parse_number_unicode_minus_sign():
    assert runner._parse_number("−273.15") == "-273.15"
    assert runner._parse_number("–273.15") == "-273.15"
    assert runner._parse_number("‒273.15") == "-273.15"
    assert runner._parse_number("-273.15") == "-273.15"
    assert runner._parse_number("273.15") == "273.15"
    assert runner._parse_number("+5.5") == "+5.5"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("299,792,458 m/s", "299792458"),
        ("1,2,3", "3"),
        ("1_000_000", "1000000"),
        ("-273.15", "-273.15"),
    ],
)
def test_parse_number_thousands_separator(raw, expected):
    assert runner._parse_number(raw) == expected


def test_pair_table_same_wrong_numeric_equality():
    # fact0 both-wrong "9.8" vs "9.80" -> numerically equal -> same_wrong counts it;
    # fact1 both-wrong "x" vs "y" -> not; fact2 m1-right -> c; fact3 both-wrong but
    # both unparseable ("") -> NOT same-wrong.
    ei = [1.0, 1.0, 0.0, 1.0]
    ej = [1.0, 1.0, 1.0, 1.0]
    ai = ["9.8", "x", "10", ""]
    aj = ["9.80", "y", "20", ""]
    ci = [True, True, True, True]
    cj = [True, True, True, True]
    a, b, c, d, both_wrong, same_wrong = stats._pair_table(ei, ej, ai, aj, ci, cj)
    assert (a, b, c, d) == (3, 0, 1, 0)
    assert both_wrong == 3
    assert same_wrong == 1


def test_pair_table_missing_not_same_wrong():
    # a missing/missing fact (covered=False on both) must not enter any cell.
    ei = [1.0, 0.0]
    ej = [1.0, 0.0]
    ai = ["", ""]
    aj = ["", ""]
    ci = [False, True]
    cj = [False, True]
    a, b, c, d, both_wrong, same_wrong = stats._pair_table(ei, ej, ai, aj, ci, cj)
    assert (a, b, c, d, both_wrong, same_wrong) == (0, 0, 0, 1, 0, 0)


def test_bootstrap_ci_deterministic_and_sane():
    corpus = [{"id": f"f{i}", "oracle_value": str(i)} for i in range(20)]
    # m1 errs on facts 0-9; m2 errs on facts 0-7 and 10-11 -> phi = 0.6.
    m1 = {f"f{i}": {"answer_value": "999" if i < 10 else str(i)} for i in range(20)}
    m2 = {
        f"f{i}": {"answer_value": "999" if (i < 8 or i in (10, 11)) else str(i)} for i in range(20)
    }
    models = {"m1": m1, "m2": m2}
    ei, ai, ci = stats.error_vector(m1, corpus)
    ej, aj, cj = stats.error_vector(m2, corpus)
    a, b, c, d, _both, _same = stats._pair_table(ei, ej, ai, aj, ci, cj)
    phi = stats._phi(a, b, c, d)
    assert math.isclose(phi, 0.6, abs_tol=1e-9)
    pairs = [{"mi": "m1", "mj": "m2", "phi": phi}]
    lo1, hi1 = stats._bootstrap_ci(pairs, models, corpus, k=2, n_draws=100, seed=0)
    lo2, hi2 = stats._bootstrap_ci(pairs, models, corpus, k=2, n_draws=100, seed=0)
    assert lo1 is not None and hi1 is not None
    assert lo1 <= hi1
    assert lo1 == lo2 and hi1 == hi2  # deterministic under a fixed seed
