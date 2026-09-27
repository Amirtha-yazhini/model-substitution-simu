# Results

> NOTE: budget 1.75 pages (~950 words of prose + Fig. F3, Fig. F4, Fig. F5 and Tab. live). This draft is ~1,000 words.
> NOTE: figures: F3 = fig_coverage, F4 = fig_evasion, F5 = fig_fpr, F7 = fig_live. If over budget, drop F5 and keep its numbers in the text.
> NOTE: all grid, FPR and power numbers are protocol v2 (hand-written mock / fitted mock) unless the text says v1.

**A. Coverage on real endpoints.** We probed 14 free-tier model endpoints on three providers; 11
returned completions. For each we recorded whether it returns `usage`, `usage.cached_tokens`,
logprobs and `system_fingerprint`, and whether it spends hidden reasoning tokens (Fig. F3).
IRIS-lite, KBF, BENCH and GATEOPS latency run on all 11 endpoints. Three auditors are limited. RUT needs logprobs, and no
endpoint returns them: coverage 0/11. GateScope's billing channel needs `cached_tokens`: 2/11. And
the one-token method *as published* runs on only 4/11. Four endpoints spend 26–36 hidden reasoning
tokens before answering, so a 16-token cap returns an empty string. Bruckner excluded 0.76% of his
census for reasoning traces [@bruckner2026]; on this fleet the share is 36%. Raising the cap to 256
tokens restores coverage to 10/11 but multiplies the cost per probe. The cheapest known auditor
became more expensive because the models changed, not because the method did.

> NOTE: caption Fig. F3: "Auditor coverage on 11 working free-tier endpoints. RUT needs logprobs (0/11); OTE with its published 16-token cap fails on reasoning models (4/11)."

**B. The sealed grid.** Each of the twelve arms was audited in 30 sessions per ladder and scored
against 500 honest holdout sessions under the v2 thresholds (Fig. F4). Full substitution (A1) is
caught by every applicable auditor with AUROC 1.00. Three results matter more.

*Probe-aware evasion beats every auditor.* Against A5 the best AUROC is 0.56 on the hand-written
ladder and 0.61 on the fitted ladder, including FUSE. Every auditor's probes are short, capped and
repeated, which is exactly what makes them cheap and exactly what A5 detects. Cheapness and
detectability are the same property: a probe that did not look like a probe would need longer
prompts, larger token budgets and fewer repeats, and so would cost more.

*Canary-awareness defeats only the benchmark auditor.* A static list of public benchmark questions
drops BENCH to AUROC 0.48 on A10, while auditors that write their own probes still reach 1.00.

*Specificity fails on genuine traffic.* A4 serves the correct weights with altered sampling
settings. OTE and FUSE flag it with AUROC 1.00, and IRIS-lite with 0.94–0.96: a shifted answer
distribution is read as a different model. GATEOPS scores benign routing (A11) at AUROC 1.00, which
Section 5 examines. Against the cache-replay arm A6, which has no real response time, GATEOPS returns
*uninformative* rather than a false pass, as the protocol requires.

> NOTE: caption Fig. F4: "AUROC of each auditor against each arm (v2, hand-written ladder). Row A5: no auditor exceeds 0.56. RUT is inapplicable throughout."

**C. False-positive rates, v1 and v2.** Under v1 (100 calibration sessions, `>=` rule), the sealed
50-session holdout gave GATEOPS a 10.0% false-positive rate [4.3, 21.4] against a 1% target, and
KBF and BENCH 4.0%. Re-measurement on 700 further honest sessions showed that GATEOPS exceeds its v1
threshold on about 5% of sessions in every block: the calibration block's 0/100 was an unlucky
draw, roughly one in 300. The `>=` rule separately turned ties into flags, doubling KBF's and
BENCH's rate from 2% to 4%. Protocol v2 fixes both (Section 3). On a 500-session holdout every
auditor's false-positive rate is at most 0.8% [0.3, 2.0] (KBF), and GATEOPS falls to 0/500 (Fig.
F5). The lesson generalises beyond this paper: a maximum over 100 honest sessions leaves a
non-trivial chance that one threshold misses its target, and only a larger calibration set, sealed
in advance, makes that chance small.

> NOTE: caption Fig. F5: "Holdout false-positive rates with Wilson 95% intervals, v1 (50 sessions) and v2 (500 sessions). Dashed line: alpha = 1%."

**D. Real recorded responses.** The census recorded 742 real responses, including one full
240-request OTE session each for `gpt-oss-120b` and `gpt-oss-20b`, two sizes of one family. Run
directly on these recordings, OTE is clean on the null (120b first half vs second half, Fisher
$p = 1.0$), separates 20b from 120b at $p = 4.5 \times 10^{-6}$, and a different family (Qwen) at
$p = 3.8 \times 10^{-8}$. The two sizes have different "random" preferences: asked for a number from
1 to 100, the 120b most often answers 73 and the 20b 42. Two findings cut the other way. IRIS-lite's
surface features cannot separate 20b from 120b on real text (cross-validated accuracy 0.46,
$p = 0.96$), although they separate a different family ($p = 2.1 \times 10^{-7}$). And Groq returned
50 distinct `system_fingerprint` values in 239 honest requests to the 120b, so a new fingerprint is
routine, not evidence.

**E. Live run.** Latency cannot be replayed, so we placed five SHIM servers in front of Groq: an
honest reference (REF), A0, A1, A3 at $\epsilon = 0.10$, and A9 (Tab. live). Each received 96
requests (8 OTE cells × 12 repeats), interleaved in a fresh random order each round so that load
drift could not appear as an arm difference, and timed at the client. Decision rules were hashed
before the first request. All 480 requests succeeded in 25 minutes at no cost.

| Server | Swapped | Median s | CV | KS vs REF (p) | OTE p |
|---|---|---|---|---|---|
| REF | 0/96 | 0.656 | 0.57 | – | – |
| A0 | 0/96 | 0.695 | 0.70 | 0.18 (0.099) | 0.65 |
| A1 | 96/96 | 0.538 | 0.79 | **0.50** ($2.9 \times 10^{-11}$) | 0.10 |
| A3 | 14/96 | 0.650 | 0.61 | 0.08 (0.90) | 0.84 |
| A9 | 96/96 | 0.870 | 0.99 | **0.43** ($3.1 \times 10^{-8}$) | 0.028 |

> NOTE: caption Tab. live: "Live run on Groq, 96 requests per server. Bold: flagged at p < 0.01. Advertised gpt-oss-120b, substitute gpt-oss-20b."

The honest A0 is clean on both calibration-free tests. The real speed gap is 18%, not the threefold
gap the hand-written mock assumed, yet the latency side channel still catches full substitution
(KS 0.50). OTE misses it at 12 repeats per cell ($p = 0.10$), although 30 repeats caught the same
swap in the census: depth per cell matters. A3 with 14 of 96 requests swapped passes both tests.
A9 pads responses toward the 0.9 s mean reported by GateScope [@lin2026gatescope], but Groq answers
in 0.66 s, so the padding made the substitute slower and noisier than the real model and it was
caught (KS 0.43). An evasion tuned to a published baseline rather than the live one incriminates
itself. Benign routing could not run live: no second free provider serves `gpt-oss-120b`.
