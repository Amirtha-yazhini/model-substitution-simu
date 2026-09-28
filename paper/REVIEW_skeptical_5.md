# Fifth skeptical review (Reviewer 5), four-times-revised paper

*Mock review of the 6-page PDF built from commit `8124304` on branch `claude/dazzling-fermat-au2dlw`.
Written as a typical program-committee member of the COMSNETS Cyber Security and Privacy (CSP)
workshop: a networking and security researcher, not an LLM specialist, reading about ten papers in a
week. Items marked **[verified]** were checked against the PDF or the repository.*

---

## Summary

The paper builds an adversarial OpenAI-compatible gateway (SHIM) and compares five rebuilt
model-substitution detectors and one fusion method against it under sealed thresholds (ARENA). It
reports which detectors can run on 11 free endpoints, a simulated comparison in which a
probe-aware gateway beats every detector, a single-session detection floor of 10–15% cheating, a
timing detector that flags honest load balancing, a small live run on one provider, and a section of
post-hoc checks (the evasion's real-traffic cost, disguised probes, pooled audits reaching 5%).

## Recommendation

**Weak accept.** **Confidence:** 3/5 (security and measurement background; not an LLM specialist).

A timely, carefully executed and unusually honest workshop paper with a real system behind it. My
concerns are about how it reads to this audience rather than about its correctness: it is very dense,
its link to a communications-and-networks venue is left implicit, the figures are hard to read in
print, and a practitioner finishes it without knowing what to do. All are fixable in the text.

---

## Strengths

1. **A real problem with money attached**, stated clearly in the first paragraph.
2. **A reusable artifact:** a drop-in adversarial gateway is something other researchers can point
   their detectors at, which is the kind of contribution workshops exist for.
3. **Methodological discipline** rarely seen at workshop level: sealed thresholds, fresh seeds, an
   explicit post-hoc section, and results reported even when they went against the authors.
4. **Real measurements** that stand on their own: detector coverage on live endpoints, the 18% real
   speed gap, fingerprint rotation, latency drift.

---

## Major weaknesses

### M1. The paper is too dense for its audience.
Section 6 packs about 25 separate numbers into four paragraphs (sessions, costs, ε values, flag
rates, calibration sizes). Section 5 is similar. A reader outside the LLM-auditing niche cannot hold
the thread, and the key conclusions are buried inside sentences with three qualifications each. A
small table summarising Section 6 (check | result | caveat), and one sentence per paragraph that
states the takeaway before the numbers, would help more than any additional result.

### M2. The link to this venue is implicit.
COMSNETS is a communications and networking conference, and CSP's topics include AAA and network
security. The paper is about an untrusted intermediary on the network path, a timing side channel
measured over HTTP, and a measurement study of real endpoints, but it never says so. One or two
sentences in the introduction connecting the work to network intermediaries and measurement (in
the spirit of GateScope, published at IMC) would make the fit obvious to the PC without resorting to
buzzwords.

### M3. No practical guidance.
After six pages, what should a customer who suspects their gateway actually do? The paper has the
answer spread across Sections 4–6: use text-based detectors (KBF-style) not timing; pool sessions;
calibrate at the same time as auditing; disguise probes as normal traffic from ordinary accounts;
do not trust `system_fingerprint`; demand routing disclosure. A four-line "What an auditor should do"
paragraph before the conclusion would be the most-cited part of the paper.

### M4. Figures are not legible in print. **[verified]**
At the 90% width used to fit the page limit, the axis labels and tick labels of Fig. 1 (coverage) are
roughly 5 pt, below the 8 pt minimum most IEEE venues ask for, and the AUROC values in the Fig. 2
heatmap are similarly small. Regenerate the figures at the final column width with larger fonts,
rather than scaling them down.

---

## Minor weaknesses

1. **Generality.** Every real-model result comes from one model family (gpt-oss-120b/20b) on one
   provider (Groq). The paper states this as a limitation, but the abstract speaks of "LLM APIs" in
   general.
2. **Twelve arms, fewer informative ones.** A6–A9 are caught perfectly by every detector because they
   also serve the simulated cheap model, and A2 is now declared ambiguous. The informative arms are
   A1, A3, A4, A5, A10 and A11. Saying so would make the design section shorter and the contribution
   more honest.
3. **Title.** "Who's Actually Answering?" is memorable, but the subtitle promises a stress test and the
   paper's main findings are limits. A title that states a finding (e.g. "…: Test-Shaped Evasion,
   False Alarms and Honest Routing") would tell the PC what they are about to read.
4. **Seven of thirteen references are 2025–2026 preprints.** Unavoidable in this area, but the
   related work could cite one or two older, peer-reviewed works on model fingerprinting or on
   verifiable computation to anchor the problem.
5. **FUSE.** Now called a negative result in one sentence; it still occupies a row in every table.
   Consider dropping it from the tables to save space for M1 and M3.
6. **The artifact link is a placeholder**; the PC cannot check the reproducibility claims.

---

## Questions for the authors

1. What single recommendation would you give a customer who suspects substitution today?
2. Would the main findings change for a different model family or provider?
3. Can the figures be regenerated at the final size?

---

## Triage for the authors (not part of the review)

| # | Issue | Fix | Effort | New experiment? |
|---|---|---|---|---|
| M4 | Illegible figures | Regenerate at 3.3 in width with 8 pt fonts (`scripts/15_paper.py` figure size and rcParams) | Low | No |
| M3 | No practical guidance | Four-line "What an auditor should do" paragraph; space from dropping FUSE rows or trimming Section 6 | Low | No |
| M2 | Venue link | Two sentences in the introduction (intermediary on the network path, HTTP timing side channel, endpoint measurement) | Trivial | No |
| M1 | Density | A small summary table for Section 6, takeaway-first sentences | Medium | No |
| minor 1–5 | Generality wording, informative arms, title, anchoring references, FUSE | Text edits | Low | No |
| minor 6 | Artifact link | Create the anonymous.4open.science mirror at submission | Low | No |
