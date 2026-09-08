# SHIM — Who's Actually Answering?

**A zero-cost adversarial-gateway simulator and auditor benchmark for LLM model substitution.**

> Portfolio framing: *"Eight papers propose ways to detect when an LLM API lies about which model
> it serves. None of them were evaluated against each other. I built the benchmark that compares
> them, ran it for $0, and found that the strongest attack is one no paper tests — and that
> legitimate routing is indistinguishable from fraud."*

**Constraints this design is built around:** total spend **$0**, **no local model inference**,
laptop-only compute. The primary deliverable is a repository and a written report that demonstrate
research comprehension, not an arXiv submission.

---

## 1. The pitch

Since April 2025, eight papers have proposed methods to verify that an LLM API serves the model it
advertises. Every one was evaluated on its own testbed, against its own adversary, with thresholds
tuned on the data it reports. There is no shared benchmark and no shared threat model — and a 2026
holdout study showed a published token-count fingerprint going from **perfect separation
(balanced accuracy 1.00) on its 12 development pairs to only 50% of its 12 holdout pairs even
having enough valid data to score, and 50% sensitivity (2 of 4 same-family pairs missed) on the
ones that did**. Meanwhile the ecosystem moved underneath the literature:
OpenRouter's *Auto Exacto* performs quality-based provider routing **on by default**, which is
operationally identical to the "routing dilution" attack these papers were written to detect.

**SHIM** is an OpenAI-compatible gateway that misbehaves on command across a 12-arm adversary
taxonomy, backed by real responses from free-tier LLM endpoints. **ARENA** runs auditors
reimplemented from five papers against it under a pre-registered frozen-threshold protocol.
Because SHIM knows the true backend of every request, ARENA can compute real ROC curves — which no
real-world audit can, since real audits have no ground truth. Everything after a one-time response
census replays from disk, so the full grid re-runs in seconds at zero cost, on any laptop, with no
API key.

---

## 2. The competitive landscape (and why the obvious project is dead)

This table is itself a deliverable: it is the evidence that the literature was read properly.

