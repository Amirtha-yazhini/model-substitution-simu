# Third skeptical review (Reviewer 3), twice-revised paper

*Mock review of the 6-page PDF after the second round of fixes, on branch
`claude/dazzling-fermat-au2dlw`. Written as a third reviewer: a security PC member who cares about
threat-model realism and about whether the paper's claims still hang together after two rounds of
additions. Items marked **[verified]** were checked against the repository's data or code; they are
not guesses.*

---

## Summary

SHIM is an OpenAI-compatible gateway with twelve cheating strategies and a hidden ground-truth log;
ARENA runs five rebuilt model-substitution auditors and an e-value fusion under thresholds sealed in
advance. The paper reports endpoint coverage, a sealed simulated comparison, a small live run on one
provider, and an economics section. After revision, the headline is: auditing is cheap but not
robust; a gateway that spots test-shaped requests beats every auditor; single-session audits cannot
catch cheating below 10–15%, but pooling sessions catches 2–3% for under \$0.40; and timing-based
auditors flag honest load balancing.

## Recommendation

**Borderline, leaning weak reject.** **Confidence:** 4/5.

Each individual fix is reasonable, and the authors deserve credit for reporting results that went
against them. But the paper has become a sealed study wrapped in six post-hoc analyses, and the new
post-hoc headline (pooled audits catch 2–3%) is weaker than it reads: every auditor that reaches it
either flags honest routers or is beaten by a known attack. The economics figure still says the
opposite of the text. I would accept a version that re-centres the paper on what survives: coverage,
the evasion result, the specificity problem, and a clearly scoped economics section.

---

## Strengths

1. The coverage measurement and the live A9 result are solid, real, and useful to method authors.
2. Unusually honest reporting: the sealed live rules that fired on honest traffic, two invalid
   versions of the pooled test, and a headline reversal are all disclosed.
3. The A5 real-traffic replay is a good idea, and the Azure bound is a fair qualification.
4. The load-balancing confound, now with a latency sweep, is the paper's most transferable insight.

---

## Major weaknesses

### M1. The pooled "2–3%" floor comes only from auditors that fail elsewhere. **[verified]**
The pooled result is won by GATEOPS (2% hand-written, 3% fitted) and, on the fitted pair, BENCH
(3%). Applying the same pooled test to the other arms, using the committed sessions:
- **Pooled GATEOPS flags 100% of honest load-balancing (A11) sessions** on both pairs, at the same k
  that catches 2–3% dilution. It cannot be used by a customer of any router that balances load.
- **Pooled BENCH flags 0% of canary-aware (A10) sessions.** A static list of public benchmark
  questions defeats it completely.

So the audit that "catches 2–3% for under 40 cents" either flags legitimate routing or is beaten by
a known attack. The paper presents 2–3% as a floor achievable in principle without saying that no
auditor reaches it while staying specific and robust. The pooled analysis should be reported for
every arm, not only A3, and the claim restated as "pooling lowers the floor only for auditors that
fail specificity or robustness".

### M2. The hand-written "2%" rests on a latency gap the live run refuted.
Pooled GATEOPS reaches ε = 0.02 on the hand-written pair because that simulator gives the cheaper
model a threefold speed advantage. The paper's own live run measured the real gap at 18%. On the
fitted pair, which uses the measured gap, pooled GATEOPS needs 128 sessions for ε = 0.03. The
hand-written 2% should not appear in the abstract, which gives "2–3%".

### M3. The economics figure contradicts the text. **[verified]**
Fig. 2 (break-even) still plots only single-session audits, and its caption says: "In the shaded
region no acceptable audit works." Section 5 now says a pooled audit works across that entire
shaded region. A reader who looks at the figure and not the text comes away with the old,
superseded conclusion. Either add the pooled curve or rewrite the caption.

### M4. Pooling assumes the service does not change over time; real services do.
The pooled test compares the mean of k suspect sessions with a fixed set of honest calibration
sessions collected earlier. In the simulator latency is independent and identically distributed, so
this works. On a real service it is not: load, hardware and serving stacks change between the
calibration run and the audit. The live run already shows an honest-vs-honest timing difference of
KS 0.18 (p = 0.099) between two servers queried in the *same* interleaved rounds, and Groq rotated
`system_fingerprint` 41 times in 96 requests. A pooled timing test with 32–128 sessions spread over
hours or days would detect this drift as cheating. The paper needs to say that pooled timing tests
require calibration taken at the same time as the audit, which doubles the cost and needs honest
access to the genuine model throughout.

