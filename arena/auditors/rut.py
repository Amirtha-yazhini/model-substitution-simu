"""RUT - rank-uniformity testing on emitted tokens.

The method is elegant. If an endpoint really is serving model M, then the tokens
it emits are samples from M's own next-token distribution, so the RANK of each
emitted token under a reference copy of M should be uniform. Substitute a
different model and that uniformity breaks. It is a sharp test, it uses the
strongest signal available, and on this fleet it cannot be run at all.

RUT needs per-token log-probabilities from the suspect endpoint and a reference
distribution to rank against. Our measured coverage
(results/tables/coverage.md): **0 of 11 free-tier endpoints return logprobs**.
Not few - none. The paper itself notes it needs a locally deployed reference
model; measured against real endpoints the requirement is not inconvenient but
disqualifying. DiFR, which needs raw logits, is worse off still.

So this class exists to return `uninformative`, and that is a result rather than
a gap. The implementation below is real - given logprobs it computes ranks and
runs the uniformity test - so the claim "cannot run here" is a measurement about
the fleet, not an excuse for unwritten code. arena/base.py enforces the rest: a
method that cannot run is never scored as agreement.
"""

from __future__ import annotations

from typing import Any, Sequence

from ..base import Auditor, Observation


def token_ranks(logprobs: Any) -> list[int]:
    """Rank of each emitted token within its own top-k, 0 = most likely.

    Accepts the OpenAI `choices[].logprobs.content[]` shape: per position, the
    chosen token plus a `top_logprobs` list. A token outside the returned top-k
    has no observable rank and is skipped - which biases the test toward
    uniformity and therefore toward NOT flagging, the conservative direction.
    """
    out: list[int] = []
    content = (logprobs or {}).get("content") if isinstance(logprobs, dict) else None
    for pos in content or []:
        chosen = pos.get("token")
        alts = pos.get("top_logprobs") or []
        ranked = sorted(alts, key=lambda a: -a.get("logprob", float("-inf")))
        for i, a in enumerate(ranked):
            if a.get("token") == chosen:
                out.append(i)
                break
    return out


class RUTAuditor(Auditor):
    name = "RUT"
    paper = "Rank-uniformity testing"
    requires_logprobs = True
    requires_reference = False       # ranks are self-referential given logprobs

    def __init__(self, threshold: float | None = None, *, min_tokens: int = 100, **kw: Any):
        super().__init__(threshold, **kw)
        self.min_tokens = min_tokens

    def check_applicable(self, suspect, reference):
        base = super().check_applicable(suspect, reference)
        if base:
            return base
        n = sum(len(token_ranks(o.logprobs)) for o in suspect if o.ok)
        if n < self.min_tokens:
            return f"only {n} ranked tokens available; need {self.min_tokens}"
        return None

    def score(self, suspect: Sequence[Observation], reference):
        from scipy.stats import chisquare

        ranks: list[int] = []
        for o in suspect:
            if o.ok:
                ranks.extend(token_ranks(o.logprobs))
        if not ranks:
            return float("nan"), {"reason": "no ranked tokens"}

        k = max(ranks) + 1
        observed = [ranks.count(i) for i in range(k)]
        expected = [len(ranks) / k] * k
        stat, p = chisquare(observed, expected)

        # Score in [0,1]: total variation distance from uniform.
        tv = 0.5 * sum(abs(o - e) for o, e in zip(observed, expected)) / len(ranks)
        return float(tv), {
            "p_value": float(p),
            "chi2": float(stat),
            "n_tokens": len(ranks),
            "k_ranks": k,
            "rank_histogram": observed,
        }
