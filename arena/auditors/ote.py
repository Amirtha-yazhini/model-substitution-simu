"""OTE-lite - "One Token Is Enough" (Bruckner, arXiv:2607.10252).

Method: ask trivial closed-answer questions ("name a random number between 1 and
100"), collect the empirical answer distribution per probe cell, and compare the
suspect's distribution to a reference by mean Jensen-Shannon divergence.

Why it works: models are NOT uniform on these questions. Bruckner reports a
median per-cell entropy of ~1.0 bit against theoretical baselines of 1-6.6 bits,
and stable family-specific biases (GPT-family favours 42 and 73; others prefer
57, 37, 7). Our own capability probe saw four unrelated reasoning models all
answer 42.

Reported results (full 40-cell battery): AUC 0.971, EER 7.3%, $34.44 for a
165-model census. At the reduced 8-cell operating point we use: EER 10.6%.

Deltas from the paper, stated plainly:
  - 8 cells, not 40 - his own documented ablation, forced here by free-tier
    request quotas.
  - max_tokens 256, not 16. On reasoning endpoints a 16-token cap returns an
    empty string (see results/tables/coverage.md), so the published protocol
    would simply fail on 36% of our fleet.
  - Normalisation is reimplemented from the description, not his code.
  - The reported statistic is PERMUTATION-DEBIASED. Plug-in Jensen-Shannon on a
    sparse categorical is upward-biased at small n: two samples drawn from the
    SAME distribution score well above zero. At 30 repeats/cell that bias was
    0.176 here - larger than most of the separation we were trying to measure,
    and it put four arms below the honest baseline rather than near zero.
    Subtracting a per-comparison permutation estimate removes it and yields an
    exact p-value for free. Bruckner thresholds the raw statistic; we report
    both, and `raw_mean_jsd` in the detail dict is directly comparable to his.
Treat our numbers as a LOWER BOUND on the original method.
"""

from __future__ import annotations

import hashlib
import math
import random
import re
import unicodedata
from collections import Counter
from typing import Any, Sequence

from ..base import Auditor, Observation, group_by_cell

# Digit systems Bruckner normalises across (Arabic-Indic, Devanagari, CJK).
_DIGIT_MAP = {
    **{chr(0x0660 + i): str(i) for i in range(10)},   # Arabic-Indic
    **{chr(0x06F0 + i): str(i) for i in range(10)},   # Extended Arabic-Indic
    **{chr(0x0966 + i): str(i) for i in range(10)},   # Devanagari
    **{chr(0xFF10 + i): str(i) for i in range(10)},   # Fullwidth
}
_CJK_NUM = {
    "零": "0", "一": "1", "二": "2", "三": "3", "四": "4",
    "五": "5", "六": "6", "七": "7", "八": "8", "九": "9", "十": "10",
}

_REASONING_TAG = re.compile(r"<think>.*?</think>|<reasoning>.*?</reasoning>", re.S | re.I)
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)


def normalise(text: str) -> str:
    """Deterministic normalisation: strip reasoning, unify digits, fold case.

    Order matters. Reasoning blocks are removed FIRST - on this fleet many
    endpoints wrap the answer in a trace, and treating that trace as part of the
    answer would make every reasoning model look like its own distinct 'model'.
    """
    if not text:
        return ""
    s = _REASONING_TAG.sub(" ", text)
    s = unicodedata.normalize("NFKC", s)
    s = "".join(_DIGIT_MAP.get(ch, ch) for ch in s)
    for cjk, ar in _CJK_NUM.items():
        s = s.replace(cjk, ar)
    s = _PUNCT.sub(" ", s)
    return " ".join(s.lower().split())


def extract_answer(text: str, cell: str) -> str | None:
    """Pull the single categorical answer out of a normalised response."""
    s = normalise(text)
    if not s:
        return None

    if cell.startswith(("rand100", "rand10", "favnum")):
        nums = re.findall(r"\b\d{1,3}\b", s)
        if not nums:
            return None
        # The LAST number: reasoning models often restate the range ("between 1
        # and 100") before answering, so the first match is usually the prompt
        # echoed back, not the answer.
        hi = 100 if "100" in cell else 10
        for n in reversed(nums):
            v = int(n)
            if 1 <= v <= hi:
                return str(v)
        return None

    if cell.startswith("coin"):
        for w in ("heads", "tails"):
            if w in s:
                return w
        return None

    tokens = s.split()
    return tokens[-1] if tokens else None


