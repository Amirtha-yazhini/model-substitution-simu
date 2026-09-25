# v2 economics and eps*

Protocol v2 `534a56f27c154bbd...` (tag `frozen-v2`). Decision: score > sealed max of 300 honest sessions; FUSE at e >= 100. Intervals are Wilson 95%.

Rules sealed in protocol v2: power target 80%, family FPR budget 5%, per-session FPR = holdout rate floored at 0.0033, saving = $1,000 x eps x (1 - price ratio). Bootstrap: 2000 replicates over sessions.


## hand-written mock

Price ratio substitute/genuine: **0.115**. **eps\* = 0.1**, bootstrap 95% interval [0.1, 0.1]. Winner: IRIS-lite (4 sessions, power/session 34%, $0.0060).

Bootstrap distribution of eps*: 0.07: 0.5%, 0.1: 99.5%

| Auditor | holdout flags | f used | max admissible sessions | cost/session USD |
|---|---|---|---|---|
| OTE | 2/500 | 0.40% | 12 | 0.00283 |
| IRIS-lite | 2/500 | 0.40% | 12 | 0.00150 |
| GATEOPS | 0/500 | 0.33% | 15 | 0.00283 |
| KBF | 4/500 | 0.80% | 6 | 0.00132 |
| BENCH | 2/500 | 0.40% | 12 | 0.00252 |
| FUSE | 0/500 | 0.33% | 15 | 0.01381 |

## fitted mock

Price ratio substitute/genuine: **0.115**. **eps\* = 0.1**, bootstrap 95% interval [0.1, 0.1]. Winner: IRIS-lite (2 sessions, power/session 56%, $0.0030).

Bootstrap distribution of eps*: 0.1: 100.0%

| Auditor | holdout flags | f used | max admissible sessions | cost/session USD |
|---|---|---|---|---|
| OTE | 0/500 | 0.33% | 15 | 0.00283 |
| IRIS-lite | 1/500 | 0.33% | 15 | 0.00150 |
| GATEOPS | 0/500 | 0.33% | 15 | 0.00283 |
| KBF | 4/500 | 0.80% | 6 | 0.00132 |
| BENCH | 2/500 | 0.40% | 12 | 0.00252 |
| FUSE | 0/500 | 0.33% | 15 | 0.01381 |
