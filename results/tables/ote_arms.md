# OTE-lite vs the 12 adversary arms (mock backend)

Probes: 8 cells x 30 repeats = 240 per arm.

Statistic is the **permutation-debiased** mean Jensen-Shannon divergence (200 permutations per cell). The plug-in JSD it corrects is upward-biased at 30 samples/cell - it scored honest-vs-honest at 0.1755, above four of the twelve arms. `raw` is the uncorrected statistic, kept because it is what Bruckner thresholds.

Threshold: the maximum over **100 independent honest calibration sessions** = **+0.0152**. Under exchangeability that is a conformal FPR bound of 1/101 = 0.99%. Measured on **50 disjoint holdout sessions**: realised FPR **0/50 = 0.0%**.

| Arm | Name | Debiased JSD | raw JSD | Fisher p | vs threshold | True substitution rate |
|---|---|---|---|---|---|---|
| A0 | honest | -0.0128 | 0.1860 | 1.0e+00 | clean | 0/240 |
| A1 | full_substitution | +0.1819 | 0.3584 | 1.5e-05 | **FLAGGED** | 240/240 |
| A2 | quantization_swap | +0.0051 | 0.1843 | 6.4e-01 | clean | 240/240 |
| A3 | dilution | +0.0000 | 0.1858 | 5.5e-01 | clean | 30/240 |
| A4 | sampler_retune | +0.4243 | 0.5395 | 2.2e-11 | **FLAGGED** | 0/240 |
| A5 | probe_aware_evasion | -0.0210 | 0.1569 | 1.0e+00 | clean | 6/240 |
| A6 | cache_replay | +0.5560 | 0.6748 | 2.2e-11 | **FLAGGED** | 240/240 |
| A7 | laundering | +0.1745 | 0.3530 | 1.1e-04 | **FLAGGED** | 240/240 |
| A8 | billing_manipulation | +0.2119 | 0.4023 | 1.5e-04 | **FLAGGED** | 240/240 |
| A9 | latency_shaping | +0.1890 | 0.3741 | 5.2e-04 | **FLAGGED** | 240/240 |
| A10 | canary_aware | +0.2238 | 0.4123 | 1.0e-05 | **FLAGGED** | 240/240 |
| A11 | benign_quality_routing | -0.0029 | 0.1852 | 9.1e-01 | clean | 0/240 |

## Footnotes

**A2 and A11 route to the same backend under opposite labels.** Both serve `alternate-70b`; A2 is labelled substitution (the deployment differs) and A11 is labelled genuine (the weights are correct). Their responses are therefore draws from one distribution, and *no* behavioural auditor can separate them. This is a deliberate ceiling in the taxonomy, not a defect in any method - and it is the sharpest form of the confound in idea.md section 5. Pooling A2 with A11 in a ROC curve caps AUROC below 1 by construction; the evaluation grid must report them separately.

**The Fisher p-value combines per-cell permutation p-values** across the 8 cells. Cells are independently sampled prompts, so the independence assumption holds by construction here - which is also why Bruckner's battery gains power by adding cells rather than repeats.

