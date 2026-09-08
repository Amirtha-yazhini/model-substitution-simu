"""p-values, e-values, test martingales, and anytime-valid stopping.

Why e-values at all. Every auditor here produces evidence sequentially - probe,
probe, probe - and the natural question is "may I stop now?". A fixed-sample
p-value cannot answer it: peeking at a p-value and stopping when it dips below
0.05 inflates Type I error without bound, which is exactly the optional-stopping
trap. That matters here more than usual, because the economics analysis is about
BUYING evidence, and the whole point is to buy as little as possible.

An e-value is a nonnegative statistic with expectation at most 1 under the null.
Multiply independent e-values and you get a test martingale; Ville's inequality
then says the probability that such a martingale EVER exceeds 1/alpha is at most
alpha. So "stop as soon as E > 1/alpha" is valid at any stopping time, including
one chosen by looking at the data. Sample size becomes a budget decision rather
than a statistical commitment - which is what the dollars-to-detection frontier
needs to be meaningful.

References: Vovk & Wang on p-to-e calibration, Ramdas et al. on test martingales.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence


def p_to_e(p: float, kappa: float = 0.5) -> float:
    """Calibrate a p-value into an e-value.

    Uses the standard power family e = kappa * p^(kappa-1), which is a valid
    calibrator for any kappa in (0,1): it is nonincreasing in p and integrates to
    at most 1 under a uniform null. kappa=0.5 gives e = 0.5/sqrt(p), a middling
    choice - smaller kappa rewards very small p-values harder but wastes evidence
    on moderate ones.

    Note e is bounded by 0.5/sqrt(p_min): a single probe cannot manufacture
    unlimited evidence, which is the property that makes the martingale honest.
    """
    if p != p:                      # NaN in, NaN out: an uninformative channel
        return float("nan")
    p = min(max(p, 1e-12), 1.0)
    return kappa * p ** (kappa - 1.0)


def empirical_p(score: float, null_scores: Sequence[float]) -> float:
    """p-value of `score` against an empirical null, upper tail.

    The (b+1)/(n+1) form is deliberate: it is the conformal p-value, valid in
    finite samples under exchangeability, and it never returns exactly zero -
    which matters because p_to_e takes a power of it and downstream code takes
    logs.
    """
    if score != score or not null_scores:
        return float("nan")
    at_least = sum(1 for s in null_scores if s >= score)
    return (at_least + 1) / (len(null_scores) + 1)


@dataclass
class Martingale:
    """Running product of e-values, with an anytime-valid stopping rule."""

    alpha: float = 0.01
    value: float = 1.0
    history: list[float] = field(default_factory=list)
    contributions: dict[str, float] = field(default_factory=dict)

    @property
    def threshold(self) -> float:
        return 1.0 / self.alpha

    @property
    def rejected(self) -> bool:
        return self.value >= self.threshold

    def update(self, e: float, *, channel: str | None = None) -> float:
        """Multiply in one e-value. NaN (an inapplicable channel) contributes 1.

        Treating an inapplicable channel as e=1 is the correct neutral element:
        it neither helps nor hurts the case, which is precisely the semantics
        arena/base.py's `uninformative` decision is after. Scoring it as evidence
        either way would be the mistake the frozen-threshold study found.
        """
        if e != e:
            e = 1.0
        self.value *= max(e, 0.0)
        self.history.append(self.value)
        if channel:
            self.contributions[channel] = e
        return self.value

    def stopped_at(self) -> int | None:
        """Index of the first update where the martingale crossed. None if never."""
        for i, v in enumerate(self.history):
            if v >= self.threshold:
                return i
        return None

    def summary(self) -> dict[str, float | bool | int | None]:
        return {
            "e_value": self.value,
            "log10_e": math.log10(self.value) if self.value > 0 else float("-inf"),
            "threshold": self.threshold,
            "rejected": self.rejected,
            "stopped_at": self.stopped_at(),
            "n_updates": len(self.history),
        }


def fisher_to_e(p: float, kappa: float = 0.5) -> float:
    """Convenience alias kept explicit at call sites for readability."""
    return p_to_e(p, kappa)


def combine_e(evalues: Sequence[float]) -> float:
    """Product of e-values - a test martingale's terminal value.

    Multiplication requires the channels to be independent (or at least that each
    is an e-value conditional on the others). Our channels read genuinely
    different signals - answer distributions, surface strings, latency, factual
    recall - so this is defensible, but it is an ASSUMPTION and the report says
    so. The conservative alternative, averaging, is valid under arbitrary
    dependence and is offered below.
    """
    out = 1.0
    for e in evalues:
        out *= 1.0 if e != e else max(e, 0.0)
    return out


def average_e(evalues: Sequence[float]) -> float:
    """Mean of e-values: valid under ARBITRARY dependence between channels.

    Strictly weaker than the product when channels really are independent, and
    strictly safer when they are not. FUSE reports both so a reader can see how
    much of its power comes from the independence assumption.
    """
    vals = [1.0 if e != e else max(e, 0.0) for e in evalues]
    return sum(vals) / len(vals) if vals else 1.0
