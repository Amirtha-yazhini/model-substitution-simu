"""BENCH - accuracy-based detection (after Cai et al.).

The most intuitive auditor in the literature and, measured here, the most easily
defeated. Run public benchmark items through the endpoint, compare accuracy
against the reference, and test the difference. If the provider swapped in a
weaker model, accuracy should fall.

Unlike every other auditor here, BENCH needs GROUND TRUTH, which it legitimately
has: MMLU, GPQA and GSM8K answers are public. That is the method's convenience
and its fatal weakness in one property. Public means finite, finite means
hashable, and hashable means arm A10 can hold a lookup table and route exactly
those requests to the genuine model. Accuracy then comes back clean while every
other request gets the cheap model.

So A10 is not a contrived attack. It is the direct consequence of building a
detector on a public, static dataset, and it costs an adversary a hash-set
lookup. The prediction going in was that A10 should defeat BENCH completely and
that A10 should be the WEAKEST evasion against everything else, since any
paraphrase slips past an exact match. Both halves are testable, and the
evaluation grid tests them.

Statistically this is a two-proportion test on accuracy. It is quota-expensive
per bit of evidence - benchmark items need long completions, where OTE's need
one token - which is the other half of why it fares badly in the economics.
"""

from __future__ import annotations

import re
from typing import Any, Sequence

from ..base import Auditor, Observation, group_by_cell
from .ote import normalise

_LETTER = re.compile(r"\b([a-d])\b")


def extract_choice(text: str, expected: str) -> str | None:
    """Parse an answer, shaped by what the item expects.

    Multiple-choice and numeric items fail in different ways, and a single
    parser gets both wrong: a bare 'B' looks like a word, and '72' inside prose
    needs the last-number rule that reasoning traces force on us.
    """
    s = normalise(text)
    if not s:
        return None
    if expected.upper() in ("A", "B", "C", "D"):
        hits = _LETTER.findall(s)
        return hits[-1].upper() if hits else None
    nums = re.findall(r"-?\b\d+\b", s)
    return nums[-1] if nums else None


class BenchAuditor(Auditor):
    name = "BENCH"
    paper = "Cai et al. (benchmark-accuracy detection)"
    requires_reference = True

    def __init__(self, threshold: float | None = None, *,
                 answer_key: dict[str, str] | None = None,
                 min_items: int = 20, **kw: Any):
        super().__init__(threshold, **kw)
        # cell -> correct answer. Public knowledge, which is the whole point.
        self.answer_key = answer_key or {}
        self.min_items = min_items

    def check_applicable(self, suspect, reference):
        base = super().check_applicable(suspect, reference)
        if base:
            return base
        if not self.answer_key:
            return "no answer key supplied - BENCH cannot score correctness"
        scorable = sum(1 for o in suspect if o.ok and o.cell in self.answer_key)
        if scorable < self.min_items:
            return (
                f"only {scorable} suspect responses map to a known answer; "
                f"need {self.min_items}"
            )
        return None

    def _accuracy(self, obs: Sequence[Observation]) -> tuple[int, int, dict[str, Any]]:
        hits = n = 0
        per_cell: dict[str, Any] = {}
        for cell, group in group_by_cell(obs).items():
            correct = self.answer_key.get(cell)
            if correct is None:
                continue
            c = t = 0
            for o in group:
                if not o.ok:
                    continue
                got = extract_choice(o.text or "", correct)
                if got is None:
                    continue
                t += 1
                c += 1 if got.upper() == correct.upper() else 0
            if t:
                per_cell[cell] = {"correct": c, "n": t, "accuracy": c / t}
                hits += c
                n += t
        return hits, n, per_cell

    def score(self, suspect: Sequence[Observation], reference: Sequence[Observation]):
        from scipy.stats import norm

        s_hit, s_n, s_cells = self._accuracy(suspect)
        r_hit, r_n, r_cells = self._accuracy(reference)

        if s_n == 0 or r_n == 0:
            return float("nan"), {
                "reason": f"no parsable graded answers (suspect n={s_n}, reference n={r_n})"
            }

        p_s, p_r = s_hit / s_n, r_hit / r_n
        pooled = (s_hit + r_hit) / (s_n + r_n)
        se = (pooled * (1 - pooled) * (1 / s_n + 1 / r_n)) ** 0.5
        if se == 0:
            # Both sides answered everything identically - no variance, no test.
            z, p = 0.0, 1.0
        else:
            z = (p_r - p_s) / se
            # One-sided: only a DROP in accuracy is evidence of substitution.
            p = float(norm.sf(z))

        return max(0.0, p_r - p_s), {
            "p_value": p,
            "z": float(z),
            "suspect_accuracy": p_s,
            "reference_accuracy": p_r,
            "accuracy_drop": p_r - p_s,
            "n_suspect": s_n,
            "n_reference": r_n,
            "n_items": len(set(s_cells) & set(r_cells)),
            "per_cell_suspect": s_cells,
            "per_cell_reference": r_cells,
        }
