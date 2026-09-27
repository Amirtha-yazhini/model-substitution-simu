# Abstract

> NOTE: budget ~150 words. This draft is ~165. Written first so the whole paper has a target; revise last.

LLM APIs bill for a named model, but nothing in a response proves which model produced it. An
intermediary can serve a cheaper model on some requests and still bill for the expensive one. At least eight black-box detectors have been proposed, each
evaluated on its own testbed and against its own adversary. We built SHIM, an OpenAI-compatible
gateway with twelve switchable cheating strategies and a hidden ground-truth ledger, and ARENA,
which runs five reimplemented detectors and a new e-value fusion under thresholds sealed by SHA-256
before evaluation. On 11 free-tier endpoints, the logprob-based detector runs on none and the
one-token method as published on 4. A gateway that answers audit-shaped requests honestly keeps
every detector at chance (AUROC ≤ 0.61). Audits cost under one cent, yet no admissible audit
detects substitution on fewer than 10% of requests, which still saves the gateway 8.8% of the bill.
Timing detectors also flag benign load balancing more often than fraud.
