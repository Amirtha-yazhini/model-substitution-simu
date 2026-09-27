# System Design

> NOTE: budget 1.0 page. Synced from sections/*.tex after the plain-language rewrite; edit here and send back.

The testbed has two parts: SHIM, a gateway that cheats in controlled ways, and ARENA, which runs the
auditors against it under fixed rules. The names are descriptive, not acronyms: a *shim* is a thin
software layer slipped between two components, as our gateway sits between auditor and providers,
and an *arena* is where contestants compete under the same rules.

**SHIM.** SHIM is a web server that speaks the OpenAI chat API, including the `usage`
block and `system_fingerprint`. An auditor points at SHIM instead of a real provider and has
no way to tell the difference except by how it behaves. Each request goes through one of twelve
cheating strategies, which we call *arms* (Tab. arms). The arm decides which model
answers and how the response is changed. Any randomness is seeded from the request itself, never
from the clock, so every run can be repeated exactly. For every request SHIM writes a hidden log
line: the arm, the model that really answered, the response time, the reported and true token
counts, and the cost at public prices. No auditor can read this log. Because it records the truth,
we can measure exactly how often each auditor is right or wrong, which is impossible when auditing a
real gateway.

> TABLE arms caption: The twelve arms (cheating strategies). Bold arms have never been evaluated before, or (A5) only against one auditor [@iris2026]. A4 and A11 serve the correct model and test whether auditors raise false alarms.

| Arm | What the gateway does | Cheating? |
|---|---|---|
| A0 | Honest | no |
| A1 | Always serves the cheaper model | yes |
| A2 | Same model name, different provider | yes |
| A3 | Cheaper model on a share $\epsilon$ of requests | yes |
| A4 | Right model, changed sampling settings | no |
| **A5** | Honest only on requests that look like tests | yes |
| A6 | Replays saved answers to repeated prompts | yes |
| **A7** | Cheap model answers, then a rewrite pass | yes |
| A8 | Over-reports token usage | yes |
| A9 | Adds delay to match the real model's speed | yes |
| **A10** | Honest on known benchmark questions | yes |
| **A11** | Spreads traffic over honest providers of $M$ | no |

Three arms need more explanation. **A5** (hiding from tests) sends a request to the genuine
model when it *looks like a test*: an answer limit of at most 24 tokens, a prompt under 220
characters, a prompt it has seen before, or a phrase such as "reply with only". It does not need
to know any auditor's actual questions, only the shape that cheap test questions share.
**A10** keeps a list of public benchmark questions and answers those honestly. **A11** is
not cheating: it spreads traffic across legitimate providers of the correct model, as commercial
routers do by default [@openrouter_exacto]. We use it to count false alarms.

Behind SHIM sits either a *recording* of real responses, collected once from free endpoints so
that every auditor sees exactly the same data, or a *simulator* that imitates how each model
behaves (its favourite answers, writing habits, accuracy and speed) and can produce as many sessions
as needed. We use two simulated model pairs: one with hand-written behaviour, and one whose answers
and speeds are fitted to the real recordings (Section [results]).

**ARENA.** Six auditors share one interface. Each returns a score, a p-value, and a flag saying
whether it could run at all (Tab. auditors). Five are our own rebuilds of published
methods, labelled *-lite* because they are not the authors' code. FUSE is new. It turns each
auditor's p-value into an *e-value*, a measure of evidence that can be multiplied across tests,
and raises a flag when the product passes $1/\alpha$. A classical result (Ville's inequality) then
keeps the false-alarm rate below $\alpha$ [@vovk2021evalues; @ville1939], but only if the auditors'
evidence is independent. Ours is not, since all auditors read the same session, so we also report the
*average* of the e-values, which stays valid under any dependence (Section [econ]).

> TABLE auditors caption: The six auditors: five rebuilt from published papers, one new.

| Auditor | Source | What it checks |
|---|---|---|
| OTE |  [@bruckner2026] | which short answers the model prefers |
| IRIS-lite |  [@iris2026] | 16 surface features of the text |
| GATEOPS |  [@lin2026gatescope] | response times, fingerprint, billing |
| KBF |  [@fang2026kbf] | 15 hard numeric facts |
| BENCH |  [@cai2025] | accuracy on 12 benchmark questions |
| RUT |  [@zhu2025rut] | token probabilities (needs logprobs) |
| FUSE | new | combined evidence from the others |

**Fixed rules.** One *session* is one complete audit of 495 requests. To set each
auditor's threshold we ran $N$ sessions against the honest arm A0 and took the highest score seen.
A new honest session then beats that score with probability at most $1/(N+1)$, and a session is
flagged only if its score is *strictly* higher. With a 1% target ($\alpha = 0.01$) and
$N = 300$, the chance that the true false-alarm rate still ends up above 1% is at most
$0.99^{300} = 4.9%$. All thresholds and decision rules went into one file, which we fingerprinted
with SHA-256, committed and tagged before any test ran; every test script refuses to run if the file
has changed. An auditor that cannot run, for example because an endpoint lacks a field it needs,
reports *uninformative*, never *pass*. Our first version of these rules (v1, $N = 100$)
flagged scores *equal* to the threshold. We report v1 as it was sealed and fix the rule in a
second sealed version (v2), rather than editing v1. We designed v2 after seeing v1's results, so v2
was evaluated only on fresh blocks of random seeds that no earlier run had used.
