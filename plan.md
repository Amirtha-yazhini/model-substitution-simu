# SHIM + ARENA — Execution Plan (Zero-Cost Edition)

Companion to [idea.md](idea.md).

**Goal:** a working system, real free-tier data, figures and a written report **in one day, for $0,
with no local model inference.** Audience is technical recruiters, so the repository and the report
are the products; an arXiv submission is an optional follow-on, not a deadline.

**Stack:** Python 3.11+, `httpx`, `fastapi` + `uvicorn`, `numpy`, `scipy`, `scikit-learn`,
`pandas`, `matplotlib`. No GPU, no training, no local inference. Everything runs on the laptop.

**The binding resource is requests per day, not money.** Every design decision below follows from
that. Budget the quota the way the paid version budgets dollars.

---

## Repository layout

```
model-substitution-simu/
  README.md            # the real deliverable - runs with no API key
  idea.md  plan.md  REPORT.md
  config/
    providers.yaml     # free endpoints, keys, measured rate limits, capabilities
    models.yaml        # roster: advertised model, substitute ladder, reference endpoint
    arms.yaml          # 12 adversary arms
    protocol.yaml      # dev/holdout split, seeds, thresholds  <- SEALED in Phase 4
    prices.yaml        # public price tables, for imputed cost only
  shim/
    server.py          # FastAPI OpenAI-compatible proxy
    policy.py          # adversary arms A0-A11
    backends.py        # live multi-provider client + replay-corpus client
    quota.py           # per-provider rate limiter + daily budget tracker
    ledger.py          # per-request accounting: true backend, latency, usage, imputed cost
  arena/
    base.py            # Auditor ABC -> AuditResult
    probes/            # probe suites
    auditors/          # ote.py iris_lite.py gateops.py kbf.py bench.py rut.py fuse.py
    evalue.py          # p-values, e-values, test martingales, sequential stopping
    protocol.py        # frozen-threshold runner + SHA-256 sealing
    economics.py       # break-even eps*, dollars-to-detection (imputed)
  corpus/              # COMMITTED replay corpus - this is what makes the repo runnable
  results/             # results.jsonl, figures/, tables/
  scripts/
    00_keys.py  01_limits.py  02_census.py  03_calibrate.py
    04_freeze.py  05_holdout.py  06_figures.py
```

**`corpus/` is committed to git.** That single decision is what lets a recruiter clone the repo and
reproduce every figure in 30 seconds with no API key. Keep it under ~50 MB (JSONL + gzip; the
probes are `max_tokens<=16`, so this is comfortable).

---

## Phase 0 — Free accounts and capability probing (60 min)

Longer than it sounds: six signups. Do it first, in one sitting.

1. `git init`, venv, deps, layout above.
2. **Create free accounts and collect keys.** Priority order — the first two carry the census:
   - **Cerebras** (~1M tokens/day, 30 RPM) — primary workhorse
   - **Groq** (1,000 RPD, 30 RPM) — second workhorse, also the latency-signal source
   - **Google AI Studio** (5–15 RPM, 20–1,500 RPD) — first-party reference for Gemma
   - **Mistral** (~1B tokens/month, 2 RPM) — first-party reference for Mistral models; note the
     Experiment tier requires opting into training, so use no sensitive prompts
   - **GitHub Models** (10 RPM; 50 RPD high-tier / 150 RPD mini) — breadth
   - **OpenRouter** (20 RPM, **50 RPD** at zero credits) — reserve for the Auto Exacto arm and for
     models unavailable elsewhere
   - *(optional overflow)* Cloudflare Workers AI, NVIDIA NIM
   No credit card at any of these. Keys go in `.env`; `.env` goes in `.gitignore`; never commit.
3. `scripts/01_limits.py` — **empirically measure** each provider's real RPM/RPD and capabilities
   rather than trusting documentation. For each endpoint record: does it accept `logprobs`? does it
   return `usage.cached_tokens`? does it return `system_fingerprint`? does it leak reasoning
   traces? does it honour `max_tokens=16`? Write to `config/providers.yaml`.

   **That capability table is not setup — it is Result #1**, the applicability-coverage
   measurement that no paper reports. Treat it as a deliverable from the first hour.
4. `config/models.yaml` — the roster. Choose ladders where substitution is economically plausible
   *and* both rungs exist on free tiers:
   - **Llama 3.3 70B vs Llama 3.1 8B** — both on Groq and Cerebras. The primary ladder.
   - **Mistral Large vs Mistral Small** — first-party reference available. The clean case.
   - **Gemma 27B vs Gemma 9B** — Google first-party reference.
   - **Same model across providers** — Llama 3.3 70B on Groq / Cerebras / OpenRouter / NVIDIA.
     Feeds arms A2 and A11 and the §6 free-tier study.

