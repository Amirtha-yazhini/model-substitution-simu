# Introduction and Threat Model

> NOTE: budget 0.75 pages. Synced from sections/*.tex after the plain-language rewrite; edit here and send back.

When a customer calls an LLM API, they name a model and pay that model's price per token. The
response contains text and repeats the model's name, but it proves nothing about which model
actually produced the text. A gateway, reseller or router that sits between the customer and the
model provider can answer with a smaller model, a compressed (quantised) copy, or a mix of models,
and still report the name the customer asked for. The incentive is large. In our setup the cheaper
model costs 11.5% of the genuine one, so a gateway that swaps one request in ten saves about \$88
for every \$1,000 the customer spends.

The customer pays for "model X", but the only record of what ran is the gateway's own word. The
provider could prove what ran using secure hardware [@cai2025], but gateways do not offer this
today, and the customer cannot look inside the gateway. What the customer can do is test the
answers. A black-box *auditor* sends test requests (*probes*) and decides, from the text,
timing and metadata that come back, whether the advertised model answered.

At least eight such auditors have been published since April 2025
 [@cai2025; @zhu2025rut; @lin2026gatescope; @fang2026kbf; @bruckner2026; @iris2026; @difr2025].
Each was tested on its own data, against its own simulated cheater, and usually with thresholds
chosen on the same data it reports. A replication study that fixed its thresholds in
advance [@holdout2026] showed why this matters: a method that was perfect on its development
data recognised only half of the same-family model pairs in fresh data, and could not score half of
the fresh cases at all. The auditors have never been compared on the same data against the same
cheater. Only one has been tested against a gateway that tries to spot its test requests, and only
against its own probes [@iris2026].

**Threat model.** The customer sends requests over HTTPS to a gateway that advertises model
$M$. For each request the gateway decides where it goes: to $M$, to a cheaper substitute $M'$, to
another provider of $M$, or to a cache of earlier answers. It can change the reported model name,
the `usage` token counts and the `system_fingerprint` field, and it can add delay. It
sees every request, so it can guess which requests are tests from how they look. It does not know
the auditor's exact probes or thresholds, but it knows the published methods and the public
benchmarks. Its goal is to save as much as possible without being caught. The customer sees only
what comes back: the text, how long the answer took, the `usage` block, the fingerprint, and
token probabilities (logprobs) if the endpoint provides them. Response time is a side channel the
customer can always measure, and the text is the only other signal. Honest variation, such as
spreading traffic across several legitimate providers of $M$, is allowed and should not be flagged.

**Contributions.**
- *A shared test gateway.* SHIM, a drop-in OpenAI-compatible gateway that can cheat in
  twelve ways. Three of them (restyling cheap answers, recognising benchmark questions, and
  honest load balancing) have never been evaluated before, and a fourth (hiding from tests) only
  against one auditor's own probes. A hidden log records which
  model really answered each request.
- *A fair comparison of six auditors.* Five published methods, rebuilt from their papers,
  and one new method that combines them. All thresholds were fixed and fingerprinted before testing,
  and an auditor that cannot run reports *uninformative*, never *pass*.
- *Which auditors work on real endpoints.* On 11 free endpoints, a method that needs token
  probabilities runs on none, and the cheapest published method runs as described on only 4,
  because models now "think" silently before answering.
- *Three negative results.* A gateway that hides from tests beats every auditor. False
  alarms, not cost, mean nobody can catch cheating on fewer than about 10% of requests. And
  timing-based auditors cannot tell cheating from honest load balancing.
