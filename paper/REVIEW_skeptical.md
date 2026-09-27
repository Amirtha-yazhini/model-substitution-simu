# Skeptical review: "Who's Actually Answering? Stress-Testing LLM Model-Substitution Auditors Against an Adversarial Gateway"

*Mock review written in the style of a COMSNETS CSP workshop reviewer, against the 6-page PDF on branch
`claude/dazzling-fermat-au2dlw`. Items marked **[verified]** were checked
against the repository's code or config; they are not guesses.*

---

## Summary

The paper builds SHIM, an OpenAI-compatible gateway with twelve cheating strategies ("arms") and a
hidden ground-truth log, and ARENA, which runs simplified rebuilds of five published
model-substitution detectors plus a new e-value fusion (FUSE) against it under thresholds sealed by
SHA-256. It reports: (1) two detectors cannot run on most of 11 free-tier endpoints; (2) an arm that
answers honestly on "test-shaped" requests (A5) defeats all detectors; (3) a break-even analysis in
which false-alarm budgets, not cost, prevent detecting dilution below about 10–15%; (4) timing-based
detectors flag honest load balancing more than fraud, motivating a three-way taxonomy.

## Recommendation

**Weak reject** (would move to weak accept with the major points addressed).
**Confidence:** 4/5 (familiar with LLM fingerprinting and sequential testing).

The problem is timely, the pre-registration discipline is genuinely good, and the limitations are
stated more honestly than usual. But the headline results are, on inspection, largely properties
of the authors' own simulator and their own attacker design rather than measurements of the
published methods, and the paper does not make that distinction prominent enough.

---

## Strengths

1. **Sealed thresholds with a hash and a tag**, and a v1 → v2 story that reports the failed v1
   rather than quietly replacing it. Rare and welcome.
2. **"Uninformative, never pass"** is a clean, useful rule that the field should adopt.
3. **The coverage measurement** (RUT 0/11, OTE-as-published 4/11 because of hidden reasoning
   tokens) is real, cheap to reproduce, and actionable for method authors.
4. **The live A9 result** (latency shaping toward a fixed target makes the substitute *slower* and
   gets caught) is a nice, concrete, counter-intuitive observation.
5. **The A3-vs-A11 confound** asks the right question: detectors that measure heterogeneity will
   flag legitimate routers.

---

## Major weaknesses

### M1. The A5 result is close to circular.
A5 is designed by the same authors who built the probes, using thresholds (`max_tokens ≤ 24`,
prompt ≤ 220 characters, repeated prompt, "reply with only") that are exactly the shape of the
authors' own rebuilt probes. Beating them is therefore expected by construction. Three things are
missing:
- **Countermeasures.** IRIS already shows that disguised probes (paraphrased, embedded in
  realistic-looking requests) keep their fingerprint. The paper never runs a single disguised
  probe, so "A5 beats every auditor" really means "A5 beats undisguised probes".
- **The attacker's cost.** A5 serves the *genuine* model for every short request. If a meaningful
  share of real production traffic is short (classification, extraction, chat turns), A5 gives up
  much of its saving. The paper never estimates what A5 actually saves, so we cannot tell whether
  it is a rational attack or a free lunch.
- **False routing.** A5's classifier is never scored on realistic non-probe traffic.
The Limitations section admits "A5 is our own design" but the abstract and conclusion state the
result without that qualifier.

### M2. The quantitative headline results come from a simulator, and one of them from invented features.
The grid, the false-alarm rates, ε\*, the break-even curve and the confound all run on the mock
backend. The "fitted" pair fits only answer distributions and latency; surface habits and accuracy
are hand-written. The paper's own post-hoc check shows IRIS-lite sets ε\* on both pairs but
**cannot separate the two real models** on recorded text (accuracy 0.46, p = 0.96). So the headline
"no audit works below ~10%" is set by a detector whose signal in the simulator is invented. Several
other cells look like simulator artefacts: every auditor, including the benchmark one, scores
**AUROC 1.00** on A1, A6, A7, A8 and A9 (GATEOPS is inapplicable on A6). BENCH catching latency shaping or billing inflation
perfectly is not plausible on real models; it happens because those arms also serve the simulated
substitute, whose hand-written accuracy is far lower. The abstract should say "in simulation" next
to every number that comes from the simulator.

### M3. The price ratio does not match the models studied. **[verified]**
The 11.5% price ratio that drives every dollar figure (the \$88 saving, 8.8% of the bill, the whole
break-even figure) comes from `config/prices.yaml` entries for **Llama 3.3 70B vs Llama 3.1 8B at
Cerebras prices** (`mock:genuine-70b` / `mock:substitute-8b`). The real and fitted experiments use
**gpt-oss-120b vs gpt-oss-20b**, which have no price entry at all. The paper never says which
models the ratio comes from. Either justify the ratio for gpt-oss or present the economics as a
function of the ratio, with a sensitivity plot.

### M4. FUSE's validity guarantee rests on an unstated independence assumption. **[verified]**
The paper says FUSE multiplies per-auditor e-values and that Ville's inequality then bounds the
false-alarm rate "however long the audit runs". A product of e-values is only an e-value when the
factors are independent (or built sequentially, each conditional on the past). Here the auditors
are computed from the *same session's* responses and timing, so their p-values are dependent. The
code (`arena/auditors/fuse.py`) acknowledges this assumption and computes an averaged e-value that
is valid under arbitrary dependence, but the paper mentions neither. The empirical 0/500 holdout
rate does not rescue this: it is a single-configuration check, not a guarantee. In addition, FUSE is
the paper's only new method and it does not win anywhere: it is beaten by A5, flags genuine A4
traffic with AUROC 1.00, and flags 50% of honest routing sessions on the fitted pair. A reader
will ask why it is a contribution.

