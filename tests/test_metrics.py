"""Tests for the §8.1 evaluation metrics."""
from __future__ import annotations

import numpy as np

from orchestrator.metrics import evaluate, false_positive_rate, format_report, precision_at_fpr


def test_perfect_separation():
    y_true = [0, 0, 0, 1, 1, 1]
    y_prob = [0.05, 0.1, 0.2, 0.8, 0.9, 0.95]
    m = evaluate(y_true, y_prob, threshold=0.5)
    assert m["auroc"] == 1.0
    assert m["recall"] == 1.0
    assert m["precision"] == 1.0
    assert m["f1"] == 1.0
    assert m["fpr"] == 0.0
    assert m["n"] == 6 and m["n_fraud"] == 3


def test_precision_at_fpr_cap():
    # Clean separation → at FPR 0 we already capture all fraud at full precision.
    y_true = [0, 0, 0, 0, 1, 1]
    y_prob = [0.1, 0.1, 0.2, 0.3, 0.9, 0.95]
    prec, thr = precision_at_fpr(y_true, y_prob, max_fpr=0.05)
    assert prec == 1.0
    assert 0.0 < thr <= 1.0


def test_false_positive_rate():
    # 1 FP out of 4 negatives → 0.25.
    y_true = [0, 0, 0, 0, 1]
    y_pred = [1, 0, 0, 0, 1]
    assert false_positive_rate(y_true, y_pred) == 0.25


def test_evaluate_handles_threshold():
    y_true = [0, 1, 1]
    y_prob = [0.3, 0.6, 0.9]
    lax = evaluate(y_true, y_prob, threshold=0.5)
    strict = evaluate(y_true, y_prob, threshold=0.8)
    assert lax["recall"] == 1.0
    assert strict["recall"] == 0.5  # only the 0.9 row clears 0.8


def test_format_report_is_string():
    m = evaluate([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9])
    report = format_report(m)
    assert "AUROC" in report and "baseline" in report
    assert isinstance(report, str)
