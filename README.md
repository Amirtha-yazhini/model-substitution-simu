# SHIM — Who's Actually Answering?

**An adversarial LLM-gateway simulator and auditor benchmark. Runs on free API tiers. Costs $0.**

You pay for a specific model through an API. Nothing in the response proves you got it. Since
April 2025, eight papers have proposed ways to detect when a provider quietly serves something
cheaper — but every one was evaluated on its own testbed, against its own adversary, with
thresholds tuned on the data it reports. None were compared against each other.

This repository is the benchmark they should have been evaluated on.

- **SHIM** — an OpenAI-compatible gateway that misbehaves on command across 12 adversary arms,
  backed by real free-tier model responses.
- **ARENA** — auditors reimplemented from five papers, run against SHIM under a pre-registered,
  SHA-256-sealed frozen-threshold protocol.

Because SHIM knows the true backend of every request, ARENA can compute real ROC curves — which no
real-world audit can, since real audits have no ground truth.

See [idea.md](idea.md) for the research framing and [plan.md](plan.md) for the execution plan.

---

## Status

Phases 0 and 1 of 8 complete. This is an in-progress build.

| Phase | State |
|---|---|
| 0. Setup, capability probing | **done** — see [coverage results](results/tables/coverage.md) |
| 1. SHIM gateway core (arms A0–A11) | **done** — all 12 arms pass acceptance tests |
| 2. Probe census / replay corpus | not started |
| 3. Auditors (OTE, IRIS-lite, GATEOPS, KBF, BENCH, RUT, FUSE) | in progress — OTE done, [results](results/tables/ote_arms.md) |
| 4. Seal thresholds (SHA-256 + git tag) | not started |
| 5. Evaluation grid | not started |
| 6. Live confirmation run | not started |
| 7. Figures + report | not started |

---

## Quickstart

Once the corpus is committed (Phase 2), every figure reproduces with **no API key**. Until then,
reproducing the capability measurement needs free keys.

```bash
python -m venv .venv
.venv/Scripts/activate          # Windows;  source .venv/bin/activate on Unix
pip install -r requirements.txt

cp .env.example .env            # then paste in your free keys
python scripts/00_keys.py       # which keys are present? (0 API calls)
python scripts/01_limits.py     # dry run: prints the quota plan, fires nothing
python scripts/01_limits.py --yes
```

All providers used are **free tiers with no credit card**. Signup links are in
[config/providers.yaml](config/providers.yaml).

| Provider | Free limit | Role here |
|---|---|---|
| Groq | 1,000 RPD, 30 RPM | **Primary census engine** + latency baselines |
| Mistral | ~1B tokens/month, 2 RPM | **First-party reference** (ground truth) |
| Google AI Studio | up to 1,500 RPD | **First-party reference** |
| OpenRouter | 20 RPM, **50 RPD** | Rationed — Nemotron ladder + the Auto Exacto arm |
| GitHub Models | 50–150 RPD | Model breadth (optional) |
| ~~Cerebras~~ | — | Returns HTTP 402 (payment required) as of 2026-09-08 |

Quota, not money, is the scarce resource. `01_limits.py` refuses to make calls without `--yes` and
prints its request budget first.

---

## Result #1: auditor applicability across the free-tier fleet

`scripts/01_limits.py` measures what each endpoint can actually do. This is not setup — it decides
**which auditors can run at all**, and no paper in this literature reports it for its own method.

Measured on 11 working endpoints ([full table](results/tables/coverage.md)):

| Auditor | Requires | Coverage |
|---|---|---|
| IRIS-lite / KBF / BENCH / GATEOPS-latency | text or timing only | **100%** |
| OTE @256 tok (adapted) | text only | **91%** |
| OTE @16 tok (**as published**) | no hidden reasoning | **36%** |
| GateScope billing dimension | `usage.cached_tokens` | **18%** |
| **RUT** | logprobs | **0%** |

Two findings fall straight out of this:

**RUT is undeployable on this fleet.** Not a single free endpoint returns logprobs. Its paper
already notes it needs a locally deployed reference model; measured against real endpoints, the
requirement is not merely inconvenient but disqualifying. DiFR, which needs raw logits, is worse off
still.

**Hidden reasoning has repriced the cheapest auditing method.** 4 of 11 endpoints spend 26–36 tokens
thinking before emitting an answer. Bruckner's published protocol caps completions at 16 tokens — on
those endpoints it returns an *empty string* with `finish_reason=length`, so the probe fails rather
than answers. He reported excluding 0.76% of his census for reasoning traces; here it is 36%. Per-probe
cost rises from ~16 tokens to ~45, which inflates the audit side of the break-even analysis directly:
the cheapest known method got more expensive because the fleet changed, not because the method did.

<sub>Incidental: all four reasoning models answered **42** — Bruckner's documented GPT-family bias,
apparently surviving across families. Single observations each; the census will tell us if it holds.</sub>

---

## Layout

```
config/      providers, model ladders, prices, sealed protocol
shim/        the adversarial gateway (server, arm policies, quota, ledger)
arena/       auditors, probes, e-values, frozen-threshold runner
corpus/      committed replay corpus - what makes results reproducible offline
results/     figures, tables, audit trail
scripts/     00_keys  01_limits  02_census  03_calibrate  04_freeze  05_holdout  06_figures
```

## Reimplemented vs. new

Auditors are labelled `-lite` because they are reimplementations, not the authors' code; treat
their numbers as lower bounds on the original methods. Deltas from each original are documented in
[idea.md](idea.md).

**New here:** the 12-arm adversary taxonomy (arms A5 probe-aware evasion, A7 laundering, and A10
canary-awareness are attacks no source paper evaluates), the audit-economics break-even analysis,
the FUSE behavioural×operational fusion auditor, and arm A11 — benign quality routing scored as a
false-positive arm, testing whether any auditor can distinguish fraud from sanctioned routing.

## Ethics

Any live-endpoint findings anonymise the provider and claim *statistical inconsistency with a
reference*, never *fraud*. Endpoints differ for many innocent reasons — engine version, tool-call
parser, disclosed quantization. See [idea.md](idea.md) §6.
