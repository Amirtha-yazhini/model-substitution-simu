# Results

> NOTE: budget 1.75 pages. Synced from sections/*.tex after the plain-language rewrite; edit here and send back.

We report detection quality as AUROC: the chance that a cheating session scores higher than an
honest one. 0.5 is a coin flip and 1.0 is perfect. Sections [grid]–[fpr], [econ] and [posthoc]
use the simulator; the others use real endpoints.

## Which auditors can run on real endpoints
We tested 14 free model endpoints from three providers; 11 worked. For each we checked whether it
returns token counts (`usage`), cache counts (`cached_tokens`), token probabilities
(logprobs) and a `system_fingerprint`, and whether the model "thinks" in hidden tokens
before answering (Fig. F3). IRIS-lite, KBF, BENCH and the timing part of GATEOPS run on all
11. Three do not. RUT needs token probabilities, and no endpoint provides them: 0 of 11. GateScope's
billing check needs cache counts: 2 of 11. And the one-token method, as published, works on only 4
of 11. Four endpoints spend 26–36 hidden tokens thinking before they answer, so a 16-token limit
returns an empty answer. The one-token paper met the same problem on 14 model–provider
combinations and dropped 0.76% of its responses [@bruckner2026]; here it affects 4 of 11
endpoints. Raising the limit to 256 tokens brings the method back
to 10 of 11, but each question now costs more. The cheapest known auditor became more expensive
because the models changed, not the method.

> FIGURE F3 (fig_coverage): Share of the 11 working free endpoints on which each auditor can run. RUT needs token probabilities (0/11); OTE with its published 16-token limit fails on models that think before answering (4/11).

## Main comparison
We ran 30 audit sessions against each arm on each simulated model pair, and compared their scores
with 500 honest sessions, using the fixed v2 thresholds (Fig. F4). Every auditor that can
run catches full substitution (A1) perfectly (AUROC 1.00). Three results matter more.

*Hiding from tests beats every auditor as published.* Against A5 no auditor exceeds AUROC 0.56
on the hand-written pair or 0.61 on the fitted pair, and no 95% bootstrap interval reaches above
0.70. Every
auditor's questions are short and repeated, and some contain phrases like "reply with only". That
is what makes them cheap, and exactly what A5 looks for. Section [posthoc] prices this
evasion and tests a countermeasure.

*Knowing the benchmarks beats only the benchmark auditor.* A fixed list of public benchmark
questions (A10) drops BENCH to AUROC 0.48. Auditors that write their own questions still score 1.00.

*Some honest behaviour is flagged.* A4 serves the correct model but with different sampling
settings. OTE and FUSE flag it perfectly (AUROC 1.00) and IRIS-lite nearly so (0.94–0.96): a change
in the answer pattern is mistaken for a different model. Whether a silent change of sampling settings should count as cheating is a policy choice; we
score it as honest. GATEOPS flags honest load balancing (A11) perfectly too, which
Section [econ] discusses. The perfect scores against A6–A9 say little: these arms also serve
the cheaper model, which our simulator makes very different from the genuine one. Against A6, which replays saved answers and
so has no real response time, GATEOPS correctly says *uninformative* instead of passing it.

> FIGURE F4 (fig_evasion): AUROC of each auditor (rows) against each arm (columns), v2, hand-written model pair. * marks honest arms; hatched cells mean the auditor could not run. Column A5: no auditor exceeds 0.56 (0.61 on the fitted pair).

## False alarms, v1 and v2
With the v1 rules (100 calibration sessions, flag on equal scores), GATEOPS wrongly flagged 10.0%
[4.3, 21.4] of the 50 honest test sessions, against a 1% target; KBF and BENCH flagged 4.0%. We
then ran 700 more honest sessions. GATEOPS beat its v1 threshold in about 5% of them, in every
batch: the 100 calibration sessions had simply produced an unluckily low threshold, a roughly 1 in
300 event. Separately, flagging equal scores turned ties into alarms, which doubled KBF's and
BENCH's rate from 2% to 4%. Version v2 fixes both (Section [design]). On 500 honest test
sessions, every auditor's false-alarm rate is now at most 0.8% [0.3, 2.0] (KBF), and GATEOPS drops
to 0 of 500 (Wilson 95% intervals [@wilson1927]). A threshold set from 100 honest sessions can easily miss its target.

## Real recorded responses
We recorded 742 real responses, including one full 240-request OTE session each from
`gpt-oss-120b` and `gpt-oss-20b`, a large and a small model from the same family.
Running OTE directly on these recordings gives the expected results. Comparing the first half of the
120b's answers with the second half finds no difference ($p = 1.0$). The 20b differs from the 120b
($p = 4.5 \times 10^{-6}$), and a model from another family (Qwen) differs even more
($p = 3.8 \times 10^{-8}$). The two sizes have different "favourite" numbers: asked for a number
from 1 to 100, the 120b most often says 73 and the 20b says 42. Two results point the other way.
IRIS-lite's surface features cannot tell the 20b from the 120b on real text (accuracy 0.46, $p =
0.96$), although they do separate a different family ($p = 2.1 \times 10^{-7}$). And Groq returned
50 different `system_fingerprint` values in 239 honest requests to the 120b, so a new
fingerprint is normal, not a sign of cheating.

## Live test
Response times cannot be recorded and replayed, so we ran five SHIM servers live in front of Groq:
an honest reference (REF), A0, A1, A3 cheating on 10% of requests, and A9 (Tab. live).
Each server got 96 requests (8 questions $\times$ 12 repeats). The order was shuffled every round,
so changes in Groq's load could not look like differences between arms, and times were measured on
the client. The decision rules were fingerprinted before the first request. All 480 requests
succeeded in 25 minutes, at no cost.

> TABLE live caption: Live test on Groq, 96 requests per server. Advertised model `gpt-oss-120b`, cheaper model `gpt-oss-20b`. Timing is compared with REF (KS statistic, $p$). Bold: flagged at $p < 0.01$.

| Server | Swapped | Median s | CV | Timing ($p$) | Text $p$ |
|---|---|---|---|---|---|
| REF | 0/96 | 0.656 | 0.57 | – | – |
| A0 | 0/96 | 0.695 | 0.70 | 0.18 (0.099) | 0.65 |
| A1 | 96/96 | 0.538 | 0.79 | **0.50** ($2.9\times10^{-11}$) | 0.10 |
| A3 | 14/96 | 0.650 | 0.61 | 0.08 (0.90) | 0.84 |
| A9 | 96/96 | 0.870 | 0.99 | **0.43** ($3.1\times10^{-8}$) | 0.028 |

The honest A0 passes both calibration-free tests, but two sealed rules fired on it: the GATEOPS
threshold, calibrated on simulated 240-request sessions, and the new-fingerprint rule, since Groq
rotates `system_fingerprint` on honest traffic. Neither is usable on this service. The real speed difference between the two models is 18%, not the
3$\times$ our hand-written simulator assumed, but timing still catches full substitution (A1). The
text test misses it with 12 repeats per question ($p = 0.10$), although 30 repeats caught the same
swap in the recordings: the number of repeats matters. A3, which swapped 14 of 96 requests, passes
both tests. A9 added delay to reach a fixed target (0.9 s on average, with the timing variation that
GateScope reported for an honest baseline [@lin2026gatescope]), but Groq's real model answers
in 0.66 s, so the delay made the cheap model *slower* and more
erratic than the real one, and it was caught. A cheater that shapes delay to live measurements of
the genuine service was not tested. Honest load balancing (A11) could not be tested live, because
no second free provider offers `gpt-oss-120b`.
