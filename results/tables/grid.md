# Auditors x arms, against the sealed protocol

Protocol SHA-256 `923a3d217470a347be94fbef29f419f79f08ed9f6c6fbf506d1f7f49ebdb51c0` (tag `frozen-v1`), alpha=0.01. No threshold was fitted after sealing.

**F** = flagged (inconsistent), `.` = clean, `u` = uninformative (the auditor could not run - never scored as a pass).

Majority over 3 seeds. `truth` is the ground-truth label from the ledger, which no auditor can see.

| Arm | Name | truth | OTE | IRIS-lite | GATEOPS | KBF | BENCH | RUT | FUSE |
|---|---|---|---|---|---|---|---|---|---|
| A0 | honest | genuine | . | . | . | . | . | u | . |
| A1 | full_substitution | **substitution** | **F** | **F** | **F** | **F** | **F** | u | **F** |
| A2 | quantization_swap | **substitution** | . | . | **F** | . | . | u | **F** |
| A3 | dilution | **substitution** | . | . | **F** | . | . | u | . |
| A4 | sampler_retune | genuine | **F** | . | . | . | . | u | **F** |
| A5 | probe_aware_evasion | **substitution** | . | . | . | . | . | u | . |
| A6 | cache_replay | **substitution** | **F** | **F** | u | **F** | **F** | u | **F** |
| A7 | laundering | **substitution** | **F** | **F** | **F** | **F** | **F** | u | **F** |
| A8 | billing_manipulation | **substitution** | **F** | **F** | **F** | **F** | **F** | u | **F** |
| A9 | latency_shaping | **substitution** | **F** | **F** | **F** | **F** | **F** | u | **F** |
| A10 | canary_aware | **substitution** | **F** | **F** | **F** | **F** | . | u | **F** |
| A11 | benign_quality_routing | genuine | . | . | **F** | . | . | u | . |

## Realised false-positive rate on the untouched holdout

| Auditor | flagged | applicable sessions | FPR | target |
|---|---|---|---|---|
| OTE | 0 | 50 | 0.0% | <= 1.0% |
| IRIS-lite | 0 | 50 | 0.0% | <= 1.0% |
| GATEOPS | 5 | 50 | 10.0% | <= 1.0% |
| KBF | 2 | 50 | 4.0% | <= 1.0% |
| BENCH | 2 | 50 | 4.0% | <= 1.0% |
| RUT | 0 | 0 | n/a | <= 1.0% |
| FUSE | 0 | 50 | 0.0% | <= 1.0% |

## Median scores

| Arm | OTE | IRIS-lite | GATEOPS | KBF | BENCH | RUT | FUSE |
|---|---|---|---|---|---|---|---|
| A0 | -0.013 | +0.000 | +0.050 | +0.000 | +0.000 | - | -1.166 |
| A1 | +0.199 | +1.000 | +0.979 | +0.320 | +0.217 | - | +19.470 |
| A2 | +0.003 | +0.000 | +0.358 | +0.027 | +0.000 | - | +5.027 |
| A3 | +0.003 | +0.092 | +0.133 | +0.080 | +0.000 | - | +0.447 |
| A4 | +0.424 | +0.017 | +0.050 | +0.000 | +0.000 | - | +4.255 |
| A5 | -0.011 | +0.000 | +0.050 | +0.000 | +0.000 | - | -1.244 |
| A6 | +0.505 | +1.000 | - | +0.427 | +0.283 | - | +17.734 |
| A7 | +0.199 | +0.125 | +0.696 | +0.320 | +0.217 | - | +14.587 |
| A8 | +0.199 | +1.000 | +0.979 | +0.320 | +0.217 | - | +19.470 |
| A9 | +0.199 | +1.000 | +0.358 | +0.320 | +0.217 | - | +19.470 |
| A10 | +0.199 | +1.000 | +0.979 | +0.320 | +0.000 | - | +18.387 |
| A11 | +0.005 | +0.000 | +0.175 | +0.027 | +0.000 | - | +0.697 |
