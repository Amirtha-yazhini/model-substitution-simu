# Cost of Cheating vs. Cost of Catching It

> NOTE: budget 1.0 page. Synced from sections/*.tex after the plain-language rewrite; edit here and send back.

**Break-even.** If the gateway swaps a share $\epsilon$ of requests, it saves
$\$1{,}000 \cdot \epsilon \cdot (1 - r)$ for every \$1,000 the customer spends, where $r$ is the
price of the cheaper model relative to the genuine one: 0.115 for the Llama pair that prices our
simulator, 0.50 for the real gpt-oss pair. We compare this with the cost of running enough audit
sessions to catch the cheating 80% of the time, using measured token counts and public prices
(Fig. F2).

> FIGURE F2 (fig_break_even): What the cheater saves per \$1,000 per month (top line) vs. what an audit costs to catch it 80% of the time, by share of requests swapped (v2, hand-written pair). Audits judge each session alone; hollow markers would cause too many false alarms. In the shaded region no such audit works (Section [posthoc] pools sessions).

*Cost is never the problem.* One audit session costs \$0.0013 (KBF) to \$0.014 (FUSE);
wherever an auditor reaches 80%, the total is under ten cents, against savings of tens of dollars.

*False alarms limit repeated audits.* Running more sessions catches more
cheating, but if each session is judged on its own it also raises more false alarms. If one honest session is wrongly flagged with probability $f$, then $k$ sessions
produce at least one false alarm with probability $1 - (1-f)^k$. Our fixed rules allow at most a
5% chance of any false alarm per audit, which limits each auditor to 6–15 sessions. Below
$\epsilon = 0.10$, a single session almost never catches anything: at $\epsilon = 0.07$ the best
auditor catches 6% of sessions on the hand-written pair and 1% on the fitted pair, so 15 sessions
are not enough to reach 80%. The lowest cheating rate any acceptable audit can catch is therefore
$\epsilon^* = 0.10$ on both simulated pairs, with a bootstrap 95% interval of [0.10, 0.10] (on a grid that steps 0.07, 0.10, 0.15).
IRIS-lite reaches it with 2–4 sessions for \$0.003–\$0.006. The price ratio does not move
$\epsilon^*$, because audit cost is far below the saving at either ratio.

One caveat changes $\epsilon^*$. IRIS-lite sets it on both pairs, but on real recordings
it cannot tell the two models apart (Section [real]); in the simulator it relies on
hand-written writing habits. As an extra check done after sealing, we removed IRIS-lite:
$\epsilon^*$ stays at 0.10 on the hand-written pair and rises to 0.15 on the fitted pair, both now
set by GATEOPS. We therefore report $\epsilon^*$ as 0.10–0.15 for audits that judge each session alone. Swapping
5% of requests still saves \$25–\$44 per \$1,000 undetected; Section [posthoc] pools sessions.

**Cheating or load balancing?** A3 at $\epsilon = 0.10$ sends 10% of traffic to a cheaper
model. A11 spreads traffic across honest providers of the correct model. (Fig. F6) compares them over 200 sessions each.

> FIGURE F6 (fig_confound): Share of sessions flagged for A3 (cheating on 10% of requests) and A11 (honest load balancing), v2 hand-written pair, 200 sessions each. Top row: AUROC for telling them apart.

GATEOPS finds honest load balancing *more* suspicious than cheating (AUROC 0.03; 0.00 on the
fitted pair, where it flags 100% of load-balancing and 5% of cheating sessions), and
FUSE inherits the problem: on the fitted pair it flags half of the honest load-balancing sessions
and none of the cheating ones. Section [posthoc] shows how much of this depends on the second provider's timing,
which we had to invent. Timing and metadata show whether traffic is *mixed*, not
whether the model is *wrong*, and load balancing mixes traffic by design. Text-based
auditors separate them here only because our simulated second provider returns the same text.

So "model substitution" mixes three questions that need different evidence:
- *Wrong model:* the model is cheaper on all requests (A1, A7) or some of them (A3). Text
  can reveal it, given enough sessions (Section [posthoc]).
- *Honest routing:* traffic is split across honest providers of the right model (A11). This
  should not be flagged, and timing cannot tell it from a wrong model; whether it must be disclosed
  is a policy question, not a detection problem.
- *Wrong bill:* the invoice does not match the service (A8). This needs an invoice, and free
  tiers do not issue one.
Black-box auditing can address only the first, and only with text. Honest routing needs a disclosure
rule, and a wrong bill needs metering the customer can verify. This reaches the conclusion of Cai
et al. [@cai2025], who recommend secure hardware, from the opposite direction: some of what
auditors are asked to detect cannot be seen from the customer's side at all.
