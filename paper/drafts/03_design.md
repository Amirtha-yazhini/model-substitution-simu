# System Design

> NOTE: budget 1.0 page (~450 words of prose + the arms table + the auditors table). This draft is ~560 words of prose.
> NOTE: if over budget, merge the auditors table into prose (one line each) first.

The testbed has two parts: SHIM, a gateway that cheats in controlled ways, and ARENA, which runs
auditors against it under a sealed protocol.

**SHIM.** SHIM is an HTTP server that implements the OpenAI chat-completions API, including the
`usage` block and `system_fingerprint`. An auditor points its base URL at SHIM and cannot
distinguish it from a provider except by behaviour. Each request passes through one of twelve
*adversary arms* (Tab. arms), which decide which backend answers and how the response is
rewritten. Randomised arms seed on a hash of the request body, never on wall-clock time, so every
run replays exactly. For every request SHIM appends a ledger line recording the arm, the backend
that really answered, latency, reported and true token usage, and imputed cost from public price
tables. No auditor can read the ledger. It is the ground truth from which every ROC curve and
false-positive rate in this paper is computed, which no audit of a real gateway can do.

| Arm | Gateway behaviour | Truth |
|---|---|---|
| A0 | Honest | genuine |
| A1 | Always serves the substitute | subst. |
| A2 | Same model name, other provider | subst. |
| A3 | Substitute on a fraction $\epsilon$ of requests | subst. |
| A4 | Right model, altered sampling settings | genuine |
| **A5** | Honest only on audit-shaped requests | subst. |
| A6 | Replays cached answers to repeated prompts | subst. |
| **A7** | Substitute answers, second pass restyles | subst. |
| A8 | Inflates reported token usage | subst. |
| A9 | Adds delay to mimic the genuine latency | subst. |
| **A10** | Honest on public benchmark questions | subst. |
| **A11** | Splits traffic across honest providers of $M$ | genuine |

> NOTE: caption for Tab. arms: "Adversary arms. Bold arms appear in no prior evaluation. A4 and A11 are genuine and test specificity."

Three arms deserve detail. **A5** (probe-aware evasion) routes a request to the genuine model when
it *looks like an audit*: at most 24 `max_tokens`, a prompt under 220 characters, a prompt seen
before, or a closed-answer phrase such as "reply with only". It needs no knowledge of any
particular probe set, only of the shape that cheap probes share. **A10** keeps a static list of
public benchmark questions and answers those honestly. **A11** is not an attack: it spreads traffic
across legitimate providers of the correct model, as commercial routers do by default
[@openrouter_exacto], and is scored as a false-positive test.

Backends are either a *replay corpus* of real responses, recorded once from free-tier endpoints and
committed so that every auditor sees byte-identical data, or a *mock* whose model personalities
(answer preferences, surface habits, accuracy, latency) can be sampled in unlimited sessions. We use
two mock ladders: one hand-written, and one whose answer distributions and latency are fitted to the
recorded census and the live run (Section 4).

**ARENA.** Six auditors implement one interface that returns a score, a p-value and an
`applicable` flag (Tab. auditors). Five are reimplementations labelled *-lite*, since none is the
authors' code. FUSE is new: it converts each applicable auditor's calibrated p-value to an e-value,
multiplies them, and flags when the product exceeds $1/\alpha$, which by Ville's inequality
controls the Type-I error at any stopping time [@vovk2021evalues; @ville1939].

| Auditor | Source | Signal |
|---|---|---|
| OTE | [@bruckner2026] | JSD of single-answer distributions, 8 cells |
| IRIS-lite | [@iris2026] | 16 surface-string features, random forest |
| GATEOPS | [@lin2026gatescope] | latency KS test, fingerprint, billing |
| KBF | [@fang2026kbf] | agreement on 15 knowledge-boundary facts |
| BENCH | [@cai2025] | accuracy on 12 MMLU/GPQA/GSM8K items |
| RUT | [@zhu2025rut] | token-rank uniformity (needs logprobs) |
| FUSE | new | product of e-values, flag at $E > 1/\alpha$ |

**Sealed protocol.** A session is one audit of 495 queries. Each threshold is the largest score
seen over $N$ honest (A0) calibration sessions, which bounds the marginal false-positive rate by
$1/(N+1)$; a session is flagged when its score *strictly* exceeds the threshold. With $\alpha = 0.01$
and $N = 300$, the realised false-positive rate exceeds $\alpha$ with probability at most
$0.99^{300} = 4.9\%$. The thresholds and all decision rules are written to one file, hashed with
SHA-256, committed and tagged before any evaluation runs, and every evaluation script refuses to run
if the hash has changed. An auditor that cannot run on an endpoint, or on a response without the
field it needs, returns *uninformative*, never *consistent*. Our first seal (v1, $N = 100$) used a
`>=` rule; we report its results as sealed and correct the rule in a second seal (v2) rather than
editing v1.
