# Second skeptical review (Reviewer 2), revised paper

*Mock review of the revised 6-page PDF on branch `claude/dazzling-fermat-au2dlw`, written as a
different reviewer from `REVIEW_skeptical.md`: someone who works on measurement and statistical
testing and reads the artifact. Items marked **[verified]** were checked against the repository;
they are not guesses.*

---

## Summary

The paper presents SHIM, an OpenAI-compatible gateway with twelve cheating strategies and a hidden
ground-truth log, and ARENA, which runs simplified rebuilds of five published model-substitution
detectors plus an e-value fusion under pre-sealed thresholds. It reports coverage on 11 free
endpoints, a sealed simulated comparison, a live run on one provider, and a break-even analysis
concluding that false alarms, not cost, prevent detection below about 10% substitution. The revision
adds post-hoc checks: A5's cost on real chat traffic, disguised probes that defeat A5 in simulation,
sensitivity of the dilution floor, and a dependence-safe FUSE.

## Recommendation

**Weak accept for a workshop, conditional on the major points.** **Confidence:** 4/5.

The revision is much more careful than a typical workshop paper, and the added experiments answer
the obvious "is A5 rational?" objection. My concerns are now less about honesty than about three
conclusions that depend on design choices the paper does not examine: the any-flag repetition rule
behind ε\*, an invented latency parameter behind the load-balancing confound, and a simulator that
makes the disguised-probe result true by construction. There are also a few factual slips
introduced by the revision.

---

## Strengths

1. Pre-registration is taken seriously: sealed hashes, fresh seed blocks for v2, and a clear
   separation between sealed results and exploratory ones in the limitations.
2. The WildChat replay (172,418 requests) is a cheap, convincing way to price the evasion; I have not
   seen this done for probe-aware attacks.
3. The coverage result and the live A9 result remain the most solid, real-world contributions.
4. The FUSE revision (dependence-safe mean) is the right fix, and reporting that it does not remove
   the confound is honest.

---

## Major weaknesses

### M1. ε\* is a property of the "repeat and flag if any session flags" rule, not of auditing.
The break-even analysis lets an auditor run k independent sessions and raises an alarm if **any**
one flags, capping k so that 1 − (1 − f)^k ≤ 5%. That is the least efficient way to spend queries:
each session is tested on its own 495 requests, and evidence is never pooled. A test on the pooled
k × 495 requests (e.g., OTE on 300 repeats per cell instead of 30), or a sequential e-value test
across sessions (the paper's own FUSE machinery was built for exactly this), keeps the false-alarm
rate at α while power grows with total sample size. For a mixture at rate ε, divergence-based tests
need roughly 1/ε² samples, so lower dilution becomes a question of budget, and the audit is cheap.
The paper's headline, "false alarms, not cost, set the floor", is therefore a statement about its
chosen decision rule. The new "no cap" sensitivity row (ε\* = 0.02 with 107–161 sessions) does not
address this; it only shows that repeating a weak per-session test is bad. **Pooling or sequential
testing across sessions must be evaluated, or the claim must be narrowed.**

### M2. The load-balancing confound rests on an invented latency parameter. **[verified]**
In both simulated pairs, the honest second provider behind A11 (`alternate-70b`) has **hand-written**
timing: 0.85 s mean and 0.45 CV against the genuine model's 1.10 s and 0.30 (`shim/mock.py`). The
"fitted" pair borrows the genuine model's fitted latency and rescales it by these same hand-written
ratios, because no second provider of gpt-oss-120b was measurable (`scripts/12_fit_mock.py`). So
the honest second provider is, by construction, *more* different in timing from the genuine model
than the real 20b substitute is from the real 120b (the live gap is 18%). GATEOPS flagging A11 at
96–100% (AUROC 0.00–0.03) is then a consequence of that parameter choice. The qualitative point
(timing measures heterogeneity) is plausible, but the numbers, and the FUSE-flags-50% result that
follows from them, should be presented as illustrative, with a sweep over the alternate provider's
latency gap.

### M3. The disguised-probe result is true by construction in this simulator. **[verified]**
The mock models choose an answer from keywords in the prompt ("100", "coin") and reply with a bare
token (`shim/mock.py`), whatever the surrounding request says. So a disguised probe, from the
simulator's point of view, is the same probe, and A5 facing it degenerates into A1 (always
substitute), which every auditor catches. The paper says this, but the abstract and conclusion still
present "disguising tests restores detection" as a finding. Two real-world problems are not tested:
(a) a real model asked "pick a number" inside a story request replies with prose, so answer
extraction may fail or bias the distribution; (b) context changes the answer distribution itself
(IRIS reports only 0.50–0.75 cross-framing transfer accuracy). The one real test that would settle
this, disguised OTE on gpt-oss-120b vs 20b on Groq, costs a few hundred free requests.

### M4. The WildChat replay does not represent API traffic.
WildChat is consumer chat through a free web chatbot: no `max_tokens`, long conversational prompts.
The paper's own threat model is a gateway selling API access, where traffic includes classification
and extraction pipelines, agents and RAG, which commonly send short, templated, repeated prompts
with small `max_tokens`. A5 would serve much of that honestly, so its real cost could be far higher
than 0.6%. The claim "on 172k real chat requests this evasion gives up under 1% of the cheater's
saving" is accurate as stated, but the conclusion "gives up almost nothing on real traffic"
generalises beyond it. Either add an API-like trace or restrict the claim to chat traffic.

