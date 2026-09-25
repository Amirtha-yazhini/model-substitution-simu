# v2 confound: A3 at eps = 0.10 vs A11 (benign routing)

Protocol v2 `534a56f27c154bbd...` (tag `frozen-v2`). Decision: score > sealed max of 300 honest sessions; FUSE at e >= 100. Intervals are Wilson 95%.


## hand-written mock (200 sessions each)

| Auditor | flags A3 | flags A11 | AUROC A3 vs A11 |
|---|---|---|---|
| OTE | 4% [2, 8] | 0% [0, 2] | 0.68 |
| IRIS-lite | 34% [27, 40] | 0% [0, 2] | 0.96 |
| GATEOPS | 18% [13, 23] | 96% [93, 98] | 0.03 |
| KBF | 2% [1, 5] | 2% [1, 4] | 0.63 |
| BENCH | 2% [1, 5] | 0% [0, 3] | 0.53 |
| FUSE | 2% [1, 4] | 5% [3, 9] | 0.35 |

## fitted mock (200 sessions each)

| Auditor | flags A3 | flags A11 | AUROC A3 vs A11 |
|---|---|---|---|
| OTE | 0% [0, 2] | 0% [0, 2] | 0.48 |
| IRIS-lite | 56% [49, 62] | 0% [0, 2] | 0.98 |
| GATEOPS | 5% [3, 9] | 100% [98, 100] | 0.00 |
| KBF | 2% [1, 5] | 2% [1, 4] | 0.63 |
| BENCH | 2% [1, 5] | 0% [0, 3] | 0.53 |
| FUSE | 0% [0, 2] | 50% [44, 57] | 0.01 |
