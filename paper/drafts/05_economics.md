# Cost of Cheating vs. Cost of Catching It

> NOTE: budget 1.0 page. Synced from sections/*.tex after the plain-language rewrite; edit here and send back.

**Break-even.** If the gateway swaps a share $\epsilon$ of requests, it saves
$\$1{,}000 \cdot \epsilon \cdot (1 - r)$ for every \$1,000 the customer spends, where $r$ is the
price of the cheaper model relative to the genuine one: 0.115 for the Llama pair that prices our
simulator, 0.50 for the real gpt-oss pair. We compare this with the cost of running enough audit
sessions to catch the cheating 80% of the time, using measured token counts and public prices
(Fig. F2).

> FIGURE F2 (fig_break_even): What the cheater saves per \$1,000 per month (top line) vs. what an audit costs to catch it 80% of the time, by share of requests swapped (v2, hand-written pair). Hollow markers would cause too many false alarms. In the shaded region no acceptable audit works.

*Cost is never the problem.* One audit session costs \$0.0013 (KBF) to \$0.014 (FUSE);
wherever an auditor reaches 80%, the total is under ten cents, against savings of tens of dollars.

*False alarms limit repeated single-session audits.* Running more sessions catches more
cheating, but if each session is judged on its own it also raises more false alarms. If one honest session is wrongly flagged with probability $f$, then $k$ sessions
produce at least one false alarm with probability $1 - (1-f)^k$. Our fixed rules allow at most a
5% chance of any false alarm per audit, which limits each auditor to 6–15 sessions. Below
$\epsilon = 0.10$, a single session almost never catches anything: at $\epsilon = 0.07$ the best
auditor catches 6% of sessions on the hand-written pair and 1% on the fitted pair, so 15 sessions
are not enough to reach 80%. The lowest cheating rate any acceptable audit can catch is therefore
$\epsilon^* = 0.10$ on both simulated pairs, with a bootstrap 95% interval of [0.10, 0.10] (on a grid that steps 0.07, 0.10, 0.15).
IRIS-lite reaches it, catching 34% of single sessions and needing 4 sessions (hand-written pair), or
56% and 2 sessions (fitted pair), for \$0.003–\$0.006. The price ratio does not move $\epsilon^*$,
because audit cost is far below the saving at either ratio.

*Sensitivity.* Varying our choices after sealing, a power target of
50–90% and a false-alarm budget of 1–10% give $\epsilon^*$ between 0.07 and 0.15 (up to 0.25 without IRIS-lite at a 1% budget). Only removing the
false-alarm cap altogether pushes it lower, to 0.02, and then only through 107–161 repeated sessions
in which the winning auditor flags cheating sessions (1.0–1.5%) barely more often than honest ones
(0.4%); an honest customer running that audit would face a 35–48% chance of a false alarm. This is
the sense in which false alarms, not cost, set the floor *for audits that judge each session
alone*.

*Pooling sessions removes most of the floor.* An auditor can instead fix $k$ in advance and run
one test on all $k$ sessions: a one-sided Welch $t$-test of their mean score against the 300 honest
calibration sessions, at the same 5% budget. Checked on random splits of our 800 honest sessions,
its false-alarm rate stays at or below 5% for every auditor up to $k = 128$. With it, GATEOPS
catches $\epsilon = 0.02$ in 32 sessions for \$0.09 on the hand-written pair, and $\epsilon = 0.03$
in 128 sessions for \$0.36 on the fitted pair (where BENCH needs \$0.32). In simulation, then, the
floor is set by how evidence is combined, and cost is again not the limit.

One caveat changes this number. IRIS-lite sets $\epsilon^*$ on both pairs, but on real recordings
it cannot tell the two models apart (Section [real]); in the simulator it relies on
hand-written writing habits. As an extra check done after sealing, we removed IRIS-lite:
$\epsilon^*$ stays at 0.10 on the hand-written pair and rises to 0.15 on the fitted pair, both now
set by GATEOPS. We therefore report $\epsilon^*$ as 0.10–0.15 for single-session audits and 0.02–0.03 for pooled
ones. Swapping 5% of requests saves \$25–\$44 per \$1,000; a pooled audit catches that for under
\$0.40, while a single-session audit cannot.

**Cheating or load balancing?** A3 at $\epsilon = 0.10$ sends 10% of traffic to a cheaper
model. A11 spreads traffic across honest providers of the correct model. The first is fraud; the
second is normal load balancing, which routers do by default. (Fig. F6) compares
them over 200 sessions each.

> FIGURE F6 (fig_confound): Share of sessions flagged for A3 (cheating on 10% of requests) and A11 (honest load balancing), v2 hand-written pair, 200 sessions each. Top row: AUROC for telling them apart. The timing auditor flags honest load balancing far more often than cheating.

GATEOPS finds honest load balancing *more* suspicious than cheating (AUROC 0.03; 0.00 on the
fitted pair, where it flags 100% of load-balancing and 5% of cheating sessions), and
FUSE inherits the problem: on the fitted pair it flags half of the honest load-balancing sessions
and none of the cheating ones. The dependence-safe average of FUSE's e-values does not fix this: it
still flags 44% of honest load-balancing sessions on the fitted pair, and no cheating session at
$\epsilon = 0.10$ on either pair. The honest second provider's timing is invented, since none could
be measured, and it drives this result: set 18% faster than the genuine model (the measured gap
between the two real models), GATEOPS still flags 74–100% of load-balancing sessions; set
identical, it flags none. Timing and metadata show whether traffic is *mixed*, not
whether the model is *wrong*, and load balancing mixes traffic by design. The text-based
auditors can tell the two apart here only because our simulated second provider returns almost the
same text. A real second provider, running different software or a compressed copy, would change the
text too, and the difference would shrink.

So "model substitution" is really three different problems, and each needs different evidence:
- *Wrong model:* the model itself is different (A1, A2, A7). Text-based auditors can see it.
- *Undisclosed routing:* traffic is split, but the customer is not told (A3 vs. A11).
  Timing cannot separate the two; text can only while every honest provider returns the same text.
- *Wrong bill:* the invoice does not match the service (A8). This needs an invoice, and
  free tiers do not issue one.
Only the first can be solved by black-box auditors. The second needs gateways to disclose their
routing, and the third needs metering the customer can verify. This reaches the same conclusion as
Cai et al. [@cai2025], who recommend secure hardware, from the opposite direction: some of what
auditors are asked to detect cannot be seen from the customer's side at all.
