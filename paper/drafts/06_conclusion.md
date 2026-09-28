# Limitations and Conclusion

> NOTE: budget 0.5 pages (~380 words). This draft is ~410.

**Limitations.** Five matter most.
(i) *The grid runs on simulated models.* Calibration, holdout, grid, dilution sweep and confound use
SHIM's mock backend. The fitted ladder takes answer distributions and latency from real
measurements, but surface habits and accuracy remain hand-written, and the post-hoc IRIS-lite check
shows this can move $\epsilon^*$. Real endpoints decide the coverage, real-response and live results;
the grid's power numbers describe the mock.
(ii) *One real session per endpoint.* Free-tier quotas bought one 240-request session per endpoint,
so thresholds could not be calibrated on real traffic, and real-endpoint results use permutation
p-values rather than sealed thresholds.
(iii) *Reimplementations at reduced operating points.* None of the auditors is the authors' code.
OTE uses 8 of 40 cells, IRIS-lite 16 of 179 features, KBF and BENCH 15 and 12 items, and GATEOPS
omits GateScope's memory channel. Each number is a lower bound on the original method.
(iv) *Free tier, one moment.* Groq served nearly all real traffic; other providers returned payment
errors or exhausted daily quotas. Free tiers change monthly.
(v) *Simulated adversaries and a small live run.* A5 is our classifier; a real one could be better or
worse. The live run is 96 requests per arm on one provider, and benign routing could not run live.

**Conclusion.** We ran five published model-substitution auditors and one new fusion on a common
adversarial gateway under thresholds sealed before evaluation. Auditing is cheap: sessions cost well
under a cent. It is not robust: a gateway that recognises audit-shaped requests keeps every auditor
at chance, and the shape it recognises is what makes probes cheap. Below $\epsilon^* \approx$
0.10–0.15 no admissible audit detects dilution, because false-positive budgets, not cost, limit
repetition. And timing auditors flag sanctioned routing more readily than fraud, which separates
identity violations, which content can reveal, from disclosure and billing violations, which it
cannot. Verifiable accounting for LLM APIs will need probes indistinguishable from production
traffic, disclosure of routing, and attested metering; black-box statistics alone cannot supply the
last two.

**Artifact.** The gateway, auditors, sealed protocols, replay corpus and every figure are available
at an anonymised repository: https://anonymous.4open.science/r/model-substitution-simu-0F5B. All results except the
live run regenerate without an API key.
