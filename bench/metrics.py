"""ISNAD-Bench: metrics — confusion matrix, Cohen's kappa, per-class P/R.

Pure, dependency-free (no numpy/sklearn — the project keeps a minimal core).
Cohen's kappa is the *primary* metric: the chain grades are ordinally ordered
but the classes are imbalanced (sahih dominates), so raw accuracy would flatter
a trivial majority-class predictor.

Both unweighted kappa and linear-weighted kappa are provided. Unweighted is
the headline (standard, interpretable); linear-weighted rewards "near misses"
(sahih→hasan is a smaller error than sahih→mawdu), which is more faithful to
the ordinal nature of the grades.
"""

from __future__ import annotations

from collections.abc import Sequence


def confusion_matrix(
    y_true: Sequence[str], y_pred: Sequence[str], classes: Sequence[str]
) -> dict[str, dict[str, int]]:
    """Build a label-keyed confusion matrix: cm[true][pred]."""
    cm: dict[str, dict[str, int]] = {c: dict.fromkeys(classes, 0) for c in classes}
    for t, p in zip(y_true, y_pred, strict=True):
        cm[t][p] += 1
    return cm


def _row_sums(cm: dict[str, dict[str, int]], classes: Sequence[str]) -> dict[str, int]:
    return {c: sum(cm[c].values()) for c in classes}


def _col_sums(cm: dict[str, dict[str, int]], classes: Sequence[str]) -> dict[str, int]:
    return {c: sum(cm[d][c] for d in classes) for c in classes}


def cohens_kappa(cm: dict[str, dict[str, int]], classes: Sequence[str]) -> float:
    """Unweighted Cohen's kappa over the confusion matrix.

    kappa = (p_o - p_e) / (1 - p_e), where p_o is observed agreement and p_e is
    chance agreement from the marginal distributions.
    """
    n = sum(sum(cm[c].values()) for c in classes)
    if n == 0:
        return 0.0
    rows = _row_sums(cm, classes)
    cols = _col_sums(cm, classes)
    p_o = sum(cm[c][c] for c in classes) / n
    p_e = sum((rows[c] / n) * (cols[c] / n) for c in classes)
    if p_e == 1.0:
        # Degenerate: all labels in one cell. Agreement is trivially perfect.
        return 1.0 if p_o == 1.0 else 0.0
    return (p_o - p_e) / (1.0 - p_e)


def linear_weighted_kappa(cm: dict[str, dict[str, int]], classes: Sequence[str]) -> float:
    """Linear-weighted Cohen's kappa (ordinal classes: near-misses cost less)."""
    n = sum(sum(cm[c].values()) for c in classes)
    if n == 0:
        return 0.0
    k = len(classes)

    observed = 0.0
    expected = 0.0
    for i, a in enumerate(classes):
        for j, b in enumerate(classes):
            weight = 1.0 - abs(i - j) / (k - 1)
            observed += weight * cm[a][b]
            expected += weight * _row_sums(cm, classes)[a] * _col_sums(cm, classes)[b] / n
    p_o = observed / n
    p_e = expected / n
    if p_e == 1.0:
        return 1.0 if p_o == 1.0 else 0.0
    return (p_o - p_e) / (1.0 - p_e)


def per_class_metrics(
    y_true: Sequence[str], y_pred: Sequence[str], classes: Sequence[str]
) -> dict[str, dict[str, float]]:
    """Per-class precision / recall / F1 over label sequences."""
    tp = dict.fromkeys(classes, 0)
    fp = dict.fromkeys(classes, 0)
    fn = dict.fromkeys(classes, 0)
    for t, p in zip(y_true, y_pred, strict=True):
        if t == p:
            tp[t] += 1
        else:
            fp[p] += 1
            fn[t] += 1
    out: dict[str, dict[str, float]] = {}
    for c in classes:
        precision = tp[c] / (tp[c] + fp[c]) if (tp[c] + fp[c]) else 0.0
        recall = tp[c] / (tp[c] + fn[c]) if (tp[c] + fn[c]) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        out[c] = {"precision": precision, "recall": recall, "f1": f1, "support": tp[c] + fn[c]}
    return out