def _dist(answers: Sequence[str]) -> dict[str, float]:
    c = Counter(a for a in answers if a)
    n = sum(c.values())
    return {k: v / n for k, v in c.items()} if n else {}


def jensen_shannon(p: dict[str, float], q: dict[str, float]) -> float:
    """JSD in bits, base 2, so the result lies in [0, 1].

    Well-defined on disjoint supports (unlike KL), which matters: two models can
    easily share no answers at all on a low-entropy cell.
    """
    keys = set(p) | set(q)
    if not keys:
        return float("nan")
    total = 0.0
    for k in keys:
        pi, qi = p.get(k, 0.0), q.get(k, 0.0)
        mi = 0.5 * (pi + qi)
        if pi > 0:
            total += 0.5 * pi * math.log2(pi / mi)
        if qi > 0:
            total += 0.5 * qi * math.log2(qi / mi)
    return max(0.0, min(1.0, total))


# ----------------------------------------------------------------------
# Debiasing
#
# The plug-in JSD estimator is biased upward at small n, badly so on sparse
# categoricals: draw two samples of 30 from ONE distribution and they will not
# share support, which the estimator reads as divergence. The bias depends on n
# and on the distribution's effective support, so it cannot be subtracted with a
# constant - it has to be estimated per comparison.
#
# A permutation does exactly that. Pool the two samples, reshuffle, re-split at
# the original sizes, recompute. Under the null (same source) that resample is
# distributed like the observed statistic, so its mean IS the bias; under the
# alternative it estimates what the statistic would have been had the labels
# carried no information. The same permutations give an exact p-value at no
# extra cost.
# ----------------------------------------------------------------------

DEFAULT_PERMUTATIONS = 200


def permutation_jsd(
    sus: Sequence[str], ref: Sequence[str], *,
    n_perm: int = DEFAULT_PERMUTATIONS, seed: int = 0,
) -> tuple[float, float, float]:
    """Return (observed JSD, permutation-mean JSD, p-value).

    The p-value is the standard (b+1)/(B+1) form, which keeps it strictly
    positive - important because the Fisher combination below takes its log.
    """
    obs = jensen_shannon(_dist(sus), _dist(ref))
    if obs != obs:  # NaN: nothing to permute
        return obs, float("nan"), float("nan")

    pool = [*sus, *ref]
    k = len(sus)
    rng = random.Random(seed)
    total = 0.0
    at_least = 0
    for _ in range(n_perm):
        rng.shuffle(pool)
        v = jensen_shannon(_dist(pool[:k]), _dist(pool[k:]))
        total += v
        if v >= obs:
            at_least += 1
    return obs, total / n_perm, (at_least + 1) / (n_perm + 1)


def _chi2_sf_even(x: float, df: int) -> float:
    """Upper tail of chi-square for EVEN df, in closed form.

    Fisher's statistic always has df=2k, so the series terminates and we need no
    scipy dependency in the hot path:  sf = e^{-x/2} * sum_{i<k} (x/2)^i / i!
    """
    if x <= 0:
        return 1.0
    k = df // 2
    half = x / 2.0
    term = 1.0
    acc = 1.0
    for i in range(1, k):
        term *= half / i
        acc += term
    return min(1.0, math.exp(-half) * acc)


def fisher_combine(pvals: Sequence[float]) -> tuple[float, float]:
    """Combine independent per-cell p-values. Returns (statistic, p).

    Cells are separate prompts sent independently, so treating them as
    independent is reasonable here - which is exactly why Bruckner's battery
    gains power by adding cells rather than repeats.
    """
    ps = [p for p in pvals if p == p]
    if not ps:
        return float("nan"), float("nan")
    stat = -2.0 * sum(math.log(max(p, 1e-12)) for p in ps)
    return stat, _chi2_sf_even(stat, 2 * len(ps))


