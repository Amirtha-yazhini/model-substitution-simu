"""GATEOPS - operational signals (after GateScope).

Behavioural auditors ask what the model SAID. GateScope asks how the endpoint
BEHAVED: how long it took, how consistent that timing was, what metadata it
returned, and what the bill looked like. Those signals are attractive because
they survive an adversary who controls the text completely - laundering rewrites
a response but cannot make a 8B model take as long as a 70B one without actually
waiting.

Three channels here, and their coverage is as much the result as their power:

  latency      Two-sample Kolmogorov-Smirnov on response times, plus the
               coefficient of variation sigma/mu that GateScope reports. Works
               on 11/11 endpoints - timing needs no provider cooperation.
  fingerprint  Distinct `system_fingerprint` values, and whether the suspect
               shows any the reference never did. Only 7/11 endpoints emit one.
  billing      GateScope's strongest published channel, and INAPPLICABLE here:
               free tiers issue no invoice, and only 2/11 endpoints report
               usage.cached_tokens. Recorded as coverage rather than worked
               around - it is an honest finding about where the method
               transfers, not a gap to paper over.

Not implemented: the 25-turn memory-checkpoint dimension. It needs multi-turn
conversational state that the probe suites here do not generate, and claiming it
without running it would be exactly the sin this project exists to document. It
is declared in `channels_not_run` so the coverage table stays truthful.

Arm A9 (latency shaping) is built to defeat the latency channel, and shapes
toward a REALISTIC coefficient of variation rather than flattening it - an
implausibly smooth endpoint is itself a tell, and GateScope's own baseline was
about 0.63, not 0.
"""

from __future__ import annotations

import statistics
from typing import Any, Sequence

from ..base import Auditor, Observation


def cv(values: Sequence[float]) -> float:
    """Coefficient of variation, GateScope's headline statistic."""
    vals = [v for v in values if v and v > 0]
    if len(vals) < 2:
        return float("nan")
    mu = statistics.mean(vals)
    return statistics.stdev(vals) / mu if mu > 0 else float("nan")


class GateOpsAuditor(Auditor):
    name = "GATEOPS"
    paper = "GateScope (operational-signal auditing)"
    requires_reference = True

    channels_not_run = ("memory_checkpoints",)

    def __init__(self, threshold: float | None = None, *, min_per_side: int = 20, **kw: Any):
        super().__init__(threshold, **kw)
        self.min_per_side = min_per_side

    def check_applicable(self, suspect, reference):
        base = super().check_applicable(suspect, reference)
        if base:
            return base
        n_s = sum(1 for o in suspect if o.ok and o.latency_s > 0)
        n_r = sum(1 for o in (reference or []) if o.ok and o.latency_s > 0)
        if min(n_s, n_r) < self.min_per_side:
            return (
                f"needs >={self.min_per_side} timed responses per side "
                f"(suspect={n_s}, reference={n_r}); replayed corpora carry "
                f"recorded latencies, but a cache-served arm has none"
            )
        return None

    def score(self, suspect: Sequence[Observation], reference: Sequence[Observation]):
        from scipy.stats import ks_2samp

        lat_s = [o.latency_s for o in suspect if o.ok and o.latency_s > 0]
        lat_r = [o.latency_s for o in reference if o.ok and o.latency_s > 0]

        ks = ks_2samp(lat_s, lat_r)
        cv_s, cv_r = cv(lat_s), cv(lat_r)

        fp_s = {o.system_fingerprint for o in suspect if o.system_fingerprint}
        fp_r = {o.system_fingerprint for o in reference if o.system_fingerprint}
        fp_applicable = bool(fp_s or fp_r)
        # A fingerprint the reference never emitted is direct evidence of a
        # backend the client was not promised.
        fp_novel = sorted(fp_s - fp_r)

        cached = [o for o in suspect if "cached_tokens" in (o.usage or {})]
        billing_applicable = bool(cached)

        channels = {
            "latency_ks": float(ks.statistic),
            "latency_cv_delta": (
                abs(cv_s - cv_r) if cv_s == cv_s and cv_r == cv_r else float("nan")
            ),
            "fingerprint_novel": float(len(fp_novel)) if fp_applicable else float("nan"),
        }

        # The KS statistic is already a [0,1] distance between the two timing
        # distributions, so it doubles as the score. The fingerprint channel is
        # reported but not folded in: one novel fingerprint is categorical
        # evidence, not a matter of degree, and averaging it into a distance
        # would blur that.
        return float(ks.statistic), {
            "latency_ks_stat": float(ks.statistic),
            "latency_ks_p": float(ks.pvalue),
            "p_value": float(ks.pvalue),
            "cv_suspect": cv_s,
            "cv_reference": cv_r,
            "median_latency_suspect": statistics.median(lat_s),
            "median_latency_reference": statistics.median(lat_r),
            "n_suspect": len(lat_s),
            "n_reference": len(lat_r),
            "fingerprints_suspect": sorted(fp_s),
            "fingerprints_reference": sorted(fp_r),
            "fingerprint_novel": fp_novel,
            "channels": channels,
            "channels_applicable": {
                "latency": True,
                "fingerprint": fp_applicable,
                # The honest zero. See the module docstring.
                "billing": billing_applicable,
                "memory_checkpoints": False,
            },
            "channels_not_run": list(self.channels_not_run),
        }
