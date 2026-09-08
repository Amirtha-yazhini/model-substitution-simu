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
Treat our numbers as a LOWER BOUND on the original method.
"""

from __future__ import annotations

import math
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


class OTEAuditor(Auditor):
    name = "OTE"
    paper = "Bruckner 2026, arXiv:2607.10252"
    requires_reference = True

    def __init__(self, threshold: float | None = None, min_per_cell: int = 8, **kw: Any):
        super().__init__(threshold, **kw)
        self.min_per_cell = min_per_cell

    def fingerprint(self, obs: Sequence[Observation]) -> dict[str, dict[str, float]]:
        """Per-cell empirical answer distribution."""
        out: dict[str, dict[str, float]] = {}
        for cell, group in group_by_cell(obs).items():
            answers = [extract_answer(o.text or "", cell) for o in group if o.ok]
            answers = [a for a in answers if a]
            if len(answers) >= self.min_per_cell:
                out[cell] = _dist(answers)
        return out

    def score(self, suspect, reference):
        fp_s = self.fingerprint(suspect)
        fp_r = self.fingerprint(reference or [])

        shared = sorted(set(fp_s) & set(fp_r))
        if not shared:
            return float("nan"), {
                "reason": (
                    f"no cell had >={self.min_per_cell} valid answers on both sides "
                    f"(suspect cells={sorted(fp_s)}, reference cells={sorted(fp_r)})"
                ),
                "cells_suspect": sorted(fp_s),
                "cells_reference": sorted(fp_r),
            }

        per_cell = {c: jensen_shannon(fp_s[c], fp_r[c]) for c in shared}
        mean_jsd = sum(per_cell.values()) / len(per_cell)

        return mean_jsd, {
            "per_cell_jsd": per_cell,
            "cells_used": shared,
            "n_cells": len(shared),
            # Coverage is reported alongside the score, per the frozen-threshold
            # study's recommendation: a score from 2 cells is not a score from 8.
            "cell_coverage": len(shared) / max(len(set(fp_s) | set(fp_r)), 1),
            "suspect_modes": {c: max(fp_s[c], key=fp_s[c].get) for c in shared},
            "reference_modes": {c: max(fp_r[c], key=fp_r[c].get) for c in shared},
        }