**Exit criteria:** every roster entry returns a completion from at least one provider; capability
matrix filled in; measured rate limits recorded.

---

## Phase 1 — SHIM core (90 min)

`shim/server.py`: FastAPI `POST /v1/chat/completions`, OpenAI-compatible request and response
schemas including `usage`. It must be a drop-in — an auditor points `base_url` at it and cannot
tell it from a real endpoint except by its behavior. That is the entire point.

`shim/quota.py`: per-provider token-bucket limiter plus a persistent daily counter. Requests that
would exceed a provider's daily quota fail over to the next provider that serves the same model,
or park in a queue. **Write this before the census** — a census that dies at request 51 because
OpenRouter's daily cap hit is the most likely way this day fails.

`shim/policy.py`: one class per arm, all implementing `route(request) -> RoutingDecision` and
`transform(response) -> response`. Build in this order; the first three unblock everything else:

- **A0 Honest** — pass through to the designated genuine provider.
- **A1 Full substitution** — rewrite the model to the cheaper sibling.
- **A3 eps-dilution** — Bernoulli(eps) per request, **seeded on a hash of the request body**, never
  on wall-clock, so replays are deterministic.
- **A2 Quantization swap** — same model, different provider.
- **A4 Sampler retune** — override temperature / top_p.
- **A6 Cache replay** — LRU keyed on the normalized request; report `cached_tokens`.
- **A8 Billing manipulation** — scale reported `usage` fields.
- **A9 Latency shaping** — `asyncio.sleep` from a configured jitter distribution.
- **A10 Canary-aware** — substring match against a bundled MMLU/GPQA prompt list → genuine model.
- **A5 Probe-aware evasion** — heuristic classifier: short prompt, small `max_tokens`, prompt seen
  before, or obviously closed answer space → genuine model. **This arm should break KBF and OTE,
  so give it real thought — it is one of the project's novel contributions, not a stub.**
- **A7 Laundering** — two-hop: cheap model generates, then a formatting-transfer pass. The most
  quota-expensive arm; implement last, run on a reduced probe set, use Cerebras' token budget.
- **A11 Benign quality routing** — round-robin among genuine providers of the *correct* model,
  reweighted every K requests. Structurally identical to A3, semantically innocent.

`shim/ledger.py`: append one `results.jsonl` line per request — arm, true backend, advertised
model, prompt hash, response hash, latency, reported usage, true usage, imputed cost from
`prices.yaml`. **This file is the ground truth for every metric and the basis of the
reproducibility claim.**

**Exit criteria:** `curl` against SHIM under A0 and A1 returns valid OpenAI-shaped JSON; ledger
lines appear; A3 at eps=0.5 shows roughly 50% substitute routing over 100 requests.

---

## Phase 2 — The census (launch by hour 3; runs all day unattended)

`scripts/02_census.py` — execute the probe suites against every roster model and write each
response to `corpus/`, content-addressed by `sha256(provider, model, probe_id, repeat_idx)`.

**Quota arithmetic drives the probe design.** Bruckner's full battery is 40 cells x 30 repeats =
1,200 requests per model — at ~3,000 requests/day total that is barely two models. So run
**Bruckner's own 8-cell operating point**, which his ablation reports at **EER 10.6%** versus 7.3%
for the full battery. 8 cells x 30 repeats = **240 requests/model**, giving ~12 models/day. This is
not a compromise to apologize for: it is a documented operating point from the original paper, and
citing it that way is the correct move.

| Suite | Source | Content | Repeats | Req/model |
|---|---|---|---|---|
| `ote` | Bruckner | **8 cells** (2 tasks x 4 languages) at the paper's reduced operating point | 30 | 240 |
| `kbf` | KBF | 20 numeric-recall items near the knowledge boundary | 5 | 100 |
| `iris` | IRIS | random numbers/strings, varied alphabet and length | 20 | 20 |
| `gateops` | GateScope | 25-turn conversation, memory checkpoints at turns 10/24/25 | 2 | 50 |
| `bench` | Cai et al. | 20 each MMLU / GPQA / GSM8K | 1 | 60 |
| `rut` | RUT | natural prompts with `logprobs=true` where supported | 10 | 10 |

~480 requests per model. Route by provider capacity: Cerebras and Groq take the bulk, Mistral runs
overnight at 2 RPM, OpenRouter's 50/day is spent only on what nothing else serves.

Concurrency respecting each provider's measured RPM, exponential backoff on 429, and
**resume-from-manifest** so an interrupted run costs nothing to restart. Log every failure —
failures are the coverage metric.