class OTEAuditor(Auditor):
    name = "OTE"
    paper = "Bruckner 2026, arXiv:2607.10252"
    requires_reference = True

    def __init__(
        self, threshold: float | None = None, min_per_cell: int = 8,
        n_perm: int = DEFAULT_PERMUTATIONS, **kw: Any,
    ):
        super().__init__(threshold, **kw)
        self.min_per_cell = min_per_cell
        self.n_perm = n_perm

    def answers_by_cell(self, obs: Sequence[Observation]) -> dict[str, list[str]]:
        """Per-cell list of extracted answers, gated on min_per_cell.

        The permutation test needs the raw samples, not just the distribution -
        the bias it corrects is a function of sample SIZE, which a normalised
        distribution has already thrown away.
        """
        out: dict[str, list[str]] = {}
        for cell, group in group_by_cell(obs).items():
            answers = [extract_answer(o.text or "", cell) for o in group if o.ok]
            answers = [a for a in answers if a]
            if len(answers) >= self.min_per_cell:
                out[cell] = answers
        return out

    def fingerprint(self, obs: Sequence[Observation]) -> dict[str, dict[str, float]]:
        """Per-cell empirical answer distribution."""
        return {c: _dist(a) for c, a in self.answers_by_cell(obs).items()}

    def score(self, suspect, reference):
        ans_s = self.answers_by_cell(suspect)
        ans_r = self.answers_by_cell(reference or [])

        shared = sorted(set(ans_s) & set(ans_r))
        if not shared:
            return float("nan"), {
                "reason": (
                    f"no cell had >={self.min_per_cell} valid answers on both sides "
                    f"(suspect cells={sorted(ans_s)}, reference cells={sorted(ans_r)})"
                ),
                "cells_suspect": sorted(ans_s),
                "cells_reference": sorted(ans_r),
            }

        raw: dict[str, float] = {}
        bias: dict[str, float] = {}
        debiased: dict[str, float] = {}
        pvals: dict[str, float] = {}
        for c in shared:
            # Seeded on cell and sample sizes only, so every arm faces the SAME
            # permutation draws for a given cell shape (common random numbers).
            # That removes permutation noise from between-arm comparisons.
            seed = int(hashlib.sha256(
                f"{c}|{len(ans_s[c])}|{len(ans_r[c])}".encode()
            ).hexdigest()[:8], 16)
            o, b, p = permutation_jsd(
                ans_s[c], ans_r[c], n_perm=self.n_perm, seed=seed
            )
            raw[c], bias[c], pvals[c] = o, b, p
            # Deliberately NOT clamped at zero. Rectifying per cell would
            # reintroduce an upward bias in the mean, which is the entire thing
            # this correction exists to remove; the null must be free to go
            # negative so it centres on zero.
            debiased[c] = o - b

        mean_debiased = sum(debiased.values()) / len(debiased)
        mean_raw = sum(raw.values()) / len(raw)
        fisher_stat, fisher_p = fisher_combine([pvals[c] for c in shared])

        fp_s = {c: _dist(ans_s[c]) for c in shared}
        fp_r = {c: _dist(ans_r[c]) for c in shared}

        return mean_debiased, {
            "per_cell_jsd": debiased,
            "per_cell_raw_jsd": raw,
            "per_cell_bias": bias,
            "per_cell_p": pvals,
            # Bruckner thresholds this one; kept so our numbers stay comparable
            # to his published operating point.
            "raw_mean_jsd": mean_raw,
            "mean_bias": sum(bias.values()) / len(bias),
            "fisher_stat": fisher_stat,
            "fisher_p": fisher_p,
            "n_perm": self.n_perm,
            "cells_used": shared,
            "n_cells": len(shared),
            # Coverage is reported alongside the score, per the frozen-threshold
            # study's recommendation: a score from 2 cells is not a score from 8.
            "cell_coverage": len(shared) / max(len(set(ans_s) | set(ans_r)), 1),
            "suspect_modes": {c: max(fp_s[c], key=fp_s[c].get) for c in shared},
            "reference_modes": {c: max(fp_r[c], key=fp_r[c].get) for c in shared},
        }
