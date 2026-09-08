"""FUSE - behavioural x operational fusion. New here, not from any source paper.

Every published auditor reads one channel. OTE reads the answer distribution,
IRIS the visible string, GATEOPS the timing, KBF factual recall. Each is
individually evadable, and the evaluation grid shows exactly how: A7 rewrites the
surface and beats IRIS, A9 reshapes latency and beats GATEOPS, A5 detects probes
and beats everything probe-shaped.

But those evasions have different costs, and no adversary pays all of them at
once. Laundering costs a second inference call per request. Latency shaping
costs the entire speed advantage that motivated the substitution. Canary lookups
cost nothing but only cover memorised items. FUSE asks the question that follows:
if a defender combines channels, must the adversary defeat all of them
simultaneously - and at what point does evasion cost more than honesty?

Mechanism. Each channel contributes a p-value; each p-value is calibrated into an
e-value; the e-values are multiplied into a test martingale. Ville's inequality
bounds the probability that the product EVER exceeds 1/alpha at alpha, so the
defender may stop as soon as it does, at any time, having peeked as often as they
like. That anytime-validity is what makes the dollars-to-detection frontier
meaningful: sample size becomes a budget decision instead of a statistical
commitment.

Two honest caveats, both reported rather than buried:

  * Multiplying e-values assumes the channels are independent. They read
    genuinely different signals, so it is defensible, but it is an assumption.
    The averaged e-value, valid under ARBITRARY dependence, is reported
    alongside, so a reader can see how much power rests on that assumption.
  * An inapplicable channel contributes e=1 - the neutral element. It neither
    helps nor hurts, which is the whole point of arena/base.py's `uninformative`
    decision. On this fleet RUT contributes e=1 always, and that is visible in
    the output rather than hidden in an average.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from ..base import AuditResult, Decision
from ..evalue import Martingale, average_e, combine_e, p_to_e


def channel_p(result: AuditResult) -> float:
    """The p-value a channel reports, or NaN when it has none.

    Auditors here expose `p_value` in their detail dict. OTE reports the
    Fisher-combined per-cell permutation p-value under `fisher_p`.
    """
    if not result.applicable:
        return float("nan")
    d = result.detail or {}
    for key in ("p_value", "fisher_p"):
        v = d.get(key)
        if isinstance(v, (int, float)) and v == v:
            return float(v)
    return float("nan")


def fuse(
    results: Mapping[str, AuditResult],
    *,
    alpha: float = 0.01,
    kappa: float = 0.5,
    order: Sequence[str] | None = None,
) -> AuditResult:
    """Combine per-channel AuditResults into one anytime-valid verdict."""
    names = list(order or results.keys())
    mart = Martingale(alpha=alpha)

    per_channel: dict[str, Any] = {}
    evalues: list[float] = []
    n_applicable = 0
    queries = 0
    cost = 0.0

    for name in names:
        res = results.get(name)
        if res is None:
            continue
        queries += res.queries
        cost += res.cost_usd
        p = channel_p(res)
        e = p_to_e(p, kappa) if p == p else float("nan")
        mart.update(e, channel=name)
        evalues.append(e)
        if res.applicable:
            n_applicable += 1
        per_channel[name] = {
            "applicable": res.applicable,
            "decision": res.decision,
            "score": res.score,
            "p_value": p,
            "e_value": e,
            "reason": (res.detail or {}).get("reason") if not res.applicable else None,
        }

    if n_applicable == 0:
        return AuditResult.uninformative(
            "no channel was applicable", queries=queries, cost_usd=cost
        )

    product = combine_e(evalues)
    averaged = average_e(evalues)

    # The decision uses the PRODUCT, and the averaged value is reported so the
    # cost of the independence assumption is visible rather than implicit.
    decision: Decision = "inconsistent" if product >= 1.0 / alpha else "consistent"

    return AuditResult(
        decision=decision,
        # log10 of the e-value is the natural scale: evidence accumulates
        # multiplicatively, and a linear score would be unreadable across arms
        # spanning e = 1 to e = 1e12.
        score=math.log10(product) if product > 0 else float("-inf"),
        e_value=product,
        queries=queries,
        cost_usd=cost,
        applicable=True,
        channel_scores={k: v["e_value"] for k, v in per_channel.items()},
        detail={
            "alpha": alpha,
            "threshold_e": 1.0 / alpha,
            "e_product": product,
            "e_average_dependence_robust": averaged,
            "rejected_product": product >= 1.0 / alpha,
            "rejected_average": averaged >= 1.0 / alpha,
            "n_channels": len(per_channel),
            "n_applicable": n_applicable,
            "per_channel": per_channel,
            "martingale": mart.summary(),
        },
    )