**Exit criteria:** `corpus/manifest.json` complete for at least the primary Llama ladder; a
documented list of which models refused which suites and why.

---

## Phase 3 — Auditors (2.5–3 h, overlapping the census)

All implement `arena/base.py`'s `AuditResult` (see idea.md §4 C2). The `applicable` flag is
load-bearing: **a method that cannot run returns `uninformative`, never `consistent`.**

Build in this order. The first three alone constitute a complete, defensible result if the day
runs short:

1. **`ote.py` (Bruckner)** — normalize responses (Unicode, punctuation, case, digit systems), build
   a categorical distribution per cell, score by mean Jensen–Shannon divergence against the
   reference. Cheapest and strongest baseline. **Build first.** Sanity target: clear separation on
   A0-vs-A1, in the neighbourhood of the paper's 8-cell EER.
2. **`iris_lite.py`** — visible-string features (format compliance, symbol frequency, length,
   structural patterns) → random forest → posterior over enrolled backends. Also yields attribution
   and an `eps` estimate by fitting a posterior mixture.
3. **`gateops.py` (GateScope)** — latency CV (`sigma/mu`), memory-checkpoint pass rate over 25
   turns, `system_fingerprint` distinct-value count. **The billing dimension is inapplicable on
   free tiers — there is no invoice.** Record that as coverage rather than working around it; it is
   an honest finding about where GateScope's method transfers.
4. **`kbf.py`** — reference consensus per numeric probe, domain tolerances, binomial test on the
   agreement rate.
5. **`bench.py` (Cai et al.)** — accuracy on MMLU / GPQA / GSM8K against the reference,
   two-proportion test. Expected to be quota-expensive and weak; that is a finding, and A10 is the
   arm that defeats it.
6. **`rut.py`** — rank of API-emitted tokens under the reference distribution, uniformity test.
   With no local inference the reference must be a free endpoint exposing `logprobs`. **Record
   applicability aggressively** — this is where the coverage result comes from, and a low number
   here is a legitimate result about RUT's deployability, not a failure of the implementation.
7. **`fuse.py` (ours)** — per-channel p-values from OTE / IRIS / GATEOPS / KBF, converted to
   e-values, multiplied into a test martingale, stopping when `E > 1/alpha`. Ville's inequality
   gives an anytime-valid Type-I guarantee with no fixed sample size — exactly what the economics
   analysis needs.

`arena/evalue.py`: empirical-CDF calibrators fit on the A0 control arm, p-to-e conversion,
martingale accumulation, sequential stopping.

**Exit criteria:** every implemented auditor runs end-to-end against the replay corpus and returns
a calibrated score, an e-value and an imputed cost.

---

## Phase 4 — Seal the protocol (45 min) — DO NOT SKIP

This phase is what separates the project from the work that failed to replicate. It is also the
single most legible signal of research maturity in the whole repository.

1. `scripts/03_calibrate.py` — using **the dev split only**, fit each auditor's threshold at a
   target FPR <= 1% on the A0 control arm.
2. `scripts/04_freeze.py` — write `config/protocol.yaml` with every threshold, print its
   **SHA-256**, commit, `git tag frozen-v1`. Put the hash in the README.
3. Encode the validity gates: minimum paired observations per cell, minimum coverage, and
   `applicable=False` → `uninformative`.
4. **Only now touch the holdout.**

Any threshold change after this point requires a new tag and must be reported as such. That
constraint is the point — you are deliberately giving up the ability to tune.

**Exit criteria:** `protocol.yaml` committed, hash in README, tag created.

---

## Phase 5 — The grid (20 min, $0)

`scripts/05_holdout.py` — 12 arms x N auditors x 3 seeds x {dev, holdout} against the replay
corpus, plus the eps-sweep {0.02, 0.05, 0.10, 0.25, 0.50} on A3 and A11.

Per cell: decision, score, e-value trajectory, queries used, imputed dollars, `eps` estimate and
backend attribution where available.

Because it replays, this is free and fast. Re-run it as often as you like — **against the frozen
thresholds only.**

---

## Phase 6 — Live confirmation (background, 1–2 h wall-clock)

Latency and metadata signals cannot be replayed, so GATEOPS and A9 need live traffic. Run a reduced
grid (A0, A1, A3@0.1, A9, A11) live through SHIM, ~100 requests per arm on Groq and Cerebras.
Cost: $0, roughly 500 requests of quota.

Stretch, if quota and time remain: the **free-tier study** from idea.md §6 — first-party endpoint
as reference, third-party re-hosts as suspects. Anonymize providers; claim *inconsistency with a
reference*, never *fraud*.

