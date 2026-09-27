# Introduction and Threat Model

> NOTE: budget 0.75 pages (~550 words of prose). This draft is ~600.
> NOTE: Phase 2 items.
> Working title: **Who's Actually Answering? Stress-Testing LLM Model-Substitution Auditors Against an Adversarial Gateway**
> Alternative: *Billed for One Model, Served Another: A Sealed-Protocol Benchmark of Model-Substitution Detectors*
> One-sentence finding: *Auditing an LLM gateway is cheap, but a gateway that recognises audit-shaped requests defeats every published detector, and below a 10% substitution rate no detector can catch it without unacceptable false alarms.*

A client of an LLM API names a model, pays that model's per-token price, and receives text together
with a response that repeats the model's name. Nothing in that response is evidence. A gateway,
reseller or router between the client and the model provider can serve a smaller model, a
quantised copy, or a mix of both, and still return the name the client asked for. The incentive is
large. For the token mix used in this paper, the substitute costs 11.5% of the genuine model, so a
gateway that swaps on one request in ten saves about \$88 per \$1,000 of billed traffic.

The client pays for "model X", but the only record of what ran is the gateway's own word. The
provider behind the gateway could attest to the computation in hardware [@cai2025], but gateways
do not offer this today, and the client cannot inspect the gateway. What the client can do is test
the responses. A black-box *auditor* sends probe requests and decides, from the text, timing and
metadata that come back, whether the advertised model answered.

At least eight such auditors have appeared since April 2025
[@cai2025; @zhu2025rut; @lin2026gatescope; @fang2026kbf; @bruckner2026; @iris2026; @difr2025].
Each was evaluated on its own testbed, against its own adversary, usually with thresholds chosen on
the data it reports. A frozen-threshold replication [@holdout2026] showed how fragile that is: a
method with perfect development accuracy fell to 50% sensitivity on fresh model pairs, and half of
those pairs could not be scored at all. The auditors have never been compared on one testbed
against one adversary, and none has been tested against a gateway that knows it may be audited.

**Threat model.** The client sends requests over HTTPS to a gateway that advertises model $M$. The
gateway controls routing and response metadata. For each request it may forward to $M$, to a
cheaper substitute $M'$, to another provider of $M$, or to a cache. It may rewrite the reported
model name, the `usage` token counts and `system_fingerprint`, and it may add delay. It can read
every request, so it can classify requests by their shape. It does not know the auditor's
particular probes or thresholds, but it knows the published methods and the public benchmarks. Its
goal is to maximise savings while keeping the probability of detection low. The client observes
only what crosses the wire: response text, client-side latency, the `usage` block, the
fingerprint, and logprobs where the endpoint exposes them. Timing is therefore a side channel the
client can measure without the gateway's cooperation, and content is the only other signal.
Honest variation, such as load balancing across legitimate providers of $M$, is allowed and must not
be flagged.

**Contributions.**

- **A shared adversarial testbed.** SHIM, an OpenAI-compatible gateway with twelve adversary arms,
  four of which (probe-aware evasion, laundering, canary-awareness and benign routing) appear in no
  prior evaluation, and a hidden ledger that records which backend really answered.
- **A sealed comparison of six auditors.** Five published methods reimplemented and one new e-value
  fusion, evaluated under thresholds hashed and tagged before evaluation, where an auditor that
  cannot run reports *uninformative*, never *pass*.
- **Measured deployability on real endpoints.** On 11 free-tier endpoints, a logprob-based auditor
  runs on 0 and the one-token method as published on 4, because hidden reasoning consumes the
  token budget.
- **Three negative results.** Probe-aware evasion keeps every auditor at chance. False-positive
  budgets, not audit cost, set a dilution floor of $\epsilon^* \approx 0.10$. Timing auditors
  cannot tell fraud from sanctioned routing, which splits "substitution" into identity, disclosure
  and billing violations.
