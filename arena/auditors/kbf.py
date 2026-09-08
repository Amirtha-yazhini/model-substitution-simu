"""KBF - knowledge-boundary fingerprinting.

The idea: pick factual items sitting at the edge of what a model reliably knows,
then ask whether the suspect recalls them as often as the reference does. Items
everyone gets right carry no information, and items nobody gets right carry none
either; the signal lives at the boundary, which is why the probe set matters more
here than for any other auditor.

Crucially, KBF is CONSENSUS-based, not answer-key-based. It never needs to know
the true answer - it takes the reference's modal response as the expected one and
measures how often the suspect agrees. That is what lets it run against any
endpoint with no curated dataset, and it is why its coverage is 11/11 while BENCH
depends on public benchmarks that an adversary can memorise.

The null is the reference's own self-agreement rate, not 100%. A model at
temperature 1 disagrees with itself on boundary items - that is what makes them
boundary items - so testing against perfect agreement would flag every honest
endpoint. Estimating the null from the reference is what keeps the false-positive
rate honest.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Sequence

from ..base import Auditor, Observation, group_by_cell
from .ote import normalise


def extract_fact(text: str) -> str | None:
    """Pull a short factual answer - a number, a year, or a single word."""
    s = normalise(text)
    if not s:
        return None
    nums = re.findall(r"\b\d{1,6}\b", s)
    if nums:
        # The LAST number, for the same reason OTE takes it: reasoning models
        # restate the question before answering.
        return nums[-1]
    tokens = s.split()
    return tokens[-1] if tokens else None


class KBFAuditor(Auditor):
    name = "KBF"
    paper = "Knowledge-boundary fingerprinting"
    requires_reference = True

    def __init__(self, threshold: float | None = None, *, min_per_cell: int = 3,
                 min_cells: int = 5, **kw: Any):
        super().__init__(threshold, **kw)
        self.min_per_cell = min_per_cell
        self.min_cells = min_cells

    def score(self, suspect: Sequence[Observation], reference: Sequence[Observation]):
        from scipy.stats import binomtest

        by_s = group_by_cell(suspect)
        by_r = group_by_cell(reference)
        shared = sorted(set(by_s) & set(by_r))

        ref_hits = ref_n = sus_hits = sus_n = 0
        per_cell: dict[str, dict[str, Any]] = {}
        used = []

        for cell in shared:
            r_ans = [extract_fact(o.text or "") for o in by_r[cell] if o.ok]
            s_ans = [extract_fact(o.text or "") for o in by_s[cell] if o.ok]
            r_ans = [a for a in r_ans if a]
            s_ans = [a for a in s_ans if a]
            if len(r_ans) < self.min_per_cell or len(s_ans) < self.min_per_cell:
                continue

            consensus, n_mode = Counter(r_ans).most_common(1)[0]
            r_hit = sum(1 for a in r_ans if a == consensus)
            s_hit = sum(1 for a in s_ans if a == consensus)

            ref_hits += r_hit
            ref_n += len(r_ans)
            sus_hits += s_hit
            sus_n += len(s_ans)
            used.append(cell)
            per_cell[cell] = {
                "consensus": consensus,
                "reference_rate": r_hit / len(r_ans),
                "suspect_rate": s_hit / len(s_ans),
                "n_reference": len(r_ans),
                "n_suspect": len(s_ans),
            }

        if len(used) < self.min_cells:
            return float("nan"), {
                "reason": (
                    f"only {len(used)} cells had >={self.min_per_cell} parsable answers "
                    f"on both sides; need {self.min_cells}"
                ),
                "cells_used": used,
            }

        p0 = ref_hits / ref_n            # the reference's own self-agreement
        rate = sus_hits / sus_n

        # One-sided: only a DEFICIT in agreement is evidence of substitution.
        # A suspect that agrees with the consensus MORE than the reference does
        # is odd, but it is not evidence that the client got a cheaper model -
        # if anything it suggests a lower sampling temperature, which is arm A4's
        # territory and a different auditor's problem.
        p = binomtest(sus_hits, sus_n, min(max(p0, 1e-9), 1 - 1e-9),
                      alternative="less").pvalue

        return max(0.0, p0 - rate), {
            "p_value": float(p),
            "reference_agreement": p0,
            "suspect_agreement": rate,
            "agreement_deficit": p0 - rate,
            "n_suspect": sus_n,
            "n_reference": ref_n,
            "n_cells": len(used),
            "cells_used": used,
            "cell_coverage": len(used) / max(len(set(by_s) | set(by_r)), 1),
            "per_cell": per_cell,
        }