### M5. The threat model omits the cheapest evasion: by account, not by request.
A5 classifies each request. A real gateway knows which customer account each request comes from,
and an auditing customer sends hundreds of probe-shaped requests from one key. Serving the genuine
model to that *account* (or to any account that ever sends probe-like traffic) defeats every
auditor here, including disguised probes, because disguised probes still come from the auditor's
account. It costs the cheater only the auditing customers' traffic. The disguised-probe "fix" is only
meaningful if the auditor's traffic is indistinguishable from, and mixed with, real production
traffic on the same account. The paper should name account-level targeting in the threat model
and say which results survive it.

### M6. Post-hoc analyses now carry the headline.
The abstract's findings are, in order: coverage (real), A5 beats auditors (sealed, simulated), A5's
real-traffic cost (post-hoc), disguised probes (post-hoc, simulated), single-session floor (sealed,
simulated), pooled floor (post-hoc, simulated), timing confound (sealed, depends on a post-hoc
sweep). Six analyses were added after reviewers asked, each choosing its own test, k grid, settings
and wording, and the pooled test needed three attempts. That is exactly the garden of forking paths
the sealed protocol was built to avoid. The abstract marks them as post-hoc, which helps, but the
paper would be more credible if the post-hoc material were grouped in one clearly labelled section,
and the sealed findings stated first and on their own.

---

## Minor weaknesses

1. **Uncounted cost of the pooled test.** It needs 300 honest calibration sessions run against a
   trusted source of the genuine model (about \$0.85 at the paper's prices), more than the pooled
   audit itself (\$0.09–\$0.36). "Under 40 cents" should include it.
2. **"One caveat changes this number"** now follows the pooled paragraph, so "this number" reads as
   the pooled ε\*, but the caveat (IRIS-lite) applies to the single-session ε\*. Reorder.
3. **"At least eight such auditors"** counts the holdout study (a model-lineage method) and DiFR, which
   needs the provider's cooperation (a shared random seed), so it is not a black-box auditor. "Six
   black-box auditors and two related methods" is more accurate.
4. **A5 and pooling.** Pooled GATEOPS catches A5 on 74% of audits at k = 30 on the fitted pair
   **[verified]**, so "A5 beats every auditor as published" is true only for single sessions. Worth
   one clause.
5. **No description of the simulator's parameters in the paper.** A reader cannot judge the
   simulator's realism (answer biases, 3× latency gap, accuracy 0.86 vs 0.54) without the artifact,
   and the artifact link is still a placeholder.
6. **Citations.** Nine of the fourteen references are 2025–2026 arXiv preprints; that is the state of
   the field, but the related work should say which are peer-reviewed (GateScope at IMC).
7. **Figure 4 and the fitted pair.** The evasion heatmap shows the hand-written pair only; its
   caption's "no auditor exceeds 0.56" differs from the text's "0.56 / 0.61".
8. **Writing.** The contribution list now carries about ten separate claims in four bullets, several
   with nested qualifications. A workshop reader needs three crisp takeaways.

---

## Questions for the authors

1. Which auditor, if any, reaches a pooled ε below 0.10 while flagging fewer than 5% of honest
   load-balancing (A11) sessions and remaining robust to A10 and A5?
2. How would the pooled timing test behave if calibration and audit sessions were collected hours
   apart on a real provider?
3. Does any result survive a gateway that serves the genuine model to every request from an account
   once that account sends probe-shaped traffic?
4. Why keep Fig. 2's shaded "no acceptable audit" region now that the text says pooled audits work
   there?

---

## Triage for the authors (not part of the review)

| # | Issue | Fix | Effort | New experiment? |
|---|---|---|---|---|
| M3 | Figure 2 contradicts text | Add the pooled curve (data exist in `pooled_sessions.md`) or change the caption | Low | No |
| minor 2, 3, 4, 7 | Caveat order, "eight auditors", A5 vs pooling, Fig. 4 caption | Text edits | Trivial | No |
| M2 | Hand-written 2% | Quote the fitted 3% in abstract and intro | Trivial | No |
| M1 | Pooled winners fail A11/A10 | Run the pooled test on every arm (reuse `19_pooled_sessions.py` on grid/A11 sessions); restate the claim | Low | Simulator re-analysis only |
| minor 1 | Calibration cost | Add \$0.85 to pooled cost | Trivial | No |
| M5 | Account-level evasion | Add to threat model and limitations; argue which results survive | Low | No |
| M4 | Drift | Add as limitation; ideally, time-split the live data to measure drift | Low / Medium | Optional (live data exist) |
| M6 | Post-hoc sprawl | Restructure: sealed findings first, one "post-hoc checks" subsection | Medium | No |
| minor 5, 8 | Simulator parameters; contribution list | One-line parameter summary; tighten bullets to three | Low | No |
