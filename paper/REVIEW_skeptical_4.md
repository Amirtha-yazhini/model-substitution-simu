# Fourth skeptical review (Reviewer 4), thrice-revised paper

*Mock review of the restructured 6-page PDF on branch `claude/dazzling-fermat-au2dlw`. Written as
a fourth reviewer: someone who reads for conceptual consistency, submission readiness and whether
each headline is a property of the problem or of the setup. Items marked **[verified]** were checked
against the repository's code, config or PDF; they are not guesses.*

---

## Summary

The paper builds an adversarial OpenAI-compatible gateway (SHIM) with twelve cheating strategies and a
ground-truth log, and compares five rebuilt model-substitution auditors plus an e-value fusion under
sealed thresholds (ARENA). Sealed findings: two auditors cannot run on most free endpoints; a gateway
that answers honestly on test-shaped requests beats every auditor; single-session audits cannot catch
cheating below 10–15%; timing auditors flag honest load balancing. A separate, clearly labelled
section of post-hoc checks prices the evasion on real traffic, tests disguised probes, and shows that
pooling sessions lowers the floor to 7% for auditors that stay quiet on honest traffic.

## Recommendation

**Weak accept.** **Confidence:** 4/5.

The restructure worked: sealed and post-hoc results are now separated, and the claims are
proportionate. The remaining problems are one inconsistency in ground truth that affects the main
comparison, one headline number that is limited by the amount of simulated data rather than by
auditing, a conceptual muddle in the three-way taxonomy, and several submission-readiness issues,
including one that breaks double-blind review. None needs new experiments except, optionally, M2.

---

## Strengths

1. The sealed/post-hoc separation is now a model of how to report follow-up analyses honestly.
2. The pooled analysis across every arm, with specificity and robustness conditions, is thorough and
   genuinely changes how the economics should be read.
3. The measured real-world facts (coverage, 18% speed gap, fingerprint rotation, latency drift,
   A5's cost on WildChat) are useful regardless of the simulator.
4. Clear writing for a technically dense topic.

---

## Major weaknesses

### M1. A2 and A11 use the same honest provider but opposite ground truth. **[verified]**
A2 ("same model name, different provider") sends *every* request to the simulator's second provider
of the correct model, `alternate-70b`; A11 ("honest load balancing") sends *some* requests to that same
provider. A2 is labelled cheating and A11 honest (`config/arms.yaml`; the config itself calls A2's
label "genuinely ambiguous"). The paper's table lists A2 as cheating without explanation. The result
is that the same behaviour is scored in opposite directions: GATEOPS flagging A2 (AUROC 1.00) counts as
a success in Fig. 4, while GATEOPS flagging A11 counts as the paper's central specificity failure; and
OTE, IRIS-lite, KBF and BENCH scoring ≈0.5 on A2 count as misses. Either justify A2's label (for
example, that a different provider at lower precision breaks the customer's expectation, while A11's
mixing does not) in the paper, or mark A2 as ambiguous and exclude it from success/failure counts.

### M2. The pooled floor of 7% is limited by the data, not by auditing. **[verified]**
The pooled test draws suspect sessions without replacement from the 200 simulated sessions per
cheating rate, so k is capped at 128. KBF, the only pooled auditor that passes the specificity and
robustness checks, catches ε = 0.05 on only 18–23% of audits at k = 64–128, still rising. With more
sessions it would plausibly reach 80% at 0.05 or below, for well under a dollar. The abstract's "lowers
the floor only to 7%" reads as a property of auditing; it is a property of k ≤ 128. State the cap in
the abstract ("to 7% within 128 sessions"), or generate more sessions to find where KBF's floor
actually is. A related point: with only 300 honest calibration sessions, the pooled test cannot
detect a shift smaller than the calibration set can resolve, whatever k is; the paper should say so.