### M5. The live run's sealed rules fired on honest traffic, and the paper no longer says so. **[verified]**
`results/tables/live.md` shows that for the honest A0 server, **both** pre-registered sealed rules
fired: the GATEOPS sealed threshold (KS 0.177 ≥ 0.100) and the novel-fingerprint rule (7 new values).
The report discussed this; the paper now says "The honest A0 passes both tests", referring only to
the calibration-free p < 0.01 tests. For a paper whose main selling point is pre-registration,
omitting that the pre-registered live rules produced false alarms is the kind of selective reporting
it criticises in others. One sentence fixes it.

---

## Minor weaknesses and errors

1. **Cost claims contradict the data. [verified]** Section 5: "Wherever an auditor can reach 80%, the
   total is under one cent." Admissible 80%-power audits cost up to **\$0.083** (FUSE at ε = 0.15,
   hand-written pair) and \$0.069 (fitted pair); GATEOPS at ε\* costs \$0.025. The conclusion's "a
   session costs well under a cent" is false for FUSE (\$0.014) and for a disguised session
   (\$0.0139). "Under ten cents" is correct.
2. **Garbled sentence.** Section 5 opens: "where r = 0.115 is the price of the cheaper model relative
   to the genuine one: 0.115 for the Llama pair … 0.50 for the real gpt-oss pair."
3. **Inconsistent ε\* ranges.** Abstract "about 10%", Section 5 "0.10–0.15", sensitivity "0.07–0.15
   (up to 0.25)", conclusion "10–15%". Pick one statement and use it everywhere. The bootstrap
   interval [0.10, 0.10] is still reported as if it were informative; on a grid with steps of 0.03–0.05
   it only says the grid is coarse.
4. **Unit mismatch. [verified]** "The one-token paper had to drop 0.76% of its census for this
   reason; here it is 36%." The 0.76% is a share of *responses* (2,486 of 326,047); the 36% is a share
   of *endpoints* (4 of 11). Compare like with like (the one-token paper reports 14 affected
   model–provider combinations).
5. **"Honest load balancing … which no earlier evaluation does."** KBF reports "without rejecting any
   same-model controls" across deployments, which is a false-alarm test on honest cross-deployment
   traffic. Narrow the novelty claim to "routing that mixes providers within one session".
6. **Taxonomy contradicts the paper's own data.** "A3 vs A11 … differ only in intent, which nothing on
   the customer's side can measure." A3 serves a different model on 10% of requests; IRIS-lite
   separates A3 from A11 at AUROC 0.96–0.98 in the paper's own simulation, and IRIS estimates ε from
   text. The defensible claim is that *timing* cannot separate them, and that text can only when the
   honest providers serve identical weights.
7. **"Beats every auditor as published."** On the fitted pair FUSE reaches AUROC 0.61 with a bootstrap
   interval [0.51, 0.70] that excludes 0.5: weak but non-zero detection. Say "no auditor exceeds
   0.61".
8. **A9 generalisation.** "Hiding by copying fixed numbers instead of the real service gives the
   cheater away" generalises from one arm's parameter choice. An A9 that shapes to live measurements
   of the genuine model is the obvious next attack and is not tested.
9. **Sealed vs exploratory in the abstract.** The abstract mixes sealed findings with post-hoc ones
   (WildChat, disguised probes) without marking which is which; the limitations do, but most readers
   stop at the abstract.
10. **Single-session real evidence** for the recorded-response result remains; the permutation
    p-values are fine, but the "73 vs 42" anecdote is from one session per model.

---

## Questions for the authors

1. What is ε\* if an auditor pools k sessions into one test, or accumulates e-values across sessions,
   at the same 5% false-alarm budget?
2. How do the confound results change if the honest second provider's latency gap is set to the
   measured 20b/120b gap, or swept from 0 to the hand-written value?
3. Would disguised OTE still separate gpt-oss-120b from 20b on real endpoints? What fraction of
   disguised replies yields an extractable answer?
4. What share of an API-style trace (short templated prompts with `max_tokens`) does A5 classify as a
   probe?
5. Why does the paper omit that the sealed GATEOPS and fingerprint rules fired on the honest live
   server?

---

## Triage for the authors (not part of the review)

| # | Issue | Fix | Effort | New experiment? |
|---|---|---|---|---|
| minor 1, 2 | Wrong cost claims; garbled sentence | Edit text ("under ten cents") | Trivial | No |
| M5 | Live sealed rules fired on A0 | One sentence in the live section | Trivial | No |
| minor 3, 4, 5, 6, 7, 9 | ε\* range, unit mismatch, novelty, taxonomy, "every auditor", sealed-vs-exploratory marking | Text edits | Low | No |
| M1 | Any-flag rule behind ε\* | Add a pooled-session variant to the sensitivity script (re-run OTE on concatenated sessions, or sum e-values across sessions); report ε\* under it | Medium | Simulator only |
| M2 | Invented alternate-provider latency | Sweep the alternate's latency gap in the confound (re-run A11 sessions with 3–4 settings) | Medium | Simulator only |
| M4 | WildChat is not API traffic | Restrict the claim to chat traffic, or add an API-like trace if one is public | Low / Medium | Optional |
| M3 | Disguise true by construction | Narrow the abstract; the decisive fix is a small live run on Groq | Low (text) / Medium (live) | Live run needs a Groq key |
| minor 8, 10 | A9 generalisation; single session | Soften the wording | Trivial | No |