---

## Phase 7 — Figures and report (2 h)

`scripts/06_figures.py`. Six figures carry the story:

1. **F1 — Dollars-to-detection frontier.** x: imputed audit spend (log). y: power at FPR<=1%. One
   curve per auditor, faceted by arm. *The headline.*
2. **F2 — Break-even.** x: dilution eps (log). Two curves: adversary savings per $1,000 of spend,
   and audit cost to reach power 0.8. Their crossing is **eps\***, shaded below. *The quotable one.*
3. **F3 — Applicability coverage.** Stacked bars per auditor: applicable / uninformative / blocked
   across the free-tier fleet. *Straight from the Phase 0 capability matrix.*
4. **F4 — Evasion degradation.** Heatmap of auditors x arms, cell = AUROC. Columns A5/A6/A7/A9/A10
   show which methods are brittle. *The novel-attack figure.*
5. **F5 — Dev vs holdout.** Paired scatter per auditor. Replicates 2608.29930 across N methods.
   *The methodology figure.*
6. **F6 — The confound.** Score distributions for A3 (fraud) vs A11 (benign routing) per auditor,
   with overlap quantified. *What the project is actually about.*

Then write, in this order of importance:

- **`README.md`** — the deliverable most readers stop at. Must contain: the one-paragraph problem
  statement, F2 inline, a 30-second no-API-key quickstart, the frozen-threshold hash, and an
  explicit table of what was reimplemented versus what is new.
- **`REPORT.md`** — ~2,000 words. Lead with F2, not with methods. Structure: (1) you are billed for
  a model and nothing proves you received it; (2) here is a gateway that cheats and five published
  ways to catch it; (3) findings; (4) the economics — cheating below eps\* is not worth catching;
  (5) the confound — sanctioned routing looks exactly like fraud; (6) limitations, stated plainly;
  (7) run it yourself.

**Write the limitations section carefully and at length.** For this audience it is worth more than
another figure: reduced 8-cell operating point, free-tier endpoints only, no local reference model,
reimplementations labelled `-lite`, simulated rather than observed adversaries. A candidate who
states these unprompted reads as considerably stronger than one who does not.

---

## Today's schedule

| Time | Phase | Background |
|---|---|---|
| 0:00–1:00 | P0 free accounts, capability probing, roster | |
| 1:00–2:30 | P1 SHIM core + quota manager | |
| 2:30–2:45 | **launch P2 census** | census runs all day |
| 2:45–5:30 | P3 auditors 1–3 (OTE, IRIS-lite, GATEOPS) | census |
| 5:30–6:15 | break; census progresses | census |
| 6:15–7:45 | P3 auditors 4–7 (KBF, BENCH, RUT, FUSE) | census |
| 7:45–8:30 | P4 seal protocol, git tag | **launch P6 live run** |
| 8:30–8:50 | P5 grid | live run |
| 8:50–10:00 | P7 figures | |
| 10:00–11:30 | P7 README + REPORT | |

**Cut lines, in order, if you fall behind:**

1. Drop A7 (laundering) — most quota-expensive, least essential.
2. Drop BENCH and RUT — keep their coverage rows as measurements rather than runs.
3. Drop the live free-tier study — keep the simulator results.
4. Ship with **OTE + IRIS-lite + GATEOPS**, arms A0/A1/A3/A5/A11, and figures F2/F4/F6.

Cut line 4 is still a complete, honest, defensible project. It contains the economics result, a
novel attack, and the confound — every idea that makes this interesting. **Do not sacrifice the
frozen-threshold protocol (P4) or the README to save time; sacrifice auditors.** Three auditors
under a sealed protocol reads far better than seven under a tuned one.

---

## Reality check

**What one day genuinely produces:** a working adversarial gateway, a committed replay corpus of
real free-tier responses, three to seven auditors, a sealed-threshold grid, six figures, a strong
README and a written report. For a portfolio piece that is comfortably above bar — most candidates
present a fine-tuning notebook.

**What it does not produce:** an arXiv paper. The drift analysis needs repeats spaced across days,
the free-tier study needs more quota than one day allows, and positioning against IRIS needs care.
That is fine, because the stated goal is demonstrating comprehension, and the repository does that
on its own. Revisit publication in a week or two only if the results warrant it.

**One caution, stated once.** The value of this project rests on *not* tuning your way out of a bad
holdout. If the sealed thresholds produce weak numbers, report them. "Five auditing methods, one
protocol, honest degradation, and here is why" is a stronger interview conversation than a tidy
table — and any interviewer who would probe the methodology will find the sealed hash and the
`applicable` flag and reach the right conclusion about how you work.
