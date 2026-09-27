# Economics and the Routing Confound

> NOTE: budget 1.0 page (~500 words of prose + Fig. F2 and Fig. F6). This draft is ~620 words.
> NOTE: eps* is stated as a range (0.10–0.15) because of the post-hoc IRIS-lite check in paper_numbers.md §9. Keep that honest.

**Break-even.** At dilution rate $\epsilon$ the gateway saves $\$1{,}000 \cdot \epsilon \cdot (1 - r)$
per \$1,000 of billed traffic, where $r = 0.115$ is the price ratio of substitute to genuine model.
Against this we set the imputed cost of enough audit sessions to reach 80% detection power, using
measured token counts and public list prices. Both curves are shown in Fig. F2.

Cost is never the obstacle. One audit session costs between \$0.0013 (KBF) and \$0.014 (FUSE), and
wherever an auditor reaches 80% power the total is below one cent, against savings of tens of
dollars. On price alone, auditing always pays.

False positives are the obstacle. Repeating a session raises power, but it raises false alarms too:
with per-session false-positive rate $f$, $k$ sessions raise at least one false alarm with
probability $1 - (1-f)^k$. The protocol seals a family budget of 5%, which caps each auditor at 6 to
15 sessions. Below $\epsilon = 0.10$ per-session power collapses: at $\epsilon = 0.07$ the best
auditor detects 6% of sessions on the hand-written ladder and 1% on the fitted one, so no admissible
number of repeats reaches 80%. The smallest dilution an admissible audit detects is therefore
$\epsilon^* = 0.10$ on both ladders, with a bootstrap 95% interval of [0.10, 0.10]. IRIS-lite gets
there with 34% power per session and 4 sessions (hand-written ladder) or 56% and 2 sessions
(fitted ladder), for \$0.003–\$0.006.

One caveat changes the number. IRIS-lite sets $\epsilon^*$ on both ladders, but on real recordings
its features cannot separate 20b from 120b (Section 4D); its mock signal comes from hand-written
surface habits. Removing it after the seal, as a post-hoc and unsealed check, leaves
$\epsilon^* = 0.10$ on the hand-written ladder and moves it to $0.15$ on the fitted ladder, both set
by GATEOPS. We therefore claim $\epsilon^* \in [0.10, 0.15]$. A rational gateway sets $\epsilon$ just
below it. At $\epsilon = 0.05$ it still saves \$44 per \$1,000, and no auditor here detects it within
a false-alarm budget a customer would accept.

> NOTE: caption Fig. F2: "Break-even. Adversary saving per $1,000 of traffic vs. imputed cost of an audit reaching 80% power, by dilution rate. No admissible audit exists left of eps* (shaded)."

**The confound.** A3 at $\epsilon = 0.10$ sends 10% of traffic to a cheaper model. A11 spreads
traffic across honest providers of the correct model. The first is fraud; the second is ordinary
load balancing, and routers do it by default. Fig. F6 compares them over 200 sessions each.

| Auditor | Flags A3 | Flags A11 | AUROC |
|---|---|---|---|
| IRIS-lite | 34% / 56% | 0% / 0% | 0.96 / 0.98 |
| OTE | 4% / 0% | 0% / 0% | 0.68 / 0.48 |
| GATEOPS | 18% / 5% | 96% / 100% | 0.03 / 0.00 |
| FUSE | 2% / 0% | 5% / 50% | 0.35 / 0.01 |

> NOTE: caption Tab. confound: "A3 (eps = 0.10, fraud) vs A11 (benign routing). Hand-written / fitted ladder. AUROC below 0.5 means benign routing scores as more suspicious than fraud." If space is short, drop the table and keep Fig. F6.

GATEOPS finds benign routing *more* anomalous than fraud (AUROC 0.00–0.03), and FUSE inherits this:
on the fitted ladder it flags half of all honest routing sessions and no fraud sessions. Timing and
metadata measure whether traffic is *heterogeneous*, not whether the model is *wrong*, and honest
routing is maximally heterogeneous. The text auditors separate the two arms only because our
simulated alternate provider returns near-identical text. A real alternate provider running a
different engine or quantisation would shift the text too, and the gap would narrow.

This suggests that "model substitution" merges three violations that need different evidence:

- **Identity:** the weights are wrong (A1, A2, A7). Content signals can observe this.
- **Disclosure:** routing happens but is not disclosed (A3 vs A11). The two differ only in intent,
  which no client-side measurement observes.
- **Billing:** the invoice does not match the service (A8). This needs an invoice, and free tiers
  issue none.

Only the first is a detection problem for black-box auditors. The second needs a disclosure
obligation on the gateway, and the third needs verifiable metering. This reaches the recommendation
of hardware attestation in [@cai2025] from the opposite direction: part of what auditors are asked to
detect is not observable from the client at all.

> NOTE: caption Fig. F6: "Score distributions for A3 (fraud) and A11 (benign routing) per auditor. Timing-based scores rank benign routing above fraud."
