# v2 holdout: realised false-positive rate

Protocol v2 `534a56f27c154bbd...` (tag `frozen-v2`). Decision: score > sealed max of 300 honest sessions; FUSE at e >= 100. Intervals are Wilson 95%.

| Auditor | FPR, hand-written mock | FPR, fitted mock | threshold, mock | threshold, mock-fit |
|---|---|---|---|---|
| OTE | 2/500 = 0.4% [0.1, 1.4] | 0/500 = 0.0% [0.0, 0.8] | +0.0206 | +0.0228 |
| IRIS-lite | 2/500 = 0.4% [0.1, 1.4] | 1/500 = 0.2% [0.0, 1.1] | +0.0917 | +0.0583 |
| GATEOPS | 0/500 = 0.0% [0.0, 0.8] | 0/500 = 0.0% [0.0, 0.8] | +0.1458 | +0.1333 |
| KBF | 4/500 = 0.8% [0.3, 2.0] | 4/500 = 0.8% [0.3, 2.0] | +0.1333 | +0.1333 |
| BENCH | 2/500 = 0.4% [0.1, 1.4] | 2/500 = 0.4% [0.1, 1.4] | +0.0500 | +0.0500 |
| FUSE | 0/500 = 0.0% [0.0, 0.8] | 0/500 = 0.0% [0.0, 0.8] | +100.0000 | +100.0000 |