### M5. The break-even analysis depends on four unexamined choices.
ε\* follows from: an 80% power target, a 5% family false-alarm budget, a \$1,000/month account,
and the 11.5% price ratio (M3). None is justified or varied. With a 10% budget, or a customer who
audits once per month for a year, the admissible number of sessions changes and so does ε\*. The
bootstrap interval [0.10, 0.10] only reflects resampling of sessions on a coarse grid of ε values
(0.07, 0.10, 0.15); it says nothing about sensitivity to these choices and looks falsely precise.
The analysis also assumes the auditor has free, trustworthy access to the genuine model as a
reference. In practice obtaining that reference is the hard part and it is not costed.

### M6. Real-world evidence is thin and single-provider.
Coverage: 11 endpoints, 3 providers, most on one provider (Groq), at one point in time. The
generalisation "models now think silently before answering" rests on 4 endpoints. Recorded
responses: one 240-request session per model. Live run: one provider, one session, 96 requests per
arm, and A11 could not run live at all, so the central confound is **never observed on real
traffic**. The text of Section 5 then argues from the simulated confound to a general taxonomy.

### M7. The v2 re-seal happened after seeing v1's holdout results.
The paper frames v2 as a correction, which is honest, but v2's changes (strict inequality, N = 300)
were chosen *because* v1 over-fired on the holdout. That is a mild form of tuning on the test set.
The paper should state explicitly that v2 was designed after v1's holdout was observed and that v2's
holdout is fresh data (if it is). Otherwise "sealed before any test ran" in the abstract is
misleading for v2.

---

## Minor weaknesses

1. **Novelty relative to IRIS.** IRIS already combines substitution detection, dilution estimation,
   budgets, and probe-spotting gateways. The contribution here is a common testbed and an adaptive
   attacker across methods. That is useful, but the introduction still reads as if the problem
   space is untouched.
2. **"-lite" rebuilds understate the originals.** OTE uses 8 of 40 cells, IRIS-lite 16 of 179
   features, KBF 15 items, BENCH 12 items, and GATEOPS drops the memory channel. Reporting that
   these simplified rebuilds fail says little about the published methods; the paper says "lower
   bound" but the abstract says "beats every detector".
3. **A4 as a "specificity failure" is debatable.** Changing temperature and top-p changes the
   service the customer pays for; many customers would want it flagged. Calling detection of A4 a
   false alarm is a policy choice, not a fact.
4. **AUROC without intervals.** Grid AUROCs come from 30 sessions per arm and are reported to two
   decimals without confidence intervals; 0.56 vs 0.61 on A5 is not a meaningful difference.
5. **Only the hand-written pair is plotted** in the evasion heatmap, break-even figure and confound
   figure; the fitted pair, which the paper calls the more realistic one, appears only in text.
6. **"At least eight" auditors** but the introduction cites seven.
7. **Tone.** The plain-language rewrite helps, but a few phrases ("near a coin flip", "gives the
   cheater away") read as informal for IEEE proceedings.
8. **Title.** The question form is catchy but does not say what the paper found.
9. **Security framing.** For a security workshop, the threat model lacks a clear statement of
   attacker knowledge levels (does the attacker know the auditor exists? the probe distribution?)
   and of what the customer is assumed to trust (the reference provider?).
10. **Artifact.** The anonymised link is a placeholder; the review cannot check reproducibility
    claims.

---

## Questions for the authors

1. What share of realistic production requests would A5 classify as "test-shaped", and what is
   A5's actual saving at that share?
2. Does any auditor survive A5 if its probes are disguised as ordinary requests, as IRIS proposes?
3. Where does the 11.5% price ratio come from, and what is it for gpt-oss-120b vs 20b?
4. Is the FUSE product valid when all channels are computed from the same session? What do the
   results look like with the averaged e-value?
5. How does ε\* change with a 10% false-alarm budget, a 50% power target, or a price ratio of 0.3?
6. Were v2's design choices made after observing v1's holdout? Is v2's holdout disjoint from all
   data seen before v2 was sealed?
7. Why do BENCH and KBF reach AUROC 1.00 against latency shaping (A9) and billing inflation (A8)?

---

## Triage for the authors (not part of the review)

Ordered by how much a fix changes the reviewer's score per unit of effort, given the 6-page limit
and about half a page of free space.

| # | Issue | Suggested fix | Effort | Needs new experiments? |
|---|---|---|---|---|
| M3 | Price ratio from Llama prices | One sentence stating the source, plus ε\* as a function of the ratio (a small sweep of the existing economics script over 3–4 ratios) | Low | Rerun of existing script only |
| M4 | FUSE independence | State the assumption; report the averaged e-value result the code already computes | Low | No (already computed) |
| M7 | v2 designed after v1 holdout | One sentence in Section 3 saying so, and that v2's holdout is fresh | Low | No |
| M2 | Simulator numbers in abstract | Add "in simulation" to the abstract and conclusion numbers; explain why A8/A9 are trivially caught | Low | No |
| minor 6 | "Eight" vs seven citations | Cite the eighth (holdout study or Stemma) or say "seven" | Trivial | No |
| M5 | Break-even sensitivity | One short paragraph or table varying the budget and power target | Medium | Rerun of existing script only |
| M1 | A5 circularity | Reframe as "undisguised probes"; estimate A5's cost from a public request-length distribution | Medium | Small analysis |
| M1 | Disguised probes | Run one disguised-probe OTE variant against A5 in the simulator | Higher | Yes |
| M6 | Single provider | State as scope in the abstract; nothing cheap fixes this | — | Yes (quota) |
