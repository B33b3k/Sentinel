"""Evaluation metrics (DATA_DESCRIPTION §8.1) for the fraud scorer.

Given ground-truth labels and predicted fraud probabilities, compute the ranking +
operating-point metrics the rubric scores on, and compare them to the §8.1 targets and
the §8.3 rule-engine baseline.
"""
from __future__ import annotations

import numpy as np
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score, roc_curve

# §8.1 targets and §8.3 legacy rule-engine baseline (the bar to beat).
TARGETS = {"auroc": 0.93, "precision_at_5pct_fpr": 0.75, "recall": 0.88, "f1": 0.80}
BASELINE_RULE_ENGINE = {"auroc": 0.71, "recall": 0.62, "f1": 0.54, "fpr": 0.14}


def precision_at_fpr(y_true, y_prob, max_fpr: float = 0.05) -> tuple[float, float]:
    """Precision at the highest-recall operating point with FPR ≤ max_fpr.

    Returns (precision, threshold). If no threshold meets the FPR cap, returns (0, 1).
    """
    fpr, tpr, thresholds = roc_curve(y_true, y_prob)
    ok = np.where(fpr <= max_fpr)[0]
    if len(ok) == 0:
        return 0.0, 1.0
    idx = ok[np.argmax(tpr[ok])]  # most recall within the FPR budget
    thr = float(thresholds[idx])
    preds = (np.asarray(y_prob) >= thr).astype(int)
    prec = precision_score(y_true, preds, zero_division=0)
    return float(prec), thr


def false_positive_rate(y_true, y_pred) -> float:
    y_true = np.asarray(y_true).astype(int)
    y_pred = np.asarray(y_pred).astype(int)
    neg = (y_true == 0).sum()
    if neg == 0:
        return 0.0
    fp = ((y_pred == 1) & (y_true == 0)).sum()
    return float(fp / neg)


def evaluate(y_true, y_prob, threshold: float = 0.5) -> dict:
    """Compute the §8.1 metric bundle at the given decision threshold."""
    y_true = np.asarray(y_true).astype(int)
    y_prob = np.asarray(y_prob, dtype=float)
    y_pred = (y_prob >= threshold).astype(int)

    prec_at_fpr, op_thr = precision_at_fpr(y_true, y_prob)
    return {
        "n": int(len(y_true)),
        "n_fraud": int(y_true.sum()),
        "auroc": float(roc_auc_score(y_true, y_prob)) if y_true.min() != y_true.max() else float("nan"),
        "precision_at_5pct_fpr": prec_at_fpr,
        "precision_at_5pct_fpr_threshold": op_thr,
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "fpr": false_positive_rate(y_true, y_pred),
        "threshold": threshold,
    }


def format_report(m: dict) -> str:
    """Human-readable comparison vs §8.1 targets and the §8.3 baseline."""
    def mark(metric: str, value: float, higher_better: bool = True) -> str:
        t = TARGETS.get(metric)
        if t is None:
            return ""
        hit = value >= t if higher_better else value <= t
        return f"  (target {t:.2f} {'✓' if hit else '✗'})"

    lines = [
        f"n={m['n']:,}  fraud={m['n_fraud']:,} ({m['n_fraud']/max(m['n'],1):.2%})",
        f"AUROC                 {m['auroc']:.4f}{mark('auroc', m['auroc'])}"
        f"   [baseline {BASELINE_RULE_ENGINE['auroc']:.2f}]",
        f"Precision @ 5% FPR    {m['precision_at_5pct_fpr']:.4f}{mark('precision_at_5pct_fpr', m['precision_at_5pct_fpr'])}",
        f"Recall (thr={m['threshold']:.2f})      {m['recall']:.4f}{mark('recall', m['recall'])}"
        f"   [baseline {BASELINE_RULE_ENGINE['recall']:.2f}]",
        f"F1 (thr={m['threshold']:.2f})          {m['f1']:.4f}{mark('f1', m['f1'])}"
        f"   [baseline {BASELINE_RULE_ENGINE['f1']:.2f}]",
        f"FPR (thr={m['threshold']:.2f})         {m['fpr']:.4f}   [baseline {BASELINE_RULE_ENGINE['fpr']:.2f}]",
    ]
    return "\n".join(lines)
