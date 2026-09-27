# Cost of Cheating vs. Cost of Catching It

> NOTE: budget 1.0 page. Synced from sections/*.tex after the plain-language rewrite; edit here and send back.

**Break-even.** If the gateway swaps a share $\epsilon$ of requests, it saves
$\$1{,}000 \cdot \epsilon \cdot (1 - r)$ for every \$1,000 the customer spends, where $r = 0.115$ is
the price of the cheaper model relative to the genuine one. We compare this with the cost of running
enough audit sessions to catch the cheating 80% of the time, using measured token counts and public
prices (Fig. F2).

> FIGURE F2 (fig_break_even): What the cheater saves per \$1,000 per month (top line) vs. what an audit costs to catch it 80% of the time, by share of requests swapped (v2, hand-written pair). Hollow markers would cause too many false alarms. In the shaded region no acceptable audit works.

*Cost is never the problem.* One audit session costs between \$0.0013 (KBF) and \$0.014
(FUSE). Wherever an auditor can reach 80%, the total is under one cent, while the cheater saves tens
of dollars. On price alone, auditing always pays.

*False alarms are the problem.* Running more sessions catches more cheating, but also raises
more false alarms. If one honest session is wrongly flagged with probability $f$, then $k$ sessions
produce at least one false alarm with probability $1 - (1-f)^k$. Our fixed rules allow at most a
5% chance of any false alarm per audit, which limits each auditor to 6–15 sessions. Below
$\epsilon = 0.10$, a single session almost never catches anything: at $\epsilon = 0.07$ the best
auditor catches 6% of sessions on the hand-written pair and 1% on the fitted pair, so 15 sessions
are not enough to reach 80%. The lowest cheating rate any acceptable audit can catch is therefore
$\epsilon^* = 0.10$ on both simulated pairs, with a bootstrap 95% interval of [0.10, 0.10].
IRIS-lite reaches it, catching 34% of single sessions and needing 4 sessions (hand-written pair), or
56% and 2 sessions (fitted pair), for \$0.003–\$0.006.

One caveat changes this number. IRIS-lite sets $\epsilon^*$ on both pairs, but on real recordings
it cannot tell the two models apart (Section [real]); in the simulator it relies on
hand-written writing habits. As an extra check done after sealing, we removed IRIS-lite:
$\epsilon^*$ stays at 0.10 on the hand-written pair and rises to 0.15 on the fitted pair, both now
set by GATEOPS. We therefore report $\epsilon^*$ as 0.10–0.15. A sensible cheater stays just below
it. Swapping 5% of requests still saves \$44 per \$1,000, and no auditor here catches that without
more false alarms than a customer would accept.

**Cheating or load balancing?** A3 at $\epsilon = 0.10$ sends 10% of traffic to a cheaper
model. A11 spreads traffic across honest providers of the correct model. The first is fraud; the
second is normal load balancing, which routers do by default. (Fig. F6) and
(Tab. confound) compare them over 200 sessions each.

> FIGURE F6 (fig_confound): Share of sessions flagged for A3 (cheating on 10% of requests) and A11 (honest load balancing), v2 hand-written pair, 200 sessions each. Top row: AUROC for telling them apart. The timing auditor flags honest load balancing far more often than cheating.

> TABLE confound caption: A3 (cheating, $\epsilon = 0.10$) vs. A11 (honest load balancing), hand-written / fitted pair. AUROC below 0.5 means honest load balancing looks *more* suspicious than cheating.

| Auditor | Flags A3 | Flags A11 | AUROC |
|---|---|---|---|
| IRIS-lite | 34% / 56% | 0% / 0% | 0.96 / 0.98 |
| OTE | 4% / 0% | 0% / 0% | 0.68 / 0.48 |
| GATEOPS | 18% / 5% | 96% / 100% | 0.03 / 0.00 |
| FUSE | 2% / 0% | 5% / 50% | 0.35 / 0.01 |

GATEOPS finds honest load balancing *more* suspicious than cheating (AUROC 0.00–0.03), and
FUSE inherits the problem: on the fitted pair it flags half of the honest load-balancing sessions
and none of the cheating ones. Timing and metadata show whether traffic is *mixed*, not
whether the model is *wrong*, and load balancing mixes traffic by design. The text-based
auditors can tell the two apart here only because our simulated second provider returns almost the
same text. A real second provider, running different software or a compressed copy, would change the
text too, and the difference would shrink.

So "model substitution" is really three different problems, and each needs different evidence:
- *Wrong model:* the model itself is different (A1, A2, A7). Text-based auditors can see it.
- *Undisclosed routing:* traffic is split, but the customer is not told (A3 vs. A11). The
  two differ only in intent, which nothing on the customer's side can measure.
- *Wrong bill:* the invoice does not match the service (A8). This needs an invoice, and
  free tiers do not issue one.
Only the first can be solved by black-box auditors. The second needs gateways to disclose their
routing, and the third needs metering the customer can verify. This reaches the same conclusion as
Cai et al. [@cai2025], who recommend secure hardware, from the opposite direction: some of what
auditors are asked to detect cannot be seen from the customer's side at all.
