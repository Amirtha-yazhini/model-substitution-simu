# Introduction and Threat Model

> NOTE: budget 0.75 pages. Synced from sections/*.tex after the plain-language rewrite; edit here and send back.

When a customer calls an LLM API, they name a model and pay that model's price per token. The
response contains text and repeats the model's name, but it proves nothing about which model
actually produced the text. A gateway, reseller or router that sits between the customer and the
model provider can answer with a smaller model, a compressed (quantised) copy, or a mix of models,
and still report the name the customer asked for. The incentive is large. For the two model pairs in this paper the cheaper
model costs 11.5% (Llama 3.3 70B vs. 3.1 8B, used to price our simulator) or 50% (gpt-oss-120b
vs. 20b, the real pair we measure) of the genuine one, so a gateway that swaps one request in ten
saves \$50–\$88 for every \$1,000 the customer spends.

The customer pays for "model X", but the only record of what ran is the gateway's own word. The
provider could prove what ran using secure hardware [@cai2025], but gateways do not offer this
today, and the customer cannot look inside the gateway. What the customer can do is test the
answers. A black-box *auditor* sends test requests (*probes*) and decides, from the text,
timing and metadata that come back, whether the advertised model answered.

At least six black-box auditors have been published since April 2025
 [@cai2025; @zhu2025rut; @lin2026gatescope; @fang2026kbf; @bruckner2026; @iris2026], alongside a method that
needs the provider's cooperation [@difr2025]. Each was tested on its own data, against its own simulated cheater, and usually with thresholds
chosen on the same data it reports; a replication with thresholds fixed in advance found far weaker
results [@holdout2026]. The auditors have never been compared on the same data against the same
cheater. Only one has been tested against a gateway that tries to spot its test requests, and only
against its own probes [@iris2026].

**Threat model.** The customer sends requests over HTTPS to a gateway that advertises model
$M$. For each request the gateway decides where it goes: to $M$, to a cheaper substitute $M'$, to
another provider of $M$, or to a cache of earlier answers. It can change the reported model name,
the `usage` token counts and the `system_fingerprint` field, and it can add delay. It
sees every request, so it can guess which requests are tests from how they look. It also knows which
customer account sent each request; we model evasion per request (A5), and a gateway that serves the
genuine model to any account that ever sends test-like traffic would be stronger still. It does not know
the auditor's exact probes or thresholds, but it knows the published methods and the public
benchmarks. Its goal is to save as much as possible without being caught. We assume the customer can obtain
honest answers from the genuine model, for example from its first-party provider, to use as a
reference. The customer sees only
what comes back: the text, how long the answer took, the `usage` block, the fingerprint, and
token probabilities (logprobs) if the endpoint provides them. Response time is a side channel the
customer can always measure, though through the gateway's own network and queueing noise; the text is
the only other signal. Honest variation, such as
spreading traffic across several legitimate providers of $M$, is allowed and should not be flagged.

**Contributions.**
- *A shared, sealed testbed.* SHIM, a drop-in gateway that can cheat in twelve ways and logs
  which model really answered, and ARENA, which runs six auditors under thresholds fixed and
  fingerprinted before testing; an auditor that cannot run reports *uninformative*, never
  *pass*.
- *Deployability on real endpoints.* On 11 free endpoints a logprob-based auditor runs on
  none and the cheapest published method on 4, because models now "think" silently before
  answering; the real speed gap between a large and a small model is 18%, not 3$\times$.
- *Three limits of black-box auditing.* Test-shaped evasion beats every auditor; judged one
  session at a time, no auditor catches cheating below 10–15%; and timing cannot tell cheating from
  honest load balancing. Post-hoc checks (Section [posthoc]) price the evasion and show how
  far pooling and disguised tests move these limits.