### M3. The three-way taxonomy mixes two different questions.
"Wrong model / undisclosed routing / wrong bill" puts A3 under undisclosed routing, but A3 serves a
cheaper *model* on 10% of requests: it is a partial wrong-model violation, and the post-hoc section
shows text auditors (KBF, IRIS-lite) catch it while staying quiet on A11. What A11 raises is a
different question: is honest routing across providers acceptable without disclosure? That is a policy
question, not a detection problem. The paper then concludes "Only the first can be solved by black-box
auditors", which its own pooled results contradict for A3. Restate as: (a) wrong model, fully or
partly (A1, A3, A7), detectable by text given enough sessions; (b) honest routing, which should not be
flagged, and which timing cannot tell apart from (a); (c) wrong bill, which needs an invoice.

### M4. Double-blind breach. **[verified]**
Section 6 opens: "These checks were designed after the sealed results were known, to answer reviewers'
questions." A first-round submission has no reviewers; this sentence tells the PC the paper was
reviewed before (e.g., a resubmission), which double-blind venues ask authors not to reveal. Rephrase
as "to test the robustness of the sealed findings".

---

## Minor weaknesses

1. **Abstract length. [verified]** 189 words against a 150-word budget.
2. **Live timing is optimistic. [verified]** The five SHIM servers ran on `127.0.0.1`, on the same
   machine as the client (`scripts/11_live.py`), so the client-to-gateway network path, which a real
   customer always has, is absent. Timing auditors will be noisier in practice. One sentence in the
   live section.
3. **Post-hoc settings are unexplained.** The pooled test uses k ≤ 128, 300 calibration sessions and
   a Welch t-test; the disguise uses 30 invented wrappers; WildChat uses one of fourteen shards. None of
   these choices is justified in the paper, and each was chosen after the fact. A short sentence per
   check ("chosen because…") would help.
4. **FUSE is barely a contribution now.** It is beaten by A5, flags A4, flags honest routing, and the
   dependence-safe variant has no power at 10%. Either say plainly that it is a negative result or drop
   it from the contributions.
5. **"Response time is a side channel the customer can always measure"** (threat model). It can be
   measured, but through the gateway's own network and queueing noise; see minor 2.
6. **Ethics.** WildChat contains real user conversations (ODC-BY; the dataset includes toxic content),
   and the live test ran through Groq's free tier via a proxy. A one-line ethics statement (aggregate
   statistics only; no content reproduced; free-tier terms respected) is expected at a security venue.
7. **Floating sentence.** "A threshold set from 100 honest sessions can easily miss its target" ends
   the v1/v2 paragraph without connecting to anything.
8. **Section 4 intro** lists "Sections 4.2–4.3, 5 and 6 use the simulator" but Section 6 also uses
   real data (WildChat, Azure, the live drift). Say "most of Section 6".

---

## Questions for the authors

1. What justifies labelling A2 as cheating and A11 as honest, when both serve the same honest provider
   of the correct model?
2. Where does KBF's pooled floor lie if more than 200 sessions per cheating rate are simulated?
3. Would the live timing results hold with a real network path between client and gateway?
4. Is FUSE still a contribution, and if so, of what?

---

## Triage for the authors (not part of the review)

| # | Issue | Fix | Effort | New experiment? |
|---|---|---|---|---|
| M4 | Double-blind breach | Rephrase one sentence | Trivial | No |
| minor 1 | Abstract 189 words | Cut to ~150 | Low | No |
| M1 | A2 vs A11 ground truth | One sentence justifying A2's label, or mark A2 ambiguous in the table and text | Low | No |
| M3 | Taxonomy | Rewrite the three bullets and the sentence after them | Low | No |
| M2 | Pooled floor capped by k ≤ 128 | State the cap (text), or simulate more A3 sessions at ε = 0.03–0.07 for KBF (~1,000 sessions, ~5 min) | Low / Medium | Optional, simulator only |
| minor 2, 5 | Local gateway, timing claim | One sentence each | Trivial | No |
| minor 3, 4, 6, 7, 8 | Post-hoc choices, FUSE, ethics, floating sentence, section scope | Short text edits | Low | No |
