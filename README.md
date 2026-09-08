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

Phase 0 of 8 complete. This is an in-progress build.

| Phase | State |
|---|---|
| 0. Setup, capability probing | **done** — scaffolding, provider client, coverage prober |
| 1. SHIM gateway core (arms A0–A11) | not started |
| 2. Probe census / replay corpus | not started |
| 3. Auditors (OTE, IRIS-lite, GATEOPS, KBF, BENCH, RUT, FUSE) | not started |
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
| Cerebras | ~1M tokens/day, 30 RPM | Primary census engine |
| Groq | 1,000 RPD, 30 RPM | Second engine + latency baselines |
| Mistral | ~1B tokens/month, 2 RPM | **First-party reference** (ground truth) |
| Google AI Studio | up to 1,500 RPD | **First-party reference** (Gemma) |
| GitHub Models | 50–150 RPD | Model breadth |
| OpenRouter | 20 RPM, **50 RPD** | Rationed — the Auto Exacto arm only |

Quota, not money, is the scarce resource. `01_limits.py` refuses to make calls without `--yes` and
prints its request budget first.

---

## Why the capability probe is a result, not setup

`scripts/01_limits.py` measures what each endpoint can actually do — does it return `logprobs`?
`usage.cached_tokens`? `system_fingerprint`? does it honour `max_tokens`? does it leak reasoning
traces? These are not incidental: they decide **which auditors can run at all**.

RUT needs a logprob-exposing reference. GateScope's billing dimension needs cached-token
accounting. Bruckner's single-token method breaks on endpoints that emit reasoning traces. No paper
in this literature reports how much of the real endpoint fleet it can actually be deployed on. The
generated `results/tables/coverage.md` is that measurement.

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