| Work | Signal | Testbed | What it leaves open |
|---|---|---|---|
| **Cai, Shi, Zhao, Song 2025** ([2504.04715](https://arxiv.org/abs/2504.04715)) | Benchmarks (MMLU/Math/GPQA/GSM8k), text tests, log-probs | Formalization + eval | Concludes software-only auditing is *unreliable*; recommends TEEs. That pessimism has never been tested under a common benchmark. |
| **RUT** ([2506.06975](https://arxiv.org/abs/2506.06975)) | Rank-based uniformity of API tokens under a reference model | Quantization, harmful FT, jailbreak, full swap | **Requires a locally deployed authentic reference.** Its applicability across the real endpoint fleet was never measured. |
| **GateScope** ([2604.21083](https://arxiv.org/abs/2604.21083), IMC'26) | 4 dims: content (XGBoost, F1 0.968), 25-turn memory, billing residual, latency CV | 24 models x 10 commercial gateways | Operational signals never fused with behavioral fingerprints. Cannot attribute cause. |
| **KBF** ([2605.29524](https://arxiv.org/abs/2605.29524)) | Numeric recall at the knowledge boundary | 16 endpoints; 155 substitutions flagged, 0 FP; catches 5–10% dilution | Probe set is conspicuous and cacheable — never tested against an evasive gateway. |
| **Bruckner, "One Token Is Enough"** ([2607.10252](https://arxiv.org/abs/2607.10252)) | Single-token distributions, 40 cells (10 tasks x 4 langs), mean JSD | 165 models, **$34.44**, AUC 0.971, EER 7.3% | Cheapest known signal. Assumes a passive gateway. Ablations: 8 cells → EER 10.6%; 1 cell → 23.3%. |
| **IRIS** ([2607.20860](https://arxiv.org/html/2607.20860v1)) | 179 visible-string features + RF posterior, budgeted sequential plan | Qwen3 ladder + **17–45 OpenRouter models** | **The paper that scoops the naive project.** Already does OpenRouter + dilution + budget. But: its own probes, its own features, its own axes, no evasive adversary. |
| **DiFR** ([2511.20621](https://arxiv.org/pdf/2511.20621)) | Logits, verification despite nondeterminism | In-the-wild Llama 3.1 8B provider audit | Needs raw logits — almost never exposed. |
| **Frozen-threshold holdout study** ([2608.29930](https://arxiv.org/html/2608.29930)) | `usage.prompt_tokens` shift-invariant match, methodological critique | 24 pairs (12 dev / 12 holdout), 4,320 calls | Dev: perfect separation, BA 1.00. Holdout: only 6/12 pairs scoreable (rate limits/missing fields), and of those, BA 0.75, sensitivity 0.50 (2 of 4 same-family pairs missed), specificity 1.00. Cause: dev pairs shared a "same tokenization stack," holdout same-family pairs didn't. The field's evaluations do not replicate. |

**Do not write "we combined five papers."** IRIS already did the combination-plus-OpenRouter
version. Write the benchmark all eight should have been evaluated on, and use it for results none
of them could produce.

---

## 3. How the constraints shape the design (and why they help)

| Constraint | Consequence | Why it turns out to be an advantage |
|---|---|---|
| **$0 budget** | No paid endpoints. Census runs on free tiers; the binding resource is **requests/day, not dollars**. | Forces the *collect-once-replay-forever* architecture, which is what makes the auditor comparison genuinely controlled — all methods see byte-identical data. No prior paper achieves this. |
| **No local inference** | RUT cannot use a locally deployed reference, as its paper specifies. | Becomes a **measurement**: RUT's real-world applicability is exactly the coverage question nobody has quantified. A method you cannot deploy is a finding, not a gap in the project. |
| **Laptop only** | numpy / scikit-learn / scipy. No GPU, no training. | Everything a reader needs to reproduce runs in seconds. Reproducibility is a selling point rather than a caveat. |
| **Recruiter audience** | The artifact is a repo + report, not a submission. | Removes the 30-day responsible-disclosure clock and the pressure to rush a thin paper into a crowded subfield. |

### The free-tier resource map

Verified September 2026; **limits change often, so measure them empirically at runtime.**

| Provider | Limit | Free models | OpenAI-compatible | Role in this project |
|---|---|---|---|---|
| **Cerebras** | ~1M tokens/day, 30 RPM | Llama 3.3 70B, others | Yes | **Primary workhorse.** With `max_tokens=16` probes, 1M tokens/day is effectively unlimited requests. |
| **Groq** | 1,000 RPD, 30 RPM | Llama 3.3 70B, Mixtral | Yes | **Second workhorse.** Fast; good for latency-signal collection. |
| **Mistral** | ~1B tokens/month, 2 RPM | All Mistral models | Yes | **First-party reference** for Mistral models. Slow RPM — run overnight. Requires opting into training. |
| **Google AI Studio** | 5–15 RPM, 20–1,500 RPD | Gemini + Gemma variants | Partial | **First-party reference** for Gemma. |
| **GitHub Models** | 10 RPM, 50 RPD high-tier / 150 RPD mini | 100+ incl. GPT-4o, Claude, Llama, Phi | Yes | Widest model variety; low quota. Use for breadth, not depth. |
| **OpenRouter** | 20 RPM, **50 RPD** (zero-credit account) | 28+ `:free` slugs | Yes | **Quota-starved — use sparingly.** Reserve for models unavailable elsewhere and for the Auto Exacto arm. |
| **Cloudflare Workers AI** | ~10k neurons/day | 20+ | Partial | Overflow capacity. |
| **NVIDIA NIM** | ~1,000 RPD | Nemotron, Llama | Partial | Overflow capacity. |

Realistic aggregate: **~3,000–5,000 requests/day at $0.** No credit card anywhere.

### The reference-model trick

RUT and KBF need a trusted reference. With no local inference, use **first-party free endpoints as
ground truth and third-party re-hosts as suspects**:

- Mistral models → Mistral's own API is the reference; Groq / OpenRouter / GitHub re-hosts are suspects.
- Gemma → Google AI Studio is the reference.
- Llama 3.3 70B → no first-party endpoint, so use **cross-provider consensus** across Groq,
  Cerebras, OpenRouter and NVIDIA as a soft reference, and report it as such.

This yields real ground truth for $0, and the "no first-party reference exists for open-weight
models" problem is itself worth stating plainly in the writeup.

---

## 4. The three contributions

### C1 — SHIM: an adversary anyone can point an auditor at

An OpenAI-compatible reverse proxy (`POST /v1/chat/completions`) serving real free-tier responses,
where the true backend and every wire-level manipulation are under experimental control.

| Arm | Name | Behavior |
|---|---|---|
| A0 | Honest | Serve the advertised model. Control arm; source of null calibration. |
| A1 | Full substitution | Always serve a cheaper sibling (Llama 70B → 8B). |
| A2 | Quantization swap | Same slug, different provider at lower precision. |
| A3 | eps-dilution | Serve substitute on fraction eps in {0.02, 0.05, 0.10, 0.25, 0.50}. |
| A4 | Sampler retune | Genuine weights, altered temperature / top-p. |
| A5 | **Probe-aware evasion** | Classify inbound requests; route short / low-entropy / repeated prompts to the genuine model. Directly targets KBF and one-token probes. |
| A6 | Cache replay | Serve a cached completion for repeated prompts. Defeats repetition-based distribution estimation. |
| A7 | **Laundering** | Cheap model generates; a second cheap pass restyles output to match the target's formatting. Targets IRIS-style string features. |
| A8 | Billing manipulation | Inflate reported `usage`; misreport `cached_tokens`. |
| A9 | Latency shaping | Inject jitter to mask backend heterogeneity from GateScope's CV metric. |
| A10 | Canary-aware | Route verbatim public-benchmark prompts (MMLU/GPQA) to the genuine model. Defeats benchmark-based detection. |
| A11 | **Benign quality routing** | Route among *genuine* providers of the correct model, Auto-Exacto style. **Not fraud.** |

**A5, A7 and A10 are attacks no published paper evaluates.** Every prior threat model assumes a
passive gateway that substitutes uniformly and never inspects the request stream. A real adversary
would look at what it is being asked.

**A11 is the scientific pivot.** See §5.

### C2 — ARENA: five reimplemented auditors, one frozen protocol

All auditors sit behind one interface:

```python
class AuditResult(NamedTuple):
    decision: Literal["consistent", "inconsistent", "uninformative"]
    score: float        # calibrated; higher = more suspicious
    e_value: float      # for anytime-valid sequential stopping
    queries: int
    cost_usd: float     # imputed from published price tables
    applicable: bool    # False -> "uninformative", NEVER a pass
```

That `applicable` flag encodes the frozen-threshold paper's central lesson in the type system:
**a method that cannot run must not be scored as though it passed.**

Auditors: `OTE` (Bruckner), `IRIS-lite`, `GATEOPS` (GateScope minus billing, which is
inapplicable to free tiers — itself a coverage result), `KBF`, `BENCH` (Cai et al.),
`RUT` (coverage-limited by design), and `FUSE` (ours).

Evaluated under the frozen-threshold protocol from
[2608.29930](https://arxiv.org/html/2608.29930): arms split into dev/holdout **before** data
collection, thresholds calibrated on dev only and **SHA-256-sealed and git-tagged before the
holdout is touched**, validity gates enforced, missing data counted as uninformative.

Metrics the literature does not report: **dollars-to-detection** (imputed from public price tables,
so measurable at zero spend), **applicability coverage** across the real endpoint fleet, and
**break-even dilution eps\***.

### C3 — Two results nobody has

**(a) The audit-economics frontier.** An adversary diluting at rate `eps` on spend `S` saves
`eps * S * (1 - c_sub/c_adv)`. IRIS establishes detection needs `m(eps) = Theta(1/eps)` queries in
the favorable regime and `Theta(1/eps^2)` in the hard one. So **audit cost grows as the theft
shrinks, while savings shrink only linearly** — there exists a break-even `eps*` below which
auditing is economically irrational for every known method, and a rational adversary simply lives
below it. This requires no spend to compute: token counts are measured, prices come from public
tables. It is the headline finding and the most quotable line in the writeup.

**(b) FUSE — behavioral x operational fusion.** Every prior auditor uses a single channel.
GateScope reads latency CV, `system_fingerprint` churn and cached-token ratios but has no
distributional fingerprint; Bruckner / RUT / KBF have distributions but ignore the wire. FUSE
calibrates each channel to a p-value on the A0 null, converts to e-values, and multiplies them
into a test martingale, stopping when `E > 1/alpha` — anytime-valid by Ville's inequality, with no
fixed sample size. **Hypothesis:** FUSE dominates on dollars-to-detection and is the only method
surviving A5/A7, because text is far cheaper to launder than latency and metadata simultaneously.

---

## 5. The idea that makes this research rather than plumbing

**Legitimate routing and fraudulent substitution have the same observable signature.**

Auto Exacto re-evaluates providers every ~5 minutes on throughput, tool-call telemetry and
benchmark scores, and is on by default for tool-calling requests. Failover, load balancing and
capacity routing do the same. All of them produce precisely what the literature calls an attack: a
fraction of requests served by a different backend, with different latency, formatting and
distributional fingerprint.

So A11 routes among *genuine* providers of the *correct* model, and every auditor is scored on it
as a **false-positive arm**. Expectation: all of them flag it. That yields a taxonomy the
literature conflates:

- **Identity violation** — the weights are not the advertised weights. (A1, A2, A7)
- **Disclosure violation** — the routing is real but undisclosed. (A3 and A11 differ *only in intent*.)
- **Billing violation** — the invoice does not match the service. (A8)

Only the third is separable from pure observation. The uncomfortable conclusion: **client-side
auditing is trying to recover a ground truth that is not observable from the client side** — which
is independent support for Cai et al.'s TEE recommendation, reached from the opposite direction.

---

## 6. Optional second study: is the free tier the same model?

A genuinely novel, entirely free research question that no paper has touched. GateScope audited
commercial gateways, KBF audited reseller APIs, IRIS audited paid OpenRouter. **Nobody has audited
the free tier** — and it is exactly where you would expect a quantized or smaller variant to hide,
since the cheapest way to subsidize free access is to serve something cheaper.

Design: for each model with a first-party free endpoint, treat that as reference and audit every
third-party re-host. For Llama-family models, use cross-provider consensus. Report agreement
matrices and applicability coverage.

Either outcome is publishable-quality: evidence of inconsistency is a finding, and *no* evidence
plus an honest statistical-power analysis is a more mature finding than most portfolio projects
contain. **Anonymize providers** (GateScope used `a*yi`, `b*ie`) and claim *inconsistency with a
reference*, never *fraud* — a provider can differ for many innocent reasons.

---

## 7. Deliverables, in priority order

1. **`README.md`** — runs in 30 seconds, no API key, committed replay corpus. Most recruiters
   never get past this file; it must carry the whole story with the headline figure inline.
2. **`shim/`** — the adversarial gateway. The component most likely to be independently reused.
3. **`arena/`** — auditor implementations + frozen-threshold runner.
4. **`REPORT.md` / blog post** — 2,000 words, leading with the economics figure.
5. **`corpus/` + `results/`** — full audit trail of every API call.
6. *(Stretch)* arXiv preprint — only if the results are strong and there is appetite weeks later.

---

## 8. What each piece signals to a technical reader

| Component | Signal |
|---|---|
| §2 landscape table, incl. IRIS | Read the literature properly, and identified the paper that scoops the naive idea rather than hoping nobody notices. |
| Frozen-threshold pre-registration + git tag | Understands why ML results fail to replicate, and gave up the ability to tune. Rare in portfolio work. |
| `applicable` flag / coverage metric | Understands that unmeasurable is not the same as negative — the exact error the 2026 holdout study documents. |
| A5 / A7 / A10 arms | Can extend a threat model rather than only reimplement one. |
| Collect-once-replay-forever | Systems judgment under a hard resource constraint. |
| e-values / anytime-valid stopping | Comfortable with modern sequential statistics, not just t-tests. |
| Multi-provider quota-aware async orchestration | Real engineering, not notebook code. |
| §5 confound + honest negative results | Research taste. The strongest signal in the whole project. |

---

## 9. Risk register

| Risk | Severity | Mitigation |
|---|---|---|
| Free-tier rate limits stall the census | **High** | Cerebras + Groq are the workhorses; run the 8-cell Bruckner operating point (240 req/model, EER 10.6% in the original ablation) rather than the full 40-cell battery; census resumes from a manifest. |
| Free endpoints churn or vanish mid-project | Medium | Commit the replay corpus. Once collected, results are permanent and reproducible regardless of endpoint availability. |
| IRIS overlaps more than its abstract suggests | Medium | Position as benchmark + economics + fusion + evasive adversary. Cite IRIS as the strongest baseline, reimplement it as `IRIS-lite`. Never claim a first OpenRouter audit. |
| Reimplementations are unfaithful | Medium | Label every auditor `-lite`; publish a deltas-from-original table; report results as lower bounds on the original methods. |
| Weak or null holdout results | Medium | **A null result is the finding** — it replicates 2608.29930 across five methods instead of one. Do not tune your way out of it; that is the whole point of sealing the thresholds. |
| Naming free providers | Medium | Anonymize; claim inconsistency, never fraud. §6. |

---

## 10. References

- Cai, Shi, Zhao, Song. *Are You Getting What You Pay For? Auditing Model Substitution in LLM APIs.* [arXiv:2504.04715](https://arxiv.org/abs/2504.04715)
- Zhu et al. *Auditing Black-Box LLM APIs with a Rank-Based Uniformity Test.* [arXiv:2506.06975](https://arxiv.org/abs/2506.06975)
- Lin et al. *Behavioral Consistency and Transparency Analysis on LLM API Gateways* (GateScope, IMC'26). [arXiv:2604.21083](https://arxiv.org/abs/2604.21083)
- Fang et al. *KBF: Knowledge Boundary as Fingerprint.* [arXiv:2605.29524](https://arxiv.org/abs/2605.29524)
- Bruckner. *One Token Is Enough.* [arXiv:2607.10252](https://arxiv.org/abs/2607.10252)
- *IRIS: Budgeted Black-Box Auditing of Model Substitution and Routing Dilution in LLM Gateways.* [arXiv:2607.20860](https://arxiv.org/html/2607.20860v1)
- *DiFR: Inference Verification Despite Nondeterminism.* [arXiv:2511.20621](https://arxiv.org/pdf/2511.20621)
- *Token Counts Are Not Model Lineage: A Frozen-Threshold Holdout Study.* [arXiv:2608.29930](https://arxiv.org/html/2608.29930)
- *Stemma: Induced Decision Regions Reveal LLM Provenance.* [arXiv:2607.25880](https://arxiv.org/html/2607.25880v1)
- *Black-Box Inference of LLM Architectural Properties with Restrictive API Access.* [arXiv:2607.01313](https://arxiv.org/pdf/2607.01313)
- Thinking Machines Lab. *Defeating Nondeterminism in LLM Inference.* https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/
- OpenRouter. *Auto Exacto: Adaptive Quality Routing, On by Default.* https://openrouter.ai/blog/announcements/auto-exacto/
- OpenRouter. *Free LLM APIs in 2026: 13 Options Compared.* https://openrouter.ai/blog/tutorials/free-llm-apis-compared/
