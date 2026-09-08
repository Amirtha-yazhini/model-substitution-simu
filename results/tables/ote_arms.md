# OTE-lite vs the 12 adversary arms (mock backend)

Probes: 8 cells x 30 repeats = 240 per arm. Null: 20 independent honest sessions vs the same reference.

Null ceiling (p95): **0.1900**  |  null mean: 0.1755

| Arm | Name | Mean JSD | vs null | True substitution rate |
|---|---|---|---|---|
| A0 | honest | 0.1987 | **FLAGGED** | 0/240 |
| A1 | full_substitution | 0.3826 | **FLAGGED** | 240/240 |
| A2 | quantization_swap | 0.1544 | clean | 240/240 |
| A3 | dilution | 0.1839 | clean | 30/240 |
| A4 | sampler_retune | 0.5395 | **FLAGGED** | 0/240 |
| A5 | probe_aware_evasion | 0.1508 | clean | 6/240 |
| A6 | cache_replay | 0.6113 | **FLAGGED** | 240/240 |
| A7 | laundering | 0.3884 | **FLAGGED** | 240/240 |
| A8 | billing_manipulation | 0.3919 | **FLAGGED** | 240/240 |
| A9 | latency_shaping | 0.3831 | **FLAGGED** | 240/240 |
| A10 | canary_aware | 0.3779 | **FLAGGED** | 240/240 |
| A11 | benign_quality_routing | 0.1848 | clean | 0/240 |
