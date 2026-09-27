# Limitations and Conclusion

> NOTE: budget 0.5 pages. Synced from sections/*.tex after the plain-language rewrite; edit here and send back.

**Limitations.** Five matter most.
(i) *The main comparison uses simulated models.* The fitted pair takes its answers and speeds
from real measurements, but its writing habits, accuracy and honest second provider are
hand-written; detection rates in Sections [grid], [econ] and [posthoc]
describe the simulator.
(ii) *One real session per endpoint, and no drift.* Free quotas allowed one 240-request session
per endpoint, so thresholds could not be set on real traffic, and the simulator's timing never drifts
while real timing does.
(iii) *Simplified rebuilds.* None of the auditors is the authors' code. OTE uses 8 of 40
questions, IRIS-lite 16 of 179 features, KBF and BENCH 15 and 12 items, and GATEOPS leaves out
GateScope's memory test. Each result is a lower bound on the original method.
(iv) *Free endpoints, one provider, one moment.* Groq served nearly all real traffic, and the
live test used 96 requests per arm; honest load balancing could not be tested live.
(v) *Simulated cheaters.* A5 is our own design and works per request; a gateway that targets
auditing accounts would be stronger. The checks in Section [posthoc] are exploratory.

**Conclusion.** Auditing an LLM gateway is cheap, but not robust as published. A gateway that
spots test-shaped requests beats every auditor and, on chat traffic, gives up almost nothing. Judged
one session at a time, no auditor catches cheating below 10–15%; pooling sessions reaches 7% only
for an auditor that stays quiet on honest traffic, and lower only for auditors that flag honest
routing or lose to benchmark-aware cheating. Timing cannot tell cheating from honest load balancing.
Trustworthy
billing for LLM APIs will need test requests that look like normal traffic from ordinary accounts,
gateways that disclose their routing, and metering the customer can verify.

**Artifact.** The gateway, auditors, sealed rules, recorded responses and every figure are
available at an anonymised repository: [ANONYMISED LINK]. Everything except
the live test can be rerun without an API key.
