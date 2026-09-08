"""IRIS-lite - identity verification from the visible string alone.

IRIS asks whether two response populations could have come from one model, using
only what a client can see: the text. No logprobs, no logits, no provider
cooperation. That is what makes it deployable where RUT and DiFR are not - our
own coverage table puts IRIS at 11/11 endpoints and RUT at 0/11.

Reimplemented here as a CLASSIFIER TWO-SAMPLE TEST, which is the cleanest way to
turn "these look different" into a number with a null. Label reference responses
0 and suspect responses 1, fit a classifier under cross-validation, and ask
whether it beats chance. Under the null - one model behind both samples - the
labels are arbitrary, so held-out accuracy is Binomial(n, 1/2) and a one-sided
binomial test gives an exact p-value. Above chance means something in the visible
string carries backend identity.

Deltas from the paper, stated plainly:
  - The original enrols a set of known backends and returns a posterior over
    them, giving attribution ("this is model X"). We return a two-sample verdict
    plus feature attributions, because attribution needs an enrolled fleet and
    the free-tier fleet is too small to enrol meaningfully.
  - Features are reimplemented from the description: format compliance, symbol
    frequency, run structure, positional balance.
  - Its Theta(1/eps) and Theta(1/eps^2) query-complexity results are theory we
    inherit, not results we reproduce.

This is the auditor arm A7 (laundering) is built to defeat: every feature below
is a property of the visible string, and a restyling pass rewrites all of them
without touching the answer. If A7 does not beat IRIS-lite, one of the two is
not doing its job.
"""

from __future__ import annotations

import math
import unicodedata
from collections import Counter
from typing import Any, Sequence

from ..base import Auditor, Observation

_PUNCT_CATS = {"Po", "Pd", "Ps", "Pe", "Pi", "Pf", "Pc", "Sm", "Sc", "Sk", "So"}

FEATURE_NAMES = [
    "length", "n_tokens", "mean_token_len", "digit_ratio", "alpha_ratio",
    "upper_ratio", "punct_ratio", "space_ratio", "distinct_char_ratio",
    "char_entropy", "ends_period", "starts_upper", "leading_space",
    "trailing_space", "max_run", "n_lines",
]


def features(text: str) -> list[float]:
    """Visible-string features. Deliberately shallow - no semantics.

    Every one of these is a FORMATTING habit, not a fact about the answer. That
    is IRIS's strength (it works on any text, in any language, with no reference
    model) and precisely its exposure to a laundering adversary.
    """
    t = text or ""
    n = len(t)
    if n == 0:
        return [0.0] * len(FEATURE_NAMES)

    tokens = t.split()
    cats = [unicodedata.category(c) for c in t]
    counts = Counter(t)
    entropy = -sum(
        (c / n) * math.log2(c / n) for c in counts.values() if c
    )

    # Longest run of one character: models differ in how they pad and repeat.
    max_run = run = 1
    for i in range(1, n):
        run = run + 1 if t[i] == t[i - 1] else 1
        max_run = max(max_run, run)

    return [
        float(n),
        float(len(tokens)),
        sum(len(w) for w in tokens) / len(tokens) if tokens else 0.0,
        sum(c.isdigit() for c in t) / n,
        sum(c.isalpha() for c in t) / n,
        sum(c.isupper() for c in t) / max(sum(c.isalpha() for c in t), 1),
        sum(1 for c in cats if c in _PUNCT_CATS) / n,
        sum(c.isspace() for c in t) / n,
        len(counts) / n,
        entropy,
        1.0 if t.rstrip().endswith(".") else 0.0,
        1.0 if t[:1].isupper() else 0.0,
        1.0 if t[:1].isspace() else 0.0,
        1.0 if t[-1:].isspace() else 0.0,
        float(max_run),
        float(t.count("\n") + 1),
    ]


class IRISAuditor(Auditor):
    name = "IRIS-lite"
    paper = "IRIS (identity verification from visible responses)"
    requires_reference = True

    def __init__(self, threshold: float | None = None, *, n_splits: int = 5,
                 n_estimators: int = 200, seed: int = 0, min_per_side: int = 30,
                 **kw: Any):
        super().__init__(threshold, **kw)
        self.n_splits = n_splits
        self.n_estimators = n_estimators
        self.seed = seed
        self.min_per_side = min_per_side

    def check_applicable(self, suspect, reference):
        base = super().check_applicable(suspect, reference)
        if base:
            return base
        n_s = sum(1 for o in suspect if o.ok and (o.text or "").strip())
        n_r = sum(1 for o in (reference or []) if o.ok and (o.text or "").strip())
        if min(n_s, n_r) < self.min_per_side:
            return (
                f"needs >={self.min_per_side} non-empty responses per side "
                f"(suspect={n_s}, reference={n_r})"
            )
        return None

    def score(self, suspect: Sequence[Observation], reference: Sequence[Observation]):
        import numpy as np
        from scipy.stats import binomtest
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.model_selection import StratifiedKFold, cross_val_predict

        def matrix(obs):
            return [features(o.text or "") for o in obs if o.ok and (o.text or "").strip()]

        Xs, Xr = matrix(suspect), matrix(reference)
        X = np.asarray(Xr + Xs, dtype=float)
        y = np.asarray([0] * len(Xr) + [1] * len(Xs), dtype=int)

        # Constant columns carry no signal and make some splitters unhappy.
        keep = X.std(axis=0) > 0
        if not keep.any():
            return float("nan"), {
                "reason": "every visible-string feature is constant across both samples"
            }

        clf = RandomForestClassifier(
            n_estimators=self.n_estimators, random_state=self.seed, n_jobs=1,
        )
        cv = StratifiedKFold(n_splits=self.n_splits, shuffle=True, random_state=self.seed)
        pred = cross_val_predict(clf, X[:, keep], y, cv=cv)

        correct = int((pred == y).sum())
        n = len(y)
        acc = correct / n
        # One-sided: only ABOVE-chance separability is evidence of two backends.
        p = binomtest(correct, n, 0.5, alternative="greater").pvalue

        # Fit once more on everything, purely for attribution. This model is not
        # used for the decision, so it cannot leak an optimistic accuracy.
        clf.fit(X[:, keep], y)
        names = [n_ for n_, k in zip(FEATURE_NAMES, keep) if k]
        importances = dict(
            sorted(zip(names, (float(v) for v in clf.feature_importances_)),
                   key=lambda kv: -kv[1])
        )

        # Score is scaled so 0 = chance and 1 = perfect separation, matching the
        # [0,1] convention the other auditors use.
        return max(0.0, 2.0 * (acc - 0.5)), {
            "cv_accuracy": acc,
            "p_value": p,
            "n_suspect": len(Xs),
            "n_reference": len(Xr),
            "n_features_used": int(keep.sum()),
            "top_features": dict(list(importances.items())[:5]),
            "feature_importances": importances,
        }
